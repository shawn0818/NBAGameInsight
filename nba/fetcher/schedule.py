import os
from typing import Dict, Optional
import logging
from datetime import datetime
from .base import BaseNBAFetcher
from config.nba_config import NBAConfig

class ScheduleFetcher(BaseNBAFetcher):
    """NBA赛程数据获取器 - 专注于数据获取"""
    
    UPDATE_INTERVAL = 7 * 24 * 60 * 60  # 7天的更新间隔
    
    def __init__(self):
        """初始化赛程获取器"""
        super().__init__()
        self.cache_dir = os.path.join(os.getcwd(), 'data', 'cache')
        self.cache_file = os.path.join(self.cache_dir, 'schedule.json')
        
        # 确保缓存目录存在
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def get_schedule(self, force_update: bool = False) -> Optional[Dict]:
        """
        获取NBA赛程数据，优先使用缓存

        Args:
            force_update: 是否强制更新数据

        Returns:
            Optional[Dict]: 赛程数据
        """
        try:
            current_time = datetime.now().timestamp()
            cache_status = self._check_cache_status()

            # 如果缓存有效且不强制更新，使用缓存
            if not force_update and cache_status['status'] == 'valid':
                cached_data = self._read_file(self.cache_file)
                if cached_data and 'data' in cached_data:
                    logging.info("Using cached schedule data")
                    return cached_data['data']

            # 获取新数据
            logging.info("Fetching new schedule data from API")
            schedule_data = self._fetch_schedule_data()
            if schedule_data:
                self._cache_schedule_data(schedule_data, current_time)
                logging.info("Successfully cached new schedule data")
            return schedule_data
            
        except Exception as e:
            logging.error(f"Error getting schedule: {e}")
            return None

    def _fetch_schedule_data(self) -> Optional[Dict]:
        """从 NBA API 获取最新赛程"""
        return self._make_request(NBAConfig.URLS.SCHEDULE)

    def _check_cache_status(self) -> Dict:
        """检查缓存状态"""
        try:
            if not os.path.exists(self.cache_file):
                return {'status': 'no_cache'}
                
            cached_data = self._read_file(self.cache_file)
            if not cached_data:
                return {'status': 'no_cache'}

            time_diff = datetime.now().timestamp() - cached_data.get('timestamp', 0)
            return {
                'status': 'valid' if time_diff < self.UPDATE_INTERVAL else 'expired',
                'last_updated': cached_data.get('last_updated'),
                'days_old': round(time_diff / (24 * 60 * 60), 1)
            }
        except Exception as e:
            logging.error(f"Error checking cache status: {e}")
            return {'status': 'error'}

    def _cache_schedule_data(self, data: Dict, timestamp: float) -> bool:
        """缓存赛程数据"""
        cache_data = {
            'timestamp': timestamp,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data': data
        }
        return self._save_to_file(cache_data, self.cache_file)