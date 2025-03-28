# sync/sync_manager.py
from typing import Dict, List, Optional, Any, Union, Set
from datetime import datetime, timedelta
from sqlalchemy import and_, or_, not_, exists, func
import concurrent.futures
import threading

from utils.logger_handler import AppLogger
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
    """
    NBA数据同步管理器
    负责协调和管理所有数据同步操作
    提供统一的接口进行数据同步
    """

    def __init__(self):
        """初始化同步管理器"""
        self.db_session = DBSession.get_instance()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        # 初始化所有同步器
        self.schedule_sync = ScheduleSync()
        self.team_sync = TeamSync()
        self.player_sync = PlayerSync()
        self.boxscore_sync = BoxscoreSync()
        self.playbyplay_sync = PlayByPlaySync()

        self.logger.info("同步管理器初始化完成")

    def sync_all(self, force_update: bool = False, skip_game_stats: bool = False) -> Dict[str, Any]:
        """
        执行全量数据同步

        Args:
            force_update: 是否强制更新所有数据
            skip_game_stats: 是否跳过比赛统计数据同步，默认为False

        Returns:
            Dict: 同步结果摘要
        """
        start_time = datetime.now()
        self.logger.info("开始全量数据同步...")

        results = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "details": {}
        }

        try:
            # 1. 同步球队基本信息
            team_result = self.sync_teams(force_update)
            results["details"]["teams"] = team_result

            # 2. 同步球员信息
            player_result = self.sync_players(force_update)
            results["details"]["players"] = player_result

            # 3. 同步赛程信息（指定all_seasons=True确保同步所有赛季）
            schedule_result = self.sync_schedules(force_update, all_seasons=True)
            results["details"]["schedules"] = schedule_result

            # 4. 全量同步比赛统计数据（如果不跳过）
            if not skip_game_stats:
                game_stats_result = self.sync_all_game_stats(force_update)
                results["details"]["game_stats"] = game_stats_result

            # 同步完成，记录结束时间
            end_time = datetime.now()
            results["end_time"] = end_time.isoformat()
            results["duration"] = (end_time - start_time).total_seconds()

            self.logger.info(f"全量数据同步完成，耗时: {results['duration']}秒")

        except Exception as e:
            self.logger.error(f"全量数据同步失败: {e}", exc_info=True)
            results["status"] = "failed"
            results["error"] = str(e)

            end_time = datetime.now()
            results["end_time"] = end_time.isoformat()
            results["duration"] = (end_time - start_time).total_seconds()

        return results

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

    def sync_game_stats(self, game_id: str, force_update: bool = False) -> Dict[str, Any]:
        """
        同步指定比赛的统计数据

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新，默认为False

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
            boxscore_result = self.boxscore_sync.sync_boxscore(game_id, force_update)
            result["details"]["boxscore"] = boxscore_result

            # 同步Play-by-Play数据
            playbyplay_result = self.playbyplay_sync.sync_playbyplay(game_id, force_update)
            result["details"]["playbyplay"] = playbyplay_result

            # 检查同步结果
            boxscore_success = boxscore_result.get("status") == "success"
            playbyplay_success = playbyplay_result.get("status") == "success"

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

    def sync_all_game_stats(self, force_update: bool = False) -> Dict[str, Any]:
        """
        全量同步所有已完成比赛的统计数据（串行方式）

        Args:
            force_update: 是否强制更新，默认为False

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info("开始全量同步比赛统计数据...")

        result = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "details": {
                "total_games": 0,
                "synced_games": 0,
                "failed_games": 0,
                "skipped_games": 0
            }
        }

        try:
            # 查询所有已完成的比赛
            with self.db_session.session_scope('nba') as session:
                finished_games = session.query(Game).filter(
                    Game.game_status == 3  # 已完成的比赛
                ).all()

                result["details"]["total_games"] = len(finished_games)

                self.logger.info(f"找到{len(finished_games)}场已完成的比赛需要同步")

                # 对每场比赛进行同步
                for i, game in enumerate(finished_games):
                    self.logger.info(f"正在同步第{i + 1}/{len(finished_games)}场比赛(ID:{game.game_id})...")

                    # 同步比赛统计数据
                    game_result = self.sync_game_stats(game.game_id, force_update)

                    # 统计结果
                    if game_result.get("details", {}).get("already_synchronized", False):
                        result["details"]["skipped_games"] += 1
                    elif game_result["status"] == "success":
                        result["details"]["synced_games"] += 1
                    else:
                        result["details"]["failed_games"] += 1

                # 统计成功率
                success_rate = 0
                if result["details"]["total_games"] > 0:
                    success_rate = (result["details"]["synced_games"] + result["details"]["skipped_games"]) / \
                                   result["details"]["total_games"] * 100

                result["details"]["success_rate"] = round(success_rate, 2)

                # 设置总体状态
                if result["details"]["failed_games"] > 0:
                    if result["details"]["synced_games"] > 0:
                        result["status"] = "partially_failed"
                    else:
                        result["status"] = "failed"

        except Exception as e:
            self.logger.error(f"全量同步比赛统计数据失败: {e}", exc_info=True)
            result["status"] = "failed"
            result["error"] = str(e)

        end_time = datetime.now()
        result["end_time"] = end_time.isoformat()
        result["duration"] = (end_time - start_time).total_seconds()

        return result

    def sync_all_game_stats_parallel(self, force_update: bool = False, max_workers: int = 10,
                                     batch_size: int = 50) -> Dict[str, Any]:
        """
        使用并行处理同步所有已完成比赛的统计数据

        Args:
            force_update: 是否强制更新
            max_workers: 最大工作线程数
            batch_size: 每批处理的比赛数量

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info(f"开始并行同步所有比赛统计数据，最大线程数: {max_workers}, 批次大小: {batch_size}")

        result = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "details": {
                "boxscore": {},
                "playbyplay": {}
            }
        }

        try:
            # 查询所有已完成的比赛
            with self.db_session.session_scope('nba') as session:
                finished_games = session.query(Game).filter(
                    Game.game_status == 3  # 已完成的比赛
                ).all()

                game_ids = [game.game_id for game in finished_games]

                result["total_games"] = len(game_ids)
                self.logger.info(f"找到{len(game_ids)}场已完成的比赛需要同步")

                # 1. 首先并行同步所有boxscore数据
                self.logger.info("开始并行同步所有Boxscore数据")
                boxscore_result = self.boxscore_sync.batch_sync_boxscores(
                    game_ids=game_ids,
                    force_update=force_update,
                    max_workers=max_workers,
                    batch_size=batch_size
                )
                result["details"]["boxscore"] = boxscore_result

                # 2. 然后并行同步所有playbyplay数据（根据需要）
                self.logger.info("开始并行同步所有Play-by-Play数据")
                playbyplay_result = self.playbyplay_sync.batch_sync_playbyplay(
                    game_ids=game_ids,
                    force_update=force_update,
                    max_workers=max_workers,
                    batch_size=batch_size
                )
                result["details"]["playbyplay"] = playbyplay_result

                # 设置总体状态
                if boxscore_result.get("status") != "completed":
                    result["status"] = "partially_failed"

        except Exception as e:
            self.logger.error(f"并行同步所有比赛统计数据失败: {e}", exc_info=True)
            result["status"] = "failed"
            result["error"] = str(e)

        # 完成统计
        end_time = datetime.now()
        result["end_time"] = end_time.isoformat()
        result["duration"] = (end_time - start_time).total_seconds()

        self.logger.info(f"并行同步所有比赛统计数据完成，状态: {result['status']}, 总耗时: {result['duration']}秒")

        return result

    def sync_unsynchronized_game_stats(self) -> Dict[str, Any]:
        """
        增量同步未同步过的比赛统计数据（串行方式）

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info("开始增量同步比赛统计数据...")

        result = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "details": {
                "total_games": 0,
                "synced_games": 0,
                "failed_games": 0
            }
        }

        try:
            # 首先获取所有已完成的比赛ID
            finished_game_ids = set()
            with self.db_session.session_scope('nba') as session:
                games = session.query(Game.game_id).filter(
                    Game.game_status == 3  # 已完成的比赛
                ).all()

                finished_game_ids = {game.game_id for game in games}

            # 然后获取所有已同步的比赛ID
            synchronized_game_ids = set()
            with self.db_session.session_scope('game') as session:
                # 获取有成功boxscore同步记录的比赛ID
                boxscore_synced = session.query(GameStatsSyncHistory.game_id).filter(
                    and_(
                        GameStatsSyncHistory.sync_type == 'boxscore',
                        GameStatsSyncHistory.status == 'success'
                    )
                ).distinct().all()

                boxscore_synced_ids = {record.game_id for record in boxscore_synced}

                # 获取有成功playbyplay同步记录的比赛ID
                playbyplay_synced = session.query(GameStatsSyncHistory.game_id).filter(
                    and_(
                        GameStatsSyncHistory.sync_type == 'playbyplay',
                        GameStatsSyncHistory.status == 'success'
                    )
                ).distinct().all()

                playbyplay_synced_ids = {record.game_id for record in playbyplay_synced}

                # 两种数据都同步成功的才算完全同步
                synchronized_game_ids = boxscore_synced_ids.intersection(playbyplay_synced_ids)

            # 计算需要同步的比赛ID
            games_to_sync = finished_game_ids - synchronized_game_ids

            result["details"]["total_games"] = len(games_to_sync)

            self.logger.info(f"找到{len(games_to_sync)}场已完成但未同步的比赛需要同步")

            # 对每场未同步的比赛进行同步
            for i, game_id in enumerate(sorted(games_to_sync)):
                self.logger.info(f"正在同步第{i + 1}/{len(games_to_sync)}场比赛(ID:{game_id})...")

                # 同步比赛统计数据，不需要force_update
                game_result = self.sync_game_stats(game_id, force_update=False)

                # 统计结果
                if game_result["status"] == "success":
                    result["details"]["synced_games"] += 1
                else:
                    result["details"]["failed_games"] += 1

            # 统计成功率
            success_rate = 0
            if result["details"]["total_games"] > 0:
                success_rate = result["details"]["synced_games"] / result["details"]["total_games"] * 100

            result["details"]["success_rate"] = round(success_rate, 2)

            # 设置总体状态
            if result["details"]["failed_games"] > 0:
                if result["details"]["synced_games"] > 0:
                    result["status"] = "partially_failed"
                else:
                    result["status"] = "failed"

        except Exception as e:
            self.logger.error(f"增量同步比赛统计数据失败: {e}", exc_info=True)
            result["status"] = "failed"
            result["error"] = str(e)

        end_time = datetime.now()
        result["end_time"] = end_time.isoformat()
        result["duration"] = (end_time - start_time).total_seconds()

        return result

    def sync_remaining_game_stats_parallel(self, force_update: bool = False, max_workers: int = 10,
                                           batch_size: int = 50) -> Dict[str, Any]:
        """
        使用并行处理同步剩余未同步的比赛统计数据

        Args:
            force_update: 是否强制更新
            max_workers: 最大工作线程数
            batch_size: 每批处理的比赛数量

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info(f"开始并行同步剩余未同步的比赛统计数据...")

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

            # 2. 查询已同步的boxscore数据的比赛ID
            with self.db_session.session_scope('game') as session:
                synced_records = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'boxscore',
                    GameStatsSyncHistory.status == 'success'
                ).all()
                synced_game_ids = {record.game_id for record in synced_records}

            # 3. 计算需要同步的比赛ID
            games_to_sync = [gid for gid in all_game_ids if gid not in synced_game_ids]

            result["total_games"] = len(all_game_ids)
            result["synced_games"] = len(synced_game_ids)
            result["games_to_sync"] = len(games_to_sync)

            self.logger.info(f"总计{len(all_game_ids)}场比赛，已同步{len(synced_game_ids)}场，"
                             f"剩余{len(games_to_sync)}场需要同步")

            # 4. 如果没有需要同步的比赛，直接返回
            if not games_to_sync:
                end_time = datetime.now()
                result["end_time"] = end_time.isoformat()
                result["duration"] = (end_time - start_time).total_seconds()
                self.logger.info("所有比赛已同步，无需处理")
                return result

            # 5. 并行同步所有boxscore数据
            self.logger.info(f"开始并行同步剩余{len(games_to_sync)}场比赛的Boxscore数据")
            boxscore_result = self.boxscore_sync.batch_sync_boxscores(
                game_ids=games_to_sync,
                force_update=force_update,
                max_workers=max_workers,
                batch_size=batch_size
            )
            result["details"]["boxscore"] = boxscore_result

            # 6. 并行同步所有playbyplay数据（根据需要）
            self.logger.info(f"开始并行同步剩余{len(games_to_sync)}场比赛的Play-by-Play数据")
            playbyplay_result = self.playbyplay_sync.batch_sync_playbyplay(
                game_ids=games_to_sync,
                force_update=force_update,
                max_workers=max_workers,
                batch_size=batch_size
            )
            result["details"]["playbyplay"] = playbyplay_result

            # 设置总体状态
            if boxscore_result.get("status") != "completed":
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