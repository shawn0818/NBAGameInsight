# nba/services/nba_service.py
"""NBA服务统一接口模块

这个模块提供了NBA数据服务的统一接口，整合了以下功能：
1. 数据获取和处理 (game_data_service)
2. 视频下载和转换 (game_video_service)
3. 数据展示和格式化 (game_display_service)
4. 图表生成 (game_charts_service)
5. AI辅助处理 (ai_processor)

主要类:
- NBAServiceConfig: 统一的服务配置
- ServiceStatus: 服务状态枚举
- ServiceHealth: 服务健康状态记录
- NBAService: 主服务类
"""
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import logging
import time

from nba.services.game_data_service import NBAGameDataProvider, ServiceConfig
from nba.services.game_video_service import GameVideoService, VideoOutputConfig
from nba.services.game_display_service import DisplayService, DisplayConfig
from nba.services.game_charts_service import GameChartsService, ChartStyleConfig
from utils.ai_processor import AIProcessor, AIConfig
from nba.models.video_model import ContextMeasure, VideoAsset  # [新增] 导入VideoAsset
from config.nba_config import NBAConfig
from utils.gif_converter import GIFConfig


# ===========================
# 1. 各子模块配置
# ===========================

@dataclass
class NBAServiceConfig:
    """NBA服务统一配置类

    整合了所有子服务的配置参数，提供统一的配置管理。
    使用dataclass的field添加元数据和验证信息。

    属性:
        基础配置:
            team (str): 默认球队名称
            player (str): 默认球员名称
            date_str (str): 日期字符串
            language (str): 显示语言

        AI配置:
            use_ai (bool): 是否使用AI服务
            ai_api_key (str): AI服务API密钥
            ai_base_url (str): AI服务基础URL

        视频配置:
            video_format (str): 视频输出格式 (mp4/gif)
            video_quality (str): 视频质量 (sd/hd)
            show_progress (bool): 是否显示进度条
            gif_config (GIFConfig): GIF转换配置

        存储配置:
            storage_paths (Dict[str, Path]): 各类文件的存储路径
            cache_size (int): 缓存大小

        其他配置:
            auto_refresh (bool): 是否自动刷新数据
            use_pydantic_v2 (bool): 是否使用Pydantic v2
    """

    # 基础配置
    team: str = field(default="Lakers", metadata={"description": "球队名称"})
    player: str = field(default="LeBron James", metadata={"description": "球员名称"})
    date_str: str = field(default="last", metadata={"description": "日期字符串"})
    language: str = field(default="zh_CN", metadata={"description": "显示语言"})

    # AI配置
    use_ai: bool = field(default=True, metadata={"description": "是否使用AI服务"})
    ai_api_key: Optional[str] = field(default=None, metadata={"description": "AI API密钥"})
    ai_base_url: Optional[str] = field(default=None, metadata={"description": "AI API基础URL"})

    # 图表配置
    chart_style: ChartStyleConfig = field(
        default_factory=ChartStyleConfig,
        metadata={"description": "图表样式配置"}
    )

    # 视频配置
    video_format: str = field(
        default='mp4',
        metadata={
            "description": "视频输出格式",
            "validators": ["one_of", ["mp4", "gif"]]
        }
    )
    video_quality: str = field(
        default='hd',
        metadata={
            "description": "视频质量",
            "validators": ["one_of", ["sd", "hd"]]
        }
    )

    # GIF配置
    gif_config: Optional[GIFConfig] = field(
        default=None,
        metadata={"description": "GIF配置参数"}
    )

    # 存储配置
    storage_paths: Dict[str, Path] = field(
        default_factory=lambda: {
            "figure": NBAConfig.PATHS.PICTURES_DIR,
            "cache": NBAConfig.PATHS.CACHE_DIR,
            "storage": NBAConfig.PATHS.STORAGE_DIR,
            "video": NBAConfig.PATHS.VIDEO_DIR,
            "gif": NBAConfig.PATHS.GIF_DIR
        },
        metadata={"description": "存储路径配置"}
    )

    # 其他配置
    cache_size: int = field(
        default=128,
        metadata={"description": "缓存大小", "min_value": 32, "max_value": 512}
    )
    auto_refresh: bool = field(default=False, metadata={"description": "自动刷新"})
    use_pydantic_v2: bool = field(default=True, metadata={"description": "使用Pydantic v2"})

    def __post_init__(self):
        """配置后初始化

        执行配置验证和默认值设置：
        1. 确保所有路径都是Path对象
        2. 为GIF格式创建默认配置（如果需要）
        """
        # 验证并转换存储路径
        for name, path in self.storage_paths.items():
            if not isinstance(path, Path):
                self.storage_paths[name] = Path(path)

        # 如果是GIF格式但没有配置，创建默认GIF配置
        if self.video_format == 'gif' and self.gif_config is None:
            self.gif_config = GIFConfig(
                fps=12,
                scale=960,
                max_retries=3,
                retry_delay=1.0
            )


