from typing import Dict, Optional, Any
from datetime import timedelta
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config.nba_config import NBAConfig


class PlayerConfig:
    """球员数据配置 (仅单个球员)"""
    BASE_URL: str = "https://stats.nba.com/stats"
    PLAYER_INFO_ENDPOINT: str = "commonplayerinfo"
    CACHE_PATH = NBAConfig.PATHS.PLAYER_CACHE_DIR
    CACHE_DURATION: timedelta = timedelta(days=1) # 单个球员信息缓存1天


class PlayerFetcher(BaseNBAFetcher):
    """NBA球员数据获取器 (仅单个球员)
    专门用于获取NBA单个球员的详细信息，特点：
    1. 支持获取单个球员详细信息
    2. 数据自动缓存
    3. 可配置的更新策略
    """

    def __init__(self, custom_config: Optional[PlayerConfig] = None):
        """初始化球员数据获取器

        Args:
            custom_config: 可选的自定义配置对象
        """
        self.player_config = custom_config or PlayerConfig()

        # 配置缓存
        cache_config = BaseCacheConfig(
            duration=self.player_config.CACHE_DURATION,
            root_path=self.player_config.CACHE_PATH
        )

        # 创建基础请求配置
        base_config = BaseRequestConfig(
            base_url=self.player_config.BASE_URL,
            cache_config=cache_config
        )

        # 初始化基类
        super().__init__(base_config)


    def get_player_info(self, player_id: int, force_update: bool = False) -> Optional[Dict[str, Any]]:
        """获取单个球员的详细信息

        Args:
            player_id: NBA球员ID
            force_update: 是否强制更新缓存数据

        Returns:
            单个球员的详细信息，获取失败时返回None
        """
        try:
            params = {
                "PlayerID": player_id,
                "LeagueID": "" # LeagueID 可以为空字符串
            }
            data = self.fetch_data(
                endpoint=self.player_config.PLAYER_INFO_ENDPOINT,
                params=params,
                cache_key=f"player_info_{player_id}", # 使用球员ID作为缓存key
                force_update=force_update
            )
            return data if data else None

        except Exception as e:
            self.logger.error(f"获取球员ID为 {player_id} 的信息失败: {e}")
            return None


    def cleanup_cache(self, older_than: Optional[timedelta] = None) -> None:
        """清理缓存数据

        Args:
            older_than: 可选的时间间隔，清理该时间之前的缓存
        """
        try:
            cache_age = older_than or self.player_config.CACHE_DURATION # 默认清理单球员信息缓存时间
            self.logger.info(f"正在清理{cache_age}之前的球员缓存数据") # 修改log信息
            self.cache_manager.clear(
                prefix=self.__class__.__name__.lower(),
                age=cache_age
            )

        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")
