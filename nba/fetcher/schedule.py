from typing import Dict, Optional
import logging
from .base import BaseNBAFetcher
from config.nba_config import NBAConfig


class ScheduleFetcher(BaseNBAFetcher):
    """NBA赛程数据获取器 - 提供了获取赛程数据的方法，并支持缓存管理。
    它通过缓存机制减少对 API 请求的依赖，提高性能。如果缓存过期或强制更新时，
    它会从 NBA API 获取新的赛程数据并更新缓存。"""

    UPDATE_INTERVAL = NBAConfig.API.SCHEDULE_UPDATE_INTERVAL  # 使用配置中的更新间隔

    def __init__(self):
        """初始化赛程获取器"""
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)

        # 初始化缓存配置
        self.cache_file = NBAConfig.PATHS.LEAGUE_CACHE / 'schedule.json'

    def get_schedule(self, force_update: bool = False) -> Optional[Dict]:
        """
        获取NBA赛程数据，优先使用缓存

        Args:
            force_update (bool): 是否强制更新数据

        Returns:
            Optional[Dict]: 赛程数据
        """
        cache_key = "schedule"

        # 检查缓存
        if not force_update:
            cached_data = self._get_cached_data(cache_key, self.cache_file, self.UPDATE_INTERVAL)
            if cached_data:
                self.logger.info("Using cached schedule data")
                return cached_data

        # 获取新数据
        try:
            self.logger.info("Fetching new schedule data from API")
            schedule_data = self._fetch_schedule_data()
            if schedule_data:
                if self._cache_data(schedule_data, cache_key, self.cache_file):
                    self.logger.info("Successfully cached new schedule data")
                else:
                    self.logger.warning("Failed to cache new schedule data")
            return schedule_data

        except Exception as e:
            self.logger.error(f"Error getting schedule: {e}")
            return None

    def _fetch_schedule_data(self) -> Optional[Dict]:
        """从 NBA API 获取最新赛程"""
        return self._make_request(NBAConfig.URLS.SCHEDULE)

