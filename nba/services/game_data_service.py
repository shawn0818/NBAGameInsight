from typing import  Optional, Any
from functools import lru_cache
from pathlib import Path
from dataclasses import dataclass

import pandas as pd

from nba.fetcher.game_fetcher import GameFetcher
from nba.parser.game_parser import GameDataParser
from nba.fetcher.schedule_fetcher import ScheduleFetcher
from nba.parser.schedule_parser import ScheduleParser
from nba.parser.league_parser import LeagueDataProvider

from nba.models.game_model import Game
from config.nba_config import NBAConfig
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
    auto_refresh: bool = True
    use_pydantic_v2: bool = True


class GameDataProvider:
    """NBA比赛数据获取入口:
    GameDataService 的核心职责是：数据获取和解析。客户端或 NBAService 需要获取 NBA 比赛数据时，首先会找到 GameDataService。
    GameDataService 负责协调 GameFetcher 和 GameParser，从外部数据源获取和解析数据。
    在数据获取层面，GameDataService 确实是入口。它的任务是从外部数据源（例如 NBA API）获取原始数据，
    并将其解析成我们系统内部可以理解和操作的 GameModel 对象。
     一旦 GameDataService 完成了这个任务，它就应该把 解析后的 Game 对象 交给系统的其他部分使用，
     而不是继续作为数据源直接服务于所有模块。GameDataService 更专注于 数据生产。
      它就像一个数据工厂，负责从原料 (外部数据源) 中生产出成品 ( GameModel 对象)。
       一旦成品生产出来，就交给系统的其他部分 (例如 NBAService, GameDisplayService) 去使用和加工。
        GameDataService 本身不再直接负责数据的分发和使用，而是专注于 高效、稳定地生产高质量的数据成品。
    """

    def __init__(
            self,
            config: Optional[GameDataConfig] = None,
            game_fetcher: Optional[GameFetcher] = None,
            game_parser: Optional[GameDataParser] = None,
            schedule_fetcher: Optional[ScheduleFetcher] = None,
            schedule_parser: Optional[ScheduleParser] = None,
            league_provider: Optional[LeagueDataProvider] = None, # 只注入 LeagueDataProvider
    ):
        """初始化NBA比赛数据服务"""
        # 基础配置
        self.config = config or GameDataConfig()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        # 初始化状态
        self._initialized = False
        self._schedule_df: Optional[pd.DataFrame] = None

        # 组件注入或初始化
        self.schedule_fetcher = schedule_fetcher or ScheduleFetcher()
        self.schedule_parser = schedule_parser or ScheduleParser()
        self.league_provider = league_provider or LeagueDataProvider() # 用来映射球队以及球员的名称与ID

        self.game_fetcher = game_fetcher or GameFetcher()
        # 验证 game_fetcher 是否正确初始化
        if not hasattr(self.game_fetcher, 'get_game_data'):
            raise InitializationError("GameFetcher 实例未正确初始化")
        self.game_parser = game_parser or GameDataParser()

        # 启动初始化
        self._init_service()


    ## ===============以下是赛程数据，球队映射数据，球员映射数据的数据加载============

    def _init_service(self) -> None:
        """服务初始化"""
        try:

            # 1. 初始化联盟数据(球队和球员映射)
            self._init_league_data()

            # 2. 初始化赛程数据
            self._init_schedule_data()

            # 初始化成功
            self._initialized = True
            self.logger.info("GameData服务初始化成功")
            return

        except InitializationError as e:
            self.logger.error(f"GameData服务初始化失败: {e}")
            raise
        except Exception as e:
            self.logger.error(f"GameData服务初始化过程中发生未预期的错误: {e}")
            raise InitializationError(f"GameData服务初始化过程中发生未预期的错误: {e}")

    def _init_league_data(self) -> None:  # 修改为不返回 bool，失败直接抛出异常
        """初始化联盟数据(球队和球员映射)"""
        try:
            # 验证球队映射服务 (Check Team Mapping Service)
            test_team_id = self.league_provider.get_team_id_by_name(self.config.default_team)
            if not test_team_id:
                self.logger.error("球队映射服务验证失败")
                raise InitializationError("球队映射服务验证失败")

            # 验证球员映射服务 (Check Player Mapping Service)
            test_player_id = self.league_provider.get_player_id_by_name(self.config.default_player)
            if not test_player_id:
                self.logger.error("球员映射服务验证失败")
                raise InitializationError("球员映射服务验证失败")

            self.logger.info("联盟球队/球员名字-ID映射初始化成功")

        except Exception as e:
            self.logger.error(f"联盟球队/球员名字-ID映射初始化时出错: {e}")
            raise InitializationError(f"联盟球队/球员名字-ID映射初始化失败: {e}")  # 抛出 InitializationError

    def _init_schedule_data(self) -> None: # 修改为不返回 bool，失败直接抛出异常
        """初始化赛程数据"""
        try:
            # 获取赛程数据
            schedule_data = self.schedule_fetcher.get_schedule(
                force_update=self.config.auto_refresh
            )
            if not schedule_data:
                raise InitializationError("无法获取赛程数据")

            # 解析赛程数据
            self._schedule_df = self.schedule_parser.parse_raw_schedule(schedule_data)
            if self._schedule_df.empty:
                raise InitializationError("赛程数据解析失败或为空")

            self.logger.info(f"成功加载赛程数据，包含本赛季 {len(self._schedule_df)} 场比赛")

        except InitializationError as e:
            self.logger.error(f"初始化赛程数据时出错: {e}")
            raise e # 抛出 InitializationError
        except Exception as e:
            self.logger.error(f"初始化赛程数据时出错: {e}")
            raise InitializationError(f"初始化赛程数据失败: {e}") # 捕捉其他异常并抛出 InitializationError

    def _ensure_initialized(self) -> None:
        """确保服务已初始化"""
        if not self._initialized:
            raise ServiceNotReadyError("服务尚未完成初始化")


    ## ===========================
    ## 3.获取到某一个GAME的完整数据，
    ## ===========================

    def get_game(self, team: Optional[str] = None, date: Optional[str] = None) -> Optional[Game]:
        """获取完整的比赛数据
        数据流：数据源 -> GameFetcher -> GameParser -> GameModel -> GameDataService接口（get_game）。
         """
        self._ensure_initialized() # 确保服务已初始化
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
            # 使用新的 get_game_data 方法获取完整比赛数据
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
            # 使用 LeagueDataProvider 获取球队ID
            team_id = self.league_provider.get_team_id_by_name(team_name)
            if not team_id:
                self.logger.warning(f"未找到球队: {team_name}")
                return None

            # 直接使用已经初始化好的赛程数据
            if self._schedule_df is None:
                self.logger.error("赛程数据未初始化")
                return None

            # 使用 schedule_parser 直接从现有的 DataFrame 获取比赛ID
            game_id = self.schedule_parser.get_game_id(self._schedule_df, team_id, date_str)

            if game_id:
                self.logger.info(f"找到 {team_name} 的在{date_str}比赛: {game_id}")
            else:
                self.logger.warning(f"未找到 {team_name} 的比赛")

            return game_id

        except Exception as e:
            self.logger.error(f"查找比赛ID时出错: {e}", exc_info=True)
            return None

    ## ===========================
    ## 4.辅助方法
    ## ===========================

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