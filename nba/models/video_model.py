from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from enum import Enum
from datetime import datetime
from dataclasses import dataclass

# 1. 定义枚举类

class ContextMeasure(str, Enum):
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

# 2. 定义辅助模型
@dataclass
class VideoRequestParams:
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

class VideoUrl(BaseModel):
    """视频URL及相关信息"""
    uuid: str
    sdur: int                  # 标清视频时长
    surl: str                  # 标清视频URL
    sth: str                   # 标清缩略图
    mdur: int                  # 中等质量视频时长
    murl: str                  # 中等质量视频URL
    mth: str                   # 中等质量缩略图
    ldur: int                  # 高清视频时长
    lurl: str                  # 高清视频URL
    lth: str                   # 高清缩略图
    vtt: str                   # WebVTT字幕
    scc: str                   # SCC字幕
    srt: str                   # SRT字幕

    @property
    def duration(self) -> int:
        """获取视频时长（使用高清时长）"""
        return self.ldur

    @property
    def urls(self) -> Dict[str, str]:
        """获取不同质量的视频URL"""
        return {
            'sd': self.surl,
            'md': self.murl,
            'hd': self.lurl
        }

    @property
    def thumbnails(self) -> Dict[str, str]:
        """获取不同质量的缩略图URL"""
        return {
            'sd': self.sth,
            'md': self.mth,
            'hd': self.lth
        }

    @property
    def subtitles(self) -> Dict[str, str]:
        """获取不同格式的字幕URL"""
        return {
            'vtt': self.vtt,
            'scc': self.scc,
            'srt': self.srt
        }

class PlaylistItem(BaseModel):
    """播放列表项目"""
    gi: str                    # 比赛ID
    ei: int                    # 事件ID
    y: int                     # 年份
    m: str                     # 月份
    d: str                     # 日期
    gc: str                    # 比赛代码
    p: int                     # 节次
    dsc: str                   # 描述
    ha: str                    # 主队缩写
    hid: int                   # 主队ID
    va: str                    # 客队缩写
    vid: int                   # 客队ID
    hpb: int                   # 主队得分(之前)
    hpa: int                   # 主队得分(之后)
    vpb: int                   # 客队得分(之前)
    vpa: int                   # 客队得分(之后)
    pta: int = 0               # 得分增量
    personId: Optional[int] = None          # 涉及的球员ID (新增)
    event_type: Optional[str] = None        # 事件类型 (使用字符串，避免直接依赖 EventType)

    @property
    def game_date(self) -> datetime:
        """获取比赛日期"""
        return datetime(self.y, int(self.m), int(self.d))

    @property
    def score_before(self) -> Dict[str, int]:
        """获取得分变化前的比分"""
        return {'home': self.hpb, 'away': self.vpb}

    @property
    def score_after(self) -> Dict[str, int]:
        """获取得分变化后的比分"""
        return {'home': self.hpa, 'away': self.vpa}

    @property
    def score_difference(self) -> int:
        """计算主客队分差（正数表示主队领先）"""
        return self.hpa - self.vpa

class VideoMetaData(BaseModel):
    """视频元数据"""
    videoUrls: List[VideoUrl]

class VideoResultSets(BaseModel):
    """视频结果集"""
    Meta: VideoMetaData
    playlist: List[PlaylistItem]

class GameEvent(BaseModel):
    """关联的比赛事件信息"""
    game_id: str
    event_id: int
    event_type: Optional[str] = None  # 使用字符串，避免直接依赖 EventType
    description: str
    period: int
    clock: Optional[str] = None
    person_id: Optional[int] = None
   

class VideoAsset(BaseModel):
    """视频资产信息"""
    uuid: str
    duration: int
    urls: Dict[str, str]
    thumbnails: Dict[str, str]
    subtitles: Dict[str, str]
    event_info: Dict[str, Any]  # 可以根据需求调整为更具体的类型
    game_event: Optional[GameEvent] = None  # 事件信息为可选
    
    @property
    def get_video_url(self, quality: str) -> Optional[str]:
        """
        获取指定质量的视频URL。

        Args:
            quality (str): 视频质量，支持 'sd'、'md'、'hd'

        Returns:
            Optional[str]: 对应质量的视频URL，如果不存在则返回 None
        """
        return self.urls.get(quality)

class VideoResponse(BaseModel):
    """视频响应数据"""
    resource: str
    parameters: VideoRequestParams
    resultSets: VideoResultSets

    def get_video_by_event_id(self, event_id: int) -> Optional[VideoAsset]:
        """根据事件ID获取对应的视频资产信息"""
        for video_url in self.resultSets.Meta.videoUrls:
            # 假设视频URL中包含事件ID，可以根据实际情况调整匹配逻辑
            if f'/{event_id}/' in video_url.lurl:
                # 假设你有方法通过 uuid 获取 VideoAsset
                video_asset = fetch_video_asset_by_uuid(video_url.uuid)
                if video_asset:
                    return video_asset
        return None

    def get_playlist_by_period(self, period: int) -> List[PlaylistItem]:
        """获取指定节次的所有播放项"""
        return [item for item in self.resultSets.playlist if item.p == period]

    def get_total_videos(self) -> int:
        """获取视频总数"""
        return len(self.resultSets.Meta.videoUrls)
