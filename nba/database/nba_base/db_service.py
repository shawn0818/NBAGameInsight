# db_service.py
from typing import Optional, Dict, List, Union
from datetime import datetime, date
from utils.logger_handler import AppLogger


class DatabaseService:
    """数据库服务 - 统一的数据访问接口，负责数据同步和查询"""

    def __init__(self, db_path: Optional[str] = None, env: str = "default"):
        """
        初始化数据库服务

        Args:
            db_path: 数据库文件路径，如果为None则使用配置中的默认路径
            env: 环境名称，可以是 "default", "test", "development", "production"
        """
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        # 如果未提供db_path，则使用配置中的路径
        if db_path is None:
            from config import NBAConfig
            db_path = str(NBAConfig.DATABASE.get_db_path(env))

        # 导入并创建数据库管理器
        from nba.database.nba_base.db_manager import DBManager
        self.db_manager = DBManager(db_path)

        # 创建同步管理器
        from nba.database.nba_base.nba_sync_manager import NBASyncManager
        self.sync_manager = NBASyncManager(self.db_manager)

        # 延迟初始化仓库对象
        self._team_repository = None
        self._player_repository = None
        self._schedule_repository = None

    def get_database_path(self) -> str:
        """获取当前使用的数据库文件路径"""
        return self.db_manager.db_path

    def initialize(self, force_sync: bool = False) -> bool:
        """初始化数据库并执行初始数据同步"""
        try:
            # 检查是否是首次运行
            is_first_run = self.sync_manager.is_first_run()

            # 如果是首次运行或强制同步，执行初始数据同步
            if is_first_run or force_sync:
                self.logger.info("执行初始数据同步...")
                result = self.sync_manager.initial_data_sync()
                return result.get("status") == "success"

            return True

        except Exception as e:
            self.logger.error(f"数据库初始化失败: {e}")
            return False

    def sync_current_season_schedule(self, force_update: bool = False) -> bool:
        """
        同步当前赛季赛程数据
        建议频率：每天一次
        """
        try:
            result = self.sync_manager.sync_current_season(force_update=force_update)
            return result.get("status") == "success"
        except Exception as e:
            self.logger.error(f"同步当前赛季赛程数据失败: {e}")
            return False

    def sync_new_season(self, season: Optional[str] = None, force_update: bool = True) -> bool:
        """
        新赛季开始时更新所有数据（球队、球员、赛程）
        建议频率：一年调用1-2次，通常在赛季初或交易截止日之后

        Args:
            season: 赛季标识，如"2024-25"，默认使用当前赛季
            force_update: 是否强制更新，默认为True以确保全量更新

        Returns:
            bool: 同步是否成功
        """
        try:
            result = self.sync_manager.new_season_sync(season=season, force_update=force_update)
            return result.get("status") == "success"
        except Exception as e:
            self.logger.error(f"同步新赛季数据失败: {e}")
            return False

    def sync_data(self, data_type: str, force_update: bool = False) -> bool:
        """
        按需同步指定类型的数据

        Args:
            data_type: 数据类型，可选值:
                      'teams' - 同步球队数据
                      'players' - 同步球员数据
                      'schedule' - 同步当前赛季赛程
                      'all' - 同步所有数据（相当于新赛季同步）
            force_update: 是否强制更新

        Returns:
            bool: 同步是否成功
        """
        try:

            if data_type.lower() == 'teams':
                result = self.sync_manager.sync_teams(force_update=force_update)
            elif data_type.lower() == 'players':
                result = self.sync_manager.sync_players(force_update=force_update)
            elif data_type.lower() == 'schedule':
                result = self.sync_manager.sync_current_season(force_update=force_update)
            elif data_type.lower() == 'all':
                result = self.sync_manager.new_season_sync(force_update=force_update)
            else:
                self.logger.error(f"未知的数据类型: {data_type}")
                return False

            if isinstance(result, dict):
                return result.get("status") == "success"
            return bool(result)

        except Exception as e:
            self.logger.error(f"同步{data_type}数据失败: {e}")
            return False

    # 获取仓库对象的懒加载方法
    def get_team_repository(self):
        if not self._team_repository:
            from nba.database.nba_base.team_repository import TeamRepository
            self._team_repository = TeamRepository(self.db_manager)
        return self._team_repository

    def get_player_repository(self):
        if not self._player_repository:
            from nba.database.nba_base.player_repository import PlayerRepository
            self._player_repository = PlayerRepository(self.db_manager)
        return self._player_repository

    def get_schedule_repository(self):
        if not self._schedule_repository:
            from nba.database.nba_base.schedule_repository import ScheduleRepository
            self._schedule_repository = ScheduleRepository(self.db_manager)
        return self._schedule_repository

    # ======== 球队相关查询方法 ========

    def get_team_id_by_name(self, name: str) -> Optional[int]:
        """
        通过名称获取球队ID，支持名称、缩写、城市名等多种形式

        Args:
            name: 球队名称、缩写、城市名或team_slug

        Returns:
            Optional[int]: 球队ID，未找到时返回None
        """
        try:
            team_repo = self.get_team_repository()
            return team_repo.get_team_id_by_name(name)
        except Exception as e:
            self.logger.error(f"获取球队ID失败: {e}")
            return None

    def get_team_name_by_id(self, team_id: int, name_type: str = 'full') -> Optional[str]:
        """
        通过ID获取球队名称

        Args:
            team_id: 球队ID
            name_type: 返回的名称类型，可选值包括:
                      'full' - 完整名称 (城市+昵称)
                      'nickname' - 仅球队昵称
                      'city' - 仅城市名
                      'abbr' - 球队缩写

        Returns:
            Optional[str]: 球队名称，未找到时返回None
        """
        try:
            team_repo = self.get_team_repository()
            return team_repo.get_team_name_by_id(team_id, name_type)
        except Exception as e:
            self.logger.error(f"获取球队名称失败: {e}")
            return None

    # ======== 球员相关查询方法 ========

    def get_player_id_by_name(self, name: str) -> Optional[int]:
        """
        通过球员名称查询ID，支持模糊匹配

        Args:
            name: 球员名称(全名、姓、名、slug等)

        Returns:
            Optional[int]: 球员ID，未找到或模糊匹配度不足时返回None
        """
        try:
            player_repo = self.get_player_repository()
            return player_repo.get_player_id_by_name(name)
        except Exception as e:
            self.logger.error(f"获取球员ID失败: {e}")
            return None

    def get_player_name_by_id(self, player_id: int, name_type: str = 'full') -> Optional[str]:
        """
        通过ID获取球员名称

        Args:
            player_id: 球员ID
            name_type: 返回的名称类型，可选值:
                      'full' - 完整名称(名姓格式，如 LeBron James)
                      'last_first' - 姓名格式(如 James, LeBron)
                      'first' - 仅名字(如 LeBron)
                      'last' - 仅姓氏(如 James)

        Returns:
            Optional[str]: 球员名称，未找到时返回None
        """
        try:
            player_repo = self.get_player_repository()
            return player_repo.get_player_name_by_id(player_id, name_type)
        except Exception as e:
            self.logger.error(f"获取球员名称失败: {e}")
            return None

    # ======== 赛程相关查询方法 ========

    def get_game_id(self, team_id: int, date_query: str = 'today') -> Optional[str]:
        """获取指定球队在特定日期的比赛ID"""
        try:
            schedule_repo = self.get_schedule_repository()
            return schedule_repo.get_game_id(team_id, date_query)
        except Exception as e:
            self.logger.error(f"获取比赛ID失败: {e}")
            return None

    def get_team_next_game(self, team_id: int) -> Optional[Dict]:
        """
        获取指定球队的下一场比赛

        Args:
            team_id: 球队ID

        Returns:
            Optional[Dict]: 下一场比赛信息，无下一场比赛时返回None
        """
        try:
            schedule_repo = self.get_schedule_repository()
            return schedule_repo.get_team_next_schedule(team_id)
        except Exception as e:
            self.logger.error(f"获取球队下一场比赛失败: {e}")
            return None

    def get_team_last_game(self, team_id: int) -> Optional[Dict]:
        """
        获取指定球队的上一场比赛

        Args:
            team_id: 球队ID

        Returns:
            Optional[Dict]: 上一场比赛信息，无上一场比赛时返回None
        """
        try:
            schedule_repo = self.get_schedule_repository()
            return schedule_repo.get_team_last_schedule(team_id)
        except Exception as e:
            self.logger.error(f"获取球队上一场比赛失败: {e}")
            return None

    def get_schedules_by_date(self, target_date: Union[str, date, datetime]) -> List[Dict]:
        """
        获取指定日期的赛程

        Args:
            target_date: 目标日期，可以是日期对象或YYYY-MM-DD格式的字符串

        Returns:
            List[Dict]: 匹配的赛程信息列表
        """
        try:
            schedule_repo = self.get_schedule_repository()
            return schedule_repo.get_schedules_by_date(target_date)
        except Exception as e:
            self.logger.error(f"获取日期赛程失败: {e}")
            return []

    def get_schedules_by_team(self, team_id: int, limit: int = 10) -> List[Dict]:
        """
        获取指定球队的赛程

        Args:
            team_id: 球队ID
            limit: 最大返回数量

        Returns:
            List[Dict]: 匹配的赛程信息列表
        """
        try:
            schedule_repo = self.get_schedule_repository()
            return schedule_repo.get_schedules_by_team(team_id, limit)
        except Exception as e:
            self.logger.error(f"获取球队赛程失败: {e}")
            return []


    def close(self):
        """关闭数据库连接"""
        try:
            if self.db_manager:
                self.db_manager.close()
                self.logger.info("数据库连接已关闭")
        except Exception as e:
            self.logger.error(f"关闭数据库连接失败: {e}")