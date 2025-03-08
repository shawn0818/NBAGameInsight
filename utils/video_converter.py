import os
import tempfile
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
    gif_fps: int = 12  # 提高帧率到 15fps，更流畅
    gif_scale: str = "960:-1"  # 保持宽度 1280，最佳清晰度
    gif_quality: int = 8  # 质量设置为 5，高清晰度


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

    def merge_videos(self,
                     video_files: List[Path],
                     output_path: Path,
                     remove_watermark: bool = True,
                     force_reprocess: bool = False) -> Optional[Path]:
        """合并多个视频文件，并可选去除水印

        Args:
            video_files: 视频文件路径列表
            output_path: 输出路径
            remove_watermark: 是否去除水印
            force_reprocess: 是否强制重新处理

        Returns:
            Optional[Path]: 合并后的视频路径，失败则返回None
        """
        if not video_files:
            self.logger.error("没有视频文件可供合并")
            return None

        # 检查输出文件是否已存在
        if output_path.exists() and not force_reprocess:
            self.logger.info(f"输出文件已存在: {output_path}")
            return output_path

        # 创建输出目录
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # 准备输入文件列表
            with tempfile.NamedTemporaryFile('w+t', suffix='.txt', delete=False) as f:
                input_list_path = f.name
                for video_file in video_files:
                    if video_file.exists():
                        f.write(f"file '{video_file.absolute()}'\n")
                    else:
                        self.logger.warning(f"文件不存在: {video_file}")

            # 先合并视频（不去水印）
            merged_temp_path = output_path.parent / f"temp_{output_path.name}"
            concat_cmd = [
                'ffmpeg',
                '-y',  # 覆盖现有文件
                '-f', 'concat',
                '-safe', '0',
                '-i', input_list_path,
                '-c', 'copy',
                str(merged_temp_path)
            ]

            # 执行合并命令
            self.logger.info(f"执行视频合并命令: {' '.join(concat_cmd)}")
            subprocess.run(concat_cmd, check=True)

            # 如果需要去水印，对合并后的视频进行处理
            if remove_watermark and merged_temp_path.exists():
                delogo_cmd = [
                    'ffmpeg',
                    '-y',
                    '-i', str(merged_temp_path),
                    '-vf', 'delogo=x=1030:y=5:w=230:h=40',
                    '-c:v', 'libx264',  # 使用H.264编码器
                    '-crf', '18',  # 高质量设置
                    '-preset', 'medium',  # 平衡处理时间和质量
                    '-c:a', 'copy',  # 保持音频不变
                    str(output_path)
                ]

                # 执行去水印命令
                self.logger.info(f"执行水印去除命令: {' '.join(delogo_cmd)}")
                subprocess.run(delogo_cmd, check=True)

                # 删除临时合并文件
                merged_temp_path.unlink()
            elif not remove_watermark and merged_temp_path.exists():
                # 如果不需要去水印，直接重命名合并文件
                merged_temp_path.rename(output_path)

            # 清理输入文件列表
            os.unlink(input_list_path)

            if output_path.exists():
                self.logger.info(f"视频处理成功: {output_path}")
                return output_path
            else:
                self.logger.error(f"视频处理后未找到输出文件: {output_path}")
                return None

        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFmpeg命令执行失败: {e}")
            return None
        except Exception as e:
            self.logger.error(f"视频处理失败: {e}")
            # 确保清理临时文件
            temp_path = output_path.parent / f"temp_{output_path.name}"
            if temp_path.exists():
                temp_path.unlink()
            return None

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
                remove_watermark=True,
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
