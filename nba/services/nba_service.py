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
from nba.services.ai_service import AIService, AIConfig
from nba.models.video_model import ContextMeasure
from config.nba_config import NBAConfig


# ===========================
# 1. 各子模块配置
# ===========================

@dataclass
class NBAServiceConfig:
    """NBA服务统一配置"""
    # 基础配置
    team: str = "Lakers"
    player: str = "LeBron James"
    date_str: str = "last"
    language: str = "zh_CN"

    # AI配置
    use_ai: bool = True
    ai_api_key: Optional[str] = None
    ai_base_url: Optional[str] = None

    # **DisplayService 配置 **
    format_type: str = "translate"  # 新增 format_type 参数


    # 视频videoservice配置
    video_quality: str = "hd"
    to_gif: bool = False
    compress_video: bool = False
    compression_preset: str = 'medium'
    compression_crf: int = 23
    compression_audio_bitrate: str = '128k'
    video_fps: int = 12
    video_scale: int = 960
    video_show_progress: bool = True
    video_max_workers: int = 3

    # 存储路径配置
    figure_path: Path = NBAConfig.PATHS.PICTURES_DIR
    cache_dir: Path = NBAConfig.PATHS.CACHE_DIR
    storage_dir: Path = NBAConfig.PATHS.STORAGE_DIR
    video_dir: Path = NBAConfig.PATHS.VIDEO_DIR
    gif_dir: Path = NBAConfig.PATHS.GIF_DIR

    # 其他配置
    cache_size: int = 128
    auto_refresh: bool = False
    use_pydantic_v2: bool = True

# ===========================
# 2. 监测各个子模块服务
# ===========================

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

# ===========================
# 3. 统一协调各个子模块服务
# ===========================


