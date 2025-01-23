from typing import Dict, Optional
import logging
from datetime import timedelta
from dataclasses import dataclass
from config.nba_config import NBAConfig
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig


@dataclass
class ScheduleConfig(BaseRequestConfig):
    """赛程数据配置"""
    BASE_URL: str = "https://cdn.nba.com/static/json"
    
    CACHE_PATH: str = NBAConfig.PATHS.SCHEDULE_CACHE_DIR
    CACHE_DURATION: timedelta = timedelta(days=1)  # 赛程数据每天更新

    # API端点
    SCHEDULE_URL: str = f"{BASE_URL}/staticData/scheduleLeagueV2_1.json"

    # 缓存文件名
    CACHE_FILES = {
        'schedule': 'schedule.json'
    }


class ScheduleFetcher(BaseNBAFetcher):
    """NBA赛程数据获取器

    用于获取NBA赛程相关数据，特点：
    1. 支持缓存机制，避免频繁请求
    2. 自动处理数据更新
    3. 每日更新的缓存策略
    """

    schedule_config = ScheduleConfig()

    def __init__(self):
        super().__init__()

    def get_schedule(self, force_update: bool = False) -> Optional[Dict]:
        """获取NBA赛程数据

        获取NBA比赛赛程信息，包括：
        - 已完成的比赛
        - 即将进行的比赛
        - 比赛基本信息（时间、队伍、场地等）

        Args:
            force_update: 是否强制更新缓存数据

        Returns:
            赛程数据，获取失败时返回None
        """
        try:
            return self.fetch_data(
                url=self.schedule_config.SCHEDULE_URL,
                cache_config={
                    'key': "schedule",
                    'file': self.schedule_config.CACHE_PATH / self.schedule_config.CACHE_FILES['schedule'],
                    'interval': int(self.schedule_config.CACHE_DURATION.total_seconds()),
                    'force_update': False
                }
            )
        except Exception as e:
            self.logger.error(f"Error fetching schedule: {e}")
            return None