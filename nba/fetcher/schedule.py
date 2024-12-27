from typing import Dict, Optional
import json
import logging
from pathlib import Path
from datetime import datetime
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

    def _get_cached_data(self, cache_key: str, cache_file: Path, update_interval: int) -> Optional[Dict]:
        """
        获取缓存数据

        Args:
            cache_key (str): 缓存键名
            cache_file (Path): 缓存文件路径
            update_interval (int): 更新间隔（秒）

        Returns:
            Optional[Dict]: 缓存的数据，如果缓存无效则返回None
        """
        try:
            if cache_file.exists():
                with cache_file.open('r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    if cache_key in cache_data:
                        entry = cache_data[cache_key]
                        if datetime.now().timestamp() - entry['timestamp'] < update_interval:
                            return entry['data']
            return None
        except Exception as e:
            self.logger.error(f"Error reading cache: {e}")
            return None

    def _cache_data(self, data: Dict, cache_key: str, cache_file: Path) -> bool:
        """
        缓存数据

        Args:
            data (Dict): 要缓存的数据
            cache_key (str): 缓存键名
            cache_file (Path): 缓存文件路径

        Returns:
            bool: 缓存操作是否成功
        """
        try:
            # 读取现有缓存
            cache_data = {}
            if cache_file.exists():
                with cache_file.open('r', encoding='utf-8') as f:
                    cache_data = json.load(f) or {}

            # 更新缓存
            cache_data[cache_key] = {
                'timestamp': datetime.now().timestamp(),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data': data
            }

            # 写入缓存文件
            with cache_file.open('w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=4)
            return True

        except Exception as e:
            self.logger.error(f"Error writing cache: {e}")
            return False