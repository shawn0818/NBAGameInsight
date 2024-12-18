from typing import Dict, Optional
import logging
from pathlib import Path
import json
from datetime import datetime
from .base import BaseNBAFetcher
from config.nba_config import NBAConfig



class PlayerFetcher(BaseNBAFetcher):
    """NBA球员数据获取器"""

    def __init__(self):
        """初始化数据获取器"""
        super().__init__()
        self.player_profile_url = NBAConfig.URLS.PLAYER_PROFILE
        self.logger = logging.getLogger(__name__)

        # 初始化缓存配置
        self.cache_file = NBAConfig.PATHS.LEAGUE_CACHE / 'players.json'
        self.players_update_interval = NBAConfig.API.PLAYERS_UPDATE_INTERVAL  # 秒

    def get_player_profile(self, force_update: bool = False) -> Optional[Dict]:
        """
        获取所有球员的基础信息

        Args:
            force_update (bool): 是否强制更新缓存

        Returns:
            Optional[Dict]: 包含所有球员信息的原始JSON数据
        """
        cache_key = "players_all"

        # 检查缓存
        if not force_update:
            cached_data = self._get_cached_data(cache_key, self.cache_file, self.players_update_interval)
            if cached_data:
                self.logger.info("Using cached player profile data")
                return cached_data

        # 获取新数据
        try:
            self.logger.debug(f"Fetching player profile data from URL: {self.player_profile_url}")
            data = self._make_request(self.player_profile_url)

            if data:
                # 缓存新数据
                if self._cache_data(data, cache_key, self.cache_file):
                    self.logger.info("Successfully cached new player profile data")
                else:
                    self.logger.warning("Failed to cache new player profile data")
            return data

        except Exception as e:
            self.logger.error(f"Error fetching player profile data: {e}")
            return None

    def _get_cached_data(self, cache_key: str, cache_file: Path, update_interval: int) -> Optional[Dict]:
        """获取缓存的数据"""
        try:
            if not cache_file.exists():
                self.logger.debug(f"Cache file {cache_file} does not exist.")
                return None

            with cache_file.open('r', encoding='utf-8') as f:
                cached_data = json.load(f)

            if not cached_data or cache_key not in cached_data:
                self.logger.debug(f"No cached data found for key: {cache_key}")
                return None

            data_entry = cached_data[cache_key]
            time_diff = datetime.now().timestamp() - data_entry.get('timestamp', 0)

            if time_diff < update_interval:
                self.logger.debug(f"Cached data for key {cache_key} is still valid.")
                return data_entry.get('data')
            self.logger.debug(f"Cached data for key {cache_key} has expired.")
            return None

        except Exception as e:
            self.logger.error(f"Error reading cache from {cache_file}: {e}")
            return None

    def _cache_data(self, data: Dict, cache_key: str, cache_file: Path) -> bool:
        """缓存数据"""
        try:
            current_cache = {}
            if cache_file.exists():
                with cache_file.open('r', encoding='utf-8') as f:
                    current_cache = json.load(f) or {}

            current_cache[cache_key] = {
                'timestamp': datetime.now().timestamp(),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data': data
            }

            with cache_file.open('w', encoding='utf-8') as f:
                json.dump(current_cache, f, indent=4)
            self.logger.debug(f"Data cached successfully for key: {cache_key}")
            return True

        except Exception as e:
            self.logger.error(f"Error caching data to {cache_file}: {e}")
            return False


