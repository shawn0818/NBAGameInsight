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
    max_retries: int = 5
    base_delay: float = 5.0
    max_delay: float = 120.0
    backoff_factor: float = 2.5
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


class RequestWindowManager:
    """请求窗口管理器 - 主动预防API限制"""

    def __init__(self):
        self.window_stats = {
            'large_window': {  # 大窗口(约30分钟)
                'max_requests': 200,  # 根据观察，约800-850请求后会遇到限制
                'count': 0,
                'start_time': time.time(),
                'duration': 1800  # 30分钟
            },
            'medium_window': {  # 中窗口(约5分钟)
                'max_requests': 100,
                'count': 0,
                'start_time': time.time(),
                'duration': 300
            }
        }
        self.logger = logging.getLogger(__name__)

    def register_request(self):
        """注册一次请求"""
        current_time = time.time()

        # 更新所有窗口的请求计数
        for name, window in self.window_stats.items():
            # 检查是否需要重置窗口
            if current_time - window['start_time'] > window['duration']:
                self.logger.info(f"重置{name}窗口计数")
                window['count'] = 0
                window['start_time'] = current_time

            # 增加计数
            window['count'] += 1

            # 检查是否接近限制
            if window['count'] >= window['max_requests'] * 0.85:
                self.logger.warning(f"{name}接近限制阈值({window['count']}/{window['max_requests']})")

            # 检查是否需要强制暂停
            if window['count'] >= window['max_requests']:
                wait_time = window['duration'] - (current_time - window['start_time']) + 10
                if wait_time > 0:
                    self.logger.warning(f"{name}达到限制，强制等待{wait_time:.1f}秒")
                    return wait_time

        return 0  # 无需等待