# ===========================
# 2. 监测各个子模块服务
# ===========================

class ServiceStatus(Enum):
    """服务状态枚举类

    定义服务可能的状态：
    - AVAILABLE: 服务可用
    - UNAVAILABLE: 服务不可用
    - DEGRADED: 服务性能降级
    """
    AVAILABLE = "可用"
    UNAVAILABLE = "不可用"
    DEGRADED = "降级"

    def __str__(self):
        """返回中文状态描述"""
        return self.value


@dataclass
class ServiceHealth:
    """服务健康状态记录类

    记录和跟踪服务的健康状态信息。

    属性:
        status (ServiceStatus): 当前状态
        last_check (float): 最后检查时间戳
        error_count (int): 错误计数
        last_error (str): 最后一次错误信息
    """
    status: ServiceStatus
    last_check: float
    error_count: int = 0
    last_error: Optional[str] = None

    @property
    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.status == ServiceStatus.AVAILABLE

    @property
    def is_healthy(self) -> bool:
        """检查服务是否健康（可用或降级状态）"""
        return self.status != ServiceStatus.UNAVAILABLE


# ===========================
# 3. 统一协调各个子模块服务
# ===========================


class NBAService:
    """NBA数据服务统一接口,集成管理所有NBA相关服务，提供统一的接口。负责服务的初始化、状态管理、和业务功能调用。
    主要功能:
    1. 服务生命周期管理（初始化、状态监控、关闭）
    2. 数据获取和处理
    3. 视频下载和转换
    4. 数据展示和格式化
    5. 图表生成

    属性:
        config (NBAServiceConfig): 服务配置
        logger (logging.Logger): 日志记录器
        _service_status (Dict[str, ServiceHealth]): 各服务的健康状态
    """

    ## ===========================
    ## 3.1 初始化各个子模块服务
    ## ===========================

    def __init__(self, config: Optional[NBAServiceConfig] = None):
        self.config = config or NBAServiceConfig()
        self.logger = logging.getLogger(self.__class__.__name__)

        # 确保所需目录存在
        NBAConfig.PATHS.ensure_directories()

        # 服务健康状态
        self._service_status = {
            'data': ServiceHealth(ServiceStatus.UNAVAILABLE, time.time()),
            'display': ServiceHealth(ServiceStatus.UNAVAILABLE, time.time()),
            'chart': ServiceHealth(ServiceStatus.UNAVAILABLE, time.time()),
            'video': ServiceHealth(ServiceStatus.UNAVAILABLE, time.time()),
            'ai': ServiceHealth(ServiceStatus.UNAVAILABLE, time.time())
        }

        # 初始化服务
        self._init_services()

        # 记录可用服务
        available = [name for name, status in self._service_status.items()
                     if status.is_available]
        self.logger.info(f"可用服务: {available}")

    def _init_services(self) -> None:
        """初始化所有子服务

        按依赖顺序初始化各个服务：
        1. AI服务 (可选)
        2. 数据服务 (核心)
        3. 显示服务 (依赖数据服务)
        4. 图表服务 (依赖数据服务)
        5. 视频服务
        """
        self._init_ai_service()
        self._init_data_service()
        if self._service_status['data'].is_available:
            self._init_display_service()
            self._init_chart_service()
        self._init_video_service()  # 确保在最后初始化视频服务

    def _init_ai_service(self) -> None:
        """初始化AI服务"""
        if not (self.config.use_ai and self.config.ai_api_key and self.config.ai_base_url):
            return

        try:
            ai_config = AIConfig(
                api_key=self.config.ai_api_key,
                base_url=self.config.ai_base_url
            )
            self._ai_service = AIProcessor(ai_config)
            self._update_service_status('ai', ServiceStatus.AVAILABLE)
        except Exception as e:
            self.logger.error(f"AI服务初始化失败: {str(e)}")
            self._update_service_status('ai', ServiceStatus.UNAVAILABLE, str(e))

    def _init_data_service(self) -> None:
        """初始化数据服务"""
        try:
            service_config = ServiceConfig(
                default_team=self.config.team,
                default_player=self.config.player,
                date_str=self.config.date_str,
                cache_dir=self.config.storage_paths['cache'],
                cache_size=self.config.cache_size,
                auto_refresh=self.config.auto_refresh,
                use_pydantic_v2=self.config.use_pydantic_v2
            )

            self._data_service = NBAGameDataProvider(service_config)
            self._update_service_status('data', ServiceStatus.AVAILABLE)
        except Exception as e:
            self.logger.error(f"数据服务初始化失败: {str(e)}")
            self._update_service_status('data', ServiceStatus.UNAVAILABLE, str(e))

    def _init_display_service(self) -> None:
        """初始化显示服务"""
        try:
            display_config = DisplayConfig(
                language=self.config.language,
                cache_size=self.config.cache_size
            )

            self._display_service = DisplayService(
                display_config=display_config,
                ai_service=getattr(self, '_ai_service', None)  # [修改] 使用getattr
            )
            self._update_service_status('display', ServiceStatus.AVAILABLE)
        except Exception as e:
            self.logger.error(f"显示服务初始化失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.UNAVAILABLE, str(e))

    def _init_chart_service(self) -> None:
        """初始化图表服务"""
        try:
            self._chart_service = GameChartsService(
                game_data_service=self._data_service,
                figure_path=self.config.storage_paths['figure'],
                style_config=self.config.chart_style  # 传递 ChartStyleConfig
            )
            self._update_service_status('chart', ServiceStatus.AVAILABLE)
        except Exception as e:
            self.logger.error(f"图表服务初始化失败: {str(e)}")
            self._update_service_status('chart', ServiceStatus.UNAVAILABLE, str(e))


    def _init_video_service(self) -> None:
        """初始化视频服务"""
        try:
            video_config = VideoOutputConfig(
                format=self.config.video_format,
                quality=self.config.video_quality,
                gif_config=self.config.gif_config,
                max_retries=3,
                retry_delay=1.0
            )

            self._video_service = GameVideoService(video_config=video_config)
            self._update_service_status('video', ServiceStatus.AVAILABLE)

        except Exception as e:
            self.logger.error(f"视频服务初始化失败: {str(e)}")
            self._update_service_status('video', ServiceStatus.UNAVAILABLE, str(e))


    def _update_service_status(
            self,
            service_name: str,
            status: ServiceStatus,
            error: Optional[str] = None
    ) -> None:
        """更新服务健康状态

        Args:
            service_name: 服务名称
            status: 新状态
            error: 错误信息（可选）
        """
        health = self._service_status.get(service_name)
        if health:
            health.status = status
            health.last_check = time.time()
            if error:
                health.error_count += 1
                health.last_error = error

    def get_service_status(self) -> Dict[str, ServiceStatus]:
        """获取所有服务的当前状态

        Returns:
            Dict[str, ServiceStatus]: 服务名称到状态的映射
        """
        return {name: status.status for name, status in self._service_status.items()}


    ## ===========================
    ## 3.2 调用个各子模块服务
    ## ===========================


    ### =============3.2.1调用gamedisplay子模块==============

    def format_basic_game_info(self, team: Optional[str] = None, date: Optional[str] = None) -> Dict[str, Any]:
        """格式化基础比赛信息"""
        if not self._service_status['display'].is_available or not self._service_status['data'].is_available:
            self.logger.error("显示服务或数据服务不可用")
            return {}

        try:
            game = self._data_service.get_game(team or self.config.team, date)
            if not game:
                return {}

            game_data = self._data_service.get_basic_game_info(game)
            return self._display_service.format_basic_game_info(game_data)
        except Exception as e:
            self.logger.error(f"格式化基础比赛信息失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.DEGRADED, str(e))
            return {}

    def format_player_stats(self, team: Optional[str] = None, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """格式化所有球员统计数据"""
        if not self._service_status['display'].is_available or not self._service_status['data'].is_available:
            self.logger.error("显示服务或数据服务不可用")
            return []

        try:
            game = self._data_service.get_game(team or self.config.team, date)
            if not game:
                return []

            game_stats = self._data_service.get_team_game_stats(game)
            if not game_stats:
                return []

            all_players_stats = []
            for team_type in ['home_team', 'away_team']:
                team_data = game_stats.get(team_type)
                if team_data and hasattr(team_data, 'players'):
                    for player in team_data.players:
                        if player.has_played:  # 只返回上场球员的数据
                            all_players_stats.append(
                                self._display_service.format_player_stats(player)
                            )
            return all_players_stats
        except Exception as e:
            self.logger.error(f"格式化球员统计数据失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.DEGRADED, str(e))
            return []

    def format_team_stats(self, team: Optional[str] = None, date: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """格式化两队统计数据"""
        if not self._service_status['display'].is_available or not self._service_status['data'].is_available:
            self.logger.error("显示服务或数据服务不可用")
            return {}

        try:
            game = self._data_service.get_game(team or self.config.team, date)
            if not game:
                return {}

            game_data = self._data_service.get_basic_game_info(game)
            return {
                "home_team": self._display_service.format_team_stats(game_data, "home"),
                "away_team": self._display_service.format_team_stats(game_data, "away")
            }
        except Exception as e:
            self.logger.error(f"格式化球队统计数据失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.DEGRADED, str(e))
            return {}

    def analyze_game_events(self, team: Optional[str] = None, date: Optional[str] = None) -> Dict[str, Any]:
        """分析比赛事件"""
        if not self._service_status['display'].is_available or not self._service_status['data'].is_available:
            self.logger.error("显示服务或数据服务不可用")
            return {}

        try:
            game = self._data_service.get_game(team or self.config.team, date)
            if not game:
                return {}

            events = self._data_service.get_game_events(game)
            if not events:
                return {}

            return self._display_service.analyze_game_events(events)
        except Exception as e:
            self.logger.error(f"分析比赛事件失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.DEGRADED, str(e))
            return {}

    def display_game_info(self, team: Optional[str] = None, date: Optional[str] = None) -> Dict[str, Any]:
        """显示完整比赛信息"""
        if not self._service_status['display'].is_available or not self._service_status['data'].is_available:
            self.logger.error("显示服务或数据服务不可用")
            return {}

        try:
            game = self._data_service.get_game(team or self.config.team, date)
            if not game:
                return {}

            game_data = self._data_service.get_basic_game_info(game)
            events = self._data_service.get_game_events(game)

            return self._display_service.display_game_info(game_data, events)
        except Exception as e:
            self.logger.error(f"显示完整比赛信息失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.DEGRADED, str(e))
            return {}


    ### =============3.2.2调用gamevideo子模块==============

    def get_game_videos(self, context_measure: str = "FGM") -> Dict[str, Path]:
        """获取比赛视频"""
        if not self._service_status['video'].is_available:
            self.logger.error("视频服务不可用")
            return {}

        if not self._service_status['data'].is_available:
            self.logger.error("数据服务不可用")
            return {}

        try:
            # 验证视频类型
            if not hasattr(ContextMeasure, context_measure):
                raise ValueError(f"无效的视频类型: {context_measure}")

            # 获取比赛信息
            game = self._data_service.get_game(self.config.team)
            if not game:
                self.logger.error("未找到比赛信息")
                return {}

            game_id = game.game.gameId
            player_id = self._get_player_id(game)

            self.logger.info(
                f"准备获取视频 - 比赛ID: {game_id}, "
                f"球员: {self.config.player}, "
                f"球员ID: {player_id}, "
                f"类型: {context_measure}"
            )

            if not player_id:
                self.logger.error(f"无法获取球员 {self.config.player} 的ID")
                return {}

            # 获取视频资源
            video_assets = self._video_service.get_game_videos(
                game_id=game_id,
                player_id=player_id,
                context_measure=ContextMeasure[context_measure]
            )

            if not video_assets:
                self.logger.warning(f"未找到 {context_measure} 类型的视频资产")
                return {}

            self.logger.info(f"成功获取 {len(video_assets)} 个视频资产，开始处理...")

            # 处理视频
            results = self._video_service.batch_process_videos(
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

    ### ============ 3.2.3调用gamecharts子模块===============

    def plot_player_scoring_impact(self,
                                   team: Optional[str] = None,
                                   player_id: Optional[int] = None,
                                   title: Optional[str] = None) -> Optional[Path]:
        """绘制球员得分影响力图

        Args:
            team: 球队名称（可选）
            player_id: 球员ID（可选）
            title: 图表标题（可选）

        Returns:
            Optional[Path]: 生成的图表文件路径
        """
        if not self._service_status['chart'].is_available:
            self.logger.error("图表服务不可用")
            return None

        try:
            game = self._data_service.get_game(team or self.config.team)
            if not game:
                self.logger.error("未找到比赛数据")
                return None

            player_id = player_id or self._get_player_id(game)
            if not player_id:
                self.logger.error("无法获取球员ID")
                return None

            # 生成输出文件名
            output_filename = f"scoring_impact_{game.game.gameId}.png"

            fig, _ = self._chart_service.plot_player_scoring_impact(
                game=game,
                player_id=player_id,
                title=title,
                output_path=output_filename
            )

            if fig:
                output_path = self.config.storage_paths['figure'] / output_filename
                self.logger.info(f"已生成得分影响力图: {output_path}")
                return output_path
            else:
                self.logger.error("图表生成失败")
                return None

        except Exception as e:
            self.logger.error(f"绘制得分影响力图失败: {str(e)}", exc_info=True)
            self._update_service_status('chart', ServiceStatus.DEGRADED, str(e))
            return None

    ### =============3.2.4辅助方法==============

    def _get_player_id(self, game: Any) -> Optional[int]:
        """获取球员ID

        Args:
            game: 比赛数据对象

        Returns:
            Optional[int]: 球员ID
        """
        if not self.config.player:
            return None

        try:
            player_name = self.config.player.lower()
            for team in [game.game.homeTeam, game.game.awayTeam]:
                for player in team.players:
                    if player.name.lower() == player_name:
                        return player.personId
            return None
        except Exception as e:
            self.logger.error(f"获取球员ID失败: {str(e)}")
            return None

    ### =============3.2.5 资源管理 ==============

    def clear_cache(self) -> None:
        """清理所有服务的缓存

        包括数据缓存、显示缓存和临时文件
        """
        try:
            if hasattr(self, '_data_service'):
                self._data_service.clear_cache()
            if hasattr(self, '_display_service'):
                self._display_service.clear_cache()
            if hasattr(self, '_video_service'):
                self._video_service.close()
        except Exception as e:
            self.logger.error(f"清理缓存失败: {str(e)}")

    def close(self) -> None:
        """关闭服务并清理资源"""
        try:
            self.clear_cache()
        except Exception as e:
            self.logger.error(f"关闭服务时出错: {str(e)}")

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