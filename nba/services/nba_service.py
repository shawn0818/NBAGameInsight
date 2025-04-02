import time
from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
import functools
from contextlib import contextmanager
from typing import List, Optional, Dict, Any, Union, Set
from pathlib import Path

from database.db_service import DatabaseService
from nba.services.game_data_provider import GameDataProvider
from nba.services.game_data_adapter import GameDataAdapter
from nba.services.game_video_service import GameVideoService, VideoConfig
from nba.services.game_charts_service import GameChartsService, ChartConfig
from nba.models.video_model import ContextMeasure
from config import NBAConfig
from utils.logger_handler import AppLogger
from utils.video_converter import VideoProcessConfig, VideoProcessor


# ============1. 配置管理===============

@dataclass
class NBAServiceConfig:
    """NBA 服务主配置
    该类管理 NBA 服务的全局配置参数，包括默认球队、球员信息，以及缓存和刷新策略。

    Attributes:
        default_team (str): 默认关注的球队名称，用于未指定球队时的查询
        default_player (str): 默认关注的球员名称，用于未指定球员时的查询
        auto_refresh (bool): 是否启用自动刷新功能，用于实时更新数据
        cache_size (int): 缓存大小限制，范围必须在32到512之间
        base_output_dir (Path): 基础输出目录，默认使用配置中的目录
    """
    default_team: str = "Lakers"
    default_player: str = "LeBron James"
    auto_refresh: bool = False
    cache_size: int = 128
    base_output_dir: Path = NBAConfig.PATHS.STORAGE_DIR

    def __post_init__(self):
        """配置验证与初始化"""
        # 验证缓存大小
        if not (32 <= self.cache_size <= 512):
            raise ValueError("Cache size must be between 32 and 512")
        # 验证必填参数
        if not self.default_team:
            raise ValueError("default_team cannot be empty")
        if not self.default_player:
            raise ValueError("default_player cannot be empty")

        # 确保输出目录存在
        self.base_output_dir.mkdir(parents=True, exist_ok=True)

        # 确保子目录存在
        (self.base_output_dir / "videos" / "team_videos").mkdir(parents=True, exist_ok=True)
        (self.base_output_dir / "videos" / "player_videos").mkdir(parents=True, exist_ok=True)
        (self.base_output_dir / "pictures").mkdir(parents=True, exist_ok=True)
        (self.base_output_dir / "gifs").mkdir(parents=True, exist_ok=True)


# ========= 2. 服务基类==================

class InitializationError(Exception):
    """初始化失败异常"""
    pass


class ServiceError(Exception):
    """服务错误基类"""
    pass


class ServiceNotAvailableError(ServiceError):
    """服务不可用异常"""
    pass


class BaseService(ABC):
    """服务基类，提供通用功能，该类实现了基础的日志记录和错误处理功能，所有具体的服务类都应该继承此类。

    Attributes:
        config (Any): 服务配置对象
        logger (Logger): 日志记录器实例
    """

    def __init__(self, config: Any, logger_name: str = __name__):
        """初始化服务基类

        Args:
            config: 服务配置对象
            logger_name: 日志记录器名称，默认使用当前模块名
        """
        self.config = config
        self.logger = AppLogger.get_logger(logger_name, app_name='nba')

    def handle_error(self, error: Exception, context: str) -> None:
        """统一错误处理方法

        记录错误信息到日志，包括错误发生的上下文和完整的堆栈跟踪。

        Args:
            error: 异常对象
            context: 错误发生的上下文描述
        """
        if hasattr(self, 'logger'):
            self.logger.error(f"{context}: {str(error)}", exc_info=True)
        else:
            fallback_logger = AppLogger.get_logger(__name__, app_name='nba')
            fallback_logger.error(f"{context}: {str(error)}", exc_info=True)


# ===========3. 服务状态管理================

class ServiceStatus(Enum):
    """服务状态枚举"""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
    DEGRADED = "degraded"
    INITIALIZING = "initializing"
    RECOVERING = "recovering"


