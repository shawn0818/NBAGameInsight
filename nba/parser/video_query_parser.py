import logging
from typing import Optional, Dict, Any
from config.nba_config import NBAConfig
from nba.fetcher.base import BaseNBAFetcher
from nba.parser.game_parser import GameDataParser
from datetime import datetime
from utils.http_handler import HTTPRequestManager, HTTPConfig  # 替换为实际的模块名
from nba.models.video_model import VideoAsset, VideoResponse, PlaylistItem,  VideoRequestParams

class NBAVideoProcessor(BaseNBAFetcher):
    """NBA视频资源处理器"""
    
    def __init__(self):
        """初始化视频处理器"""
        super().__init__()
        self.video_assets: Dict[str, VideoAsset] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_videos_by_query(self, query: VideoRequestParams) -> Dict[str, VideoAsset]:
        """根据查询参数获取视频"""
        try:
            # 构建API参数
            params = query.build()
            
            # 记录请求信息
            self.logger.info(f"Fetching videos for game {query.game_id}")
            
            # 使用 HTTPRequestManager 发送请求
            with HTTPRequestManager(
                headers=HTTPConfig.HEADERS,
                max_retries=HTTPConfig.MAX_RETRIES,
                timeout=HTTPConfig.TIMEOUT,
                backoff_factor=HTTPConfig.BACKOFF_FACTOR,
                retry_status_codes=HTTPConfig.RETRY_STATUS_CODES,
                fallback_urls=NBAConfig.API.FALLBACK_URLS  # 确保在 NBAConfig.API 中定义了 FALLBACK_URLS
            ) as http_manager:
                response_data = http_manager.make_request(
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
        """
        处理视频响应数据

        Args:
            game_id: 比赛ID
            response_data: API响应数据

        Returns:
            Dict[str, VideoAsset]: 事件ID到视频资产的映射
        """
        try:
            # 验证数据结构
            if not self._validate_response_data(response_data):
                return {}

            # 获取视频数据和播放列表
            video_urls = response_data.get('resultSets', {}).get('Meta', {}).get('videoUrls', [])
            playlist = response_data.get('resultSets', {}).get('playlist', [])
            
            self.logger.debug(f"Found {len(video_urls)} videos and {len(playlist)} playlist items")
            
            # 创建事件ID到播放列表项的映射
            playlist_map = {
                str(item.get('ei')): item 
                for item in playlist
            }

            # 处理每个视频资产
            event_video_map = {}
            for video_data in video_urls:
                try:
                    # 提取事件ID
                    event_id = self._extract_event_id(video_data.get('lurl', ''))
                    if not event_id:
                        continue
                        
                    # 获取关联的播放列表项
                    play_item = playlist_map.get(event_id)
                    if not play_item:
                        continue

                    # 创建视频资产
                    video_asset = self._create_video_asset(game_id, video_data, play_item)
                    if not video_asset:
                        continue

                    # 更新缓存和映射
                    key = f"{game_id}_{event_id}"
                    self.video_assets[key] = video_asset
                    event_video_map[event_id] = video_asset

                except Exception as e:
                    self.logger.error(f"Error processing video {video_data.get('uuid')}: {e}")
                    continue
                    
            self.logger.info(f"Successfully processed {len(event_video_map)} videos")
            return event_video_map
            
        except Exception as e:
            self.logger.error(f"Error processing video response: {e}")
            return {}

    def _validate_response_data(self, data: Dict[str, Any]) -> bool:
        """验证响应数据结构"""
        if not isinstance(data, dict):
            self.logger.error("Invalid response data type")
            return False
            
        if 'resultSets' not in data:
            self.logger.error("Missing resultSets in response")
            return False
            
        result_sets = data['resultSets']
        if not isinstance(result_sets, dict):
            self.logger.error("Invalid resultSets type")
            return False
            
        if 'Meta' not in result_sets or 'playlist' not in result_sets:
            self.logger.error("Missing Meta or playlist in resultSets")
            return False
            
        return True

    def get_video_by_game_event(self, game_id: str, event_id: str) -> Optional[VideoAsset]:
        """根据比赛ID和事件ID获取视频资产"""
        key = f"{game_id}_{event_id}"
        return self.video_assets.get(key)

    def clear_cache(self) -> None:
        """清除视频资产缓存"""
        self.video_assets.clear()
        self.logger.info("Video assets cache cleared")