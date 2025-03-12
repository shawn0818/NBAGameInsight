from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass
import time
import threading
import random
from nba.fetcher.video_fetcher import VideoFetcher
from nba.models.video_model import VideoAsset, ContextMeasure
from nba.parser.video_parser import VideoParser
from config.nba_config import NBAConfig
from utils.logger_handler import AppLogger
from utils.http_handler import HTTPRequestManager


@dataclass
class VideoConfig:
    """视频配置"""
    quality: str = 'hd'  # sd, md, hd
    chunk_size: int = 8192
    max_retries: int = 3
    retry_delay: float = 1.0
    min_download_delay: float = 2.0  # 最小下载延迟(秒)
    max_download_delay: float = 5.0  # 最大下载延迟(秒)
    concurrent_downloads: int = 3  # 同时进行的下载任务数量
    output_dir: Path = NBAConfig.PATHS.VIDEO_DIR
    request_timeout: int = 30  # 请求超时时间(秒)

    def __post_init__(self):
        if self.quality not in ['sd', 'md', 'hd']:
            raise ValueError("quality must be one of: sd, md, hd")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_random_delay(self) -> float:
        """获取随机延迟时间"""
        return random.uniform(self.min_download_delay, self.max_download_delay)

    def get_output_path(self, game_id: str, video_asset: VideoAsset, player_id: Optional[int] = None,
                        context_measure: Optional[str] = None) -> Path:

        # 从 VideoAsset 对象中获取 event_id
        event_id = video_asset.event_id

        # 文件名格式: event_xxx_game_xxxx.mp4
        filename = f"event_{event_id}_game_{game_id}"

        # 如果有player_id，添加到文件名
        if player_id is not None:
            filename += f"_player{player_id}"

        # 如果有context_measure，添加到文件名
        if context_measure is not None:
            filename += f"_{context_measure}"

        # 添加文件扩展名
        filename += ".mp4"

        return self.output_dir / filename