@dataclass
class ServiceHealth:
    """服务健康状态追踪类

    记录和管理服务的健康状态信息，包括当前状态、最后检查时间和错误信息。

    Attributes:
        status (ServiceStatus): 当前服务状态
        last_check (float): 最后一次状态检查的时间戳
        error_message (Optional[str]): 错误信息，仅在发生错误时存在
        recovery_attempts (int): 恢复尝试次数
        max_recovery_attempts (int): 最大恢复尝试次数
    """
    status: ServiceStatus
    last_check: float = field(default_factory=time.time)
    error_message: Optional[str] = None
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3

    @property
    def is_available(self) -> bool:
        """检查服务是否可用

        Returns:
            bool: 服务状态为AVAILABLE时返回True，否则返回False
        """
        return self.status == ServiceStatus.AVAILABLE

    @property
    def can_recover(self) -> bool:
        """检查服务是否可以恢复

        Returns:
            bool: 如果恢复尝试次数未达到最大值，返回True
        """
        return (self.status in [ServiceStatus.ERROR, ServiceStatus.UNAVAILABLE, ServiceStatus.DEGRADED] and
                self.recovery_attempts < self.max_recovery_attempts)

    def update_status(self, new_status: ServiceStatus, error_message: Optional[str] = None) -> None:
        """更新服务状态

        更新服务状态并刷新最后检查时间。如果提供了错误信息，则同时更新错误信息。

        Args:
            new_status: 新的服务状态
            error_message: 可选的错误信息
        """
        self.status = new_status
        self.last_check = time.time()

        if new_status == ServiceStatus.AVAILABLE:
            # 成功恢复，重置错误信息和恢复计数
            self.error_message = None
            self.recovery_attempts = 0
        elif new_status in [ServiceStatus.ERROR, ServiceStatus.UNAVAILABLE]:
            # 记录错误信息
            self.error_message = error_message

        if new_status == ServiceStatus.RECOVERING:
            # 增加恢复尝试计数
            self.recovery_attempts += 1


