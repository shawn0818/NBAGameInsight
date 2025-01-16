from typing import Optional, Dict
from pathlib import Path
import logging

from nba.models.video_model import VideoAsset, ContextMeasure, VideoRequestParams
from utils.video_downloader import VideoDownloader, VideoConverter
from nba.parser.video_query_parser import NBAVideoProcessor
from config.nba_config import NBAConfig


class GameVideoService:
    """NBA比赛视频服务
    
    提供比赛视频相关的功能，包括：
    1. 视频资源获取
    2. 视频下载和处理
    3. 格式转换（MP4到GIF）
    4. 视频压缩
    
    支持批量处理和自定义输出格式。
    """

    def __init__(self, video_processor: Optional[NBAVideoProcessor] = None,
                 downloader: Optional[VideoDownloader] = None,
                 converter: Optional[VideoConverter] = None):
        """初始化视频服务
        
        Args:
            video_processor: 视频处理器实例
            downloader: 视频下载器实例
            converter: 视频转换器实例
        """
        self.logger = logging.getLogger("nba.services.game_video_service")
        self.video_processor = video_processor or NBAVideoProcessor()
        self.downloader = downloader or VideoDownloader()
        self.converter = converter or VideoConverter()

    def get_game_videos(
        self,
        game_id: str,
        context_measure: ContextMeasure = ContextMeasure.FGM,
        player_id: Optional[int] = None,
        team_id: Optional[int] = None
    ) -> Dict[str, VideoAsset]:
        """
        获取比赛视频

        Args:
            game_id (str): 比赛ID
            context_measure (ContextMeasure): 上下文度量类型
            player_id (Optional[int]): 球员ID
            team_id (Optional[int]): 球队ID

        Returns:
            Dict[str, VideoAsset]: 以event_id为key的视频资产字典
        """
        try:
            # 构建查询参数
            query = VideoRequestParams(
                game_id=game_id,
                player_id=str(player_id) if player_id else None,
                team_id=str(team_id) if team_id else None,
                context_measure=context_measure
            )

            self.logger.debug(f"查询参数: {query}")

            # 获取视频数据
            videos = self.video_processor.get_videos_by_query(query)
            self.logger.info(f"获取到 {len(videos)} 个视频")

            return videos

        except Exception as e:
            self.logger.error(f"获取视频时出错: {e}", exc_info=True)
            return {}

    def download_video(
        self,
        video_asset: VideoAsset,
        output_path: Path,
        quality: str = 'hd',
        to_gif: bool = False,
        compress: bool = False
    ) -> Optional[Path]:
        """
        下载并处理单个视频

        Args:
            video_asset (VideoAsset): 视频资产
            output_path (Path): 输出路径
            quality (str): 视频质量 ('sd' 或 'hd')
            to_gif (bool): 是否转换为GIF
            compress (bool): 是否压缩视频

        Returns:
            Optional[Path]: 处理后的视频路径或None
        """
        try:
            # 确保输出目录存在
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 获取指定质量的视频URL
            video_quality = video_asset.qualities.get(quality)
            if not video_quality:
                self.logger.error(f"找不到 {quality} 质量的视频")
                return None

            # 下载视频
            if not self.downloader.download(video_quality.url, output_path):
                self.logger.error(f"下载视频失败: {video_quality.url}")
                return None

            # 处理视频格式
            if to_gif:
                return self._convert_to_gif(output_path)

            if compress:
                return self._compress_video(output_path)

            return output_path

        except Exception as e:
            self.logger.error(f"处理视频时出错: {e}")
            if output_path.exists():
                output_path.unlink()
            return None

    def batch_download(
        self,
        videos: Dict[str, VideoAsset],
        output_dir: Optional[Path] = None,
        quality: str = 'hd',
        to_gif: bool = False,
        compress: bool = False
    ) -> Dict[str, Path]:
        """
        批量下载视频

        Args:
            videos (Dict[str, VideoAsset]): 视频资产字典
            output_dir (Optional[Path]): 输出目录
            quality (str): 视频质量 ('sd' 或 'hd')
            to_gif (bool): 是否转换为GIF
            compress (bool): 是否压缩视频

        Returns:
            Dict[str, Path]: 下载结果字典 {event_id: Path}
        """
        output_dir = output_dir or NBAConfig.PATHS.VIDEO_DIR
        results = {}

        for event_id, video in videos.items():
            try:
                self.logger.info(f"处理视频 {event_id}")
                output_path = output_dir / f"{event_id}.mp4"

                result_path = self.download_video(
                    video_asset=video,
                    output_path=output_path,
                    quality=quality,
                    to_gif=to_gif,
                    compress=compress
                )

                if result_path:
                    results[event_id] = result_path
                    self.logger.info(f"成功处理视频 {event_id}: {result_path}")

            except Exception as e:
                self.logger.error(f"处理视频 {event_id} 时出错: {e}", exc_info=True)
                continue

        return results

    def _convert_to_gif(self, video_path: Path) -> Optional[Path]:
        """将视频转换为GIF"""
        gif_path = video_path.with_suffix('.gif')
        if self.converter.to_gif(
            video_path=video_path,
            output_path=gif_path,
            fps=12,
            scale=960,
            remove_source=True
        ):
            return gif_path
        return None

    def _compress_video(self, video_path: Path) -> Optional[Path]:
        """压缩视频"""
        compressed_path = video_path.with_name(f"{video_path.stem}_compressed{video_path.suffix}")
        if self.converter.compress_video(
            video_path=video_path,
            output_path=compressed_path,
            remove_source=True
        ):
            return compressed_path
        return None
