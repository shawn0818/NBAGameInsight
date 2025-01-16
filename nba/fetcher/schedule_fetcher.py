from typing import Dict, Optional
import logging
from .base_fetcher import BaseNBAFetcher
from config.nba_config import NBAConfig


class ScheduleFetcher(BaseNBAFetcher):
    """NBA赛程数据获取器
    
    用于获取NBA赛程相关数据，特点：
    1. 支持缓存机制，避免频繁请求
    2. 自动处理数据更新
    3. 可配置的缓存更新间隔
    
    通过继承BaseNBAFetcher获得基础的HTTP请求和缓存管理能力。
    """

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_schedule(self, force_update: bool = False) -> Optional[Dict]:
        """获取NBA赛程数据
        
        获取NBA比赛赛程信息，包括：
        - 已完成的比赛
        - 即将进行的比赛
        - 比赛基本信息（时间、队伍、场地等）
        
        Args:
            force_update: 是否强制更新缓存数据
        
        Returns:
            Optional[Dict]: 赛程数据，获取失败时返回None
        """
        return self.fetch_data(
            url=NBAConfig.URLS.SCHEDULE,
            cache_config={
                'key': "schedule",
                'file': NBAConfig.PATHS.SCHEDULE_CACHE / 'schedule.json',
                'interval': NBAConfig.API.SCHEDULE_UPDATE_INTERVAL,
                'force_update': force_update
            }
        )