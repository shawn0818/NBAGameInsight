import logging
from typing import Optional, Dict
from nba.models.game_event_model import (
    VideoAsset,
    VideoCollection,
    ContextMeasure,
    VideoQueryParams,
    GameEvent,
    EventType,
    Score
)
from utils.http_handler import HTTPRequestManager, HTTPConfig
from utils.video_download import VideoDownloader
from config.nba_config import NBAConfig
from nba.fetcher.base import BaseNBAFetcher
from nba.parser.game_parser import GameDataParser


class NBAVideoProcessor(BaseNBAFetcher):
    """NBA视频资源处理器"""
    
    def __init__(self):
        """初始化视频处理器"""
        super().__init__()
        self.video_assets: Dict[str, VideoAsset] = {}


    def get_videos_by_query(self, query: VideoQueryParams) -> Dict[str, VideoAsset]:
        """根据查询参数获取视频"""
        try:
            # 构建API参数
            params = query.build()
            
            # 记录请求信息
            self.logger.info(f"Fetching videos for game {query.game_id}")

            # 使用基类的请求方法
            response_data = self._make_request(
                url=NBAConfig.URLS.VIDEO_DATA,
                method='GET',
                params=params
            )

            if response_data:
                return self.process_video_response(query.game_id, response_data)
            return {}
            
        except Exception as e:
            self.logger.error(f"Failed to get videos by query: {e}")
            return {}

    def process_video_response(self, game_id: str, response_data: Dict) -> Dict[str, VideoAsset]:
        """处理视频响应数据"""
        event_video_map = {}
        
        try:
            video_urls = response_data.get('resultSets', {}).get('Meta', {}).get('videoUrls', [])
            playlist = response_data.get('resultSets', {}).get('playlist', [])
            
            self.logger.debug(f"Video URLs: {video_urls}")
            self.logger.debug(f"Playlist: {playlist}")
            
            for play_item in playlist:
                event_id = str(play_item.get('ei'))
                if not event_id:
                    continue
                
                # 查找对应的视频数据，仅基于 event_id 进行匹配
                video_data = next((v for v in video_urls if f'/{event_id}/' in v.get('lurl', '')), None)
                
                if video_data:
                    game_event = GameEvent(
                        game_id=game_id,
                        event_id=event_id,
                        event_type=self._determine_event_type(play_item.get('action_type', '')),
                        description=play_item.get('dsc', 'Unknown Event'),
                        period=play_item.get('p', 1),
                        clock=play_item.get('clk', '00:00'),
                        score=Score(
                            home=play_item.get('hpb', 0), 
                            away=play_item.get('vpb', 0), 
                            difference=play_item.get('hpb', 0) - play_item.get('vpb', 0)
                        ),
                    )
                    
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
                        },
                        game_event=game_event  # 关联 GameEvent
                    )
                    
                    key = (game_id, event_id)
                    self.video_assets[key] = video_asset
                    event_video_map[event_id] = video_asset
                else:
                    self.logger.warning(f"No video data found for event_id: {event_id}")
                    
        except Exception as e:
            self.logger.error(f"Error processing video response: {e}")
            
        return event_video_map

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


