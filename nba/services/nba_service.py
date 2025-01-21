# nba/services/nba_service.py
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any, List, Callable, Union
import logging
import asyncio
from pathlib import Path
from dataclasses import dataclass, field
from functools import wraps
from datetime import datetime

from nba.services.game_data_service import NBAGameDataProvider, ServiceConfig
from nba.services.game_video_service import GameVideoService
from nba.services.game_display_service import DisplayService, DisplayConfig
from nba.services.game_charts_service import GameChartsService
from nba.services.ai_service import AIConfig
from nba.models.video_model import ContextMeasure
from config.nba_config import NBAConfig

# 初始化日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class NBAServiceConfig:
    """NBA服务统一配置类"""
    # 基础配置
    default_team: str = "Lakers"  # 修改：设置默认值
    default_player: str = "LeBron James"  # 修改：设置默认值
    date_str: str = "last"  # 修改：设置默认值为 "last"

    # 显示配置
    display_language: str = "zh_CN"
    show_advanced_stats: bool = True

    # 视频配置
    video_quality: str = "hd"
    max_concurrent_downloads: int = 3
    video_output_dir: Path = NBAConfig.PATHS.VIDEO_DIR

    # AI配置
    enable_ai: bool = False
    ai_api_key: Optional[str] = None
    ai_base_url: Optional[str] = None

    # 输出配置
    output_dir: Path = NBAConfig.PATHS.PICTURES_DIR

    # 服务配置实例（内部使用）
    service_config: ServiceConfig = field(init=False)
    display_config: DisplayConfig = field(init=False)
    ai_config: Optional[AIConfig] = field(init=False)

    def __post_init__(self):
        """初始化派生配置"""
        # 配置AI服务
        self._setup_ai_config()
        # 初始化子服务配置
        self._init_service_configs()

    def _setup_ai_config(self) -> None:
        """设置AI服务配置"""
        if self.enable_ai and not self.ai_api_key:
            self.enable_ai = False
            logger.warning("未提供AI API密钥，已禁用AI功能")

        self.ai_config = AIConfig(
            api_key=self.ai_api_key,
            base_url=self.ai_base_url
        ) if self.enable_ai else None

    def _init_service_configs(self) -> None:
        """初始化子服务配置"""
        self.service_config = ServiceConfig(
            default_team=self.default_team,
            default_player=self.default_player,
            date_str=self.date_str,
            cache_dir=NBAConfig.PATHS.CACHE_DIR,
            auto_refresh=False
        )

        self.display_config = DisplayConfig(
            language=self.display_language,
            show_advanced_stats=self.show_advanced_stats
        )


def handle_service_exceptions(func: Callable) -> Callable:
    """服务层异常处理装饰器"""
    if asyncio.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"服务调用错误 - {func.__name__}: {str(e)}", exc_info=True)
                return_type = func.__annotations__.get('return')
                if return_type == Dict:
                    return {}
                elif return_type == List:
                    return []
                elif return_type == str:
                    return ""
                return None

        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"服务调用错误 - {func.__name__}: {str(e)}", exc_info=True)
                return_type = func.__annotations__.get('return')
                if return_type == Dict:
                    return {}
                elif return_type == List:
                    return []
                elif return_type == str:
                    return ""
                return None

        return sync_wrapper


