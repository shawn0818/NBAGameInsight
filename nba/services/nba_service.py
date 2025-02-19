# nba/services/nba_service.py
from abc import ABC
from typing import Optional, Dict, Any, List, Union, Type
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import time

from nba.services.game_data_service import GameDataProvider, InitializationError, GameDataConfig
from nba.services.game_video_service import GameVideoService, VideoConfig
from nba.services.game_display_service import GameDisplayService,  DisplayConfig
from nba.services.game_charts_service import GameChartsService, ChartConfig
from utils.ai_processor import AIProcessor, AIConfig
from nba.models.video_model import ContextMeasure
from config.nba_config import NBAConfig
from utils.logger_handler import AppLogger


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
        if not (32 <= self.cache_size <= 512):
            raise ValueError("Cache size must be between 32 and 512")



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


# =======4. NBA服务主类====================


class NBAService:
    """NBA数据服务统一接口
    这是NBA服务的主类，整合了数据查询、视频处理、图表生成等多个子服务。
    该类采用组合模式，将各个子服务组织在一起，提供统一的访问接口。
    """

    ## =======4.1 完成主服务以及子服务初始化 ====================

    def __init__(
            self,
            config: Optional[NBAServiceConfig] = None,
            ai_config: Optional[AIConfig] = None,
            data_config: Optional[GameDataConfig] = None,
            display_config: Optional[DisplayConfig] = None,
            video_config: Optional[VideoConfig] = None,
            chart_config: Optional[ChartConfig] = None,
    ):
        """初始化NBA服务
        这是服务的主要入口点，负责初始化所有子服务和配置。
        采用依赖注入模式，允许自定义各个子服务的配置。

        Args:
            config: NBA服务主配置，控制全局行为
            ai_config: AI处理器配置，用于高级数据分析
            data_config: 比赛数据服务配置
            display_config: 数据展示服务配置
            video_config: 视频处理服务配置
            chart_config: 图表生成服务配置

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

        # 服务健康状态初始化
        self._services: Dict[str, Any] = {}
        self._service_status: Dict[str, ServiceHealth] = {}

        # 初始化服务
        self._init_all_services(
            ai_config=ai_config,
            data_config=data_config,
            display_config=display_config,
            video_config=video_config,
            chart_config=chart_config
        )

    def _init_all_services(
            self,
            ai_config: Optional[AIConfig] = None,
            data_config: Optional[GameDataConfig] = None,
            display_config: Optional[DisplayConfig] = None,
            video_config: Optional[VideoConfig] = None,
            chart_config: Optional[ChartConfig] = None
    ) -> None:
        """初始化所有子服务

        按照特定的顺序和依赖关系初始化各个子服务。

        初始化顺序：
        1. AI处理器（可选）
        2. 数据服务（核心服务）
        3. 显示服务
        4. 图表服务
        5. 视频服务

        服务依赖关系：
        - 显示服务依赖于AI配置（如果存在）
        - 所有服务都依赖于数据服务

        Args:
            ai_config: AI服务配置
            data_config: 数据服务配置
            display_config: 显示服务配置
            video_config: 视频服务配置
            chart_config: 图表服务配置

        Raises:
            InitializationError: 当核心服务初始化失败时抛出
        """
        try:
            # 初始化 AI 处理器（可选服务）
            ai_processor = AIProcessor(ai_config) if ai_config else None

            # 创建GameData服务配置（核心服务）
            data_config = data_config or GameDataConfig(
                default_team=self.config.default_team,
                default_player=self.config.default_player,
                date_str=self.config.date_str,
                cache_size=self.config.cache_size,
                auto_refresh=self.config.auto_refresh
            )

            # Display配置处理
            display_config = display_config or DisplayConfig()
            # AI 配置作为可选配置传入 display_config
            if ai_config:
                display_config.ai_config = ai_config

            video_config = video_config or VideoConfig()
            chart_config = chart_config or ChartConfig()

            # 服务初始化映射
            service_configs = {
                'ai': (AIProcessor, ai_config),
                'data': (GameDataProvider, data_config),
                'display': (GameDisplayService, display_config),
                'chart': (GameChartsService, chart_config),
                'video': (GameVideoService, video_config),
            }

            # 按照预定义顺序初始化服务
            for service_name, (service_class, service_config) in service_configs.items():
                self._init_service(service_name, service_class, service_config)

        except Exception as e:
            self.logger.error(f"服务初始化失败: {str(e)}")
            raise InitializationError(f"服务初始化失败: {str(e)}")

    def _init_service(self,
                      name: str,
                      service_class: Type,
                      service_config: Any) -> None:
        """单个服务的初始化方法

        负责初始化单个服务并更新其状态。如果是AI服务且配置为None，
        则将服务标记为不可用而不是报错。

        Args:
            name: 服务名称
            service_class: 服务类
            service_config: 服务配置对象

        注意：
            - 初始化失败会被记录但不会阻止其他服务的初始化
            - AI服务是可选的，其他服务初始化失败会被记录为错误状态
        """
        try:
            if name == 'ai' and service_config is None:
                self._update_service_status(name, ServiceStatus.UNAVAILABLE)
                return

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

    ## =============4.2 调用个各子模块服务=================

    ### =============4.2.1基本查询功能，调用gamedisplay子模块==============

    def format_basic_game_info(self, team: Optional[str] = None,
                               date: Optional[str] = None) -> Dict[str, Any]:
        """格式化基础比赛信息"""
        data_service = self._get_service('data')
        display_service = self._get_service('display')

        if not (data_service and display_service):
            return {}

        try:
            game = data_service.get_game(team or self.config.default_team, date)
            if not game:
                return {}

            game_display = display_service.display_game(game)
            return game_display.get("game_narrative", {})
        except Exception as e:
            self.logger.error(f"格式化基础比赛信息失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.DEGRADED, str(e))
            return {}

    def format_player_stats(
            self,
            team: Optional[str] = None,
            date: Optional[str] = None,
            player_name: Optional[str] = None
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """格式化球员统计数据"""
        data_service = self._get_service('data')
        display_service = self._get_service('display')

        if not (data_service and display_service):
            return [] if not player_name else {}

        try:
            game = data_service.get_game(team or self.config.default_team, date)
            if not game:
                return [] if not player_name else {}

            game_display = display_service.display_game(game)
            player_narratives = game_display.get('player_narratives', {})

            if player_name:
                all_players = (
                        player_narratives.get('original', {}).get('home', []) +
                        player_narratives.get('original', {}).get('away', [])
                )
                for narrative in all_players:
                    if player_name in narrative:
                        return {'original': narrative}
                return {}

            return player_narratives
        except Exception as e:
            self.logger.error(f"格式化球员统计数据失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.DEGRADED, str(e))
            return [] if not player_name else {}

    def format_team_stats(
            self,
            game_selector: Optional[str] = None,
            date: Optional[str] = None,
            filter_team: Optional[str] = None
    ) -> Union[Dict[str, Dict[str, Any]], Dict[str, Any]]:
        """格式化球队统计数据"""
        data_service = self._get_service('data')
        display_service = self._get_service('display')

        if not (data_service and display_service):
            return {}

        try:
            game = data_service.get_game(game_selector or self.config.default_team, date)
            if not game:
                return {}

            game_display = display_service.display_game(game)
            team_narratives = game_display.get('team_narratives', {})

            if filter_team:
                if game.game_data.home_team.team_name == filter_team:
                    return {'original': team_narratives.get('original', {}).get('home', '')}
                elif game.game_data.away_team.team_name == filter_team:
                    return {'original': team_narratives.get('original', {}).get('away', '')}
                return {}

            return team_narratives
        except Exception as e:
            self.logger.error(f"格式化球队统计数据失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.DEGRADED, str(e))
            return {}

    def analyze_game_events(
            self,
            game_selector: Optional[str] = None,
            date: Optional[str] = None,
            filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """分析比赛事件"""
        data_service = self._get_service('data')
        display_service = self._get_service('display')

        if not (data_service and display_service):
            return {}

        try:
            game = data_service.get_game(game_selector or self.config.default_team, date)
            if not game:
                return {}

            game_display = display_service.display_game(game)
            events_data = game_display.get('events', {})

            if filters:
                filtered_events = game.filter_events(**filters)
                events_data['events'] = [
                    display_service._parse_event(event)
                    for event in filtered_events
                ]

            return events_data
        except Exception as e:
            self.logger.error(f"分析比赛事件失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.DEGRADED, str(e))
            return {}


    ### =============4.2.2视频功能，调用gamevideo子模块==============

    def get_game_videos(self, context_measure: Union[str, ContextMeasure] = ContextMeasure.FGM) -> Dict[str, Path]:
        """获取比赛视频"""
        video_service = self._get_service('video')
        data_service = self._get_service('data')

        if not (video_service and data_service):
            return {}

        try:
            if isinstance(context_measure, str):
                try:
                    context_measure = ContextMeasure(context_measure)
                except ValueError:
                    self.logger.error(f"无效的视频类型: {context_measure}")
                    return {}

            team_id = self.get_team_id_by_name(self.config.default_team)
            if not team_id:
                self.logger.error(f"未找到球队: {self.config.default_team}")
                return {}

            player_id = self.get_player_id_by_name(self.config.default_player)
            if not player_id:
                self.logger.error(f"未找到球员: {self.config.default_player}")
                return {}

            game = data_service.get_game(self.config.default_team)
            if not game:
                self.logger.error("未找到比赛信息")
                return {}

            game_id = game.game_data.game_id

            self.logger.info(
                f"准备获取视频 - 比赛ID: {game_id}, "
                f"球队ID: {team_id}, "
                f"球员: {self.config.default_player}, "
                f"球员ID: {player_id}, "
                f"类型: {context_measure.value}"
            )

            video_assets = video_service.get_game_videos(
                game_id=game_id,
                player_id=player_id,
                context_measure=context_measure
            )

            if not video_assets:
                self.logger.warning(f"未找到 {context_measure.value} 类型的视频资产")
                return {}

            self.logger.info(f"成功获取 {len(video_assets)} 个视频资产，开始处理...")

            results = video_service.batch_process_videos(
                videos=video_assets,
                game_id=game_id
            )

            if results:
                self.logger.info(f"成功处理 {len(results)} 个视频")
            else:
                self.logger.warning("视频处理失败")

            return results

        except Exception as e:
            self.logger.error(f"获取视频失败: {str(e)}", exc_info=True)
            self._update_service_status('video', ServiceStatus.DEGRADED, str(e))
            return {}

    ### ============ 4.2.3图表可视化功能，调用gamecharts子模块===============

    def plot_player_scoring_impact(self,
                                   team: Optional[str] = None,
                                   player_name: Optional[str] = None,
                                   title: Optional[str] = None) -> Optional[Path]:
        """绘制球员得分影响力图"""
        chart_service = self._get_service('chart')
        data_service = self._get_service('data')

        if not (chart_service and data_service):
            return None

        try:
            game = data_service.get_game(team or self.config.default_team)
            if not game:
                self.logger.error("未找到比赛数据")
                return None

            player_id = self.get_player_id_by_name(player_name or self.config.default_player)
            if not player_id:
                self.logger.error(f"未找到球员: {player_name or self.config.default_player}")
                return None

            output_filename = f"scoring_impact_{game.game_data.game_id}.png"
            output_path = NBAConfig.PATHS.PICTURES_DIR / output_filename

            fig, _ = chart_service.plot_player_scoring_impact(
                game=game,
                player_id=player_id,
                title=title,
                output_path=str(output_path)
            )

            if fig:
                self.logger.info(f"已生成得分影响力图: {output_path}")
                return output_path
            else:
                self.logger.error("图表生成失败")
                return None

        except Exception as e:
            self.logger.error(f"绘制得分影响力图失败: {str(e)}", exc_info=True)
            self._update_service_status('chart', ServiceStatus.DEGRADED, str(e))
            return None

    def plot_team_shots(self,
                        team: Optional[str] = None,
                        title: Optional[str] = None,
                        scale_factor: float = 2.0,
                        dpi: int = 300) -> Optional[Path]:
        """绘制球队所有球员的投篮图"""
        chart_service = self._get_service('chart')
        data_service = self._get_service('data')

        if not (chart_service and data_service):
            return None

        try:
            game = data_service.get_game(team or self.config.default_team)
            if not game:
                self.logger.error("未找到比赛数据")
                return None

            team_id = self.get_team_id_by_name(team or self.config.default_team)
            if not team_id:
                self.logger.error(f"未找到球队: {team or self.config.default_team}")
                return None

            self.logger.info(f"准备为球队 {team or self.config.default_team} (ID: {team_id}) 生成投篮图")

            output_filename = f"team_shots_{game.game_data.game_id}_{team_id}.png"
            output_path = NBAConfig.PATHS.PICTURES_DIR / output_filename

            self.logger.info(f"开始生成球队投篮图，输出路径: {output_path}")

            fig = chart_service.plot_team_shots(
                game=game,
                team_id=team_id,
                title=title,
                output_path=str(output_path),
                scale_factor=scale_factor,
                dpi=dpi
            )

            if fig:
                self.logger.info(f"已生成球队投篮图: {output_path}")
                return output_path
            else:
                self.logger.error("球队投篮图生成失败")
                return None

        except Exception as e:
            self.logger.error(f"绘制球队投篮图失败: {str(e)}", exc_info=True)
            self._update_service_status('chart', ServiceStatus.DEGRADED, str(e))
            return None

    ### =============4.2.4 辅助方法 ==============

    def get_team_id_by_name(self, team_name: str) -> Optional[int]:
        """获取球队ID"""
        data_service = self._get_service('data')
        if not data_service:
            return None

        try:
            return data_service.league_provider.get_team_id_by_name(team_name)
        except Exception as e:
            self.logger.error(f"获取球队ID失败: {str(e)}")
            return None

    def get_player_id_by_name(self, player_name: str) -> Optional[Union[int, List[int]]]:
        """获取球员ID"""
        data_service = self._get_service('data')
        if not data_service:
            return None

        try:
            return data_service.league_provider.get_player_id_by_name(player_name)
        except Exception as e:
            self.logger.error(f"获取球员ID失败: {str(e)}")
            return None


    ### =============4.2.5 资源管理 ==============

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