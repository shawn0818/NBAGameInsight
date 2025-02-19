from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
import asyncio
import aiohttp

from nba.fetcher.video_fetcher import VideoFetcher
from nba.models.video_model import VideoAsset, ContextMeasure
from nba.parser.video_parser import VideoParser
from utils.gif_converter import GIFConverter, GIFConfig
from config.nba_config import NBAConfig
from utils.logger_handler import AppLogger


@dataclass
class VideoConfig:
    """视频输出配置"""
    format: str = 'gif'  # mp4 or gif
    quality: str = 'hd'  # sd or hd
    chunk_size: int = 8192
    max_retries: int = 3
    retry_delay: float = 1.0
    gif_config: Optional[GIFConfig] = None

    def __post_init__(self):
        if self.format not in ['mp4', 'gif']:
            raise ValueError("format must be either 'mp4' or 'gif'")
        if self.quality not in ['sd', 'hd']:
            raise ValueError("quality must be either 'sd' or 'hd'")

        if self.format == 'gif' and self.gif_config is None:
            self.gif_config = GIFConfig(
                max_retries=self.max_retries,
                retry_delay=self.retry_delay
            )

    def get_output_path(self, game_id: str, event_id: str) -> Path:
        """获取输出路径"""
        filename = f"gamevideo_{game_id}_{event_id}"
        output_dir = NBAConfig.PATHS.GIF_DIR if self.format == 'gif' else NBAConfig.PATHS.VIDEO_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"{filename}.{self.format}"


class AsyncVideoProcessor:
    """异步视频处理器"""

    def __init__(self, config: Optional[VideoConfig] = None):
        self.config = config or VideoConfig() # 使用传入的 config 或默认的 VideoConfig()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.session_context = aiohttp.ClientSession
        self.gif_converter = GIFConverter(config.gif_config) if config.format == 'gif' else None

    async def process_video(
            self,
            video_asset: VideoAsset,
            game_id: str
    ) -> Optional[Path]:
        """处理单个视频"""
        try:
            video_quality = video_asset.get_preferred_quality(self.config.quality)
            if not video_quality:
                self.logger.error(f"未找到指定质量的视频: {self.config.quality}")
                return None

            final_path = self.config.get_output_path(game_id, video_asset.event_id)
            if final_path.exists():
                return final_path

            temp_path = final_path.with_suffix('.tmp')
            try:
                if not await self.download_video(video_quality.url, temp_path):
                    return None

                if self.config.format == 'gif':
                    success = await self.gif_converter.convert_async(temp_path, final_path)
                    if not success:
                        return None
                else:
                    temp_path.replace(final_path)
                    success = True

                return final_path if success else None

            finally:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception as e:
                        self.logger.error(f"清理临时文件失败: {str(e)}")

        except Exception as e:
            self.logger.error(f"视频处理失败: {str(e)}", exc_info=True)
            return None

    async def download_video(
            self,
            url: str,
            output_path: Path
    ) -> bool:
        """
        异步下载视频

        Args:
            url (str): 视频URL
            output_path (Path): 输出路径

        Returns:
            bool: 下载是否成功
        """
        try:
            for retry in range(self.config.max_retries):
                try:
                    async with self.session_context() as session:
                        async with session.get(url) as response:
                            if not response.ok:
                                raise aiohttp.ClientError(f"HTTP错误: {response.status}")

                            with open(output_path, 'wb') as f:
                                async for chunk in response.content.iter_chunked(self.config.chunk_size):
                                    if chunk:
                                        f.write(chunk)

                            return True

                except asyncio.CancelledError:
                    self.logger.warning(f"下载任务被取消: {url}")
                    raise
                except Exception as e:
                    self.logger.warning(f"下载重试 {retry + 1}/{self.config.max_retries}: {e}")
                    if retry < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay)
                    continue

            self.logger.error(f"下载失败，已重试{self.config.max_retries}次")
            return False

        except Exception as e:
            self.logger.error(f"下载视频失败: {str(e)}")
            return False


class GameVideoService:
    """NBA比赛视频服务"""

    def __init__(self, video_config: Optional[VideoConfig] = None):
        self.config = video_config or VideoConfig()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        # 初始化视频获取器和解析器作为实例属性
        self.video_fetcher = VideoFetcher()
        self.video_parser = VideoParser()
        self.processor = AsyncVideoProcessor(config=self.config)

    def get_game_videos(
            self,
            game_id: str,
            player_id: Optional[int] = None,
            context_measure: ContextMeasure = ContextMeasure.FGM
    ) -> Dict[str, VideoAsset]:
        """获取比赛相关视频资源"""
        try:
            # 直接使用实例属性
            raw_data = self.video_fetcher.get_game_videos_raw(
                game_id=game_id,
                player_id=player_id,
                context_measure=context_measure
            )

            if not raw_data:
                self.logger.error("获取视频数据失败")
                return {}

            parsed_data = self.video_parser.parse_videos(raw_data)
            if not parsed_data:
                self.logger.error("解析视频数据失败")
                return {}

            return parsed_data.resultSets.get('video_assets', {})

        except Exception as e:
            self.logger.error(f"获取视频资源时出错: {e}")
            return {}

    async def _async_batch_process(
            self,
            videos: Dict[str, VideoAsset],
            game_id: str,
            timeout: float = 300.0
    ) -> Dict[str, Path]:
        """异步批量处理视频"""
        results: Dict[str, Path] = {}
        tasks: List[tuple[str, asyncio.Task]] = []

        try:
            self.logger.info(f"开始处理 {len(videos)} 个视频")

            # 创建所有视频处理任务
            for event_id, video in videos.items():
                task = asyncio.create_task(
                    self.processor.process_video(
                        video_asset=video,
                        game_id=game_id
                    )
                )
                tasks.append((event_id, task))

            # 处理所有任务
            async with asyncio.timeout(timeout):
                for event_id, task in tasks:
                    try:
                        result_path = await task
                        if result_path:
                            results[event_id] = result_path
                    except asyncio.CancelledError:
                        self.logger.warning(f"视频处理被取消 {event_id}")
                        raise
                    except Exception as e:
                        self.logger.error(f"处理视频出错 {event_id}: {str(e)}")

            return results

        except Exception as e:
            self.logger.error(f"批量处理视频失败: {str(e)}", exc_info=True)
            return results

    def batch_process_videos(
            self,
            videos: Dict[str, VideoAsset],
            game_id: str
    ) -> Dict[str, Path]:
        """批量处理视频的同步接口"""
        return asyncio.run(self._async_batch_process(videos, game_id))

    def close(self):
        """关闭服务并清理资源"""
        pass