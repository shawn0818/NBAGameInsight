# nba/models/videos.py

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum
from nba.models.game_events import GameEvent

class ContextMeasure(Enum):
    """视频查询的上下文度量类型"""
    FG3M = "FG3M"       # 三分命中
    FG3A = "FG3A"       # 三分出手
    FGM = "FGM"         # 投篮命中
    FGA = "FGA"         # 投篮出手
    OREB = "OREB"       # 进攻篮板
    DREB = "DREB"       # 防守篮板
    REB = "REB"         # 总篮板
    AST = "AST"         # 助攻
    STL = "STL"         # 抢断
    BLK = "BLK"         # 盖帽
    TOV = "TOV"         # 失误

@dataclass
class VideoAsset:
    """视频资源数据模型"""
    uuid: str
    duration: int  # 视频时长（秒）
    urls: Dict[str, str]  # 不同质量的视频URL，如 {'sd': url1, 'hd': url2}
    thumbnails: Dict[str, str]  # 不同质量的缩略图URL
    subtitles: Dict[str, str]  # 不同格式的字幕文件URL
    event_info: Dict[str, Any]  # 事件相关信息
    game_event: Optional[GameEvent] = None  # 关联的比赛事件

    @property
    def sd_url(self) -> Optional[str]:
        """获取标清视频URL"""
        return self.urls.get('sd')

    @property
    def hd_url(self) -> Optional[str]:
        """获取高清视频URL"""
        return self.urls.get('hd')

    @property
    def fhd_url(self) -> Optional[str]:
        """获取全高清视频URL"""
        return self.urls.get('fhd')

    @property
    def thumbnail(self) -> Optional[str]:
        """获取默认缩略图URL（优先返回高清）"""
        return self.thumbnails.get('hd') or self.thumbnails.get('sd')

    def get_video_url(self, quality: str = 'hd') -> Optional[str]:
        """
        获取指定质量的视频URL

        Args:
            quality (str): 视频质量，支持 'sd'、'hd'、'fhd'

        Returns:
            Optional[str]: 视频URL，如果指定质量不存在则返回None
        """
        return self.urls.get(quality.lower())

    def get_subtitle_url(self, format: str = 'vtt') -> Optional[str]:
        """
        获取指定格式的字幕URL

        Args:
            format (str): 字幕格式，支持 'vtt'、'scc'、'srt'

        Returns:
            Optional[str]: 字幕URL，如果指定格式不存在则返回None
        """
        return self.subtitles.get(format.lower())

    def get_thumbnail_url(self, quality: str = 'hd') -> Optional[str]:
        """
        获取指定质量的缩略图URL

        Args:
            quality (str): 缩略图质量，支持 'sd'、'hd'、'fhd'

        Returns:
            Optional[str]: 缩略图URL，如果指定质量不存在则返回None
        """
        return self.thumbnails.get(quality.lower())

@dataclass
class VideoCollection:
    """视频集合"""
    game_id: str
    videos: Dict[str, VideoAsset]  # 键为event_id
    timestamp: datetime = field(default_factory=datetime.now)

    def get_video(self, event_id: str) -> Optional[VideoAsset]:
        """获取指定事件的视频"""
        return self.videos.get(event_id)

    def get_videos_by_period(self, period: int) -> Dict[str, VideoAsset]:
        """获取指定节的所有视频"""
        return {
            event_id: video 
            for event_id, video in self.videos.items() 
            if video.game_event and video.game_event.period == period
        }

    def get_videos_by_player(self, player_id: str) -> Dict[str, VideoAsset]:
        """获取指定球员的所有视频"""
        return {
            event_id: video
            for event_id, video in self.videos.items()
            if video.game_event and self._player_in_event(video.game_event, player_id)
        }

    @property 
    def video_count(self) -> int:
        """获取视频总数"""
        return len(self.videos)

    def __len__(self) -> int:
        """获取视频总数"""
        return self.video_count

    def _player_in_event(self, event: GameEvent, player_id: str) -> bool:
        """检查球员是否参与了事件"""
        players = event.get_player_ids()
        return player_id in players

@dataclass
class VideoQueryParams:
    """视频查询参数构建器"""
    game_id: str
    player_id: Optional[str] = None
    team_id: Optional[str] = None
    context_measure: ContextMeasure = ContextMeasure.FGM
    season: str = "2024-25"
    season_type: str = "Regular Season"
    
    def build(self) -> dict:
        """构建与NBA API完全一致的查询参数"""
        params = {
            'LeagueID': "00",
            'Season': self.season,
            'SeasonType': self.season_type,
            'TeamID': int(self.team_id) if self.team_id else 0,
            'PlayerID': int(self.player_id) if self.player_id else 0,
            'GameID': self.game_id,
            'Outcome': None,
            'Location': None,
            'Month': 0,
            'SeasonSegment': None,
            'DateFrom': None,
            'DateTo': None,
            'OpponentTeamID': 0,
            'VsConference': None,
            'VsDivision': None,
            'Position': None,
            'RookieYear': None,
            'GameSegment': None,
            'Period': 0,
            'LastNGames': 0,
            'ClutchTime': None,
            'AheadBehind': None,
            'PointDiff': None,
            'RangeType': 0,
            'StartPeriod': 0,
            'EndPeriod': 0,
            'StartRange': 0,
            'EndRange': 28800,
            'ContextFilter': "",
            'ContextMeasure': self.context_measure.value,
            'OppPlayerID': None
        }
        
        # 转换None为空字符串，保持与API格式一致
        return {k: ('' if v is None else v) for k, v in params.items()}
