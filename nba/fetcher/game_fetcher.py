from dataclasses import dataclass
from typing import Dict, Optional, Any, Tuple
from datetime import timedelta
from enum import Enum
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config.nba_config import  NBAConfig


class GameStatusEnum(Enum):
    """比赛状态枚举"""
    NOT_STARTED = 1
    IN_PROGRESS = 2
    FINISHED = 3

    @classmethod
    def from_api_status(cls, status: Optional[int]) -> 'GameStatusEnum':
        """从API状态码转换为枚举值"""
        try:
            return cls(status)
        except (ValueError, TypeError):
            return cls.NOT_STARTED


class GameConfig:
    """比赛数据配置"""
    BASE_URL: str = "https://cdn.nba.com/static/json/liveData"
    CACHE_PATH = NBAConfig.PATHS.GAME_CACHE_DIR
    # 根据比赛状态配置不同的缓存时间
    CACHE_DURATION: Dict[GameStatusEnum, timedelta] = {
        GameStatusEnum.NOT_STARTED: timedelta(minutes=1),
        GameStatusEnum.IN_PROGRESS: timedelta(seconds=0),
        GameStatusEnum.FINISHED: timedelta(days=365)
    }

@dataclass
class GameDataResponse:
    """比赛数据响应类"""
    boxscore: Dict[str, Any]  # 比赛统计数据
    playbyplay: Dict[str, Any]  # 比赛回放数据

    @property
    def status(self) -> GameStatusEnum:
        """从boxscore中获取比赛状态"""
        return GameStatusEnum.from_api_status(
            self.boxscore.get('gameStatus', 1)
        )


class GameFetcher(BaseNBAFetcher):
    """NBA比赛数据获取器"""

    def __init__(self, custom_config: Optional[GameConfig] = None):
        """初始化

        Args:
            custom_config: 自定义配置，如果为None则使用默认配置
        """
        game_config = custom_config or GameConfig()

        # 配置缓存
        cache_config = BaseCacheConfig(
            duration=timedelta(days=1),  # 默认缓存时间
            root_path=game_config.CACHE_PATH,
            dynamic_duration=game_config.CACHE_DURATION  # 使用动态缓存时间
        )

        # 创建基础请求配置
        base_config = BaseRequestConfig(
            base_url=game_config.BASE_URL,
            cache_config=cache_config
        )

        # 初始化基类
        super().__init__(base_config)
        self.game_config = game_config

    def get_game_data(self, game_id: str, force_update: bool = False) -> Optional[GameDataResponse]:
        """获取完整的比赛数据"""
        try:
            # 1. 获取boxscore数据和状态
            boxscore_data, game_status = self._get_data_with_status(
                game_id,
                'boxscore',
                force_update
            )

            if not boxscore_data or 'game' not in boxscore_data:
                self.logger.error("无法获取boxscore数据")
                return None

            # 2. 只有当比赛进行中或已结束时才获取playbyplay数据
            playbyplay_data = None
            if game_status in [GameStatusEnum.IN_PROGRESS, GameStatusEnum.FINISHED]:
                playbyplay_data, _ = self._get_data_with_status(
                    game_id,
                    'playbyplay',
                    force_update,
                    game_status
                )

                if not playbyplay_data or 'game' not in playbyplay_data:
                    self.logger.error("无法获取playbyplay数据")
                    return None
            else:
                # 比赛未开始，返回空的playbyplay数据
                playbyplay_data = {'game': {}}
                self.logger.info("比赛未开始，不获取playbyplay数据")

            # 3. 构建响应
            return GameDataResponse(
                boxscore=boxscore_data['game'],
                playbyplay=playbyplay_data['game']
            )

        except Exception as e:
            self.logger.error(f"获取比赛数据失败: {e}")
            return None

    def _get_data_with_status(
            self,
            game_id: str,
            data_type: str,
            force_update: bool,
            game_status: Optional[GameStatusEnum] = None
    ) -> Tuple[Optional[Dict[str, Any]], GameStatusEnum]:
        """获取数据并返回比赛状态"""
        try:
            # 构建请求参数
            endpoint = f"{data_type}/{data_type}_{game_id}.json"
            cache_key = f"{data_type}_{game_id}"

            # 获取数据
            data = self.fetch_data(
                endpoint=endpoint,
                cache_key=cache_key,
                force_update=force_update,
                cache_status_key=game_status
            )

            # 如果没有传入状态，从数据中获取
            if game_status is None and data is not None:
                game_status = self._get_game_status(data)
            elif game_status is None:
                game_status = GameStatusEnum.NOT_STARTED

            return data, game_status

        except Exception as e:
            self.logger.error(f"获取{data_type}数据失败: {e}")
            return None, GameStatusEnum.NOT_STARTED

    def _get_game_status(self, data: Dict[str, Any]) -> GameStatusEnum:
        """从数据中获取比赛状态"""
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        try:
            status = data.get('game', {}).get('gameStatus', 1)
            return GameStatusEnum.from_api_status(status)
        except Exception as e:
            self.logger.error(f"获取比赛状态失败: {e}")
            return GameStatusEnum.NOT_STARTED

    def clear_cache(
            self,
            game_id: Optional[str] = None,
            older_than: Optional[timedelta] = None,
            data_type: Optional[str] = None
    ) -> None:
        """清理缓存

        Args:
            game_id: 指定清理某场比赛的缓存
            older_than: 清理指定时间之前的缓存
            data_type: 指定清理的数据类型(boxscore或playbyplay)
        """
        try:
            prefix = self.__class__.__name__.lower()

            if game_id:
                data_types = ['boxscore', 'playbyplay'] if data_type is None else [data_type]
                for dt in data_types:
                    cache_key = f"{dt}_{game_id}"
                    self.cache_manager.clear(prefix=prefix, identifier=cache_key)
            else:
                self.cache_manager.clear(prefix=prefix, age=older_than)

        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")