import logging
import time
import random
from dataclasses import dataclass
import requests
from enum import Enum
from typing import List, Optional, Dict, Any, Union
from requests.adapters import HTTPAdapter


class RetryableErrorType(Enum):
    """可重试的错误类型枚举"""
    TIMEOUT = "timeout"  # 请求超时错误
    RATE_LIMIT = "rate_limit"  # API速率限制错误
    SERVER_ERROR = "server_error"  # 服务器端错误
    NETWORK_ERROR = "network_error"  # 网络连接错误


@dataclass
class RetryConfig:
    """重试配置数据类"""
    max_retries: int = 5
    base_delay: float = 5.0
    max_delay: float = 120.0
    backoff_factor: float = 2.5
    jitter_factor: float = 0.1
    retry_status_codes: List[int] = None

    def __post_init__(self):
        """初始化后验证并设置默认值"""
        if self.retry_status_codes is None:
            self.retry_status_codes = [429, 403, 500, 502, 503, 504]

        # 参数验证
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.base_delay <= 0 or self.max_delay <= 0:
            raise ValueError("delays must be positive")
        if self.backoff_factor <= 0:
            raise ValueError("backoff_factor must be positive")
        if not 0 <= self.jitter_factor <= 1:
            raise ValueError("jitter_factor must be between 0 and 1")


class RetryStrategy:
    """重试策略类"""

    def __init__(self, config: RetryConfig):
        """初始化重试策略"""
        self.config = config
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _categorize_error(error: Exception, status_code: Optional[int] = None) -> Optional[RetryableErrorType]:
        """将错误分类为预定义的错误类型"""
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
            wait_time *= 1.5  # 速率限制错误增加50%等待时间
        elif error_type == RetryableErrorType.NETWORK_ERROR:
            wait_time *= 1.2  # 网络错误增加20%等待时间

        jitter = random.uniform(
            -wait_time * self.config.jitter_factor,
            wait_time * self.config.jitter_factor
        )

        return max(wait_time + jitter, 0)

    def should_retry(self, error: Optional[Exception] = None, status_code: Optional[int] = None,
                     retry_count: int = 0) -> tuple[bool, float]:
        """判断是否应该重试请求"""
        if retry_count >= self.config.max_retries:
            self.logger.debug(f"超过最大重试次数 ({self.config.max_retries})")
            return False, 0

        if status_code is not None:
            if status_code < 400:  # 成功的响应
                return False, 0

            self.logger.debug(f"收到状态码 {status_code}")
            if status_code in self.config.retry_status_codes:
                self.logger.info(f"状态码 {status_code} 可重试")

                error_type = RetryableErrorType.SERVER_ERROR
                if status_code == 429:
                    error_type = RetryableErrorType.RATE_LIMIT
                elif status_code == 403:
                    error_type = RetryableErrorType.RATE_LIMIT

                wait_time = self._calculate_wait_time(retry_count, error_type)
                return True, wait_time

            self.logger.debug(f"状态码 {status_code} 不可重试")
            return False, 0

        if error:
            error_type = self._categorize_error(error)
            if error_type:
                wait_time = self._calculate_wait_time(retry_count, error_type)
                return True, wait_time

        return False, 0