class NBAService:
    """NBA数据服务统一接口"""

    def __init__(self, config: Optional[NBAServiceConfig] = None):
        """初始化NBA服务"""
        self.config = config or NBAServiceConfig()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._init_services()
        self.logger.info("NBA服务初始化完成")

    def _init_services(self) -> None:
        """初始化所有子服务"""
        self._data_service = NBAGameDataProvider(self.config.service_config)
        self._display_service = DisplayService(
            game_data_service=self._data_service,
            display_config=self.config.display_config,
            ai_service=self.config.ai_config
        )
        self._viz_service = GameChartsService(game_data_service=self._data_service)
        self._video_service = GameVideoService()

    @handle_service_exceptions
    def get_game_info(self, team: Optional[str] = None,
                      date: Optional[str] = None,
                      include_ai_analysis: bool = False) -> Dict[str, Any]:
        """获取比赛信息"""
        try:
            game_data = self._data_service.get_game(team, date)
            if not game_data or not game_data.game:
                logger.warning("没有获取到比赛数据")
                return {}

            # 确保game对象存在
            game = game_data.game

            result = {
                "basic_info": self._display_service.format_game_basic_info(game),
                "status": self._display_service.format_game_status(
                    game.homeTeam,
                    game.awayTeam
                ) if hasattr(game, 'homeTeam') and hasattr(game, 'awayTeam') else None,
                "statistics": self._data_service.get_game_stats(game_data)
            }

            return {k: v for k, v in result.items() if v is not None}

        except Exception as e:
            logger.error(f"获取比赛信息时出错: {str(e)}", exc_info=True)
            return {}

    @handle_service_exceptions
    async def process_game_data(self) -> Dict[str, Any]:
        """处理完整的比赛数据流程"""
        team = self.config.default_team
        date = self.config.date_str

        logger.info(f"正在查询 {team} 的比赛数据...")

        # 获取比赛信息
        game_data = self.get_game_info(
            team=team,
            date=date,
            include_ai_analysis=self.config.enable_ai
        )

        return game_data

    @handle_service_exceptions
    async def process_game_videos(self) -> Dict[str, Path]:
        """处理比赛视频数据流程"""
        team = self.config.default_team
        player = self.config.default_player

        try:
            logger.info(f"正在获取{'球员' if player else '球队'}视频...")

            # 获取视频数据
            videos = await self.get_game_videos(
                team=team,
                player_name=player,
                context_measure=ContextMeasure.FGM
            )

            if not videos:
                logger.warning("未找到视频数据")
                return {}

            logger.info(f"找到 {len(videos)} 个视频片段，开始下载...")

            # 下载视频
            video_paths = await self.download_game_videos(
                videos=videos,
                to_gif=False,
                compress=True
            )

            logger.info(f"视频下载完成，共 {len(video_paths)} 个文件")
            return video_paths

        except Exception as e:
            logger.error(f"处理视频数据时出错: {e}")
            return {}

    @handle_service_exceptions
    async def get_game_videos(self, team: Optional[str] = None,
                              date: Optional[str] = None,
                              player_name: Optional[str] = None,
                              context_measure: ContextMeasure = ContextMeasure.FGM) -> Dict[str, Any]:
        """获取比赛视频"""
        game = self._data_service.get_game(team, date)
        if not game:
            return {}

        # 如果指定了球员，获取球员ID
        player_id = None
        if player_name:
            player = next(
                (p for t in [game.game.homeTeam, game.game.awayTeam]
                 for p in t.players if p.name.lower() == player_name.lower()),
                None
            )
            if player:
                player_id = player.personId

        videos = await self._video_service.get_game_videos(
            game_id=game.game.gameId,
            context_measure=context_measure,
            player_id=player_id
        )

        return videos

    @handle_service_exceptions
    async def download_game_videos(self,
                                   videos: Dict[str, Any],
                                   output_dir: Optional[Path] = None,
                                   to_gif: bool = False,
                                   compress: bool = False) -> Dict[str, Path]:
        """下载比赛视频"""
        output_dir = output_dir or self.config.video_output_dir
        return await self._video_service.batch_download(
            videos=videos,
            output_dir=output_dir,
            quality=self.config.video_quality,
            to_gif=to_gif,
            compress=compress,
            max_concurrent=self.config.max_concurrent_downloads
        )

    def refresh_data(self) -> None:
        """刷新所有数据"""
        self._data_service.refresh_all_data()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """清理资源"""
        try:
            if hasattr(self, '_data_service'):
                self._data_service.clear_cache()
            if hasattr(self, '_video_service'):
                await self._video_service.__aexit__(exc_type, exc_val, exc_tb)
        except Exception as e:
            self.logger.error(f"清理资源时出错: {str(e)}")