from typing import Dict, Optional
import logging
from .base import BaseNBAFetcher
from config.nba_config import NBAConfig


class GameFetcher(BaseNBAFetcher):
    """NBA比赛数据获取器----继承自 BaseNBAFetcher，专门用于获取 NBA 比赛相关的数据。
    它提供了获取比赛统计数据（如 boxscore）和比赛回放数据（如 playbyplay）的方法。
    该类依赖于 BaseNBAFetcher 中的 HTTP 请求功能，并通过提供具体的数据类型来请求不同类型的比赛数据。"""
    
    def __init__(self, base_url: Optional[str] = None):
        """
        初始化数据获取器
        
        Args:
            base_url (Optional[str]): 比赛数据的基础URL。如果未提供，则使用配置中的 LIVE_DATA。
        """
        super().__init__()
        self.base_url = base_url or NBAConfig.URLS.LIVE_DATA
        self.logger = logging.getLogger(__name__)
  
    
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
        allowed_data_types = {'boxscore', 'playbyplay'}
        if data_type not in allowed_data_types:
            self.logger.error(f"Invalid data_type: {data_type}. Must be one of {allowed_data_types}")
            return None
        
        try:
            url = f"{self.base_url}/{data_type}/{data_type}_{game_id}.json"
            self.logger.debug(f"Fetching {data_type} data for game {game_id} from URL: {url}")
            data = self.http_manager.make_request(url)
            
            if not data:
                self.logger.error(f"No data returned for {data_type} {game_id}")
                return None
                
            return data
                
        except Exception as e:
            self.logger.error(f"Error fetching {data_type} data for game {game_id}: {e}")
            return None
