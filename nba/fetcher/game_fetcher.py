from typing import Dict, Optional
import logging
from .base_fetcher import BaseNBAFetcher
from config.nba_config import NBAConfig


class GameFetcher(BaseNBAFetcher):
    """NBA比赛数据获取器
    
    专门用于获取NBA比赛相关的数据，包括：
    1. 比赛统计数据（boxscore）
    2. 比赛回放数据（playbyplay）
    
    该类支持数据缓存，可以减少对API的请求次数。
    """
    
    def __init__(self, base_url: Optional[str] = None):
        """初始化比赛数据获取器
        
        Args:
            base_url: 比赛数据的基础URL，如果未提供则使用配置中的默认值
        """
        super().__init__()
        self.base_url = base_url or NBAConfig.URLS.LIVE_DATA
        self.logger = logging.getLogger(__name__)
    
    def get_boxscore(self, game_id: str, force_update: bool = False) -> Optional[Dict]:
        """获取比赛统计数据（boxscore）
        
        获取指定比赛的详细统计数据，包括：
        - 球员数据
        - 球队数据
        - 比赛进程数据
        
        Args:
            game_id: 比赛ID
            force_update: 是否强制更新缓存
        
        Returns:
            Optional[Dict]: 比赛统计数据，获取失败时返回None
        """
        return self.fetch_data(
            url=f"{self.base_url}/boxscore/boxscore_{game_id}.json",
            cache_config={
                'key': f"boxscore_{game_id}",
                'file': NBAConfig.PATHS.GAME_CACHE / 'boxscores.json',
                'interval': NBAConfig.API.GAME_UPDATE_INTERVAL,
                'force_update': force_update
            }
        )

    def get_playbyplay(self, game_id: str, force_update: bool = False) -> Optional[Dict]:
        """获取比赛回放数据"""
        return self.fetch_data(
            url=f"{self.base_url}/playbyplay/playbyplay_{game_id}.json",
            cache_config={
                'key': f"playbyplay_{game_id}",
                'file': NBAConfig.PATHS.GAME_CACHE / 'playbyplay.json',
                'interval': NBAConfig.API.GAME_UPDATE_INTERVAL,
                'force_update': force_update
            }
        )
