import sqlite3
import os
from utils.logger_handler import AppLogger
from config import NBAConfig


class DBManager:
    """NBA数据库管理器 - 负责创建和管理SQLite数据库连接"""

    def __init__(self, db_path=None):
        """
        初始化数据库管理器

        Args:
            db_path: 数据库文件路径，如果为None则使用配置中的默认路径
        """


        if db_path is None:
            db_path = str(NBAConfig.DATABASE.get_db_path())

        # 处理路径中的~（用户主目录）
        if isinstance(db_path, str) and db_path.startswith('~'):
            db_path = os.path.expanduser(db_path)

        self.db_path = db_path
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')

        # 确保数据库目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        # 创建数据库连接
        self.conn = None
        self.connect()

        # 初始化数据库结构
        self.init_db()

    def connect(self):
        """创建数据库连接"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            # 启用外键约束
            self.conn.execute("PRAGMA foreign_keys = ON")
            # 返回行作为字典
            self.conn.row_factory = sqlite3.Row
            self.logger.info(f"成功连接到数据库: {self.db_path}")
        except sqlite3.Error as e:
            self.logger.error(f"数据库连接失败: {e}")
            raise

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def init_db(self):
        """初始化数据库结构"""
        try:
            cursor = self.conn.cursor()

            # 创建球队表 - 使用小写列名
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS teams (
                team_id INTEGER PRIMARY KEY,       -- 对应API中的TEAM_ID
                abbreviation TEXT NOT NULL,        -- 对应API中的ABBREVIATION
                nickname TEXT NOT NULL,            -- 对应API中的NICKNAME
                year_founded INTEGER,              -- 对应API中的YEARFOUNDED
                city TEXT,                         -- 对应API中的CITY
                arena TEXT,                        -- 对应API中的ARENA
                arena_capacity TEXT,               -- 对应API中的ARENACAPACITY
                owner TEXT,                        -- 对应API中的OWNER
                general_manager TEXT,              -- 对应API中的GENERALMANAGER
                head_coach TEXT,                   -- 对应API中的HEADCOACH
                dleague_affiliation TEXT,          -- 对应API中的DLEAGUEAFFILIATION
                team_slug TEXT,                    
                logo BLOB,                         
                updated_at TIMESTAMP               
            )
            ''')

            # 创建球队索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_teams_abbr ON teams (abbreviation)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_teams_name ON teams (nickname, city)')

            # 创建球员表 - 使用小写列名
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                person_id INTEGER PRIMARY KEY,     -- 对应API中的PERSON_ID
                display_last_comma_first TEXT,     -- 对应API中的DISPLAY_LAST_COMMA_FIRST
                display_first_last TEXT NOT NULL,  -- 对应API中的DISPLAY_FIRST_LAST
                roster_status INTEGER,             -- 对应API中的ROSTERSTATUS
                from_year TEXT,                    -- 对应API中的FROM_YEAR
                to_year TEXT,                      -- 对应API中的TO_YEAR
                player_slug TEXT,                  -- 对应API中的PLAYERCODE
                team_id INTEGER,                   -- 对应API中的TEAM_ID
                games_played_flag TEXT,            -- 对应API中的GAMES_PLAYED_FLAG
                updated_at TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams (team_id)
            )
            ''')

            # 创建球员索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_name ON players (display_first_last)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_team ON players (team_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_status ON players (roster_status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_players_slug ON players (player_slug)')

            # 创建赛程表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                game_code TEXT,
                game_status INTEGER,
                game_status_text TEXT,
                game_date_est TEXT,
                game_time_est TEXT,
                game_date_time_est TEXT,
                game_date_utc TEXT,
                game_time_utc TEXT,
                game_date_time_utc TEXT,
                game_date TEXT,
                season_year TEXT,
                week_number INTEGER,
                week_name TEXT,
                series_game_number TEXT,
                if_necessary TEXT,
                series_text TEXT,
                arena_name TEXT,
                arena_city TEXT,
                arena_state TEXT,
                arena_is_neutral BOOLEAN,
                home_team_id INTEGER,
                home_team_name TEXT,
                home_team_city TEXT,
                home_team_tricode TEXT,
                home_team_slug TEXT,
                home_team_wins INTEGER,
                home_team_losses INTEGER,
                home_team_score INTEGER,
                home_team_seed INTEGER,
                away_team_id INTEGER,
                away_team_name TEXT,
                away_team_city TEXT,
                away_team_tricode TEXT,
                away_team_slug TEXT,
                away_team_wins INTEGER,
                away_team_losses INTEGER,
                away_team_score INTEGER,
                away_team_seed INTEGER,
                points_leader_id INTEGER,
                points_leader_first_name TEXT,
                points_leader_last_name TEXT,
                points_leader_team_id INTEGER,
                points_leader_points REAL,
                game_type TEXT,
                game_sub_type TEXT,
                game_label TEXT,
                game_sub_label TEXT,
                postponed_status TEXT,
                game_date_bjs TEXT,            -- 北京时间日期
                game_time_bjs TEXT,            -- 北京时间
                game_date_time_bjs TEXT,       -- 北京时间日期和时间
                updated_at TIMESTAMP           -- 记录更新时间
                    )
                    ''')

            # 创建用于提高查询性能的索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_date ON games (game_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_season ON games (season_year)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_teams ON games (home_team_id, away_team_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_status ON games (game_status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_date_utc ON games (game_date_time_utc)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_date_bjs ON games (game_date_bjs)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_games_type ON games (game_type)')


            self.conn.commit()
            self.logger.info("数据库结构初始化完成")


        except sqlite3.Error as e:
            self.logger.error(f"初始化数据库结构失败: {e}")
            self.conn.rollback()
            raise