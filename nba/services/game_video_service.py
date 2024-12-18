from typing import Dict, Optional, Tuple, List, Union
import logging
from datetime import datetime, timedelta
import json
from pathlib import Path
import requests

from nba.models.game_event_model import (
    PlayerBasicInfo,
    GameEvent,
    GameEventCollection,
    Player,
    Location,
    Score,
    Shot,
    EventType,
    VideoAsset
)
from nba.fetcher.schedule import ScheduleFetcher
from nba.parser.game_parser import GameDataParser
from nba.parser.player_parser import PlayerDataParser
from nba.parser.schedule_parser import ScheduleParser
from nba.fetcher.player import PlayerFetcher
from utils.time_helper import TimeConverter
from nba.parser.video_query_parser import (
    NBAVideoProcessor, 
    VideoQueryParams, 
    ContextMeasure, 
)
from utils.video_download import VideoDownloader, VideoConverter
from nba.services.name_id_service import NBAMappingService
from config.nba_config import NBAConfig

# 维护一个事件类型到上下文度量的映射
ACTION_TO_MEASURE = {
    'FG3M': ContextMeasure.FG3M,  # 三分命中
    'FG3A': ContextMeasure.FG3A,  # 三分出手
    'FGM': ContextMeasure.FGM,    # 投篮命中
    'FGA': ContextMeasure.FGA,    # 投篮出手
    'OREB': ContextMeasure.OREB,  # 进攻篮板
    'DREB': ContextMeasure.DREB,  # 防守篮板
    'REB': ContextMeasure.REB,    # 总篮板
    'AST': ContextMeasure.AST,    # 助攻
    'STL': ContextMeasure.STL,    # 抢断
    'BLK': ContextMeasure.BLK,    # 盖帽
    'TOV': ContextMeasure.TOV,    # 失误
}


