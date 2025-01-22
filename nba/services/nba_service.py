# nba/services/nba_service.py

from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import logging
import time

from nba.services.game_data_service import NBAGameDataProvider, ServiceConfig
from nba.services.game_video_service import GameVideoService, VideoOutputConfig
from nba.services.game_display_service import DisplayService, DisplayConfig
from nba.services.game_charts_service import GameChartsService
from nba.models.video_model import ContextMeasure
from config.nba_config import NBAConfig


@dataclass
class NBAServiceConfig:
    """NBA服务统一配置"""
    # 基础配置
    team: str = "Lakers"
    player: str = "LeBron James"
    date_str: str = "last"
    language: str = "zh_CN"

    # 视频配置
    video_quality: str = "hd"
    to_gif: bool = False
    compress_video: bool = False
    compression_preset: str = 'medium'
    compression_crf: int = 23
    compression_audio_bitrate: str = '128k'
    video_fps: int = 12
    video_scale: int = 960
    video_show_progress: bool = True
    video_max_workers: int = 3  # 新增: 最大并行下载数

    # 存储路径配置
    figure_path: Path = NBAConfig.PATHS.PICTURES_DIR
    cache_dir: Path = NBAConfig.PATHS.CACHE_DIR
    storage_dir: Path = NBAConfig.PATHS.STORAGE_DIR
    video_dir: Path = NBAConfig.PATHS.VIDEO_DIR
    gif_dir: Path = NBAConfig.PATHS.GIF_DIR

    # 其他配置
    show_advanced_stats: bool = True
    cache_size: int = 128
    auto_refresh: bool = False
    use_pydantic_v2: bool = True


class ServiceStatus(Enum):
    """服务状态枚举"""
    AVAILABLE = "可用"
    UNAVAILABLE = "不可用"
    DEGRADED = "降级"


@dataclass
class ServiceHealth:
    """服务健康状态"""
    status: ServiceStatus
    last_check: float
    error_count: int = 0
    last_error: Optional[str] = None

    @property
    def is_available(self) -> bool:
        return self.status == ServiceStatus.AVAILABLE


