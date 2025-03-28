# sync/playbyplay_sync.py
from datetime import datetime
from typing import Dict, List, Any, Tuple, Set
import json
import concurrent.futures
import threading
from nba.fetcher.game_fetcher import GameFetcher
from utils.logger_handler import AppLogger
from database.models.stats_models import Event, GameStatsSyncHistory
from database.db_session import DBSession


class PlayByPlaySync:
    """
    比赛回合数据同步器
    负责从NBA API获取数据、转换并写入数据库
    支持并发同步多场比赛
    处理早期比赛无playbyplay数据的情况
    """

    def __init__(self, playbyplay_repository=None, game_fetcher=None):
        """初始化比赛回合数据同步器"""
        self.db_session = DBSession.get_instance()
        self.playbyplay_repository = playbyplay_repository
        self.game_fetcher = game_fetcher or GameFetcher()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def sync_playbyplay(self, game_id: str, force_update: bool = False) -> Dict[str, Any]:
        """
        同步指定比赛的回合数据

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新，默认为False

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info(f"开始同步比赛(ID:{game_id})的Play-by-Play数据...")

        try:
            # 获取playbyplay数据
            playbyplay_data = self.game_fetcher.get_playbyplay(game_id, force_update)
            
            # 如果无法获取数据，将其视为早期比赛（没有play-by-play数据）
            if not playbyplay_data:
                # 记录为成功但无数据可用
                summary = {"message": "没有可用的Play-by-Play数据，可能是早期比赛"}
                self._record_sync_history(game_id, "success", start_time, datetime.now(), 0, summary)
                
                self.logger.info(f"比赛(ID:{game_id})没有可用的Play-by-Play数据，已记录为同步成功")
                return {
                    "status": "success",
                    "items_processed": 0,
                    "items_succeeded": 0,
                    "summary": summary,
                    "start_time": start_time.isoformat(),
                    "end_time": datetime.now().isoformat(),
                    "no_data": True
                }

            # 解析和保存数据
            success_count, summary = self._save_playbyplay_data(game_id, playbyplay_data)

            end_time = datetime.now()
            status = "success" if success_count > 0 else "failed"

            # 记录同步历史
            self._record_sync_history(game_id, status, start_time, end_time, success_count, summary)

            self.logger.info(f"比赛(ID:{game_id})Play-by-Play数据同步完成，状态: {status}")
            return {
                "status": status,
                "items_processed": 1,
                "items_succeeded": success_count,
                "summary": summary,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }

        except Exception as e:
            error_msg = f"同步比赛(ID:{game_id})Play-by-Play数据失败: {e}"
            self.logger.error(error_msg, exc_info=True)

            # 记录失败的同步历史
            self._record_sync_history(game_id, "failed", start_time, datetime.now(), 0, {"error": str(e)})

            return {
                "status": "failed",
                "items_processed": 1,
                "items_succeeded": 0,
                "error": str(e)
            }

    def batch_sync_playbyplay(self, game_ids: List[str], force_update: bool = False, 
                                max_workers: int = 10, batch_size: int = 50) -> Dict[str, Any]:
            """
            并行同步多场比赛的Play-by-Play数据
            
            Args:
                game_ids: 比赛ID列表
                force_update: 是否强制更新缓存
                max_workers: 最大工作线程数
                batch_size: 批处理大小
                
            Returns:
                Dict: 同步结果摘要
            """
            start_time = datetime.now()
            self.logger.info(f"开始批量同步{len(game_ids)}场比赛的Play-by-Play数据，最大线程数: {max_workers}")
            
            # 结果统计
            result = {
                "start_time": start_time.isoformat(),
                "total_games": len(game_ids),
                "successful_games": 0,
                "failed_games": 0,
                "skipped_games": 0,
                "no_data_games": 0,
                "details": []
            }
            
            # 检查已同步的比赛，避免重复同步
            synced_game_ids = self._get_synced_game_ids()
            games_to_sync = [gid for gid in game_ids if gid not in synced_game_ids or force_update]
            
            if len(games_to_sync) < len(game_ids):
                skipped_count = len(game_ids) - len(games_to_sync)
                result["skipped_games"] = skipped_count
                self.logger.info(f"跳过{skipped_count}场已同步的比赛")
            
            # 如果没有需要同步的比赛，直接返回
            if not games_to_sync:
                end_time = datetime.now()
                result["end_time"] = end_time.isoformat()
                result["duration"] = (end_time - start_time).total_seconds()
                result["status"] = "completed"
                self.logger.info("所有比赛已同步，无需处理")
                return result
                
            # 分批处理
            batches = [games_to_sync[i:i + batch_size] for i in range(0, len(games_to_sync), batch_size)]
            self.logger.info(f"将{len(games_to_sync)}场比赛分为{len(batches)}批进行处理")
            
            # 处理每一批
            for batch_idx, batch_game_ids in enumerate(batches):
                batch_start_time = datetime.now()
                self.logger.info(f"开始处理第{batch_idx + 1}/{len(batches)}批，包含{len(batch_game_ids)}场比赛")
                
                # 并行处理每场比赛
                batch_results = self._process_batch_with_threading(batch_game_ids, force_update, max_workers)
                
                # 更新统计信息
                success_count = sum(1 for r in batch_results if r["status"] == "success")
                fail_count = sum(1 for r in batch_results if r["status"] == "failed")
                no_data_count = sum(1 for r in batch_results if r.get("no_data", False))
                
                result["successful_games"] += success_count
                result["failed_games"] += fail_count
                result["no_data_games"] += no_data_count
                result["details"].extend(batch_results)
                
                batch_end_time = datetime.now()
                batch_duration = (batch_end_time - batch_start_time).total_seconds()
                
                self.logger.info(f"第{batch_idx + 1}批处理完成: 成功{success_count}场, 失败{fail_count}场, "
                                f"无数据{no_data_count}场, 耗时{batch_duration:.2f}秒")
            
            # 完成统计
            end_time = datetime.now()
            total_duration = (end_time - start_time).total_seconds()
            
            result["end_time"] = end_time.isoformat()
            result["duration"] = total_duration
            result["status"] = "completed" if result["failed_games"] == 0 else "partially_completed"
            
            self.logger.info(f"批量同步完成: 总计{result['total_games']}场, 成功{result['successful_games']}场, "
                            f"失败{result['failed_games']}场, 无数据{result['no_data_games']}场, "
                            f"跳过{result['skipped_games']}场, 总耗时{total_duration:.2f}秒")
            
            return result
    
    def _process_batch_with_threading(self, game_ids: List[str], force_update: bool, max_workers: int) -> List[Dict[str, Any]]:
        """使用多线程处理一批比赛数据"""
        results = []
        
        # 线程安全的计数器
        counters = {"success": 0, "failed": 0, "no_data": 0}
        counter_lock = threading.Lock()
        
        # 定义处理单场比赛的函数
        def process_game(game_id):
            try:
                start_time = datetime.now()
                self.logger.info(f"开始同步比赛(ID:{game_id})的Play-by-Play数据")
                
                # 获取playbyplay数据
                playbyplay_data = self.game_fetcher.get_playbyplay(game_id, force_update)
                
                # 处理无数据情况
                if not playbyplay_data:
                    summary = {"message": "没有可用的Play-by-Play数据，可能是早期比赛"}
                    self._record_sync_history(game_id, "success", start_time, datetime.now(), 0, summary)
                    
                    with counter_lock:
                        counters["no_data"] += 1
                        
                    self.logger.info(f"比赛(ID:{game_id})没有可用的Play-by-Play数据，已记录为同步成功")
                    return {
                        "game_id": game_id,
                        "status": "success",
                        "items_processed": 0,
                        "items_succeeded": 0,
                        "summary": summary,
                        "start_time": start_time.isoformat(),
                        "end_time": datetime.now().isoformat(),
                        "no_data": True
                    }
                
                # 解析和保存数据
                success_count, summary = self._save_playbyplay_data(game_id, playbyplay_data)
                
                # 记录完成状态
                end_time = datetime.now()
                status = "success" if success_count > 0 else "failed"
                
                # 记录同步历史
                self._record_sync_history(game_id, status, start_time, end_time, success_count, summary)
                
                # 更新计数器
                with counter_lock:
                    if status == "success":
                        counters["success"] += 1
                    else:
                        counters["failed"] += 1
                
                self.logger.info(f"比赛(ID:{game_id})Play-by-Play数据同步完成，状态: {status}")
                
                return {
                    "game_id": game_id,
                    "status": status,
                    "items_processed": 1,
                    "items_succeeded": success_count,
                    "summary": summary,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "duration": (end_time - start_time).total_seconds()
                }
                
            except Exception as e:
                self.logger.error(f"同步比赛(ID:{game_id})Play-by-Play数据失败: {e}")
                
                # 记录失败的同步历史
                self._record_sync_history(game_id, "failed", datetime.now(), datetime.now(), 0, {"error": str(e)})
                
                # 更新计数器
                with counter_lock:
                    counters["failed"] += 1
                    
                return {
                    "game_id": game_id,
                    "status": "failed",
                    "error": str(e)
                }
        
        # 使用线程池并行处理
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_game = {executor.submit(process_game, game_id): game_id for game_id in game_ids}
            
            # 获取结果
            for future in concurrent.futures.as_completed(future_to_game):
                game_id = future_to_game[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"获取比赛(ID:{game_id})处理结果失败: {e}")
                    results.append({
                        "game_id": game_id,
                        "status": "failed",
                        "error": f"获取处理结果失败: {e}"
                    })
        
        return results
    
    def _get_synced_game_ids(self) -> Set[str]:
        """获取已成功同步的比赛ID集合"""
        try:
            with self.db_session.session_scope('game') as session:
                # 查询所有成功同步的playbyplay记录
                synced_records = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'playbyplay',
                    GameStatsSyncHistory.status == 'success'
                ).all()
                
                # 转换为集合
                return {record.game_id for record in synced_records}
                
        except Exception as e:
            self.logger.error(f"获取已同步比赛ID失败: {e}")
            return set()


    def _record_sync_history(self, game_id: str, status: str, start_time: datetime, end_time: datetime,
                             items_processed: int, details: Dict) -> None:
        """记录同步历史到数据库"""
        try:
            with self.db_session.session_scope('game') as session:
                sync_history = GameStatsSyncHistory(
                    sync_type='playbyplay',
                    game_id=game_id,
                    status=status,
                    items_processed=items_processed,
                    items_succeeded=items_processed if status == "success" else 0,
                    start_time=start_time,
                    end_time=end_time,
                    details=json.dumps(details),
                    error_message=details.get("error", "") if status == "failed" else ""
                )
                session.add(sync_history)
                # 事务会在session_scope结束时自动提交
        except Exception as e:
            self.logger.error(f"记录同步历史失败: {e}")

    def _save_playbyplay_data(self, game_id: str, playbyplay_data: Dict) -> Tuple[int, Dict]:
        """
        解析并保存playbyplay数据到数据库

        Args:
            game_id: 比赛ID
            playbyplay_data: 从API获取的回合数据

        Returns:
            Tuple[int, Dict]: 成功保存的记录数和摘要信息
        """
        try:
            success_count = 0
            summary = {
                "play_actions_count": 0
            }

            # 提取回合动作
            play_actions = self._extract_play_actions(playbyplay_data, game_id)
            if play_actions:
                with self.db_session.session_scope('game') as session:
                    for action in play_actions:
                        action["game_id"] = game_id
                        self._save_or_update_play_action(session, action)
                        success_count += 1

                summary["play_actions_count"] = len(play_actions)

            self.logger.info(f"成功保存比赛(ID:{game_id})的PlayByPlay数据，共{success_count}条记录")
            return success_count, summary

        except Exception as e:
            self.logger.error(f"保存PlayByPlay数据失败: {e}")
            raise

    def _extract_play_actions(self, playbyplay_data: Dict, game_id: str) -> List[Dict]:
        """从playbyplay数据中提取具体回合动作"""
        try:
            play_actions = []

            # 从新格式中获取actions数组
            game_data = playbyplay_data.get('game', {})
            actions = game_data.get('actions', [])

            if not actions:
                return play_actions

            # 遍历每个动作并提取数据
            for action in actions:
                extracted_action = {
                    "game_id": game_id,
                    "action_number": action.get('actionNumber', 0),
                    "clock": action.get('clock', ''),
                    "period": action.get('period', 0),
                    "team_id": action.get('teamId', 0),
                    "team_tricode": action.get('teamTricode', ''),
                    "person_id": action.get('personId', 0),
                    "player_name": action.get('playerName', ''),
                    "player_name_i": action.get('playerNameI', ''),
                    "x_legacy": action.get('xLegacy', 0),
                    "y_legacy": action.get('yLegacy', 0),
                    "shot_distance": action.get('shotDistance', 0),
                    "shot_result": action.get('shotResult', ''),
                    "is_field_goal": action.get('isFieldGoal', 0),
                    "score_home": action.get('scoreHome', ''),
                    "score_away": action.get('scoreAway', ''),
                    "points_total": action.get('pointsTotal', 0),
                    "location": action.get('location', ''),
                    "description": action.get('description', ''),
                    "action_type": action.get('actionType', ''),
                    "sub_type": action.get('subType', ''),
                    "video_available": action.get('videoAvailable', 0),
                    "shot_value": action.get('shotValue', 0),
                    "action_id": action.get('actionId', 0)
                }
                play_actions.append(extracted_action)

            return play_actions

        except Exception as e:
            self.logger.error(f"提取回合动作数据失败: {e}")
            return []

    def _save_or_update_play_action(self, session, play_action: Dict) -> None:
        """保存或更新回合动作数据"""
        try:
            game_id = play_action.get('game_id')
            action_number = play_action.get('action_number')

            # 检查是否已存在
            existing_event = session.query(Event).filter(
                Event.game_id == game_id,
                Event.action_number == action_number
            ).first()

            if existing_event:
                # 更新现有记录
                for key, value in play_action.items():
                    if hasattr(existing_event, key):
                        setattr(existing_event, key, value)
            else:
                # 创建新的Event对象
                new_event = Event(**play_action)
                session.add(new_event)

        except Exception as e:
            self.logger.error(f"保存或更新回合动作数据失败: {e}")
            raise