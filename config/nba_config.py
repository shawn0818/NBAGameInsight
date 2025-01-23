# config/nba_config.py
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler

def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent


class NBAConfig:
    """NBA应用程序全局配置"""

    class LEAGUE:
        """联盟相关配置"""
        NBA_ID = '00'
        WNBA_ID = '10'
        G_LEAGUE_ID = '20'

        # 比赛类型
        SEASON_TYPES = {
            'REGULAR': 'Regular Season',
            'PLAYOFFS': 'Playoffs',
            'PRESEASON': 'Pre Season',
            'ALLSTAR': 'All Star'
        }

        # 数据统计模式
        PER_MODES = {
            'GAME': 'PerGame',
            'TOTALS': 'Totals',
            'PER36': 'Per36',
            'PER100': 'Per100Possessions'
        }


    class PATHS:
        """文件路径配置"""
        _ROOT = get_project_root()

        # 静态资源目录
        STATIC_DIR = _ROOT / "static"
        IMAGES_DIR = STATIC_DIR / "images"

        # 动态数据目录
        DATA_DIR = _ROOT / "data"
        TEST_DIR = _ROOT / "test"
        LOGS_DIR = DATA_DIR / "logs"
        STORAGE_DIR = _ROOT / "storage"
        CACHE_DIR = DATA_DIR / "cache"
        TEMP_DIR = DATA_DIR / ".temp"

        # 媒体存储目录
        PICTURES_DIR = STORAGE_DIR / "images"
        VIDEO_DIR = STORAGE_DIR / "videos"
        GIF_DIR = STORAGE_DIR / "gifs"

        # 日志文件
        APP_LOG = LOGS_DIR / "app.log"
        ERROR_LOG = LOGS_DIR / "error.log"
        DEBUG_LOG = LOGS_DIR / "debug.log"

        @classmethod
        def ensure_directories(cls):
            """确保所有必要的目录存在"""
            # 静态资源目录
            cls.STATIC_DIR.mkdir(parents=True, exist_ok=True)
            cls.IMAGES_DIR.mkdir(parents=True, exist_ok=True)

            # 动态数据目录
            cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
            cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
            cls.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cls.TEMP_DIR.mkdir(parents=True, exist_ok=True)

            # 媒体目录
            cls.PICTURES_DIR.mkdir(parents=True, exist_ok=True)
            cls.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
            cls.GIF_DIR.mkdir(parents=True, exist_ok=True)

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
        # 获取根日志记录器
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG if cls.APP.DEBUG else logging.INFO)

        # 日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # 文件处理器
        file_handler = RotatingFileHandler(
            cls.PATHS.APP_LOG,
            maxBytes=10**6,  # 1MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # 错误日志处理器
        error_handler = RotatingFileHandler(
            cls.PATHS.ERROR_LOG,
            maxBytes=10**6,
            backupCount=5
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)

        # 调试日志处理器（仅在DEBUG模式下启用）
        if cls.APP.DEBUG:
            debug_handler = RotatingFileHandler(
                cls.PATHS.DEBUG_LOG,
                maxBytes=10**6,
                backupCount=3
            )
            debug_handler.setLevel(logging.DEBUG)
            debug_handler.setFormatter(formatter)
            logger.addHandler(debug_handler)

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)


# 初始化配置
NBAConfig.initialize()