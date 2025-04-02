# database/db_service.py
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from database.db_session import DBSession
from database.sync.sync_manager import SyncManager
from utils.logger_handler import AppLogger

# Import Repositories
from database.repositories.schedule_repository import ScheduleRepository
from database.repositories.team_repository import TeamRepository
from database.repositories.player_repository import PlayerRepository
from database.repositories.boxscore_repository import BoxscoreRepository
from database.repositories.playbyplay_repository import PlayByPlayRepository

# Import Models needed for checks
from database.models.base_models import Team, Game
from database.models.stats_models import GameStatsSyncHistory


class DatabaseService:
    """数据库服务统一接口

    提供数据库访问和核心同步操作的高级API。
    主要负责：
    1. 初始化数据库连接。
    2. 首次启动时自动同步核心数据（球队、球员、所有赛程）。
    3. 提供手动触发增量并行同步比赛统计数据的方法。
    4. 提供手动触发新赛季核心数据更新的方法（球队、球员、当前赛季赛程）。
    5. 提供基础的ID查询功能。
    """

    def __init__(self, env: str = "default", max_global_concurrency: int = 20):
        """初始化数据库服务

        Args:
            env: 环境名称，可以是 "default", "test", "development", "production"
            max_global_concurrency: 全局最大并发请求数
        """
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')
        self.env = env
        self.max_global_concurrency = max_global_concurrency

        # 获取单例实例
        self.db_session = DBSession.get_instance()
        # 初始化SyncManager，传入全局并发数限制
        self.sync_manager = SyncManager(max_global_concurrency=max_global_concurrency)

        # 初始化各个Repository
        self.schedule_repo = ScheduleRepository()
        self.team_repo = TeamRepository()
        self.player_repo = PlayerRepository()
        self.boxscore_repo = BoxscoreRepository()
        self.playbyplay_repo = PlayByPlayRepository()

        # 标记初始化状态
        self._initialized = False

    def initialize(self, create_tables: bool = True) -> bool:
        """初始化数据库连接和服务

        如果核心数据库为空，会自动执行首次全量核心数据同步。

        Args:
            create_tables: 是否创建表结构

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 初始化数据库会话
            self.db_session.initialize(env=self.env, create_tables=create_tables)
            self._initialized = True
            self.logger.info(f"数据库服务初始化成功，环境: {self.env}")

            # 检查核心数据库是否为空，如果为空则自动同步
            if self._is_nba_database_empty():
                self.logger.info("检测到核心数据库为空，开始自动执行首次核心数据同步...")
                sync_result = self._perform_initial_core_sync()
                if sync_result.get("status") == "success":
                    self.logger.info("首次核心数据同步成功")
                else:
                    self.logger.warning(f"首次核心数据同步部分失败: {sync_result}")
                    # 即使首次同步失败，初始化本身也算成功，后续可以手动重试
            else:
                self.logger.info("核心数据库已存在数据，跳过首次自动同步")

            return True
        except Exception as e:
            self.logger.error(f"数据库服务初始化失败: {e}", exc_info=True)
            self._initialized = False  # 确保标记为未初始化
            return False

    def _is_nba_database_empty(self) -> bool:
        """检查核心数据库(nba.db)是否为空"""
        if not self._initialized:
            # 如果服务未初始化成功，无法检查，保守返回True（触发同步）
            self.logger.warning("数据库服务未初始化，无法检查是否为空，假设为空")
            return True

        try:
            with self.db_session.session_scope('nba') as session:
                # 检查是否有任何球队记录
                team_count = session.query(Team).count()
                return team_count == 0
        except Exception as e:
            self.logger.error(f"检查核心数据库是否为空失败: {e}", exc_info=True)
            # 发生错误时，保守返回True，尝试进行同步
            return True

    def _perform_initial_core_sync(self) -> Dict[str, Any]:
        """执行首次核心数据同步（球队、球员、所有赛程）"""
        start_time = datetime.now()
        self.logger.info("开始首次核心数据同步...")
        results = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "details": {}
        }
        all_success = True

        try:
            # 1. 同步球队 (强制)
            self.logger.info("同步球队信息...")
            team_result = self.sync_manager.sync_teams(force_update=True)
            results["details"]["teams"] = team_result
            if team_result.get("status") != "success":
                all_success = False
                self.logger.error("首次同步球队信息失败")

            # 2. 同步球员 (强制)
            self.logger.info("同步球员信息...")
            player_result = self.sync_manager.sync_players(force_update=True)
            results["details"]["players"] = player_result
            if player_result.get("status") != "success":
                all_success = False
                self.logger.error("首次同步球员信息失败")

            # 3. 同步所有赛程 (强制)
            self.logger.info("同步所有赛季赛程信息...")
            schedule_result = self.sync_manager.sync_schedules(force_update=True, all_seasons=True)
            results["details"]["schedules"] = schedule_result
            if schedule_result.get("status") != "success":
                all_success = False
                self.logger.error("首次同步所有赛程信息失败")

            if not all_success:
                results["status"] = "partially_failed"

        except Exception as e:
            self.logger.error(f"首次核心数据同步过程中发生异常: {e}", exc_info=True)
            results["status"] = "failed"
            results["error"] = str(e)

        end_time = datetime.now()
        results["end_time"] = end_time.isoformat()
        results["duration"] = (end_time - start_time).total_seconds()
        self.logger.info(f"首次核心数据同步完成，状态: {results['status']}, 耗时: {results['duration']:.2f}秒")
        return results

    def sync_remaining_data_parallel(self, force_update: bool = False, max_workers: int = 10,
                                     batch_size: int = 50, reverse_order: bool = False,
                                     with_retry: bool = True, max_retries: int = 3,
                                     batch_interval: int = 60) -> Dict[str, Any]:
        """并行同步剩余未同步的比赛统计数据 (gamedb)

        这是日常/手动更新比赛统计数据的主要方法。

        Args:
            force_update: 是否强制更新已同步过的数据。
            max_workers: 最大工作线程数。
            batch_size: 每批处理的比赛数量。
            reverse_order: 是否优先处理最新的比赛。
            with_retry: 是否启用智能重试机制。
            max_retries: 最大重试次数。
            batch_interval: 批次之间的间隔时间(秒)。

        Returns:
            Dict[str, Any]: 同步结果摘要。
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行并行同步")
            return {"status": "failed", "error": "数据库服务未初始化"}

        self.logger.info(f"开始并行同步剩余未同步的比赛统计数据，最大线程数: {max_workers}, 批次大小: {batch_size}, "
                         f"使用重试机制: {with_retry}, 最大重试次数: {max_retries}, 批次间隔: {batch_interval}秒")

        # 调用优化后的SyncManager方法
        result = self.sync_manager.sync_remaining_game_stats_parallel(
            force_update=force_update,
            max_workers=max_workers,
            batch_size=batch_size,
            reverse_order=reverse_order,
            with_retry=with_retry,
            max_retries=max_retries,
            batch_interval=batch_interval
        )

        return result

    def sync_single_game(self, game_id: str, force_update: bool = False,
                         with_retry: bool = True) -> Dict[str, Any]:
        """同步单场比赛的统计数据，支持重试机制

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新，即使已同步
            with_retry: 是否启用智能重试机制

        Returns:
            Dict[str, Any]: 同步结果
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法同步单场比赛")
            return {"status": "failed", "error": "数据库服务未初始化"}

        self.logger.info(f"开始同步单场比赛(ID:{game_id})，使用重试机制: {with_retry}")
        return self.sync_manager.sync_game_stats(game_id, force_update, with_retry)

    def sync_new_season_core_data(self, force_update: bool = True) -> Dict[str, Any]:
        """同步新赛季的核心数据 (nba.db)

        用于赛季开始时，强制更新球队、球员信息，并同步当前赛季的赛程。

        Args:
            force_update: 是否强制更新，对于新赛季同步，通常应为True。

        Returns:
            Dict[str, Any]: 同步结果摘要。
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法同步新赛季核心数据")
            return {"status": "failed", "error": "数据库服务未初始化"}

        start_time = datetime.now()
        self.logger.info("开始同步新赛季核心数据...")
        results = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "details": {}
        }
        all_success = True

        try:
            # 1. 同步球队 (强制)
            self.logger.info("强制更新球队信息...")
            team_result = self.sync_manager.sync_teams(force_update=force_update)
            results["details"]["teams"] = team_result
            if team_result.get("status") != "success":
                all_success = False
                self.logger.error("新赛季同步球队信息失败")

            # 2. 同步球员 (强制)
            self.logger.info("强制更新球员信息...")
            player_result = self.sync_manager.sync_players(force_update=force_update)
            results["details"]["players"] = player_result
            if player_result.get("status") != "success":
                all_success = False
                self.logger.error("新赛季同步球员信息失败")

            # 3. 同步当前赛季赛程 (强制)
            self.logger.info("同步当前赛季赛程信息...")
            # 注意：all_seasons=False 表示只同步当前赛季
            schedule_result = self.sync_manager.sync_schedules(force_update=force_update, all_seasons=False)
            results["details"]["schedules"] = schedule_result
            if schedule_result.get("status") != "success":
                all_success = False
                self.logger.error("新赛季同步当前赛程信息失败")

            if not all_success:
                results["status"] = "partially_failed"

        except Exception as e:
            self.logger.error(f"新赛季核心数据同步过程中发生异常: {e}", exc_info=True)
            results["status"] = "failed"
            results["error"] = str(e)

        end_time = datetime.now()
        results["end_time"] = end_time.isoformat()
        results["duration"] = (end_time - start_time).total_seconds()
        self.logger.info(f"新赛季核心数据同步完成，状态: {results['status']}, 耗时: {results['duration']:.2f}秒")
        return results

    # --- Repository Access Methods ---

    def get_team_id_by_name(self, team_name: str) -> Optional[int]:
        """获取球队ID"""
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行查询")
            return None

        try:
            return self.team_repo.get_team_id_by_name(team_name)
        except Exception as e:
            self.logger.error(f"获取球队ID失败: {e}", exc_info=True)
            return None

    def get_player_id_by_name(self, player_name: str) -> Optional[Union[int, List[int]]]:
        """获取球员ID"""
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行查询")
            return None

        try:
            return self.player_repo.get_player_id_by_name(player_name)
        except Exception as e:
            self.logger.error(f"获取球员ID失败: {e}", exc_info=True)
            return None

    def get_game_id(self, team_id: int, date_str: str = "last") -> Optional[str]:
        """查找指定球队在特定日期的比赛ID"""
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行查询")
            return None

        try:
            # 使用ScheduleRepository的方法获取比赛ID
            if date_str.lower() == 'last':
                # 获取上一场比赛
                last_game = self.schedule_repo.get_team_last_schedule(team_id)
                if last_game:
                    game_id = last_game.get('game_id')
                    # (日期格式化逻辑保持不变)
                    formatted_time = self._format_game_time(last_game)
                    self.logger.info(f"找到最近已完成的比赛: ID={game_id}, 北京时间={formatted_time}")
                    return game_id
                else:
                    self.logger.warning(f"未找到球队ID={team_id}的最近比赛")
                    return None
            else:
                # 使用ScheduleRepository的get_game_id方法
                return self.schedule_repo.get_game_id(team_id, date_str)
        except Exception as e:
            self.logger.error(f"获取比赛ID失败: {e}", exc_info=True)
            return None

    def _format_game_time(self, game_data: Dict) -> str:
        """辅助函数：格式化比赛时间为易读字符串"""
        if 'game_date_time_bjs' in game_data and game_data['game_date_time_bjs']:
            try:
                import re
                time_str = game_data['game_date_time_bjs']
                match = re.match(r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2}).*', time_str)
                if match:
                    date_part, time_part = match.groups()
                    dt = datetime.strptime(f"{date_part} {time_part}", '%Y-%m-%d %H:%M:%S')
                    return dt.strftime('%Y年%m月%d日 %H:%M')
                else:
                    dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                    return dt.strftime('%Y年%m月%d日 %H:%M')
            except Exception as e:
                self.logger.debug(f"日期解析失败: {e}, 使用原始值: {game_data['game_date_time_bjs']}")
                return game_data['game_date_time_bjs']
        elif ('game_date_bjs' in game_data and game_data['game_date_bjs']) and \
                ('game_time_bjs' in game_data and game_data['game_time_bjs']):
            try:
                dt = datetime.strptime(f"{game_data['game_date_bjs']} {game_data['game_time_bjs']}",
                                       '%Y-%m-%d %H:%M:%S')
                return dt.strftime('%Y年%m月%d日 %H:%M')
            except Exception:
                return f"{game_data['game_date_bjs']} {game_data['game_time_bjs']}"
        elif 'game_date_bjs' in game_data and game_data['game_date_bjs']:
            try:
                dt = datetime.strptime(game_data['game_date_bjs'], '%Y-%m-%d')
                return dt.strftime('%Y年%m月%d日')
            except Exception:
                return game_data['game_date_bjs']
        else:
            return game_data.get('game_date', '未知日期')

    def get_sync_progress(self) -> Dict[str, Any]:
        """获取比赛统计数据(gamedb)的同步进度

        Returns:
            Dict: 包含同步进度统计的字典
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法获取同步进度")
            return {"error": "数据库服务未初始化"}

        try:
            # 获取所有已完成比赛总数
            total_finished_games = 0
            with self.db_session.session_scope('nba') as session:
                total_finished_games = session.query(Game).filter(
                    Game.game_status == 3
                ).count()

            # 获取已成功同步的boxscore比赛数 (以boxscore为基准判断是否同步)
            synced_games = 0
            with self.db_session.session_scope('game') as session:
                synced_games = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'boxscore',
                    GameStatsSyncHistory.status == 'success'
                ).distinct().count()

            # 计算进度
            progress_percentage = 0
            if total_finished_games > 0:
                progress_percentage = (synced_games / total_finished_games) * 100

            result = {
                "total_games": total_finished_games,
                "synced_games": synced_games,
                "remaining_games": total_finished_games - synced_games,
                "progress_percentage": round(progress_percentage, 2),
                "timestamp": datetime.now().isoformat()
            }

            return result

        except Exception as e:
            self.logger.error(f"获取同步进度失败: {e}", exc_info=True)
            return {"error": str(e)}

    def close(self) -> None:
        """关闭数据库连接"""
        if self._initialized:
            try:
                self.db_session.close_all()
                self.logger.info("数据库连接已关闭")
                self._initialized = False  # 标记为未初始化
            except Exception as e:
                self.logger.error(f"关闭数据库连接失败: {e}", exc_info=True)