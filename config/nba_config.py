from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any, Callable, List

def get_project_root() -> Path:
    """获取项目根目录。"""
    return Path(__file__).parent.parent    

class NBAConfig:
    """NBA应用程序配置。"""
    
    class LEAGUE:
        """联盟相关配置。"""
        NBA_ID = '00'
        WNBA_ID = '10'
        G_LEAGUE_ID = '20'
        
        SEASON_TYPES = {
            'REGULAR': 'Regular Season',
            'PLAYOFFS': 'Playoffs',
            'PRESEASON': 'Pre Season',
            'ALLSTAR': 'All Star'
        }
        
        PER_MODES = {
            'GAME': 'PerGame',
            'TOTALS': 'Totals',
            'PER36': 'Per36',
            'PER100': 'Per100Possessions'
        }
    
    class URLS:
        """API端点配置。"""
        BASE_URL = "https://cdn.nba.com/static/json"
        S3_BASE_URL = "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA"
        STATS_URL = "https://stats.nba.com"
        
        # API端点
        SCHEDULE = f"{BASE_URL}/staticData/scheduleLeagueV2_1.json"
        LIVE_DATA = f"{BASE_URL}/liveData"
        VIDEO_DATA = f"{STATS_URL}/stats/videodetailsasset"
        PLAYER_PROFILE = f"{BASE_URL}/staticData/playerIndex.json"
        TEAM_STATS = f"{STATS_URL}/stats/teamstats"
        
        # 新增联盟数据相关端点
        STATS_BASE = f"{STATS_URL}/stats"
        ALL_PLAYERS = f"{STATS_BASE}/commonallplayers"
        PLAYOFF_PICTURE = f"{STATS_BASE}/playoffpicture"
        LEAGUE_LEADERS = f"{STATS_BASE}/alltimeleadersgrids"
        PLAYOFF_SERIES = f"{STATS_BASE}/commonplayoffseries"
    
    class PATHS:
        """文件路径配置。"""
        _ROOT = get_project_root()

        # 静态资源目录（存放不会变动的文件）
        STATIC_DIR = _ROOT / "static"
        IMAGES_DIR = STATIC_DIR / "images"  # 静态图片，如logo等

        # 动态数据目录（存放运行时生成的数据）
        DATA_DIR = _ROOT / "data"
        TEST_DIR = _ROOT / "test"
        LOGS_DIR = DATA_DIR / "logs"
        STORAGE_DIR = _ROOT / "storage"
        CACHE_DIR = DATA_DIR / "cache"

        PICTURES_DIR = STORAGE_DIR / "images"
        VIDEO_DIR = STORAGE_DIR / "videos"
        GIF_DIR = STORAGE_DIR / "gifs"
        
        LEAGUE_CACHE = CACHE_DIR / "league"  # 联盟数据缓存目录
        SCHEDULE_CACHE = CACHE_DIR / "schedule"
        GAME_CACHE = CACHE_DIR / "games"
        PLAYER_CACHE = CACHE_DIR / "players"
        TEAM_CACHE = CACHE_DIR / "teams"
        
        APP_LOG = LOGS_DIR / "app.log"
        ERROR_LOG = LOGS_DIR / "error.log"
        DEBUG_LOG = LOGS_DIR / "debug.log"
        
        @classmethod
        def ensure_directories(cls):
            """确保所有必要的目录存在。"""
            # 静态资源目录
            cls.STATIC_DIR.mkdir(parents=True, exist_ok=True)
            cls.IMAGES_DIR.mkdir(parents=True, exist_ok=True)

            
            # 动态数据目录
            cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
            cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
            cls.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)

            # 缓存目录
            cls.LEAGUE_CACHE.mkdir(parents=True, exist_ok=True)
            cls.SCHEDULE_CACHE.mkdir(parents=True, exist_ok=True)
            cls.GAME_CACHE.mkdir(parents=True, exist_ok=True)
            cls.PLAYER_CACHE.mkdir(parents=True, exist_ok=True)
            cls.TEAM_CACHE.mkdir(parents=True, exist_ok=True)

            
            # 存储目录
            cls.PICTURES_DIR.mkdir(parents=True, exist_ok=True)
            cls.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
            cls.GIF_DIR.mkdir(parents=True, exist_ok=True)
            



    class API:
        """API相关配置。"""
        UPDATE_INTERVAL = 7 * 24 * 60 * 60  # 缓存更新间隔（7天）
        GAME_UPDATE_INTERVAL = 30  # 比赛数据更新间隔（秒）
        PLAYERS_UPDATE_INTERVAL = 7 * 24 * 60 * 60  # 球员数据缓存更新间隔（7天）
        SCHEDULE_UPDATE_INTERVAL = 7 * 24 * 60 * 60  # 赛程数据缓存更新间隔（7天）
        LEAGUE_LEADERS_UPDATE_INTERVAL = 7 * 24 * 60 * 60  # 联盟领袖数据缓存更新间隔（7天）
        MAX_RETRIES = 3  # 最大重试次数
        TIMEOUT = 30
        RETRY_STATUS_CODES: List[int] = [500, 502, 503, 504]  # 定义需要重试的状态码
        
        # API端点
        ENDPOINTS = {
            'ALL_PLAYERS': 'commonallplayers',
            'PLAYOFF_PICTURE': 'playoffpicture',
            'LEAGUE_LEADERS': 'alltimeleadersgrids',
            'PLAYOFF_SERIES': 'commonplayoffseries'
        }
        
        # 故障转移URL规则
        FALLBACK_URLS: Dict[str, str] = {
            "https://cdn.nba.com/static/json": "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA",
            "https://stats.nba.com/stats": "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA/stats"
        }

        
    
    class APP:
        """应用程序配置。"""
        DEBUG = False
        TESTING = False
        MAX_WORKERS = 4  # 最大工作线程数

    @classmethod
    def initialize(cls):
        """初始化应用配置。"""
        # 创建必要的目录
        cls.PATHS.ensure_directories()
        
        # 设置日志配置
        cls.setup_logging()
    
    @classmethod
    def setup_logging(cls):
        """配置日志。"""
        # 获取根日志记录器
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG if cls.APP.DEBUG else logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # 文件处理器
        file_handler = RotatingFileHandler(cls.PATHS.APP_LOG, maxBytes=10**6, backupCount=5)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

# 初始化配置
NBAConfig.initialize()
