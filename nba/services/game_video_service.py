from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
import asyncio
import aiohttp

from nba.fetcher.video_fetcher import VideoFetcher
from nba.models.video_model import VideoAsset, ContextMeasure
from nba.parser.video_parser import VideoParser
from config.nba_config import NBAConfig
from utils.logger_handler import AppLogger


@dataclass
class VideoConfig:
    """视频配置"""
    quality: str = 'md'  # sd, md, hd
    chunk_size: int = 8192
    max_retries: int = 3
    retry_delay: float = 1.0
    output_dir: Path = NBAConfig.PATHS.VIDEO_DIR

    def __post_init__(self):
        if self.quality not in ['sd', 'md', 'hd']:
            raise ValueError("quality must be one of: sd, md, hd")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_output_path(self, game_id: str, event_id: str) -> Path:
        """获取输出路径"""
        filename = f"video_{game_id}_{event_id}.mp4"
        return self.output_dir / filename


class AsyncVideoDownloader:
    """异步视频下载器"""

    def __init__(self, config: VideoConfig):
        self.config = config
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.session_context = aiohttp.ClientSession

    async def download_video(
            self,
            video_asset: VideoAsset,
            game_id: str
    ) -> Optional[Path]:
        """下载单个视频

        Args:
            video_asset: 视频资源
            game_id: 比赛ID

        Returns:
            Optional[Path]: 下载成功则返回文件路径，否则返回None
        """
        try:
            # 获取指定质量的视频
            video_quality = video_asset.get_preferred_quality(self.config.quality)
            if not video_quality:
                self.logger.error(f"未找到指定质量的视频: {self.config.quality}")
                return None

            # 确定输出路径
            output_path = self.config.get_output_path(game_id, video_asset.event_id)
            if output_path.exists():
                return output_path

            # 下载视频
            for retry in range(self.config.max_retries):
                try:
                    async with self.session_context() as session:
                        async with session.get(video_quality.url) as response:
                            if not response.ok:
                                raise aiohttp.ClientError(f"HTTP错误: {response.status}")

                            with open(output_path, 'wb') as f:
                                async for chunk in response.content.iter_chunked(self.config.chunk_size):
                                    if chunk:
                                        f.write(chunk)
                            return output_path

                except asyncio.CancelledError:
                    self.logger.warning(f"下载任务被取消: {video_quality.url}")
                    raise
                except Exception as e:
                    self.logger.warning(f"下载重试 {retry + 1}/{self.config.max_retries}: {e}")
                    if retry < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay)
                    continue

            self.logger.error(f"下载失败，已重试{self.config.max_retries}次")
            return None

        except Exception as e:
            self.logger.error(f"视频下载失败: {str(e)}", exc_info=True)
            return None


class GameVideoService:
    """NBA比赛视频服务"""

    def __init__(self, video_config: Optional[VideoConfig] = None):
        self.config = video_config or VideoConfig()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.video_fetcher = VideoFetcher()
        self.video_parser = VideoParser()
        self.downloader = AsyncVideoDownloader(config=self.config)  # 使用 AsyncVideoProcessor 进行下载

    def get_game_videos(
            self,
            game_id: Optional[str] = None,
            player_id: Optional[int] = None,
            team_id: Optional[int] = None,
            context_measure: Optional[ContextMeasure] = None
    ) -> Dict[str, VideoAsset]:
        """
        获取 NBA 视频资源元数据。

        可以根据不同的参数组合，获取不同类型的视频集锦。
        具体参数组合及其含义请参考 VideoRequestParams 的文档。

        Args:
            game_id (Optional[str], optional): 比赛 ID。默认为 None。
            player_id (Optional[int], optional): 球员 ID。默认为 None。
            team_id (Optional[int], optional): 球队 ID。默认为 None。
            context_measure (Optional[ContextMeasure], optional): 上下文度量 (视频类型)。默认为 None。

        Returns:
            Dict[str, VideoAsset]: 视频资源字典，key 为 event_id, value 为 VideoAsset。
                如果获取或解析失败，则返回空字典。
        """
        try:
            # 调用新的 get_game_videos_raw 方法获取原始数据
            raw_data = self.video_fetcher.get_game_video_urls(
                game_id=game_id,
                player_id=player_id,
                team_id=team_id,
                context_measure=context_measure
            )

            if not raw_data:
                error_msg = f"获取视频数据失败，参数: game_id={game_id}, player_id={player_id}, team_id={team_id}, context_measure={context_measure}"
                self.logger.error(error_msg)
                return {}

            parsed_data = self.video_parser.parse_videos(raw_data)
            if not parsed_data:
                error_msg = f"解析视频数据失败，参数: game_id={game_id}"
                self.logger.error(error_msg)
                return {}

            videos = parsed_data.resultSets.get('video_assets', {})
            log_msg = f"获取视频元数据成功，视频数量: {len(videos)}"
            self.logger.info(log_msg)
            return videos

        except Exception as e:
            error_msg = f"获取视频资源时出错，{e}"
            self.logger.error(error_msg, exc_info=True)
            return {}

    async def download_videos(
            self,
            videos: Dict[str, VideoAsset],
            game_id: str,
            timeout: float = 300.0
    ) -> Dict[str, Path]:
        """异步下载多个视频

        Args:
            videos: 要下载的视频资源字典
            game_id: 比赛ID
            timeout: 下载超时时间（秒）

        Returns:
            Dict[str, Path]: 下载成功的视频路径字典
        """
        results: Dict[str, Path] = {}
        tasks: List[tuple[str, asyncio.Task]] = []

        try:
            self.logger.info(f"开始下载 {len(videos)} 个视频")

            # 创建下载任务
            for event_id, video in videos.items():
                task = asyncio.create_task(
                    self.downloader.download_video(video, game_id)
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
                        self.logger.warning(f"视频下载被取消 {event_id}")
                        raise
                    except Exception as e:
                        self.logger.error(f"下载视频出错 {event_id}: {str(e)}")

            return results

        except Exception as e:
            self.logger.error(f"批量下载视频失败: {str(e)}", exc_info=True)
            return results

    def batch_download_videos(
            self,
            videos: Dict[str, VideoAsset],
            game_id: str
    ) -> Dict[str, Path]:
        """同步下载多个视频的便捷方法"""
        return asyncio.run(self.download_videos(videos, game_id))

    def close(self):
        """关闭服务并清理资源"""
        self.video_fetcher.clear_cache()