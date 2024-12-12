from typing import Dict, Optional
import json
import logging
from utils.http_handler import HTTPConfig, HTTPRequestManager
from config.nba_config import NBAConfig

class BaseNBAFetcher:
    """NBA数据获取基类 - 提供基础的HTTP请求和文件操作功能"""
    
    def __init__(self):
        """初始化HTTP请求管理器"""
        self.http_manager = HTTPRequestManager(
            max_retries=NBAConfig.API.MAX_RETRIES,
            timeout=NBAConfig.API.TIMEOUT
        )

    def _make_request(self, url: str) -> Optional[Dict]:
        """
        发送HTTP请求
        
        Args:
            url (str): 请求URL
            
        Returns:
            Optional[Dict]: 响应数据
        """
        try:
            response = self.http_manager.make_request(url)
            if not response:
                logging.warning(f"No data received from {url}")
            return response
        except Exception as e:
            logging.error(f"Error making request to {url}: {e}")
            return None

    def _read_file(self, filepath: str) -> Optional[Dict]:
        """
        从文件读取数据
        
        Args:
            filepath (str): 文件路径
            
        Returns:
            Optional[Dict]: 读取的数据
        """
        try:
            with open(filepath, 'r') as file:
                return json.load(file)
        except Exception as e:
            logging.error(f"Error reading file {filepath}: {e}")
            return None

    def _save_to_file(self, data: Dict, filepath: str) -> bool:
        """
        保存数据到文件
        
        Args:
            data (Dict): 要保存的数据
            filepath (str): 文件路径
            
        Returns:
            bool: 是否保存成功
        """
        try:
            with open(filepath, 'w') as file:
                json.dump(data, file, indent=4)
            return True
        except Exception as e:
            logging.error(f"Error saving data to file {filepath}: {e}")
            return False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.http_manager.close()