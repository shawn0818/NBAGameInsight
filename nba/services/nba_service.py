# nba/services/nba_service.py
from abc import ABC
from typing import Optional, Dict, Any, List, Union, Type, Set
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import time

from nba.services.game_data_service import GameDataProvider, InitializationError, GameDataConfig
from nba.services.game_video_service import GameVideoService, VideoConfig
from nba.services.game_charts_service import GameChartsService, ChartConfig
from nba.models.video_model import ContextMeasure, VideoAsset
from config.nba_config import NBAConfig
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
        date_str (str): 日期字符串，默认为"last"表示最近一场比赛
        cache_size (int): 缓存大小限制，范围必须在32到512之间
        auto_refresh (bool): 是否启用自动刷新功能，用于实时更新数据
    """
    default_team: str = "Lakers"
    default_player: str = "LeBron James"
    date_str: str = "last"
    cache_size: int = 128
    auto_refresh: bool = False

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
        if not self.date_str:
            raise ValueError("date_str cannot be empty")


# ========= 2. 服务基类==================

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


@dataclass
class ServiceHealth:
    """服务健康状态追踪类

    记录和管理服务的健康状态信息，包括当前状态、最后检查时间和错误信息。

    Attributes:
        status (ServiceStatus): 当前服务状态
        last_check (float): 最后一次状态检查的时间戳
        error_message (Optional[str]): 错误信息，仅在发生错误时存在
    """
    status: ServiceStatus
    last_check: float = field(default_factory=time.time)
    error_message: Optional[str] = None

    @property
    def is_available(self) -> bool:
        """检查服务是否可用

        Returns:
            bool: 服务状态为AVAILABLE时返回True，否则返回False
        """
        return self.status == ServiceStatus.AVAILABLE
    
    def update_status(self, new_status: ServiceStatus, error_message: Optional[str] = None) -> None:
        """更新服务状态
        
        更新服务状态并刷新最后检查时间。如果提供了错误信息，则同时更新错误信息。
        
        Args:
            new_status: 新的服务状态
            error_message: 可选的错误信息
        """
        self.status = new_status
        self.last_check = time.time()
        self.error_message = error_message


# =======4. NBA服务主类====================


class NBAService(BaseService):
    """NBA数据服务统一接口
    这是NBA服务的主类，整合了数据查询、视频处理、图表生成等多个子服务。
    该类采用组合模式，将各个子服务组织在一起，提供统一的访问接口。
    """

    ## =======4.1 完成主服务以及子服务初始化 ====================

    def __init__(
            self,
            config: Optional[NBAServiceConfig] = None,
            data_config: Optional[GameDataConfig] = None,
            video_config: Optional[VideoConfig] = None,
            chart_config: Optional[ChartConfig] = None,
            video_process_config: Optional[VideoProcessConfig] = None
    ):
        """初始化NBA服务
        这是服务的主要入口点，负责初始化所有子服务和配置。
        采用依赖注入模式，允许自定义各个子服务的配置。

        Args:
            config: NBA服务主配置，控制全局行为
            data_config: 比赛数据服务配置
            video_config: 视频下载服务配置
            chart_config: 图表生成服务配置
            video_process_config:视频合并转化gif配置

        初始化流程：
        1. 设置基础配置和日志
        2. 初始化服务状态追踪
        3. 按照依赖顺序初始化各个子服务
        4. 设置服务健康检查

        注意：
        - 如果未提供配置，将使用默认配置
        - 服务初始化失败会记录到日志但不会立即抛出异常
        - AI服务是可选的，其他核心服务是必需的
        """
        self.config = config or NBAServiceConfig()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        # 调用超类的__init__方法
        super().__init__(self.config, __name__)

        # 服务健康状态初始化
        self._services: Dict[str, Any] = {}
        self._service_status: Dict[str, ServiceHealth] = {}

        # 初始化服务
        self._init_all_services(
            data_config=data_config,
            video_config=video_config,
            chart_config=chart_config,
            video_process_config=video_process_config
        )

    def _init_all_services(
            self,
            data_config: Optional[GameDataConfig] = None,
            video_config: Optional[VideoConfig] = None,
            chart_config: Optional[ChartConfig] = None,
            video_process_config: Optional[VideoProcessConfig] = None
    ) -> None:
        """初始化所有子服务

        按照特定的顺序和依赖关系初始化各个子服务。

        初始化顺序：
        1. 数据服务（核心服务）
        2. 图表服务
        3. 视频服务

        服务依赖关系：
        - 所有服务都依赖于数据服务

        Args:
            data_config: 数据服务配置
            video_config: 视频服务配置
            chart_config: 图表服务配置

        Raises:
            InitializationError: 当核心服务初始化失败时抛出
        """
        try:

            # 初始化GameData服务配置（核心服务）
            data_config = data_config or GameDataConfig(
                default_team=self.config.default_team,
                default_player=self.config.default_player,
                date_str=self.config.date_str,
                cache_size=self.config.cache_size,
                auto_refresh=self.config.auto_refresh
            )

            #初始化视频下载配置
            video_config = video_config or VideoConfig()

            #初始化chartservice配置
            chart_config = chart_config or ChartConfig()

            # 初始化视频合并转化处理器
            if video_process_config:
                self._services['video_processor'] = VideoProcessor(video_process_config)
                self._update_service_status('video_processor', ServiceStatus.AVAILABLE)

            # 服务初始化映射
            service_configs = {
                'data': (GameDataProvider, data_config),
                'chart': (GameChartsService, chart_config),
                'videodownloader': (GameVideoService, video_config),
                'video_processor': (VideoProcessor, video_process_config)
            }

            # 按照预定义顺序初始化服务
            for service_name, (service_class, service_config) in service_configs.items():
                self._init_service(service_name, service_class, service_config)

        except Exception as e:
            self.logger.error(f"服务初始化失败: {str(e)}")
            raise InitializationError(f"服务初始化失败: {str(e)}")


    @property
    def data_service(self) -> Optional[GameDataProvider]:
        """获取数据服务实例
        
        Returns:
            Optional[GameDataProvider]: 数据服务实例，如果服务不可用则返回None
        """
        return self._get_service('data')


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


    def _init_service(self,
                      name: str,
                      service_class: Type,
                      service_config: Any) -> None:
        """单个服务的初始化方法

        负责初始化单个服务并更新其状态。
        Args:
            name: 服务名称
            service_class: 服务类
            service_config: 服务配置对象

        注意：
            - 初始化失败会被记录但不会阻止其他服务的初始化
            - AI服务是可选的，其他服务初始化失败会被记录为错误状态
        """
        try:
            # 处理不需要配置的服务
            if service_config is None :
                self._services[name] = service_class()
            else:
                self._services[name] = service_class(service_config)

            self._update_service_status(name, ServiceStatus.AVAILABLE)

        except Exception as e:
            self.logger.error(f"{name}服务初始化失败: {str(e)}")
            self._update_service_status(name, ServiceStatus.ERROR, str(e))

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
        if not self._service_status.get(name, ServiceHealth(ServiceStatus.UNAVAILABLE)).is_available:
            self.logger.error(f"{name}服务不可用")
            return None
        return self._services.get(name)

    ## =======4.2 基础数据查询API ====================

    def get_team_id_by_name(self, team_name: str) -> Optional[int]:
        """获取球队ID

        基础API：将球队名称转换为系统内部使用的唯一ID。
        此方法是多数功能的基础，用于标识和查询球队相关信息。

        Args:
            team_name: 球队名称

        Returns:
            Optional[int]: 球队ID，如果未找到则返回None
        """
        data_service = self._get_service('data')
        if not data_service:
            return None

        try:
            return data_service.league_provider.get_team_id_by_name(team_name)
        except Exception as e:
            self.logger.error(f"获取球队ID失败: {str(e)}")
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
        data_service = self._get_service('data')
        if not data_service:
            return None

        try:
            return data_service.league_provider.get_player_id_by_name(player_name)
        except Exception as e:
            self.logger.error(f"获取球员ID失败: {str(e)}")
            return None

    def get_events_timeline(self, team: Optional[str] = None, player_name: Optional[str] = None) -> List[
        Dict[str, Any]]:
        """获取比赛事件时间线并进行分类

        提取比赛中的关键事件，可按球员或球队筛选。
        这是对底层Game模型的events功能的简单封装。

        Args:
            team: 球队名称，不提供则使用默认球队
            player_name: 可选的球员名称，用于筛选特定球员的事件

        Returns:
            List[Dict[str, Any]]: 事件列表，如果获取失败则返回空列表
        """
        try:
            team = team or self.config.default_team
            data_service = self._get_service('data')
            if not data_service:
                self.logger.error("数据服务不可用")
                return []

            game_data = data_service.get_game(team)
            if not game_data:
                self.logger.error(f"获取比赛信息失败: 未找到{team}的比赛数据")
                return []

            # 如果指定了球员名称，则获取球员ID
            player_id = None
            if player_name:
                player_id = self.get_player_id_by_name(player_name)
                if not player_id:
                    self.logger.warning(f"未找到球员 {player_name} 的ID")
                    return []

            # 直接使用Game模型的events筛选功能
            events_data = game_data.prepare_ai_data(player_id)["events"]["data"]

            return events_data

        except Exception as e:
            self.handle_error(e, "获取事件时间线")
            return []

    ## =============4.3 调用个各子模块服务=================

    ### 4.3.1视频功能API，调用gamevideo子模块==============
    def get_team_highlights(self,
                            team: Optional[str] = None,
                            merge: bool = True,
                            output_dir: Optional[Path] = None,
                            force_reprocess: bool = False) -> Dict[str, Path]:
        """获取球队集锦视频

        下载并处理指定球队的比赛集锦。默认会合并视频、去除水印并删除原始短视频。

        Args:
            team: 球队名称，不提供则使用默认球队
            merge: 是否合并视频
            output_dir: 输出目录，不提供则创建规范化目录
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Path]: 视频路径字典
        """
        try:
            # 获取基础信息
            team = team or self.config.default_team
            team_id = self.get_team_id_by_name(team)
            if not team_id:
                self.logger.error(f"未找到球队: {team}")
                return {}

            game = self.data_service.get_game(team)
            if not game:
                self.logger.error(f"未找到{team}的比赛数据")
                return {}

            # 创建球队特定的视频目录
            game_id = game.game_data.game_id
            if not output_dir:
                team_video_dir = NBAConfig.PATHS.VIDEO_DIR / "team_videos" / f"team_{team_id}_{game_id}"
                team_video_dir.mkdir(parents=True, exist_ok=True)
                output_dir = team_video_dir

            # 获取视频服务
            video_service = self._get_service('videodownloader')
            if not video_service:
                self.logger.error("视频服务不可用")
                return {}

            # 获取视频资产
            videos = video_service.get_game_videos(
                game_id=game_id,
                team_id=team_id,
                context_measure=ContextMeasure.FGM
            )
            if not videos:
                self.logger.error(f"未找到{team}的集锦视频")
                return {}

            # 使用内部处理方法
            result = self._process_videos(
                game_id=game_id,
                videos=videos,
                output_dir=output_dir,
                output_prefix=f"team_{team_id}",
                output_format="video",  # 只需要视频
                merge=merge,
                remove_watermark=True,
                keep_originals=False,  # 不保留原始短视频
                force_reprocess=force_reprocess
            )

            # 简化返回结果结构
            if "video_merged" in result:
                return {"merged": result["video_merged"]}
            elif "videos" in result:
                return result["videos"]
            return {}

        except Exception as e:
            self.logger.error(f"获取球队集锦失败: {str(e)}", exc_info=True)
            return {}

    def get_player_highlights(self,
                              player_name: Optional[str] = None,
                              context_measures: Optional[Set[ContextMeasure]] = None,
                              output_format: str = "both",  # "video", "gif", "both"
                              merge: bool = True,
                              output_dir: Optional[Path] = None,
                              keep_originals: bool = True,
                              request_delay: float = 1.0,
                              force_reprocess: bool = False) -> Dict[str, Any]:
        """获取球员集锦视频和GIF

        下载并处理指定球员的比赛集锦。默认会同时生成视频和GIF，并保留原始短视频。

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
        import time

        try:
            # 获取基础信息
            player_name = player_name or self.config.default_player
            player_id = self.get_player_id_by_name(player_name)
            if not player_id:
                self.logger.error(f"未找到球员: {player_name}")
                return {}

            game = self.data_service.get_game(self.config.default_team)
            if not game:
                self.logger.error("未找到比赛数据")
                return {}

            # 创建球员特定的视频目录
            game_id = game.game_data.game_id
            if not output_dir:
                player_video_dir = NBAConfig.PATHS.VIDEO_DIR / "player_videos" / f"player_{player_id}_{game_id}"
                player_video_dir.mkdir(parents=True, exist_ok=True)
                output_dir = player_video_dir

            # 获取视频服务
            video_service = self._get_service('videodownloader')
            if not video_service:
                self.logger.error("视频服务不可用")
                return {}

            # 确定要获取的视频类型
            if context_measures is None:
                context_measures = {
                    ContextMeasure.FGM,
                    ContextMeasure.AST,
                    ContextMeasure.REB,
                    ContextMeasure.STL
                }

            # 获取并处理各类型视频
            all_videos = {}

            for measure in context_measures:
                # 获取视频资源
                videos = video_service.get_game_videos(
                    game_id=game.game_data.game_id,
                    player_id=player_id,
                    context_measure=measure
                )

                if videos:
                    all_videos.update(videos)

                    # 添加请求间隔
                    if request_delay > 0:
                        time.sleep(request_delay)
                        self.logger.info(f"等待 {request_delay} 秒后继续...")

            # 如果找到视频，处理它们
            if all_videos:
                result = self._process_videos(
                    game_id=game.game_data.game_id,
                    videos=all_videos,
                    output_dir=output_dir,
                    output_prefix=f"player_{player_id}",
                    output_format=output_format,
                    merge=merge,
                    remove_watermark=True,
                    keep_originals=keep_originals,
                    force_reprocess=force_reprocess
                )

                return result
            else:
                self.logger.error(f"未找到球员{player_name}的任何集锦视频")
                return {}

        except Exception as e:
            self.logger.error(f"获取球员集锦失败: {str(e)}", exc_info=True)
            return {}

    def create_player_round_gifs(self, player_name: Optional[str] = None) -> Dict[str, Path]:
        """从球员集锦视频创建每个回合的GIF动画

        为球员视频集锦的每个回合创建独立的GIF动画，便于在线分享和展示。

        Args:
            player_name: 球员名称，不提供则使用默认球员

        Returns:
            Dict[str, Path]: GIF路径字典，以事件ID为键
        """
        import re
        from pathlib import Path

        # 明确指定类型为Dict[str, Path]
        round_gifs: Dict[str, Path] = {}

        if not player_name:
            player_name = self.config.default_player

        try:
            self.logger.info(f"正在为 {player_name} 的集锦视频创建回合GIF")

            # 1. 获取球员ID和比赛数据
            player_id = self.get_player_id_by_name(player_name)
            if not player_id:
                self.logger.error(f"未找到球员 {player_name} 的ID")
                return round_gifs

            game = self.data_service.get_game(self.config.default_team)
            if not game:
                self.logger.error("未找到比赛数据")
                return round_gifs

            # 2. 首先尝试从现有视频创建GIF
            video_service = self._get_service('videodownloader')
            if not video_service:
                self.logger.error("视频服务不可用")
                return round_gifs

            video_dir = video_service.config.output_dir
            video_files = list(video_dir.glob(f"*player{player_id}*.mp4"))

            # 3. 如果没有找到现有视频，尝试获取新的视频
            if not video_files:
                self.logger.warning(f"未找到球员 {player_name} 的视频文件，尝试下载...")

                # 使用优化后的get_player_highlights方法获取视频，只需要视频不合并
                result = self.get_player_highlights(
                    player_name=player_name,
                    output_format="video",  # 只需要视频
                    merge=False,  # 不合并视频
                    keep_originals=True  # 保留原始视频
                )

                if not result or "videos" not in result:
                    self.logger.error("下载视频失败")
                    return round_gifs

                # 重新检查视频文件
                video_files = list(video_dir.glob(f"*player{player_id}*.mp4"))
                if not video_files:
                    self.logger.error(f"仍然未找到球员 {player_name} 的视频文件")
                    return round_gifs

            self.logger.info(f"找到 {len(video_files)} 个视频文件")

            # 4. 创建GIF输出目录
            game_id = game.game_data.game_id
            gif_dir = NBAConfig.PATHS.GIF_DIR / f"player_{player_id}_{game_id}_rounds"
            gif_dir.mkdir(parents=True, exist_ok=True)

            # 5. 获取视频处理服务
            processor = self._get_service('video_processor')
            if not processor:
                self.logger.error("视频处理器不可用")
                return round_gifs

            # 6. 为每个视频创建对应的GIF
            for video_path in video_files:
                try:
                    # 从文件名中提取事件ID
                    match = re.search(r'event_(\d+)_', video_path.name)
                    if not match:
                        continue  # 跳过无法提取事件ID的文件

                    event_id = match.group(1).lstrip('0') or '0'  # 确保event_id是一个字符串

                    # 创建GIF文件名
                    gif_path = gif_dir / f"round_{event_id}_{player_id}.gif"

                    # 检查GIF是否已存在
                    if gif_path.exists():
                        self.logger.info(f"GIF已存在: {gif_path}")
                        round_gifs[event_id] = gif_path
                        continue

                    # 生成GIF
                    self.logger.info(f"正在生成GIF: {video_path.name}")
                    result = processor.convert_to_gif(video_path, gif_path)

                    if result:
                        # 确保result是Path类型
                        path_result = Path(result) if not isinstance(result, Path) else result
                        round_gifs[event_id] = path_result
                        self.logger.info(f"GIF生成成功: {path_result}")
                    else:
                        self.logger.error(f"GIF生成失败")

                except Exception as e:
                    self.handle_error(e, f"处理视频 {video_path.name}")
                    continue

            self.logger.info(f"处理完成! 生成了 {len(round_gifs)} 个GIF")
            return round_gifs

        except Exception as e:
            self.handle_error(e, "处理球员回合GIF")
            return round_gifs

    def _process_videos(self,
                        game_id: str,
                        videos: Dict[str, VideoAsset],
                        output_dir: Optional[Path] = None,
                        output_prefix: str = "highlight",
                        output_format: str = "video",  # "video", "gif", "both"
                        merge: bool = True,
                        remove_watermark: bool = True,
                        keep_originals: bool = False,
                        force_reprocess: bool = False) -> Dict[str, Union[Path, Dict[str, Path]]]:
        """内部通用视频处理方法

        整合了下载、合并、处理和转换视频的通用逻辑。
        该方法仅供内部使用，不对外暴露。

        Args:
            game_id: 比赛ID
            videos: 视频资产字典
            output_dir: 输出目录，默认根据前缀和game_id自动创建
            output_prefix: 输出文件名前缀
            output_format: 输出格式，可选 "video"(仅视频), "gif"(仅GIF), "both"(视频和GIF)
            merge: 是否合并视频为单个文件
            remove_watermark: 是否移除视频水印
            keep_originals: 是否保留原始短视频（合并后）
            force_reprocess: 是否强制重新处理已存在的文件

        Returns:
            Dict[str, Union[Path, Dict[str, Path]]]: 处理结果路径字典
        """
        video_service = self._get_service('videodownloader')
        if not video_service:
            return {}

        result = {}

        try:
            # 处理输出目录
            if output_dir is None:
                # 根据前缀自动选择合适的目录
                if output_prefix.startswith("team_"):
                    team_id = output_prefix.split("_")[1]
                    output_dir = NBAConfig.PATHS.VIDEO_DIR / "team_videos" / f"team_{team_id}_{game_id}"
                elif output_prefix.startswith("player_"):
                    player_id = output_prefix.split("_")[1]
                    output_dir = NBAConfig.PATHS.VIDEO_DIR / "player_videos" / f"player_{player_id}_{game_id}"
                else:
                    output_dir = NBAConfig.PATHS.VIDEO_DIR / "game_highlights" / f"game_{game_id}"

                # 确保目录存在
                output_dir.mkdir(parents=True, exist_ok=True)

            # 1. 处理视频文件

            # 检查是否已存在最终合并文件
            final_video_path = None
            if merge:
                final_video_path = output_dir / f"{output_prefix}_{game_id}.mp4"
                if not force_reprocess and final_video_path.exists():
                    self.logger.info(f"检测到已存在的处理结果: {final_video_path}")
                    result["video_merged"] = final_video_path

                    # 如果只需要视频且已存在，直接返回
                    if output_format == "video":
                        return result

            # 下载原始视频（如果需要）
            video_paths = {}
            if not final_video_path or output_format == "gif" or output_format == "both" or keep_originals:
                video_paths = video_service.batch_download_videos(
                    videos,
                    game_id,
                    force_reprocess=force_reprocess
                )

                if not video_paths:
                    self.logger.error("下载视频失败")
                    return result

                if not merge:
                    result["videos"] = video_paths

            # 2. 合并视频（如果需要）
            if merge and (not final_video_path or not final_video_path.exists() or force_reprocess):
                if not self.video_processor:
                    self.logger.error("视频处理器不可用")
                    if video_paths:
                        result["videos"] = video_paths
                    return result

                # 获取所有视频路径
                video_files = list(video_paths.values())

                # 按事件ID排序
                video_files.sort(key=self._extract_event_id)

                # 合并视频
                merged = self.video_processor.merge_videos(
                    video_files,
                    final_video_path,
                    remove_watermark=remove_watermark,
                    force_reprocess=force_reprocess
                )

                if merged:
                    result["video_merged"] = merged

                # 如果不需要保留原始视频且格式不是gif
                if not keep_originals and output_format != "gif" and output_format != "both":
                    # 删除原始视频文件
                    for path in video_paths.values():
                        try:
                            path.unlink()
                            self.logger.debug(f"已删除原始视频: {path}")
                        except Exception as e:
                            self.logger.warning(f"删除原始视频失败: {e}")

            # 3. 处理GIF（如果需要）
            if output_format == "gif" or output_format == "both":
                if not self.video_processor:
                    self.logger.error("视频处理器不可用，无法创建GIF")
                    return result

                gif_result = {}

                # 创建合适的GIF输出目录
                if output_prefix.startswith("team_"):
                    team_id = output_prefix.split("_")[1]
                    gif_dir = NBAConfig.PATHS.GIF_DIR / f"team_{team_id}_{game_id}"
                elif output_prefix.startswith("player_"):
                    player_id = output_prefix.split("_")[1]
                    gif_dir = NBAConfig.PATHS.GIF_DIR / f"player_{player_id}_{game_id}"
                else:
                    gif_dir = NBAConfig.PATHS.GIF_DIR / f"game_{game_id}"

                gif_dir.mkdir(parents=True, exist_ok=True)

                # 确定用于创建GIF的视频源
                source_videos = []
                if keep_originals or not merge:
                    # 使用原始视频创建GIF
                    source_videos = [(event_id, path) for event_id, path in video_paths.items()]
                else:
                    # 使用合并后的视频创建GIF（较少见的场景）
                    if "video_merged" in result:
                        source_videos = [("merged", result["video_merged"])]

                # 为每个视频创建GIF
                for event_id, video_path in source_videos:
                    gif_path = gif_dir / f"{output_prefix}_{event_id}.gif"

                    # 检查GIF是否已存在
                    if not force_reprocess and gif_path.exists():
                        self.logger.info(f"GIF已存在: {gif_path}")
                        gif_result[event_id] = gif_path
                        continue

                    # 创建GIF
                    self.logger.info(f"正在创建GIF: {gif_path}")
                    gif = self.video_processor.convert_to_gif(video_path, gif_path)

                    if gif:
                        gif_result[event_id] = gif
                        self.logger.info(f"GIF创建成功: {gif}")

                if gif_result:
                    result["gifs"] = gif_result

            return result

        except Exception as e:
            self.logger.error(f"处理视频时发生错误: {str(e)}", exc_info=True)
            return result

    def _extract_event_id(self, path: Path) -> int:
        """从文件名中提取事件ID

        Args:
            path: 视频文件路径

        Returns:
            int: 事件ID，如果无法提取则返回0
        """
        try:
            # 从文件名 "event_0123_game_xxxx.mp4" 中提取事件ID
            filename = path.name
            parts = filename.split('_')
            if len(parts) >= 2 and parts[0] == "event":
                return int(parts[1])
            return 0
        except (ValueError, IndexError):
            self.logger.warning(f"无法从文件名'{path.name}'中提取事件ID")
            return 0

    ### 4.3.2 图表可视化功能API，调用gamecharts子模块===============
    def plot_player_scoring_impact(self,
                                   team: Optional[str] = None,
                                   player_name: Optional[str] = None,
                                   title: Optional[str] = None,
                                   output_dir: Optional[Path] = None,
                                   force_reprocess: bool = False) -> Dict[str, Path]:
        """绘制球员得分影响力图

        生成显示球员投篮分布和效率的可视化图表。

        Args:
            team: 球队名称，不提供则使用默认球队
            player_name: 球员名称，不提供则使用默认球员
            title: 图表标题，不提供则自动生成
            output_dir: 输出目录，默认使用配置中的图片目录
            force_reprocess: 是否强制重新处理已存在的文件

        Returns:
            Dict[str, Path]: 包含生成图表路径的字典，键为"player_chart"
        """
        result = {}
        chart_service = self._get_service('chart')
        data_service = self._get_service('data')

        if not (chart_service and data_service):
            self.logger.error("服务不可用")
            return result

        try:
            # 获取基础信息
            team = team or self.config.default_team
            player_name = player_name or self.config.default_player

            # 获取比赛数据
            game = data_service.get_game(team)
            if not game:
                self.logger.error("未找到比赛数据")
                return result

            # 获取球员ID
            player_id = self.get_player_id_by_name(player_name)
            if not player_id:
                self.logger.error(f"未找到球员: {player_name}")
                return result

            # 获取投篮数据
            shots = game.get_shot_data(player_id)
            if not shots:
                self.logger.error("未找到投篮数据")
                return result

            # 构建标题
            if not title:
                formatted_date = game.game_data.game_time_beijing.strftime("%Y年%m月%d日")
                title = f"{player_name} 投篮分布图\n{formatted_date}"

            # 准备输出路径
            output_filename = f"scoring_impact_{game.game_data.game_id}_{player_id}.png"
            output_path = (output_dir or NBAConfig.PATHS.PICTURES_DIR) / output_filename

            # 检查文件是否已存在
            if not force_reprocess and output_path.exists():
                self.logger.info(f"检测到已存在的处理结果: {output_path}")
                result["player_chart"] = output_path
                return result

            # 调用图表服务绘制投篮图
            fig, _ = chart_service.plot_player_scoring_impact(
                shots=shots,
                player_id=player_id,
                title=title,
                output_path=str(output_path)
            )

            if fig:
                self.logger.info(f"已生成得分影响力图: {output_path}")
                result["player_chart"] = output_path
            else:
                self.logger.error("图表生成失败")

            return result

        except Exception as e:
            self.logger.error(f"绘制得分影响力图失败: {str(e)}", exc_info=True)
            self._update_service_status('chart', ServiceStatus.DEGRADED, str(e))
            return result

    def plot_team_shots(self,
                        team: Optional[str] = None,
                        title: Optional[str] = None,
                        output_dir: Optional[Path] = None,
                        force_reprocess: bool = False) -> Dict[str, Path]:
        """绘制球队所有球员的投篮图

        生成显示整个球队投篮分布和效率的可视化图表。

        Args:
            team: 球队名称，不提供则使用默认球队
            title: 图表标题，不提供则自动生成
            output_dir: 输出目录，默认使用配置中的图片目录
            force_reprocess: 是否强制重新处理已存在的文件

        Returns:
            Dict[str, Path]: 包含生成图表路径的字典，键为"team_chart"
        """
        result = {}
        chart_service = self._get_service('chart')
        data_service = self._get_service('data')

        if not (chart_service and data_service):
            self.logger.error("服务不可用")
            return result

        try:
            # 获取基础信息
            team = team or self.config.default_team

            # 获取比赛数据
            game = data_service.get_game(team)
            if not game:
                self.logger.error("未找到比赛数据")
                return result

            # 获取球队ID
            team_id = self.get_team_id_by_name(team)
            if not team_id:
                self.logger.error(f"未找到球队: {team}")
                return result

            # 构建默认标题
            if not title:
                formatted_date = game.game_data.game_time_beijing.strftime("%Y年%m月%d日")
                title = f"{team} 球队投篮分布图\n{formatted_date}"

            # 准备输出路径
            output_filename = f"team_shots_{game.game_data.game_id}_{team_id}.png"
            output_path = (output_dir or NBAConfig.PATHS.PICTURES_DIR) / output_filename

            # 检查文件是否已存在
            if not force_reprocess and output_path.exists():
                self.logger.info(f"检测到已存在的处理结果: {output_path}")
                result["team_chart"] = output_path
                return result

            # 调用图表服务绘制球队投篮图
            fig = chart_service.plot_team_shots(
                game=game,
                team_id=team_id,
                title=title,
                output_path=str(output_path)
            )

            if fig:
                self.logger.info(f"已生成球队投篮图: {output_path}")
                result["team_chart"] = output_path
            else:
                self.logger.error("球队投篮图生成失败")

            return result

        except Exception as e:
            self.logger.error(f"绘制球队投篮图失败: {str(e)}", exc_info=True)
            self._update_service_status('chart', ServiceStatus.DEGRADED, str(e))
            return result

    def generate_shot_charts(self,
                             team: Optional[str] = None,
                             player_name: Optional[str] = None,
                             output_dir: Optional[Path] = None,
                             force_reprocess: bool = False) -> Dict[str, Path]:
        """同时生成球员和球队的投篮图表

        整合了个人投篮图和球队投篮图的生成，返回所有生成图表的路径。

        Args:
            team: 球队名称，不提供则使用默认球队
            player_name: 可选的球员名称，用于生成特定球员的投篮图
            output_dir: 输出目录，默认使用配置中的图片目录
            force_reprocess: 是否强制重新处理已存在的文件

        Returns:
            Dict[str, Path]: 图表路径字典，包含player_chart和team_chart键
        """
        chart_paths = {}

        try:
            team = team or self.config.default_team

            # 生成单个球员的投篮图
            if player_name:
                self.logger.info(f"正在生成 {player_name} 的个人投篮图")
                player_result = self.plot_player_scoring_impact(
                    player_name=player_name,
                    team=team,
                    output_dir=output_dir,
                    force_reprocess=force_reprocess
                )
                if player_result and "player_chart" in player_result:
                    self.logger.info(f"个人投篮图已生成: {player_result['player_chart']}")
                    chart_paths["player_chart"] = player_result["player_chart"]
                else:
                    self.logger.error("个人投篮图生成失败")

            # 生成球队整体投篮图
            self.logger.info(f"正在生成 {team} 的球队投篮图")
            team_result = self.plot_team_shots(
                team=team,
                output_dir=output_dir,
                force_reprocess=force_reprocess
            )
            if team_result and "team_chart" in team_result:
                self.logger.info(f"球队投篮图已生成: {team_result['team_chart']}")
                chart_paths["team_chart"] = team_result["team_chart"]
            else:
                self.logger.error("球队投篮图生成失败")

            return chart_paths

        except Exception as e:
            self.handle_error(e, "生成投篮图")
            return chart_paths


    ## 4.4资源管理 ==============
    def clear_cache(self) -> None:
        """清理所有服务的缓存"""
        for service_name, service in self._services.items():
            try:
                if hasattr(service, 'clear_cache'):
                    service.clear_cache()
            except Exception as e:
                self.logger.error(f"清理{service_name}服务缓存失败: {str(e)}")

    def close(self) -> None:
        """关闭服务并清理资源"""
        self.clear_cache()
        for service in self._services.values():
            if hasattr(service, 'close'):
                service.close()

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