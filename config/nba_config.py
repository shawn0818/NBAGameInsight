from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler

def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent

class NBAConfig:
    """NBA应用程序配置"""
    
    class URLS:
        """API端点配置"""
        BASE_URL = "https://cdn.nba.com/static/json"
        S3_BASE_URL = "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA"
        STATS_URL = "https://stats.nba.com"
        
        # API endpoints
        SCHEDULE = f"{BASE_URL}/staticData/scheduleLeagueV2_1.json"
        LIVE_DATA = f"{BASE_URL}/liveData"
        VIDEO_DATA = f"{STATS_URL}/stats/videodetailsasset"
        PLAYER_PROFILE = f"{BASE_URL}/staticData/playerIndex.json"
        TEAM_STATS = f"{STATS_URL}/stats/teamstats"
    
    class PATHS:
        """文件路径配置"""
        # 基础目录
        _ROOT = get_project_root()
        DATA_DIR = _ROOT / "data"
        LOGS_DIR = DATA_DIR / "logs"
        STORAGE_DIR = _ROOT / "storage"
        CACHE_DIR = DATA_DIR / "cache"

        # 媒体目录
        PICTURES_DIR = STORAGE_DIR / "images"
        VIDEO_DIR = STORAGE_DIR / "videos"
        GIF_DIR = STORAGE_DIR / "gifs"
        
        # 缓存文件
        SCHEDULE_CACHE = CACHE_DIR / "schedule.json"
        GAME_CACHE = CACHE_DIR / "games"
        PLAYER_CACHE = CACHE_DIR / "players"
        TEAM_CACHE = CACHE_DIR / "teams"
        
        # 日志文件
        APP_LOG = LOGS_DIR / "app.log"
        ERROR_LOG = LOGS_DIR / "error.log"
        DEBUG_LOG = LOGS_DIR / "debug.log"
        
        @classmethod
        def ensure_directories(cls):
            """确保所有必要的目录存在"""
            directories = [
                cls.CACHE_DIR,
                cls.LOGS_DIR,
                cls.PICTURES_DIR,
                cls.VIDEO_DIR,
                cls.GIF_DIR,
                cls.GAME_CACHE,
                cls.PLAYER_CACHE,
                cls.TEAM_CACHE
            ]
            for directory in directories:
                directory.mkdir(parents=True, exist_ok=True)
    
    class API:
        """API相关配置"""
        UPDATE_INTERVAL = 7 * 24 * 60 * 60  # 缓存更新间隔（7天）
        GAME_UPDATE_INTERVAL = 30  # 比赛数据更新间隔（秒）
        MAX_RETRIES = 3  # 最大重试次数
        TIMEOUT = 30
    
    class APP:
        """应用程序配置"""
        DEBUG = False
        TESTING = False
        MAX_WORKERS = 4  # 最大工作线程数

    @classmethod
    def initialize(cls):
        """初始化应用配置"""
        # 创建必要的目录
        cls.PATHS.ensure_directories()
        
        # 设置日志配置
        cls.setup_logging()
    
    @classmethod
    def setup_logging(cls):
        """配置日志"""
        # 确保日志目录存在
        cls.PATHS.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # 配置主应用日志
        app_handler = RotatingFileHandler(
            cls.PATHS.APP_LOG,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        app_handler.setFormatter(formatter)
        app_handler.setLevel(logging.INFO)
        
        # 配置错误日志
        error_handler = RotatingFileHandler(
            cls.PATHS.ERROR_LOG,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.ERROR)
        
        # 配置调试日志
        debug_handler = RotatingFileHandler(
            cls.PATHS.DEBUG_LOG,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=3
        )
        debug_handler.setFormatter(formatter)
        debug_handler.setLevel(logging.DEBUG)
        
        # 配置根日志记录器
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(app_handler)
        root_logger.addHandler(error_handler)
        root_logger.addHandler(debug_handler)


# 初始化配置
NBAConfig.initialize()