class VideoDownloader:
    """使用HTTPRequestManager的视频下载器"""

    def __init__(self, config: VideoConfig):
        self.config = config
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self._semaphore = threading.Semaphore(config.concurrent_downloads)  # 控制并发下载数量

        # 初始化HTTP请求管理器
        self.http_manager = HTTPRequestManager(
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': '*/*',  # 接受任何类型的响应
                'Accept-Encoding': 'gzip, deflate, br'
            },
            timeout=config.request_timeout
        )
        # 修改请求间隔，视频下载可能需要更长间隔
        self.http_manager.min_request_interval = config.min_download_delay

    def download_video(
            self,
            video_asset: VideoAsset,
            game_id: str,
            player_id: Optional[int] = None,
            context_measure: Optional[str] = None,
            force_reprocess: bool = False
    ) -> Optional[Path]:
        """下载单个视频

        Args:
            video_asset: 视频资源
            game_id: 比赛ID
            player_id: 可选的球员ID
            context_measure: 可选的上下文度量(视频类型)
            force_reprocess: 是否强制重新处理

        Returns:
            Optional[Path]: 下载成功则返回文件路径，否则返回None
        """
        try:
            # 获取指定质量的视频
            video_quality = video_asset.get_preferred_quality(self.config.quality)
            if not video_quality:
                self.logger.error(f"未找到指定质量的视频: {self.config.quality}")
                return None

            # 确定输出路径，传入可选参数
            output_path = self.config.get_output_path(game_id, video_asset, player_id, context_measure)

            # 增量处理: 检查文件是否已存在且有效，除非强制重新处理
            if not force_reprocess and output_path.exists():
                if output_path.stat().st_size > 1024 * 10:  # 至少10KB
                    self.logger.info(f"视频文件已存在，跳过下载: {output_path}")
                    return output_path
                else:
                    # 文件过小，可能损坏，删除并重新下载
                    self.logger.warning(f"文件过小，可能已损坏，将重新下载: {output_path}")
                    output_path.unlink()

            # 使用信号量控制并发数量
            with self._semaphore:
                return self._download_to_file(video_quality.url, output_path)

        except Exception as e:
            self.logger.error(f"视频下载失败: {str(e)}", exc_info=True)
            return None

    def _download_to_file(self, url: str, output_path: Path) -> Optional[Path]:
        """使用HTTPRequestManager下载文件到本地

        Args:
            url: 视频URL
            output_path: 输出路径

        Returns:
            Optional[Path]: 下载成功则返回文件路径，否则返回None
        """
        try:
            # 确保输出目录存在
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 使用自定义的session进行流式请求
            with self.http_manager.session.get(url, stream=True, timeout=self.config.request_timeout) as response:
                if not response.ok:
                    self.logger.error(f"HTTP错误: {response.status_code}, URL: {url}")
                    return None

                # 获取内容大小（如果服务器提供）
                total_size = int(response.headers.get('content-length', 0))

                # 实现分块下载
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=self.config.chunk_size):
                        if chunk:
                            f.write(chunk)

                # 验证下载文件
                if output_path.exists() and output_path.stat().st_size > 0:
                    if total_size > 0 and abs(output_path.stat().st_size - total_size) > 100:
                        # 文件大小不符合预期，可能下载不完整
                        self.logger.warning(
                            f"文件大小不符预期: {output_path.stat().st_size} bytes vs 预期 {total_size} bytes")

                self.logger.info(f"视频下载成功: {output_path}")
                return output_path

        except Exception as e:
            self.logger.error(f"下载视频文件失败: {str(e)}", exc_info=True)
            return None

    def close(self):
        """关闭下载器并释放资源"""
        if hasattr(self, 'http_manager'):
            self.http_manager.close()


class GameVideoService:
    """NBA比赛视频服务"""

    def __init__(self, video_config: Optional[VideoConfig] = None):
        self.config = video_config or VideoConfig()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.video_fetcher = VideoFetcher()
        self.video_parser = VideoParser()
        self.downloader = VideoDownloader(config=self.config)

    def get_game_videos(self, game_id: str, player_id: Optional[int] = None,
                        team_id: Optional[int] = None, context_measure: Optional[ContextMeasure] = None,
                        force_refresh: bool = True) -> Dict[str, VideoAsset]:
        """获取比赛视频资源"""
        try:
            # 1. 使用fetcher获取原始数据
            raw_data = self.video_fetcher.get_game_video_urls(
                game_id=game_id,
                player_id=player_id,
                team_id=team_id,
                context_measure=context_measure,
                force_refresh=force_refresh
            )

            if not raw_data:
                self.logger.warning(f"未获取到原始视频数据")
                return {}

            # 2. 使用parser解析数据
            parser = VideoParser()
            response = parser.parse_videos(raw_data, game_id)

            if not response:
                self.logger.error(f"解析视频数据失败")
                return {}

            # 3. 获取解析后的视频资产
            videos = response.get_videos()

            self.logger.info(f"获取视频元数据成功，视频数量: {len(videos)}")
            return videos

        except Exception as e:
            self.logger.error(f"获取比赛视频失败: {str(e)}")
            return {}

    def download_videos(
            self,
            videos: Dict[str, VideoAsset],
            game_id: str,
            player_id: Optional[int] = None,
            context_measure: Optional[str] = None,
            timeout: float = 300.0,
            force_reprocess: bool = False
    ) -> Dict[str, Path]:
        """同步下载多个视频"""
        results: Dict[str, Path] = {}
        start_time = time.time()

        try:
            self.logger.info(f"开始下载 {len(videos)} 个视频")

            # 处理每个视频
            for event_id, video in videos.items():
                try:
                    # 检查是否超时
                    if time.time() - start_time > timeout:
                        self.logger.warning(f"下载超时，已下载 {len(results)}/{len(videos)}")
                        break

                    # 添加随机延迟，避免过快请求服务器
                    if results:  # 如果已经下载了至少一个视频，则等待随机时间
                        random_delay = self.config.get_random_delay()
                        self.logger.info(f"等待 {random_delay:.2f} 秒后开始下载下一个视频")
                        time.sleep(random_delay)

                    # 传递player_id和context_measure参数
                    result_path = self.downloader.download_video(
                        video, game_id, player_id, context_measure,
                        force_reprocess=force_reprocess
                    )
                    if result_path:
                        results[event_id] = result_path
                        self.logger.info(f"视频 {event_id} 下载成功: {result_path}")
                    else:
                        self.logger.warning(f"视频 {event_id} 下载失败")

                except Exception as e:
                    self.logger.error(f"下载视频出错 {event_id}: {str(e)}")

            return results

        except Exception as e:
            self.logger.error(f"批量下载视频失败: {str(e)}", exc_info=True)
            return results

    def batch_download_videos(
            self,
            videos: Dict[str, VideoAsset],
            game_id: str,
            player_id: Optional[int] = None,
            team_id: Optional[int] = None,  # 添加team_id参数保持API一致性
            context_measure: Optional[str] = None,
            max_videos: Optional[int] = None,
            force_reprocess: bool = False
    ) -> Dict[str, Path]:
        """批量下载视频（支持最大数量限制）

        Args:
            videos: 视频资源字典
            game_id: 比赛ID
            player_id: 球员ID (可选)
            team_id: 球队ID (可选) - 添加此参数保持API一致性
            context_measure: 上下文指标 (可选)
            max_videos: 最大下载视频数量 (可选)
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Path]: 视频路径字典
        """
        # 创建有序的视频列表 (按事件ID排序)
        sorted_videos = sorted([(event_id, video) for event_id, video in videos.items()])

        # 如果有最大下载限制，裁剪列表
        if max_videos and max_videos < len(sorted_videos):
            sorted_videos = sorted_videos[:max_videos]
            self.logger.info(f"将下载数量限制为前 {max_videos} 个视频")

        # 创建下载子集
        limited_videos = {event_id: video for event_id, video in sorted_videos}

        # 调用标准下载方法
        return self.download_videos(
            limited_videos,
            game_id,
            player_id,
            context_measure,
            timeout=self.config.request_timeout * len(limited_videos),  # 根据视频数量调整总超时
            force_reprocess=force_reprocess
        )

    def close(self):
        """关闭服务并清理资源"""
        try:
            if hasattr(self, 'downloader'):
                self.downloader.close()

            if hasattr(self, 'video_fetcher'):
                self.video_fetcher.clear_cache()

            self.logger.info("视频服务资源已清理")
        except Exception as e:
            self.logger.error(f"清理资源失败: {str(e)}", exc_info=True)