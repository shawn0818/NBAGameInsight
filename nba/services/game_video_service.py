import logging
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
import time
import subprocess
from tqdm import tqdm

from nba.models.video_model import VideoAsset, ContextMeasure
from nba.fetcher.video_fetcher import VideoFetcher
from nba.parser.video_parser import VideoParser
from utils.http_handler import HTTPRequestManager
from config.nba_config import NBAConfig


@dataclass
class VideoOutputConfig:
    """视频输出统一配置"""
    format: str = 'mp4'  # 输出格式:mp4/gif
    quality: str = 'hd'  # 视频质量
    compress: bool = False  # 是否压缩
    compression_preset: str = 'medium'  # 压缩预设
    compression_crf: int = 23  # 压缩质量(0-51,值越小质量越好)
    compression_audio_bitrate: str = '128k'  # 音频比特率
    fps: int = 12  # GIF帧率
    scale: int = 960  # GIF宽度
    show_progress: bool = True  # 是否显示进度条
    chunk_size: int = 8192  # 下载分块大小
    max_workers: int = 3  # 最大并行下载数

    def get_output_path(self, game_id: str, event_id: str) -> Path:
        """获取统一的输出路径

        Args:
            game_id: 比赛ID
            event_id: 事件ID
            action_type: 动作类型

        Returns:
            Path: 输出文件路径
        """
        # 在文件名前加上"gamevideo"前缀
        filename = f"gamevideo_{game_id}_{event_id}"

        if self.format == 'gif':
            output_dir = NBAConfig.PATHS.GIF_DIR
        else:
            output_dir = NBAConfig.PATHS.VIDEO_DIR

        return output_dir / f"{filename}.{self.format}"