class VideoService:
    """NBA视频服务"""
    
    def __init__(self):
        """初始化视频服务"""
        self.logger = logging.getLogger(__name__)
        self.mapping_service = NBAMappingService()
        self.video_processor = NBAVideoProcessor()
        self.game_parser = GameDataParser()
        self.schedule_parser = ScheduleParser()
        self.player_fetcher = PlayerFetcher()
        self.downloader = VideoDownloader()  # 确保实例化
        self.converter = VideoConverter()    # 确保实例化
        
    def get_player_videos(
        self,
        player_name: str,
        action_type: str,
        game_date: Optional[str] = "today",
        game_id: Optional[str] = None,
        season_type: str = "Regular Season",
        season: str = "2024-25"
    ) -> Tuple[Optional[GameEventCollection], str]:
        """
        获取指定球员特定动作类型的视频集锦。

        Args:
            player_name (str): 球员姓名（支持全名、单姓、绰号等）
            action_type (str): 动作类型，支持：
                - FG3M (三分命中)
                - FG3A (三分出手)
                - FGM (投篮命中)
                - FGA (投篮出手)
                - OREB (进攻篮板)
                - DREB (防守篮板)
                - REB (总篮板)
                - AST (助攻)
                - STL (抢断)
                - BLK (盖帽)
                - TOV (失误)
            game_date (Optional[str]): 比赛日期
            game_id (Optional[str]): 比赛ID
            season_type (str): 赛季类型
            season (str): 赛季年份

        Returns:
            Tuple[Optional[GameEventCollection], str]: (事件集合, 错误信息)
        """
        try:
            # 1. 验证动作类型
            if action_type not in ACTION_TO_MEASURE:
                return None, f"不支持的动作类型: {action_type}。支持的类型包括: {list(ACTION_TO_MEASURE.keys())}"

            # 2. 获取球员信息
            player_id = self.mapping_service.get_player_id(player_name)
            if not player_id:
                return None, f"未找到球员: {player_name}"

            # 3. 获取game_id
            if not game_id and game_date:
                game_id = self._get_game_id_by_date(player_id, game_date)
                if not game_id:
                    return None, f"未找到 {player_name} 在 {game_date} 的比赛"

            # 4. 构建查询参数并获取视频数据
            query = VideoQueryParams(
                game_id=game_id,
                player_id=player_id,
                team_id=self._get_player_team_id(player_id),
                context_measure=ACTION_TO_MEASURE[action_type]
            )
            video_data = self.video_processor.get_videos_by_query(query)
            
            if not video_data:
                return None, f"未找到 {player_name} 在该比赛中 {action_type} 的视频片段"

            # 5. 转换为GameEvent模型
            events = self._convert_to_game_events(video_data, game_id)
            return GameEventCollection(game_id=game_id, events=events), ""

        except Exception as e:
            error_msg = f"获取 {player_name} 的 {action_type} 视频时出错: {e}"
            self.logger.error(error_msg)
            return None, error_msg

    def _convert_to_game_events(self, video_data: Dict[str, VideoAsset], game_id: str) -> List[GameEvent]:
        """将视频数据转换为GameEvent列表"""
        events = []
        for event_id, video in video_data.items():
            try:
                event_info = video.event_info  # 直接访问属性

                # 创建Player对象
                player_info = event_info.get('player_info', {})
                player = Player(
                    person_id=player_info.get('player_id', ''),
                    first_name=player_info.get('first_name', ''),
                    last_name=player_info.get('last_name', ''),
                    team_id=player_info.get('team_id', ''),
                    team_tricode=player_info.get('team_tricode', ''),
                    position=player_info.get('position')  # 假设有位置字段
                )

                # 创建Location对象
                location_info = event_info.get('location', {})
                location = Location(
                    x=location_info.get('x'),
                    y=location_info.get('y'),
                    area=location_info.get('area'),
                    area_detail=location_info.get('area_detail'),
                    side=location_info.get('side')
                )

                # 创建Score对象
                score_info = event_info.get('score', {})
                score = Score(
                    home=score_info.get('home', {}).get('after', 0),
                    away=score_info.get('away', {}).get('after', 0),
                    difference=score_info.get('home', {}).get('after', 0) - 
                              score_info.get('away', {}).get('after', 0)
                )

                # 根据事件类型创建特定事件详情（如Shot）
                shot = None
                if 'shot' in event_info:
                    shot_info = event_info['shot']
                    shot = Shot(
                        shooter=player,
                        shot_type=shot_info.get('shot_type', ''),
                        result=shot_info.get('result', ''),
                        distance=shot_info.get('distance'),
                        location=location,
                        assisted_by=None,  # 如果有助攻信息，需要创建另一个Player对象
                        blocked_by=None    # 如果有盖帽信息，需要创建另一个Player对象
                    )

                # 创建GameEvent对象
                event = GameEvent(
                    game_id=game_id,
                    event_id=event_id,
                    event_type=self._determine_event_type(event_info.get('action_type', '')),
                    description=event_info.get('description', ''),
                    period=event_info.get('period', 1),
                    clock=event_info.get('clock', '00:00'),
                    score=score,
                    timestamp=datetime.now(),  # 这里应该使用事件的实际时间戳
                    location=location,
                    shot=shot,
                    rebound=None,  # 需要类似shot的处理方式
                    foul=None,     # 需要类似shot的处理方式
                    video_available=True,
                    video_url=video.get_video_url('hd')  # 使用方法获取视频URL
                )
                events.append(event)
            except Exception as e:
                self.logger.error(f"转换事件 {event_id} 时出错: {e}")
                continue

        return events

    def _determine_event_type(self, action_type: str) -> EventType:
        """确定事件类型"""
        mapping = {
            'FGM': EventType.FIELD_GOAL,
            'FGA': EventType.FIELD_GOAL,
            'FG3M': EventType.THREE_POINT,
            'FG3A': EventType.THREE_POINT,
            'REB': EventType.REBOUND,
            'AST': EventType.FIELD_GOAL,  # 助攻通常与投篮关联
            'STL': EventType.TURNOVER,
            'BLK': EventType.FIELD_GOAL,  # 盖帽通常与投篮关联
            'TOV': EventType.TURNOVER
        }
        return mapping.get(action_type, EventType.FIELD_GOAL)

    def _get_game_id_by_date(self, player_id: str, date_str: str) -> Optional[str]:
        """根据日期获取比赛ID"""
        try:
            # 获取球员所属球队ID
            team_id = self._get_player_team_id(player_id)
            if not team_id:
                self.logger.error(f"未找到球员 {player_id} 的球队信息")
                return None

            # 获取赛程数据
            schedule_data = self.schedule_parser.parse_raw_schedule(
                self.player_fetcher.get_schedule()  # 假设这个方法存在
            )

            if schedule_data.empty:
                self.logger.error("无法获取赛程数据")
                return None

            if date_str.lower() == "today":
                # 获取今天的比赛ID
                beijing_now = datetime.now(TimeConverter.BEIJING_TZ)
                return self.schedule_parser.get_game_id(schedule_data, int(team_id), beijing_now.strftime("%Y-%m-%d"))
            elif date_str.lower() == "yesterday":
                # 获取昨天的比赛ID
                beijing_yesterday = datetime.now(TimeConverter.BEIJING_TZ) - timedelta(days=1)
                return self.schedule_parser.get_game_id(schedule_data, int(team_id), beijing_yesterday.strftime("%Y-%m-%d"))
            elif date_str.lower() == "recent":
                # 获取最近的比赛ID
                return self.schedule_parser.get_last_game_id(schedule_data, int(team_id))
            else:
                try:
                    # 验证日期格式
                    game_date = datetime.strptime(date_str, "%Y-%m-%d")
                    return self.schedule_parser.get_game_id(schedule_data, int(team_id), date_str)
                except ValueError:
                    self.logger.error(f"无效的日期格式: {date_str}")
                    return None

        except Exception as e:
            self.logger.error(f"获取比赛ID时出错，日期：{date_str}，错误：{e}")
            return None

    def _get_player_team_id(self, player_id: str) -> Optional[str]:
        """获取球员当前所属球队ID"""
        try:
            # 从映射服务中获取球员数据
            player_name = self.mapping_service.get_player_name(player_id)
            if not player_name:
                self.logger.error(f"未找到球员: {player_id}")
                return None

            # 使用缓存的球员数据获取球队ID
            with self.mapping_service.player_cache_file.open('r') as f:
                cache_data = json.load(f)
                for player_data in cache_data.get('players', []):
                    if player_data.get('person_id') == player_id:
                        return player_data.get('team_info', {}).get('id')

            self.logger.error(f"未找到球员 {player_id} 的球队信息")
            return None

        except Exception as e:
            self.logger.error(f"获取球员 {player_id} 的球队ID时出错: {e}")
            return None

    def refresh_mapping_data(self):
        """刷新映射数据"""
        self.mapping_service.refresh_mappings()

    def download_player_video(
        self,
        video_url: str,
        player_name: str,
        game_id: str,
        event_id: str,
        output_format: str = 'mp4',
        quality: str = 'hd',
        compress: bool = False
    ) -> Tuple[Optional[Path], str]:
        """
        下载球员视频片段

        Args:
            video_url (str): 视频URL
            player_name (str): 球员姓名
            game_id (str): 比赛ID
            event_id (str): 事件ID
            output_format (str): 输出格式，支持 'mp4' 或 'gif'
            quality (str): 视频质量，支持 'sd'、'hd' 或 'fhd'
            compress (bool): 是否压缩视频

        Returns:
            Tuple[Optional[Path], str]: (视频文件路径, 错误信息)
        """
        try:
            # 1. 生成保存路径
            video_name = f"{player_name}_{game_id}_{event_id}"
            temp_path = NBAConfig.PATHS.CACHE_DIR / f"{video_name}_temp.mp4"
            output_path = NBAConfig.PATHS.VIDEO_DIR / f"{video_name}.{output_format}"

            # 2. 下载视频
            if not self.downloader.download(video_url, temp_path):
                return None, "视频下载失败"

            # 3. 处理视频
            try:
                if output_format.lower() == 'gif':
                    # 生成GIF的输出文件路径
                    gif_output_path = NBAConfig.PATHS.GIF_DIR / f"{video_name}.gif"

                    # 确保GIF目录存在
                    gif_output_path.parent.mkdir(parents=True, exist_ok=True)

                    # 转换为GIF
                    if not self.converter.to_gif(
                        video_path=temp_path,
                        output_path=gif_output_path,  # 使用具体的文件路径
                        fps=12,
                        scale=960,
                        remove_source=True
                    ):
                        return None, "GIF转换失败"
                elif compress:
                    # 压缩视频
                    if not self.converter.compress_video(
                        video_path=temp_path,
                        output_path=output_path,
                        crf=23,
                        preset='medium',
                        remove_source=True
                    ):
                        return None, "视频压缩失败"
                else:
                    # 确保输出目录存在
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # 直接重命名
                    temp_path.rename(output_path)

                return output_path, ""

            except Exception as e:
                # 清理临时文件
                if temp_path.exists():
                    temp_path.unlink()
                raise e

        except Exception as e:
            error_msg = f"下载视频时出错: {e}"
            self.logger.error(error_msg)
            return None, error_msg

    def batch_download_videos(
        self,
        videos: Dict[str, VideoAsset],
        player_name: str,
        game_id: str,
        output_format: str = 'mp4',
        quality: str = 'hd',
        compress: bool = False
    ) -> Dict[str, Union[Path, str]]:
        """
        批量下载视频

        Args:
            videos: 视频数据字典，key为event_id，value为VideoAsset对象
            player_name: 球员姓名
            game_id: 比赛ID
            output_format: 输出格式
            quality: 视频质量
            compress: 是否压缩

        Returns:
            Dict[str, Union[Path, str]]: 下载结果字典，key为event_id，
                value为成功时的文件路径或失败时的错误信息
        """
        results = {}
        for event_id, video_asset in videos.items():
            video_url = video_asset.get_video_url(quality)
            self.logger.info(f"Event ID: {event_id}, Video URL: {video_url}")  # 添加日志记录
            
            if not video_url:
                results[event_id] = f"未找到{quality}质量的视频URL"
                continue

            path, error = self.download_player_video(
                video_url=video_url,
                player_name=player_name,
                game_id=game_id,
                event_id=event_id,
                output_format=output_format,
                quality=quality,
                compress=compress
            )

            results[event_id] = path if path else error

        return results
