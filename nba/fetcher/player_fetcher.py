from typing import Dict, Optional
from dataclasses import dataclass
from datetime import timedelta
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig
from config.nba_config import NBAConfig


@dataclass
class PlayerConfig(BaseRequestConfig):
    """球员数据配置"""
    BASE_URL: str = "https://cdn.nba.com/static/json"
    CACHE_PATH: str = NBAConfig.PATHS.PLAYER_CACHE_DIR
    CACHE_DURATION: timedelta = timedelta(days=7)  # 球员数据缓存7天

    # API端点
    PROFILE_URL: str = f"{BASE_URL}/staticData/playerIndex.json"

    # 缓存文件名
    CACHE_FILES = {
        'profile': 'player_profile.json'
    }


class PlayerFetcher(BaseNBAFetcher):
    """NBA球员数据获取器

    专门用于获取NBA球员相关的数据，特点：
    1. 支持获取球员详细信息
    2. 数据自动缓存
    3. 可配置的更新策略
    """

    player_config = PlayerConfig()

    def __init__(self):
        super().__init__()

    def get_player_profile(self, force_update: bool = False) -> Optional[Dict]:
        """获取所有球员的基础信息

        获取NBA球员的详细资料，包括：
        - 个人信息（身高、体重、出生日期等）
        - 球员生涯数据
        - 当前赛季数据

        Args:
            force_update: 是否强制更新缓存数据

        Returns:
            球员资料数据，获取失败时返回None
        """
        try:
            return self.fetch_data(
                url=self.player_config.PROFILE_URL,
                cache_config={
                    'key': "players_all",
                    'file': self.player_config.CACHE_PATH / self.player_config.CACHE_FILES['profile'],
                    'interval': int(self.player_config.CACHE_DURATION.total_seconds()),
                    'force_update': force_update
                }
            )
        except Exception as e:
            self.logger.error(f"Error fetching player profile: {e}")
            return None