class GameVideoService:
    """NBA比赛视频服务"""

    def __init__(
            self,
            http_manager: Optional[HTTPRequestManager] = None,
            max_retries: int = 3,
            timeout: Optional[int] = None,
            video_config: Optional[VideoOutputConfig] = None
    ):
        """初始化服务"""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = video_config or VideoOutputConfig()
        self.max_retries = max_retries

        # NBA API专用headers
        nba_video_headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        }

        # 处理HTTP管理器的初始化
        if http_manager:
            self.http_manager = http_manager
            self.http_manager.session.headers.update(nba_video_headers)
        else:
            self.http_manager = HTTPRequestManager(
                headers=nba_video_headers,
                timeout=timeout or 15,
                max_retries=max_retries
            )

        # 简化重定向配置
        self.http_manager.session.max_redirects = 5

        # 确保临时目录存在
        NBAConfig.PATHS.TEMP_DIR.mkdir(parents=True, exist_ok=True)

    def get_game_videos(
            self,
            game_id: str,
            player_id: Optional[int] = None,
            context_measure: ContextMeasure = ContextMeasure.FGM
    ) -> Dict[str, VideoAsset]:
        """获取比赛相关视频资源"""
        try:
            video_fetcher = VideoFetcher()
            video_parser = VideoParser()

            raw_data = video_fetcher.get_game_videos_raw(
                game_id=game_id,
                player_id=player_id,
                context_measure=context_measure
            )

            if not raw_data:
                self.logger.error("获取视频数据失败")
                return {}

            parsed_data = video_parser.parse_videos(raw_data)
            if not parsed_data:
                self.logger.error("解析视频数据失败")
                return {}

            return parsed_data.resultSets.get('video_assets', {})

        except Exception as e:
            self.logger.error(f"获取视频资源时出错: {e}")
            return {}

    def download_video(self, url: str, output_path: Path, show_progress: bool = True) -> bool:
        """下载单个视频"""
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                with self.http_manager.session.get(url, stream=True) as response:
                    if not response.ok:
                        raise Exception(f"HTTP错误: {response.status_code}")

                    total_size = int(response.headers.get('content-length', 0))

                    with open(output_path, 'wb') as f:
                        with tqdm(
                                total=total_size,
                                unit='iB',
                                unit_scale=True,
                                desc=f"下载中 {url.split('/')[-1]}",
                                disable=not show_progress
                        ) as progress_bar:
                            for chunk in response.iter_content(chunk_size=self.config.chunk_size):
                                if chunk:
                                    f.write(chunk)
                                    if progress_bar:
                                        progress_bar.update(len(chunk))
                    return True

            except Exception as e:
                retry_count += 1
                self.logger.warning(f"下载重试 {retry_count}/{self.max_retries}: {e}")
                if retry_count < self.max_retries:
                    time.sleep(1)
                continue

        self.logger.error(f"下载失败，已重试{self.max_retries}次")
        return False

    def convert_to_gif(self, input_path: Path, output_path: Path) -> bool:
        """将视频转换为GIF格式"""
        try:
            command = [
                'ffmpeg',
                '-i', str(input_path),
                '-vf', f'fps={self.config.fps},scale={self.config.scale}:-1:flags=lanczos',
                '-gifflags', '+transdiff',
                '-y',
                str(output_path)
            ]

            self.logger.info(f"执行FFmpeg命令: {' '.join(command)}")

            process = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if process.returncode == 0:
                self.logger.info(f"成功转换GIF: {output_path}")
                return True
            else:
                self.logger.error(f"GIF转换失败: {process.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"GIF转换失败: {e}")
            return False

    def compress_video(self, input_path: Path, output_path: Path) -> bool:
        """压缩视频"""
        try:
            command = [
                'ffmpeg',
                '-i', str(input_path),
                '-c:v', 'libx264',
                '-preset', self.config.compression_preset,
                '-crf', str(self.config.compression_crf),
                '-c:a', 'aac',
                '-b:a', self.config.compression_audio_bitrate,
                '-y',
                str(output_path)
            ]

            process = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if process.returncode == 0:
                self.logger.info(f"成功压缩视频: {output_path}")
                return True
            else:
                self.logger.error(f"视频压缩失败: {process.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"视频压缩失败: {e}")
            return False

    def process_video(self, video_asset: VideoAsset, game_id: str) -> Optional[Path]:
        """处理单个视频

        Args:
            video_asset: 视频资产对象
            game_id: 比赛ID

        Returns:
            Optional[Path]: 处理后的文件路径，如果处理失败则返回None
        """
        try:
            video_url = video_asset.get_preferred_quality(self.config.quality).url
            final_path = self.config.get_output_path(
                game_id=game_id,
                event_id=video_asset.event_id
            )

            # 检查文件是否已存在
            if final_path.exists():
                self.logger.info(f"文件已存在，跳过下载: {final_path}")
                return final_path

            temp_path = final_path.with_suffix('.tmp')

            # 下载到临时文件
            if not self.download_video(video_url, temp_path):
                self.logger.error(f"下载视频失败: {video_url}")
                temp_path.unlink(missing_ok=True)
                return None

            try:
                # 根据配置处理视频
                if self.config.format == 'gif':
                    success = self.convert_to_gif(temp_path, final_path)
                elif self.config.compress:
                    success = self.compress_video(temp_path, final_path)
                else:
                    # 直接重命名临时文件
                    temp_path.replace(final_path)
                    success = True

                return final_path if success else None

            finally:
                # 确保清理临时文件
                temp_path.unlink(missing_ok=True)

        except Exception as e:
            self.logger.error(f"视频处理失败: {e}")
            return None

    def batch_process_videos(self, videos: Dict[str, VideoAsset], game_id: str) -> Dict[str, Path]:
        """并行处理多个视频

        Args:
            videos: 视频资产字典
            game_id: 比赛ID

        Returns:
            Dict[str, Path]: 处理结果字典，键为事件ID，值为输出文件路径
        """
        results = {}
        total = len(videos)
        self.logger.info(f"开始处理 {total} 个视频")

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            # 提交所有下载任务
            future_to_video = {
                executor.submit(self.process_video, video, game_id): event_id
                for event_id, video in videos.items()
            }

            # 使用tqdm显示总体进度
            with tqdm(total=total, desc="总体进度", unit="个") as pbar:
                for future in concurrent.futures.as_completed(future_to_video):
                    event_id = future_to_video[future]
                    try:
                        result_path = future.result()
                        if result_path:
                            results[event_id] = result_path
                            self.logger.info(f"成功处理视频 {event_id}")
                        else:
                            self.logger.error(f"处理视频失败 {event_id}")
                    except Exception as e:
                        self.logger.error(f"处理视频出错 {event_id}: {e}")
                    finally:
                        pbar.update(1)

        self.logger.info(f"完成处理 {len(results)}/{total} 个视频")
        return results

    def close(self):
        """关闭并清理资源"""
        if hasattr(self, 'http_manager'):
            self.http_manager.close()