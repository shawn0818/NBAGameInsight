from typing import Dict, Optional, Callable
import json
import logging
from datetime import datetime
from pathlib import Path
from utils.http_handler import HTTPRequestManager
from config.nba_config import NBAConfig

class BaseNBAFetcher:
    """NBA数据获取基类，提供HTTP请求和缓存管理功能
    
    该类作为所有NBA数据获取器的基类，提供了：
    1. 统一的HTTP请求处理
    2. 灵活的缓存机制
    3. 错误处理和日志记录
    4. 可配置的重试策略
    
    所有子类通过继承此类获得基础的数据获取和缓存能力。
    """
    
    def __init__(self):
        """初始化HTTP请求管理器和日志"""
        self.http_manager = HTTPRequestManager(
            headers={
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                'Connection': 'keep-alive',
                'DNT': '1',
                'Host': 'stats.nba.com',
                'Origin': 'https://www.nba.com',
                'Referer': 'https://www.nba.com/',
                'Sec-Ch-Ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'
            },
            max_retries=NBAConfig.API.MAX_RETRIES,
            timeout=NBAConfig.API.TIMEOUT,
            backoff_factor=0.3,
            retry_status_codes=NBAConfig.API.RETRY_STATUS_CODES,
            fallback_urls=NBAConfig.API.FALLBACK_URLS
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    def fetch_data(self, 
                  url: str, 
                  params: Optional[Dict] = None, 
                  method: str = 'GET',
                  cache_config: Optional[Dict] = None) -> Optional[Dict]:
        """获取数据，支持缓存机制
        
        该方法是所有数据获取操作的统一入口，支持：
        1. 带缓存的数据获取
        2. 直接的HTTP请求
        3. 可配置的缓存策略
        
        Args:
            url: 请求URL
            params: 请求参数
            method: 请求方法（GET、POST等）
            cache_config: 缓存配置，包含：
                - key: str, 缓存键名
                - file: Path, 缓存文件路径
                - interval: int, 更新间隔（秒）
                - force_update: bool, 是否强制更新
        
        Returns:
            Optional[Dict]: 获取的数据，失败时返回None
        """
        # 如果配置了缓存，使用缓存机制
        if cache_config:
            return self._fetch_with_cache(
                fetch_func=lambda: self.http_manager.make_request(url, method=method, params=params),
                **cache_config
            )
        
        # 否则直接请求
        return self.http_manager.make_request(url, method=method, params=params)

    def _fetch_with_cache(self,
                         fetch_func: Callable[[], Optional[Dict]],
                         key: str,
                         file: Path,
                         interval: int,
                         force_update: bool = False) -> Optional[Dict]:
        """
        使用缓存机制获取数据
        
        Args:
            fetch_func: 获取新数据的函数
            key: 缓存键名
            file: 缓存文件路径
            interval: 更新间隔（秒）
            force_update: 是否强制更新
        """
        try:
            # 强制更新或缓存文件不存在时，直接获取新数据
            if force_update or not file.exists():
                return self._update_cache(fetch_func, key, file)

            # 读取缓存
            with file.open('r', encoding='utf-8') as f:
                cache_data = json.load(f)
                if key in cache_data:
                    entry = cache_data[key]
                    # 检查缓存是否过期
                    if datetime.now().timestamp() - entry['timestamp'] < interval:
                        self.logger.debug(f"Using cached data for {key}")
                        return entry['data']

            # 缓存过期，更新数据
            return self._update_cache(fetch_func, key, file)

        except Exception as e:
            self.logger.error(f"Cache error for {key}: {e}")
            # 缓存出错时尝试直接获取数据
            return fetch_func()

    def _update_cache(self, 
                     fetch_func: Callable[[], Optional[Dict]], 
                     key: str, 
                     file: Path) -> Optional[Dict]:
        """更新缓存数据"""
        try:
            new_data = fetch_func()
            if not new_data:
                return None

            # 确保缓存目录存在
            file.parent.mkdir(parents=True, exist_ok=True)

            # 读取现有缓存
            cache_data = {}
            if file.exists():
                with file.open('r', encoding='utf-8') as f:
                    cache_data = json.load(f) or {}

            # 更新缓存
            cache_data[key] = {
                'timestamp': datetime.now().timestamp(),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data': new_data
            }

            # 写入缓存
            with file.open('w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=4)

            return new_data

        except Exception as e:
            self.logger.error(f"Error updating cache for {key}: {e}")
            return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.http_manager.close()
