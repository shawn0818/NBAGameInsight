# db_session.py
from contextlib import contextmanager
from typing import Dict, Generator, Optional
from sqlalchemy.orm import Session, scoped_session
from sqlalchemy.engine import Engine
import threading
import logging
from database.connection_pool import ConnectionPool
from config import NBAConfig

logger = logging.getLogger(__name__)


class DBSession:
    """数据库会话管理器 - 提供统一的会话访问接口"""

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'DBSession':
        """单例模式获取实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        """初始化数据库会话管理器"""
        self.connection_pool = ConnectionPool()
        self.scoped_sessions: Dict[str, scoped_session] = {}

    def initialize(self, env: str = "default", create_tables: bool = True) -> None:
        """
        初始化数据库连接

        Args:
            env: 环境名称，可以是 "default", "test", "development", "production"
            create_tables: 是否创建表结构
        """
        # 获取环境配置
        echo_sql = False
        if env == "development":
            echo_sql = NBAConfig.DATABASE.DEVELOPMENT.ECHO_SQL
        elif env == "test":
            echo_sql = NBAConfig.DATABASE.TESTING.ECHO_SQL
        elif env == "production":
            echo_sql = False

        # 获取数据库路径
        nba_db_path = NBAConfig.DATABASE.get_db_path(env)
        game_db_path = NBAConfig.DATABASE.get_game_db_path(env)

        # 设置引擎
        self.connection_pool.setup_engine("nba", str(nba_db_path), echo=echo_sql)
        self.connection_pool.setup_engine("game", str(game_db_path), echo=echo_sql)

        # 设置scoped_session
        for db_name in ["nba", "game"]:
            factory = self.connection_pool.get_session_factory(db_name)
            if factory:
                self.scoped_sessions[db_name] = scoped_session(factory)

        # 创建表结构
        if create_tables:
            # Import model bases
            from database.models.base_models import Base as NBABase
            from database.models.stats_models import Base as GameBase

            # Create tables in respective databases
            NBABase.metadata.create_all(self.connection_pool.get_engine("nba"))
            GameBase.metadata.create_all(self.connection_pool.get_engine("game"))

        logger.info(f"已初始化数据库连接，环境: {env}")

    def get_engine(self, db_name: str) -> Optional[Engine]:
        """获取指定数据库的引擎"""
        return self.connection_pool.get_engine(db_name)

    def get_session(self, db_name: str) -> Optional[Session]:
        """获取指定数据库的会话"""
        scoped = self.scoped_sessions.get(db_name)
        if scoped:
            return scoped()
        logger.error(f"数据库 '{db_name}' 未配置")
        return None

    @contextmanager
    def session_scope(self, db_name: str) -> Generator[Session, None, None]:
        """
        创建会话上下文管理器，自动处理提交和回滚

        Args:
            db_name: 数据库名称

        Yields:
            Session: 数据库会话对象

        Example:
            with DBSession.get_instance().session_scope('nba') as session:
                teams = session.query(Team).all()
        """
        session = self.get_session(db_name)
        if not session:
            raise ValueError(f"无法获取数据库 '{db_name}' 的会话")

        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"会话操作失败: {e}", exc_info=True)
            raise
        finally:
            session.close()

    def close_all(self):
        """关闭所有数据库连接"""
        # 移除所有scoped_session
        for name, scoped in self.scoped_sessions.items():
            scoped.remove()
            logger.info(f"已移除数据库 '{name}' 的scoped_session")

        # 关闭所有连接
        self.connection_pool.close_all()
        logger.info("所有数据库连接已关闭")