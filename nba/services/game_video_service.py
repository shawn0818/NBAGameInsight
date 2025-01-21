import asyncio
from typing import Optional, Dict, Set
from pathlib import Path
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from nba.models.video_model import VideoAsset, ContextMeasure
from utils.video_downloader import VideoDownloader, VideoConverter
from nba.fetcher.video_fetcher import VideoFetcher
from nba.parser.video_parser import VideoParser
from config.nba_config import NBAConfig


class GameVideoService:
    """NBA比赛视频服务"""

    def __init__(self,
                 video_fetcher: Optional[VideoFetcher] = None,
                 video_parser: Optional[VideoParser] = None,
                 downloader: Optional[VideoDownloader] = None,
                 converter: Optional[VideoConverter] = None,
                 max_workers: int = 4):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.video_fetcher = video_fetcher or VideoFetcher()
        self.video_parser = video_parser or VideoParser()
        self.downloader = downloader or VideoDownloader()
        self.converter = converter or VideoConverter()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.temp_files: Set[Path] = set()

    async def get_game_videos(self, game_id: str,
                              context_measure: ContextMeasure = ContextMeasure.FGM,
                              player_id: Optional[int] = None,
                              team_id: Optional[int] = None) -> Dict[str, VideoAsset]:
        """获取比赛视频"""
        try:
            raw_video_data = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self.video_fetcher.get_game_videos_raw,
                game_id,
                context_measure,
                player_id,
                team_id
            )

            if not raw_video_data:
                self.logger.warning(f"未获取到视频数据: game_id={game_id}")
                return {}

            videos = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self.video_parser.parse_videos,
                raw_video_data
            )

            if not videos:
                return {}

            self.logger.info(f"成功获取 {len(videos.resultSets['video_assets'])} 个视频")
            return videos.resultSets['video_assets']

        except Exception as e:
            self.logger.error(f"获取视频失败: {e}", exc_info=True)
            return {}

    async def download_video(self,
                             video_asset: VideoAsset,
                             output_path: Path,
                             quality: str = 'hd',
                             to_gif: bool = False,
                             compress: bool = False) -> Optional[Path]:
        """下载并处理单个视频"""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            video_quality = video_asset.get_preferred_quality(quality)
            if not video_quality:
                raise ValueError(f"未找到 {quality} 质量的视频")

            # 下载视频
            success = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self.downloader.download,
                video_quality.url,
                output_path
            )

            if not success:
                raise Exception(f"下载视频失败: {video_quality.url}")

            result_path = output_path

            # 处理视频格式
            if to_gif:
                result_path = await self._convert_to_gif(output_path)
            elif compress:
                result_path = await self._compress_video(output_path)

            return result_path

        except Exception as e:
            self.logger.error(f"处理视频失败: {e}", exc_info=True)
            self._cleanup_temp_files()
            return None

    async def batch_download(self,
                             videos: Dict[str, VideoAsset],
                             output_dir: Optional[Path] = None,
                             quality: str = 'hd',
                             to_gif: bool = False,
                             compress: bool = False,
                             max_concurrent: int = 3) -> Dict[str, Path]:
        """批量下载视频"""
        output_dir = output_dir or NBAConfig.PATHS.VIDEO_DIR
        results = {}
        sem = asyncio.Semaphore(max_concurrent)

        async def download_task(event_id: str, video: VideoAsset):
            async with sem:
                try:
                    output_path = output_dir / f"{event_id}.mp4"
                    result_path = await self.download_video(
                        video_asset=video,
                        output_path=output_path,
                        quality=quality,
                        to_gif=to_gif,
                        compress=compress
                    )
                    if result_path:
                        results[event_id] = result_path
                except Exception as e:
                    self.logger.error(f"下载视频失败 {event_id}: {e}")

        tasks = [download_task(event_id, video) for event_id, video in videos.items()]
        await asyncio.gather(*tasks)
        return results

    async def _convert_to_gif(self, video_path: Path) -> Optional[Path]:
        """转换视频为GIF"""
        gif_path = video_path.with_suffix('.gif')
        success = await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.converter.to_gif,
            video_path,
            gif_path,
            12,  # fps
            960,  # scale
            True  # remove_source
        )
        return gif_path if success else None

    async def _compress_video(self, video_path: Path) -> Optional[Path]:
        """压缩视频"""
        compressed_path = video_path.with_name(f"{video_path.stem}_compressed{video_path.suffix}")
        success = await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.converter.compress_video,
            video_path,
            compressed_path,
            True  # remove_source
        )
        return compressed_path if success else None

    def _cleanup_temp_files(self):
        """清理临时文件"""
        for temp_file in self.temp_files:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception as e:
                    self.logger.error(f"清理临时文件失败 {temp_file}: {e}")
        self.temp_files.clear()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._cleanup_temp_files()
        self.executor.shutdown(wait=True)

    def close(self):
        self._cleanup_temp_files()
        self.executor.shutdown(wait=True)
        self.video_fetcher.__exit__(None, None, None)