import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Any, Union
from urllib.parse import urlencode

from utils.http_handler import HTTPRequestManager, RetryConfig
from utils.logger_handler import AppLogger


class BaseCacheConfig:
    """基础缓存配置"""

    def __init__(
            self,
            duration: timedelta,
            root_path: Union[str, Path],
            file_pattern: str = "{prefix}_{identifier}.json",
            dynamic_duration: Optional[Dict[Any, timedelta]] = None
    ):
        self.duration = duration
        self.root_path = Path(root_path)
        self.file_pattern = file_pattern
        self.dynamic_duration = dynamic_duration or {}

        try:
            self.root_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Failed to create cache directory: {e}")

    def get_cache_path(self, prefix: str, identifier: str) -> Path:
        """获取缓存文件路径"""
        if not prefix or not identifier:
            raise ValueError("prefix and identifier cannot be empty")
        filename = self.file_pattern.format(prefix=prefix, identifier=identifier)
        return self.root_path / filename

    def get_duration(self, key: Any = None) -> timedelta:
        """获取缓存时长,支持动态缓存时间"""
        if key is not None and key in self.dynamic_duration:
            return self.dynamic_duration[key]
        return self.duration


class CacheManager:
    """缓存管理器"""

    def __init__(self, config: BaseCacheConfig):
        if not isinstance(config, BaseCacheConfig):
            raise TypeError("config must be an instance of BaseCacheConfig")
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    def get(self, prefix: str, identifier: str, cache_key: Any = None) -> Optional[Dict]:
        """获取缓存数据

        Args:
            prefix: 缓存前缀
            identifier: 缓存标识符
            cache_key: 用于动态确定缓存时长的key
        """
        if not prefix or not identifier:
            raise ValueError("prefix and identifier cannot be empty")

        cache_path = self.config.get_cache_path(prefix, identifier)
        if not cache_path.exists():
            return None

        try:
            with cache_path.open('r', encoding='utf-8') as f:
                cache_data = json.load(f)

            timestamp = datetime.fromtimestamp(cache_data.get('timestamp', 0))
            duration = self.config.get_duration(cache_key)

            if datetime.now() - timestamp < duration:
                return cache_data.get('data')

        except json.JSONDecodeError as e:
            self.logger.error(f"缓存文件JSON解析失败: {e}")
        except Exception as e:
            self.logger.error(f"读取缓存失败: {e}")

        return None

    def set(self, prefix: str, identifier: str, data: Dict, metadata: Optional[Dict] = None) -> None:
        """设置缓存数据

        Args:
            prefix: 缓存前缀
            identifier: 缓存标识符
            data: 要缓存的数据
            metadata: 额外的元数据
        """
        if not prefix or not identifier:
            raise ValueError("prefix and identifier cannot be empty")
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        cache_path = self.config.get_cache_path(prefix, identifier)
        cache_data = {
            'timestamp': datetime.now().timestamp(),
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data': data
        }

        if metadata:
            cache_data['metadata'] = metadata

        temp_path = cache_path.with_suffix('.tmp')
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False) # type: ignore
            temp_path.replace(cache_path)
        except Exception as e:
            self.logger.error(f"写入缓存失败: {e}")
            raise
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception as e:
                    self.logger.error(f"删除临时文件失败: {e}")

    def clear(self, prefix: str, identifier: Optional[str] = None,
              age: Optional[timedelta] = None) -> None:
        """清理缓存

        Args:
            prefix: 缓存前缀
            identifier: 缓存标识符，如果指定则只清理该标识符的缓存
            age: 清理早于指定时间的缓存
        """
        if not prefix:
            raise ValueError("prefix cannot be empty")

        now = datetime.now()
        if identifier:
            cache_file = self.config.get_cache_path(prefix, identifier)
            if cache_file.exists():
                try:
                    cache_file.unlink()
                except Exception as e:
                    self.logger.error(f"删除缓存文件失败 {cache_file}: {e}")
            return

        for cache_file in self.config.root_path.glob(f"{prefix}_*.json"):
            try:
                if not cache_file.exists():
                    continue

                with cache_file.open('r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                timestamp = datetime.fromtimestamp(cache_data.get('timestamp', 0))

                if age is None or (now - timestamp) > age:
                    cache_file.unlink()

            except Exception as e:
                self.logger.error(f"清理缓存文件失败 {cache_file}: {e}")


class BaseRequestConfig:
    """基础请求配置"""

    def __init__(
        self,
        cache_config: BaseCacheConfig,
        base_url: Optional[str] = None,  # 改为可选参数
        retry_config: Optional[RetryConfig] = None,
        request_timeout: int = 30
    ):
        # base_url 现在是可选的
        self.base_url = base_url
        self.cache_config = cache_config
        self.retry_config = retry_config or RetryConfig()
        self.request_timeout = request_timeout


class BaseNBAFetcher:
    """NBA数据获取基类"""

    @staticmethod
    def _get_default_headers() -> Dict[str, str]:
        """获取默认请求头"""
        return {
        'accept': 'application/json',
        'accept-language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'accept-encoding': 'gzip, deflate, br, zstd',
        'connection': 'keep-alive',
        'dnt': '1',
        'referer': 'https://www.nba.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    }

    def __init__(self, config: BaseRequestConfig):
        """初始化"""
        if not isinstance(config, BaseRequestConfig):
            raise TypeError("config must be an instance of BaseRequestConfig")

        self.config = config
        self.cache_manager = CacheManager(config.cache_config)
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        self.http_manager = HTTPRequestManager(
            headers=self._get_default_headers(),
            timeout=config.request_timeout
        )
        if config.retry_config:
            self.http_manager.retry_strategy.config = config.retry_config

    def fetch_data(self, url: Optional[str] = None, endpoint: Optional[str] = None,
                   params: Optional[Dict] = None,
                   data: Optional[Dict] = None, cache_key: Optional[str] = None,
                   cache_status_key: Any = None,
                   force_update: bool = False,
                   metadata: Optional[Dict] = None) -> Optional[Dict]:
        """获取数据

        Args:
            url: 完整的请求URL
            endpoint: API端点
            params: URL参数
            data: POST数据
            cache_key: 缓存键
            cache_status_key: 用于确定缓存时长的状态键
            force_update: 是否强制更新
            metadata: 额外的缓存元数据
        """
        if url is None and endpoint is None:
            raise ValueError("Must provide either url or endpoint")

        if endpoint is not None:
            url = self.build_url(endpoint, params)
            params = None

        # 如果有缓存key且不强制更新，尝试获取缓存数据
        if cache_key and not force_update:
            cached_data = self.cache_manager.get(
                prefix=self.__class__.__name__.lower(),
                identifier=cache_key,
                cache_key=cache_status_key
            )
            if cached_data is not None:
                # 直接返回data字段内容
                return cached_data.get('data') if isinstance(cached_data,dict) and 'data' in cached_data else cached_data

        # 获取新数据
        try:
            self.logger.info(f"Request URL: {url}")
            data = self.http_manager.make_request(
                url=url,
                params=params,
                data=data
            )


            # 如果获取成功且需要缓存，则更新缓存
            if data is not None and cache_key:
                try:
                    self.cache_manager.set(
                        prefix=self.__class__.__name__.lower(),
                        identifier=cache_key,
                        data=data,
                        metadata=metadata
                    )
                except Exception as e:
                    self.logger.error(f"更新缓存失败: {e}")

            return data

        except Exception as e:
            self.logger.error(f"请求失败: {str(e)}")
            return None

    def build_url(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> str:
        """构建请求URL"""
        if not endpoint:
            raise ValueError("endpoint cannot be empty")

        # 如果没有 base_url，直接使用 endpoint
        if not self.config.base_url:
            if params:
                query_string = urlencode({k: v for k, v in params.items() if v is not None})
                return f"{endpoint}?{query_string}"
            return endpoint

        # 原有的 base_url 处理逻辑
        base = self.config.base_url.rstrip('/')
        clean_endpoint = endpoint.lstrip('/')
        if params:
            query_string = urlencode({k: v for k, v in params.items() if v is not None})
            return f"{base}/{clean_endpoint}?{query_string}"
        return f"{base}/{clean_endpoint}"