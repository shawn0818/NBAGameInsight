# game_data_service.py
from typing import Optional, Any
from functools import lru_cache
from pathlib import Path
from dataclasses import dataclass

from nba.database.db_service import DatabaseService
from nba.fetcher.game_fetcher import GameFetcher
from nba.parser.game_parser import GameDataParser
from nba.models.game_model import Game

from config import NBAConfig
from utils.logger_handler import AppLogger


class ServiceNotReadyError(Exception):
    """服务未就绪异常"""
    pass


class InitializationError(Exception):
    """初始化失败异常"""
    pass


@dataclass
class GameDataConfig:
    """服务配置类

    配置GameDataProvider服务的各项参数。

    Attributes:
        default_team (str, optional): 默认的球队名称
        default_player (str, optional): 默认的球员名称
        date_str (str): 日期字符串，默认为"last"表示最近一场比赛
        cache_size (int): 缓存大小，默认128
        cache_dir (Path): 缓存目录
        auto_refresh (bool): 是否自动刷新数据
        use_pydantic_v2 (bool): 是否使用Pydantic v2
    """
    default_team: Optional[str] = "Lakers"
    default_player: Optional[str] = "LeBron James"
    date_str: str = "last"
    cache_size: int = 128
    cache_dir: Path = NBAConfig.PATHS.CACHE_DIR
    auto_refresh: bool = False  # 默认不自动刷新数据
    use_pydantic_v2: bool = True


class GameDataProvider:
    """
    GameDataService的核心职责是：数据获取和解析。负责协调 GameFetcher和 GameParser从外部数据源
    （例如 NBA API）获取原始数据，并将其解析成我们系统内部可以理解和操作的 GameModel对象，交给系统的
    其他部分 (例如 NBAService, GameDisplayService) 去使用和加工。
    """

    def __init__(
            self,
            config: Optional[GameDataConfig] = None,
            game_fetcher: Optional[GameFetcher] = None,
            game_parser: Optional[GameDataParser] = None,
            database_service: Optional[DatabaseService] = None,
    ):
        """初始化NBA比赛数据服务"""
        # 基础配置
        self.config = config or GameDataConfig()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        # 初始化状态
        self._initialized = False

        # 数据库服务初始化
        self.db_service = database_service or DatabaseService()

        # 初始化数据库 - 不传递force_sync参数，让数据库服务自己判断是否是首次运行
        self.db_service.initialize()

        # 比赛的获取与解析实例化
        self.game_fetcher = game_fetcher or GameFetcher()
        self.game_parser = game_parser or GameDataParser()

        # 标记初始化成功
        self._initialized = True
        self.logger.info("GameData服务初始化成功")

    def get_game(self, team: Optional[str] = None, date: Optional[str] = None) -> Optional[Game]:
        """获取完整的比赛数据
        数据流：数据源 -> GameFetcher -> GameParser -> GameModel -> GameDataService接口（get_game）。
        """
        try:
            team_name = team or self.config.default_team
            if not team_name:
                raise ValueError("必须提供球队名称或设置默认球队")

            date_str = date or self.config.date_str
            game_id = self._find_game_id(team_name, date_str)

            if game_id:
                return self._fetch_game_data_sync(game_id)
            return None

        except Exception as e:
            self.logger.error(f"获取比赛数据时出错: {e}", exc_info=True)
            return None

    @lru_cache(maxsize=128)
    def _fetch_game_data_sync(self, game_id: str) -> Optional[Game]:
        """同步获取比赛数据（包括boxscore和playbyplay）"""
        try:
            # 使用get_game_data方法获取完整比赛数据
            game_data = self.game_fetcher.get_game_data(
                game_id,
                force_update=self.config.auto_refresh
            )

            if not game_data:
                self.logger.warning(f"无法获取比赛 {game_id} 的数据")
                return None

            # 解析比赛数据
            game = self.game_parser.parse_game_data(game_data)
            if not game:
                self.logger.warning(f"解析比赛 {game_id} 的数据失败")
                return None

            # 记录成功日志
            if game.play_by_play:
                self.logger.debug(f"成功获取比赛数据，包含 {len(game.play_by_play.actions)} 个事件")
            else:
                self.logger.debug("成功获取比赛数据，无回放数据")

            return game

        except Exception as e:
            self.logger.error(f"获取比赛数据时出错: {e}", exc_info=True)
            return None

    def _find_game_id(self, team_name: str, date_str: str) -> Optional[str]:
        """查找指定球队在特定日期的比赛ID"""
        try:
            # 获取球队ID
            team_id = self.db_service.get_team_id_by_name(team_name)
            if not team_id:
                self.logger.warning(f"未找到球队: {team_name}")
                return None

            # 直接使用数据库服务获取比赛ID
            game_id = self.db_service.get_game_id(team_id, date_str)

            if game_id:
                self.logger.info(f"找到 {team_name} 的比赛: {game_id}")
            else:
                self.logger.warning(f"未找到 {team_name} 的比赛")

            return game_id

        except Exception as e:
            self.logger.error(f"查找比赛ID时出错: {e}", exc_info=True)
            return None

    def clear_cache(self) -> None:
        """清理缓存数据"""
        try:
            if hasattr(self._fetch_game_data_sync, 'cache_clear'):
                self._fetch_game_data_sync.cache_clear()
                self.logger.info("成功清理 get_game 缓存")
        except Exception as e:
            self.logger.warning(f"清理缓存时出错: {e}")

    def __enter__(self) -> 'GameDataProvider':
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[Any]) -> None:
        """上下文管理器退出"""
        self.clear_cache()

    def close(self):
        """关闭资源"""
        try:
            self.clear_cache()
            if hasattr(self.db_service, 'close'):
                self.db_service.close()
                self.logger.info("数据库服务已关闭")
        except Exception as e:
            self.logger.error(f"关闭资源时出错: {e}", exc_info=True)