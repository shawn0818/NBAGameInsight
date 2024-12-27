from typing import Dict, Optional
import json
import logging
from datetime import datetime
from pathlib import Path
from utils.http_handler import HTTPRequestManager
from config.nba_config import NBAConfig

class BaseNBAFetcher:
    """NBA数据获取基类"""
    
    def __init__(self):
        """初始化HTTP请求管理器"""
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
            backoff_factor=0.3,
            retry_status_codes=NBAConfig.API.RETRY_STATUS_CODES,
            fallback_urls=NBAConfig.API.FALLBACK_URLS
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    def _make_request(self, url: str, **kwargs) -> Optional[Dict]:
        """发送HTTP请求"""
        try:
            self.logger.debug(f"Making request to URL: {url}")
            response = self.http_manager.make_request(url, **kwargs)
            if not response:
                self.logger.warning(f"No data returned from {url}")
            return response
        except Exception as e:
            self.logger.error(f"Error making request to {url}: {e}")
            return None

    def _get_or_update_cache(self, cache_key: str, cache_file: Path, 
                           update_interval: int, fetch_func) -> Optional[Dict]:
        """获取缓存数据或更新缓存"""
        try:
            # 检查缓存
            if cache_file.exists():
                with cache_file.open('r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    if cache_key in cache_data:
                        entry = cache_data[cache_key]
                        if datetime.now().timestamp() - entry['timestamp'] < update_interval:
                            return entry['data']

            # 获取新数据
            new_data = fetch_func()
            if new_data:
                # 更新缓存
                cache_data = {}
                if cache_file.exists():
                    with cache_file.open('r', encoding='utf-8') as f:
                        cache_data = json.load(f) or {}

                cache_data[cache_key] = {
                    'timestamp': datetime.now().timestamp(),
                    'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'data': new_data
                }

                with cache_file.open('w', encoding='utf-8') as f:
                    json.dump(cache_data, f, indent=4)

            return new_data

        except Exception as e:
            self.logger.error(f"Cache error for {cache_key}: {e}")
            return None
