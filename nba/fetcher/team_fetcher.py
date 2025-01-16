from typing import Dict, Optional
from nba.models.team_model import TeamProfile
from nba.parser.team_parser import TeamParser
from config.nba_config import NBAConfig
from .base_fetcher import BaseNBAFetcher

class TeamFetcher(BaseNBAFetcher):
    """NBA球队数据获取器
    
    专门用于获取NBA球队相关的数据，特点：
    1. 支持获取球队详细信息
    2. 集成了数据解析功能
    3. 自动缓存管理
    4. 支持强制更新
    
    使用TeamParser进行数据解析，返回结构化的TeamProfile对象。
    """
    
    def __init__(self):
        """初始化球队数据获取器
        
        设置基础URL和日志记录器，继承基类的HTTP请求和缓存功能。
        """
        super().__init__()
        self.team_details_url = f"{NBAConfig.URLS.STATS_URL}/stats/teamdetails"
    
    def get_team_details(self, team_id: int, force_update: bool = False) -> Optional[TeamProfile]:
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
            Optional[TeamProfile]: 结构化的球队信息对象，获取失败时返回None
            
        Example:
            >>> fetcher = TeamFetcher()
            >>> team_info = fetcher.get_team_details(1610612737)  # 获取老鹰队信息
            >>> print(team_info.team_name)
            'Atlanta Hawks'
        """
        return self.fetch_data(
            url=self.team_details_url,
            params={"TeamID": team_id},
            cache_config={
                'key': f"team_{team_id}",
                'file': NBAConfig.PATHS.TEAM_CACHE / "team_details.json",
                'interval': NBAConfig.API.UPDATE_INTERVAL,
                'force_update': force_update
            }
        )