from typing import Dict, Optional, Callable, Any, List
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from dataclasses import dataclass, field
from typing import List, Dict
from utils.http_handler import HTTPRequestManager


@dataclass
class BaseRequestConfig:

    #基础URL配置
    BASE_URL: str = ""  # 默认为空,子类可覆盖

    # 缓存时间
    CACHE_DURATION: timedelta = timedelta(days=7)  # 默认缓存7天

    # 故障转移URL规则
    FALLBACK_URLS: Dict[str, str] = field(
        default_factory=lambda: {
            "https://cdn.nba.com/static/json": "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA",
        }
    )


class BaseNBAFetcher:
    """NBA数据获取基类"""
    request_config = BaseRequestConfig()

    def __init__(self):
        """初始化HTTP请求管理器和日志"""
        self.http_manager = HTTPRequestManager(
            headers={
                'accept': '*/*',
                'accept-language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                'cache-control': 'no-cache',
                'dnt': '1',
                'origin': 'https://www.nba.com',
                'pragma': 'no-cache',
                'referer': 'https://www.nba.com/',
                'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'
            },
            fallback_urls=self.request_config.FALLBACK_URLS
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    def build_url(self, endpoint: str, params: Dict[str, Any]) -> str:
        """构建URL"""
        filtered_params = {k: v for k, v in params.items() if v is not None}
        query_string = urlencode(filtered_params)
        return f"{self.request_config.BASE_URL}/{endpoint}?{query_string}"

    def fetch_data(self,
                   url: Optional[str] = None,
                   endpoint: Optional[str] = None,
                   params: Optional[Dict] = None,
                   method: str = 'GET',
                   cache_config: Optional[Dict] = None) -> Optional[Dict]:
        """
        获取数据，支持缓存机制

        Args:
            url: 完整的请求URL
            endpoint: API端点
            params: 请求参数
            method: 请求方法
            cache_config: 缓存配置，包含以下字段:
                - key: 缓存键名
                - file: 缓存文件路径
                - interval: 缓存有效期(秒)
                - force_update: 是否强制更新
        """
        if url is None and endpoint is None:
            raise ValueError("Must provide either url or endpoint")

        if endpoint is not None:
            params = params or {}
            url = self.build_url(endpoint, params)
            params = None

        # 如果有缓存配置，使用缓存机制
        if cache_config and isinstance(cache_config, dict):
            required_fields = {'key', 'file', 'interval'}
            if not all(field in cache_config for field in required_fields):
                self.logger.warning(f"Invalid cache config, missing required fields: {required_fields}")
                return self.http_manager.make_request(url, method=method, params=params)

            return self._fetch_with_cache(
                fetch_func=lambda: self.http_manager.make_request(url, method=method, params=params),
                key=cache_config['key'],
                file=cache_config['file'],
                interval=cache_config['interval'],
                force_update=cache_config.get('force_update', False)
            )

        # 无缓存配置，直接请求
        return self.http_manager.make_request(url, method=method, params=params)

    def _fetch_with_cache(self,
                          fetch_func: Callable[[], Optional[Dict]],
                          key: str,
                          file: Path,
                          interval: int,
                          force_update: bool = False,
                          data: Optional[Dict] = None) -> Optional[Dict]:
        """使用缓存机制获取数据"""
        try:
            # 如果interval为0，表示不使用缓存
            if interval == 0:
                return data if data is not None else fetch_func()

            if force_update:
                return self._update_cache(fetch_func, key, file, data)

            if not file.exists():
                return self._update_cache(fetch_func, key, file, data)

            try:
                with file.open('r', encoding='utf-8') as f:
                    cache_data = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                self.logger.warning(f"Invalid cache file {file}, creating new one")
                return self._update_cache(fetch_func, key, file, data)

            if key in cache_data:
                entry = cache_data[key]
                cache_time = datetime.fromtimestamp(entry['timestamp'])
                if datetime.now() - cache_time < timedelta(seconds=interval):
                    self.logger.debug(f"Using cached data for {key}")
                    return entry['data']

            return self._update_cache(fetch_func, key, file, data)

        except Exception as e:
            self.logger.error(f"Cache error for {key}: {e}")
            return data if data is not None else fetch_func()

    def _update_cache(self,
                      fetch_func: Callable[[], Optional[Dict]],
                      key: str,
                      file: Path,
                      data: Optional[Dict] = None) -> Optional[Dict]:
        """更新缓存数据"""
        try:
            new_data = data if data is not None else fetch_func()
            if not new_data:
                return None

            file.parent.mkdir(parents=True, exist_ok=True)

            cache_data = {}
            if file.exists():
                try:
                    with file.open('r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                except json.JSONDecodeError:
                    self.logger.warning(f"Invalid cache file {file}, creating new one")

            # 清理过期的缓存条目（超过400天的数据）
            now = datetime.now()
            cache_data = {
                k: v for k, v in cache_data.items()
                if now - datetime.fromtimestamp(v['timestamp']) < timedelta(days=400)
            }

            cache_data[key] = {
                'timestamp': now.timestamp(),
                'last_updated': now.strftime('%Y-%m-%d %H:%M:%S'),
                'data': new_data
            }

            # 使用临时文件进行原子写入
            temp_file = file.with_suffix('.tmp')
            try:
                with temp_file.open('w', encoding='utf-8') as f:
                    json.dump(cache_data, f, indent=2, ensure_ascii=False)
                if file.exists():
                    file.unlink()
                temp_file.replace(file)
            finally:
                if temp_file.exists():
                    temp_file.unlink()

            return new_data

        except Exception as e:
            self.logger.error(f"Error updating cache for {key}: {e}")
            return data if data is not None else None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.http_manager.close()