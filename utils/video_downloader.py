import logging
import subprocess
from pathlib import Path
from typing import Optional
import requests
from config.nba_config import NBAConfig

logger = logging.getLogger(__name__)

class VideoDownloader:
    """视频下载工具类"""
    
    def __init__(self, session: Optional[requests.Session] = None):
        """
        初始化下载器
        
        Args:
            session: 可选的requests.Session对象,用于复用连接
        """
        self.session = session or requests.Session()

    def download(self, url: str, output_path: Path, chunk_size: int = 8192) -> bool:
        """
        下载视频文件
        
        Args:
            url: 视频URL
            output_path: 输出文件路径
            chunk_size: 分块大小
            
        Returns:
            bool: 下载是否成功
        """
        try:
            for _ in range(NBAConfig.API.MAX_RETRIES):
                try:
                    response = self.session.get(
                        url,
                        stream=True,
                        timeout=NBAConfig.API.TIMEOUT
                    )
                    response.raise_for_status()
                    
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            f.write(chunk)
                    return True
                    
                except requests.RequestException as e:
                    logger.warning(f"Retry after download error: {e}")
                    continue
                    
            return False
            
        except Exception as e:
            logger.error(f"Failed to download video: {e}")
            return False

class VideoConverter:
    """视频转换器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def to_gif(
        self, 
        video_path: Path, 
        output_path: Path, 
        fps: int = 12, 
        scale: int = 960, 
        remove_source: bool = False
    ) -> bool:
        """
        将视频转换为GIF格式

        Args:
            video_path (Path): 输入视频路径
            output_path (Path): 输出GIF路径
            fps (int): 帧率
            scale (int): 宽度，保持纵横比
            remove_source (bool): 是否删除源视频

        Returns:
            bool: 成功与否
        """
        try:
            # 构建FFmpeg命令
            command = [
                'ffmpeg',
                '-i', str(video_path),
                '-vf', f'fps={fps},scale={scale}:-1:flags=lanczos',
                '-gifflags', '+transdiff',
                '-y',  # 覆盖输出文件
                str(output_path)
            ]
            self.logger.info(f"Running FFmpeg command: {' '.join(command)}")
            
            # 运行命令
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            self.logger.info(f"Successfully converted to GIF: {output_path}")
            
            if remove_source:
                video_path.unlink()
            
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFmpeg conversion failed: {e.stderr.decode()}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during GIF conversion: {e}")
            return False
            
    @staticmethod
    def compress_video(
        video_path: Path,
        output_path: Path,
        crf: int = 23,
        preset: str = 'medium',
        remove_source: bool = False
    ) -> bool:
        """
        压缩视频文件
        
        Args:
            video_path: 源视频文件路径
            output_path: 输出文件路径
            crf: 压缩质量(0-51,值越小质量越好)
            preset: 编码速度预设
            remove_source: 转换完成后是否删除源文件
            
        Returns:
            bool: 压缩是否成功
        """
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            cmd = [
                'ffmpeg',
                '-i', str(video_path),
                '-c:v', 'libx264',
                '-crf', str(crf),
                '-preset', preset,
                '-c:a', 'aac',
                '-b:a', '128k',
                '-y',
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            if remove_source and video_path.exists():
                video_path.unlink()
                
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg compression failed: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Compression error: {e}")
            return False