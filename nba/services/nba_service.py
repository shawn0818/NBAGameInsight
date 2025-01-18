# nba/services/nba_service.py

from typing import Optional, Dict, Any, List, Callable
import logging
from pathlib import Path
from dataclasses import dataclass, field
from functools import wraps
from datetime import datetime

from nba.services.game_data_service import NBAGameDataProvider, ServiceConfig
from nba.services.game_video_service import GameVideoService
from nba.services.game_display_service import DisplayService, DisplayConfig
from nba.services.game_charts_service import GameChartsService
from nba.services.ai_service import AIConfig
from config.nba_config import NBAConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class NBAServiceConfig:
    """NBA服务统一配置类"""

    # 基础配置
    default_team: Optional[str] = None
    default_player: Optional[str] = None
    date_str: Optional[str] = None

    # 显示配置
    display_language: str = "zh_CN"
    show_advanced_stats: bool = True

    # AI配置
    enable_ai: bool = False
    ai_api_key: Optional[str] = None
    ai_base_url: Optional[str] = None

    # 输出配置
    output_dir: Path = NBAConfig.PATHS.PICTURES_DIR

    # 日志配置
    log_level: int = logging.INFO
    log_format: str = '%(asctime)s [%(levelname)s] %(name)s - %(message)s'

    # 服务配置实例（内部使用）
    service_config: ServiceConfig = field(init=False)
    display_config: DisplayConfig = field(init=False)
    ai_config: Optional[AIConfig] = field(init=False)

    def __post_init__(self):
        """初始化派生配置"""
        # 配置日志
        self._setup_logging()

        # 配置AI服务
        self._setup_ai_config()

        # 初始化子服务配置
        self._init_service_configs()

    def _setup_logging(self) -> None:
        """设置日志配置"""
        if self.log_level:
            logger.setLevel(self.log_level)
        if self.log_format:
            for handler in logger.handlers:
                handler.setFormatter(logging.Formatter(self.log_format))

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
            cache_size=128,
            cache_dir=NBAConfig.PATHS.CACHE_DIR,
            auto_refresh=True,
            refresh_interval=NBAConfig.API.SCHEDULE_UPDATE_INTERVAL
        )

        self.display_config = DisplayConfig(
            language=self.display_language,
            show_advanced_stats=self.show_advanced_stats
        )


