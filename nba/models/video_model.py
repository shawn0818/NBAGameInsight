from typing import Optional, Dict, Any
from pydantic import BaseModel
from enum import Enum


class VideoQuality(BaseModel):
    """不同质量的视频信息"""
    duration: int  # 视频时长
    url: str       # 视频URL
    thumbnail: str # 缩略图URL

    class Config:
        frozen = True


class ContextMeasure(str, Enum):
    """视频查询的上下文度量类型"""
    FG3M = "FG3M"  # 三分命中
    FG3A = "FG3A"  # 三分出手
    FGM = "FGM"    # 投篮命中
    FGA = "FGA"    # 投篮出手
    OREB = "OREB"  # 进攻篮板
    DREB = "DREB"  # 防守篮板
    REB = "REB"    # 总篮板
    AST = "AST"    # 助攻
    STL = "STL"    # 抢断
    BLK = "BLK"    # 盖帽
    TOV = "TOV"    # 失误


class VideoAsset(BaseModel):
    """
    视频资产信息

    - event_id: 用于与外部事件模型关联的标识符
    - uuid: NBA 返回的视频唯一标识
    - qualities: 不同清晰度的视频信息（如 'sd', 'hd'）
    """
    event_id: str
    uuid: str
    qualities: Dict[str, VideoQuality]

    @property
    def duration(self) -> int:
        """获取视频时长（优先使用高清时长）"""
        return self.qualities.get('hd', self.qualities.get('sd')).duration

    @property
    def urls(self) -> Dict[str, str]:
        """获取不同质量的视频URL"""
        return {
            quality_key: q.url for quality_key, q in self.qualities.items()
        }

    @property
    def thumbnails(self) -> Dict[str, str]:
        """获取不同质量的缩略图URL"""
        return {
            quality_key: q.thumbnail for quality_key, q in self.qualities.items()
        }

    class Config:
        frozen = True



class VideoResponse(BaseModel):
    """视频响应数据"""
    resource: str
    parameters: Dict[str, Any]
    resultSets: Dict[str, Any]

    def get_total_videos(self) -> int:
        """获取视频总数"""
        return len(self.resultSets.get('Meta', {}).get('videoUrls', []))

    class Config:
        frozen = True
