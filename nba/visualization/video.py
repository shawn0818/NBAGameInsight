import re
from pathlib import Path
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum
import requests
from config.nba_config import NBAConfig
from utils import http_handler
from utils.video_utils import VideoDownloader, VideoConverter

logger = logging.getLogger(__name__)

class ContextMeasure(Enum):
    """上下文度量类型"""
    FGM = "FGM"       # 投篮命中
    FGA = "FGA"       # 投篮出手
    AST = "AST"       # 助攻
    BLOCK = "BLOCK"   # 盖帽
    STEAL = "STEAL"   # 抢断

@dataclass
class VideoQueryParams:
    """视频查询参数构建器"""
    # 必需参数
    game_id: str
    player_id: Optional[str] = None
    team_id: Optional[str] = None
    context_measure: ContextMeasure = ContextMeasure.FGM
    
    def build(self) -> dict:
        """构建与NBA API完全一致的查询参数"""
        return {
            'AheadBehind': '',
            'CFID': '',
            'CFPARAMS': '',
            'ClutchTime': '',
            'Conference': '',
            'ContextFilter': '',
            'ContextMeasure': self.context_measure.value,
            'DateFrom': '',
            'DateTo': '',
            'Division': '',
            'EndPeriod': 0,
            'EndRange': 28800,
            'GROUP_ID': '',
            'GameEventID': '',
            'GameID': self.game_id,
            'GameSegment': '',
            'GroupID': '',
            'GroupMode': '',
            'GroupQuantity': 5,
            'LastNGames': 0,
            'LeagueID': '00',
            'Location': '',
            'Month': 0,
            'OnOff': '',
            'OppPlayerID': '',
            'OpponentTeamID': 0,
            'Outcome': '',
            'PORound': 0,
            'Period': 0,
            'PlayerID': self.player_id if self.player_id else '',
            'PlayerID1': '',
            'PlayerID2': '',
            'PlayerID3': '',
            'PlayerID4': '',
            'PlayerID5': '',
            'PlayerPosition': '',
            'PointDiff': '',
            'Position': '',
            'RangeType': 0,
            'RookieYear': '',
            'Season': '2024-25',
            'SeasonSegment': '',
            'SeasonType': 'Regular Season',
            'ShotClockRange': '',
            'StartPeriod': 0,
            'StartRange': 0,
            'StarterBench': '',
            'TeamID': self.team_id if self.team_id else '',
            'VsConference': '',
            'VsDivision': '',
            'VsPlayerID1': '',
            'VsPlayerID2': '',
            'VsPlayerID3': '',
            'VsPlayerID4': '',
            'VsPlayerID5': '',
            'VsTeamID': ''
        }

@dataclass
class VideoAsset:
    """视频资源数据类"""
    uuid: str                   # 视频唯一标识符
    duration: int               # 视频时长(毫秒)
    urls: Dict[str, str]        # 不同分辨率的视频URL
    thumbnails: Dict[str, str]  # 缩略图URL
    subtitles: Dict[str, str]   # 字幕文件URL
    event_info: Dict            # 事件相关信息

