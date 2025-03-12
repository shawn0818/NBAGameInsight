import sqlite3
import os
from utils.logger_handler import AppLogger


class DBManager:
    """
    NBA数据库管理器
    负责创建和管理SQLite数据库连接
    """

    def __init__(self, db_path="data/nba.db"):
        """初始化数据库管理器"""
        self.db_path = db_path
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

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

            # 创建球队表 - 完全按照API结构设计
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS team (
                TEAM_ID INTEGER PRIMARY KEY,
                ABBREVIATION TEXT NOT NULL,
                NICKNAME TEXT NOT NULL,
                YEARFOUNDED INTEGER,
                CITY TEXT,
                ARENA TEXT,
                ARENACAPACITY TEXT,
                OWNER TEXT,
                GENERALMANAGER TEXT,
                HEADCOACH TEXT,
                DLEAGUEAFFILIATION TEXT,
                team_slug TEXT,          -- 额外的URL友好标识符
                logo BLOB,               -- 直接存储logo的二进制数据
                updated_at TIMESTAMP     -- 更新时间戳
            )
            ''')

            # 创建球队索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_team_abbr ON team (ABBREVIATION)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_team_name ON team (NICKNAME, CITY)')

            # 创建球员表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS player (
                player_id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                full_name TEXT NOT NULL,
                player_slug TEXT,
                team_id INTEGER,
                updated_at TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES team (TEAM_ID)
            )
            ''')

            # 创建球员索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_name ON player (full_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_team ON player (team_id)')

            # 创建赛程表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule (
                game_id TEXT PRIMARY KEY,
                season TEXT NOT NULL,
                game_date_utc TIMESTAMP,
                game_date_bjs TIMESTAMP,
                home_team_id INTEGER,
                away_team_id INTEGER,
                home_score INTEGER,
                away_score INTEGER,
                arena TEXT,
                game_status INTEGER DEFAULT 1,
                updated_at TIMESTAMP,
                FOREIGN KEY (home_team_id) REFERENCES team (TEAM_ID),
                FOREIGN KEY (away_team_id) REFERENCES team (TEAM_ID)
            )
            ''')

            # 创建赛程索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_schedule_date ON schedule (game_date_utc, game_date_bjs)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_schedule_teams ON schedule (home_team_id, away_team_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_schedule_season ON schedule (season)')

            self.conn.commit()
            self.logger.info("数据库结构初始化完成")

        except sqlite3.Error as e:
            self.logger.error(f"初始化数据库结构失败: {e}")
            self.conn.rollback()
            raise