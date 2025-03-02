from pathlib import Path
from typing import List, Optional, Union, Dict
import subprocess
import threading
from dataclasses import dataclass
from utils.logger_handler import AppLogger
from concurrent.futures import ThreadPoolExecutor


@dataclass
class VideoProcessConfig:
    """视频处理配置"""
    ffmpeg_path: str = 'ffmpeg'
    max_workers: int = 3  # 并发处理数量
    max_retries: int = 3
    retry_delay: float = 1.0

    # GIF配置
    gif_fps: int = 12
    gif_scale: str = "960:-1"
    gif_quality: int = 20


class VideoProcessor:
    """视频处理工具类 (同步版本)"""

    def __init__(self, config: Optional[VideoProcessConfig] = None):
        self.config = config or VideoProcessConfig()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self._semaphore = threading.Semaphore(self.config.max_workers)
        self._executor = ThreadPoolExecutor(max_workers=self.config.max_workers)

    def _run_ffmpeg(self, cmd: List[str], task_id: str) -> bool:
        """同步执行ffmpeg命令"""
        with self._semaphore:
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                stdout, stderr = process.communicate()

                if process.returncode != 0:
                    self.logger.error(f"处理失败[{task_id}]: {stderr.decode()}")
                    return False

                return True

            except KeyboardInterrupt:
                self.logger.warning(f"任务被取消[{task_id}]")
                if process:
                    process.terminate()
                    process.wait()
                raise

            except Exception as e:
                self.logger.error(f"处理出错[{task_id}]: {str(e)}")
                return False

    def merge_videos(
            self,
            video_paths: List[Path],
            output_path: Path,
            remove_source: bool = False,
            force_reprocess: bool = False
    ) -> Optional[Path]:
        """同步合并多个视频文件"""
        task_id = f"merge_{output_path.stem}"
        file_list = output_path.parent / f"filelist_{task_id}.txt"  # 在这里初始化

        try:
            if not video_paths:
                return None

            # 增量处理: 检查是否已存在
            if not force_reprocess and output_path.exists():
                self.logger.info(f"合并视频已存在，跳过处理: {output_path}")
                return output_path

            # 创建filelist文件
            with open(file_list, "w") as f:
                for video_path in sorted(video_paths):
                    f.write(f"file '{video_path}'\n")

            cmd = [
                self.config.ffmpeg_path,
                '-f', 'concat',
                '-safe', '0',
                '-i', str(file_list),
                '-c', 'copy',
                str(output_path)
            ]

            success = self._run_ffmpeg(cmd, task_id)
            if success and remove_source:
                for video_path in video_paths:
                    video_path.unlink()

            return output_path if success else None

        except Exception as e:
            self.logger.error(f"合并失败[{task_id}]: {str(e)}")
            return None

        finally:
            if file_list.exists():
                file_list.unlink()

    def batch_convert_to_gif(
            self,
            video_paths: List[Path],
            output_dir: Path,
            force_reprocess: bool = False,
            **kwargs
    ) -> Dict[str, Path]:
        """批量同步转换GIF (使用线程池实现并行)"""
        # 确保输出目录存在
        output_dir.mkdir(parents=True, exist_ok=True)

        # 定义单个转换函数
        def convert_single(video_path):
            try:
                output_path = output_dir / f"{video_path.stem}.gif"

                # 增量处理: 检查是否已存在
                if not force_reprocess and output_path.exists():
                    self.logger.info(f"GIF已存在，跳过转换: {output_path}")
                    return video_path.stem, output_path

                # 这里将原来的变量名 result 改为 gif_result
                gif_result = self.convert_to_gif(video_path, output_path, **kwargs)
                if gif_result:
                    return video_path.stem, gif_result
                return None
            # 这里将原来的异常变量名 e 改为 conv_error
            except Exception as conv_error:
                self.logger.error(f"转换失败 {video_path}: {str(conv_error)}")
                return None

        # 使用线程池并行处理
        results = {}
        futures = {self._executor.submit(convert_single, path): path for path in video_paths}

        for future in futures:
            try:
                result = future.result()
                if result:
                    key, path = result
                    results[key] = path
            except Exception as e:
                self.logger.error(f"GIF转换任务失败: {str(e)}")

        return results

    def convert_to_gif(
            self,
            video_path: Path,
            output_path: Optional[Path] = None,
            force_reprocess: bool = False,
            **kwargs
    ) -> Optional[Path]:
        """同步转换单个视频到GIF"""
        if not output_path:
            output_path = video_path.with_suffix('.gif')

        task_id = f"gif_{output_path.stem}"

        # 增量处理: 检查是否已存在
        if not force_reprocess and output_path.exists():
            self.logger.info(f"GIF已存在，跳过转换: {output_path}")
            return output_path

        try:
            cmd = [self.config.ffmpeg_path, '-i', str(video_path)]

            # 添加可选参数
            if kwargs.get('start_time'):
                cmd.extend(['-ss', str(kwargs['start_time'])])
            if kwargs.get('duration'):
                cmd.extend(['-t', str(kwargs['duration'])])

            # 设置输出参数
            fps = kwargs.get('fps', self.config.gif_fps)
            scale = kwargs.get('scale', self.config.gif_scale)
            quality = kwargs.get('quality', self.config.gif_quality)

            cmd.extend([
                '-vf', f'fps={fps},scale={scale}:flags=lanczos',
                '-c:v', 'gif',
                '-q:v', str(quality),
                str(output_path)
            ])

            success = self._run_ffmpeg(cmd, task_id)
            return output_path if success else None

        except Exception as e:
            self.logger.error(f"GIF转换失败[{task_id}]: {str(e)}")
            return None

    def process_videos(
            self,
            videos: Dict[str, Path],
            merge: bool = True,
            to_gif: bool = False,
            force_reprocess: bool = False,
            **kwargs
    ) -> Dict[str, Union[Path, Dict[str, Path]]]:
        """综合处理视频 (同步版本)"""
        results = {}
        video_paths = list(videos.values())

        if merge:
            output_path = kwargs.get('merge_output_path')
            if not output_path:
                raise ValueError("合并视频需要指定输出路径")

            merged = self.merge_videos(
                video_paths,
                output_path,
                remove_source=False,
                force_reprocess=force_reprocess
            )
            if merged:
                results['merged'] = merged

                if to_gif:
                    gif_path = self.convert_to_gif(
                        merged,
                        force_reprocess=force_reprocess,
                        **kwargs.get('gif_params', {})
                    )
                    if gif_path:
                        results['merged_gif'] = gif_path

        if to_gif and not merge:
            # 转换所有原始视频
            gif_dir = kwargs.get('gif_output_dir')
            if not gif_dir:
                raise ValueError("需要指定GIF输出目录")

            gifs = self.batch_convert_to_gif(
                video_paths,
                gif_dir,
                force_reprocess=force_reprocess,
                **kwargs.get('gif_params', {})
            )
            results['gifs'] = gifs

        return results
