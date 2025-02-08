from typing import Dict, Optional, Any, Tuple, TypedDict
from datetime import timedelta
from pathlib import Path
from enum import Enum
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig


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
    CACHE_PATH: Path = Path("./cache/game")
    # 根据比赛状态配置不同的缓存时间
    CACHE_DURATION: Dict[GameStatusEnum, timedelta] = {
        GameStatusEnum.NOT_STARTED: timedelta(minutes=1),
        GameStatusEnum.IN_PROGRESS: timedelta(seconds=0),
        GameStatusEnum.FINISHED: timedelta(days=365)
    }


class GameResponse(TypedDict):
    """比赛数据响应类型"""
    game: Dict[str, Any]
    stats: Dict[str, Any]
    meta: Dict[str, Any]


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

    def get_game_data(self, game_id: str, data_type: str = 'boxscore', force_update: bool = False) -> Optional[
        GameResponse]:
        """获取比赛数据(基础方法)

        Args:
            game_id: 比赛ID
            data_type: 数据类型，可选值：boxscore, playbyplay
            force_update: 是否强制更新缓存

        Returns:
            比赛数据字典，获取失败时返回None

        Raises:
            ValueError: 当game_id为空或data_type不合法时抛出
        """
        if not game_id:
            raise ValueError("game_id cannot be empty")
        if data_type not in ['boxscore', 'playbyplay']:
            raise ValueError("data_type must be either 'boxscore' or 'playbyplay'")

        cache_key = f"{data_type}_{game_id}"

        # 构建请求URL
        url = f"{data_type}/{data_type}_{game_id}.json"

        try:
            response_data = self.fetch_data(
                endpoint=url,
                cache_key=cache_key,
                force_update=force_update
            )

            if response_data is not None:
                game_status = self._get_game_status(response_data)
                # 使用fetch_data的cache_status_key参数来处理动态缓存时间
                return self.fetch_data(
                    endpoint=url,
                    cache_key=cache_key,
                    force_update=force_update,
                    cache_status_key=game_status
                )

            return response_data

        except Exception as e:
            self.logger.error(f"获取比赛数据失败: {e}")
            return None

    def get_boxscore(self, game_id: str, force_update: bool = False) -> Tuple[Optional[GameResponse], GameStatusEnum]:
        """获取比赛数据统计(boxscore)

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新缓存

        Returns:
            Tuple[Optional[GameResponse], GameStatusEnum]:
            - 第一个元素是比赛数据，当获取失败时为None
            - 第二个元素是比赛状态枚举值
        """
        try:
            data = self.get_game_data(game_id, 'boxscore', force_update)
            if data is None:
                return None, GameStatusEnum.NOT_STARTED

            game_status = self._get_game_status(data)
            return data, game_status

        except Exception as e:
            self.logger.error(f"获取比赛统计数据失败: {e}")
            return None, GameStatusEnum.NOT_STARTED

    def get_playbyplay(self, game_id: str, force_update: bool = False) -> Tuple[
        Optional[GameResponse], GameStatusEnum]:
        """获取比赛回放数据(play-by-play)

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新缓存

        Returns:
            Tuple[Optional[GameResponse], GameStatusEnum]:
            - 第一个元素是比赛回放数据，当获取失败时为None
            - 第二个元素是比赛状态枚举值
        """
        try:
            data = self.get_game_data(game_id, 'playbyplay', force_update)
            if data is None:
                return None, GameStatusEnum.NOT_STARTED

            game_status = self._get_game_status(data)
            return data, game_status

        except Exception as e:
            self.logger.error(f"获取比赛回放数据失败: {e}")
            return None, GameStatusEnum.NOT_STARTED

    def _get_game_status(self, data: Dict[str, Any]) -> GameStatusEnum:
        """从数据中获取比赛状态

        Args:
            data: 比赛数据字典

        Returns:
            GameStatusEnum: 比赛状态枚举值
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        try:
            status = data.get('game', {}).get('gameStatus', 1)
            return GameStatusEnum.from_api_status(status)
        except Exception as e:
            self.logger.error(f"获取比赛状态失败: {e}")
            return GameStatusEnum.NOT_STARTED

    def clear_cache(self, game_id: Optional[str] = None, older_than: Optional[timedelta] = None) -> None:
        """清理缓存

        Args:
            game_id: 指定清理某场比赛的缓存，为None时清理所有缓存
            older_than: 清理指定时间之前的缓存
        """
        try:
            prefix = self.__class__.__name__.lower()
            if game_id:
                for data_type in ['boxscore', 'playbyplay']:
                    cache_key = f"{data_type}_{game_id}"
                    self.cache_manager.clear(prefix=prefix, identifier=cache_key)
            else:
                self.cache_manager.clear(prefix=prefix, age=older_than)
        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")