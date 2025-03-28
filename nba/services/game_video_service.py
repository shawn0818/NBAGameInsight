from pathlib import Path
import time
import threading
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass

from nba.fetcher.video_fetcher import VideoFetcher
from nba.models.video_model import VideoAsset, ContextMeasure
from nba.parser.video_parser import VideoParser
from config import NBAConfig
from utils.logger_handler import AppLogger
from utils.http_handler import HTTPRequestManager
from utils.video_converter import VideoProcessor, VideoProcessConfig


@dataclass
class VideoConfig:
    """视频配置"""
    quality: str = 'hd'  # sd, md, hd
    chunk_size: int = 8192
    max_retries: int = 3
    retry_delay: float = 1.0
    # 保留这两个参数用于配置HTTPRequestManager
    min_download_delay: float = 2.0  # HTTP请求最小延迟(秒)
    max_download_delay: float = 5.0  # HTTP请求最大延迟(秒)
    concurrent_downloads: int = 3  # 同时进行的下载任务数量
    output_dir: Path = NBAConfig.PATHS.VIDEO_DIR
    request_timeout: int = 30  # 请求超时时间(秒)

    # 新增，用于高级业务功能
    team_video_dir: Path = None  # 球队视频目录
    player_video_dir: Path = None  # 球员视频目录
    gif_dir: Path = None  # GIF目录
    base_output_dir: Path = NBAConfig.PATHS.STORAGE_DIR  # 基础输出目录

    def __post_init__(self):
        if self.quality not in ['sd', 'md', 'hd']:
            raise ValueError("quality must be one of: sd, md, hd")

        # 确保基础目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 设置子目录
        if self.base_output_dir:
            if not self.team_video_dir:
                self.team_video_dir = self.base_output_dir / "videos" / "team_videos"
            if not self.player_video_dir:
                self.player_video_dir = self.base_output_dir / "videos" / "player_videos"
            if not self.gif_dir:
                self.gif_dir = self.base_output_dir / "gifs"

            # 确保子目录存在
            self.team_video_dir.mkdir(parents=True, exist_ok=True)
            self.player_video_dir.mkdir(parents=True, exist_ok=True)
            self.gif_dir.mkdir(parents=True, exist_ok=True)

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

    def get_team_video_dir(self, team_id: int, game_id: str) -> Path:
        """获取球队视频目录"""
        team_dir = self.team_video_dir / f"team_{team_id}_{game_id}"
        team_dir.mkdir(parents=True, exist_ok=True)
        return team_dir

    def get_player_video_dir(self, player_id: int, game_id: str) -> Path:
        """获取球员视频目录"""
        player_dir = self.player_video_dir / f"player_{player_id}_{game_id}"
        player_dir.mkdir(parents=True, exist_ok=True)
        return player_dir

    def get_player_gif_dir(self, player_id: int, game_id: str) -> Path:
        """获取球员GIF目录"""
        gif_dir = self.gif_dir / f"player_{player_id}_{game_id}_rounds"
        gif_dir.mkdir(parents=True, exist_ok=True)
        return gif_dir


