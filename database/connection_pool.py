# connection_pool.py
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
import os
from typing import Dict, Optional
import logging
from config import NBAConfig

logger = logging.getLogger(__name__)


class ConnectionPool:
    """数据库连接池管理器，支持多数据库实例"""

    def __init__(self):
        """初始化连接池管理器"""
        self.engines: Dict[str, Engine] = {}
        self.session_factories: Dict[str, sessionmaker] = {}
        self.db_paths: Dict[str, str] = {}

        # 确保数据目录存在
        NBAConfig.PATHS.ensure_directories()

    def setup_engine(self, name: str, db_path: str, echo: bool = False,
                     pool_size: int = 5, max_overflow: int = 10,
                     pool_timeout: int = 30) -> Engine:
        """
        创建并配置SQLAlchemy引擎

        Args:
            name: 数据库实例名称(用于引用)
            db_path: 数据库文件路径
            echo: 是否打印SQL语句
            pool_size: 连接池大小
            max_overflow: 最大溢出连接数
            pool_timeout: 连接超时时间(秒)

        Returns:
            Engine: SQLAlchemy引擎实例
        """
        # 确保目录存在
        if isinstance(db_path, str) and db_path.startswith('~'):
            db_path = os.path.expanduser(db_path)

        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # 创建SQLite连接URL
        db_url = f"sqlite:///{db_path}"

        # 创建引擎
        engine = create_engine(
            db_url,
            echo=echo,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            # SQLite特定参数
            connect_args={
                "check_same_thread": False,  # 允许多线程访问
                "timeout": NBAConfig.DATABASE.TIMEOUT,
                "isolation_level": NBAConfig.DATABASE.ISOLATION_LEVEL,
            }
        )

        # 存储引擎和路径
        self.engines[name] = engine
        self.db_paths[name] = db_path

        # 创建会话工厂
        self.session_factories[name] = sessionmaker(bind=engine)

        logger.info(f"数据库引擎 '{name}' 创建成功, 路径: {db_path}")
        return engine

    def get_engine(self, name: str) -> Optional[Engine]:
        """获取指定名称的数据库引擎"""
        engine = self.engines.get(name)
        if not engine:
            logger.error(f"数据库引擎 '{name}' 不存在")
        return engine

    def get_session_factory(self, name: str) -> Optional[sessionmaker]:
        """获取指定名称的会话工厂"""
        factory = self.session_factories.get(name)
        if not factory:
            logger.error(f"数据库会话工厂 '{name}' 不存在")
        return factory

    def close_all(self):
        """关闭所有数据库连接"""
        for name, engine in self.engines.items():
            engine.dispose()
            logger.info(f"数据库引擎 '{name}' 已关闭")

        self.engines.clear()
        self.session_factories.clear()