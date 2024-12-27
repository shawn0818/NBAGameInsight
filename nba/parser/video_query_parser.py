import logging
from typing import Optional, Dict, Any
import re
from config.nba_config import NBAConfig
from utils.http_handler import HTTPRequestManager, HTTPConfig
from nba.models.video_model import (
    VideoAsset,
    VideoRequestParams,
    VideoQuality,
)


class NBAVideoProcessor:
    """NBA视频资源处理器"""

    def __init__(self):
        """初始化视频处理器"""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.video_assets: Dict[str, VideoAsset] = {}

    def get_videos_by_query(self, query: VideoRequestParams) -> Dict[str, VideoAsset]:
        """
        获取视频查询结果

        - query: 包含 game_id, player_id, team_id, context_measure 等参数
        - return: 以 event_id 作为 key, VideoAsset 作为 value 的字典
        """
        try:
            self.logger.info(f"Fetching videos for game {query.game_id}")

            # 构建API参数
            params = query.build()

            # 使用 HTTPRequestManager 发送请求
            with HTTPRequestManager(
                headers=HTTPConfig.HEADERS,
                max_retries=HTTPConfig.MAX_RETRIES,
                timeout=HTTPConfig.TIMEOUT
            ) as http_manager:
                response_data = http_manager.make_request(
                    url=NBAConfig.URLS.VIDEO_DATA,
                    method='GET',
                    params=params
                )

                if response_data:
                    video_assets = self.process_video_response(response_data)
                    self.logger.info(f"Successfully processed {len(video_assets)} videos")
                    return video_assets

            self.logger.warning("No response data received from API")
            return {}

        except Exception as e:
            self.logger.error(f"Failed to get videos by query: {e}", exc_info=True)
            return {}

    def process_video_response(self, response_data: Dict[str, Any]) -> Dict[str, VideoAsset]:
        """
        处理视频响应数据 - 只关注视频资源

        - response_data: 来自 NBA API 的完整 JSON 响应
        - return: dict[event_id, VideoAsset]
        """
        try:
            if not isinstance(response_data, dict):
                return {}

            # 解析出所有 videoUrls
            video_urls = response_data \
                .get('resultSets', {}) \
                .get('Meta', {}) \
                .get('videoUrls', [])

            video_assets = {}

            for video_data in video_urls:
                try:
                    # 根据 lurl 等字段解析出 event_id
                    event_id = self._extract_event_id(video_data.get('lurl', ''))
                    if not event_id:
                        # 如果取不到 event_id，就跳过
                        continue

                    video_asset = self._create_video_asset(event_id, video_data)
                    if video_asset:
                        # 以 event_id 作为 key，存储到字典中
                        video_assets[event_id] = video_asset
                        self.logger.debug(f"Processed video for event {event_id}")

                except Exception as e:
                    self.logger.error(f"Error processing video {video_data.get('uuid')}: {e}")
                    continue

            return video_assets

        except Exception as e:
            self.logger.error(f"Error processing video response: {e}", exc_info=True)
            return {}

    def _extract_event_id(self, video_url: str) -> Optional[str]:
        """从视频URL中提取事件ID (如 /2024/12/25/0022400408/14/xxx ) 中的'14'"""
        if not video_url:
            return None

        # 这里的正则需要根据实际url格式进行调整
        match = re.search(r'/\d{4}/\d{2}/\d{2}/\d+/(\d+)/', video_url)
        if match:
            return match.group(1)
        return None

    def _create_video_asset(self, event_id: str, video_data: Dict[str, Any]) -> Optional[VideoAsset]:
        """
        创建简化的视频资产, 去除字幕逻辑, 仅保留清晰度信息
        """
        try:
            qualities = {
                'sd': VideoQuality(
                    duration=video_data['sdur'],
                    url=video_data['surl'],
                    thumbnail=video_data['sth']
                ),
                'hd': VideoQuality(
                    duration=video_data['ldur'],
                    url=video_data['lurl'],
                    thumbnail=video_data['lth']
                )
            }

            return VideoAsset(
                event_id=event_id,
                uuid=video_data['uuid'],
                qualities=qualities
            )

        except KeyError as e:
            self.logger.error(f"Missing key in video_data: {e}, video_data={video_data}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to create video asset: {str(e)}", exc_info=True)
            return None

    def get_video_by_event_id(self, event_id: str) -> Optional[VideoAsset]:
        """通过 event_id 获取已缓存的视频资产（如果之前存到 self.video_assets 里）"""
        return self.video_assets.get(event_id)

    def clear_cache(self) -> None:
        """清除视频资产缓存"""
        self.video_assets.clear()
        self.logger.info("Video assets cache cleared")