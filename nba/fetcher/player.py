from typing import Dict, Optional
from .base import BaseNBAFetcher
from config.nba_config import NBAConfig
import logging

class PlayerFetcher(BaseNBAFetcher):
    """NBA球员数据获取器"""

    def __init__(self):
        super().__init__()
        self.player_profile_url = NBAConfig.URLS.PLAYER_PROFILE
        self.cache_file = NBAConfig.PATHS.LEAGUE_CACHE / 'players.json'
        self.update_interval = NBAConfig.API.PLAYERS_UPDATE_INTERVAL

        # 确保缓存目录存在
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        # 配置日志
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger(__name__)

    def get_player_profile(self, force_update: bool = False) -> Optional[Dict]:
        """获取所有球员的基础信息"""
        self.logger.debug(f"get_player_profile called with force_update={force_update}")
        try:
            if force_update:
                self.logger.debug("Force update is True, making direct request.")
                return self._make_request(self.player_profile_url)

            self.logger.debug("Force update is False, attempting to get from cache.")
            return self._get_or_update_cache(
                "players_all",
                self.cache_file,
                self.update_interval,
                lambda: self._make_request(self.player_profile_url)
            )
        except Exception as e:
            self.logger.error(f"Error in get_player_profile: {e}")
            return None