def handle_service_exceptions(func: Callable) -> Callable:
    """服务层异常处理装饰器"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"服务调用错误 - {func.__name__}: {str(e)}", exc_info=True)

            # 根据返回类型返回适当的空值
            return_type = func.__annotations__.get('return')
            if return_type == Dict:
                return {}
            elif return_type == List:
                return []
            elif return_type == str:
                return ""
            return None

    return wrapper


class NBAService:
    """NBA数据服务统一接口

    主要职责:
    1. 统一配置管理
    2. 服务组件协调
    3. 提供简化的API
    4. 统一的错误处理
    5. 资源生命周期管理
    """

    def __init__(self, config: Optional[NBAServiceConfig] = None):
        """初始化NBA服务

        Args:
            config: 服务配置对象，如果为None则使用默认配置
        """
        self.config = config or NBAServiceConfig()
        self.logger = logging.getLogger(self.__class__.__name__)

        # 初始化子服务
        self._init_services()

        self.logger.info("NBA服务初始化完成")

    def _init_services(self) -> None:
        """初始化所有子服务"""
        # 数据服务（核心）
        self._data_service = NBAGameDataProvider(self.config.service_config)

        # 显示服务
        self._display_service = DisplayService(
            game_data_service=self._data_service,
            display_config=self.config.display_config,
            ai_service=self.config.ai_config
        )

        # 可视化服务
        self._viz_service = GameChartsService(game_data_service=self._data_service)

        # 视频服务
        self._video_service = GameVideoService()

    @handle_service_exceptions
    def get_game_info(self, team: Optional[str] = None,
                      date: Optional[str] = None,
                      include_ai_analysis: bool = False) -> Dict[str, Any]:
        """获取比赛信息

        Args:
            team: 球队名称
            date: 比赛日期
            include_ai_analysis: 是否包含AI分析

        Returns:
            比赛信息字典，包含基本信息、实时状态和统计数据
        """
        # 获取原始比赛数据
        game_data = self._data_service.get_game(team, date)
        if not game_data:
            return {}

        # 转换为显示服务需要的格式
        game_dict = game_data.game.to_dict()

        # 获取并格式化信息
        result = {
            "basic_info": self._display_service.format_game_basic_info(game_dict),
            "live_status": self._display_service.format_game_live_status(game_dict),
            "statistics": self._data_service.get_game_stats(game_data)
        }

        # 添加AI分析（如果启用）
        if include_ai_analysis and self.config.enable_ai:
            events = self._data_service.get_filtered_events(game_data)
            result["ai_analysis"] = self._display_service.analyze_events({
                "game_id": game_dict["gameId"],
                "events": events
            })

        return result

    @handle_service_exceptions
    def get_player_stats(self, player_name: str,
                         team: Optional[str] = None,
                         date: Optional[str] = None) -> Dict[str, Any]:
        """获取球员统计数据

        Args:
            player_name: 球员姓名
            team: 球队名称
            date: 比赛日期

        Returns:
            球员统计数据字典
        """
        # 获取比赛数据
        game_data = self._data_service.get_game(team, date)
        if not game_data:
            return {}

        # 查找球员数据
        player_data = None
        for team_data in [game_data.game.homeTeam, game_data.game.awayTeam]:
            for player in team_data.players:
                if player.name.lower() == player_name.lower():
                    player_data = player
                    break
            if player_data:
                break

        if not player_data:
            self.logger.warning(f"未找到球员: {player_name}")
            return {}

        # 获取统计数据
        stats = self._data_service.get_player_stats(player_data)
        return {
            "name": player_data.name,
            "stats": self._display_service.format_player_stats(stats)
        }

    @handle_service_exceptions
    def get_team_stats(self, team: Optional[str] = None,
                       date: Optional[str] = None) -> Dict[str, Any]:
        """获取球队统计数据

        Args:
            team: 球队名称
            date: 比赛日期

        Returns:
            球队统计数据字典
        """
        game_data = self._data_service.get_game(team, date)
        if not game_data:
            return {}

        return self._data_service.get_game_stats(game_data)

    @handle_service_exceptions
    def create_shot_chart(self, team: Optional[str] = None,
                          player_name: Optional[str] = None,
                          date: Optional[str] = None) -> Optional[Path]:
        """创建投篮分布图

        Args:
            team: 球队名称
            player_name: 球员姓名（可选）
            date: 比赛日期

        Returns:
            图表文件路径
        """
        game_data = self._data_service.get_game(team, date)
        if not game_data:
            return None

        # 获取球员ID（如果指定了球员）
        player_id = None
        if player_name:
            player = next(
                (p for t in [game_data.game.homeTeam, game_data.game.awayTeam]
                 for p in t.players if p.name.lower() == player_name.lower()),
                None
            )
            if player:
                player_id = player.personId

        # 生成标题
        title = f"{team or game_data.game.homeTeam.teamName}"
        if player_name:
            title += f" - {player_name}"
        title += " 投篮分布图"

        # 生成输出路径
        output_path = (
                self.config.output_dir /
                f"shot_chart_{game_data.game.gameId}"
                f"{'_' + player_name.replace(' ', '_') if player_name else ''}.png"
        )

        return self._viz_service.plot_player_shots(
            game=game_data,
            player_id=player_id,
            title=title,
            output_path=str(output_path)
        )

    def refresh_data(self) -> None:
        """刷新所有数据"""
        self._data_service.refresh_all_data()

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """清理资源"""
        try:
            if hasattr(self, '_data_service'):
                self._data_service.clear_cache()
        except Exception as e:
            self.logger.error(f"清理资源时出错: {str(e)}")