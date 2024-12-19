from typing import Optional, Dict, Union
from pathlib import Path
import logging

from nba.models.video_model import VideoResponse, VideoAsset, ContextMeasure, VideoRequestParams
from utils.video_downloader import VideoDownloader, VideoConverter
from nba.parser.video_query_parser import NBAVideoProcessor
from config.nba_config import NBAConfig

class GameVideoService:
    """比赛视频下载服务"""
    
    def __init__(
        self,
        video_processor: Optional[NBAVideoProcessor] = None
    ):
        """
        初始化下载服务
        
        Args:
            video_processor: 视频处理器，负责获取视频数据
        """
        self.logger = logging.getLogger(__name__)
        self.video_processor = video_processor or NBAVideoProcessor()
        self.downloader = VideoDownloader()
        self.converter = VideoConverter()
        
    async def get_game_video_response(
        self,
        game_id: str,
        player_id: Optional[int] = None,
        team_id: Optional[int] = None,
        context_measure: Optional[ContextMeasure] = None,
    ) -> Optional[VideoResponse]:
        """
        获取比赛视频数据
        
        Args:
            game_id: 比赛ID
            player_id: 球员ID（可选）
            team_id: 球队ID（可选）
            context_measure: 动作类型筛选（可选）
            
        Returns:
            VideoResponse: 视频响应数据
        """
        try:
            # 构建查询参数
            query = VideoRequestParams(
                game_id=game_id,
                player_id=str(player_id) if player_id else None,
                team_id=str(team_id) if team_id else None,
                context_measure=context_measure or ContextMeasure.FGM
            )
            
            # 获取视频数据
            return await self.video_processor.get_videos_by_query(query)
        except Exception as e:
            self.logger.error(f"获取视频数据失败: {e}")
            return None
        
    def get_player_videos(
        self,
        video_response: VideoResponse,
        player_id: int,
        action_type: Optional[str] = None,
        period: Optional[int] = None
    ) -> Dict[str, VideoAsset]:
        """
        获取指定球员的视频片段
        
        Args:
            video_response: 视频响应数据
            player_id: 球员ID
            action_type: 动作类型（如 FG3M, AST 等）
            period: 比赛节次
            
        Returns:
            Dict[str, VideoAsset]: 过滤后的视频资产字典
        """
        filtered_videos = {}
        
        for item in video_response.resultSets.playlist:
            # 筛选球员
            if item.personId != player_id:
                continue
                
            # 筛选动作类型
            if action_type and item.event_type != action_type:
                continue
                
            # 筛选节次
            if period and item.p != period:
                continue
                
            # 找到对应的视频URL
            video_urls = [v for v in video_response.resultSets.Meta.videoUrls 
                         if any(str(item.ei) in url for url in v.urls.values())]
            
            if video_urls:
                video_url = video_urls[0]
                filtered_videos[str(item.ei)] = VideoAsset(
                    uuid=video_url.uuid,
                    duration=video_url.duration,
                    urls=video_url.urls,
                    thumbnails=video_url.thumbnails,
                    subtitles=video_url.subtitles,
                    event_info={
                        'event_id': item.ei,
                        'description': item.dsc,
                        'period': item.p,
                        'score': {
                            'before': {'home': item.hpb, 'away': item.vpb},
                            'after': {'home': item.hpa, 'away': item.vpa}
                        }
                    }
                )
                
        return filtered_videos

    def download_video(
        self,
        video_url: str,
        output_path: Path,
        to_gif: bool = False,
        compress: bool = False
    ) -> Optional[Path]:
        """
        下载单个视频
        
        Args:
            video_url: 视频URL
            output_path: 输出路径
            to_gif: 是否转换为GIF
            compress: 是否压缩视频
            
        Returns:
            Path: 处理后的视频路径，失败返回None
        """
        try:
            # 1. 确保输出目录存在
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 2. 下载视频
            if not self.downloader.download(video_url, output_path):
                self.logger.error(f"下载视频失败: {video_url}")
                return None
                
            # 3. 处理视频格式
            if to_gif:
                gif_path = output_path.with_suffix('.gif')
                if not self.converter.to_gif(
                    video_path=output_path,
                    output_path=gif_path,
                    fps=12,
                    scale=960,
                    remove_source=True
                ):
                    return None
                return gif_path
                
            elif compress:
                compressed_path = output_path.with_name(f"{output_path.stem}_compressed{output_path.suffix}")
                if not self.converter.compress_video(
                    video_path=output_path,
                    output_path=compressed_path,
                    remove_source=True
                ):
                    return None
                return compressed_path
                
            return output_path
            
        except Exception as e:
            self.logger.error(f"处理视频时出错: {e}")
            if output_path.exists():
                output_path.unlink()  # 清理失败的文件
            return None

    def batch_download_videos(
        self,
        video_assets: Dict[str, VideoAsset],
        output_dir: Optional[Path] = None,
        to_gif: bool = False,
        quality: str = 'hd'
    ) -> Dict[str, Union[Path, str]]:
        """
        批量下载视频
        
        Args:
            video_assets: 视频资产字典
            output_dir: 输出目录，默认使用配置的视频目录
            to_gif: 是否转换为GIF
            quality: 视频质量('sd', 'hd')
            
        Returns:
            Dict[str, Path]: 下载成功的视频路径字典
        """
        output_dir = output_dir or NBAConfig.PATHS.VIDEO_DIR
        results = {}
        
        for event_id, asset in video_assets.items():
            try:
                # 获取视频URL
                video_url = asset.urls.get(quality)
                if not video_url:
                    self.logger.warning(f"找不到{quality}质量的视频: {event_id}")
                    continue
                
                # 构建输出路径
                output_path = output_dir / f"{event_id}.mp4"
                
                # 下载并处理视频
                result_path = self.download_video(
                    video_url=video_url,
                    output_path=output_path,
                    to_gif=to_gif
                )
                
                if result_path:
                    results[event_id] = result_path
                    
            except Exception as e:
                self.logger.error(f"处理视频 {event_id} 时出错: {e}")
                continue
                
        return results