# game_stats_db_manager.py
import sqlite3
import os
from utils.logger_handler import AppLogger
from config import NBAConfig


class GameStatsDBManager:
    """NBA比赛统计数据库管理器 - 负责创建和管理比赛统计数据的SQLite数据库连接"""

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
            self.logger.info(f"成功连接到比赛统计数据库: {self.db_path}")
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

            # 创建球员比赛数据统计表（statistics）- 包含比赛信息和球员统计
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                -- 比赛标识字段
                game_id TEXT NOT NULL,
                person_id INTEGER NOT NULL,
                team_id INTEGER NOT NULL,

                -- 比赛基本信息字段 
                home_team_id INTEGER,
                away_team_id INTEGER,
                home_team_tricode TEXT,
                away_team_tricode TEXT,
                home_team_name TEXT,
                home_team_city TEXT,
                away_team_name TEXT,
                away_team_city TEXT,
                game_status INTEGER,
                home_team_score INTEGER,
                away_team_score INTEGER,
                game_time TEXT,
                game_date TEXT,
                period INTEGER,
                video_available INTEGER DEFAULT 0,

                -- 球员个人信息字段
                first_name TEXT,
                family_name TEXT,
                name_i TEXT,
                player_slug TEXT,
                position TEXT,
                jersey_num TEXT,
                comment TEXT,
                is_starter INTEGER DEFAULT 0,

                -- 球员统计数据字段
                minutes TEXT,
                field_goals_made INTEGER DEFAULT 0,
                field_goals_attempted INTEGER DEFAULT 0,
                field_goals_percentage REAL DEFAULT 0,
                three_pointers_made INTEGER DEFAULT 0,
                three_pointers_attempted INTEGER DEFAULT 0,
                three_pointers_percentage REAL DEFAULT 0,
                free_throws_made INTEGER DEFAULT 0,
                free_throws_attempted INTEGER DEFAULT 0,
                free_throws_percentage REAL DEFAULT 0,
                rebounds_offensive INTEGER DEFAULT 0,
                rebounds_defensive INTEGER DEFAULT 0,
                rebounds_total INTEGER DEFAULT 0,
                assists INTEGER DEFAULT 0,
                steals INTEGER DEFAULT 0,
                blocks INTEGER DEFAULT 0,
                turnovers INTEGER DEFAULT 0,
                fouls_personal INTEGER DEFAULT 0,
                points INTEGER DEFAULT 0,
                plus_minus_points REAL DEFAULT 0,

                -- 元数据字段
                last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                PRIMARY KEY (game_id, person_id)
            )
            ''')

            # 为statistics表创建索引以提高查询性能
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_statistics_game ON statistics (game_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_statistics_teams ON statistics (home_team_id, away_team_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_statistics_date ON statistics (game_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_statistics_status ON statistics (game_status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_statistics_team ON statistics (team_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_statistics_points ON statistics (points)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_statistics_position ON statistics (position)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_statistics_name ON statistics (first_name, family_name)')

            # 创建回合动作数据表 (events)
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                -- 动作标识字段
                game_id TEXT NOT NULL,
                action_number INTEGER NOT NULL,

                -- 回合动作信息字段
                clock TEXT,
                period INTEGER,
                team_id INTEGER,
                team_tricode TEXT,
                person_id INTEGER,
                player_name TEXT,
                player_name_i TEXT,
                x_legacy INTEGER,
                y_legacy INTEGER,
                shot_distance INTEGER,
                shot_result TEXT,
                is_field_goal INTEGER DEFAULT 0,
                score_home TEXT,
                score_away TEXT,
                points_total INTEGER DEFAULT 0,
                location TEXT,
                description TEXT,
                action_type TEXT,
                sub_type TEXT,
                video_available INTEGER DEFAULT 0,
                shot_value INTEGER DEFAULT 0,
                action_id INTEGER,

                -- 元数据字段
                last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                PRIMARY KEY (game_id, action_number)
            )
            ''')

            # 为events表创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_game ON events (game_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_person ON events (person_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_team ON events (team_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_period ON events (period)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_action_type ON events (action_type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_shot_result ON events (shot_result)')

            # 创建同步历史记录表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_stats_sync_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type TEXT NOT NULL,
                game_id TEXT,
                status TEXT NOT NULL,
                items_processed INTEGER,
                items_succeeded INTEGER,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                details TEXT,
                error_message TEXT
            )
            ''')

            self.conn.commit()
            self.logger.info("比赛统计数据库结构初始化完成")

        except sqlite3.Error as e:
            self.logger.error(f"初始化数据库结构失败: {e}")
            self.conn.rollback()
            raise