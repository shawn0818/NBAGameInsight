# game_config/nba_config.py

from pathlib import Path

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

        #缓存目录
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

    class APP:
        """应用程序配置"""
        DEBUG = False
        TESTING = False
        MAX_WORKERS = 4  # 最大工作线程数

