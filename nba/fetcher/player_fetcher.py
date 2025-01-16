from typing import Dict, Optional
from .base_fetcher import BaseNBAFetcher
from config.nba_config import NBAConfig
import logging

class PlayerFetcher(BaseNBAFetcher):
    """NBA球员数据获取器
    
    专门用于获取NBA球员相关的数据，特点：
    1. 支持获取球员详细信息
    2. 数据自动缓存
    3. 可配置的更新策略
    
    所有数据获取方法都支持强制更新选项。
    """

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

    def get_player_profile(self, force_update: bool = False) -> Optional[Dict]:
        """获取所有球员的基础信息
        
        获取NBA球员的详细资料，包括：
        - 个人信息（身高、体重、出生日期等）
        - 球员生涯数据
        - 当前赛季数据
        
        Args:
            force_update: 是否强制更新缓存数据
        
        Returns:
            Optional[Dict]: 球员资料数据，获取失败时返回None
        """
        return self.fetch_data(
            url=NBAConfig.URLS.PLAYER_PROFILE,
            cache_config={
                'key': "players_all",
                'file': NBAConfig.PATHS.PLAYER_CACHE / 'player_info.json',
                'interval': NBAConfig.API.PLAYERS_UPDATE_INTERVAL,
                'force_update': force_update
            }
        )
