# http_handler.py
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import random
import time
import logging
import requests
from enum import Enum


class RetryableErrorType(Enum):
    """可重试的错误类型"""
    TIMEOUT = "timeout"  # 超时错误
    RATE_LIMIT = "rate_limit"  # 请求频率限制
    SERVER_ERROR = "server_error"  # 服务器错误
    NETWORK_ERROR = "network_error"  # 网络连接错误


@dataclass
class RetryConfig:
    """重试配置"""
    # 最大重试次数
    max_retries: int = 3
    # 基础退避时间（秒）
    base_delay: float = 2.0
    # 最大退避时间（秒）
    max_delay: float = 60.0
    # 退避因子
    backoff_factor: float = 2.0
    # 抖动范围 (0-1)
    jitter_factor: float = 0.1
    # 需要重试的HTTP状态码
    retry_status_codes: List[int] = None

    def __post_init__(self):
        if self.retry_status_codes is None:
            self.retry_status_codes = [429,403, 500, 502, 503, 504]


class RetryStrategy:
    """重试策略"""

    def __init__(self, config: RetryConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def _categorize_error(self, error: Exception, status_code: Optional[int] = None) -> Optional[RetryableErrorType]:
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
        # 基础退避时间
        wait_time = min(
            self.config.base_delay * (self.config.backoff_factor ** retry_count),
            self.config.max_delay
        )

        # 根据错误类型调整等待时间
        if error_type == RetryableErrorType.RATE_LIMIT:
            # 频率限制错误需要更长的等待时间
            wait_time *= 1.5
        elif error_type == RetryableErrorType.NETWORK_ERROR:
            # 网络错误可能需要更多时间恢复
            wait_time *= 1.2

        # 添加随机抖动避免雪崩效应
        jitter = random.uniform(
            -wait_time * self.config.jitter_factor,
            wait_time * self.config.jitter_factor
        )

        return max(wait_time + jitter, 0)

    def should_retry(self,
                     error: Optional[Exception] = None,
                     status_code: Optional[int] = None,
                     retry_count: int = 0) -> tuple[bool, float]:
        """判断是否应该重试请求"""
        # 超过最大重试次数
        if retry_count >= self.config.max_retries:
            self.logger.debug(f"Exceeded maximum retry attempts ({self.config.max_retries})")
            return False, 0

        # 处理 HTTP 状态码
        if status_code is not None:
            if status_code < 400:  # 成功的响应
                return False, 0

            # 记录状态码的详细信息
            self.logger.debug(f"Received status code {status_code}")

            if status_code in self.config.retry_status_codes:
                self.logger.info(f"Status code {status_code} is retryable")
                error_type = RetryableErrorType.SERVER_ERROR
                if status_code == 429:
                    error_type = RetryableErrorType.RATE_LIMIT
                elif status_code == 403:
                    error_type = RetryableErrorType.RATE_LIMIT  # 将403也视为频率限制

                wait_time = self._calculate_wait_time(retry_count, error_type)
                return True, wait_time

            self.logger.debug(f"Status code {status_code} is not retryable")
            return False, 0



class HTTPRequestManager:
    """HTTP请求管理器，支持请求重试和备用URL"""

    def __init__(self,
                 headers: Optional[Dict[str, str]] = None,
                 timeout: Optional[int] = None,
                 backoff_factor: float = 1.0,
                 retry_status_codes: Optional[List[int]] = None,
                 max_retries: int = 3,
                 fallback_urls: Optional[Dict[str, str]] = None):
        """初始化请求管理器"""
        self.headers = self._prepare_headers(headers)
        retry_config = RetryConfig(
            max_retries=max_retries,
            backoff_factor=backoff_factor,
            retry_status_codes=retry_status_codes or [429, 500, 502, 503, 504]
        )
        self.retry_strategy = RetryStrategy(retry_config)
        self.timeout = timeout or 30
        self.fallback_urls = fallback_urls or {}
        self.logger = logging.getLogger(__name__)
        self.session = self._create_session()
        self.last_request_time = 0
        self.min_request_interval = 1.0

    def make_request(self,
                     url: str,
                     method: str = 'GET',
                     params: Optional[Dict[str, Any]] = None,
                     data: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """发送HTTP请求"""
        try:
            retry_count = 0
            while True:
                try:
                    self._wait_for_rate_limit()

                    # 记录实际发送的请求头
                    self.logger.debug(f"Sending request with headers: {dict(self.session.headers)}")
                    self.logger.debug(f"Request headers: {self.session.headers}")
                    self.logger.debug(f"Request params: {params}")

                    response = self.session.request(
                        method=method.upper(),
                        url=url,
                        params=params,
                        json=data,
                        timeout=self.timeout
                    )


                    # 如果响应不成功
                    if not response.ok:
                        self.logger.warning(f"Request failed with status {response.status_code}")
                        self.logger.debug(f"Response content: {response.text}")

                        # 检查是否需要重试
                        should_retry, wait_time = self.retry_strategy.should_retry(
                            status_code=response.status_code,
                            retry_count=retry_count
                        )

                        if should_retry:
                            retry_count += 1
                            self.logger.info(f"Retrying after {wait_time} seconds...")
                            time.sleep(wait_time)
                            continue

                        # 如果不重试，尝试使用备用URL
                        fallback_url = self._get_fallback_url(url)
                        if fallback_url:
                            self.logger.info(f"Trying fallback URL: {fallback_url}")
                            return self.make_request(
                                url=fallback_url,
                                method=method,
                                params=params,
                                data=data
                            )

                        response.raise_for_status()

                    # 如果响应成功
                    self.logger.info(f"Making {method} request to: {url} (attempt {retry_count + 1})")
                    self.logger.info(f"Request successful")
                    return response.json()

                except requests.RequestException as e:
                    self.logger.error(f"Request error: {str(e)}")

                    should_retry, wait_time = self.retry_strategy.should_retry(
                        error=e,
                        retry_count=retry_count
                    )

                    if should_retry:
                        retry_count += 1
                        self.logger.info(f"Retrying after {wait_time} seconds...")
                        time.sleep(wait_time)
                        continue

                    # 如果不重试，尝试使用备用URL
                    fallback_url = self._get_fallback_url(url)
                    if fallback_url:
                        self.logger.info(f"Trying fallback URL: {fallback_url}")
                        return self.make_request(
                            url=fallback_url,
                            method=method,
                            params=params,
                            data=data
                        )
                    raise

        except Exception as e:
            self.logger.error(f"Request failed: {str(e)}")
            return None


    def _prepare_headers(self, headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        """准备请求头"""
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'
        }
        if headers:
            default_headers.update(headers)
        return default_headers

    def _create_session(self) -> requests.Session:
        """创建session"""
        session = requests.Session()
        session.headers.update(self.headers)
        return session

    def _wait_for_rate_limit(self):
        """等待请求间隔"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _get_fallback_url(self, url: str) -> Optional[str]:
        """获取备用URL"""
        for base_url, fallback_base in self.fallback_urls.items():
            if url.startswith(base_url):
                return url.replace(base_url, fallback_base)
        return None

    def close(self):
        """关闭session"""
        if self.session:
            self.session.close()