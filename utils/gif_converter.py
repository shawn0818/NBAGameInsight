import logging
from pathlib import Path
import asyncio
from dataclasses import dataclass
from typing import Optional, Union


@dataclass
class GIFConfig:
    """GIF转换配置类"""
    fps: int = 12
    scale: int = 960
    max_retries: int = 3
    retry_delay: float = 1.0


class GIFConverter:
    """GIF转换工具类"""

    def __init__(self, config: Optional[GIFConfig] = None):
        self.config = config or GIFConfig()
        self.logger = logging.getLogger(self.__class__.__name__)

    async def convert_async(self, input_path: Union[str, Path], output_path: Union[str, Path]) -> bool:
        """异步将视频转换为GIF"""
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            self.logger.error(f"输入文件不存在: {input_path}")
            return False

        for retry in range(self.config.max_retries):
            try:
                command = [
                    'ffmpeg',
                    '-i', str(input_path),
                    '-vf', f'fps={self.config.fps},scale={self.config.scale}:-1:flags=lanczos',
                    '-y',
                    str(output_path)
                ]

                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                _, stderr = await process.communicate()

                if process.returncode == 0 and output_path.exists():
                    self.logger.info(f"成功生成GIF: {output_path.name}")
                    return True
                else:
                    error_msg = stderr.decode() if stderr else "未知错误"
                    self.logger.error(f"生成GIF失败: {error_msg}")
                    if retry < self.config.max_retries - 1:
                        self.logger.info(f"重试转换 ({retry + 1}/{self.config.max_retries})")
                        await asyncio.sleep(self.config.retry_delay)
                        continue
                    return False

            except asyncio.CancelledError:
                self.logger.warning(f"GIF转换任务被取消: {input_path}")
                raise
            except Exception as e:
                self.logger.error(f"GIF转换出错: {str(e)}")
                if retry < self.config.max_retries - 1:
                    self.logger.info(f"重试转换 ({retry + 1}/{self.config.max_retries})")
                    await asyncio.sleep(self.config.retry_delay)
                    continue
                return False

        return False

    def convert(self, input_path: Union[str, Path], output_path: Union[str, Path]) -> bool:
        """同步将视频转换为GIF"""
        return asyncio.run(self.convert_async(input_path, output_path))
