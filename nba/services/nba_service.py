# nba/services/nba_service.py
from abc import ABC
from typing import Optional, Dict, Any, List, Union, Type, Set
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import time

from nba.database.db_service import DatabaseService
from nba.services.game_data_service import GameDataProvider, InitializationError, GameDataConfig
from nba.services.game_video_service import GameVideoService, VideoConfig
from nba.services.game_charts_service import GameChartsService, ChartConfig
from nba.models.video_model import ContextMeasure, VideoAsset
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
            video_process_config: 视频处理器配置

        Raises:
            InitializationError: 当核心服务初始化失败时抛出
        """
        try:
            # 初始化数据库服务 - 将在GameDataProvider中使用
            database_service = DatabaseService()

            # 初始化GameData服务配置
            data_config = data_config or GameDataConfig(
                default_team=self.config.default_team,
                default_player=self.config.default_player,
                date_str=self.config.date_str,
                cache_size=self.config.cache_size,
                auto_refresh=False  # 强制设置为False，除非显式指定
            )

            # 初始化视频下载配置
            video_config = video_config or VideoConfig()

            # 初始化chart服务配置
            chart_config = chart_config or ChartConfig()

            # 初始化视频合并转化处理器
            if video_process_config:
                self._services['video_processor'] = VideoProcessor(video_process_config)
                self._update_service_status('video_processor', ServiceStatus.AVAILABLE)

            # 首先初始化数据服务，因为其他服务可能依赖它
            try:
                self._services['data'] = GameDataProvider(
                    config=data_config,
                    database_service=database_service
                )
                self._update_service_status('data', ServiceStatus.AVAILABLE)
            except Exception as e:
                self.logger.error(f"数据服务初始化失败: {str(e)}")
                self._update_service_status('data', ServiceStatus.ERROR, str(e))
                # 如果数据服务初始化失败，可能需要提前结束
                raise InitializationError(f"核心数据服务初始化失败: {str(e)}")

            # 初始化图表服务 -
            try:
                self._services['chart'] = GameChartsService(chart_config)
                self._update_service_status('chart', ServiceStatus.AVAILABLE)
            except Exception as e:
                self.logger.error(f"图表服务初始化失败: {str(e)}")
                self._update_service_status('chart', ServiceStatus.ERROR, str(e))

            # 初始化视频下载服务
            try:
                self._services['videodownloader'] = GameVideoService(video_config)
                self._update_service_status('videodownloader', ServiceStatus.AVAILABLE)
            except Exception as e:
                self.logger.error(f"视频下载服务初始化失败: {str(e)}")
                self._update_service_status('videodownloader', ServiceStatus.ERROR, str(e))

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
            if service_config is None:
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
            # 通过数据库服务获取球队ID
            return data_service.db_service.get_team_id_by_name(team_name)
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
            # 通过数据库服务获取球员ID
            return data_service.db_service.get_player_id_by_name(player_name)
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

        球队视频文件命名规则:
        - 球队事件视频: event_{事件ID}_game_{比赛ID}.mp4
        - 球队集锦: team_{球队ID}_{game_id}.mp4
        - 视频根目录 (VIDEO_DIR)
            - /team_videos/team_{球队ID}_{game_id}/ - 球队视频目录

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

            # 创建球队特定的视频目录 - 确保符合规范的目录结构
            game_id = game.game_data.game_id
            if not output_dir:
                # 修改为规范化的目录结构
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

            # 1. 下载视频
            videos_dict = self._download_videos(
                video_service=video_service,
                videos=videos,
                game_id=game_id,
                team_id=team_id,  # 传递team_id
                force_reprocess=force_reprocess
            )

            if not videos_dict:
                self.logger.error("视频下载失败")
                return {}

            if not merge:
                return videos_dict

            # 2. 合并视频
            output_filename = f"team_{team_id}_{game_id}.mp4"
            output_path = output_dir / output_filename

            merged_video = self._merge_videos(
                video_files=list(videos_dict.values()),
                output_path=output_path,
                remove_watermark=True,
                force_reprocess=force_reprocess
            )

            if merged_video:
                return {"merged": merged_video}
            else:
                return videos_dict

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

        球员视频文件命名规则:
        - 球员事件视频: event_{事件ID}_game_{比赛ID}_{ContextMeasure}.mp4
        - 球员集锦: player_{球员ID}_{game_id}.mp4
        - 视频根目录 (VIDEO_DIR)
            - /player_videos/player_{球员ID}_{game_id}/ - 球员视频目录

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

            # 创建球员特定的视频目录 - 确保符合规范的目录结构
            game_id = game.game_data.game_id
            if not output_dir:
                # 修改为规范化的目录结构
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
                    ContextMeasure.STL,
                    ContextMeasure.BLK
                }

            # 获取并处理各类型视频
            all_videos = {}
            videos_type_map = {}  # 新增：保存视频ID到类型的映射

            for measure in context_measures:
                # 获取视频资源
                videos = video_service.get_game_videos(
                    game_id=game.game_data.game_id,
                    player_id=player_id,
                    context_measure=measure
                )

                if videos:
                    # 保存每个视频的类型信息
                    for event_id in videos.keys():
                        videos_type_map[event_id] = measure.value

                    all_videos.update(videos)

                    # 添加请求间隔
                    if request_delay > 0:
                        time.sleep(request_delay)
                        self.logger.info(f"等待 {request_delay} 秒后继续...")

            # 如果找到视频，处理它们
            if not all_videos:
                self.logger.error(f"未找到球员{player_name}的任何集锦视频")
                return {}

            result = {}

            # 1. 下载视频 - 传递类型映射
            videos_dict = self._download_videos(
                video_service=video_service,
                videos=all_videos,
                game_id=game_id,
                player_id=player_id,
                videos_type_map=videos_type_map,  # 新增：传递类型映射
                force_reprocess=force_reprocess
            )

            if not videos_dict:
                self.logger.error("视频下载失败")
                return {}

            # 保存原始视频
            if keep_originals or not merge:
                result["videos"] = videos_dict

            # 2. 合并视频（如果需要）
            if merge:
                output_filename = f"player_{player_id}_{game_id}.mp4"
                output_path = output_dir / output_filename

                merged_video = self._merge_videos(
                    video_files=list(videos_dict.values()),
                    output_path=output_path,
                    remove_watermark=True,
                    force_reprocess=force_reprocess
                )

                if merged_video:
                    result["video_merged"] = merged_video

            # 3. 生成GIF（如果需要）
            if output_format == "gif" or output_format == "both":
                gif_dir = NBAConfig.PATHS.GIF_DIR / f"player_{player_id}_{game_id}_rounds"
                gif_dir.mkdir(parents=True, exist_ok=True)

                gif_paths = self._create_gifs_from_videos(
                    videos=videos_dict,
                    output_dir=gif_dir,
                    player_id=player_id,
                    force_reprocess=force_reprocess
                )

                if gif_paths:
                    result["gifs"] = gif_paths

            return result

        except Exception as e:
            self.logger.error(f"获取球员集锦失败: {str(e)}", exc_info=True)
            return {}

    def get_player_round_gifs(self, player_name: Optional[str] = None) -> Dict[str, Path]:
        """从球员集锦视频创建每个回合的GIF动画

        为球员视频集锦的每个回合创建独立的GIF动画，便于在线分享和展示。
        本质上是调用get_player_highlights方法并设置为仅生成GIF。

        GIF文件命名规则:
       - 球员回合GIF: round_{事件ID}_{球员ID}.gif

        Args:
            player_name: 球员名称，不提供则使用默认球员

        Returns:
            Dict[str, Path]: GIF路径字典，以事件ID为键
        """
        try:
            self.logger.info(f"正在为 {player_name or self.config.default_player} 的集锦视频创建回合GIF")

            # 设置特定的context_measures，包含进球和助攻
            context_measures = {
                ContextMeasure.FGM,  # 进球
                ContextMeasure.AST,  # 助攻
                ContextMeasure.BLK,  # 盖帽
            }

            # 直接调用get_player_highlights方法，设置为只生成GIF
            result = self.get_player_highlights(
                player_name=player_name,
                context_measures=context_measures,
                output_format="gif",  # 只生成GIF，不生成视频
                merge=False,  # 不需要合并视频
                keep_originals=True  # 保留原始视频文件
            )

            # 从结果中提取GIF路径
            if result and "gifs" in result:
                self.logger.info(f"处理完成! 生成了 {len(result['gifs'])} 个GIF")
                return result["gifs"]
            else:
                self.logger.error("未能生成GIF，检查球员名称或视频可用性")
                return {}

        except Exception as e:
            self.handle_error(e, "处理球员回合GIF")
            return {}

    # ==== 拆分后的辅助方法 ====

    def _download_videos(self,
                         video_service,
                         videos: Dict[str, VideoAsset],
                         game_id: str,
                         player_id: Optional[int] = None,
                         team_id: Optional[int] = None,  # 保留用于API一致性，当前实现未直接使用
                         context_measure: Optional[str] = None,
                         videos_type_map: Optional[Dict[str, str]] = None,  # 新增：类型映射参数
                         force_reprocess: bool = False) -> Dict[str, Path]:
        """下载视频辅助方法

        从视频服务下载一组视频资产。

        Args:
            video_service: 视频服务实例
            videos: 视频资产字典
            game_id: 比赛ID
            player_id: 球员ID (可选)
            team_id: 球队ID (可选)
            context_measure: 上下文类型 (可选)
            videos_type_map: 视频ID到类型的映射 (可选)
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Path]: 视频路径字典，以事件ID为键
        """
        try:
            # 如果提供了类型映射，使用单独下载
            if videos_type_map:
                video_paths = {}
                for event_id, video in videos.items():
                    # 从映射中获取该视频的类型
                    video_type = videos_type_map.get(event_id)
                    # 单独下载每个视频，传递其类型
                    path = video_service.downloader.download_video(
                        video, game_id, player_id, video_type, force_reprocess
                    )
                    if path:
                        video_paths[event_id] = path
                        self.logger.info(f"视频 {event_id} 下载成功: {path}")
                return video_paths
            else:
                # 原有的批量下载
                video_paths = video_service.batch_download_videos(
                    videos,
                    game_id,
                    player_id=player_id,
                    context_measure=context_measure,
                    force_reprocess=force_reprocess
                )

                if not video_paths:
                    self.logger.error("下载视频失败")

                return video_paths

        except Exception as e:
            self.logger.error(f"视频下载失败: {str(e)}", exc_info=True)
            return {}

    def _merge_videos(self,
                      video_files: List[Path],
                      output_path: Path,
                      remove_watermark: bool = True,
                      force_reprocess: bool = False) -> Optional[Path]:
        """合并视频辅助方法

        将多个视频文件合并为一个视频文件。

        Args:
            video_files: 视频文件路径列表
            output_path: 输出文件路径
            remove_watermark: 是否移除水印
            force_reprocess: 是否强制重新处理

        Returns:
            Optional[Path]: 合并后的视频路径，失败则返回None
        """
        try:
            # 检查输出文件是否已存在
            if not force_reprocess and output_path.exists():
                self.logger.info(f"合并视频已存在: {output_path}")
                return output_path

            # 获取视频处理器
            processor = self._get_service('video_processor')
            if not processor:
                self.logger.error("视频处理器不可用")
                return None

            # 按事件ID排序
            video_files.sort(key=self._extract_event_id)

            # 合并视频
            merged = processor.merge_videos(
                video_files,
                output_path,
                remove_watermark=remove_watermark,
                force_reprocess=force_reprocess
            )

            if merged:
                self.logger.info(f"视频合并成功: {merged}")
                return merged
            else:
                self.logger.error("视频合并失败")
                return None

        except Exception as e:
            self.logger.error(f"合并视频失败: {str(e)}", exc_info=True)
            return None

    def _create_gifs_from_videos(self,
                                 videos: Dict[str, Path],
                                 output_dir: Path,
                                 player_id: Optional[int] = None,
                                 force_reprocess: bool = False) -> Dict[str, Path]:
        """从视频创建GIF辅助方法

        为一组视频创建对应的GIF文件。

        Args:
            videos: 视频路径字典，以事件ID为键
            output_dir: GIF输出目录
            player_id: 球员ID (可选)
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Path]: GIF路径字典，以事件ID为键
        """
        try:
            # 确保输出目录存在
            output_dir.mkdir(parents=True, exist_ok=True)

            # 获取视频处理器
            processor = self._get_service('video_processor')
            if not processor:
                self.logger.error("视频处理器不可用")
                return {}

            gif_result = {}

            # 为每个视频创建GIF
            for event_id, video_path in videos.items():
                # 创建GIF文件名
                if player_id:
                    gif_path = output_dir / f"round_{event_id}_{player_id}.gif"
                else:
                    gif_path = output_dir / f"event_{event_id}.gif"

                # 检查GIF是否已存在
                if not force_reprocess and gif_path.exists():
                    self.logger.info(f"GIF已存在: {gif_path}")
                    gif_result[event_id] = gif_path
                    continue

                # 生成GIF
                self.logger.info(f"正在创建GIF: {gif_path}")
                gif = processor.convert_to_gif(video_path, gif_path)

                if gif:
                    gif_result[event_id] = gif
                    self.logger.info(f"GIF创建成功: {gif}")
                else:
                    self.logger.error(f"GIF创建失败: {video_path}")

            return gif_result

        except Exception as e:
            self.logger.error(f"创建GIF失败: {str(e)}", exc_info=True)
            return {}

    def _extract_event_id(self, path: Path) -> int:
        """从文件名中提取事件ID

        Args:
            path: 视频文件路径

        Returns:
            int: 事件ID，如果无法提取则返回0
        """
        try:
            # 从文件名 "event_0123_game_xxxx.mp4" 中提取事件ID - 符合命名规范
            filename = path.name
            parts = filename.split('_')
            if len(parts) >= 2 and parts[0] == "event":
                return int(parts[1])
            return 0
        except (ValueError, IndexError):
            self.logger.warning(f"无法从文件名'{path.name}'中提取事件ID")
            return 0

    ### 4.3.2 图表可视化功能API，调用gamecharts子模块===============
    '''
        文件命名规则与目录结构:
           - 图表目录 (PICTURES_DIR)
             - 球员投篮图: scoring_impact_{game_id}_{player_id}.png
             - 球队投篮图: team_shots_{game_id}_{team_id}.png
             -查找策略统一使用glob
    '''

    def generate_player_scoring_impact_charts(self,
                                              player_name: str,
                                              team: Optional[str] = None,
                                              output_dir: Optional[Path] = None,
                                              force_reprocess: bool = False,
                                              impact_type: str = "full_impact") -> Dict[str, Path]:
        """生成球员得分影响力图

        展示球员自己的投篮和由其助攻的队友投篮，以球员头像方式显示。

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
        result = {}

        try:
            # 验证impact_type参数
            if impact_type not in ["scoring_only", "full_impact"]:
                self.logger.warning(f"无效的impact_type值: {impact_type}，使用默认值 'full_impact'")
                impact_type = "full_impact"

            # 获取基础信息
            team = team or self.config.default_team
            if not player_name:
                player_name = self.config.default_player

            # 获取服务实例
            data_service = self._get_service('data')
            chart_service = self._get_service('chart')

            if not (data_service and chart_service):
                self.logger.error("服务不可用")
                return result

            # 获取球员ID
            player_id = self.get_player_id_by_name(player_name)
            if not player_id:
                self.logger.error(f"未找到球员: {player_name}")
                return result

            # 获取比赛数据
            game = data_service.get_game(team)
            if not game:
                self.logger.error(f"未找到{team}的比赛数据")
                return result

            # 1. 获取球员自己的投篮数据
            player_shots = game.get_shot_data(player_id)
            if not player_shots:
                self.logger.warning(f"未找到{player_name}的投篮数据")
                player_shots = []

            # 2. 获取由球员助攻的队友投篮数据（仅在full_impact模式下需要）
            assisted_shots = []
            if impact_type == "full_impact":
                assisted_shots = game.get_assisted_shot_data(player_id)
                if not assisted_shots:
                    self.logger.warning(f"未找到{player_name}的助攻投篮数据")

            # 3. 如果没有投篮数据，返回空结果
            if not player_shots:
                if impact_type == "full_impact" and not assisted_shots:
                    self.logger.error(f"{player_name}没有投篮或助攻数据")
                    return result
                elif impact_type == "scoring_only":
                    self.logger.error(f"{player_name}没有投篮数据")
                    return result

            # 4. 准备输出路径和标题
            formatted_date = game.game_data.game_time_beijing.strftime("%Y年%m月%d日")

            # 根据impact_type选择合适的标题和文件名
            if impact_type == "full_impact":
                title = f"{player_name} 得分影响力图\n{formatted_date}"
                output_filename = f"player_impact_{game.game_data.game_id}_{player_id}.png"
                result_key = "impact_chart"
            else:  # scoring_only
                title = f"{player_name} 投篮分布图\n{formatted_date}"
                output_filename = f"player_scoring_{game.game_data.game_id}_{player_id}.png"
                result_key = "scoring_chart"

            output_path = (output_dir or NBAConfig.PATHS.PICTURES_DIR) / output_filename

            # 5. 检查是否已存在
            existing_files = list((output_dir or NBAConfig.PATHS.PICTURES_DIR).glob(output_filename))
            if not force_reprocess and existing_files:
                self.logger.info(f"检测到已存在的处理结果: {existing_files[0]}")
                result[result_key] = existing_files[0]
                return result

            # 6. 调用图表服务绘制图表
            fig = chart_service.plot_player_impact(
                player_shots=player_shots,
                assisted_shots=assisted_shots,
                player_id=player_id,
                title=title,
                output_path=str(output_path),
                impact_type=impact_type
            )

            if fig:
                self.logger.info(f"球员{impact_type}图已生成: {output_path}")
                result[result_key] = output_path
            else:
                self.logger.error(f"球员{impact_type}图生成失败")

            return result

        except Exception as e:
            self.handle_error(e, "生成球员图表")
            return result

    def generate_shot_charts(self,
                             team: Optional[str] = None,
                             player_name: Optional[str] = None,
                             chart_type: str = "both",  # "team", "player", "both"
                             output_dir: Optional[Path] = None,
                             force_reprocess: bool = False,
                             shot_outcome: str = "made_only",  # "made_only", "all"
                             impact_type: str = "full_impact") -> Dict[str, Path]:
        """生成投篮分布图"""
        chart_paths = {}

        try:
            # 验证参数
            team = team or self.config.default_team

            if chart_type not in ["team", "player", "both"]:
                self.logger.error(f"无效的图表类型: {chart_type}")
                return chart_paths

            if shot_outcome not in ["made_only", "all"]:
                self.logger.warning(f"无效的shot_outcome值: {shot_outcome}，使用默认值 'made_only'")
                shot_outcome = "made_only"

            if impact_type not in ["scoring_only", "full_impact"]:
                self.logger.warning(f"无效的impact_type值: {impact_type}，使用默认值 'scoring_only'")
                impact_type = "scoring_only"

            # 检查当指定chart_type为"player"或"both"时是否提供了player_name
            if (chart_type in ["player", "both"]) and not player_name:
                player_name = self.config.default_player
                self.logger.info(f"未指定球员名称，使用默认球员: {player_name}")

            # 获取数据服务和图表服务
            data_service = self._get_service('data')
            chart_service = self._get_service('chart')

            if not (data_service and chart_service):
                self.logger.error("服务不可用")
                return chart_paths

            # 获取比赛数据
            game = data_service.get_game(team)
            if not game:
                self.logger.error(f"未找到{team}的比赛数据")
                return chart_paths

            # 1. 生成球员投篮图
            if chart_type in ["player", "both"] and player_name:
                player_chart = self._generate_player_chart(
                    player_name=player_name,
                    team=team,
                    game=game,
                    chart_service=chart_service,
                    output_dir=output_dir,
                    shot_outcome=shot_outcome,
                    impact_type=impact_type,
                    force_reprocess=force_reprocess
                )
                if player_chart:
                    chart_paths["player_chart"] = player_chart

            # 2. 生成球队投篮图
            if chart_type in ["team", "both"]:
                team_chart = self._generate_team_chart(
                    team=team,
                    game=game,
                    chart_service=chart_service,
                    output_dir=output_dir,
                    shot_outcome=shot_outcome,
                    force_reprocess=force_reprocess
                )
                if team_chart:
                    chart_paths["team_chart"] = team_chart

            return chart_paths

        except Exception as e:
            self.handle_error(e, "生成投篮图")
            return chart_paths

    def _generate_player_chart(self,
                               player_name: str,
                               team: str,
                               game,
                               chart_service,
                               output_dir: Optional[Path] = None,
                               shot_outcome: str = "made_only",
                               impact_type: str = "full_impact",
                               force_reprocess: bool = False) -> Optional[Path]:
        """生成球员投篮图的辅助方法"""
        self.logger.info(f"正在生成 {player_name} 的投篮图")

        # 选择生成方法：如果是full_impact则使用generate_player_scoring_impact_charts
        if impact_type == "full_impact":
            impact_charts = self.generate_player_scoring_impact_charts(
                player_name=player_name,
                team=team,
                output_dir=output_dir,
                force_reprocess=force_reprocess,
                impact_type=impact_type
            )
            if impact_charts and "impact_chart" in impact_charts:
                self.logger.info(f"球员得分影响力图已生成: {impact_charts['impact_chart']}")
                return impact_charts["impact_chart"]
            return None

        # 球员单独投篮图生成逻辑
        player_id = self.get_player_id_by_name(player_name)
        if not player_id:
            self.logger.error(f"未找到球员: {player_name}")
            return None

        # 获取球员投篮数据
        shots = game.get_shot_data(player_id)
        if not shots:
            self.logger.warning(f"未找到{player_name}的投篮数据")
            return None

        # 准备输出路径和文件名
        formatted_date = game.game_data.game_time_beijing.strftime("%Y年%m月%d日")
        title_prefix = "所有" if shot_outcome == "all" else ""
        title = f"{player_name} {title_prefix}投篮分布图\n{formatted_date}"

        filename_prefix = "all_shots" if shot_outcome == "all" else "scoring"
        output_filename = f"{filename_prefix}_{game.game_data.game_id}_{player_id}.png"
        output_path = (output_dir or NBAConfig.PATHS.PICTURES_DIR) / output_filename

        # 检查是否已存在
        existing_files = list((output_dir or NBAConfig.PATHS.PICTURES_DIR).glob(output_filename))
        if not force_reprocess and existing_files:
            self.logger.info(f"检测到已存在的处理结果: {existing_files[0]}")
            return existing_files[0]

        # 使用plot_shots方法绘制球员投篮图
        fig = chart_service.plot_shots(
            shots_data=shots,
            title=title,
            output_path=str(output_path),
            shot_outcome=shot_outcome,
            data_type="player"
        )

        if fig:
            self.logger.info(f"球员投篮图已生成: {output_path}")
            return output_path
        else:
            self.logger.error("球员投篮图生成失败")
            return None

    def _generate_team_chart(self,
                             team: str,
                             game,
                             chart_service,
                             output_dir: Optional[Path] = None,
                             shot_outcome: str = "made_only",
                             force_reprocess: bool = False) -> Optional[Path]:
        """生成球队投篮图的辅助方法"""
        self.logger.info(f"正在生成 {team} 的球队投篮图")

        # 获取球队ID
        team_id = self.get_team_id_by_name(team)
        if not team_id:
            self.logger.error(f"未找到球队: {team}")
            return None

        # 准备输出路径和文件名
        formatted_date = game.game_data.game_time_beijing.strftime("%Y年%m月%d日")
        title_prefix = "所有" if shot_outcome == "all" else ""
        title = f"{team} {title_prefix}球队投篮分布图\n{formatted_date}"

        filename_prefix = "all_shots" if shot_outcome == "all" else "team_shots"
        output_filename = f"{filename_prefix}_{game.game_data.game_id}_{team_id}.png"
        output_path = (output_dir or NBAConfig.PATHS.PICTURES_DIR) / output_filename

        # 检查是否已存在
        existing_files = list((output_dir or NBAConfig.PATHS.PICTURES_DIR).glob(output_filename))
        if not force_reprocess and existing_files:
            self.logger.info(f"检测到已存在的处理结果: {existing_files[0]}")
            return existing_files[0]

        # 获取球队投篮数据 - 传递 team_id 参数
        team_shots = game.get_team_shot_data(team_id)

        # 调用图表服务绘制球队投篮图
        fig = chart_service.plot_shots(
            shots_data=team_shots,
            title=title,
            output_path=str(output_path),
            shot_outcome=shot_outcome,
            data_type="team"
        )

        if fig:
            self.logger.info(f"球队投篮图已生成: {output_path}")
            return output_path
        else:
            self.logger.error("球队投篮图生成失败")
            return None

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
        for service_name, service in self._services.items():
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