class VideoDownloader:
    """使用HTTPRequestManager的视频下载器"""

    def __init__(self, config: VideoConfig):
        self.config = config
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self._semaphore = threading.Semaphore(config.concurrent_downloads)  # 控制并发下载数量

        # 初始化HTTP请求管理器，适配新的速率限制功能
        self.http_manager = HTTPRequestManager(
            headers={
                "Accept": "*/*",
                "Accept-Encoding": "identity;q=1, *;q=0",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "no-cache",
                "DNT": "1",
                "Host": "videos.nba.com",
                "Pragma": "no-cache",
                "Sec-Ch-Ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            },
            timeout=config.request_timeout
        )

        # 配置HTTP管理器的延迟参数，使用视频配置中的设置
        self.http_manager.min_request_interval = config.min_download_delay
        self.http_manager._min_delay = config.min_download_delay
        self.http_manager._max_delay = config.max_download_delay

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
    """NBA比赛视频服务 - 增强版，整合业务逻辑"""

    def __init__(self, video_config: Optional[VideoConfig] = None, video_processor: Optional[VideoProcessor] = None):
        self.config = video_config or VideoConfig()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.video_fetcher = VideoFetcher()  # 使用 VideoFetcher
        self.video_parser = VideoParser()  # 保留 VideoParser 用于解析
        self.downloader = VideoDownloader(config=self.config)
        # 视频处理器 (由外部注入或内部创建)
        self.video_processor = video_processor or VideoProcessor(VideoProcessConfig())

    def get_game_videos(self, game_id: str, player_id: Optional[int] = None,
                        team_id: Optional[int] = None, context_measure: Optional[ContextMeasure] = None,
                        force_refresh: bool = True) -> Dict[str, VideoAsset]:
        """获取比赛视频资源"""
        try:
            # 1. 使用 VideoFetcher 获取原始数据
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

            # 2. 使用 VideoParser 解析数据
            response = self.video_parser.parse_videos(raw_data, game_id)

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

    # ==== 从NBAService下放的业务方法 ====

    def get_team_highlights(self,
                            team_id: int,
                            game_id: str,
                            merge: bool = True,
                            output_dir: Optional[Path] = None,
                            force_reprocess: bool = False) -> Dict[str, Path]:
        """获取球队集锦视频

        下载并处理指定球队的比赛集锦。默认会合并视频、去除水印并删除原始短视频。

        Args:
            team_id: 球队ID
            game_id: 比赛ID
            merge: 是否合并视频
            output_dir: 输出目录，不提供则创建规范化目录
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Path]: 视频路径字典
        """
        try:
            # 创建球队特定的视频目录
            if not output_dir:
                # 使用更灵活的路径配置
                team_video_dir = self.config.get_team_video_dir(team_id, game_id)
                output_dir = team_video_dir

            # 获取视频资产
            videos = self.get_game_videos(
                game_id=game_id,
                team_id=team_id,
                context_measure=ContextMeasure.FGM
            )
            if not videos:
                self.logger.error(f"未找到球队ID={team_id}的集锦视频")
                return {}

            # 下载视频
            videos_dict = self._download_videos(
                videos=videos,
                game_id=game_id,
                team_id=team_id,
                force_reprocess=force_reprocess
            )

            if not videos_dict:
                self.logger.error("视频下载失败")
                return {}

            if not merge:
                return videos_dict

            # 合并视频
            output_filename = f"team_{team_id}_{game_id}.mp4"
            output_path = output_dir / output_filename

            merged_video = self._merge_videos(
                video_files=list(videos_dict.values()),
                output_path=output_path,
                remove_watermark=True,
                force_reprocess=force_reprocess
            )

            if merged_video:
                return {"merged": merged_video}
            else:
                return videos_dict

        except Exception as e:
            self.logger.error(f"获取球队集锦失败: {str(e)}", exc_info=True)
            return {}

    def get_player_highlights(self,
                              player_id: int,
                              game_id: str,
                              context_measures: Optional[Set[ContextMeasure]] = None,
                              output_format: str = "both",  # "video", "gif", "both"
                              merge: bool = True,
                              output_dir: Optional[Path] = None,
                              keep_originals: bool = True,
                              request_delay: float = 1.0,
                              force_reprocess: bool = False) -> Dict[str, Any]:
        """获取球员集锦视频和GIF

        下载并处理指定球员的比赛集锦。默认会同时生成视频和GIF，并保留原始短视频。

        Args:
            player_id: 球员ID
            game_id: 比赛ID
            context_measures: 上下文度量集合，如{FGM, AST}
            output_format: 输出格式，可选 "video"(仅视频), "gif"(仅GIF), "both"(视频和GIF)
            merge: 是否合并视频
            output_dir: 输出目录，不提供则创建规范化目录
            keep_originals: 是否保留原始短视频
            request_delay: 请求间隔时间(秒)
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Any]: 处理结果路径字典
        """
        try:
            # 创建球员特定的视频目录
            if not output_dir:
                player_video_dir = self.config.get_player_video_dir(player_id, game_id)
                output_dir = player_video_dir

            # 确定要获取的视频类型
            if context_measures is None:
                context_measures = {
                    ContextMeasure.FGM,
                    ContextMeasure.AST,
                    ContextMeasure.REB,
                    ContextMeasure.STL,
                    ContextMeasure.BLK
                }

            # 获取并处理各类型视频
            videos_result = self._collect_player_videos(
                game_id=game_id,
                player_id=player_id,
                context_measures=context_measures,
                request_delay=request_delay
            )

            if not videos_result["success"]:
                return {}

            all_videos = videos_result["videos"]
            videos_type_map = videos_result["videos_type_map"]

            # 下载视频
            videos_dict = self._download_videos(
                videos=all_videos,
                game_id=game_id,
                player_id=player_id,
                videos_type_map=videos_type_map,
                force_reprocess=force_reprocess
            )

            if not videos_dict:
                self.logger.error("视频下载失败")
                return {}

            # 处理结果
            result = {}

            # 保存原始视频
            if keep_originals or not merge:
                result["videos"] = videos_dict

            # 处理视频和GIF
            processing_result = self._process_player_videos(
                videos_dict=videos_dict,
                player_id=player_id,
                game_id=game_id,
                output_dir=output_dir,
                output_format=output_format,
                merge=merge,
                force_reprocess=force_reprocess
            )

            # 合并结果
            result.update(processing_result)

            return result

        except Exception as e:
            self.logger.error(f"获取球员集锦失败: {str(e)}", exc_info=True)
            return {}

    def get_player_round_gifs(self, player_id: int, game_id: str, force_reprocess: bool = False) -> Dict[str, Path]:
        """从球员集锦视频创建每个回合的GIF动画

        为球员视频集锦的每个回合创建独立的GIF动画，便于在线分享和展示。
        本质上是调用get_player_highlights方法并设置为仅生成GIF。

        Args:
            player_id: 球员ID
            game_id: 比赛ID
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Path]: GIF路径字典，以事件ID为键
        """
        try:
            self.logger.info(f"正在为球员ID={player_id}的集锦视频创建回合GIF")

            # 设置特定的context_measures，包含进球和助攻
            context_measures = {
                ContextMeasure.FGM,  # 进球
                ContextMeasure.AST,  # 助攻
                ContextMeasure.BLK,  # 盖帽
            }

            # 调用get_player_highlights方法，设置为只生成GIF
            result = self.get_player_highlights(
                player_id=player_id,
                game_id=game_id,
                context_measures=context_measures,
                output_format="gif",  # 只生成GIF，不生成视频
                merge=False,  # 不需要合并视频
                keep_originals=True,  # 保留原始视频文件
                force_reprocess=force_reprocess
            )

            # 从结果中提取GIF路径
            if result and "gifs" in result:
                self.logger.info(f"处理完成! 生成了 {len(result['gifs'])} 个GIF")
                return result["gifs"]
            else:
                self.logger.error("未能生成GIF，检查球员ID或视频可用性")
                return {}

        except Exception as e:
            self.logger.error(f"处理球员回合GIF失败: {e}", exc_info=True)
            return {}

    # ==== 辅助方法 ====

    def _collect_player_videos(self,
                               game_id: str,
                               player_id: int,
                               context_measures: Set[ContextMeasure],
                               request_delay: float = 1.0) -> Dict[str, Any]:
        """收集球员所有相关视频资产

        Args:
            game_id: 比赛ID
            player_id: 球员ID
            context_measures: 上下文度量集合
            request_delay: 请求间隔时间(秒)

        Returns:
            Dict[str, Any]: 包含视频资产和类型映射的字典，以及success标志
        """
        result = {"success": False}

        # 获取并处理各类型视频
        all_videos = {}
        videos_type_map = {}  # 保存视频ID到类型的映射

        import time

        for measure in context_measures:
            # 获取视频资源
            videos = self.get_game_videos(
                game_id=game_id,
                player_id=player_id,
                context_measure=measure
            )

            if videos:
                # 保存每个视频的类型信息
                for event_id in videos.keys():
                    videos_type_map[event_id] = measure.value

                all_videos.update(videos)

                # 添加请求间隔
                if request_delay > 0:
                    time.sleep(request_delay)
                    self.logger.info(f"等待 {request_delay} 秒后继续...")

        # 如果找到视频，处理它们
        if not all_videos:
            self.logger.error(f"未找到球员ID={player_id}的任何集锦视频")
            return result

        result.update({
            "success": True,
            "videos": all_videos,
            "videos_type_map": videos_type_map
        })

        return result

    def _download_videos(self,
                         videos: Dict[str, VideoAsset],
                         game_id: str,
                         player_id: Optional[int] = None,
                         team_id: Optional[int] = None,
                         context_measure: Optional[str] = None,
                         videos_type_map: Optional[Dict[str, str]] = None,
                         force_reprocess: bool = False) -> Dict[str, Path]:
        """下载视频辅助方法

        从视频服务下载一组视频资产。

        Args:
            videos: 视频资产字典
            game_id: 比赛ID
            player_id: 球员ID (可选)
            team_id: 球队ID (可选)
            context_measure: 上下文类型 (可选)
            videos_type_map: 视频ID到类型的映射 (可选)
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Path]: 视频路径字典，以事件ID为键
        """
        try:
            # 如果提供了类型映射，使用单独下载
            if videos_type_map:
                video_paths = {}
                for event_id, video in videos.items():
                    # 从映射中获取该视频的类型
                    video_type = videos_type_map.get(event_id)
                    # 单独下载每个视频，传递其类型
                    path = self.downloader.download_video(
                        video, game_id, player_id, video_type, force_reprocess
                    )
                    if path:
                        video_paths[event_id] = path
                        self.logger.info(f"视频 {event_id} 下载成功: {path}")
                return video_paths
            else:
                # 批量下载
                return self.batch_download_videos(
                    videos,
                    game_id,
                    player_id=player_id,
                    team_id=team_id,
                    context_measure=context_measure,
                    force_reprocess=force_reprocess
                )

        except Exception as e:
            self.logger.error(f"视频下载失败: {str(e)}", exc_info=True)
            return {}

    def _process_player_videos(self,
                               videos_dict: Dict[str, Path],
                               player_id: int,
                               game_id: str,
                               output_dir: Path,
                               output_format: str = "both",
                               merge: bool = True,
                               force_reprocess: bool = False) -> Dict[str, Any]:
        """处理球员视频，包括合并和创建GIF

        Args:
            videos_dict: 视频路径字典
            player_id: 球员ID
            game_id: 比赛ID
            output_dir: 输出目录
            output_format: 输出格式，可选 "video"(仅视频), "gif"(仅GIF), "both"(视频和GIF)
            merge: 是否合并视频
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Any]: 处理结果路径字典
        """
        result = {}

        # 合并视频
        if merge and (output_format == "video" or output_format == "both"):
            output_filename = f"player_{player_id}_{game_id}.mp4"
            output_path = output_dir / output_filename

            merged_video = self._merge_videos(
                video_files=list(videos_dict.values()),
                output_path=output_path,
                remove_watermark=True,
                force_reprocess=force_reprocess
            )

            if merged_video:
                result["video_merged"] = merged_video

                if output_format == "both":
                    gif_path = self.video_processor.convert_to_gif(
                        merged_video,
                        force_reprocess=force_reprocess
                    )
                    if gif_path:
                        result["merged_gif"] = gif_path

        # 生成GIF
        if output_format == "gif" or output_format == "both":
            gif_dir = self.config.get_player_gif_dir(player_id, game_id)

            gif_paths = self._create_gifs_from_videos(
                videos=videos_dict,
                output_dir=gif_dir,
                player_id=player_id,
                force_reprocess=force_reprocess
            )

            if gif_paths:
                result["gifs"] = gif_paths

        return result

    def _merge_videos(self,
                      video_files: List[Path],
                      output_path: Path,
                      remove_watermark: bool = True,
                      force_reprocess: bool = False) -> Optional[Path]:
        """合并视频辅助方法

        将多个视频文件合并为一个视频文件。

        Args:
            video_files: 视频文件路径列表
            output_path: 输出文件路径
            remove_watermark: 是否移除水印
            force_reprocess: 是否强制重新处理

        Returns:
            Optional[Path]: 合并后的视频路径，失败则返回None
        """
        try:
            # 检查输出文件是否已存在
            if not force_reprocess and output_path.exists():
                self.logger.info(f"合并视频已存在: {output_path}")
                return output_path

            # 按事件ID排序
            video_files.sort(key=self._extract_event_id)

            # 使用视频处理器合并视频
            merged = self.video_processor.merge_videos(
                video_files,
                output_path,
                remove_watermark=remove_watermark,
                force_reprocess=force_reprocess
            )

            if merged:
                self.logger.info(f"视频合并成功: {merged}")
                return merged
            else:
                self.logger.error("视频合并失败")
                return None

        except Exception as e:
            self.logger.error(f"合并视频失败: {str(e)}", exc_info=True)
            return None

    def _create_gifs_from_videos(self,
                                 videos: Dict[str, Path],
                                 output_dir: Path,
                                 player_id: Optional[int] = None,
                                 force_reprocess: bool = False) -> Dict[str, Path]:
        """从视频创建GIF辅助方法

        为一组视频创建对应的GIF文件。

        Args:
            videos: 视频路径字典，以事件ID为键
            output_dir: GIF输出目录
            player_id: 球员ID (可选)
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Path]: GIF路径字典，以事件ID为键
        """
        try:
            # 确保输出目录存在
            output_dir.mkdir(parents=True, exist_ok=True)

            # 准备批量转换
            gif_result = {}
            video_paths = []
            event_ids = []

            # 收集视频信息
            for event_id, video_path in videos.items():
                # 创建GIF文件名
                if player_id:
                    gif_path = output_dir / f"round_{event_id}_{player_id}.gif"
                else:
                    gif_path = output_dir / f"event_{event_id}.gif"

                # 检查GIF是否已存在
                if not force_reprocess and gif_path.exists():
                    self.logger.info(f"GIF已存在: {gif_path}")
                    gif_result[event_id] = gif_path
                    continue

                # 添加到转换队列
                video_paths.append(video_path)
                event_ids.append(event_id)

            # 使用批量转换
            if video_paths:
                batch_results = self.video_processor.batch_convert_to_gif(
                    video_paths,
                    output_dir,
                    force_reprocess=force_reprocess
                )

                # 处理结果
                for i, path in enumerate(video_paths):
                    stem = path.stem
                    if stem in batch_results:
                        event_id = event_ids[i]
                        gif_result[event_id] = batch_results[stem]
                        self.logger.info(f"GIF创建成功: {batch_results[stem]}")

            return gif_result

        except Exception as e:
            self.logger.error(f"创建GIF失败: {str(e)}", exc_info=True)
            return {}

    def _extract_event_id(self, path: Path) -> int:
        """从文件名中提取事件ID

        Args:
            path: 视频文件路径

        Returns:
            int: 事件ID，如果无法提取则返回0
        """
        try:
            # 从文件名 "event_0123_game_xxxx.mp4" 中提取事件ID - 符合命名规范
            filename = path.name
            parts = filename.split('_')
            if len(parts) >= 2 and parts[0] == "event":
                return int(parts[1])
            return 0
        except (ValueError, IndexError):
            self.logger.warning(f"无法从文件名'{path.name}'中提取事件ID")
            return 0

    def batch_download_videos(
            self,
            videos: Dict[str, VideoAsset],
            game_id: str,
            player_id: Optional[int] = None,
            team_id: Optional[int] = None,
            context_measure: Optional[str] = None,
            max_videos: Optional[int] = None,
            force_reprocess: bool = False
    ) -> Dict[str, Path]:
        """批量下载视频（支持最大数量限制）

        Args:
            videos: 视频资源字典
            game_id: 比赛ID
            player_id: 球员ID (可选)
            team_id: 球队ID (可选)
            context_measure: 上下文指标 (可选)
            max_videos: 最大下载视频数量 (可选)
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Path]: 视频路径字典
        """
        if team_id:
            self.logger.info(f"处理球队ID={team_id}的视频下载")

        # 创建有序的视频列表 (按事件ID排序)
        sorted_videos = sorted([(event_id, video) for event_id, video in videos.items()])

        # 如果有最大下载限制，裁剪列表
        if max_videos and max_videos < len(sorted_videos):
            sorted_videos = sorted_videos[:max_videos]
            self.logger.info(f"将下载数量限制为前 {max_videos} 个视频")

        # 创建下载子集
        limited_videos = {event_id: video for event_id, video in sorted_videos}

        # 调用下载方法
        return self.download_videos(
            limited_videos,
            game_id,
            player_id,
            context_measure,
            timeout=self.config.request_timeout * len(limited_videos),  # 根据视频数量调整总超时
            force_reprocess=force_reprocess
        )

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

    def clear_cache(self):
        """清理视频服务缓存"""
        try:
            if hasattr(self, 'video_fetcher') and hasattr(self.video_fetcher, 'clear_cache'):
                self.video_fetcher.clear_cache()
                self.logger.info("已清理视频获取器缓存")
        except Exception as e:
            self.logger.error(f"清理缓存失败: {str(e)}")

    def close(self):
        """关闭服务并清理资源"""
        try:
            if hasattr(self, 'downloader'):
                self.downloader.close()

            if hasattr(self, 'video_fetcher') and hasattr(self.video_fetcher, 'clear_cache'):
                self.video_fetcher.clear_cache()

            self.logger.info("视频服务资源已清理")
        except Exception as e:
            self.logger.error(f"清理资源失败: {str(e)}", exc_info=True)