class NBAService:
    """NBA数据服务统一接口"""

    def __init__(self, config: Optional[NBAServiceConfig] = None):
        """初始化服务"""
        self.config = config or NBAServiceConfig()
        self.logger = logging.getLogger(self.__class__.__name__)

        # 确保所需目录存在
        NBAConfig.PATHS.ensure_directories()

        # 服务健康状态
        self._service_status = {
            'data': ServiceHealth(ServiceStatus.UNAVAILABLE, time.time()),
            'display': ServiceHealth(ServiceStatus.UNAVAILABLE, time.time()),
            'chart': ServiceHealth(ServiceStatus.UNAVAILABLE, time.time()),
            'video': ServiceHealth(ServiceStatus.UNAVAILABLE, time.time())
        }

        # 初始化服务
        self._init_services()

        # 记录可用服务
        available = [name for name, status in self._service_status.items()
                     if status.is_available]
        self.logger.info(f"可用服务: {available}")

    def _init_services(self) -> None:
        """分离式初始化各个服务"""
        self._init_data_service()
        if self._service_status['data'].is_available:
            self._init_display_service()
            self._init_chart_service()
        self._init_video_service()

    def _init_data_service(self) -> None:
        """初始化数据服务"""
        try:
            # 创建数据服务配置
            service_config = ServiceConfig(
                default_team=self.config.team,
                default_player=self.config.player,
                date_str=self.config.date_str,
                cache_dir=self.config.cache_dir,
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
            # 创建显示服务配置
            display_config = DisplayConfig(
                language=self.config.language,
                show_advanced_stats=self.config.show_advanced_stats,
                cache_size=self.config.cache_size
            )

            self._display_service = DisplayService(
                game_data_service=self._data_service,
                display_config=display_config
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
                figure_path=self.config.figure_path
            )
            self._update_service_status('chart', ServiceStatus.AVAILABLE)
        except Exception as e:
            self.logger.error(f"图表服务初始化失败: {str(e)}")
            self._update_service_status('chart', ServiceStatus.UNAVAILABLE, str(e))

    def _init_video_service(self) -> None:
        """初始化视频服务"""
        try:
            # 创建视频服务配置
            video_config = VideoOutputConfig(
                format='gif' if self.config.to_gif else 'mp4',
                quality=self.config.video_quality,
                compress=self.config.compress_video,
                compression_preset=self.config.compression_preset,
                compression_crf=self.config.compression_crf,
                compression_audio_bitrate=self.config.compression_audio_bitrate,
                fps=self.config.video_fps,
                scale=self.config.video_scale,
                show_progress=self.config.video_show_progress,
                max_workers=self.config.video_max_workers  # 设置并行下载数
            )

            self._video_service = GameVideoService(video_config=video_config)
            self._update_service_status('video', ServiceStatus.AVAILABLE)
        except Exception as e:
            self.logger.error(f"视频服务初始化失败: {str(e)}")
            self._update_service_status('video', ServiceStatus.UNAVAILABLE, str(e))

    def _update_service_status(self, service_name: str,
                               status: ServiceStatus, error: Optional[str] = None) -> None:
        """更新服务状态"""
        health = self._service_status.get(service_name)
        if health:
            health.status = status
            health.last_check = time.time()
            if error:
                health.error_count += 1
                health.last_error = error

    def get_service_status(self) -> Dict[str, ServiceStatus]:
        """获取所有服务状态"""
        return {name: status.status for name, status in self._service_status.items()}

    def get_game_summary(self,
                          team: Optional[str] = None,
                          date: Optional[str] = None) -> Dict[str, Any]:
        """获取比赛概况"""
        summary = {}

        if not self._service_status['data'].is_available:
            self.logger.error("数据服务不可用")
            return summary

        try:
            game = self._data_service.get_game(team or self.config.team, date)
            if not game:
                return summary

            # 基础信息
            game_data = game.game
            summary["basic_info"] = {
                "game_id": game_data.gameId,
                "gameTimeLocal": game_data.gameTimeLocal
            }

            # 格式化信息(如果显示服务可用)
            if self._service_status['display'].is_available:
                try:
                    summary.update({
                        "formatted_info": self._display_service.format_game_basic_info(game_data),
                        "status": self._display_service.format_game_status(
                            game_data.homeTeam,
                            game_data.awayTeam
                        )
                    })
                except Exception as e:
                    self.logger.error(f"格式化比赛信息失败: {str(e)}")
                    self._update_service_status('display', ServiceStatus.DEGRADED, str(e))

            # 统计信息
            try:
                summary["statistics"] = self._data_service.get_game_stats(game)
            except Exception as e:
                self.logger.error(f"获取比赛统计失败: {str(e)}")

            return summary

        except Exception as e:
            self.logger.error(f"获取比赛概况失败: {str(e)}")
            self._update_service_status('data', ServiceStatus.DEGRADED, str(e))
            return summary

    def get_game_videos(self, context_measure: str = "FGM") -> Dict[str, Path]:
        """获取比赛视频"""
        if not self._service_status['video'].is_available:
            self.logger.error("视频服务不可用")
            return {}

        if not self._service_status['data'].is_available:
            self.logger.error("数据服务不可用，无法获取比赛信息")
            return {}

        try:
            game = self._data_service.get_game(self.config.team)
            if not game:
                return {}

            player_id = self._get_player_id(game)
            game_id = game.game.gameId  # 获取game_id

            videos = self._video_service.get_game_videos(
                game_id=game_id,
                player_id=player_id,
                context_measure=ContextMeasure[context_measure]
            )

            if not videos:
                return {}

            return self._video_service.batch_process_videos(
                videos=videos,
                game_id=game_id  # 传入game_id参数
            )

        except Exception as e:
            self.logger.error(f"获取视频失败: {str(e)}")
            self._update_service_status('video', ServiceStatus.DEGRADED, str(e))
            return {}

    def plot_player_scoring_impact(self,
                                   team: Optional[str] = None,
                                   player_id: Optional[int] = None,
                                   title: Optional[str] = None) -> Optional[Path]:
        """绘制球员得分影响力图"""
        if not self._service_status['chart'].is_available:
            self.logger.error("图表服务不可用")
            return None

        try:
            game = self._data_service.get_game(team or self.config.team)
            if not game:
                return None

            player_id = player_id or self._get_player_id(game)
            if not player_id:
                self.logger.error("无法获取球员ID")
                return None

            fig, _ = self._chart_service.plot_player_scoring_impact(
                game=game,
                player_id=player_id,
                title=title,
                output_path=f"scoring_impact_{game.game.gameId}.png"
            )

            return self.config.figure_path / f"scoring_impact_{game.game.gameId}.png" if fig else None

        except Exception as e:
            self.logger.error(f"绘制得分影响力图失败: {str(e)}")
            self._update_service_status('chart', ServiceStatus.DEGRADED, str(e))
            return None

    def _get_player_id(self, game: Any) -> Optional[int]:
        """获取球员ID"""
        if not self.config.player:
            return None

        try:
            player_obj = next(
                (p for t in [game.game.homeTeam, game.game.awayTeam]
                 for p in t.players if p.name.lower() == self.config.player.lower()),
                None
            )
            return player_obj.personId if player_obj else None
        except Exception:
            return None

    def __enter__(self):
        """同步上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """同步上下文管理器出口"""
        self.close()

    def close(self):
        """关闭并清理资源"""
        try:
            if hasattr(self, '_data_service'):
                self._data_service.clear_cache()
            if hasattr(self, '_video_service'):
                self._video_service.close()
        except Exception as e:
            self.logger.error(f"清理资源失败: {str(e)}")