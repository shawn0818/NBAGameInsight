# game_data_provider.py
from typing import Optional
from functools import lru_cache

from nba.fetcher.game_fetcher import GameFetcher
from nba.parser.game_parser import GameDataParser
from nba.models.game_model import Game

from utils.logger_handler import AppLogger


class GameDataProvider:
    """
    GameDataProvider的核心职责是：数据获取和解析。
    负责从外部数据源获取原始数据，并将其解析成系统内部的Game对象。
    """

    def __init__(
            self,
            game_fetcher: Optional[GameFetcher] = None,
            game_parser: Optional[GameDataParser] = None,
    ):
        """初始化NBA比赛数据服务"""
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        # 初始化状态
        self._initialized = False

        # 比赛的获取与解析实例化
        self.game_fetcher = game_fetcher or GameFetcher()
        self.game_parser = game_parser or GameDataParser()

        # 标记初始化成功
        self._initialized = True
        self.logger.info("GameData服务初始化成功")

    def get_game(self, game_id: str, force_update: bool = False) -> Optional[Game]:
        """
        获取完整的比赛数据，根据game_id

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新缓存

        Returns:
            Optional[Game]: 解析后的比赛数据对象
        """
        try:
            if not game_id:
                raise ValueError("必须提供有效的比赛ID")

            return self._fetch_game_data_sync(game_id, force_update)

        except Exception as e:
            self.logger.error(f"获取比赛数据时出错: {e}", exc_info=True)
            return None

    @lru_cache(maxsize=128)
    def _fetch_game_data_sync(self, game_id: str, force_update: bool = False) -> Optional[Game]:
        """同步获取比赛数据（包括boxscore和playbyplay）"""
        try:
            # 使用get_game_data方法获取完整比赛数据
            game_data = self.game_fetcher.get_game_data(
                game_id,
                force_update=force_update
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

    def clear_cache(self) -> None:
        """清理缓存数据"""
        try:
            if hasattr(self._fetch_game_data_sync, 'cache_clear'):
                self._fetch_game_data_sync.cache_clear()
                self.logger.info("成功清理 get_game 缓存")
        except Exception as e:
            self.logger.warning(f"清理缓存时出错: {e}")

    def close(self):
        """关闭资源"""
        try:
            self.clear_cache()
        except Exception as e:
            self.logger.error(f"关闭资源时出错: {e}")