class HTTPRequestManager:
    """HTTP请求管理器，支持请求重试和备用URL"""

    def __init__(self, headers: Optional[Dict[str, str]] = None, timeout: Optional[int] = None):
        """初始化请求管理器"""
        self.headers = self._prepare_headers(headers)
        self.retry_strategy = RetryStrategy(RetryConfig())
        self.timeout = timeout or 30
        self.logger = logging.getLogger(__name__)
        self.session = self._create_session()

        # 请求间隔控制
        self.last_request_time = 0
        self.min_request_interval = 6.0

        # 会话管理增强
        self.session_age = 0  # 会话年龄(请求次数)
        self.max_session_age = 500  # 会话最大寿命
        self.total_requests = 0  # 总请求计数
        self.last_session_reset = time.time()

        # 窗口管理
        self.window_manager = RequestWindowManager()

        # 自适应参数
        self._min_delay = 5.0
        self._max_delay = 10.0
        self._consecutive_failures = 0
        self._failure_backoff_time = 0

        # 批次阈值调整
        self._batch_thresholds = {
            500: {"delay": 30, "message": "达到500请求阈值，增加等待时间"},
            750: {"delay": 60, "message": "达到750请求阈值，显著增加等待时间"},
            850: {"delay": 120, "message": "接近限制阈值，大幅增加等待时间"}
        }

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

    def _get_random_user_agent(self):
        """获取随机用户代理"""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36"
        ]
        return random.choice(user_agents)

    def _refresh_headers(self):
        """刷新请求头"""
        self.headers['user-agent'] = self._get_random_user_agent()

        # 更新请求头中的时间戳相关字段
        self.headers['cache-control'] = f"no-cache, no-store, must-revalidate, max-age=0"

    def _reset_session(self):
        """重置会话，模拟'停止并重启'效果"""
        if self.session:
            try:
                self.session.close()
            except Exception as e:
                self.logger.error(f"关闭session失败: {str(e)}")

        # 刷新请求头
        self._refresh_headers()

        # 创建新会话
        self.session = self._create_session()
        self.session_age = 0
        self.last_session_reset = time.time()
        self.logger.info("会话已重置，创建新连接")

        # 重置后适当暂停，让服务器"认可"连接变化
        pause_time = random.uniform(3.0, 8.0)
        time.sleep(pause_time)

    def _wait_for_rate_limit(self):
        """等待请求间隔 - 优化的自适应策略"""
        elapsed = time.time() - self.last_request_time

        # 检查是否有强制等待时间(由窗口管理器决定)
        force_wait = self.window_manager.register_request()
        if force_wait > 0:
            self.logger.warning(f"检测到窗口限制，强制等待{force_wait:.1f}秒")
            time.sleep(force_wait)
            # 重置会话
            self._reset_session()
            # 重置时间
            self.last_request_time = time.time()
            return

        # 检查是否达到特定阈值
        for threshold, action in sorted(self._batch_thresholds.items()):
            if self.total_requests >= threshold and self.total_requests < threshold + 5:
                self.logger.warning(action["message"])
                time.sleep(action["delay"])
                break

        # 连续失败指数退避
        if self._consecutive_failures > 0:
            # 更激进的退避策略
            failure_factor = min(10.0, 2.0 ** self._consecutive_failures)
            self.logger.warning(f"检测到连续失败({self._consecutive_failures})，应用退避因子: {failure_factor}")

            # 如果连续失败次数较多，重置会话
            if self._consecutive_failures >= 3:
                self.logger.warning(f"连续失败次数过多({self._consecutive_failures})，重置会话")
                self._reset_session()
                self._consecutive_failures = 0  # 重置失败计数
        else:
            failure_factor = 1.0

        # 会话年龄因子
        session_age_factor = min(3.0, 1.0 + (self.session_age / self.max_session_age) * 2)

        # 基础延迟考虑所有因素
        base_delay = max(
            self.min_request_interval,
            random.uniform(
                self._min_delay * session_age_factor,
                self._max_delay * session_age_factor
            )
        ) * failure_factor

        # 如果需要延迟，则等待
        if elapsed < base_delay:
            wait_time = base_delay - elapsed
            if wait_time > 10:
                self.logger.info(f"应用较长等待: {wait_time:.2f}秒")
            time.sleep(wait_time)

        # 检查是否需要重置会话
        self.session_age += 1
        self.total_requests += 1

        # 基于会话年龄的重置逻辑
        if self.session_age >= self.max_session_age:
            self.logger.info(f"会话请求数达到阈值({self.session_age})，重置会话")
            self._reset_session()

        # 基于时间的会话重置
        session_lifetime = time.time() - self.last_session_reset
        if session_lifetime > 1200 and self.session_age > 100:  # 20分钟且至少处理了100个请求
            self.logger.info(f"会话生命周期达到阈值({session_lifetime:.1f}秒)，重置会话")
            self._reset_session()

        # 随机会话重置 - 10%概率在100次以上请求后随机重置
        if self.session_age > 100 and random.random() < 0.1:
            self.logger.info("随机重置会话，避免出现规律")
            self._reset_session()

        self.last_request_time = time.time()

    def make_request(self, url: str, method: str = 'GET', params: Optional[Dict[str, Any]] = None,
                     data: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """发送HTTP请求 - 保持原接口不变，内部增强自适应逻辑"""
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
                        params=params,
                        json=data,
                        timeout=self.timeout,
                        headers=self.headers
                    )

                    self.logger.info(f"实际请求URL: {response.request.url}")

                    if response.ok:
                        # 请求成功，重置连续失败计数
                        self._consecutive_failures = 0
                        return response.json()
                    else:
                        self.logger.warning(f"请求失败: {response.status_code}, URL: {url}")

                        # 检测到429（请求过多）或服务器错误，增加连续失败计数
                        if response.status_code == 429 or response.status_code >= 500:
                            self._consecutive_failures += 1
                            self.logger.warning(f"检测到可能的请求限制，当前连续失败: {self._consecutive_failures}")

                        should_retry, wait_time = self.retry_strategy.should_retry(
                            status_code=response.status_code,
                            retry_count=retry_count
                        )

                        if should_retry:
                            retry_count += 1
                            # 增加额外随机延迟
                            extra_delay = random.uniform(2.0, 10.0)
                            total_wait = wait_time + extra_delay
                            self.logger.info(f"等待{total_wait:.2f}秒后重试(第{retry_count}次)")
                            time.sleep(total_wait)
                            continue

                        response.raise_for_status()

                except requests.RequestException as e:
                    # 网络异常，增加连续失败计数
                    self._consecutive_failures += 1
                    self.logger.warning(f"请求异常，当前连续失败: {self._consecutive_failures}")

                    should_retry, wait_time = self.retry_strategy.should_retry(
                        error=e,
                        retry_count=retry_count
                    )

                    if should_retry:
                        retry_count += 1
                        # 网络异常使用更长的等待时间
                        total_wait = wait_time + 5.0 * retry_count
                        self.logger.info(f"网络异常，等待{total_wait:.2f}秒后重试(第{retry_count}次)")
                        time.sleep(total_wait)
                        continue
                    raise

        except requests.JSONDecodeError as e:
            self.logger.error(f"JSON解析失败: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"请求失败: {str(e)}")
            return None

    def make_binary_request(self, url: str, method: str = 'GET',
                            params: Optional[Dict[str, Any]] = None) -> Optional[bytes]:
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
                        params=params,  # 增加对params的支持
                        timeout=self.timeout,
                        headers=self.headers
                    )

                    # 添加完整URL日志记录（包含参数）
                    self.logger.info(f"二进制请求URL: {response.request.url}")

                    if response.ok:
                        # 请求成功，重置连续失败计数
                        self._consecutive_failures = 0

                        # 验证是否为二进制数据
                        content_type = response.headers.get('Content-Type', '')
                        if 'text/html' in content_type.lower():
                            self.logger.warning(f"警告：响应可能不是二进制数据，而是HTML: {content_type}")

                        return response.content
                    else:
                        # 检测到429（请求过多）或服务器错误，增加连续失败计数
                        if response.status_code == 429 or response.status_code >= 500:
                            self._consecutive_failures += 1

                        should_retry, wait_time = self.retry_strategy.should_retry(
                            status_code=response.status_code,
                            retry_count=retry_count
                        )

                        if should_retry:
                            retry_count += 1
                            time.sleep(wait_time)
                            continue

                        response.raise_for_status()

                except requests.RequestException as e:
                    # 网络异常，增加连续失败计数
                    self._consecutive_failures += 1

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
            self.logger.error(f"二进制请求失败: {str(e)}")
            return None

    def close(self):
        """关闭session"""
        if self.session:
            try:
                self.session.close()
            except Exception as e:
                self.logger.error(f"关闭session失败: {str(e)}")