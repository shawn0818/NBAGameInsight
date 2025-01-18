import requests
from typing import Optional, Dict, Any, List
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config.nba_config import NBAConfig
import time


class HTTPConfig:
    """通用 HTTP 请求配置
    
    定义了HTTP请求的全局配置参数，包括：
    1. 默认请求头
    2. 超时设置
    3. 重试策略
    4. 代理配置
    
    所有配置参数都可以通过类属性访问和修改。
    """
    TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 5
    BACKOFF_FACTOR: float = 0.3
    
    PROXY: Optional[str] = None
    
    RETRY_STATUS_CODES: List[int] = [429, 500, 502, 503, 504]

    @classmethod
    def get_proxies(cls) -> Optional[Dict[str, str]]:
        """获取代理配置
        
        Returns:
            Optional[Dict[str, str]]: 代理配置字典，格式为：
            {
                "http": "proxy_url",
                "https": "proxy_url"
            }
            如果未配置代理则返回None
        """
        if cls.PROXY:
            return {
                "http": cls.PROXY,
                "https": cls.PROXY
            }
        return None

class HTTPRequestManager:
    """HTTP请求管理器，支持请求重试和备用URL
    
    提供了强大的HTTP请求功能，特点：
    1. 自动重试机制
    2. 备用URL故障转移
    3. 可配置的请求策略
    4. 详细的日志记录
    
    支持上下文管理器（with语句），自动管理会话资源。
    """
    
    def __init__(self, 
                 headers: Optional[Dict[str, str]] = None,
                 max_retries: Optional[int] = None,
                 timeout: Optional[int] = None,
                 backoff_factor: Optional[float] = None,
                 retry_status_codes: Optional[list] = None,
                 fallback_urls: Optional[Dict[str, str]] = None):
        """初始化请求管理器
        
        Args:
            headers: 自定义请求头
            max_retries: 最大重试次数
            timeout: 请求超时时间（秒）
            backoff_factor: 重试间隔因子，用于计算重试等待时间
            retry_status_codes: 需要重试的HTTP状态码列表
            fallback_urls: 故障转移URL映射，格式：{"primary_url": "fallback_url"}
        """
        self.headers = headers or {}  # 改为空字典作为默认值
        self.timeout = timeout or NBAConfig.API.TIMEOUT
        self.max_retries = max_retries or NBAConfig.API.MAX_RETRIES
        self.backoff_factor = backoff_factor or 0.3
        self.retry_status_codes = retry_status_codes or NBAConfig.API.RETRY_STATUS_CODES
        self.fallback_urls = fallback_urls or NBAConfig.API.FALLBACK_URLS
        
        self.logger = logging.getLogger(__name__)
        self.session = self._create_session()
        
    def _create_session(self) -> requests.Session:
        """创建带有重试机制的会话"""
        session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=self.retry_status_codes,
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE"]
        )
        
        # 配置适配器
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # 更新请求头
        if self.headers:
            session.headers.update(self.headers)
        
        return session
        
    def _get_fallback_url(self, url: str) -> Optional[str]:
        """获取故障转移URL"""
        for primary, fallback in self.fallback_urls.items():
            if url.startswith(primary):
                self.logger.debug(f"Found fallback URL for {url}: {fallback}")
                return url.replace(primary, fallback, 1)
        return None

    def make_request(self, 
                    url: str,
                    method: str = 'GET',
                    params: Optional[Dict[str, Any]] = None,
                    data: Optional[Dict[str, Any]] = None,
                    allow_fallback: bool = True,
                    retry_count: int = 0) -> Dict[str, Any]:
        """发送HTTP请求，支持重试和故障转移
        
        特点：
        1. 自动重试失败的请求
        2. 支持故障转移到备用URL
        3. 指数退避重试策略
        4. 详细的错误处理
        
        Args:
            url: 请求URL
            method: 请求方法（GET、POST等）
            params: URL查询参数
            data: 请求体数据
            allow_fallback: 是否允许使用备用URL
            retry_count: 当前重试次数
            
        Returns:
            Dict[str, Any]: 响应数据，请求失败时返回空字典
            
        Example:
            >>> manager = HTTPRequestManager()
            >>> data = manager.make_request("https://api.example.com/data")
            >>> print(data)
            {"status": "success", "data": [...]}
        """
        try:
            self.logger.info(f"Making {method} request to: {url} (attempt {retry_count + 1})")
            
            response = self.session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=data,
                timeout=self.timeout
            )
            
            # 处理成功响应
            if response.ok:
                return response.json()
            
            # 处理需要重试的状态码
            if response.status_code in self.retry_status_codes:
                if retry_count < self.max_retries:
                    wait_time = self._get_retry_wait_time(retry_count)
                    self.logger.warning(
                        f"Request failed with status {response.status_code}. "
                        f"Retrying in {wait_time} seconds..."
                    )
                    time.sleep(wait_time)
                    return self.make_request(
                        url=url,
                        method=method,
                        params=params,
                        data=data,
                        allow_fallback=allow_fallback,
                        retry_count=retry_count + 1
                    )
                    
            # 如果重试失败且允许故障转移，尝试备用URL
            if allow_fallback:
                fallback_url = self._get_fallback_url(url)
                if fallback_url:
                    self.logger.info(f"Trying fallback URL: {fallback_url}")
                    return self.make_request(
                        url=fallback_url,
                        method=method,
                        params=params,
                        data=data,
                        allow_fallback=False,  # 防止无限递归
                        retry_count=0  # 重置重试计数
                    )
            
            response.raise_for_status()
            return {}

        except requests.exceptions.RequestException as e:
            # 处理网络错误的重试
            if retry_count < self.max_retries:
                wait_time = self._get_retry_wait_time(retry_count)
                self.logger.warning(
                    f"Request failed with error: {str(e)}. "
                    f"Retrying in {wait_time} seconds..."
                )
                time.sleep(wait_time)
                return self.make_request(
                    url=url,
                    method=method,
                    params=params,
                    data=data,
                    allow_fallback=allow_fallback,
                    retry_count=retry_count + 1
                )
            
            # 如果重试耗尽且允许故障转移，尝试备用URL
            if allow_fallback:
                fallback_url = self._get_fallback_url(url)
                if fallback_url:
                    self.logger.info(f"Trying fallback URL after error: {fallback_url}")
                    return self.make_request(
                        url=fallback_url,
                        method=method,
                        params=params,
                        data=data,
                        allow_fallback=False,
                        retry_count=0
                    )
            
            self.logger.error(f"Request failed after {retry_count} retries: {str(e)}")
            return {}

    def _get_retry_wait_time(self, retry_count: int) -> float:
        """计算重试等待时间"""
        return self.backoff_factor * (2 ** retry_count)

    def close(self):
        """关闭会话"""
        if self.session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()