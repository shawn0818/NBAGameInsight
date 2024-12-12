import requests
from typing import Optional, Dict, Any, Union, Callable
from collections.abc import Callable as ABCCallable
import time
from functools import wraps
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class HTTPConfig:
    """HTTP 请求配置"""
    HEADERS: Dict[str, str] = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "DNT": "1",
        "Origin": "https://www.nba.com",
        "Pragma": "no-cache",
        "Referer": "https://www.nba.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }
    
    TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 5
    BACKOFF_FACTOR: float = 0.3
    
    PROXY: Optional[str] = None
    
    RETRY_STATUS_CODES: list[int] = [429, 500, 502, 503, 504]
    
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
    """通用 HTTP 请求管理器"""
    
    def __init__(self, 
                 headers: Optional[Dict[str, str]] = None,
                 max_retries: Optional[int] = None,
                 timeout: Optional[int] = None,
                 backoff_factor: Optional[float] = None):
        """
        初始化请求管理器
        
        Args:
            headers: 请求头
            max_retries: 最大重试次数
            timeout: 超时时间（秒）
            backoff_factor: 重试间隔因子
        """
        self.headers: Dict[str, str] = headers or HTTPConfig.HEADERS
        self.timeout: int = timeout or HTTPConfig.TIMEOUT
        self.max_retries: int = max_retries or HTTPConfig.MAX_RETRIES
        self.backoff_factor: float = backoff_factor or HTTPConfig.BACKOFF_FACTOR
        self.session: requests.Session = self._create_session()
        
    def _create_session(self) -> requests.Session:
        """创建带有重试机制的会话"""
        session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=HTTPConfig.RETRY_STATUS_CODES,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(self.headers)
        
        proxies = HTTPConfig.get_proxies()
        if proxies:
            session.proxies.update(proxies)
            
        return session
        
    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """处理响应数据"""
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.JSONDecodeError as e:
            logging.error(f"JSON decode error: {e}")
            return {}
        except requests.exceptions.HTTPError as e:
            logging.error(f"HTTP error: {e}")
            return {}
            
    def make_request(self, 
                    url: str, 
                    method: str = 'GET',
                    params: Optional[Dict[str, Any]] = None,
                    data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        发送 HTTP 请求
        
        Args:
            url: 请求 URL
            method: 请求方法 ('GET', 'POST' 等)
            params: URL 参数
            data: 请求体数据
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=self.timeout
            )
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error: {e}")
            return {}
            
    def close(self) -> None:
        """关闭会话"""
        self.session.close()
        
    def __enter__(self) -> 'HTTPRequestManager':
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

def rate_limit(calls: int, period: int):
    """
    请求频率限制装饰器
    
    Args:
        calls: 允许的调用次数
        period: 时间周期（秒）
    """
    def decorator(func):
        last_reset = time.time()
        calls_made = 0
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal last_reset, calls_made
            
            now = time.time()
            if now - last_reset >= period:
                calls_made = 0
                last_reset = now
                
            if calls_made >= calls:
                wait_time = period - (now - last_reset)
                if wait_time > 0:
                    time.sleep(wait_time)
                calls_made = 0
                last_reset = time.time()
                
            calls_made += 1
            return func(*args, **kwargs)
            
        return wrapper
    return decorator

class DataPoller:
    """通用数据轮询器"""
    
    def __init__(self, interval: int = 60):
        """
        初始化轮询器
        
        Args:
            interval: 轮询间隔（秒）
        """
        self.interval = interval
        self.http_manager = HTTPRequestManager()
        
    @rate_limit(calls=60, period=60)
    def poll_data(self, url: str, **kwargs) -> Dict[str, Any]:
        """
        获取数据
        
        Args:
            url: 请求 URL
            **kwargs: 其他请求参数
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        return self.http_manager.make_request(url, **kwargs)
        
    def start_polling(self, 
                     url: str, 
                     stop_condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
                     callback: Optional[Callable[[Dict[str, Any]], None]] = None,
                     **kwargs) -> None:
        """
        开始轮询数据
        
        Args:
            url: 请求 URL
            stop_condition: 停止条件函数
            callback: 数据处理回调函数
            **kwargs: 其他请求参数
        """
        try:
            while True:
                data = self.poll_data(url, **kwargs)
                if callback:
                    callback(data)
                if stop_condition and stop_condition(data):
                    break
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logging.info("Polling stopped by user")
        finally:
            self.http_manager.close()