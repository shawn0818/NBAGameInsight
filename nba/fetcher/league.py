from typing import Dict, Optional
import logging
import json
from datetime import datetime
from .base import BaseNBAFetcher
from config.nba_config import NBAConfig
from utils.http_handler import HTTPRequestManager


class LeagueFetcher(BaseNBAFetcher):
    """NBA联盟数据获取器---该类包括获取球员信息、季后赛形势、联盟数据统计领袖等功能，同时支持数据缓存管理。"""
    
    def __init__(self):
        """初始化联盟数据获取器"""
        super().__init__()
        self.logger = logging.getLogger(__name__)
        # 使用 BaseNBAFetcher 中的 http_manager，无需重复初始化
        # self.http_manager = HTTPRequestManager()  # 已在基类中初始化

        # 初始化缓存配置
        self.cache_dir = NBAConfig.PATHS.LEAGUE_CACHE
        self.players_cache_file = self.cache_dir / 'players.json'
        self.playoff_picture_cache_file = self.cache_dir / 'playoff_picture.json'
        self.league_leaders_cache_file = self.cache_dir / 'league_leaders.json'
        self.players_update_interval = NBAConfig.API.PLAYERS_UPDATE_INTERVAL  # 秒

        # 确保缓存目录存在（已在 NBAConfig.PATHS.ensure_directories() 中调用）
        # self.cache_dir.mkdir(parents=True, exist_ok=True)  # 已在初始化中处理

    def get_all_players(self, current_season_only: bool = True, 
                       force_update: bool = False) -> Optional[Dict]:
        """
        获取球员名册信息
        
        Args:
            current_season_only (bool): 是否只获取当前赛季的球员
            force_update (bool): 是否强制更新缓存
            
        Returns:
            Optional[Dict]: 包含球员列表的数据
        """
        cache_key = f"players_{'current' if current_season_only else 'all'}"
        
        # 检查缓存
        if not force_update:
            cached_data = self._get_cached_players(cache_key)
            if cached_data:
                self.logger.info("Using cached players data")
                return cached_data
        
        # 获取新数据
        params = {
            'LeagueID': NBAConfig.LEAGUE.NBA_ID,
            'Season': self._get_current_season(),
            'IsOnlyCurrentSeason': '1' if current_season_only else '0'
        }
        
        url = f"{NBAConfig.URLS.STATS_BASE}/{NBAConfig.API.ENDPOINTS.ALL_PLAYERS}"
        data = self._make_request(url, params=params)
        
        if data:
            # 缓存新数据
            if self._cache_players_data(data, cache_key):
                self.logger.info("Successfully cached new players data")
            else:
                self.logger.warning("Failed to cache new players data")
        return data

    def get_playoff_picture(self) -> Optional[Dict]:
        """
        获取季后赛形势数据
        
        Returns:
            Optional[Dict]: 包含东西部季后赛形势的数据
        """
        try:
            season_id = f"2{self._get_current_season().split('-')[0]}"  # 2023-24 -> 22023
            params = {
                'LeagueID': NBAConfig.LEAGUE.NBA_ID,
                'SeasonID': season_id
            }
            
            url = f"{NBAConfig.URLS.STATS_BASE}/{NBAConfig.API.ENDPOINTS.PLAYOFF_PICTURE}"
            return self._make_request(url, params=params)
            
        except Exception as e:
            self.logger.error(f"Error fetching playoff picture data: {e}")
            return None

    def get_league_leaders(self, 
                           season_type: str = 'Regular Season',
                           per_mode: str = 'PerGame',
                           top_x: int = 10) -> Optional[Dict]:
        """
        获取联盟数据统计领袖
        
        Args:
            season_type (str): 赛季类型 ('Regular Season', 'Playoffs', 'All Star')
            per_mode (str): 统计方式 ('PerGame', 'Totals', 'Per36', 'Per100Possessions')
            top_x (int): 返回前几名
            
        Returns:
            Optional[Dict]: 包含各项数据领袖的数据
        """
        try:
            params = {
                'LeagueID': NBAConfig.LEAGUE.NBA_ID,
                'SeasonType': season_type,
                'PerMode': per_mode,
                'TopX': str(top_x)
            }
            
            url = f"{NBAConfig.URLS.STATS_BASE}/{NBAConfig.API.ENDPOINTS.LEAGUE_LEADERS}"
            return self._make_request(url, params=params)
            
        except Exception as e:
            self.logger.error(f"Error fetching league leaders data: {e}")
            return None

    def _get_cached_players(self, cache_key: str) -> Optional[Dict]:
        """获取缓存的球员数据"""
        try:
            if not self.players_cache_file.exists():
                return None
                
            with self.players_cache_file.open('r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            if not cached_data or cache_key not in cached_data:
                return None
            
            data_entry = cached_data[cache_key]
            time_diff = datetime.now().timestamp() - data_entry.get('timestamp', 0)
            
            if time_diff < self.players_update_interval:
                return data_entry.get('data')
            return None
                
        except Exception as e:
            self.logger.error(f"Error reading players cache: {e}")
            return None

    def _cache_players_data(self, data: Dict, cache_key: str) -> bool:
        """缓存球员数据"""
        try:
            current_cache = {}
            if self.players_cache_file.exists():
                with self.players_cache_file.open('r', encoding='utf-8') as f:
                    current_cache = json.load(f) or {}
            
            current_cache[cache_key] = {
                'timestamp': datetime.now().timestamp(),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data': data
            }
            
            with self.players_cache_file.open('w', encoding='utf-8') as f:
                json.dump(current_cache, f, indent=4)
            return True
            
        except Exception as e:
            self.logger.error(f"Error caching players data: {e}")
            return False