class RequestWindowManager:
    """请求窗口管理器 - 优化版

    通过监控不同时间窗口内的请求数量，主动预防API限制。
    使用更灵活的等待策略和渐进式减速机制。
    """

    def __init__(self):
        """初始化请求窗口管理器"""
        # 定义多个时间窗口来监控不同周期的请求频率
        self.window_stats = {
            'large_window': {  # 大窗口(约30分钟)
                'max_requests': 800,  # 根据观察，约800-850请求后会遇到限制
                'count': 0,
                'start_time': time.time(),
                'duration': 1800,  # 30分钟
                'warning_threshold': 0.75  # 75%时开始预警
            },
            'medium_window': {  # 中窗口(约5分钟)
                'max_requests': 200,
                'count': 0,
                'start_time': time.time(),
                'duration': 300,  # 5分钟
                'warning_threshold': 0.75  # 75%时开始预警
            }
        }

        # 强制等待相关设置
        self.max_force_wait = 300  # 最大强制等待时间(秒)
        self.min_force_wait = 10  # 最小强制等待时间(秒)
        self.consecutive_limits = 0  # 连续触发限制计数
        self.last_limit_time = 0  # 上次触发限制的时间
        self.last_action = None  # 上次执行的动作类型

        self.logger = logging.getLogger(__name__)

    def register_request(self) -> Dict[str, Union[float, str, None]]:
        """注册一次请求并检查是否需要限流

        采用更智能的三级限流策略：预警减速、部分暂停和强制等待

        Returns:
            Dict[str, Union[float, str, None]]: 包含等待信息的字典，包括等待时间、原因和窗口信息
        """
        current_time = time.time()
        result: Dict[str, Union[float, str, None]] = {
            "wait_time": 0,
            "action": "none",
            "window": None,
            "message": None
        }

        # 更新所有窗口的请求计数和状态
        for name, window in self.window_stats.items():
            # 检查是否需要重置窗口
            if current_time - window['start_time'] > window['duration']:
                self.logger.info(f"重置{name}窗口计数，之前计数: {window['count']}")
                window['count'] = 0
                window['start_time'] = current_time

            # 增加计数
            window['count'] += 1

            # 计算窗口使用率
            usage_ratio = window['count'] / window['max_requests']

            # 三级限流策略
            if usage_ratio >= 1.0:
                # 1. 强制等待策略 - 使用指数退避但有上限
                # 计算窗口剩余时间
                remaining_time = window['duration'] - (current_time - window['start_time'])

                # 基础等待时间是剩余时间的一部分加上固定的安全边际
                base_wait = remaining_time * 0.4 + self.min_force_wait

                # 根据连续触发次数应用退避因子
                if current_time - self.last_limit_time < window['duration'] * 2:
                    # 短时间内再次触发，增加连续计数
                    self.consecutive_limits += 1
                else:
                    # 较长时间未触发，重置连续计数
                    self.consecutive_limits = 0

                # 应用指数退避，但有上限
                backoff_factor = min(4.0, 1.0 + (0.5 * self.consecutive_limits))
                force_wait = min(base_wait * backoff_factor, self.max_force_wait)

                self.logger.warning(
                    f"{name}达到限制阈值({window['count']}/{window['max_requests']}), "
                    f"强制等待{force_wait:.1f}秒 (连续触发:{self.consecutive_limits}, 退避因子:{backoff_factor:.1f})"
                )

                self.last_limit_time = current_time
                self.last_action = "force_wait"

                result["wait_time"] = force_wait
                result["action"] = "force_wait"
                result["window"] = name
                result["message"] = f"{name}达到限制阈值，强制等待"
                return result

            elif usage_ratio >= 0.9:
                # 2. 部分暂停策略 - 接近限制时采取较短暂停
                # 只有在没有其他更高优先级等待时才执行
                if result["wait_time"] == 0:
                    partial_wait = min(30.0, (usage_ratio - 0.9) * 300)  # 最多30秒
                    self.logger.warning(
                        f"{name}接近限制阈值({window['count']}/{window['max_requests']}={usage_ratio:.2f}), "
                        f"部分暂停{partial_wait:.1f}秒"
                    )
                    self.last_action = "partial_wait"

                    result["wait_time"] = partial_wait
                    result["action"] = "partial_wait"
                    result["window"] = name
                    result["message"] = f"{name}接近限制阈值，部分暂停"

            elif usage_ratio >= window['warning_threshold']:
                # 3. 预警减速策略 - 达到警告阈值但未接近限制
                # 只记录日志，不强制等待
                self.logger.info(
                    f"{name}达到警告阈值({window['count']}/{window['max_requests']}={usage_ratio:.2f})"
                )

                # 如果没有更高优先级的等待，设置一个非常短的随机等待
                if result["wait_time"] == 0:
                    # 轻微随机等待，0.5-2秒
                    minor_wait = random.uniform(0.5, 2.0)
                    result["wait_time"] = minor_wait
                    result["action"] = "minor_wait"
                    result["window"] = name
                    result["message"] = f"{name}达到警告阈值，轻微减速"

        return result


