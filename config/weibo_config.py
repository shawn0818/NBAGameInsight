import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class WeiboConfig:
    """微博配置类"""
    
    class PATHS:
        """文件路径配置"""
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        COOKIES_FILE = os.getenv('WEIBO_COOKIES_PATH', os.path.join(BASE_DIR, "weibo_cookies.json"))
    
    class PUBLISH:
        """发布相关配置"""
        POST_INTERVAL = int(os.getenv('WEIBO_POST_INTERVAL', '60'))  # 发布间隔（秒）
        MAX_RETRIES = 3  # 发布失败最大重试次数
        RETRY_DELAY = 5  # 重试间隔（秒）
        
    class BROWSER:
        """浏览器相关配置"""
        HEADLESS = False  # 是否隐藏浏览器界面
        VIEWPORT = {
            'width': 1280,
            'height': 800
        }
        
    @classmethod
    def initialize(cls):
        """初始化配置"""
        # 如果将来需要初始化操作，可以在这里添加
        pass