# 输入验证装饰器
def validate_input(**validators):
    """输入参数验证装饰器

    用于验证方法的输入参数是否符合预期

    Args:
        validators: 验证函数字典，键为参数名，值为验证函数

    Returns:
        装饰后的函数
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # 获取函数参数的名称
            import inspect
            sig = inspect.signature(func)
            bound_args = sig.bind(self, *args, **kwargs)
            bound_args.apply_defaults()

            # 验证参数
            for param_name, validator in validators.items():
                if param_name in bound_args.arguments:
                    value = bound_args.arguments[param_name]
                    if value is not None:  # 只验证非None的值
                        validator_result = validator(value)
                        if validator_result is not True:
                            error_msg = f"Invalid value for {param_name}: {validator_result}"
                            self.logger.error(error_msg)
                            raise ValueError(error_msg)

            # 调用原始函数
            return func(self, *args, **kwargs)

        return wrapper

    return decorator


# 常用验证函数
def validate_shot_outcome(value):
    """验证shot_outcome参数"""
    if value not in ["made_only", "all"]:
        return f"must be one of: made_only, all, got {value}"
    return True


def validate_impact_type(value):
    """验证impact_type参数"""
    if value not in ["scoring_only", "full_impact"]:
        return f"must be one of: scoring_only, full_impact, got {value}"
    return True


def validate_chart_type(value):
    """验证chart_type参数"""
    if value not in ["team", "player", "both"]:
        return f"must be one of: team, player, both, got {value}"
    return True


def validate_output_format(value):
    """验证output_format参数"""
    if value not in ["video", "gif", "both"]:
        return f"must be one of: video, gif, both, got {value}"
    return True


# =======4. NBA服务主类====================


class NBAService(BaseService):
    """NBA数据服务统一接口 - 重构版
    协调各个专业服务，为客户端提供统一的API访问点。
    简化后主要职责：服务管理、ID转换、基础查询和错误处理。
    """

    ## =======4.1 完成主服务以及子服务初始化 ====================

    def __init__(
            self,
            config: Optional[NBAServiceConfig] = None,
            video_config: Optional[VideoConfig] = None,
            chart_config: Optional[ChartConfig] = None,
            video_process_config: Optional[VideoProcessConfig] = None,
            env: str = "default",
            create_tables: bool = True
    ):
        """初始化NBA服务
        这是服务的主要入口点，负责初始化所有子服务和配置。
        采用依赖注入模式，允许自定义各个子服务的配置。

        Args:
            config: NBA服务主配置，控制全局行为
            video_config: 视频下载服务配置
            chart_config: 图表生成服务配置
            video_process_config: 视频合并转化gif配置
            env: 环境名称，可以是 "default", "test", "development", "production"
            create_tables: 是否创建数据表结构，默认为True
        """
        self.config = config or NBAServiceConfig()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        # 调用超类的__init__方法
        super().__init__(self.config, __name__)

        # 服务健康状态初始化
        self._services: Dict[str, Any] = {}
        self._service_status: Dict[str, ServiceHealth] = {}

        # 环境和表创建配置保存
        self.env = env
        self.create_tables = create_tables

        # 初始化服务
        self._init_all_services(
            video_config=video_config,
            chart_config=chart_config,
            video_process_config=video_process_config
        )

    def _init_all_services(
            self,
            video_config: Optional[VideoConfig] = None,
            chart_config: Optional[ChartConfig] = None,
            video_process_config: Optional[VideoProcessConfig] = None
    ) -> None:
        """初始化所有子服务

        按照依赖顺序初始化各个子服务：
        1. 数据库服务（核心服务，提供统一入口）
        2. 数据适配器服务
        3. 视频处理器
        4. 数据提供服务
        5. 图表服务
        6. 视频服务

        Args:
            video_config: 视频服务配置
            chart_config: 图表服务配置
            video_process_config: 视频处理器配置

        Raises:
            InitializationError: 当核心服务初始化失败时抛出
        """
        # 定义初始化服务列表 - 包含初始化顺序和依赖关系
        services_to_init = [
            {
                'name': 'db_service',
                'init_func': self._init_db_service,
                'args': {},
                'required': True,  # 核心服务，必须成功初始化
                'depends_on': []
            },
            {
                'name': 'adapter',
                'init_func': self._init_adapter_service,
                'args': {},
                'required': True,  # 核心服务，必须成功初始化
                'depends_on': ['db_service']
            },
            {
                'name': 'video_processor',
                'init_func': self._init_video_processor,
                'args': {'video_process_config': video_process_config},
                'required': False,  # 非核心服务，初始化失败不影响整体功能
                'depends_on': []
            },
            {
                'name': 'data',
                'init_func': self._init_data_service,
                'args': {},
                'required': True,  # 核心服务，必须成功初始化
                'depends_on': ['db_service', 'adapter']
            },
            {
                'name': 'chart',
                'init_func': self._init_chart_service,
                'args': {'chart_config': chart_config},
                'required': False,  # 非核心服务，初始化失败不影响整体功能
                'depends_on': ['data']
            },
            {
                'name': 'videodownloader',
                'init_func': self._init_video_service,
                'args': {'video_config': video_config, 'video_processor': 'video_processor'},
                'required': False,  # 非核心服务，初始化失败不影响整体功能
                'depends_on': ['data']
            }
        ]

        # 初始化所有服务
        failed_required_services = []
        for service_info in services_to_init:
            service_name = service_info['name']

            # 检查依赖服务是否初始化成功
            dependencies_ok = True
            for dep in service_info['depends_on']:
                if dep in failed_required_services or not self._service_status.get(dep, ServiceHealth(
                        ServiceStatus.UNAVAILABLE)).is_available:
                    dependencies_ok = False
                    self.logger.warning(f"服务 {service_name} 的依赖 {dep} 初始化失败，跳过初始化")
                    break

            if not dependencies_ok:
                # 依赖服务初始化失败，跳过当前服务
                if service_info['required']:
                    failed_required_services.append(service_name)
                self._update_service_status(service_name, ServiceStatus.UNAVAILABLE, f"依赖服务初始化失败")
                continue

            # 初始化当前服务
            try:
                self._update_service_status(service_name, ServiceStatus.INITIALIZING)

                # 处理可能的依赖注入 - 解析args中的字符串引用
                processed_args = {}
                for arg_name, arg_value in service_info['args'].items():
                    if isinstance(arg_value, str) and arg_value in self._services:
                        # 将服务名称替换为实际的服务实例
                        processed_args[arg_name] = self._services[arg_value]
                    else:
                        processed_args[arg_name] = arg_value

                success = service_info['init_func'](**processed_args)

                if success:
                    self._update_service_status(service_name, ServiceStatus.AVAILABLE)
                    self.logger.info(f"{service_name}服务初始化成功")
                else:
                    self._update_service_status(service_name, ServiceStatus.ERROR, f"初始化返回失败")
                    if service_info['required']:
                        failed_required_services.append(service_name)
                        self.logger.error(f"核心服务 {service_name} 初始化失败")
            except Exception as e:
                self.logger.error(f"{service_name}服务初始化失败: {str(e)}", exc_info=True)
                self._update_service_status(service_name, ServiceStatus.ERROR, str(e))
                if service_info['required']:
                    failed_required_services.append(service_name)

        # 检查是否有必需服务初始化失败
        if failed_required_services:
            error_msg = f"以下核心服务初始化失败: {', '.join(failed_required_services)}"
            self.logger.error(error_msg)
            raise InitializationError(error_msg)

    def _init_db_service(self) -> bool:
        """初始化数据库服务

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 创建数据库服务实例
            self._services['db_service'] = DatabaseService(env=self.env)

            # 初始化数据库连接
            db_init_success = self._services['db_service'].initialize(create_tables=self.create_tables)

            return db_init_success
        except Exception as e:
            self.logger.error(f"数据库服务初始化失败: {str(e)}", exc_info=True)
            raise  # 重新抛出异常，由调用者处理

    def _init_adapter_service(self) -> bool:
        """初始化数据适配器服务

        Returns:
            bool: 初始化是否成功
        """
        try:
            self._services['adapter'] = GameDataAdapter()
            return True
        except Exception as e:
            self.logger.error(f"数据适配器初始化失败: {str(e)}", exc_info=True)
            raise  # 重新抛出异常，由调用者处理

    def _init_video_processor(self, video_process_config: Optional[VideoProcessConfig] = None) -> bool:
        """初始化视频处理器

        Args:
            video_process_config: 视频处理配置

        Returns:
            bool: 初始化是否成功
        """
        try:
            self._services['video_processor'] = VideoProcessor(video_process_config)
            return True
        except Exception as e:
            self.logger.error(f"视频处理器初始化失败: {str(e)}", exc_info=True)
            return False  # 非核心服务，初始化失败不抛出异常

    def _init_data_service(self) -> bool:
        """初始化数据服务

        Returns:
            bool: 初始化是否成功
        """
        try:
            self._services['data'] = GameDataProvider()
            return True
        except Exception as e:
            self.logger.error(f"数据服务初始化失败: {str(e)}", exc_info=True)
            raise  # 重新抛出异常，由调用者处理

    def _init_chart_service(self, chart_config: Optional[ChartConfig] = None) -> bool:
        """初始化图表服务

        Args:
            chart_config: 图表配置

        Returns:
            bool: 初始化是否成功
        """
        try:
            self._services['chart'] = GameChartsService(chart_config or ChartConfig())
            return True
        except Exception as e:
            self.logger.error(f"图表服务初始化失败: {str(e)}", exc_info=True)
            return False  # 非核心服务，初始化失败不抛出异常

    def _init_video_service(self, video_config: Optional[VideoConfig] = None,
                            video_processor: Optional[VideoProcessor] = None) -> bool:
        """初始化视频服务

        Args:
            video_config: 视频配置
            video_processor: 视频处理器实例

        Returns:
            bool: 初始化是否成功
        """
        try:
            self._services['videodownloader'] = GameVideoService(
                video_config=video_config or VideoConfig(),
                video_processor=video_processor
            )
            return True
        except Exception as e:
            self.logger.error(f"视频下载服务初始化失败: {str(e)}", exc_info=True)
            return False  # 非核心服务，初始化失败不抛出异常

    @property
    def data_service(self) -> Optional[GameDataProvider]:
        """获取数据服务实例

        Returns:
            Optional[GameDataProvider]: 数据服务实例，如果服务不可用则返回None
        """
        return self._get_service('data')

    @property
    def adapter_service(self) -> Optional[GameDataAdapter]:
        """获取数据适配器服务实例

        Returns:
            Optional[GameDataAdapter]: 数据适配器实例，如果服务不可用则返回None
        """
        return self._get_service('adapter')

    @property
    def db_service(self) -> Optional[DatabaseService]:
        """获取数据库服务实例

        Returns:
            Optional[DatabaseService]: 数据库服务实例，如果服务不可用则返回None
        """
        return self._get_service('db_service')

    @property
    def chart_service(self) -> Optional[GameChartsService]:
        """获取图表服务实例

        Returns:
            Optional[GameChartsService]: 图表服务实例，如果服务不可用则返回None
        """
        return self._get_service('chart')

    @property
    def video_service(self) -> Optional[GameVideoService]:
        """获取视频服务实例

        Returns:
            Optional[GameVideoService]: 视频服务实例，如果服务不可用则返回None
        """
        return self._get_service('videodownloader')

    @property
    def video_processor(self) -> Optional[VideoProcessor]:
        """获取视频处理器实例

        Returns:
            Optional[VideoProcessor]: 视频处理器实例，如果服务不可用则返回None
        """
        return self._get_service('video_processor')

    @contextmanager
    def _ensure_service(self, name: str, auto_recover: bool = True) -> Any:
        """确保服务可用的上下文管理器

        Args:
            name: 服务名称
            auto_recover: 是否自动尝试恢复服务

        Yields:
            Any: 服务实例

        Raises:
            ServiceNotAvailableError: 如果服务不可用且无法恢复
        """
        service_health = self._service_status.get(name)

        if not service_health or not service_health.is_available:
            # 服务不可用，检查是否可以恢复
            if auto_recover and service_health and service_health.can_recover:
                self.logger.info(f"尝试恢复 {name} 服务...")
                self._update_service_status(name, ServiceStatus.RECOVERING)

                # 根据服务类型选择恢复方法
                recovery_success = False
                if name == 'db_service':
                    recovery_success = self._init_db_service()
                elif name == 'adapter':
                    recovery_success = self._init_adapter_service()
                elif name == 'data':
                    recovery_success = self._init_data_service()
                elif name == 'chart':
                    recovery_success = self._init_chart_service()
                elif name == 'videodownloader':
                    recovery_success = self._init_video_service()
                elif name == 'video_processor':
                    recovery_success = self._init_video_processor()

                if recovery_success:
                    self._update_service_status(name, ServiceStatus.AVAILABLE)
                    self.logger.info(f"{name} 服务恢复成功")
                else:
                    error_msg = f"{name} 服务无法恢复"
                    self._update_service_status(name, ServiceStatus.ERROR, error_msg)
                    self.logger.error(error_msg)
                    raise ServiceNotAvailableError(error_msg)
            else:
                # 无法恢复
                error_msg = f"{name} 服务不可用"
                if service_health and service_health.error_message:
                    error_msg += f": {service_health.error_message}"
                self.logger.error(error_msg)
                raise ServiceNotAvailableError(error_msg)

        try:
            yield self._services.get(name)
        except Exception as e:
            # 发生异常，标记服务状态
            self._update_service_status(name, ServiceStatus.ERROR, str(e))
            self.logger.error(f"{name} 服务发生错误: {str(e)}", exc_info=True)
            raise

    def _update_service_status(self,
                               service_name: str,
                               status: ServiceStatus,
                               error_message: Optional[str] = None) -> None:
        """更新服务状态信息

        更新指定服务的状态记录，包括状态、最后检查时间和错误信息。

        Args:
            service_name: 服务名称
            status: 新的服务状态
            error_message: 错误信息（如果有）
        """
        # 获取现有状态或创建新状态
        existing_health = self._service_status.get(service_name)

        if existing_health:
            # 更新现有状态
            existing_health.update_status(status, error_message)
        else:
            # 创建新状态
            self._service_status[service_name] = ServiceHealth(
                status=status,
                last_check=time.time(),
                error_message=error_message
            )

    def _get_service(self, name: str) -> Optional[Any]:
        """安全地获取服务实例

        检查服务可用性并返回服务实例。如果服务不可用，
        返回None并记录错误日志。

        Args:
            name: 要获取的服务名称

        Returns:
            服务实例或None（如果服务不可用）
        """
        service_health = self._service_status.get(name)

        if not service_health:
            self.logger.error(f"服务 {name} 不存在")
            return None

        if not service_health.is_available:
            error_detail = f": {service_health.error_message}" if service_health.error_message else ""
            self.logger.error(f"服务 {name} 不可用{error_detail}")
            return None

        return self._services.get(name)

    ## =======4.2 基础数据查询API ====================

    def get_game(self, team: Optional[str] = None, date: Optional[str] = "last", force_update: bool = False) -> \
            Optional[Any]:
        """获取比赛数据

        Args:
            team: 球队名称
            date: 日期字符串，默认获取最近一场比赛
            force_update: 是否强制更新

        Returns:
            Optional[Any]: 比赛数据对象
        """
        try:
            # 使用默认球队，如果未提供
            team_name = team or self.config.default_team
            self.logger.info(f"尝试获取球队 {team_name} 的比赛数据，日期参数: {date}")

            # 使用上下文管理器确保服务可用
            with self._ensure_service('db_service') as db_service:
                # 获取team_id
                team_id = db_service.get_team_id_by_name(team_name)
                if not team_id:
                    self.logger.error(f"未找到球队: {team_name}")
                    return None

                self.logger.info(f"获取到球队ID: {team_id}")

                # 获取game_id
                game_id = db_service.get_game_id(team_id, date)
                if not game_id:
                    self.logger.error(f"未找到比赛ID，球队: {team_name}, 日期: {date}")
                    return None

                self.logger.info(f"获取到比赛ID: {game_id}")

            # 使用game_id获取比赛数据
            with self._ensure_service('data') as data_service:
                game = data_service.get_game(game_id, force_update=force_update)
                if not game:
                    self.logger.error(f"未找到比赛数据，比赛ID: {game_id}")
                    return None

                return game

        except ServiceNotAvailableError as e:
            self.logger.error(f"获取比赛数据失败: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"获取比赛数据失败: {str(e)}", exc_info=True)
            return None

    def get_team_id_by_name(self, team_name: str) -> Optional[int]:
        """获取球队ID

        基础API：将球队名称转换为系统内部使用的唯一ID。
        此方法是多数功能的基础，用于标识和查询球队相关信息。

        Args:
            team_name: 球队名称

        Returns:
            Optional[int]: 球队ID，如果未找到则返回None
        """
        try:
            with self._ensure_service('db_service') as db_service:
                return db_service.get_team_id_by_name(team_name)
        except ServiceNotAvailableError:
            self.logger.error("获取球队ID失败: 数据库服务不可用")
            return None
        except Exception as e:
            self.logger.error(f"获取球队ID失败: {str(e)}", exc_info=True)
            return None

    def get_player_id_by_name(self, player_name: str) -> Optional[Union[int, List[int]]]:
        """获取球员ID

        基础API：将球员名称转换为系统内部使用的唯一ID。
        此方法是多数球员相关功能的基础，用于标识和查询球员信息。

        Args:
            player_name: 球员名称

        Returns:
            Optional[Union[int, List[int]]]: 球员ID或ID列表，如果未找到则返回None
        """
        try:
            with self._ensure_service('db_service') as db_service:
                return db_service.get_player_id_by_name(player_name)
        except ServiceNotAvailableError:
            self.logger.error("获取球员ID失败: 数据库服务不可用")
            return None
        except Exception as e:
            self.logger.error(f"获取球员ID失败: {str(e)}", exc_info=True)
            return None

    def sync_remaining_data_parallel(self, force_update: bool = False, max_workers: int = 2,
                                     batch_size: int = 6, reverse_order: bool = False) -> Dict[str, Any]:
        """并行增量同步剩余未同步的比赛统计数据 (gamedb)

        这是日常/手动更新比赛统计数据的主要方法。

        Args:
            force_update: 是否强制更新已同步过的数据。
            max_workers: 最大工作线程数。
            batch_size: 每批处理的比赛数量。
            reverse_order: 是否优先处理最新的比赛。

        Returns:
            Dict[str, Any]: 同步结果摘要。
        """
        try:
            with self._ensure_service('db_service') as db_service:
                # Directly call the corresponding method in DatabaseService
                return db_service.sync_remaining_data_parallel(
                    force_update=force_update,
                    max_workers=max_workers,
                    batch_size=batch_size,
                    reverse_order=reverse_order
                )
        except ServiceNotAvailableError as e:
            self.logger.error(f"并行增量同步数据失败: {str(e)}")
            return {"status": "failed", "error": str(e)}
        except Exception as e:
            self.logger.error(f"并行增量同步数据失败: {str(e)}", exc_info=True)
            return {"status": "failed", "error": str(e)}

    def sync_new_season_core_data(self, force_update: bool = True) -> Dict[str, Any]:
        """同步新赛季的核心数据 (nba.db)

        用于赛季开始时，强制更新球队、球员信息，并同步当前赛季的赛程。

        Args:
            force_update: 是否强制更新，对于新赛季同步，通常应为True。

        Returns:
            Dict[str, Any]: 同步结果摘要。
        """
        try:
            with self._ensure_service('db_service') as db_service:
                # Directly call the corresponding method in DatabaseService
                return db_service.sync_new_season_core_data(force_update=force_update)
        except ServiceNotAvailableError as e:
            self.logger.error(f"同步新赛季核心数据失败: {str(e)}")
            return {"status": "failed", "error": str(e)}
        except Exception as e:
            self.logger.error(f"同步新赛季核心数据失败: {str(e)}", exc_info=True)
            return {"status": "failed", "error": str(e)}

    ## =============4.3 简化的API，委托到各专业服务=================

    @validate_input(impact_type=validate_impact_type)
    def generate_player_scoring_impact_charts(self,
                                              player_name: str,
                                              team: Optional[str] = None,
                                              output_dir: Optional[Path] = None,
                                              force_reprocess: bool = False,
                                              impact_type: str = "full_impact") -> Dict[str, Path]:
        """生成球员得分影响力图 - 委托给图表服务

        Args:
            player_name: 球员名称
            team: 球队名称，不提供则使用默认球队
            output_dir: 输出目录，默认使用配置中的图片目录
            force_reprocess: 是否强制重新处理已存在的文件
            impact_type: 图表类型，可选 "scoring_only"(仅显示球员自己的投篮)
                        或 "full_impact"(同时显示球员投篮和助攻队友投篮)

        Returns:
            Dict[str, Path]: 图表路径字典，键包含"impact_chart"或"scoring_chart"
        """
        try:
            # 获取必要的ID和数据
            player_name = player_name or self.config.default_player
            team = team or self.config.default_team

            # 获取球员ID
            player_id = self.get_player_id_by_name(player_name)
            if not player_id:
                self.logger.error(f"未找到球员: {player_name}")
                return {}

            # 获取比赛数据
            game = self.get_game(team)
            if not game:
                self.logger.error(f"未找到{team}的比赛数据")
                return {}

            # 调用图表服务
            with self._ensure_service('chart') as chart_service:
                return chart_service.generate_player_scoring_impact_charts(
                    game=game,
                    player_id=player_id,
                    player_name=player_name,
                    output_dir=output_dir,
                    force_reprocess=force_reprocess,
                    impact_type=impact_type
                )
        except ServiceNotAvailableError as e:
            self.logger.error(f"图表服务不可用: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"生成球员图表失败: {e}", exc_info=True)
            return {}

    @validate_input(
        chart_type=validate_chart_type,
        shot_outcome=validate_shot_outcome,
        impact_type=validate_impact_type
    )
    def generate_shot_charts(self,
                             team: Optional[str] = None,
                             player_name: Optional[str] = None,
                             chart_type: str = "both",  # "team", "player", "both"
                             output_dir: Optional[Path] = None,
                             force_reprocess: bool = False,
                             shot_outcome: str = "made_only",  # "made_only", "all"
                             impact_type: str = "full_impact") -> Dict[str, Path]:
        """生成投篮分布图 - 委托给图表服务"""
        try:
            # 获取基础数据
            team = team or self.config.default_team
            if (chart_type in ["player", "both"]) and not player_name:
                player_name = self.config.default_player

            # 获取相关ID
            team_id = self.get_team_id_by_name(team)
            if not team_id:
                self.logger.error(f"未找到球队: {team}")
                return {}

            player_id = None
            if player_name:
                player_id = self.get_player_id_by_name(player_name)
                if not player_id and chart_type in ["player", "both"]:
                    self.logger.error(f"未找到球员: {player_name}")
                    return {}

            # 获取比赛数据
            game = self.get_game(team)
            if not game:
                self.logger.error(f"未找到{team}的比赛数据")
                return {}

            # 调用图表服务
            with self._ensure_service('chart') as chart_service:
                return chart_service.generate_shot_charts(
                    game=game,
                    team_id=team_id,
                    player_id=player_id,
                    team_name=team,
                    player_name=player_name,
                    chart_type=chart_type,
                    output_dir=output_dir,
                    force_reprocess=force_reprocess,
                    shot_outcome=shot_outcome,
                    impact_type=impact_type
                )
        except ServiceNotAvailableError as e:
            self.logger.error(f"图表服务不可用: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"生成投篮图失败: {e}", exc_info=True)
            return {}

    def get_team_highlights(self, team: Optional[str] = None, merge: bool = True,
                            output_dir: Optional[Path] = None, force_reprocess: bool = False) -> Dict[str, Path]:
        """获取球队集锦视频 - 委托给视频服务

        Args:
            team: 球队名称，不提供则使用默认球队
            merge: 是否合并视频
            output_dir: 输出目录，不提供则创建规范化目录
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Path]: 视频路径字典
        """
        try:
            # 获取必要的ID和数据
            team = team or self.config.default_team

            # 获取球队ID
            team_id = self.get_team_id_by_name(team)
            if not team_id:
                self.logger.error(f"未找到球队: {team}")
                return {}

            # 获取比赛数据
            game = self.get_game(team)
            if not game:
                self.logger.error(f"未找到{team}的比赛数据")
                return {}

            # 调用视频服务
            with self._ensure_service('videodownloader') as video_service:
                return video_service.get_team_highlights(
                    team_id=team_id,
                    game_id=game.game_data.game_id,
                    merge=merge,
                    output_dir=output_dir,
                    force_reprocess=force_reprocess
                )
        except ServiceNotAvailableError as e:
            self.logger.error(f"视频服务不可用: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"获取球队集锦失败: {e}", exc_info=True)
            return {}

    @validate_input(output_format=validate_output_format)
    def get_player_highlights(self,
                              player_name: Optional[str] = None,
                              context_measures: Optional[Set[ContextMeasure]] = None,
                              output_format: str = "both",  # "video", "gif", "both"
                              merge: bool = True,
                              output_dir: Optional[Path] = None,
                              keep_originals: bool = True,
                              request_delay: float = 1.0,
                              force_reprocess: bool = False) -> Dict[str, Any]:
        """获取球员集锦视频和GIF - 委托给视频服务

        Args:
            player_name: 球员名称，不提供则使用默认球员
            context_measures: 上下文度量集合，如{FGM, AST}
            output_format: 输出格式，可选 "video"(仅视频), "gif"(仅GIF), "both"(视频和GIF)
            merge: 是否合并视频
            output_dir: 输出目录，不提供则创建规范化目录
            keep_originals: 是否保留原始短视频
            request_delay: 请求间隔时间(秒)
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Any]: 处理结果路径字典
        """
        try:
            # 获取必要的ID和数据
            player_name = player_name or self.config.default_player

            # 获取球员ID
            player_id = self.get_player_id_by_name(player_name)
            if not player_id:
                self.logger.error(f"未找到球员: {player_name}")
                return {}

            # 获取比赛数据
            game = self.get_game(self.config.default_team)
            if not game:
                self.logger.error(f"未找到比赛数据")
                return {}

            # 调用视频服务
            with self._ensure_service('videodownloader') as video_service:
                return video_service.get_player_highlights(
                    player_id=player_id,
                    game_id=game.game_data.game_id,
                    context_measures=context_measures,
                    output_format=output_format,
                    merge=merge,
                    output_dir=output_dir,
                    keep_originals=keep_originals,
                    request_delay=request_delay,
                    force_reprocess=force_reprocess
                )
        except ServiceNotAvailableError as e:
            self.logger.error(f"视频服务不可用: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"获取球员集锦失败: {e}", exc_info=True)
            return {}

    def get_player_round_gifs(self, player_name: Optional[str] = None,
                              force_reprocess: bool = False) -> Dict[str, Path]:
        """从球员集锦视频创建每个回合的GIF动画 - 委托给视频服务

        Args:
            player_name: 球员名称，不提供则使用默认球员
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Path]: GIF路径字典，以事件ID为键
        """
        try:
            # 获取必要的ID和数据
            player_name = player_name or self.config.default_player

            # 获取球员ID
            player_id = self.get_player_id_by_name(player_name)
            if not player_id:
                self.logger.error(f"未找到球员: {player_name}")
                return {}

            # 获取比赛数据
            game = self.get_game(self.config.default_team)
            if not game:
                self.logger.error(f"未找到比赛数据")
                return {}

            # 调用视频服务
            with self._ensure_service('videodownloader') as video_service:
                return video_service.get_player_round_gifs(
                    player_id=player_id,
                    game_id=game.game_data.game_id,
                    force_reprocess=force_reprocess
                )
        except ServiceNotAvailableError as e:
            self.logger.error(f"视频服务不可用: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"获取球员回合GIF失败: {e}", exc_info=True)
            return {}

    ## 4.4资源管理 ==============
    def clear_cache(self) -> None:
        """清理所有服务的缓存"""
        for service_name, service in self._services.items():
            try:
                if hasattr(service, 'clear_cache'):
                    service.clear_cache()
                    self.logger.info(f"已清理 {service_name} 服务缓存")
            except Exception as e:
                self.logger.error(f"清理 {service_name} 服务缓存失败: {str(e)}")

    def close(self) -> None:
        """关闭服务并清理资源"""
        self.clear_cache()

        # 定义关闭顺序 - 先关闭高级服务，再关闭基础服务（依赖倒序）
        closing_order = [
            'videodownloader',  # 先关闭视频服务
            'chart',  # 再关闭图表服务
            'video_processor',  # 关闭视频处理器
            'data',  # 关闭数据服务
            'adapter',  # 关闭适配器
            'db_service'  # 最后关闭数据库服务
        ]

        # 按顺序关闭服务
        for service_name in closing_order:
            service = self._services.get(service_name)
            if service:
                try:
                    if hasattr(service, 'close'):
                        service.close()
                        self.logger.info(f"{service_name}服务已关闭")
                except Exception as e:
                    self.logger.error(f"关闭{service_name}服务失败: {str(e)}")

    def __enter__(self) -> 'NBAService':
        """上下文管理器入口

        实现上下文管理器协议，支持 with 语句使用。

        Returns:
            NBAService: 服务实例本身

        Example:
            with NBAService() as service:
                service.get_game_videos()
        """
        return self

    def __exit__(
            self,
            exc_type: Optional[type],
            exc_val: Optional[Exception],
            exc_tb: Optional[Any]
    ) -> None:
        """上下文管理器出口

        在退出上下文时自动清理资源。

        Args:
            exc_type: 异常类型（如果发生）
            exc_val: 异常值（如果发生）
            exc_tb: 异常回溯（如果发生）
        """
        self.close()

    def restart_service(self, service_name: str) -> bool:
        """手动重启指定服务

        Args:
            service_name: 服务名称

        Returns:
            bool: 重启是否成功
        """
        self.logger.info(f"正在手动重启服务: {service_name}")

        # 先关闭服务
        service = self._services.get(service_name)
        if service and hasattr(service, 'close'):
            try:
                service.close()
            except Exception as e:
                self.logger.warning(f"关闭服务 {service_name} 失败: {e}")

        # 重新初始化服务
        try:
            if service_name == 'db_service':
                success = self._init_db_service()
            elif service_name == 'adapter':
                success = self._init_adapter_service()
            elif service_name == 'data':
                success = self._init_data_service()
            elif service_name == 'chart':
                success = self._init_chart_service()
            elif service_name == 'videodownloader':
                success = self._init_video_service()
            elif service_name == 'video_processor':
                success = self._init_video_processor()
            else:
                self.logger.error(f"未知服务: {service_name}")
                return False

            if success:
                self._update_service_status(service_name, ServiceStatus.AVAILABLE)
                self.logger.info(f"服务 {service_name} 重启成功")
                return True
            else:
                self._update_service_status(service_name, ServiceStatus.ERROR, "重启失败")
                self.logger.error(f"服务 {service_name} 重启失败")
                return False

        except Exception as e:
            self._update_service_status(service_name, ServiceStatus.ERROR, str(e))
            self.logger.error(f"重启服务 {service_name} 失败: {e}", exc_info=True)
            return False

    def check_services_health(self) -> Dict[str, Dict[str, Any]]:
        """检查所有服务的健康状态

        Returns:
            Dict[str, Dict[str, Any]]: 服务健康状态报告
        """
        result = {}

        for name, health in self._service_status.items():
            result[name] = {
                "status": health.status.value,
                "is_available": health.is_available,
                "last_check": health.last_check,
                "recovery_attempts": health.recovery_attempts,
                "error": health.error_message
            }

        return result