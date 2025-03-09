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


class NBAService:
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

    ## =============4.2 调用个各子模块服务=================

    ### =============4.2.1基本查询功能，调用game_model里提供的接口==============

    def get_game_basic_info(self, team: Optional[str] = None, date: Optional[str] = None) -> Dict[str, Any]:
        """获取比赛基本信息

        获取一场比赛的基本信息，包括比赛状态、比分、场馆等。

        Args:
            team: 球队名称，不提供则使用默认球队
            date: 比赛日期，不提供则使用最近一场比赛

        Returns:
            Dict[str, Any]: 包含比赛基本信息的字典
        """
        data_service = self._get_service('data')
        if not data_service:
            return {"error": "数据服务不可用"}

        try:
            # 获取比赛数据
            game = data_service.get_game(team or self.config.default_team, date)
            if not game:
                return {"error": f"未找到{team or self.config.default_team}的比赛数据"}

            # 获取比赛状态信息
            game_status = game.get_game_status()

            # 准备更完整的比赛基本信息
            game_info = {
                "game_id": game.game_data.game_id,
                "status": game_status,
                "teams": {
                    "home": {
                        "id": game.game_data.home_team.team_id,
                        "name": f"{game.game_data.home_team.team_city} {game.game_data.home_team.team_name}",
                        "tricode": game.game_data.home_team.team_tricode,
                        "score": int(game.game_data.home_team.score)
                    },
                    "away": {
                        "id": game.game_data.away_team.team_id,
                        "name": f"{game.game_data.away_team.team_city} {game.game_data.away_team.team_name}",
                        "tricode": game.game_data.away_team.team_tricode,
                        "score": int(game.game_data.away_team.score)
                    }
                },
                "arena": {
                    "name": game.game_data.arena.arena_name,
                    "city": game.game_data.arena.arena_city,
                    "state": game.game_data.arena.arena_state
                },
                "date": {
                    "utc": game.game_data.game_time_utc.strftime('%Y-%m-%d %H:%M:%S'),
                    "local": game.game_data.game_time_local.strftime('%Y-%m-%d %H:%M:%S'),
                    "beijing": game.game_data.game_time_beijing.strftime('%Y-%m-%d %H:%M:%S')
                }
            }

            return game_info
        except Exception as e:
            self.logger.error(f"获取比赛基本信息失败: {str(e)}")
            return {"error": f"获取比赛基本信息失败: {str(e)}"}

    def get_team_stats(self, team: Optional[str] = None, date: Optional[str] = None) -> Dict[str, Any]:
        """获取球队统计数据

        获取指定球队在指定比赛中的详细统计数据。

        Args:
            team: 球队名称，不提供则使用默认球队
            date: 比赛日期，不提供则使用最近一场比赛

        Returns:
            Dict[str, Any]: 包含球队统计数据的字典
        """
        data_service = self._get_service('data')
        if not data_service:
            return {"error": "数据服务不可用"}

        try:
            # 获取比赛数据
            game = data_service.get_game(team or self.config.default_team, date)
            if not game:
                return {"error": f"未找到{team or self.config.default_team}的比赛数据"}

            # 获取球队ID
            team_id = self.get_team_id_by_name(team or self.config.default_team)
            if not team_id:
                return {"error": f"无法确定球队ID: {team or self.config.default_team}"}

            # 使用Game模型中的get_team_stats方法获取球队统计数据
            team_data = game.get_team_stats(team_id)
            if not team_data:
                return {"error": f"未找到ID为{team_id}的球队统计数据"}

            # 转换为字典格式返回
            return {
                "team_id": team_id,
                "team_name": f"{team_data.team_city} {team_data.team_name}",
                "team_tricode": team_data.team_tricode,
                "score": int(team_data.score),
                "statistics": team_data.statistics.dict(),
                "players": [p.dict() for p in team_data.players]
            }
        except Exception as e:
            self.logger.error(f"获取球队统计数据失败: {str(e)}")
            return {"error": f"获取球队统计数据失败: {str(e)}"}

    def get_player_stats(self,
                         team: Optional[str] = None,
                         date: Optional[str] = None,
                         player_name: Optional[str] = None) -> Dict[str, Any]:
        """获取球员统计数据

        获取指定球员在指定比赛中的详细统计数据。

        Args:
            team: 球队名称，不提供则使用默认球队
            date: 比赛日期，不提供则使用最近一场比赛
            player_name: 球员姓名，不提供则返回所有球员数据

        Returns:
            Dict[str, Any]: 包含球员统计数据的字典
        """
        data_service = self._get_service('data')
        if not data_service:
            return {"error": "数据服务不可用"}

        try:
            # 获取比赛数据
            game = data_service.get_game(team or self.config.default_team, date)
            if not game:
                return {"error": f"未找到{team or self.config.default_team}的比赛数据"}

            # 如果提供了球员姓名，获取特定球员数据
            if player_name:
                player_id = self.get_player_id_by_name(player_name)
                if not player_id:
                    return {"error": f"未找到球员: {player_name}"}

                # 使用Game模型中的get_player_stats方法获取球员统计数据
                player_data = game.get_player_stats(player_id)
                if not player_data:
                    return {"error": f"未找到ID为{player_id}的球员统计数据"}

                # 返回详细球员数据
                return {
                    "player_id": player_id,
                    "player_name": player_data.name,
                    "team_id": None,  # 需要额外查询
                    "position": player_data.position,
                    "jersey_num": player_data.jersey_num,
                    "starter": player_data.starter == "1",
                    "minutes": player_data.statistics.minutes_calculated,
                    "statistics": player_data.statistics.dict()
                }
            else:
                # 如果没有提供球员姓名，返回所有球员的统计数据
                # 分为主队和客队
                home_players = [
                    {
                        "player_id": p.person_id,
                        "player_name": p.name,
                        "team_id": game.game_data.home_team.team_id,
                        "team_name": f"{game.game_data.home_team.team_city} {game.game_data.home_team.team_name}",
                        "position": p.position,
                        "jersey_num": p.jersey_num,
                        "starter": p.starter == "1",
                        "minutes": p.statistics.minutes_calculated,
                        "points": p.statistics.points,
                        "rebounds": p.statistics.rebounds_total,
                        "assists": p.statistics.assists
                    } for p in game.game_data.home_team.players if p.played == "1"
                ]

                away_players = [
                    {
                        "player_id": p.person_id,
                        "player_name": p.name,
                        "team_id": game.game_data.away_team.team_id,
                        "team_name": f"{game.game_data.away_team.team_city} {game.game_data.away_team.team_name}",
                        "position": p.position,
                        "jersey_num": p.jersey_num,
                        "starter": p.starter == "1",
                        "minutes": p.statistics.minutes_calculated,
                        "points": p.statistics.points,
                        "rebounds": p.statistics.rebounds_total,
                        "assists": p.statistics.assists
                    } for p in game.game_data.away_team.players if p.played == "1"
                ]

                return {
                    "home_team_players": home_players,
                    "away_team_players": away_players
                }
        except Exception as e:
            self.logger.error(f"获取球员统计数据失败: {str(e)}")
            return {"error": f"获取球员统计数据失败: {str(e)}"}

    def get_game_events(self,
                        team: Optional[str] = None,
                        date: Optional[str] = None,
                        player_name: Optional[str] = None,
                        event_types: Optional[Set[str]] = None,
                        limit: Optional[int] = None) -> Dict[str, Any]:
        """获取比赛事件数据

        获取比赛中的事件数据，可以按球员、事件类型进行筛选。

        Args:
            team: 球队名称，不提供则使用默认球队
            date: 比赛日期，不提供则使用最近一场比赛
            player_name: 球员姓名，不提供则获取所有球员事件
            event_types: 事件类型集合，如{"2pt", "3pt", "rebound"}
            limit: 返回事件的最大数量

        Returns:
            Dict[str, Any]: 包含筛选后事件的字典
        """
        data_service = self._get_service('data')
        if not data_service:
            return {"error": "数据服务不可用"}

        try:
            # 获取比赛数据
            game = data_service.get_game(team or self.config.default_team, date)
            if not game:
                return {"error": f"未找到{team or self.config.default_team}的比赛数据"}

            # 获取player_id（如果提供了球员姓名）
            player_id = None
            if player_name:
                player_id = self.get_player_id_by_name(player_name)
                if not player_id:
                    return {"error": f"未找到球员: {player_name}"}

            # 使用Game模型中的filter_events方法筛选事件
            filtered_events = game.filter_events(
                player_id=player_id,
                action_types=event_types
            )

            # 如果没有事件，返回空列表
            if not filtered_events:
                return {"events": [], "count": 0}

            # 按照事件重要性排序
            sorted_events = sorted(
                filtered_events,
                key=lambda evt: evt.calculate_importance() if hasattr(e, 'calculate_importance') else 0,
                reverse=True
            )

            # 应用限制
            if limit and len(sorted_events) > limit:
                sorted_events = sorted_events[:limit]

            # 转换为字典格式
            events_data = []
            for event in sorted_events:
                event_dict = {
                    "action_number": event.action_number,
                    "period": event.period,
                    "clock": event.clock,
                    "action_type": event.action_type,
                    "sub_type": getattr(event, "sub_type", None),
                    "description": event.description,
                    "team_id": getattr(event, "team_id", None),
                    "team_tricode": getattr(event, "team_tricode", None),
                    "player_id": getattr(event, "person_id", None),
                    "player_name": getattr(event, "player_name", None),
                    "importance": event.calculate_importance() if hasattr(event, 'calculate_importance') else 0
                }

                # 对于投篮事件，添加更多详细信息
                if event.action_type in ["2pt", "3pt"]:
                    event_dict.update({
                        "shot_result": getattr(event, "shot_result", None),
                        "shot_distance": getattr(event, "shot_distance", None),
                        "area": getattr(event, "area", None),
                        "x": getattr(event, "x_legacy", None),
                        "y": getattr(event, "y_legacy", None)
                    })

                events_data.append(event_dict)

            return {"events": events_data, "count": len(events_data)}
        except Exception as e:
            self.logger.error(f"获取比赛事件失败: {str(e)}")
            return {"error": f"获取比赛事件失败: {str(e)}"}

    def get_game_summary(self, team: Optional[str] = None, date: Optional[str] = None) -> Dict[str, Any]:
        """获取比赛概况摘要

        获取一场比赛的摘要信息，包括比分、最佳球员、关键数据等。
        直接调用Game模型中的get_game_summary方法。

        Args:
            team: 球队名称，不提供则使用默认球队
            date: 比赛日期，不提供则使用最近一场比赛

        Returns:
            Dict[str, Any]: 比赛摘要信息
        """
        data_service = self._get_service('data')
        if not data_service:
            return {"error": "数据服务不可用"}

        try:
            # 获取比赛数据
            game = data_service.get_game(team or self.config.default_team, date)
            if not game:
                return {"error": f"未找到{team or self.config.default_team}的比赛数据"}

            # 直接使用Game模型的get_game_summary方法
            summary = game.get_game_summary()

            # 添加一些可能对用户有用的额外信息
            summary["formatted_date"] = game.game_data.game_time_beijing.strftime('%Y年%m月%d日')
            summary["arena_info"] = f"{game.game_data.arena.arena_name}, {game.game_data.arena.arena_city}"

            return summary
        except Exception as e:
            self.logger.error(f"获取比赛概况失败: {str(e)}")
            return {"error": f"获取比赛概况失败: {str(e)}"}

    def get_current_lineup(self, team: Optional[str] = None, date: Optional[str] = None) -> Dict[str, Any]:
        """获取当前场上阵容

        获取比赛当前场上的两队阵容。

        Args:
            team: 球队名称，不提供则使用默认球队
            date: 比赛日期，不提供则使用最近一场比赛

        Returns:
            Dict[str, Any]: 包含当前场上阵容的字典
        """
        data_service = self._get_service('data')
        if not data_service:
            return {"error": "数据服务不可用"}

        try:
            # 获取比赛数据
            game = data_service.get_game(team or self.config.default_team, date)
            if not game:
                return {"error": f"未找到{team or self.config.default_team}的比赛数据"}

            # 直接使用Game模型的get_current_lineup方法
            lineup = game.get_current_lineup()

            # 添加球队信息
            lineup["home_team"] = {
                "team_id": game.game_data.home_team.team_id,
                "team_name": f"{game.game_data.home_team.team_city} {game.game_data.home_team.team_name}",
                "team_tricode": game.game_data.home_team.team_tricode
            }

            lineup["away_team"] = {
                "team_id": game.game_data.away_team.team_id,
                "team_name": f"{game.game_data.away_team.team_city} {game.game_data.away_team.team_name}",
                "team_tricode": game.game_data.away_team.team_tricode
            }

            return lineup
        except Exception as e:
            self.logger.error(f"获取当前阵容失败: {str(e)}")
            return {"error": f"获取当前阵容失败: {str(e)}"}



    ### =============4.2.2视频功能，调用gamevideo子模块==============

    def get_team_highlights(self,
                            team: Optional[str] = None,
                            merge: bool = True,
                            output_dir: Optional[Path] = None,
                            force_reprocess: bool = False) -> Dict[str, Path]:
        """获取球队集锦视频（同步版本，添加增量处理）

        Args:
            team: 球队名称，不提供则使用默认球队
            merge: 是否合并视频
            output_dir: 输出目录
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Path]: 视频路径字典
        """
        video_service = self._get_service('videodownloader')
        if not video_service or not self.data_service:
            return {}

        try:
            # 获取基础信息
            team_id = self.get_team_id_by_name(team or self.config.default_team)
            if not team_id:
                return {}

            game = self.data_service.get_game(team or self.config.default_team)
            if not game:
                return {}

            # 检查最终合并文件是否已存在
            if merge and not force_reprocess:
                output_path = (output_dir or NBAConfig.PATHS.VIDEO_DIR) / f"highlight_{game.game_data.game_id}.mp4"
                if output_path.exists():
                    self.logger.info(f"检测到已存在的球队集锦: {output_path}")
                    return {"merged": output_path}

            # 获取视频资产
            videos = video_service.get_game_videos(
                game_id=game.game_data.game_id,
                team_id=team_id,
                context_measure=ContextMeasure.FGM
            )
            if not videos:
                return {}

            # 下载视频
            video_paths = video_service.batch_download_videos(
                videos,
                game.game_data.game_id,
                force_reprocess=force_reprocess
            )
            if not video_paths:
                return {}

            # 如果不需要合并，直接返回
            if not merge or not self.video_processor:
                return video_paths

            # 获取所有视频路径
            video_files = list(video_paths.values())

            # 按事件ID排序
            video_files.sort(key=self._extract_event_id)

            # 合并视频
            output_path = (output_dir or NBAConfig.PATHS.VIDEO_DIR) / f"highlight_{game.game_data.game_id}.mp4"
            merged = self.video_processor.merge_videos(
                video_files,
                output_path,
                remove_watermark=True,
                force_reprocess=force_reprocess
            )
            return {"merged": merged} if merged else video_paths

        except Exception as e:
            self.logger.error(f"获取球队集锦失败: {e}")
            return {}

    def get_player_highlights(self,
                              player_name: Optional[str] = None,
                              context_measures: Optional[Set[ContextMeasure]] = None,
                              merge: bool = True,
                              output_dir: Optional[Path] = None,
                              request_delay: float = 1.0,
                              force_reprocess: bool = False) -> Dict[str, Union[Path, Dict[str, Path]]]:
        """获取球员集锦视频（添加增量处理）

        Args:
            player_name: 球员名称，不提供则使用默认球员
            context_measures: 上下文度量集合，如{FGM, AST}
            merge: 是否合并视频
            output_dir: 输出目录
            request_delay: 请求间隔时间(秒)
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Union[Path, Dict[str, Path]]]: 视频路径字典
        """
        import time
        video_service = self._get_service('videodownloader')
        if not video_service or not self.data_service:
            return {}

        try:
            # 获取基础信息
            player_id = self.get_player_id_by_name(player_name or self.config.default_player)
            if not player_id:
                return {}

            # 检查最终合并文件是否已存在
            if merge and not force_reprocess:
                output_path = (output_dir or NBAConfig.PATHS.VIDEO_DIR) / f"player_highlight_{player_id}.mp4"
                if output_path.exists():
                    self.logger.info(f"检测到已存在的处理结果: {output_path}")
                    return {"merged": output_path}

            game = self.data_service.get_game(self.config.default_team)
            if not game:
                return {}

            # 确定要获取的视频类型
            if context_measures is None:
                context_measures = {
                    ContextMeasure.FGM,
                    ContextMeasure.AST,
                    ContextMeasure.STL
                }

            # 获取并下载各类型视频
            all_paths = {}
            for measure in context_measures:
                # 获取视频资源
                videos = video_service.get_game_videos(
                    game_id=game.game_data.game_id,
                    player_id=player_id,
                    context_measure=measure
                )
                if videos:
                    # 下载视频
                    paths = video_service.batch_download_videos(
                        videos,
                        game.game_data.game_id,
                        player_id=player_id,
                        context_measure=measure.value,
                        force_reprocess=force_reprocess
                    )
                    if paths:
                        all_paths[measure.value] = paths

                    # 添加请求间隔
                    if request_delay > 0:
                        time.sleep(request_delay)
                        self.logger.info(f"等待 {request_delay} 秒后继续...")

            if not all_paths:
                return {}

            if not merge or not self.video_processor:
                return all_paths

            # 收集所有视频路径
            all_video_paths = [
                path for paths in all_paths.values()
                for path in paths.values()
            ]

            # 按事件ID排序
            all_video_paths.sort(key=self._extract_event_id)

            # 合并视频
            output_path = (output_dir or NBAConfig.PATHS.VIDEO_DIR) / f"player_highlight_{player_id}_{game.game_data.game_id}.mp4"
            merged = self.video_processor.merge_videos(
                all_video_paths,
                output_path,
                remove_watermark=True,
                force_reprocess=force_reprocess
            )
            return {"merged": merged} if merged else all_paths

        except Exception as e:
            self.logger.error(f"获取球员集锦失败: {e}")
            return {}

    def _process_game_videos(
            self,
            game_id: str,
            videos: Dict[str, VideoAsset],
            merge: bool = True,
            output_dir: Optional[Path] = None,
            force_reprocess: bool = False
    ) -> Dict[str, Path]:
        """处理比赛视频的通用方法（同步版）

        Args:
            game_id: 比赛ID
            videos: 视频资产字典
            merge: 是否合并视频
            output_dir: 输出目录
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Path]: 视频路径字典
        """
        video_service = self._get_service('videodownloader')  # 使用正确的服务名称
        if not video_service:
            return {}

        try:
            # 合并视频检查
            if merge:
                output_path = (output_dir or NBAConfig.PATHS.VIDEO_DIR) / f"highlight_{game_id}.mp4"
                if not force_reprocess and output_path.exists():
                    self.logger.info(f"检测到已存在的处理结果: {output_path}")
                    return {"merged": output_path}

            # 下载视频
            video_paths = video_service.batch_download_videos(videos, game_id, force_reprocess=force_reprocess)
            if not video_paths:
                return {}

            # 如果不需要合并，直接返回
            if not merge or not self.video_processor:
                return video_paths

            # 获取所有视频路径
            video_files = list(video_paths.values())

            # 按事件ID排序
            video_files.sort(key=self._extract_event_id)

            # 合并视频
            output_path = (output_dir or NBAConfig.PATHS.VIDEO_DIR) / f"highlight_{game_id}.mp4"
            merged = self.video_processor.merge_videos(
                video_files,
                output_path,
                remove_watermark=True,
                force_reprocess=force_reprocess
            )
            return {"merged": merged} if merged else video_paths

        except Exception as e:
            self.logger.error(f"处理比赛视频失败: {e}")
            return {}

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


    def get_player_analysis(self,
                            player_name: Optional[str] = None,
                            output_dir: Optional[Path] = None,
                            request_delay: float = 1.0,
                            force_reprocess: bool = False) -> Dict[str, Union[Path, Dict]]:
        """获取球员进攻分析（添加增量处理）"""
        import time
        video_service = self._get_service('videodownloader')  # 使用正确的服务名称
        if not video_service or not self.data_service or not self.video_processor:
            return {}

        try:
            # 获取基础信息
            player_id = self.get_player_id_by_name(player_name or self.config.default_player)
            if not player_id:
                return {}

            # 检查输出目录是否已存在GIF
            gif_dir = (output_dir or NBAConfig.PATHS.VIDEO_DIR) / f"player_analysis_{player_id}"
            if not force_reprocess and gif_dir.exists() and any(gif_dir.glob("*.gif")):
                self.logger.info(f"检测到已存在的分析结果: {gif_dir}")
                # 这里可以进一步处理返回现有结果，但需要额外代码
                # 简单起见，仍然继续处理以获取完整结果

            game = self.data_service.get_game(self.config.default_team)
            if not game:
                return {}

            # 获取并下载视频
            videos = video_service.get_game_videos(
                game_id=game.game_data.game_id,
                player_id=player_id,
                context_measure=ContextMeasure.FGM
            )
            if not videos:
                return {}

            # 添加请求间隔
            if request_delay > 0:
                self.logger.info(f"等待 {request_delay} 秒...")
                time.sleep(request_delay)

            video_paths = video_service.batch_download_videos(
                videos,
                game.game_data.game_id,
                force_reprocess=force_reprocess
            )
            if not video_paths:
                return {}

            # 获取事件描述
            events = game.filter_events(
                player_id=player_id,
                action_types={'shot'}
            )

            # 生成GIF并关联事件描述
            gif_dir.mkdir(parents=True, exist_ok=True)

            gif_results = self.video_processor.batch_convert_to_gif(
                list(video_paths.values()),
                gif_dir,
                force_reprocess=force_reprocess
            )

            if not gif_results:
                return {}

            # 关联事件描述和GIF
            analysis_results = {
                "gifs": gif_results,
                "events": events
            }

            return analysis_results

        except Exception as e:
            self.logger.error(f"获取球员分析失败: {e}")
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
            self.logger.error("服务不可用")
            return None

        try:
            # 获取比赛数据
            game = data_service.get_game(team or self.config.default_team)
            if not game:
                self.logger.error("未找到比赛数据")
                return None

            # 获取球员ID
            player_id = self.get_player_id_by_name(player_name or self.config.default_player)
            if not player_id:
                self.logger.error(f"未找到球员: {player_name or self.config.default_player}")
                return None

            # 直接使用Game模型的get_shot_data方法获取投篮数据
            shots = game.get_shot_data(player_id)
            if not shots:
                self.logger.error("未找到投篮数据")
                return None

            # 构建标题
            if not title and player_name:
                formatted_date = game.game_data.game_time_beijing.strftime("%Y年%m月%d日")
                title = f"{player_name} 投篮分布图\n{formatted_date}"

            # 准备输出路径
            output_filename = f"scoring_impact_{game.game_data.game_id}_{player_id}.png"
            output_path = str(NBAConfig.PATHS.PICTURES_DIR / output_filename)

            # 调用图表服务绘制投篮图
            fig, _ = chart_service.plot_player_scoring_impact(
                shots=shots,
                player_id=player_id,
                title=title,
                output_path=output_path
            )

            if fig:
                self.logger.info(f"已生成得分影响力图: {output_path}")
                return Path(output_path)
            else:
                self.logger.error("图表生成失败")
                return None

        except Exception as e:
            self.logger.error(f"绘制得分影响力图失败: {str(e)}", exc_info=True)
            self._update_service_status('chart', ServiceStatus.DEGRADED, str(e))
            return None

    def plot_team_shots(self,
                        team: Optional[str] = None,
                        title: Optional[str] = None) -> Optional[Path]:
        """绘制球队所有球员的投篮图"""
        chart_service = self._get_service('chart')
        data_service = self._get_service('data')

        if not (chart_service and data_service):
            self.logger.error("服务不可用")
            return None

        try:
            # 获取比赛数据
            game = data_service.get_game(team or self.config.default_team)
            if not game:
                self.logger.error("未找到比赛数据")
                return None

            # 获取球队ID
            team_id = self.get_team_id_by_name(team or self.config.default_team)
            if not team_id:
                self.logger.error(f"未找到球队: {team or self.config.default_team}")
                return None

            self.logger.info(f"准备为球队 {team or self.config.default_team} (ID: {team_id}) 生成投篮图")

            # 构建默认标题
            if not title:
                formatted_date = game.game_data.game_time_beijing.strftime("%Y年%m月%d日")
                title = f"{team or self.config.default_team} 球队投篮分布图\n{formatted_date}"

            # 准备输出路径
            output_filename = f"team_shots_{game.game_data.game_id}_{team_id}.png"
            output_path = str(NBAConfig.PATHS.PICTURES_DIR / output_filename)

            self.logger.info(f"开始生成球队投篮图，输出路径: {output_path}")

            # 调用图表服务绘制球队投篮图
            fig = chart_service.plot_team_shots(
                game=game,
                team_id=team_id,
                title=title,
                output_path=output_path
            )

            if fig:
                self.logger.info(f"已生成球队投篮图: {output_path}")
                return Path(output_path)
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