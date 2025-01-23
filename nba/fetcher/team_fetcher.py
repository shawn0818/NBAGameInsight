from typing import Dict, Optional
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import logging
from .base_fetcher import BaseNBAFetcher


@dataclass
class TeamConfig:
    """球队数据配置"""
    BASE_URL: str = "https://stats.nba.com/stats"
    CACHE_PATH: Path = Path("data/cache/teams")
    CACHE_DURATION: timedelta = timedelta(days=7)  # 球队数据缓存7天

    # 缓存文件名
    CACHE_FILES = {
        'details': 'team_details.json'
    }


class TeamFetcher(BaseNBAFetcher):
    """NBA球队数据获取器

    专门用于获取NBA球队相关的数据，特点：
    1. 支持获取球队详细信息
    2. 自动缓存管理
    3. 错误重试机制
    4. 支持强制更新
    """

    config = TeamConfig()

    def __init__(self):
        """初始化球队数据获取器

        设置基础URL和日志记录器，继承基类的HTTP请求和缓存功能。
        """
        super().__init__()
        self.team_details_url = f"{self.config.BASE_URL}/teamdetails"

    def get_team_details(self,
                         team_id: int,
                         force_update: bool = False) -> Optional[Dict]:
        """获取球队详细信息

        获取指定球队的完整信息，包括：
        - 基本信息（队名、所在地、成立时间等）
        - 球队历史数据
        - 当前赛季统计
        - 主场信息

        Args:
            team_id: 球队ID，NBA官方分配的唯一标识
            force_update: 是否强制更新缓存数据

        Returns:
            球队信息数据，获取失败时返回None
        """
        try:
            return self.fetch_data(
                url=self.team_details_url,
                params={"TeamID": team_id},
                cache_config={
                    'key': f"team_{team_id}",
                    'file': self.config.CACHE_PATH / self.config.CACHE_FILES['details'],
                    'interval': int(self.config.CACHE_DURATION.total_seconds()),
                    'force_update': force_update
                }
            )
        except Exception as e:
            self.logger.error(f"Error fetching team details for team {team_id}: {e}")
            return None