class HTTPRequestManager:
    """增强版HTTP请求管理器

    集成了单个请求管理和批量请求控制功能，提供统一的请求速率控制、
    重试逻辑、会话管理，以及批量处理能力。

    优化的协调机制确保不同层级的速率控制正确配合，避免过度保守。
    """

    def __init__(self, headers: Optional[Dict[str, str]] = None, timeout: Optional[int] = None):
        """初始化请求管理器"""
        self.headers = self._prepare_headers(headers)
        self.retry_strategy = RetryStrategy(RetryConfig())
        self.timeout = timeout or 30
        self.logger = logging.getLogger(__name__)
        self.session = self._create_session()

        # 请求间隔控制
        self.last_request_time = 0
        self.min_request_interval = 3.0  # 降低最小请求间隔，更依赖窗口管理器的控制

        # 会话管理
        self.session_age = 0  # 会话年龄(请求次数)
        self.max_session_age = 500  # 会话最大寿命
        self.total_requests = 0  # 总请求计数
        self.last_session_reset = time.time()

        # 窗口管理
        self.window_manager = RequestWindowManager()

        # 自适应请求参数
        self._min_delay = 3.0  # 降低最小延迟(秒)
        self._max_delay = 8.0  # 降低最大延迟(秒)
        self._consecutive_failures = 0  # 连续失败计数

        # 统计信息
        self.recent_delays = []  # 记录最近的延迟信息，用于动态调整
        self.recent_delay_sources = {}  # 记录不同来源的延迟频率
        self.last_long_wait_time = 0  # 上次长时间等待的时间点
        self.last_long_wait_duration = 0  # 上次长时间等待的持续时间

        # 批次阈值调整 - 基于总请求数的调整策略
        # 减少固定阈值层级，避免与窗口限制重叠
        self._batch_thresholds = {
            400: {"delay": 20, "message": "达到400请求阈值，适度增加等待时间"},
            700: {"delay": 45, "message": "达到700请求阈值，显著增加等待时间"}
        }

        # 批次管理相关属性
        self.batch_count = 0  # 已处理批次数
        self.last_batch_time = 0  # 上次批次处理时间
        self.batch_interval = 60  # 默认批次间隔(秒)
        self.adaptive_batch = True  # 是否启用自适应批次间隔

        # 批次间隔调整阈值
        self.batch_interval_thresholds = {
            10: 1.5,  # 10批后增加50%
            15: 2.0,  # 15批后加倍
            20: 3.0  # 20批后增加3倍
        }

        # 长暂停阈值 - 减少长暂停次数和时长
        self.long_pause_thresholds = [
            {"batch": 20, "pause": 120, "message": "完成20批处理，暂停120秒让API冷却"},
            {"batch": 40, "pause": 180, "message": "完成40批处理，暂停180秒让API冷却"}
        ]

        # 协调控制参数
        self.recent_force_wait = False  # 最近是否执行了强制等待
        self.last_force_wait_time = 0  # 上次强制等待的时间
        self.post_force_wait_count = 0  # 强制等待后的请求计数

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
        """创建HTTP会话"""
        session = requests.Session()
        session.headers.update(self.headers)
        adapter = HTTPAdapter(max_retries=1)  # 内置重试设为1，使用自定义重试策略
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    @staticmethod
    def _get_random_user_agent():
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
        self.headers['user-agent'] = HTTPRequestManager._get_random_user_agent()
        self.headers['cache-control'] = f"no-cache, no-store, must-revalidate, max-age=0"

    def _reset_session(self):
        """重置会话"""
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
        pause_time = random.uniform(2.0, 5.0)  # 减少默认等待时间
        time.sleep(pause_time)

    def _record_delay(self, source: str, duration: float):
        """记录延迟信息

        跟踪不同来源的延迟频率和时长，用于分析和调整策略。

        Args:
            source: 延迟来源标识
            duration: 延迟时长(秒)
        """
        # 记录延迟来源统计
        self.recent_delay_sources[source] = self.recent_delay_sources.get(source, 0) + 1

        # 保存最近的延迟信息
        self.recent_delays.append({"source": source, "duration": duration, "time": time.time()})

        # 只保留最近50条记录
        if len(self.recent_delays) > 50:
            self.recent_delays.pop(0)

        # 如果是长时间等待，特别记录
        if duration > 60:
            self.last_long_wait_time = time.time()
            self.last_long_wait_duration = duration

    def _wait_for_rate_limit(self):
        """等待请求间隔 - 优化的自适应策略

        控制请求频率，实现自适应等待策略，根据多种因素动态调整等待时间。
        与窗口管理器和批次控制器协调，避免重叠等待。
        """
        elapsed = time.time() - self.last_request_time
        delay_source = "adaptive"  # 默认延迟来源

        # 1. 检查窗口管理器是否需要强制等待
        window_result = self.window_manager.register_request()
        force_wait = window_result["wait_time"]

        if force_wait > 0:
            delay_source = f"window_{window_result['action']}"
            self.logger.warning(
                f"{window_result['message']}，等待{force_wait:.1f}秒"
            )

            # 记录强制等待信息
            self._record_delay(delay_source, force_wait)

            # 执行等待
            time.sleep(force_wait)

            # 重置会话 - 只在强制等待较长时间后重置
            if force_wait > 30:
                self._reset_session()

            # 更新强制等待相关状态
            self.recent_force_wait = True
            self.last_force_wait_time = time.time()
            self.post_force_wait_count = 0

            # 重置时间
            self.last_request_time = time.time()
            return

        # 2. 检查批次阈值 - 只有在距离上次强制等待较远时才检查
        # 避免与窗口管理器的强制等待重叠
        if not self.recent_force_wait or time.time() - self.last_force_wait_time > 300:
            for threshold, action in sorted(self._batch_thresholds.items()):
                if threshold <= self.total_requests < threshold + 5:
                    wait_time = action["delay"]
                    self.logger.warning(action["message"])

                    delay_source = f"threshold_{threshold}"
                    self._record_delay(delay_source, wait_time)

                    time.sleep(wait_time)
                    break

        # 3. 自适应延迟策略 - 根据强制等待后的状态适当调整
        # 强制等待后降低普通延迟，随着请求数增加逐渐恢复正常延迟
        if self.recent_force_wait:
            self.post_force_wait_count += 1

            # 强制等待后的渐进恢复期
            if self.post_force_wait_count < 50:
                # 前50个请求使用更短的延迟
                recovery_factor = min(1.0, self.post_force_wait_count / 50)
                min_delay = self._min_delay * recovery_factor
                max_delay = self._max_delay * recovery_factor

                # 记录日志
                if self.post_force_wait_count == 1:
                    self.logger.info(f"强制等待后应用减速恢复策略，初始延迟减少至正常的{recovery_factor:.1%}")
            else:
                # 恢复正常延迟
                min_delay = self._min_delay
                max_delay = self._max_delay

                # 完全恢复
                if self.post_force_wait_count == 50:
                    self.logger.info("强制等待后的减速恢复期结束，恢复正常延迟")
                    self.recent_force_wait = False
        else:
            # 正常延迟参数
            min_delay = self._min_delay
            max_delay = self._max_delay

        # 连续失败指数退避
        if self._consecutive_failures > 0:
            # 更激进的退避策略
            failure_factor = min(5.0, 1.5 ** self._consecutive_failures)
            self.logger.warning(f"检测到连续失败({self._consecutive_failures})，应用退避因子: {failure_factor}")

            # 如果连续失败次数较多，重置会话
            if self._consecutive_failures >= 3:
                self.logger.warning(f"连续失败次数过多({self._consecutive_failures})，重置会话")
                self._reset_session()
                self._consecutive_failures = 0  # 重置失败计数

            delay_source = "failure_backoff"
        else:
            failure_factor = 1.0

        # 会话年龄因子 - 会话使用时间越长，等待时间越长
        session_age_ratio = self.session_age / self.max_session_age
        session_age_factor = 1.0 + session_age_ratio  # 线性增长，最大2倍

        # 基础延迟考虑所有因素
        base_delay = random.uniform(min_delay, max_delay) * failure_factor * session_age_factor

        # 确保至少有最小的请求间隔
        base_delay = max(self.min_request_interval, base_delay)

        # 如果需要延迟，则等待
        if elapsed < base_delay:
            wait_time = base_delay - elapsed
            if wait_time > 5:
                self.logger.info(
                    f"自适应延迟: {wait_time:.2f}秒 (失败:{failure_factor:.1f}, 会话:{session_age_factor:.1f})"
                )

            self._record_delay(delay_source, wait_time)
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

        # 随机会话重置 - 8%概率在100次以上请求后随机重置，降低概率避免频繁重置
        if self.session_age > 100 and random.random() < 0.08:
            self.logger.info("随机重置会话，避免出现规律")
            self._reset_session()

        self.last_request_time = time.time()

    def wait_for_next_batch(self):
        """等待直到可以处理下一批次

        实现批量处理控制逻辑，根据批次数动态调整等待时间。
        与单个请求的速率控制协调，避免重叠等待。

        Returns:
            float: 实际应用的间隔时间(秒)
        """
        current_time = time.time()
        elapsed = current_time - self.last_batch_time

        # 计算应用的间隔时间
        interval = self.batch_interval
        delay_source = "batch_interval"

        # 检查是否距离上次强制等待较近
        # 如果刚进行了强制等待，减少批次间隔
        if time.time() - self.last_long_wait_time < 300:  # 5分钟内
            reduction_factor = 0.3  # 减少至30%
            original_interval = interval
            interval = interval * reduction_factor
            self.logger.info(
                f"最近有长时间等待({self.last_long_wait_duration:.1f}秒)，"
                f"批次间隔从{original_interval}秒减少到{interval}秒"
            )

        # 如果启用自适应模式，根据已处理批次数动态调整间隔
        # 初始化变量，确保在任何情况下都有值
        needs_long_pause = False
        pause_time = 0

        if self.adaptive_batch:
            # 检查是否需要长暂停
            for threshold in self.long_pause_thresholds:
                if self.batch_count == threshold["batch"]:
                    # 如果最近有强制等待，减少长暂停时间
                    pause_time = threshold["pause"]
                    if time.time() - self.last_long_wait_time < 600:  # 10分钟内
                        pause_time = pause_time * 0.5  # 减少到一半
                        self.logger.warning(
                            f"{threshold['message']}(但由于最近有长等待，减半至{pause_time}秒)"
                        )
                    else:
                        self.logger.warning(threshold["message"])

                    delay_source = "batch_long_pause"
                    self._record_delay(delay_source, pause_time)
                    time.sleep(pause_time)
                    needs_long_pause = True
                    break

            # 如果需要长暂停，跳过普通间隔
            if needs_long_pause:
                self.batch_count += 1
                self.last_batch_time = time.time()
                return pause_time

            # 应用批次阈值调整 - 按降序检查，找到第一个匹配的阈值
            for batch_num, factor in sorted(self.batch_interval_thresholds.items(), reverse=True):
                if self.batch_count >= batch_num:
                    interval *= factor
                    break

        # 检查是否需要等待
        if elapsed < interval and self.last_batch_time > 0:
            wait_time = interval - elapsed

            # 根据间隔长度决定日志级别
            if wait_time > 60:
                self.logger.warning(f"批次{self.batch_count}后等待较长时间: {wait_time:.1f}秒")
            else:
                self.logger.info(f"批次{self.batch_count}后等待: {wait_time:.1f}秒")

            # 记录延迟来源
            self._record_delay(delay_source, wait_time)
            time.sleep(wait_time)

        # 更新计数和时间
        self.batch_count += 1
        self.last_batch_time = time.time()

        # 添加一些随机性，避免完全规律的请求模式
        # 降低概率和时间范围，避免过多的随机等待
        if random.random() < 0.15:  # 降低到15%概率
            extra_delay = random.uniform(0.5, 2.0)  # 降低上限
            self.logger.debug(f"添加额外随机延迟: {extra_delay:.1f}秒")
            time.sleep(extra_delay)
        return interval  # 返回实际应用的间隔，便于调试

    def reset_batch_count(self):
        """重置批次计数器

        将批次计数和时间重置为初始状态，用于开始新的批量处理任务。
        """
        self.batch_count = 0
        self.last_batch_time = 0
        self.logger.info("批次计数器已重置")

    def set_batch_interval(self, interval: float, adaptive: bool = True):
        """设置批次间隔和自适应模式

        Args:
            interval: 批次间隔时间(秒)
            adaptive: 是否启用自适应模式
        """
        self.batch_interval = interval
        self.adaptive_batch = adaptive
        self.logger.info(f"批次间隔已设置为{interval}秒，自适应模式: {adaptive}")

    def make_request(self, url: str, method: str = 'GET', params: Optional[Dict[str, Any]] = None,
                     data: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """发送HTTP请求

        执行HTTP请求，包含速率限制、重试逻辑和错误处理。

        Args:
            url: 请求URL
            method: HTTP方法(默认'GET')
            params: URL查询参数(可选)
            data: 请求体数据(可选)

        Returns:
            Dict: 响应JSON数据，失败时返回None
        """
        if not url:
            raise ValueError("URL cannot be empty")

        try:
            retry_count = 0
            while True:
                try:
                    # 等待请求间隔
                    self._wait_for_rate_limit()

                    # 发送请求
                    response = self.session.request(
                        method=method.upper(),
                        url=url,
                        params=params,
                        json=data,
                        timeout=self.timeout,
                        headers=self.headers
                    )

                    self.logger.info(f"请求: {method} {response.request.url}")

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

                        # 判断是否重试
                        should_retry, wait_time = self.retry_strategy.should_retry(
                            status_code=response.status_code,
                            retry_count=retry_count
                        )

                        if should_retry:
                            retry_count += 1
                            # 增加额外随机延迟
                            extra_delay = random.uniform(2.0, 5.0)  # 减少随机延迟上限
                            total_wait = wait_time + extra_delay
                            self.logger.info(f"等待{total_wait:.2f}秒后重试(第{retry_count}次)")
                            time.sleep(total_wait)
                            continue

                        response.raise_for_status()

                except requests.RequestException as e:
                    # 网络异常，增加连续失败计数
                    self._consecutive_failures += 1
                    self.logger.warning(f"请求异常，当前连续失败: {self._consecutive_failures}")

                    # 判断是否重试
                    should_retry, wait_time = self.retry_strategy.should_retry(
                        error=e,
                        retry_count=retry_count
                    )

                    if should_retry:
                        retry_count += 1
                        # 网络异常使用更长的等待时间
                        total_wait = wait_time + 3.0 * retry_count  # 降低乘数
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
        """发送HTTP请求并返回二进制响应内容

        适用于获取图片、文件等二进制数据的请求。

        Args:
            url: 请求URL
            method: HTTP方法(默认'GET')
            params: URL查询参数(可选)

        Returns:
            bytes: 二进制响应数据，失败时返回None
        """
        if not url:
            raise ValueError("URL cannot be empty")

        try:
            retry_count = 0
            while True:
                try:
                    # 等待请求间隔
                    self._wait_for_rate_limit()

                    # 发送请求
                    response = self.session.request(
                        method=method.upper(),
                        url=url,
                        params=params,
                        timeout=self.timeout,
                        headers=self.headers
                    )

                    # 添加完整URL日志记录（包含参数）
                    self.logger.info(f"二进制请求: {method} {response.request.url}")

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

                        # 判断是否重试
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

                    # 判断是否重试
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
        """关闭会话

        清理和释放资源，应在不再需要请求管理器时调用。
        """
        if self.session:
            try:
                self.session.close()
            except Exception as e:
                self.logger.error(f"关闭session失败: {str(e)}")

    def get_batch_stats(self):
        """获取批次处理统计信息

        返回当前批次处理的统计数据，用于监控和诊断。

        Returns:
            Dict: 批次处理统计信息
        """
        return {
            "batch_count": self.batch_count,
            "last_batch_time": self.last_batch_time,
            "batch_interval": self.batch_interval,
            "adaptive_mode": self.adaptive_batch,
            "total_requests": self.total_requests,
            "consecutive_failures": self._consecutive_failures,
            "session_age": self.session_age,
            "session_lifetime": time.time() - self.last_session_reset
        }

    def get_delay_stats(self):
        """获取延迟统计信息

        返回不同来源的延迟频率和时长统计，用于分析和优化策略。

        Returns:
            Dict: 延迟统计信息
        """
        # 计算不同来源的平均延迟时间
        delay_averages = {}
        for source in self.recent_delay_sources.keys():
            source_delays = [d["duration"] for d in self.recent_delays if d["source"] == source]
            if source_delays:
                delay_averages[source] = sum(source_delays) / len(source_delays)

        # 最近的长等待信息
        long_wait_info = None
        if self.last_long_wait_time > 0:
            long_wait_info = {
                "time": self.last_long_wait_time,
                "duration": self.last_long_wait_duration,
                "age": time.time() - self.last_long_wait_time
            }

        return {
            "delay_sources": self.recent_delay_sources,
            "delay_averages": delay_averages,
            "recent_force_wait": self.recent_force_wait,
            "post_force_wait_count": self.post_force_wait_count,
            "long_wait": long_wait_info
        }

    def set_retry_config(self, config: RetryConfig):
        """设置重试配置

        更新重试策略的配置参数。

        Args:
            config: 新的RetryConfig配置对象
        """
        self.retry_strategy.config = config
        self.logger.info("已更新重试配置")

    def adjust_request_rate(self, min_delay: float = None, max_delay: float = None,
                            min_interval: float = None):
        """调整请求速率参数

        更新控制请求频率的关键参数。

        Args:
            min_delay: 最小延迟时间(秒)(可选)
            max_delay: 最大延迟时间(秒)(可选)
            min_interval: 最小请求间隔(秒)(可选)
        """
        if min_delay is not None:
            self._min_delay = min_delay
        if max_delay is not None:
            self._max_delay = max_delay
        if min_interval is not None:
            self.min_request_interval = min_interval

        self.logger.info(f"请求速率参数已调整: min_delay={self._min_delay}, "
                         f"max_delay={self._max_delay}, min_interval={self.min_request_interval}")