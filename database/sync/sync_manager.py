# database/sync/sync_manager.py
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy import and_, exists
import time

from utils.logger_handler import AppLogger
from utils.http_handler import HTTPRequestManager
from database.db_session import DBSession

# 导入所有同步器
from database.sync.schedule_sync import ScheduleSync
from database.sync.team_sync import TeamSync
from database.sync.player_sync import PlayerSync
from database.sync.boxscore_sync import BoxscoreSync
from database.sync.playbyplay_sync import PlayByPlaySync

# 导入模型
from database.models.base_models import Game
from database.models.stats_models import GameStatsSyncHistory, Statistics, Event


class SyncManager:
    """增强版NBA数据同步管理器"""

    def __init__(self, max_global_concurrency=8):
        """初始化同步管理器"""
        self.db_session = DBSession.get_instance()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        # 使用较小的全局并发数
        self.max_global_concurrency = max_global_concurrency

        # 初始化专用于段控制的http_manager
        self.segment_http_manager = HTTPRequestManager(headers={"User-Agent": "SegmentController"})

        # 初始化所有同步器
        self.schedule_sync = ScheduleSync()
        self.team_sync = TeamSync()
        self.player_sync = PlayerSync()

        # 使用优化后的同步器，传入全局并发参数
        self.boxscore_sync = BoxscoreSync(max_global_concurrency=max(3, max_global_concurrency // 2))
        self.playbyplay_sync = PlayByPlaySync(max_global_concurrency=max(3, max_global_concurrency // 2))

        self.logger.info(f"同步管理器初始化完成，全局最大并发数: {max_global_concurrency}")

        # 状态记录
        self.sync_state = {
            'last_sync_time': None,
            'total_processed': 0,
            'window_start_time': time.time(),
            'window_processed': 0
        }

    def should_sync_playbyplay(self, game_id: str) -> bool:
        """
        判断是否应该同步此比赛的Play-by-Play数据
        统一判断规则（按执行效率排序）：
        1. 首先检查是否是1996赛季及之后的比赛（最快筛选）
        2. 然后检查是否是季前赛(第三位数字为'1')
        3. 最后检查其他条件

        Args:
            game_id: 比赛ID

        Returns:
            bool: 是否应该同步PlayByPlay数据
        """
        # 1. 首先检查是否为1996赛季及之后（最快的筛选条件）
        try:
            if len(game_id) == 10:
                season_year = int(game_id[3:5])
                # 将两位数年份转换为四位数年份，46-99表示1946-1999，00-45表示2000-2045
                if 46 <= season_year <= 99:
                    full_year = 1900 + season_year
                else:  # 00-45
                    full_year = 2000 + season_year

                # 检查是否为1996年之前
                if full_year < 1996:
                    # self.logger.debug(f"比赛ID {game_id} 在1996赛季之前，不同步 PlayByPlay。")
                    return False
            else:
                self.logger.warning(f"比赛ID {game_id} 格式异常，无法判断赛季，将按需处理 PlayByPlay。")
                return True  # 格式异常，默认同步
        except Exception as e:
            self.logger.error(f"判断比赛PlayByPlay时代时出错 ({game_id}): {e}")
            return True  # 解析错误，保守返回同步

        # 2. 检查赛季类型是否为季前赛 (第三位为 '1')
        season_type_char = game_id[2]
        if season_type_char == '1':
            # self.logger.debug(f"比赛ID {game_id} 为季前赛，不同步 PlayByPlay。")
            return False  # 季前赛不同步

        # 3. 其他可能需要排除的类型
        # 例如：if season_type_char == '3': return False  # 全明星赛不同步

        return True  # 默认需要同步

    def sync_teams(self, force_update: bool = False) -> Dict[str, Any]:
        """
        同步球队数据

        Args:
            force_update: 是否强制更新

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info("开始同步球队数据...")

        result = {
            "start_time": start_time.isoformat(),
            "status": "success"
        }

        try:
            # 同步球队基本信息
            team_details_success = self.team_sync.sync_team_details(force_update)

            # 同步球队Logo
            logo_success = self.team_sync.sync_team_logos()

            result["team_details_synced"] = team_details_success
            result["team_logos_synced"] = logo_success

        except Exception as e:
            self.logger.error(f"同步球队数据失败: {e}", exc_info=True)
            result["status"] = "failed"
            result["error"] = str(e)

        end_time = datetime.now()
        result["end_time"] = end_time.isoformat()
        result["duration"] = (end_time - start_time).total_seconds()

        return result

    def sync_players(self, force_update: bool = False) -> Dict[str, Any]:
        """
        同步球员数据

        Args:
            force_update: 是否强制更新

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info("开始同步球员数据...")

        result = {
            "start_time": start_time.isoformat(),
            "status": "success"
        }

        try:
            # 同步球员信息
            success = self.player_sync.sync_players(force_update)
            result["success"] = success

        except Exception as e:
            self.logger.error(f"同步球员数据失败: {e}", exc_info=True)
            result["status"] = "failed"
            result["error"] = str(e)

        end_time = datetime.now()
        result["end_time"] = end_time.isoformat()
        result["duration"] = (end_time - start_time).total_seconds()

        return result

    def sync_player_details(self, player_ids: Optional[List[int]] = None,
                            force_update: bool = True,
                            only_active: bool = False) -> Dict[str, Any]:
        """
        同步球员详细信息

        从commonplayerinfo API获取球员详细数据，并更新到球员表中

        Args:
            player_ids: 指定的球员ID列表，不指定则同步所有符合条件的球员
            force_update: 是否强制更新
            only_active: 是否只同步可能活跃的球员（基于to_year字段判断）

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info("开始同步球员详细信息...")

        result = {
            "start_time": start_time.isoformat(),
            "status": "success"
        }

        try:
            # 获取当前环境的最优参数
            params = self.get_optimal_params()
            max_workers = params.get("max_workers", 6)
            batch_size = params.get("batch_size", 30)
            batch_interval = params.get("batch_interval", 60)

            # 调用PlayerSync的批量同步方法（带重试机制）
            sync_result = self.player_sync.batch_sync_player_details_with_retry(
                player_ids=player_ids,
                max_retries=3,
                force_update=force_update,
                only_active=only_active,
                max_workers=max_workers,
                batch_size=batch_size
            )

            result.update(sync_result)

        except Exception as e:
            self.logger.error(f"同步球员详细信息失败: {e}", exc_info=True)
            result["status"] = "failed"
            result["error"] = str(e)

        # 计算耗时
        end_time = datetime.now()
        result["end_time"] = end_time.isoformat()
        result["duration"] = (end_time - start_time).total_seconds()

        self.logger.info(f"球员详细信息同步完成: 总计{result.get('total', 0)}名球员, "
                         f"成功{result.get('successful', 0)}名, 失败{result.get('failed', 0)}名, "
                         f"跳过{result.get('skipped', 0)}名, 耗时{result['duration']:.2f}秒")

        return result

    def sync_schedules(self, force_update: bool = False, all_seasons: bool = True) -> Dict[str, Any]:
        """
        同步赛程数据

        Args:
            force_update: 是否强制更新（对于all_seasons=True时，决定是否重新同步数据库中已有数据的赛季）
            all_seasons: 是否同步所有赛季，默认为True

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info("开始同步赛程数据...")

        result = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "details": {}
        }

        try:
            if all_seasons:
                # 同步所有赛季，force_update在这里用于决定是否跳过数据库中已有的赛季
                seasons_result = self.schedule_sync.sync_all_seasons(force_update=force_update)
                total_count = sum(seasons_result.values())

                result["details"]["all_seasons"] = {
                    "count": total_count,
                    "success": total_count > 0,
                    "seasons_detail": seasons_result
                }
            else:
                # 只同步当前赛季，当前赛季总是获取最新数据
                current_season_count = self.schedule_sync.sync_current_season()
                result["details"]["current_season"] = {
                    "count": current_season_count,
                    "success": current_season_count > 0
                }

        except Exception as e:
            self.logger.error(f"同步赛程数据失败: {e}", exc_info=True)
            result["status"] = "failed"
            result["error"] = str(e)

        end_time = datetime.now()
        result["end_time"] = end_time.isoformat()
        result["duration"] = (end_time - start_time).total_seconds()

        return result

    def sync_game_stats(self, game_id: str, force_update: bool = False, with_retry: bool = False) -> Dict[str, Any]:
        """
        同步指定比赛的统计数据

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新，默认为False
            with_retry: 是否启用重试机制，默认为False

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info(f"开始同步比赛(ID:{game_id})统计数据...")

        result = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "game_id": game_id,
            "details": {}
        }

        try:
            # 先检查是否需要同步
            if not force_update:
                # 检查是否已成功同步过
                is_synchronized = self._is_game_stats_synchronized(game_id)
                if is_synchronized:
                    self.logger.info(f"比赛(ID:{game_id})统计数据已同步，跳过")
                    result["details"]["already_synchronized"] = True
                    result["details"]["boxscore"] = {"status": "skipped"}
                    result["details"]["playbyplay"] = {"status": "skipped"}

                    end_time = datetime.now()
                    result["end_time"] = end_time.isoformat()
                    result["duration"] = (end_time - start_time).total_seconds()
                    return result

            # 同步Boxscore数据
            if with_retry:
                # 使用重试机制，单场比赛时使用batch_sync_with_retry处理单个ID
                boxscore_result = self.boxscore_sync.batch_sync_with_retry(
                    game_ids=[game_id],
                    max_retries=2,
                    force_update=force_update,
                    max_workers=1,  # 单个比赛只需要一个线程
                    batch_size=1
                )
                # 从批量同步结果中提取单个比赛的详细信息
                if boxscore_result.get("details") and len(boxscore_result["details"]) > 0:
                    boxscore_detail = next((d for d in boxscore_result["details"] if d.get("game_id") == game_id), None)
                    if boxscore_detail:
                        boxscore_status = boxscore_detail.get("status", "failed")
                        boxscore_detail["status"] = boxscore_status  # 确保状态信息存在
                        result["details"]["boxscore"] = boxscore_detail
                    else:
                        result["details"]["boxscore"] = {"status": "failed", "error": "未找到比赛详情"}
                else:
                    result["details"]["boxscore"] = {"status": "failed", "error": "批量同步未返回有效结果"}
            else:
                # 不使用重试机制，直接调用单场同步方法
                boxscore_result = self.boxscore_sync.sync_boxscore(game_id, force_update)
                result["details"]["boxscore"] = boxscore_result

            # 同步Play-by-Play数据 - 添加判断
            if self.should_sync_playbyplay(game_id):
                if with_retry:
                    # 使用重试机制
                    playbyplay_result = self.playbyplay_sync.batch_sync_with_retry(
                        game_ids=[game_id],
                        max_retries=2,
                        force_update=force_update,
                        max_workers=1,
                        batch_size=1
                    )
                    # 从批量同步结果中提取单个比赛的详细信息
                    if playbyplay_result.get("details") and len(playbyplay_result["details"]) > 0:
                        playbyplay_detail = next(
                            (d for d in playbyplay_result["details"] if d.get("game_id") == game_id),
                            None)
                        if playbyplay_detail:
                            playbyplay_status = playbyplay_detail.get("status", "failed")
                            playbyplay_detail["status"] = playbyplay_status  # 确保状态信息存在
                            result["details"]["playbyplay"] = playbyplay_detail
                        else:
                            result["details"]["playbyplay"] = {"status": "failed", "error": "未找到比赛详情"}
                    else:
                        result["details"]["playbyplay"] = {"status": "failed", "error": "批量同步未返回有效结果"}
                else:
                    # 不使用重试机制
                    playbyplay_result = self.playbyplay_sync.sync_playbyplay(game_id, force_update)
                    result["details"]["playbyplay"] = playbyplay_result
            else:
                # 为不需要同步的PlayByPlay创建跳过记录
                playbyplay_success = True  # 视为成功处理
                playbyplay_result = {
                    "game_id": game_id,
                    "status": "success",
                    "items_processed": 0,
                    "items_succeeded": 0,
                    "summary": {"message": "根据规则跳过PlayByPlay处理，1996赛季之前或季前赛"},
                    "no_data": True,
                    "skipped": True
                }
                result["details"]["playbyplay"] = playbyplay_result

                # 记录同步历史
                sync_history = GameStatsSyncHistory(
                    sync_type='playbyplay',
                    game_id=game_id,
                    status='success',
                    items_processed=0,
                    items_succeeded=0,
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    details=json.dumps({"message": "根据规则跳过PlayByPlay处理，1996赛季之前或季前赛", "no_data": True}),
                    error_message=""
                )
                with self.db_session.session_scope('game') as session:
                    session.add(sync_history)

            # 检查同步结果
            boxscore_success = result["details"]["boxscore"].get("status") == "success"
            playbyplay_success = result["details"]["playbyplay"].get("status") == "success"

            if not (boxscore_success and playbyplay_success):
                result["status"] = "partially_failed"

        except Exception as e:
            self.logger.error(f"同步比赛(ID:{game_id})统计数据失败: {e}", exc_info=True)
            result["status"] = "failed"
            result["error"] = str(e)

        end_time = datetime.now()
        result["end_time"] = end_time.isoformat()
        result["duration"] = (end_time - start_time).total_seconds()

        return result

    def _is_game_stats_synchronized(self, game_id: str) -> bool:
        """
        检查比赛统计数据是否已同步
        只检查boxscore同步状态，忽略playbyplay

        Args:
            game_id: 比赛ID

        Returns:
            bool: 是否已同步
        """
        try:
            with self.db_session.session_scope('game') as session:
                # 只检查boxscore同步记录
                boxscore_synced = session.query(exists().where(
                    and_(
                        GameStatsSyncHistory.game_id == game_id,
                        GameStatsSyncHistory.sync_type == 'boxscore',
                        GameStatsSyncHistory.status == 'success'
                    )
                )).scalar()

                # 检查是否有实际的统计数据
                has_statistics = session.query(exists().where(
                    Statistics.game_id == game_id
                )).scalar()

                # 只需要boxscore数据同步成功即可
                return boxscore_synced and has_statistics

        except Exception as e:
            self.logger.error(f"检查比赛(ID:{game_id})同步状态失败: {e}", exc_info=True)
            return False

    def sync_remaining_game_stats_parallel(self, force_update: bool = False, max_workers: int = 6,
                                           batch_size: int = 30, reverse_order: bool = False,
                                           with_retry: bool = True, max_retries: int = 3,
                                           batch_interval: int = 60) -> Dict[str, Any]:
        """顺序同步剩余未同步的比赛统计数据，根据历史分段处理，并修复错误标记的数据"""
        start_time = datetime.now()
        self.logger.info(f"开始顺序同步剩余未同步的比赛统计数据...")
        if with_retry:
            self.logger.info(f"启用智能重试机制，最大重试次数: {max_retries}")

        result = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "details": {}
        }

        # 在同步统计数据前，先更新当前赛季赛程状态
        self.logger.info("在同步统计数据前，先更新当前赛季赛程状态...")
        schedule_sync_result = self.sync_schedules(force_update=True, all_seasons=False)
        if schedule_sync_result.get("status") != "success":
            self.logger.warning("更新当前赛季赛程失败，将继续尝试同步统计数据，但可能不是最新状态。")
        else:
            schedule_count = schedule_sync_result.get("details", {}).get("current_season", {}).get("count", 0)
            self.logger.info(f"当前赛季赛程更新完成，共处理 {schedule_count} 场比赛。")

        try:
            # 1. 查询所有已完成的比赛ID
            with self.db_session.session_scope('nba') as session:
                finished_games = session.query(Game).filter(
                    Game.game_status == 3  # 已完成的比赛
                ).all()
                all_game_ids = [game.game_id for game in finished_games]

            # 按时间顺序排序（而不是根据reverse_order参数）
            all_game_ids.sort()  # 按ID排序，较早的比赛ID较小
            self.logger.info("使用顺序(从旧到新)处理比赛数据")

            # 2. 查询同步状态和检测错误标记
            with self.db_session.session_scope('game') as session:
                # 获取boxscore已同步的比赛ID
                boxscore_synced = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'boxscore',
                    GameStatsSyncHistory.status == 'success'
                ).all()
                boxscore_synced_ids = {record.game_id for record in boxscore_synced}

                # 获取playbyplay已同步的比赛ID
                playbyplay_synced = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'playbyplay',
                    GameStatsSyncHistory.status == 'success'
                ).all()
                playbyplay_synced_ids = {record.game_id for record in playbyplay_synced}

                # 检测错误标记的playbyplay记录（标记为成功但没有实际数据）
                mismarked_playbyplay_ids = set()

                # 查询标记为成功同步的playbyplay记录
                potential_mismarked = session.query(GameStatsSyncHistory).filter(
                    GameStatsSyncHistory.sync_type == 'playbyplay',
                    GameStatsSyncHistory.status == 'success'
                ).all()

                for record in potential_mismarked:
                    game_id = record.game_id

                    # 只检查应该有PlayByPlay数据的比赛
                    if not self.should_sync_playbyplay(game_id):
                        continue

                    # 检查Event表中是否有实际数据
                    event_count = session.query(Event).filter(
                        Event.game_id == game_id
                    ).count()

                    # 检查同步历史记录的items_succeeded字段
                    items_succeeded = record.items_succeeded or 0

                    # 检查details字段中是否标记为no_data
                    no_data_flag = False
                    if record.details:
                        try:
                            details_dict = json.loads(record.details)
                            if details_dict.get('no_data', False) or 'no_data' in details_dict.get('message',
                                                                                                   '').lower():
                                no_data_flag = True
                        except (json.JSONDecodeError, TypeError):
                            pass

                    # 如果没有事件数据且不是明确标记为无数据的记录，则认为是错误标记
                    if event_count == 0 and items_succeeded == 0 and not no_data_flag:
                        mismarked_playbyplay_ids.add(game_id)
                        self.logger.warning(f"发现错误标记的PlayByPlay记录: {game_id}, 将重新同步")

                self.logger.info(
                    f"发现{len(mismarked_playbyplay_ids)}场比赛的PlayByPlay数据被错误标记为成功但实际无数据")

            # 3. 区分需要同步PlayByPlay的比赛和不需要的比赛
            playbyplay_games = []
            no_playbyplay_games = []

            for gid in all_game_ids:
                if self.should_sync_playbyplay(gid):
                    playbyplay_games.append(gid)
                else:
                    no_playbyplay_games.append(gid)

            self.logger.info(
                f"总计{len(all_game_ids)}场比赛，需要PlayByPlay的比赛：{len(playbyplay_games)}场，"
                f"不需要PlayByPlay的比赛：{len(no_playbyplay_games)}场")

            # 4. 过滤需要同步的比赛ID
            # 对于boxscore，所有比赛都需要
            to_sync_boxscore = [gid for gid in all_game_ids if
                                gid not in boxscore_synced_ids or force_update]

            # 对于playbyplay，只考虑应该有数据的比赛
            to_sync_playbyplay = [
                gid for gid in playbyplay_games if  # 这些已经是应该有PlayByPlay的比赛
                (gid not in playbyplay_synced_ids or  # 未同步
                 gid in mismarked_playbyplay_ids or  # 错误标记
                 force_update)  # 强制更新
            ]

            self.logger.info(f"需要同步的比赛：boxscore: {len(to_sync_boxscore)}场, "
                             f"playbyplay: {len(to_sync_playbyplay)}场 "
                             f"(其中错误标记: {len(mismarked_playbyplay_ids & set(to_sync_playbyplay))}场)")

            # 5. 同步boxscore数据
            if to_sync_boxscore:
                self.logger.info(f"开始同步{len(to_sync_boxscore)}场比赛的Boxscore数据")
                if with_retry:
                    boxscore_result = self.boxscore_sync.batch_sync_with_retry(
                        game_ids=to_sync_boxscore,
                        max_retries=max_retries,
                        force_update=force_update,
                        max_workers=max_workers,
                        batch_size=batch_size
                    )
                else:
                    boxscore_result = self.boxscore_sync.batch_sync_boxscores(
                        game_ids=to_sync_boxscore,
                        force_update=force_update,
                        max_workers=max_workers,
                        batch_size=batch_size,
                        batch_interval=batch_interval
                    )
                result["details"]["boxscore"] = boxscore_result
            else:
                self.logger.info("Boxscore数据已全部同步，无需处理")
                result["details"]["boxscore"] = {"status": "skipped", "message": "所有数据已同步"}

            # 6. 处理错误标记的记录，清除错误的成功标记
            if mismarked_playbyplay_ids:
                self.logger.info(f"开始清除{len(mismarked_playbyplay_ids)}场错误标记的PlayByPlay同步记录")
                with self.db_session.session_scope('game') as session:
                    for game_id in mismarked_playbyplay_ids:
                        # 查询并更新错误标记的记录状态为"invalid"
                        session.query(GameStatsSyncHistory).filter(
                            GameStatsSyncHistory.game_id == game_id,
                            GameStatsSyncHistory.sync_type == 'playbyplay',
                            GameStatsSyncHistory.status == 'success'
                        ).update({
                            "status": "invalid",
                            "error_message": "错误标记，实际无数据"
                        })
                self.logger.info("错误标记的PlayByPlay同步记录已清除")

            # 7. 为不需要同步PlayByPlay的比赛创建记录
            if no_playbyplay_games:
                self.logger.info(f"为{len(no_playbyplay_games)}场不需要PlayByPlay数据的比赛创建记录")

                # 分批处理以避免SQLite的"too many SQL variables"错误
                batch_size = 500  # SQLite变量限制是999，保守设置为500
                total_created = 0

                for i in range(0, len(no_playbyplay_games), batch_size):
                    batch = no_playbyplay_games[i:i + batch_size]

                    with self.db_session.session_scope('game') as session:
                        # 只查询当前批次
                        existing_records = session.query(GameStatsSyncHistory.game_id).filter(
                            GameStatsSyncHistory.game_id.in_(batch),
                            GameStatsSyncHistory.sync_type == 'playbyplay',
                            GameStatsSyncHistory.status == 'success'
                        ).all()
                        existing_ids = {record.game_id for record in existing_records}

                        # 只为没有记录的比赛创建新记录
                        to_create_records = [gid for gid in batch if gid not in existing_ids]

                        if to_create_records:
                            self.logger.info(
                                f"为批次{i // batch_size + 1}中的{len(to_create_records)}场比赛创建新的PlayByPlay跳过记录")
                            now = datetime.now()
                            for game_id in to_create_records:
                                sync_history = GameStatsSyncHistory(
                                    sync_type='playbyplay',
                                    game_id=game_id,
                                    status='success',
                                    items_processed=0,
                                    items_succeeded=0,
                                    start_time=now,
                                    end_time=now,
                                    details=json.dumps({"message": "根据规则跳过PlayByPlay处理，1996赛季之前或季前赛",
                                                        "no_data": True}),
                                    error_message=""
                                )
                                session.add(sync_history)
                            total_created += len(to_create_records)

                self.logger.info(f"完成记录创建，总共为{total_created}场比赛创建了PlayByPlay跳过记录")
            else:
                self.logger.info("没有不需要PlayByPlay数据的比赛，无需创建记录")

            # 8. 然后同步playbyplay（适当等待以避免API压力）
            if to_sync_playbyplay:

                self.logger.info(f"开始同步{len(to_sync_playbyplay)}场比赛的Play-by-Play数据")
                # 使用更保守的参数
                playbyplay_batch_size = min(20, batch_size)
                playbyplay_max_workers = min(4, max_workers)
                self.logger.info(
                    f"PlayByPlay同步使用更保守的参数: 批次大小={playbyplay_batch_size}, 线程数={playbyplay_max_workers}")

                if with_retry:
                    playbyplay_result = self.playbyplay_sync.batch_sync_with_retry(
                        game_ids=to_sync_playbyplay,
                        max_retries=max_retries,
                        force_update=True,  # 对于错误标记的记录，强制更新
                        max_workers=playbyplay_max_workers,
                        batch_size=playbyplay_batch_size
                    )
                else:
                    playbyplay_result = self.playbyplay_sync.batch_sync_playbyplay(
                        game_ids=to_sync_playbyplay,
                        force_update=True,  # 对于错误标记的记录，强制更新
                        max_workers=playbyplay_max_workers,
                        batch_size=playbyplay_batch_size,
                        batch_interval=batch_interval * 1.5  # 增加批次间隔
                    )
                result["details"]["playbyplay"] = playbyplay_result
            else:
                self.logger.info("Play-by-Play数据已全部同步，无需处理")
                result["details"]["playbyplay"] = {"status": "skipped", "message": "所有数据已同步"}

            # 9. 验证同步效果
            if mismarked_playbyplay_ids:
                self.logger.info("验证错误标记的记录是否已正确同步...")
                with self.db_session.session_scope('game') as session:
                    fixed_count = 0
                    still_missing_count = 0

                    for game_id in mismarked_playbyplay_ids:
                        # 检查Event表中是否现在有数据
                        event_count = session.query(Event).filter(
                            Event.game_id == game_id
                        ).count()

                        if event_count > 0:
                            fixed_count += 1
                        else:
                            still_missing_count += 1

                    self.logger.info(
                        f"错误标记记录处理结果: 成功修复 {fixed_count} 场, 仍缺数据 {still_missing_count} 场")

                    # 如果仍有缺数据的记录，可能是真的没数据，自动标记为no_data
                    if still_missing_count > 0:
                        self.logger.info(f"自动标记 {still_missing_count} 场真正没有数据的比赛")
                        for game_id in mismarked_playbyplay_ids:
                            event_count = session.query(Event).filter(
                                Event.game_id == game_id
                            ).count()

                            if event_count == 0:
                                # 创建一个新的成功记录，但标记为no_data
                                now = datetime.now()
                                new_history = GameStatsSyncHistory(
                                    sync_type='playbyplay',
                                    game_id=game_id,
                                    status='success',
                                    items_processed=0,
                                    items_succeeded=0,
                                    start_time=now,
                                    end_time=now,
                                    details=json.dumps({"message": "没有可用的Play-by-Play数据", "no_data": True}),
                                    error_message=""
                                )
                                session.add(new_history)

                    result["details"]["fix_validation"] = {
                        "fixed_count": fixed_count,
                        "still_missing_count": still_missing_count
                    }

            # 设置总体状态
            if ((to_sync_boxscore and result["details"]["boxscore"].get("status") not in ["completed", "success",
                                                                                          "skipped"]) or
                    (to_sync_playbyplay and result["details"]["playbyplay"].get("status") not in ["completed",
                                                                                                  "success",
                                                                                                  "skipped"])):
                result["status"] = "partially_failed"

        except Exception as e:
            self.logger.error(f"顺序同步剩余比赛统计数据失败: {e}", exc_info=True)
            result["status"] = "failed"
            result["error"] = str(e)

        # 完成统计
        end_time = datetime.now()
        result["end_time"] = end_time.isoformat()
        result["duration"] = (end_time - start_time).total_seconds()

        self.logger.info(f"顺序同步剩余比赛统计数据完成，状态: {result['status']}, 总耗时: {result['duration']}秒")

        return result

    def _segmented_sync_strategy(self, games_to_sync, start_time, force_update, max_workers,
                                 batch_size, with_retry, max_retries, batch_interval):
        """改进的分段同步策略 - 处理大量比赛时采用更智能的策略"""

        # 分别获取需要同步的boxscore和playbyplay数据
        with self.db_session.session_scope('game') as session:
            # 获取boxscore已同步的比赛ID
            boxscore_synced = session.query(GameStatsSyncHistory.game_id).filter(
                GameStatsSyncHistory.sync_type == 'boxscore',
                GameStatsSyncHistory.status == 'success'
            ).all()
            boxscore_synced_ids = {record.game_id for record in boxscore_synced}

        # 分别计算需要同步的boxscore和playbyplay的比赛ID
        boxscore_to_sync = [gid for gid in games_to_sync if gid not in boxscore_synced_ids or force_update]

        # 只对需要同步PlayByPlay的比赛进行PlayByPlay同步
        playbyplay_to_sync = [gid for gid in games_to_sync if self.should_sync_playbyplay(gid)]

        self.logger.info(f"分段同步策略: 需要同步boxscore的比赛数量: {len(boxscore_to_sync)}, "
                         f"需要同步playbyplay的比赛数量: {len(playbyplay_to_sync)}")

        result = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "segments": [],
            "segment_stats": {
                "total": 0,
                "completed": 0,
                "failed": 0
            }
        }

        # 将比赛分成更小的段
        segment_size = 800  # 每段最多800场比赛

        # 根据实际需要同步的数据类型创建段
        boxscore_segments = []
        if boxscore_to_sync:
            boxscore_segments = [boxscore_to_sync[i:i + segment_size] for i in
                                 range(0, len(boxscore_to_sync), segment_size)]
            self.logger.info(f"已将{len(boxscore_to_sync)}场需要同步boxscore的比赛分为{len(boxscore_segments)}个段")

        playbyplay_segments = []
        if playbyplay_to_sync:
            playbyplay_segments = [playbyplay_to_sync[i:i + segment_size] for i in
                                   range(0, len(playbyplay_to_sync), segment_size)]
            self.logger.info(
                f"已将{len(playbyplay_to_sync)}场需要同步playbyplay的比赛分为{len(playbyplay_segments)}个段")

        total_segments = max(len(boxscore_segments), len(playbyplay_segments))
        result["segment_stats"]["total"] = total_segments

        # 设置段控制器的批次间隔
        self.segment_http_manager.set_batch_interval(900, adaptive=True)  # 15分钟基础间隔

        # 逐段处理
        for segment_idx in range(total_segments):
            self.logger.info(f"开始处理第{segment_idx + 1}/{total_segments}段")

            # 如果不是第一个段，使用控制器等待
            if segment_idx > 0:
                self.segment_http_manager.wait_for_next_batch()

            # 第一段使用提供的参数，后续段使用更保守的参数
            current_batch_size = batch_size if segment_idx == 0 else min(20, batch_size)
            current_max_workers = max_workers if segment_idx == 0 else min(4, max_workers)
            current_batch_interval = batch_interval if segment_idx == 0 else batch_interval * 1.5

            segment_start_time = datetime.now()
            segment_result = {
                "segment_index": segment_idx + 1,
                "start_time": segment_start_time.isoformat(),
                "parameters": {
                    "batch_size": current_batch_size,
                    "max_workers": current_max_workers,
                    "batch_interval": current_batch_interval
                }
            }

            try:
                # 获取当前段的比赛ID
                current_boxscore_games = boxscore_segments[segment_idx] if segment_idx < len(boxscore_segments) else []
                current_playbyplay_games = playbyplay_segments[segment_idx] if segment_idx < len(
                    playbyplay_segments) else []

                segment_result["boxscore_games_count"] = len(current_boxscore_games)
                segment_result["playbyplay_games_count"] = len(current_playbyplay_games)

                # 只有当有boxscore数据需要同步时才进行boxscore同步
                if current_boxscore_games:
                    if with_retry:
                        # Boxscore同步
                        self.logger.info(f"开始段{segment_idx + 1}的Boxscore同步，共{len(current_boxscore_games)}场比赛")
                        boxscore_result = self.boxscore_sync.batch_sync_with_retry(
                            game_ids=current_boxscore_games,
                            max_retries=max_retries,
                            force_update=force_update,
                            max_workers=current_max_workers,
                            batch_size=current_batch_size
                        )
                    else:
                        # 标准同步
                        self.logger.info(f"开始段{segment_idx + 1}的Boxscore同步，共{len(current_boxscore_games)}场比赛")
                        boxscore_result = self.boxscore_sync.batch_sync_boxscores(
                            game_ids=current_boxscore_games,
                            force_update=force_update,
                            max_workers=current_max_workers,
                            batch_size=current_batch_size,
                            batch_interval=current_batch_interval
                        )

                    # 记录boxscore同步结果
                    segment_result["boxscore"] = {
                        "successful": boxscore_result.get("successful_games", 0),
                        "failed": boxscore_result.get("failed_games", 0)
                    }

                    # 仅当实际同步了boxscore数据后才休息
                    if boxscore_result.get("successful_games", 0) > 0 or boxscore_result.get("failed_games", 0) > 0:
                        rest_time = 300  # 5分钟
                        self.logger.info(f"段{segment_idx + 1} Boxscore同步完成，休息{rest_time}秒")
                        time.sleep(rest_time)
                    else:
                        self.logger.info(f"段{segment_idx + 1} 没有实际同步任何Boxscore数据，跳过休息")
                else:
                    self.logger.info(f"段{segment_idx + 1} 没有需要同步的Boxscore数据，跳过此步骤")
                    segment_result["boxscore"] = {"status": "skipped", "message": "没有需要同步的数据"}

                # 只有当有playbyplay数据需要同步时才进行playbyplay同步
                if current_playbyplay_games:
                    if with_retry:
                        # PlayByPlay同步
                        self.logger.info(
                            f"开始段{segment_idx + 1}的PlayByPlay同步，共{len(current_playbyplay_games)}场比赛")
                        playbyplay_result = self.playbyplay_sync.batch_sync_with_retry(
                            game_ids=current_playbyplay_games,
                            max_retries=max_retries,
                            force_update=force_update,
                            max_workers=current_max_workers // 2,  # 减半线程数
                            batch_size=max(10, current_batch_size // 2)  # 减半批次大小
                        )
                    else:
                        # 标准同步
                        self.logger.info(
                            f"开始段{segment_idx + 1}的PlayByPlay同步，共{len(current_playbyplay_games)}场比赛")
                        playbyplay_result = self.playbyplay_sync.batch_sync_playbyplay(
                            game_ids=current_playbyplay_games,
                            force_update=force_update,
                            max_workers=current_max_workers // 2,
                            batch_size=max(10, current_batch_size // 2),
                            batch_interval=current_batch_interval * 1.5
                        )

                    # 记录playbyplay同步结果
                    segment_result["playbyplay"] = {
                        "successful": playbyplay_result.get("successful_games", 0),
                        "failed": playbyplay_result.get("failed_games", 0),
                        "no_data": playbyplay_result.get("no_data_games", 0)
                    }
                else:
                    self.logger.info(f"段{segment_idx + 1} 没有需要同步的PlayByPlay数据，跳过此步骤")
                    segment_result["playbyplay"] = {"status": "skipped", "message": "没有需要同步的数据"}

                segment_result["status"] = "completed"
                result["segment_stats"]["completed"] += 1

            except Exception as e:
                self.logger.error(f"处理段{segment_idx + 1}时发生错误: {e}", exc_info=True)
                segment_result["status"] = "failed"
                segment_result["error"] = str(e)
                result["segment_stats"]["failed"] += 1

            # 段处理完成
            segment_end_time = datetime.now()
            segment_result["end_time"] = segment_end_time.isoformat()
            segment_result["duration"] = (segment_end_time - segment_start_time).total_seconds()
            result["segments"].append(segment_result)

            self.logger.info(
                f"段{segment_idx + 1}处理完成，状态: {segment_result['status']}, 耗时: {segment_result['duration']}秒")

        # 完成统计
        end_time = datetime.now()
        result["end_time"] = end_time.isoformat()
        result["duration"] = (end_time - start_time).total_seconds()
        result["status"] = "completed" if result["segment_stats"]["failed"] == 0 else "partially_completed"

        self.logger.info(f"分段同步完成: 总计{result['segment_stats']['total']}段, "
                         f"成功{result['segment_stats']['completed']}段, "
                         f"失败{result['segment_stats']['failed']}段, "
                         f"总耗时{result['duration']}秒")

        return result

    def is_api_peak_time(self):
        """检查当前是否是API高峰时段"""
        current_hour = datetime.now().hour
        # NBA统计API可能在比赛直播时段负载较高
        # 美国东部时间晚上7点到11点(比赛时间)可能是高峰
        peak_hours = range(19, 24)  # 调整为对应的本地时区时间
        return current_hour in peak_hours

    def get_optimal_params(self):
        """获取基于当前环境的最优参数"""
        if self.is_api_peak_time():
            # 高峰期使用更保守的配置
            return {
                "max_workers": 3,
                "batch_size": 10,
                "batch_interval": 90
            }
        else:
            # 非高峰期可以适度积极
            return {
                "max_workers": 6,
                "batch_size": 30,
                "batch_interval": 60
            }