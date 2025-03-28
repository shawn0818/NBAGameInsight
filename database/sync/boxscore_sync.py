# sync/boxscore_sync.py
import concurrent
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Set

from nba.fetcher.game_fetcher import GameFetcher
from utils.logger_handler import AppLogger
from database.db_session import DBSession
from database.models.stats_models import Statistics, GameStatsSyncHistory


class BoxscoreSync:
    """
    比赛数据同步器
    负责从NBA API获取数据、转换并写入数据库
    支持并发同步多场比赛
    """

    def __init__(self, game_fetcher=None):
        """初始化比赛数据同步器"""
        self.db_session = DBSession.get_instance()
        self.game_fetcher = game_fetcher or GameFetcher()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def sync_boxscore(self, game_id: str, force_update: bool = False) -> Dict[str, Any]:
        """
        同步指定比赛的统计数据 (单场比赛)
        
        Args:
            game_id: 比赛ID
            force_update: 是否强制更新，默认为False

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info(f"开始同步比赛(ID:{game_id})的Boxscore数据...")

        try:
            # 获取boxscore数据
            boxscore_data = self.game_fetcher.get_boxscore_traditional(game_id, force_update)
            if not boxscore_data:
                raise ValueError(f"无法获取比赛(ID:{game_id})的Boxscore数据")

            # 解析和保存数据
            success_count, summary = self._save_boxscore_data(game_id, boxscore_data)

            end_time = datetime.now()
            status = "success" if success_count > 0 else "failed"

            # 记录同步历史
            self._record_sync_history(game_id, status, start_time, end_time, success_count, summary)

            self.logger.info(f"比赛(ID:{game_id})Boxscore数据同步完成，状态: {status}")
            return {
                "status": status,
                "items_processed": 1,
                "items_succeeded": success_count,
                "summary": summary,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }

        except Exception as e:
            error_msg = f"同步比赛(ID:{game_id})Boxscore数据失败: {e}"
            self.logger.error(error_msg, exc_info=True)

            # 记录失败的同步历史
            self._record_sync_history(game_id, "failed", start_time, datetime.now(), 0, {"error": str(e)})

            return {
                "status": "failed",
                "items_processed": 1,
                "items_succeeded": 0,
                "error": str(e)
            }
            
    def batch_sync_boxscores(self, game_ids: List[str], force_update: bool = False, 
                             max_workers: int = 10, batch_size: int = 50) -> Dict[str, Any]:
        """
        并行同步多场比赛的Boxscore数据
        
        Args:
            game_ids: 比赛ID列表
            force_update: 是否强制更新缓存
            max_workers: 最大工作线程数
            batch_size: 批处理大小
            
        Returns:
            Dict: 同步结果摘要
        """
        start_time = datetime.now()
        self.logger.info(f"开始批量同步{len(game_ids)}场比赛的Boxscore数据，最大线程数: {max_workers}")
        
        # 结果统计
        result = {
            "start_time": start_time.isoformat(),
            "total_games": len(game_ids),
            "successful_games": 0,
            "failed_games": 0,
            "skipped_games": 0,
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
            fail_count = len(batch_results) - success_count
            
            result["successful_games"] += success_count
            result["failed_games"] += fail_count
            result["details"].extend(batch_results)
            
            batch_end_time = datetime.now()
            batch_duration = (batch_end_time - batch_start_time).total_seconds()
            
            self.logger.info(f"第{batch_idx + 1}批处理完成: 成功{success_count}场, 失败{fail_count}场, 耗时{batch_duration:.2f}秒")
        
        # 完成统计
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        result["end_time"] = end_time.isoformat()
        result["duration"] = total_duration
        result["status"] = "completed" if result["failed_games"] == 0 else "partially_completed"
        
        self.logger.info(f"批量同步完成: 总计{result['total_games']}场, 成功{result['successful_games']}场, "
                         f"失败{result['failed_games']}场, 跳过{result['skipped_games']}场, 总耗时{total_duration:.2f}秒")
        
        return result
    
    def _process_batch_with_threading(self, game_ids: List[str], force_update: bool, max_workers: int) -> List[Dict[str, Any]]:
        """使用多线程处理一批比赛数据"""
        results = []
        
        # 线程安全的计数器
        counters = {"success": 0, "failed": 0}
        counter_lock = threading.Lock()
        
        # 定义处理单场比赛的函数
        def process_game(game_id):
            try:
                start_time = datetime.now()
                self.logger.info(f"开始同步比赛(ID:{game_id})的Boxscore数据")
                
                # 获取boxscore数据
                boxscore_data = self.game_fetcher.get_boxscore_traditional(game_id, force_update)
                if not boxscore_data:
                    raise ValueError(f"无法获取比赛(ID:{game_id})的Boxscore数据")
                
                # 解析和保存数据
                success_count, summary = self._save_boxscore_data(game_id, boxscore_data)
                
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
                
                self.logger.info(f"比赛(ID:{game_id})Boxscore数据同步完成，状态: {status}")
                
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
                self.logger.error(f"同步比赛(ID:{game_id})Boxscore数据失败: {e}")
                
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
                # 查询所有成功同步的boxscore记录
                synced_records = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'boxscore',
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
                history = GameStatsSyncHistory(
                    sync_type='boxscore',
                    game_id=game_id,
                    status=status,
                    items_processed=items_processed,
                    items_succeeded=items_processed if status == "success" else 0,
                    start_time=start_time,
                    end_time=end_time,
                    details=json.dumps(details),
                    error_message=details.get("error", "") if status == "failed" else ""
                )
                session.add(history)
                self.logger.debug(f"记录同步历史成功: {history}")
        except Exception as e:
            self.logger.error(f"记录同步历史失败: {e}")

    def _save_boxscore_data(self, game_id: str, boxscore_data: Dict) -> Tuple[int, Dict]:
        """
        解析并保存boxscore数据到数据库

        Args:
            game_id: 比赛ID
            boxscore_data: 从API获取的boxscore数据

        Returns:
            Tuple[int, Dict]: 成功保存的记录数和摘要信息
        """
        try:
            now = datetime.now()
            success_count = 0
            summary = {
                "player_stats_count": 0,
                "home_team": "",
                "away_team": ""
            }

            # 1. 解析比赛基本信息
            game_info = self._extract_game_info(boxscore_data)
            if not game_info:
                raise ValueError(f"无法从Boxscore数据中提取比赛信息")

            # 添加到摘要
            summary["home_team"] = f"{game_info.get('home_team_city')} {game_info.get('home_team_name')}"
            summary["away_team"] = f"{game_info.get('away_team_city')} {game_info.get('away_team_name')}"

            # 2. 解析球员统计数据并与比赛信息合并
            player_stats = self._extract_player_stats(boxscore_data, game_id)

            if player_stats:
                with self.db_session.session_scope('game') as session:
                    for player_stat in player_stats:
                        # 合并比赛信息和球员统计数据
                        player_stat.update({
                            "game_id": game_id,
                            "home_team_id": game_info.get("home_team_id"),
                            "away_team_id": game_info.get("away_team_id"),
                            "home_team_tricode": game_info.get("home_team_tricode"),
                            "away_team_tricode": game_info.get("away_team_tricode"),
                            "home_team_name": game_info.get("home_team_name"),
                            "home_team_city": game_info.get("home_team_city"),
                            "away_team_name": game_info.get("away_team_name"),
                            "away_team_city": game_info.get("away_team_city"),
                            "game_status": game_info.get("game_status", 0),
                            "home_team_score": game_info.get("home_team_score", 0),
                            "away_team_score": game_info.get("away_team_score", 0),
                            "video_available": game_info.get("video_available", 0),
                            "last_updated_at": now
                        })

                        # 保存合并后的数据
                        self._save_or_update_player_boxscore(session, player_stat)
                        success_count += 1

                    summary["player_stats_count"] = len(player_stats)

            self.logger.info(f"成功保存比赛(ID:{game_id})的Boxscore数据，共{success_count}条记录")
            return success_count, summary

        except Exception as e:
            self.logger.error(f"保存Boxscore数据失败: {e}")
            raise

    def _extract_game_info(self, boxscore_data: Dict) -> Dict:
        """从boxscore数据中提取比赛基本信息"""
        try:
            # 初始化空字典
            game_info = {}

            # 访问boxScoreTraditional字段获取基本信息
            box_data = boxscore_data.get('boxScoreTraditional', {})
            if not box_data:
                return game_info

            # 提取基本信息
            game_id = box_data.get('gameId')
            home_team_id = box_data.get('homeTeamId')
            away_team_id = box_data.get('awayTeamId')

            # 获取主队信息
            home_team = box_data.get('homeTeam', {})
            home_team_name = home_team.get('teamName', '')
            home_team_city = home_team.get('teamCity', '')
            home_team_tricode = home_team.get('teamTricode', '')

            # 获取客队信息
            away_team = box_data.get('awayTeam', {})
            away_team_name = away_team.get('teamName', '')
            away_team_city = away_team.get('teamCity', '')
            away_team_tricode = away_team.get('teamTricode', '')

            # 获取主队和客队得分
            home_team_stats = home_team.get('statistics', {})
            away_team_stats = away_team.get('statistics', {})
            home_team_score = home_team_stats.get('points', 0)
            away_team_score = away_team_stats.get('points', 0)

            # 从meta字段中提取视频可用性
            meta = boxscore_data.get('meta', {})
            video_available = meta.get('videoAvailable', 0)

            # 根据得分情况确定比赛状态
            # 0: 未开始, 1: 进行中, 2: 已结束
            game_status = 0
            if home_team_score > 0 or away_team_score > 0:
                game_status = 2  # 假设有得分的比赛已结束

            # 构建比赛信息
            extracted_info = {
                "game_id": game_id,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "home_team_name": home_team_name,
                "home_team_city": home_team_city,
                "home_team_tricode": home_team_tricode,
                "away_team_name": away_team_name,
                "away_team_city": away_team_city,
                "away_team_tricode": away_team_tricode,
                "home_team_score": home_team_score,
                "away_team_score": away_team_score,
                "game_status": game_status,
                "video_available": video_available
            }

            return extracted_info

        except Exception as e:
            self.logger.error(f"提取比赛信息失败: {e}")
            return {}

    def _extract_player_stats(self, boxscore_data: Dict, game_id: str) -> List[Dict]:
        """从boxscore数据中提取球员统计数据"""
        try:
            player_stats = []

            # 访问boxScoreTraditional字段获取球员统计
            box_data = boxscore_data.get('boxScoreTraditional', {})
            if not box_data:
                return player_stats

            # 处理主队球员数据
            home_team = box_data.get('homeTeam', {})
            home_team_id = box_data.get('homeTeamId')
            home_players = home_team.get('players', [])

            for player in home_players:
                stats = player.get('statistics', {})
                player_stat = {
                    "person_id": player.get('personId'),
                    "team_id": home_team_id,
                    # 球员个人信息字段
                    "first_name": player.get('firstName', ''),
                    "family_name": player.get('familyName', ''),
                    "name_i": player.get('nameI', ''),
                    "player_slug": player.get('playerSlug', ''),
                    "position": player.get('position', ''),
                    "jersey_num": player.get('jerseyNum', ''),
                    "comment": player.get('comment', ''),
                    "is_starter": 1 if player.get('position', '') else 0,
                    # 球员统计数据字段
                    "minutes": stats.get('minutes', ''),
                    "field_goals_made": stats.get('fieldGoalsMade', 0),
                    "field_goals_attempted": stats.get('fieldGoalsAttempted', 0),
                    "field_goals_percentage": stats.get('fieldGoalsPercentage', 0.0),
                    "three_pointers_made": stats.get('threePointersMade', 0),
                    "three_pointers_attempted": stats.get('threePointersAttempted', 0),
                    "three_pointers_percentage": stats.get('threePointersPercentage', 0.0),
                    "free_throws_made": stats.get('freeThrowsMade', 0),
                    "free_throws_attempted": stats.get('freeThrowsAttempted', 0),
                    "free_throws_percentage": stats.get('freeThrowsPercentage', 0.0),
                    "rebounds_offensive": stats.get('reboundsOffensive', 0),
                    "rebounds_defensive": stats.get('reboundsDefensive', 0),
                    "rebounds_total": stats.get('reboundsTotal', 0),
                    "assists": stats.get('assists', 0),
                    "steals": stats.get('steals', 0),
                    "blocks": stats.get('blocks', 0),
                    "turnovers": stats.get('turnovers', 0),
                    "fouls_personal": stats.get('foulsPersonal', 0),
                    "points": stats.get('points', 0),
                    "plus_minus_points": stats.get('plusMinusPoints', 0.0)
                }
                player_stats.append(player_stat)

            # 处理客队球员数据
            away_team = box_data.get('awayTeam', {})
            away_team_id = box_data.get('awayTeamId')
            away_players = away_team.get('players', [])

            for player in away_players:
                stats = player.get('statistics', {})
                player_stat = {
                    "person_id": player.get('personId'),
                    "team_id": away_team_id,
                    # 球员个人信息字段
                    "first_name": player.get('firstName', ''),
                    "family_name": player.get('familyName', ''),
                    "name_i": player.get('nameI', ''),
                    "player_slug": player.get('playerSlug', ''),
                    "position": player.get('position', ''),
                    "jersey_num": player.get('jerseyNum', ''),
                    "comment": player.get('comment', ''),
                    "is_starter": 1 if player.get('position', '') else 0,
                    # 球员统计数据字段
                    "minutes": stats.get('minutes', ''),
                    "field_goals_made": stats.get('fieldGoalsMade', 0),
                    "field_goals_attempted": stats.get('fieldGoalsAttempted', 0),
                    "field_goals_percentage": stats.get('fieldGoalsPercentage', 0.0),
                    "three_pointers_made": stats.get('threePointersMade', 0),
                    "three_pointers_attempted": stats.get('threePointersAttempted', 0),
                    "three_pointers_percentage": stats.get('threePointersPercentage', 0.0),
                    "free_throws_made": stats.get('freeThrowsMade', 0),
                    "free_throws_attempted": stats.get('freeThrowsAttempted', 0),
                    "free_throws_percentage": stats.get('freeThrowsPercentage', 0.0),
                    "rebounds_offensive": stats.get('reboundsOffensive', 0),
                    "rebounds_defensive": stats.get('reboundsDefensive', 0),
                    "rebounds_total": stats.get('reboundsTotal', 0),
                    "assists": stats.get('assists', 0),
                    "steals": stats.get('steals', 0),
                    "blocks": stats.get('blocks', 0),
                    "turnovers": stats.get('turnovers', 0),
                    "fouls_personal": stats.get('foulsPersonal', 0),
                    "points": stats.get('points', 0),
                    "plus_minus_points": stats.get('plusMinusPoints', 0.0)
                }
                player_stats.append(player_stat)

            return player_stats

        except Exception as e:
            self.logger.error(f"提取球员统计数据失败: {e}")
            return []

    def _save_or_update_player_boxscore(self, session, player_stat: Dict) -> None:
        """保存或更新球员比赛统计数据"""
        try:
            game_id = player_stat.get('game_id')
            person_id = player_stat.get('person_id')

            # 检查是否已存在
            existing_stat = session.query(Statistics).filter_by(
                game_id=game_id,
                person_id=person_id
            ).first()

            if existing_stat:
                # 更新现有记录
                for key, value in player_stat.items():
                    if key not in ('game_id', 'person_id') and hasattr(existing_stat, key):
                        setattr(existing_stat, key, value)
            else:
                # 创建新记录
                new_stat = Statistics()
                for key, value in player_stat.items():
                    if hasattr(new_stat, key):
                        setattr(new_stat, key, value)
                session.add(new_stat)

        except Exception as e:
            self.logger.error(f"保存或更新球员比赛统计数据失败: {e}")
            raise