class NBAVideoProcessor:
    """NBA视频资源处理器"""
    
    def __init__(self):
        """初始化视频处理器"""
        # 视频资源缓存: (game_id, event_id) -> VideoAsset
        self.video_assets: Dict[Tuple[str, str], VideoAsset] = {}
        
        # 初始化session
        self.session = requests.Session()
        self.session.headers.update(http_handler.HTTPConfig.HEADERS)
        
        # 初始化视频下载器
        self.downloader = VideoDownloader(self.session)

    def get_play_type_videos(self, game_id: str, player_id: Optional[str] = None, 
                            context_measure: ContextMeasure = ContextMeasure.FGM,
                            team_id: Optional[str] = None) -> Dict[str, VideoAsset]:
        """
        获取指定类型的比赛视频
        
        Args:
            game_id: 比赛ID
            player_id: 球员ID(可选)
            context_measure: 动作类型(默认为投篮命中)
            team_id: 球队ID(可选)
            
        Returns:
            Dict[str, VideoAsset]: 视频资源映射
        """
        query = VideoQueryParams(
            game_id=game_id,
            player_id=player_id,
            team_id=team_id,
            context_measure=context_measure
        )
        
        return self.get_videos_by_query(query)

    def get_videos_by_query(self, query: VideoQueryParams) -> Dict[str, VideoAsset]:
        """根据查询参数获取视频"""
        try:
            params = query.build()
            response_data = self._fetch_video_data(params)
            if response_data:
                return self.process_video_response(query.game_id, response_data)
            return {}
            
        except Exception as e:
            logger.error(f"Failed to get videos by query: {e}")
            return {}

    def _fetch_video_data(self, params: dict) -> Optional[Dict]:
        """获取视频数据"""
        try:
            for _ in range(NBAConfig.API.MAX_RETRIES):
                try:
                    response = self.session.get(
                        NBAConfig.URLS.VIDEO_DATA,
                        params=params,
                        timeout=NBAConfig.API.TIMEOUT
                    )
                    response.raise_for_status()
                    return response.json()
                except requests.RequestException as e:
                    logger.warning(f"Retry after error: {e}")
                    continue
            return None
        except Exception as e:
            logger.error(f"Failed to fetch video data: {e}")
            return None

    def process_video_response(self, game_id: str, response_data: Dict) -> Dict[str, VideoAsset]:
        """处理视频响应数据"""
        event_video_map = {}
        
        try:
            video_urls = response_data.get('resultSets', {}).get('Meta', {}).get('videoUrls', [])
            playlist = response_data.get('resultSets', {}).get('playlist', [])
            
            for play_item in playlist:
                event_id = str(play_item.get('ei'))
                if not event_id:
                    continue
                    
                # 查找对应的视频数据
                video_data = next((v for v in video_urls if any(
                    url in v.get('lurl', '') for url in [f'/{event_id}/', f'/{game_id}/']
                )), None)
                
                if video_data:
                    video_asset = VideoAsset(
                        uuid=video_data.get('uuid', ''),
                        duration=int(video_data.get('ldur', 0)),
                        urls={
                            'sd': video_data.get('surl'),
                            'hd': video_data.get('murl'),
                            'fhd': video_data.get('lurl')
                        },
                        thumbnails={
                            'sd': video_data.get('sth'),
                            'hd': video_data.get('mth'),
                            'fhd': video_data.get('lth')
                        },
                        subtitles={
                            'vtt': video_data.get('vtt'),
                            'scc': video_data.get('scc'),
                            'srt': video_data.get('srt')
                        },
                        event_info={
                            'game_id': game_id,
                            'event_id': event_id,
                            'period': play_item.get('p'),
                            'description': play_item.get('dsc'),
                            'home_team': play_item.get('ha'),
                            'away_team': play_item.get('va'),
                            'score': {
                                'home': {
                                    'before': play_item.get('hpb'),
                                    'after': play_item.get('hpa')
                                },
                                'away': {
                                    'before': play_item.get('vpb'),
                                    'after': play_item.get('vpa')
                                }
                            }
                        }
                    )
                    
                    key = (game_id, event_id)
                    self.video_assets[key] = video_asset
                    event_video_map[event_id] = video_asset
                    
        except Exception as e:
            logger.error(f"Error processing video response: {e}")
            
        return event_video_map

    def download_video(self, video_asset: VideoAsset, quality: str = 'hd') -> Optional[Path]:
        """下载视频"""
        url = video_asset.urls.get(quality)
        if not url:
            logger.error(f"No video URL found for quality: {quality}")
            return None
            
        try:
            # 构造输出文件路径
            event_info = video_asset.event_info
            safe_name = re.sub(r'\W+', '_', event_info['description'])
            output_path = NBAConfig.PATHS.VIDEO_DIR / f"{event_info['game_id']}_{event_info['event_id']}_{safe_name}.mp4"
            
            # 下载视频
            if self.downloader.download(url, output_path):
                return output_path
            return None
            
        except Exception as e:
            logger.error(f"Failed to download video: {e}")
            return None

    def clear_cache(self):
        """清除视频资源缓存"""
        self.video_assets.clear()