from typing import Dict, Optional, Any
import logging
from config.nba_config import NBAConfig
from utils.http_handler import HTTPRequestManager
from pathlib import Path
import json
from datetime import datetime


class BaseNBAFetcher:
    """NBA数据获取基类 - 通过集成 HTTPRequestManager 来发送 HTTP 请求，并处理数据的缓存存储与读取"""

    def __init__(self):
        """初始化HTTP请求管理器。"""
        self.http_manager = HTTPRequestManager(
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/131.0.0.0 Safari/537.36",
                "Origin": "https://www.nba.com",
                "Referer": "https://www.nba.com/"
            },
            max_retries=NBAConfig.API.MAX_RETRIES,
            timeout=NBAConfig.API.TIMEOUT,
            backoff_factor=0.3,  # 可根据需要调整
            retry_status_codes=NBAConfig.API.RETRY_STATUS_CODES,
            #proxies=NBAConfig.get_proxies(),
            fallback_urls=NBAConfig.API.FALLBACK_URLS  # 设置故障转移规则
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    def _make_request(self, url: str, **kwargs) -> Optional[Dict]:
        """
        发送HTTP请求。

        Args:
            url (str): 请求URL。
            **kwargs: 请求参数。

        Returns:
            Optional[Dict]: 响应数据。
        """
        try:
            self.logger.debug(f"Making request to URL: {url} with params: {kwargs.get('params')}")
            response = self.http_manager.make_request(url, **kwargs)
            if not response:
                self.logger.warning(f"No data returned from {url}")
            return response
        except Exception as e:
            self.logger.error(f"Error making request to {url}: {e}")
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.http_manager.close()
