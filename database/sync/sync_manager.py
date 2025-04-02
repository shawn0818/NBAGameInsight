from typing import Dict, Any
from datetime import datetime
from sqlalchemy import and_, exists
import time

from utils.logger_handler import AppLogger
from utils.batch_process_controller import BatchProcessController
from database.db_session import DBSession

# 导入所有同步器
from database.sync.schedule_sync import ScheduleSync
from database.sync.team_sync import TeamSync
from database.sync.player_sync import PlayerSync
from database.sync.boxscore_sync import BoxscoreSync
from database.sync.playbyplay_sync import PlayByPlaySync

# 导入模型
from database.models.base_models import Game
from database.models.stats_models import GameStatsSyncHistory, Statistics


class SyncManager:
    """增强版NBA数据同步管理器"""

    def __init__(self, max_global_concurrency=8):
        """初始化同步管理器"""
        self.db_session = DBSession.get_instance()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        # 使用较小的全局并发数
        self.max_global_concurrency = max_global_concurrency

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

    def sync_schedules(self, force_update: bool = False, all_seasons: bool = True) -> Dict[str, Any]:
        """
        同步赛程数据

        Args:
            force_update: 是否强制更新
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
                # 同步所有赛季
                seasons_result = self.schedule_sync.sync_all_seasons(force_update=force_update)
                total_count = sum(seasons_result.values())

                result["details"]["all_seasons"] = {
                    "count": total_count,
                    "success": total_count > 0,
                    "seasons_detail": seasons_result
                }
            else:
                # 只同步当前赛季
                current_season_count = self.schedule_sync.sync_current_season(force_update)
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

            # 同步Play-by-Play数据
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
                    playbyplay_detail = next((d for d in playbyplay_result["details"] if d.get("game_id") == game_id),
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
        """智能并行同步剩余未同步的比赛统计数据"""
        start_time = datetime.now()
        self.logger.info(f"开始并行同步剩余未同步的比赛统计数据...")
        if with_retry:
            self.logger.info(f"启用智能重试机制，最大重试次数: {max_retries}")

        result = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "details": {}
        }

        try:
            # 1. 查询所有已完成的比赛ID
            with self.db_session.session_scope('nba') as session:
                finished_games = session.query(Game).filter(
                    Game.game_status == 3  # 已完成的比赛
                ).all()
                all_game_ids = [game.game_id for game in finished_games]

            # 如果需要倒序处理，则对game_ids进行排序
            if reverse_order:
                self.logger.info("使用倒序(从新到旧)处理比赛数据")
                # 从数据库中获取比赛时间信息
                games_with_dates = []
                with self.db_session.session_scope('nba') as session:
                    for game_id in all_game_ids:
                        game = session.query(Game).filter(Game.game_id == game_id).first()
                        if game and game.game_date_time_utc:
                            games_with_dates.append((game_id, game.game_date_time_utc))
                        else:
                            # 如果没有日期信息，给一个很早的默认日期
                            games_with_dates.append((game_id, "1946-01-01"))

                # 按日期排序（从新到旧）
                games_with_dates.sort(key=lambda x: x[1], reverse=True)

                # 提取排序后的比赛ID
                all_game_ids = [game[0] for game in games_with_dates]

                # 记录前几个ID以便确认
                if all_game_ids:
                    self.logger.info(f"排序后的前5个比赛ID: {all_game_ids[:5]}")

            # 2. 查询已同步的比赛ID和尝试过但无数据的比赛ID
            with self.db_session.session_scope('game') as session:
                # 获取boxscore已同步的比赛ID
                boxscore_synced = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'boxscore',
                    GameStatsSyncHistory.status == 'success'
                ).all()

                # 获取playbyplay已同步的比赛ID
                playbyplay_synced = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'playbyplay',
                    GameStatsSyncHistory.status == 'success'
                ).all()

                # 获取尝试同步playbyplay但标记为"no_data"的比赛ID
                no_playbyplay_data_games = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'playbyplay',
                    GameStatsSyncHistory.status == 'success',
                    GameStatsSyncHistory.details.like('%"no_data": true%')  # 查找包含no_data标记的记录
                ).all()

                # 超时但被错误标记为success的可能性较难直接从数据库判断
                # 可以考虑查询那些被标记为success但没有相应统计数据的记录
                timeout_success_games = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'playbyplay',
                    GameStatsSyncHistory.status == 'success',
                    ~exists().where(Statistics.game_id == GameStatsSyncHistory.game_id)  # 没有相应的统计数据
                ).all()

                boxscore_synced_ids = {record.game_id for record in boxscore_synced}
                playbyplay_synced_ids = {record.game_id for record in playbyplay_synced}
                no_playbyplay_data_ids = {record.game_id for record in no_playbyplay_data_games}
                timeout_success_ids = {record.game_id for record in timeout_success_games}

                # 需要重新验证的比赛(可能是超时但被错误标记为成功的)
                playbyplay_need_verify_ids = timeout_success_ids

                # 对于早期比赛，如果boxscore已同步且确认没有playbyplay数据，我们也认为它是"完全同步"的
                fully_synced_game_ids = boxscore_synced_ids.intersection(
                    playbyplay_synced_ids.union(no_playbyplay_data_ids).difference(playbyplay_need_verify_ids)
                )

            # 3. 计算需要同步的比赛ID - 分别标识需要同步boxscore和playbyplay的比赛
            boxscore_to_sync = [gid for gid in all_game_ids if gid not in boxscore_synced_ids or force_update]

            # 需要同步的playbyplay包括：
            # 1. 未同步的比赛
            # 2. 被错误标记为success的超时比赛
            # 3. 如果需要强制更新则包括所有比赛
            playbyplay_to_sync = [gid for gid in all_game_ids if
                                  gid not in playbyplay_synced_ids.union(no_playbyplay_data_ids) or
                                  gid in playbyplay_need_verify_ids or
                                  force_update]

            # 合并需要同步的比赛ID
            games_to_sync = playbyplay_to_sync # 直接使用保持顺序的列表

            # 记录数据状态
            result["total_games"] = len(all_game_ids)
            result["boxscore_synced"] = len(boxscore_synced_ids)
            result["playbyplay_synced"] = len(playbyplay_synced_ids)
            result["no_playbyplay_data"] = len(no_playbyplay_data_ids)
            result["timeout_success"] = len(timeout_success_ids)
            result["playbyplay_need_verify"] = len(playbyplay_need_verify_ids)
            result["fully_synced_games"] = len(fully_synced_game_ids)
            result["games_to_sync"] = len(games_to_sync)
            result["boxscore_to_sync"] = len(boxscore_to_sync)
            result["playbyplay_to_sync"] = len(playbyplay_to_sync)

            # 分别计算boxscore和playbyplay的同步状态
            only_boxscore_synced = len(boxscore_synced_ids - fully_synced_game_ids)
            only_playbyplay_synced = len(playbyplay_synced_ids - fully_synced_game_ids - no_playbyplay_data_ids)

            self.logger.info(f"总计{len(all_game_ids)}场比赛，完全同步{len(fully_synced_game_ids)}场，"
                             f"仅boxscore同步{only_boxscore_synced}场，"
                             f"仅playbyplay同步{only_playbyplay_synced}场，"
                             f"标记无playbyplay数据{len(no_playbyplay_data_ids)}场，"
                             f"需验证playbyplay{len(playbyplay_need_verify_ids)}场，"
                             f"剩余需要同步boxscore{len(boxscore_to_sync)}场，"
                             f"剩余需要同步playbyplay{len(playbyplay_to_sync)}场，"
                             f"总计需要处理{len(games_to_sync)}场")

            # 4. 如果没有需要同步的比赛，直接返回
            if not games_to_sync:
                end_time = datetime.now()
                result["end_time"] = end_time.isoformat()
                result["duration"] = (end_time - start_time).total_seconds()
                self.logger.info("所有比赛已同步，无需处理")
                return result

            # 5. 仅当实际需要同步的比赛数量超过阈值时，才实施分段同步策略
            if len(games_to_sync) > 1000:
                result["segmented_sync"] = True
                self.logger.info(f"检测到大量比赛({len(games_to_sync)})需要同步，将采用分段同步策略")
                return self._segmented_sync_strategy(
                    games_to_sync,  # 只传入实际需要同步的比赛
                    start_time,
                    force_update,
                    max_workers,
                    batch_size,
                    with_retry,
                    max_retries,
                    batch_interval
                )

            # 6. 常规同步流程
            if with_retry:
                # 使用带重试功能的批量同步，仅同步需要的数据
                if boxscore_to_sync:
                    self.logger.info(f"开始智能重试方式同步剩余{len(boxscore_to_sync)}场比赛的Boxscore数据")
                    boxscore_result = self.boxscore_sync.batch_sync_with_retry(
                        game_ids=boxscore_to_sync,
                        max_retries=max_retries,
                        force_update=force_update,
                        max_workers=max_workers,
                        batch_size=batch_size
                    )
                    result["details"]["boxscore"] = boxscore_result
                else:
                    self.logger.info("所有Boxscore数据已同步，无需处理")
                    result["details"]["boxscore"] = {"status": "skipped", "message": "所有数据已同步"}

                # 如果需要同步playbyplay数据，则等待一段时间后进行
                if playbyplay_to_sync:
                    # 等待一段时间后再同步playbyplay数据
                    wait_time = 120  # 增加等待时间到120秒
                    self.logger.info(f"等待{wait_time}秒后开始同步Play-by-Play数据")
                    time.sleep(wait_time)

                    self.logger.info(f"开始智能重试方式同步剩余{len(playbyplay_to_sync)}场比赛的Play-by-Play数据")
                    # 适当降低批次大小和线程数
                    playbyplay_batch_size = min(20, batch_size)
                    playbyplay_max_workers = min(4, max_workers)
                    self.logger.info(
                        f"PlayByPlay同步使用更保守的参数: 批次大小={playbyplay_batch_size}, 线程数={playbyplay_max_workers}")

                    playbyplay_result = self.playbyplay_sync.batch_sync_with_retry(
                        game_ids=playbyplay_to_sync,
                        max_retries=max_retries,
                        force_update=force_update,
                        max_workers=playbyplay_max_workers,
                        batch_size=playbyplay_batch_size
                    )
                    result["details"]["playbyplay"] = playbyplay_result
                else:
                    self.logger.info("所有Play-by-Play数据已同步，无需处理")
                    result["details"]["playbyplay"] = {"status": "skipped", "message": "所有数据已同步"}
            else:
                # 使用标准批量同步，仅同步需要的数据
                if boxscore_to_sync:
                    self.logger.info(f"开始并行同步剩余{len(boxscore_to_sync)}场比赛的Boxscore数据")
                    boxscore_result = self.boxscore_sync.batch_sync_boxscores(
                        game_ids=boxscore_to_sync,
                        force_update=force_update,
                        max_workers=max_workers,
                        batch_size=batch_size,
                        batch_interval=batch_interval
                    )
                    result["details"]["boxscore"] = boxscore_result
                else:
                    self.logger.info("所有Boxscore数据已同步，无需处理")
                    result["details"]["boxscore"] = {"status": "skipped", "message": "所有数据已同步"}

                # 如果需要同步playbyplay数据，则等待一段时间后进行
                if playbyplay_to_sync:
                    # 等待一段时间后再同步playbyplay数据
                    wait_time = 120  # 增加等待时间到120秒
                    self.logger.info(f"等待{wait_time}秒后开始同步Play-by-Play数据")
                    time.sleep(wait_time)

                    self.logger.info(f"开始并行同步剩余{len(playbyplay_to_sync)}场比赛的Play-by-Play数据")
                    # 使用更保守的参数
                    playbyplay_batch_size = min(20, batch_size)
                    playbyplay_max_workers = min(4, max_workers)

                    playbyplay_result = self.playbyplay_sync.batch_sync_playbyplay(
                        game_ids=playbyplay_to_sync,
                        force_update=force_update,
                        max_workers=playbyplay_max_workers,
                        batch_size=playbyplay_batch_size,
                        batch_interval=batch_interval * 1.5  # 增加批次间隔
                    )
                    result["details"]["playbyplay"] = playbyplay_result
                else:
                    self.logger.info("所有Play-by-Play数据已同步，无需处理")
                    result["details"]["playbyplay"] = {"status": "skipped", "message": "所有数据已同步"}

            # 设置总体状态
            if boxscore_to_sync and result["details"]["boxscore"].get("status") not in ["completed", "success",
                                                                                        "skipped"]:
                result["status"] = "partially_failed"
            elif playbyplay_to_sync and result["details"]["playbyplay"].get("status") not in ["completed", "success",
                                                                                              "skipped"]:
                result["status"] = "partially_failed"

        except Exception as e:
            self.logger.error(f"并行同步剩余比赛统计数据失败: {e}", exc_info=True)
            result["status"] = "failed"
            result["error"] = str(e)

        # 完成统计
        end_time = datetime.now()
        result["end_time"] = end_time.isoformat()
        result["duration"] = (end_time - start_time).total_seconds()

        self.logger.info(f"并行同步剩余比赛统计数据完成，状态: {result['status']}, 总耗时: {result['duration']}秒")

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
        playbyplay_to_sync = games_to_sync.copy()  # 假设所有games_to_sync都需要同步playbyplay

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

        # 创建段间控制器
        segment_controller = BatchProcessController(batch_interval=900, adaptive=True)  # 15分钟基础间隔

        # 逐段处理
        for segment_idx in range(total_segments):
            self.logger.info(f"开始处理第{segment_idx + 1}/{total_segments}段")

            # 如果不是第一个段，使用控制器等待
            if segment_idx > 0:
                segment_controller.wait_for_next_batch()

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