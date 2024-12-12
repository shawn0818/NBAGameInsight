from typing import Dict, Optional
import logging
from .base import BaseNBAFetcher
from config.nba_config import NBAConfig
from utils.http_handler import HTTPRequestManager

class GameFetcher(BaseNBAFetcher):
    """NBA比赛数据获取器"""
    
    def __init__(self):
        """初始化数据获取器"""
        super().__init__()
        self.base_url = NBAConfig.URLS.LIVE_DATA
        self.logger = logging.getLogger(__name__)
        self.http_manager = HTTPRequestManager()

    def get_boxscore(self, game_id: str) -> Optional[Dict]:
        """
        获取比赛统计数据
        
        Args:
            game_id (str): 比赛ID
            
        Returns:
            Optional[Dict]: 比赛统计数据
        """
        return self._fetch_game_data('boxscore', game_id)

    def get_playbyplay(self, game_id: str) -> Optional[Dict]:
        """
        获取比赛回放数据
        
        Args:
            game_id (str): 比赛ID
            
        Returns:
            Optional[Dict]: 比赛回放数据
        """
        return self._fetch_game_data('playbyplay', game_id)

    def _fetch_game_data(self, data_type: str, game_id: str) -> Optional[Dict]:
        """
        获取比赛数据的底层方法
        
        Args:
            data_type (str): 数据类型 ('boxscore' 或 'playbyplay')
            game_id (str): 比赛ID
            
        Returns:
            Optional[Dict]: 比赛数据
        """
        try:
            url = f"{self.base_url}/{data_type}/{data_type}_{game_id}.json"
            data = self.http_manager.make_request(url)
            
            if not data:
                self.logger.error(f"No data returned for {data_type} {game_id}")
                return None
                
            return data
            
        except Exception as e:
            self.logger.error(f"Error fetching {data_type} data for game {game_id}: {e}")
            return None
            
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.http_manager.close()