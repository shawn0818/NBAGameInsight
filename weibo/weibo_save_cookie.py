"""
微博 Cookie 更新模块
负责获取和更新 XSRF-TOKEN
"""

import logging
import json
from pathlib import Path
import requests
from typing import Optional, Dict

from config.weibo_config import WeiboConfig

logger = logging.getLogger(__name__)

class WeiboTokenManager:
    """微博 Token 管理器"""
    
    def __init__(self):
        self.config = WeiboConfig
        self.session = requests.Session()
        self.token_file = self.config.PATHS.DATA_DIR / 'weibo_token.json'
        
    def get_latest_token(self) -> Optional[str]:
        """获取最新的 XSRF-TOKEN"""
        try:
            # 1. 设置基本请求头和 cookies
            headers = {
                'authority': 'm.weibo.cn',
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                'dnt': '1',
                'origin': 'https://m.weibo.cn',
                'referer': 'https://m.weibo.cn/compose/',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            }
            
            # 2. 设置必要的 cookies
            cookies = {
                'SUB': self.config.MOBILE_API.COOKIES['SUB'],
                'SUBP': self.config.MOBILE_API.COOKIES['SUBP'],
                'MLOGIN': '1'
            }
            
            # 3. 发送请求获取新的 token
            response = requests.get(
                'https://m.weibo.cn/api/config',
                headers=headers,
                cookies=cookies
            )
            
            if response.status_code == 200:
                # 从响应的 cookies 中获取 XSRF-TOKEN
                if 'XSRF-TOKEN' in response.cookies:
                    token = response.cookies['XSRF-TOKEN']
                    self._save_token(token)
                    logger.info(f"成功获取新的 XSRF-TOKEN: {token}")
                    return token
                    
            logger.error("获取 XSRF-TOKEN 失败")
            return None
            
        except Exception as e:
            logger.error(f"获取 token 时出错: {e}")
            return None
            
    def _save_token(self, token: str) -> None:
        """保存 token 到文件"""
        try:
            data = {
                'XSRF-TOKEN': token,
                'timestamp': datetime.now().timestamp()
            }
            
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
                
        except Exception as e:
            logger.error(f"保存 token 时出错: {e}")

    def _load_token(self) -> Optional[str]:
        """从文件加载 token"""
        try:
            if not self.token_file.exists():
                return None
                
            with open(self.token_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('XSRF-TOKEN')
                
        except Exception as e:
            logger.error(f"加载 token 时出错: {e}")
            return None

def update_weibo_token():
    """更新微博 token 的便捷函数"""
    manager = WeiboTokenManager()
    return manager.get_latest_token()

if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 获取并保存新的 token
    token = update_weibo_token()
    if token:
        print(f"成功获取新的 XSRF-TOKEN: {token}")
    else:
        print("获取 XSRF-TOKEN 失败")
