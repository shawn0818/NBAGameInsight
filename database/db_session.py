# database/db_session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager
import threading
from utils.logger_handler import AppLogger
from config import NBAConfig


class DBSession:
    """数据库会话管理类，使用单例模式"""
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        """获取DBSession单例"""
        with cls._lock:
            if not cls._instance:
                cls._instance = DBSession()
            return cls._instance

    def __init__(self):
        """初始化数据库会话管理器"""
        self.engines = {}
        self.session_factories = {}
        self.scoped_sessions = {}  # 存储scoped_session实例
        self._initialized = False
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')

    def initialize(self, env="default", create_tables=False):
        """初始化数据库连接引擎和会话工厂

        Args:
            env: 环境配置名称，可以是"default", "development", "testing", "production"
            create_tables: 是否创建不存在的表，默认为False

        Returns:
            bool: 初始化是否成功
        """
        if self._initialized:
            return True

        try:
            # 确保数据目录存在
            NBAConfig.PATHS.ensure_directories()

            # 获取数据库路径
            nba_db_path = NBAConfig.DATABASE.get_db_path(env)
            game_db_path = NBAConfig.DATABASE.get_game_db_path(env)

            # 配置数据库连接
            db_config = {
                'nba': f'sqlite:///{nba_db_path}',
                'game': f'sqlite:///{game_db_path}',
                'default': f'sqlite:///{nba_db_path}'  # 默认使用nba数据库
            }

            # 配置SQLAlchemy引擎参数
            connect_args = {
                'timeout': NBAConfig.DATABASE.TIMEOUT,
                'isolation_level': NBAConfig.DATABASE.ISOLATION_LEVEL,
                'check_same_thread': False
            }

            # 根据环境设置echo参数
            if env == "development":
                echo = NBAConfig.DATABASE.DEVELOPMENT.ECHO_SQL
            elif env == "testing":
                echo = NBAConfig.DATABASE.TESTING.ECHO_SQL
            elif env == "production":
                echo = NBAConfig.DATABASE.PRODUCTION.ECHO_SQL
            else:
                echo = False

            # 为每个数据库创建引擎和会话工厂
            for db_name, conn_str in db_config.items():
                # 创建引擎
                engine = create_engine(
                    conn_str,
                    echo=echo,
                    connect_args=connect_args
                )
                self.engines[db_name] = engine

                # 创建会话工厂
                session_factory = sessionmaker(bind=engine, expire_on_commit=False)
                self.session_factories[db_name] = session_factory

                # 创建scoped_session
                self.scoped_sessions[db_name] = scoped_session(session_factory)

                # 如果需要创建表
                if create_tables:
                    # 这里需要导入相应的Base
                    from database.models.base_models import Base as BaseModels
                    from database.models.stats_models import Base as StatsModels

                    if db_name == 'nba':
                        BaseModels.metadata.create_all(engine)
                    elif db_name == 'game':
                        StatsModels.metadata.create_all(engine)

            self._initialized = True
            self.logger.info(f"数据库会话初始化成功，环境: {env}")
            return True

        except Exception as e:
            self.logger.error(f"初始化数据库会话失败: {e}", exc_info=True)
            return False

    def get_scoped_session(self, db_name='default'):
        """获取指定数据库的scoped_session实例"""
        if not self._initialized:
            raise Exception("DBSession not initialized")
        if db_name not in self.scoped_sessions:
            raise ValueError(f"未知数据库: {db_name}")
        return self.scoped_sessions[db_name]

    def remove_scoped_session(self, db_name='default'):
        """移除当前线程的scoped_session绑定"""
        if db_name in self.scoped_sessions:
            self.scoped_sessions[db_name].remove()

    @contextmanager
    def session_scope(self, db_name='default'):
        """创建数据库会话的上下文管理器

        Args:
            db_name: 数据库名称，可以是'nba', 'game', 'default'

        Yields:
            SQLAlchemy会话对象
        """
        if not self._initialized:
            raise Exception("DBSession not initialized")

        if db_name not in self.session_factories:
            raise ValueError(f"未知数据库: {db_name}")

        session = self.session_factories[db_name]()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"数据库会话操作失败: {e}", exc_info=True)
            raise
        finally:
            session.close()

    def close_all(self):
        """关闭所有数据库连接"""
        try:
            # 移除所有scoped_session
            for db_name in self.scoped_sessions:
                self.remove_scoped_session(db_name)

            # 处理引擎
            for engine in self.engines.values():
                engine.dispose()

            self._initialized = False
            self.logger.info("所有数据库连接已关闭")
            return True
        except Exception as e:
            self.logger.error(f"关闭数据库连接失败: {e}", exc_info=True)
            return False