import logging
from typing import Optional, Dict, Any


from nba.models.video_model import VideoAsset, VideoQuality, VideoResponse


class VideoParser:
    """NBA视频资源解析器"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def parse_videos(self, response_data: Dict[str, Any]) -> Optional[VideoResponse]:
        """解析视频响应数据"""
        try:
            if not self._validate_response_data(response_data):
                return None

            resource = response_data.get('resource')
            parameters = response_data.get('parameters')
            result_sets = response_data.get('resultSets', {})

            video_urls = result_sets.get('Meta', {}).get('videoUrls', [])
            playlist = result_sets.get('playlist', [])

            # 创建播放列表索引
            playlist_index = {str(item['ei']): item for item in playlist}

            video_assets = {}

            for idx, video_info in enumerate(video_urls):
                if not self._validate_video_info(video_info):
                    continue

                event_id = str(playlist[idx]['ei']) if idx < len(playlist) else None
                if not event_id or event_id not in playlist_index:
                    continue

                video_asset = self._create_video_asset(event_id, video_info)
                if video_asset:
                    video_assets[event_id] = video_asset

            return VideoResponse(
                resource=resource,
                parameters=parameters,
                resultSets={'video_assets': video_assets, 'playlist': playlist_index}
            )

        except Exception as e:
            self.logger.error(f"解析视频数据失败: {e}", exc_info=True)
            return None

    def _validate_response_data(self, data: Dict[str, Any]) -> bool:
        """验证响应数据的完整性"""
        required_fields = ['resource', 'parameters', 'resultSets']
        return all(field in data for field in required_fields)

    def _validate_video_info(self, video_info: Dict[str, Any]) -> bool:
        """验证视频信息的完整性"""
        required_fields = ['uuid', 'sdur', 'surl', 'sth', 'ldur', 'lurl', 'lth']
        return all(field in video_info for field in required_fields)

    def _create_video_asset(self, event_id: str, video_data: Dict[str, Any]) -> Optional[VideoAsset]:
        """创建视频资产对象"""
        try:
            qualities = {
                'sd': VideoQuality(
                    duration=video_data['sdur'] / 1000,
                    url=video_data['surl'],
                    thumbnail=video_data['sth']
                ),
                'hd': VideoQuality(
                    duration=video_data['ldur'] / 1000,
                    url=video_data['lurl'],
                    thumbnail=video_data['lth']
                )
            }

            return VideoAsset(
                event_id=event_id,
                uuid=video_data['uuid'],
                qualities=qualities
            )

        except Exception as e:
            self.logger.error(f"创建视频资产失败: {e}", exc_info=True)
            return None