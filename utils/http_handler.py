import requests
from typing import Optional, Dict, Any, List
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config.nba_config import NBAConfig


class HTTPConfig:
    """通用 HTTP 请求配置"""
    HEADERS: Dict[str, str] = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Host": "stats.nba.com",
        "Origin": "https://www.nba.com",
        "Referer": "https://www.nba.com/",
        "sec-ch-ua": "\"Not_A Brand\";v=\"8\", \"Chromium\";v=\"120\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 5
    BACKOFF_FACTOR: float = 0.3
    
    PROXY: Optional[str] = None
    
    RETRY_STATUS_CODES: List[int] = [429, 500, 502, 503, 504]

    @classmethod
    def get_proxies(cls) -> Optional[Dict[str, str]]:
        """获取代理配置"""
        if cls.PROXY:
            return {
                "http": cls.PROXY,
                "https": cls.PROXY
            }
        return None

class HTTPRequestManager:
    """HTTP请求管理器，支持请求重试和备用URL"""
    
    def __init__(self, 
                 headers: Optional[Dict[str, str]] = None,
                 max_retries: Optional[int] = None,
                 timeout: Optional[int] = None,
                 backoff_factor: Optional[float] = None,
                 retry_status_codes: Optional[list] = None,
                 fallback_urls: Optional[Dict[str, str]] = None):
        """
        初始化请求管理器。

        Args:
            headers: 请求头
            max_retries: 最大重试次数
            timeout: 超时时间（秒）
            backoff_factor: 重试间隔因子
            retry_status_codes: 需要重试的HTTP状态码列表
            fallback_urls: 故障转移URL映射 {"primary_url": "fallback_url"}
        """
        self.headers = headers
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
                    allow_fallback: bool = True) -> Dict[str, Any]:
        """
        发送HTTP请求。

        Args:
            url: 请求URL
            method: 请求方法 ('GET', 'POST' 等)
            params: URL参数
            data: 请求体数据
            allow_fallback: 是否允许使用故障转移URL
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        try:
            # 记录请求信息
            self.logger.info(f"Making {method} request to: {url}")
            if params:
                self.logger.debug(f"Request params: {params}")
            
            response = self.session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=data,
                timeout=self.timeout,
                #verify=False  # 禁用SSL验证以处理证书问题
            )
            
            # 检查响应状态
            if response.ok:
                return response.json()
                
            # 如果请求失败且允许故障转移，尝试备用URL
            if allow_fallback:
                fallback_url = self._get_fallback_url(url)
                if fallback_url:
                    self.logger.info(f"Trying fallback URL: {fallback_url}")
                    return self.make_request(
                        url=fallback_url,
                        method=method,
                        params=params,
                        data=data,
                        allow_fallback=False  # 防止无限递归
                    )
            
            response.raise_for_status()
            return {}

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed: {str(e)}")
            if allow_fallback:
                fallback_url = self._get_fallback_url(url)
                if fallback_url:
                    self.logger.info(f"Trying fallback URL after error: {fallback_url}")
                    return self.make_request(
                        url=fallback_url,
                        method=method,
                        params=params,
                        data=data,
                        allow_fallback=False
                    )
            return {}

    def close(self):
        """关闭会话"""
        if self.session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()