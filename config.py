# ./config.py

from pathlib import Path


def get_project_root() -> Path:
    """获取项目根目录（查找包含.git/.env/pyproject.toml等标记文件的目录）"""
    current = Path(__file__).parent.resolve()

    # 向上查找直到找到标记文件
    marker_files = ['.gitignore', '.env', 'main.py']

    while current != current.parent:  # 防止到达文件系统根目录
        if any((current / marker).exists() for marker in marker_files):
            return current
        current = current.parent

    # 如果没找到标记文件，返回默认目录
    return Path(__file__).parent.resolve()


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
        #STATIC_DIR = _ROOT / "static"
        #IMAGES_DIR = STATIC_DIR / "images"

        # 动态数据目录
        DATA_DIR = _ROOT / "data"
        TEST_DIR = _ROOT / "test"
        LOGS_DIR = DATA_DIR / "logs"
        STORAGE_DIR = _ROOT / "storage"
        CACHE_DIR = DATA_DIR / "cache"
        TEMP_DIR = DATA_DIR / ".temp"

        # 数据库目录
        DB_DIR = DATA_DIR / "database"

        # 缓存目录
        GAME_CACHE_DIR = CACHE_DIR / "games"
        TEAM_CACHE_DIR = CACHE_DIR / "teams"
        PLAYER_CACHE_DIR = CACHE_DIR / "players"
        SCHEDULE_CACHE_DIR = CACHE_DIR / "schedule"
        VIDEOURL_CACHE_DIR = CACHE_DIR / "videourls"
        LEAGUE_CACHE_DIR = CACHE_DIR / "league"

        # 媒体存储目录
        PICTURES_DIR = STORAGE_DIR / "pictures"
        VIDEO_DIR = STORAGE_DIR / "videos"
        GIF_DIR = STORAGE_DIR / "gifs"
        # 添加特定子目录
        TEAM_VIDEOS_DIR = VIDEO_DIR / "team_videos"
        PLAYER_VIDEOS_DIR = VIDEO_DIR / "player_videos"
        GAME_HIGHLIGHTS_DIR = VIDEO_DIR / "game_highlights"

        # 日志文件
        APP_LOG = LOGS_DIR / "app.log"
        ERROR_LOG = LOGS_DIR / "error.log"
        DEBUG_LOG = LOGS_DIR / "debug.log"

        @classmethod
        def ensure_directories(cls):
            """确保所有必要的目录存在"""
            # 获取所有目录属性
            dir_paths = [
                value for name, value in vars(cls).items()
                if isinstance(value, Path) and name.endswith('_DIR')
            ]

            # 创建所有目录
            for path in dir_paths:
                path.mkdir(parents=True, exist_ok=True)

    class DATABASE:
        """数据库配置"""
        # 相对路径 - 在运行时会与项目根目录组合
        DEFAULT_DB_FILENAME = "nba.db"
        DEFAULT_DB_RELATIVE_PATH = "data/database/nba.db"
        TEST_DB_RELATIVE_PATH = "test/test_nba.db"

        # 添加game.db相关配置
        GAME_DB_FILENAME = "game.db"
        GAME_DB_RELATIVE_PATH = "data/database/game.db"
        TEST_GAME_DB_RELATIVE_PATH = "test/test_game.db"

        # 数据库连接配置
        TIMEOUT = 30  # 连接超时时间（秒）
        ISOLATION_LEVEL = None  # 自动提交模式
        FOREIGN_KEYS = True  # 启用外键约束
        CACHE_SIZE = -1024 * 64  # 缓存大小（KB，负值表示内存中的KB）

        # 同步配置
        AUTO_SYNC_ON_START = True  # 启动时自动同步
        SYNC_INTERVAL_HOURS = 24  # 数据自动同步间隔（小时）

        # 环境特定配置
        class DEVELOPMENT:
            """开发环境配置"""
            ECHO_SQL = True  # 输出SQL语句到日志
            FORCE_SYNC = False  # 强制同步数据

        class TESTING:
            """测试环境配置"""
            IN_MEMORY = False  # 是否使用内存数据库
            ECHO_SQL = True  # 输出SQL语句到日志

        class PRODUCTION:
            """生产环境配置"""
            ECHO_SQL = False  # 不输出SQL语句
            BACKUP_ENABLED = True  # 启用自动备份
            BACKUP_INTERVAL_DAYS = 7  # 备份间隔（天）
            MAX_BACKUP_COUNT = 5  # 最大备份文件数

        @classmethod
        def get_db_path(cls, env="default"):
            """
            根据环境获取数据库完整路径

            Args:
                env: 环境名称，可以是 "default", "test", "development", "production"

            Returns:
                Path: 数据库文件的完整路径
            """
            root = get_project_root()

            if env == "test":
                return root / cls.TEST_DB_RELATIVE_PATH

            # 默认使用常规数据库路径
            return root / cls.DEFAULT_DB_RELATIVE_PATH

        @classmethod
        def get_game_db_path(cls, env="default"):
            """
            根据环境获取game.db数据库完整路径

            Args:
                env: 环境名称，可以是 "default", "test", "development", "production"

            Returns:
                Path: game.db数据库文件的完整路径
            """
            root = get_project_root()

            if env == "test":
                return root / cls.TEST_GAME_DB_RELATIVE_PATH

            # 默认使用常规game数据库路径
            return root / cls.GAME_DB_RELATIVE_PATH

    class APP:
        """应用程序配置"""
        DEBUG = False
        TESTING = False
        MAX_WORKERS = 4  # 最大工作线程数
        ENV = "development"  # 默认环境：development, testing, production