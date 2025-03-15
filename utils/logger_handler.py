import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional, Union
from functools import lru_cache
from config import NBAConfig  # 这里仍然导入 NBAConfig 作为默认配置


class AppLogger:
    """应用程序通用日志工具类

    提供统一的日志配置和管理功能：
    1. 按应用和模块分类的日志文件
    2. 控制台和文件双重输出
    3. 自动日志轮转
    4. 错误日志分离
    5. 缓存logger实例
    """

    # 默认日志格式
    DEFAULT_FORMAT = '%(asctime)s - %(name)s - [%(levelname)s] - %(filename)s:%(lineno)d - %(message)s'
    ERROR_FORMAT = '%(asctime)s - %(name)s - [%(levelname)s] - %(pathname)s:%(lineno)d - %(message)s\nTraceback:\n%(exc_info)s'

    # 日志文件配置
    MAX_BYTES = 10 * 1024 * 1024  # 10MB
    BACKUP_COUNT = 5

    # 默认日志根目录
    _LOG_ROOT = NBAConfig.PATHS.LOGS_DIR  # 默认使用 NBA 配置

    @classmethod
    def set_log_root(cls, path: Union[str, Path]) -> None:
        """设置日志根目录"""
        cls._LOG_ROOT = Path(path)
        cls._LOG_ROOT.mkdir(parents=True, exist_ok=True)
        cls.get_logger.cache_clear()

    @classmethod
    @lru_cache(maxsize=32)
    def get_logger(cls,
                   name: str,
                   level: Union[int, str] = logging.INFO,
                   log_to_console: bool = True,
                   log_to_file: bool = True,
                   app_name: Optional[str] = None) -> logging.Logger:
        """获取logger实例

        Args:
            name: logger名称（通常使用__name__）
            level: 日志级别
            log_to_console: 是否输出到控制台
            log_to_file: 是否输出到文件
            app_name: 应用名称，用于日志分类存储

        Returns:
            logging.Logger: 配置好的logger实例
        """
        # 确保日志根目录存在
        cls._LOG_ROOT.mkdir(parents=True, exist_ok=True)

        # 创建logger
        logger = logging.getLogger(name)
        if logger.handlers:  # 防止重复配置
            return logger

        # 设置日志级别
        if isinstance(level, str):
            level = getattr(logging, level.upper())
        logger.setLevel(level)

        # 创建格式器
        formatter = logging.Formatter(
            cls.DEFAULT_FORMAT,
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        error_formatter = logging.Formatter(
            cls.ERROR_FORMAT,
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 添加控制台处理器
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        # 添加文件处理器
        if log_to_file:
            # 确定日志目录路径
            if app_name:
                # 如果指定了应用名称，则在应用目录下按模块分类
                module_name = name.split('.')[0]
                log_dir = cls._LOG_ROOT / app_name / module_name
            else:
                # 否则直接按模块分类
                module_name = name.split('.')[0]
                log_dir = cls._LOG_ROOT / module_name

            log_dir.mkdir(parents=True, exist_ok=True)

            # 常规日志文件
            log_file = log_dir / f"{name.replace('.', '_')}.log"
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=cls.MAX_BYTES,
                backupCount=cls.BACKUP_COUNT,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            # 每日轮转日志
            daily_file = log_dir / f"{name.replace('.', '_')}_daily.log"
            daily_handler = TimedRotatingFileHandler(
                daily_file,
                when='midnight',
                interval=1,
                backupCount=30,
                encoding='utf-8'
            )
            daily_handler.setFormatter(formatter)
            logger.addHandler(daily_handler)

            # 错误日志文件
            error_file = log_dir / f"{name.replace('.', '_')}_error.log"
            error_handler = RotatingFileHandler(
                error_file,
                maxBytes=cls.MAX_BYTES,
                backupCount=cls.BACKUP_COUNT,
                encoding='utf-8'
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(error_formatter)
            logger.addHandler(error_handler)

            # 如果在调试模式下，添加额外的调试日志
            if getattr(logger, 'debug_mode', False):
                debug_file = log_dir / f"{name.replace('.', '_')}_debug.log"
                debug_handler = RotatingFileHandler(
                    debug_file,
                    maxBytes=cls.MAX_BYTES,
                    backupCount=cls.BACKUP_COUNT,
                    encoding='utf-8'
                )
                debug_handler.setLevel(logging.DEBUG)
                debug_handler.setFormatter(formatter)
                logger.addHandler(debug_handler)

        return logger

    @classmethod
    def set_debug_mode(cls) -> None:
        """设置调试模式"""
        cls.get_logger.cache_clear()

    @classmethod
    def clear_cache(cls) -> None:
        """清除logger缓存"""
        cls.get_logger.cache_clear()