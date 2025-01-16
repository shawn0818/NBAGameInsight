from typing import Dict, Optional
import logging
from .base_fetcher import BaseNBAFetcher
from config.nba_config import NBAConfig

class LeagueFetcher(BaseNBAFetcher):
    """NBA联盟数据获取器
    
    用于获取NBA联盟级别的数据，包括：
    1. 球员名册信息
    2. 季后赛形势
    3. 联盟数据统计领袖
    
    所有方法都支持缓存机制，可以通过force_update参数强制更新数据。
    """
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

    def get_all_players(self, current_season_only: bool = False,
                       force_update: bool = False) -> Optional[Dict]:
        """获取球员名册信息
        
        获取NBA球员的基本信息，支持：
        1. 只获取当前赛季在役球员
        2. 获取所有历史球员
        
        Args:
            current_season_only: 是否只获取当前赛季球员
            force_update: 是否强制更新缓存
        
        Returns:
            Optional[Dict]: 球员信息数据，获取失败时返回None
        """
        cache_key = f"players_{'current' if current_season_only else 'all'}"
        
        return self.fetch_data(
            url=f"{NBAConfig.URLS.STATS_BASE}/{NBAConfig.API.ENDPOINTS.ALL_PLAYERS}",
            params={
                'LeagueID': NBAConfig.LEAGUE.NBA_ID,
                'Season': self._get_current_season(),
                'IsOnlyCurrentSeason': '1' if current_season_only else '0'
            },
            cache_config={
                'key': cache_key,
                'file': NBAConfig.PATHS.LEAGUE_CACHE / 'players.json',
                'interval': NBAConfig.API.PLAYERS_UPDATE_INTERVAL,
                'force_update': force_update
            }
        )

    def get_playoff_picture(self, force_update: bool = False) -> Optional[Dict]:
        """获取季后赛形势数据"""
        season_id = f"2{self._get_current_season().split('-')[0]}"
        
        return self.fetch_data(
            url=f"{NBAConfig.URLS.STATS_BASE}/{NBAConfig.API.ENDPOINTS.PLAYOFF_PICTURE}",
            params={
                'LeagueID': NBAConfig.LEAGUE.NBA_ID,
                'SeasonID': season_id
            },
            cache_config={
                'key': f"playoff_picture_{season_id}",
                'file': NBAConfig.PATHS.LEAGUE_CACHE / 'playoff_picture.json',
                'interval': NBAConfig.API.UPDATE_INTERVAL,
                'force_update': force_update
            }
        )

    def get_league_leaders(self, 
                         season_type: str = 'Regular Season',
                         per_mode: str = 'PerGame',
                         top_x: int = 10,
                         force_update: bool = False) -> Optional[Dict]:
        """获取联盟数据统计领袖"""
        cache_key = f"leaders_{season_type}_{per_mode}_{top_x}"
        
        return self.fetch_data(
            url=f"{NBAConfig.URLS.STATS_BASE}/{NBAConfig.API.ENDPOINTS.LEAGUE_LEADERS}",
            params={
                'LeagueID': NBAConfig.LEAGUE.NBA_ID,
                'SeasonType': season_type,
                'PerMode': per_mode,
                'TopX': str(top_x)
            },
            cache_config={
                'key': cache_key,
                'file': NBAConfig.PATHS.LEAGUE_CACHE / 'league_leaders.json',
                'interval': NBAConfig.API.UPDATE_INTERVAL,
                'force_update': force_update
            }
        )

    def _get_current_season(self) -> str:
        """获取当前赛季标识"""
        # 实现获取当前赛季的逻辑
        pass
