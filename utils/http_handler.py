import logging
import time
import random
from dataclasses import dataclass
import requests
from enum import Enum
from typing import List, Optional, Dict, Any
from requests.adapters import HTTPAdapter


class RetryableErrorType(Enum):
    """可重试的错误类型"""
    TIMEOUT = "timeout"  # 超时错误
    RATE_LIMIT = "rate_limit"  # 请求频率限制
    SERVER_ERROR = "server_error"  # 服务器错误
    NETWORK_ERROR = "network_error"  # 网络连接错误


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 2.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    jitter_factor: float = 0.1
    retry_status_codes: List[int] = None

    def __post_init__(self):
        if self.retry_status_codes is None:
            self.retry_status_codes = [429, 403, 500, 502, 503, 504]

        # 添加参数验证
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.base_delay <= 0 or self.max_delay <= 0:
            raise ValueError("delays must be positive")
        if self.backoff_factor <= 0:
            raise ValueError("backoff_factor must be positive")
        if not 0 <= self.jitter_factor <= 1:
            raise ValueError("jitter_factor must be between 0 and 1")


class RetryStrategy:
    """重试策略"""

    def __init__(self, config: RetryConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _categorize_error(error: Exception, status_code: Optional[int] = None) -> Optional[RetryableErrorType]:
        """对错误进行分类"""
        if status_code:
            if status_code == 429:
                return RetryableErrorType.RATE_LIMIT
            if status_code >= 500:
                return RetryableErrorType.SERVER_ERROR

        if isinstance(error, requests.exceptions.Timeout):
            return RetryableErrorType.TIMEOUT
        if isinstance(error, requests.exceptions.ConnectionError):
            return RetryableErrorType.NETWORK_ERROR

        return None

    def _calculate_wait_time(self, retry_count: int, error_type: RetryableErrorType) -> float:
        """计算重试等待时间"""
        wait_time = min(
            self.config.base_delay * (self.config.backoff_factor ** retry_count),
            self.config.max_delay
        )

        if error_type == RetryableErrorType.RATE_LIMIT:
            wait_time *= 1.5
        elif error_type == RetryableErrorType.NETWORK_ERROR:
            wait_time *= 1.2

        jitter = random.uniform(
            -wait_time * self.config.jitter_factor,
            wait_time * self.config.jitter_factor
        )

        return max(wait_time + jitter, 0)

    def should_retry(self, error: Optional[Exception] = None, status_code: Optional[int] = None,
                    retry_count: int = 0) -> tuple[bool, float]:
        """判断是否应该重试请求"""
        if retry_count >= self.config.max_retries:
            self.logger.debug(f"Exceeded maximum retry attempts ({self.config.max_retries})")
            return False, 0

        if status_code is not None:
            if status_code < 400:  # 成功的响应
                return False, 0

            self.logger.debug(f"Received status code {status_code}")
            if status_code in self.config.retry_status_codes:
                self.logger.info(f"Status code {status_code} is retryable")
                error_type = RetryableErrorType.SERVER_ERROR
                if status_code == 429:
                    error_type = RetryableErrorType.RATE_LIMIT
                elif status_code == 403:
                    error_type = RetryableErrorType.RATE_LIMIT

                wait_time = self._calculate_wait_time(retry_count, error_type)
                return True, wait_time

            self.logger.debug(f"Status code {status_code} is not retryable")
            return False, 0

        if error:
            error_type = self._categorize_error(error)
            if error_type:
                wait_time = self._calculate_wait_time(retry_count, error_type)
                return True, wait_time

        return False, 0


class HTTPRequestManager:
    """HTTP请求管理器，支持请求重试和备用URL"""

    def __init__(self, headers: Optional[Dict[str, str]] = None, timeout: Optional[int] = None):
        """初始化请求管理器"""
        self.headers = self._prepare_headers(headers)
        self.retry_strategy = RetryStrategy(RetryConfig())
        self.timeout = timeout or 30
        self.logger = logging.getLogger(__name__)
        self.session = self._create_session()
        self.last_request_time = 0
        self.min_request_interval = 3.0

    @staticmethod
    def _prepare_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        """准备请求头"""
        default_headers = {
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate'
        }
        if headers:
            default_headers.update(headers)
        return default_headers

    def _create_session(self) -> requests.Session:
        """创建session"""
        session = requests.Session()
        session.headers.update(self.headers)
        adapter = HTTPAdapter(max_retries=1)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def make_request(self, url: str, method: str = 'GET', params: Optional[Dict[str, Any]] = None,
                    data: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """发送HTTP请求"""
        if not url:
            raise ValueError("URL cannot be empty")

        try:
            retry_count = 0
            while True:
                try:
                    self._wait_for_rate_limit()

                    response = self.session.request(method=method.upper(), url=url, params=params, json=data,
                                                 timeout=self.timeout,headers=self.headers)

                    self.logger.debug(f"请求URL: {response.request.url}")  # 打印最终请求的 URL (可能经过重定向)
                    self.logger.debug(f"请求方法: {method}")
                    self.logger.debug(f"请求头: {self.headers}")
                    self.logger.debug(f"响应状态码: {response.status_code}")
                    self.logger.debug(f"响应头: {response.headers}")

                    if not response.ok:
                        self.logger.warning(f"请求失败: {response.status_code}, URL: {url}")
                        should_retry, wait_time = self.retry_strategy.should_retry(status_code=response.status_code,
                                                                                retry_count=retry_count)

                        if should_retry:
                            retry_count += 1
                            time.sleep(wait_time)
                            continue

                        response.raise_for_status()

                    return response.json()

                except requests.RequestException as e:
                    should_retry, wait_time = self.retry_strategy.should_retry(error=e, retry_count=retry_count)

                    if should_retry:
                        retry_count += 1
                        time.sleep(wait_time)
                        continue
                    raise

        except requests.JSONDecodeError as e:
            self.logger.error(f"JSON解析失败: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"请求失败: {str(e)}")
            return None

    # 在http_handler.py中添加新方法
    def make_binary_request(self, url: str, method: str = 'GET') -> Optional[bytes]:
        """发送HTTP请求并返回二进制响应内容"""
        if not url:
            raise ValueError("URL cannot be empty")

        try:
            retry_count = 0
            while True:
                try:
                    self._wait_for_rate_limit()

                    response = self.session.request(
                        method=method.upper(),
                        url=url,
                        timeout=self.timeout,
                        headers=self.headers
                    )

                    if not response.ok:
                        should_retry, wait_time = self.retry_strategy.should_retry(
                            status_code=response.status_code,
                            retry_count=retry_count
                        )

                        if should_retry:
                            retry_count += 1
                            time.sleep(wait_time)
                            continue

                        response.raise_for_status()

                    return response.content

                except requests.RequestException as e:
                    should_retry, wait_time = self.retry_strategy.should_retry(
                        error=e,
                        retry_count=retry_count
                    )

                    if should_retry:
                        retry_count += 1
                        time.sleep(wait_time)
                        continue
                    raise

        except Exception as e:
            self.logger.error(f"请求失败: {str(e)}")
            return None

    def _wait_for_rate_limit(self):
        """等待请求间隔"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def close(self):
        """关闭session"""
        if self.session:
            try:
                self.session.close()
            except Exception as e:
                self.logger.error(f"关闭session失败: {str(e)}")