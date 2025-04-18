"""
命令模式基类和错误处理 - 所有命令的基础类

提供命令模式的基础结构和统一错误处理机制。
"""
from abc import ABC, abstractmethod
import re
import functools
# 从其他模块导入的必要异常类
from nba.services.game_data_service import ServiceNotAvailableError


class AppError(Exception):
    """应用程序异常基类"""
    pass


class CommandExecutionError(AppError):
    """命令执行失败异常"""
    pass


class DataFetchError(AppError):
    """数据获取失败异常"""
    pass


def error_handler(func):
    """错误处理装饰器，统一处理命令执行中的异常"""

    @functools.wraps(func)
    def wrapper(self, app, *args, **kwargs):
        try:
            return func(self, app, *args, **kwargs)
        except ServiceNotAvailableError as e:
            # Try to extract service name from the error message if possible
            match = re.match(r"([\w_]+)\s+服务", str(e))
            service_name = match.group(1) if match else "未知服务"
            app.logger.error(f"服务不可用: {e}")
            print(f"× {service_name} 不可用: {e}")
            return False
        except DataFetchError as e:
             app.logger.error(f"数据获取失败: {e}", exc_info=True)
             print(f"× 数据获取失败: {e}")
             return False
        except CommandExecutionError as e:
             app.logger.error(f"命令执行错误: {e}", exc_info=True)
             print(f"× 命令执行错误: {e}")
             return False
        except Exception as e:
            command_name = self.__class__.__name__.replace('Command', '')
            app.logger.error(f"执行 '{command_name}' 命令时发生意外错误: {e}", exc_info=True)
            print(f"× 执行 '{command_name}' 时发生意外错误: {e}")
            return False

    return wrapper


class NBACommand(ABC):
    """NBA命令基类"""

    @abstractmethod
    def execute(self, app) -> bool:
        """执行命令，返回是否成功执行"""
        pass

    def _log_section(self, title: str) -> None:
        """打印分节标题"""
        print(f"\n=== {title} ===")



