from typing import Dict, Optional
import logging
from .base import BaseNBAFetcher
from config.nba_config import NBAConfig
from utils.http_handler import HTTPRequestManager

class PlayerFetcher(BaseNBAFetcher):
    """NBA球员数据获取器"""
    
    def __init__(self):
        """初始化数据获取器"""
        super().__init__()
        self.player_profile_url = NBAConfig.URLS.PLAYER_PROFILE
        self.logger = logging.getLogger(__name__)
        self.http_manager = HTTPRequestManager()
        

    def get_player_profile(self) -> Optional[Dict]:
        """
        获取所有球员的基础信息
        
        Returns:
            Optional[Dict]: 包含所有球员信息的原始JSON数据
        """
        try:
            return self.http_manager.make_request(self.player_profile_url)
        except Exception as e:
            self.logger.error(f"Error fetching player index data: {e}")
            return None


    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.http_manager.close()