class NBAService:
    """NBA数据服务统一接口"""

    ## ===========================
    ## 3.1 初始化各个子模块服务
    ## ===========================

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
        """初始化各个服务"""
        self._init_ai_service()
        self._init_data_service()
        if self._service_status['data'].is_available:
            self._init_display_service()
            self._init_chart_service()
        self._init_video_service()

    def _init_ai_service(self) -> None:
        """初始化AI服务"""
        if not (self.config.use_ai and self.config.ai_api_key and self.config.ai_base_url):
            return

        try:
            ai_config = AIConfig(
                api_key=self.config.ai_api_key,
                base_url=self.config.ai_base_url
            )
            self._ai_service = AIService(ai_config)
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
            display_config = DisplayConfig(
                language=self.config.language,
                cache_size=self.config.cache_size,
                use_ai=self.config.use_ai,
                format_type=self.config.format_type,  # 使用 self.config.format_type
            )

            self._display_service = DisplayService(
                display_config=display_config,
                ai_service=self._ai_service if hasattr(self, '_ai_service') else None
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
                max_workers=self.config.video_max_workers
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

    ## ===========================
    ## 3.2 调用个各子模块服务
    ## ===========================


    ### =============3.2.1调用gamedisplay子模块==============

    def format_game_content(self,
                            team: Optional[str] = None,
                            date: Optional[str] = None,
                            content_type: str = "full") -> Optional[str]:
        """格式化比赛内容"""
        if not self._service_status['display'].is_available:
            self.logger.error("显示服务不可用")
            return None

        try:
            game = self._data_service.get_game(team or self.config.team, date)
            if not game:
                self.logger.warning("未找到比赛数据")
                return None

            game_data = self._data_service.get_basic_game_info(game)

            # 如果是完整报告，需要传入 events
            if content_type == "full":
                events = self._data_service.get_game_events(game)
                return self._display_service.generate_game_report(game_data, events)
            elif content_type == "brief":
                return self._display_service.format_game_basic_info(game_data)
            elif content_type == "technical":
                home_team = game_data.homeTeam
                away_team = game_data.awayTeam
                return self._display_service.format_team_stats(home_team, away_team)
            else:
                return self._display_service.format_game_basic_info(game_data)

        except Exception as e:
            self.logger.error(f"格式化比赛内容失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.DEGRADED, str(e))
            return None

    def get_player_statistics(self,
                              team: Optional[str] = None,
                              date: Optional[str] = None,
                              player_name: Optional[str] = None) -> Optional[str]:
        """获取球员统计数据"""
        if not self._service_status['display'].is_available:
            self.logger.error("显示服务不可用")
            return None

        try:
            game = self._data_service.get_game(team or self.config.team, date)
            if not game:
                return None

            game_data = self._data_service.get_basic_game_info(game)

            # 查找指定球员
            player = None
            player_name = player_name or self.config.player
            if player_name:
                for team_players in [game_data.homeTeam.players, game_data.awayTeam.players]:
                    for p in team_players:
                        if p.name.lower() == player_name.lower():
                            player = p
                            break
                    if player:
                        break

            if not player:
                self.logger.warning(f"未找到球员: {player_name}")
                return None

            return self._display_service.format_player_stats(player)

        except Exception as e:
            self.logger.error(f"获取球员统计失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.DEGRADED, str(e))
            return None

    def get_game_highlights(self,
                            team: Optional[str] = None,
                            date: Optional[str] = None) -> Optional[str]:
        """获取比赛精彩瞬间"""
        if not self._service_status['display'].is_available:
            self.logger.error("显示服务不可用")
            return None

        try:
            game = self._data_service.get_game(team or self.config.team, date)
            if not game:
                return None

            game_data = self._data_service.get_basic_game_info(game)
            events = self._data_service.get_game_events(game)

            return self._display_service.format_game_timeline(game_data, events)

        except Exception as e:
            self.logger.error(f"获取比赛精彩瞬间失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.DEGRADED, str(e))
            return None

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

            game_data = self._data_service.get_basic_game_info(game)

            # 基础信息
            summary["basic_info"] = {
                "game_id": game_data.gameId,
                "gameTimeLocal": game_data.gameTimeLocal
            }

            # 格式化信息
            if self._service_status['display'].is_available:
                try:
                    summary.update({
                        "formatted_info": self._display_service.format_game_basic_info(game_data),
                        "game_status": self._display_service.format_game_status(game_data)
                    })

                except Exception as e:
                    self.logger.error(f"格式化比赛信息失败: {str(e)}")
                    self._update_service_status('display', ServiceStatus.DEGRADED, str(e))

            # 统计信息
            try:
                team_stats = self._data_service.get_team_game_stats(game)
                if team_stats:
                    summary["team_stats"] = team_stats

            except Exception as e:
                self.logger.error(f"获取比赛统计失败: {str(e)}")

            return summary

        except Exception as e:
            self.logger.error(f"获取比赛概况失败: {str(e)}")
            self._update_service_status('data', ServiceStatus.DEGRADED, str(e))
            return summary

    def get_team_comparison(self,
                            team: Optional[str] = None,
                            date: Optional[str] = None) -> Optional[str]:
        """获取球队数据对比"""
        if not self._service_status['display'].is_available:
            self.logger.error("显示服务不可用")
            return None

        try:
            game = self._data_service.get_game(team or self.config.team, date)
            if not game:
                return None

            game_data = self._data_service.get_basic_game_info(game)
            return self._display_service.format_team_stats(
                game_data.homeTeam,
                game_data.awayTeam
            )

        except Exception as e:
            self.logger.error(f"获取球队对比失败: {str(e)}")
            self._update_service_status('display', ServiceStatus.DEGRADED, str(e))
            return None


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
            game = self._data_service.get_game(self.config.team)
            if not game:
                return {}

            player_id = self._get_player_id(game)
            game_id = game.game.gameId

            videos = self._video_service.get_game_videos(
                game_id=game_id,
                player_id=player_id,
                context_measure=ContextMeasure[context_measure]
            )

            if not videos:
                return {}

            return self._video_service.batch_process_videos(
                videos=videos,
                game_id=game_id
            )

        except Exception as e:
            self.logger.error(f"获取视频失败: {str(e)}")
            self._update_service_status('video', ServiceStatus.DEGRADED, str(e))
            return {}

    ### ============ 3.2.3调用gamecharts子模块===============


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

    ### =============3.2.4辅助方法==============

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

    def clear_cache(self) -> None:
        """清理所有服务的缓存"""
        try:
            if hasattr(self, '_data_service'):
                self._data_service.clear_cache()
            if hasattr(self, '_display_service'):
                self._display_service.clear_cache()
            if hasattr(self, '_video_service'):
                self._video_service.close()
        except Exception as e:
            self.logger.error(f"清理缓存失败: {str(e)}")

    def __enter__(self):
        """同步上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """同步上下文管理器出口"""
        self.close()

    def close(self):
        """关闭并清理资源"""
        self.clear_cache()