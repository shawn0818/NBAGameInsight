from typing import Optional, Dict, Any
from nba.models.video_model import VideoAsset, VideoQuality, VideoResponse
from utils.logger_handler import AppLogger


class VideoParser:
    """NBA视频资源解析器"""

    def __init__(self):
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def parse_videos(self, response_data: Dict[str, Any], game_id: str = "") -> Optional[VideoResponse]:
        """解析视频响应数据

        Args:
            response_data: 原始API响应数据
            game_id: 比赛ID，用于记录日志

        Returns:
            Optional[VideoResponse]: 解析后的视频响应对象，解析失败则返回None
        """
        try:
            if not self._validate_response_data(response_data):
                self.logger.warning(f"响应数据结构无效 (game_id: {game_id})")
                return None

            resource = response_data.get('resource')
            parameters = response_data.get('parameters')
            result_sets = response_data.get('resultSets', {})

            video_urls = result_sets.get('Meta', {}).get('videoUrls', [])
            playlist = result_sets.get('playlist', [])

            if not video_urls:
                self.logger.warning(f"视频URL列表为空 (game_id: {game_id})")
                return VideoResponse(
                    resource=resource,
                    parameters=parameters,
                    resultSets={'video_assets': {}, 'playlist': {}}
                )

            # 创建播放列表索引
            playlist_index = {str(item['ei']): item for item in playlist} if playlist else {}

            video_assets = {}
            valid_count = 0
            invalid_count = 0

            for idx, video_info in enumerate(video_urls):
                try:
                    # 获取事件ID
                    event_id = None
                    if idx < len(playlist):
                        event_id = str(playlist[idx]['ei'])
                    elif 'uuid' in video_info and playlist:
                        # 尝试通过UUID匹配
                        for item in playlist:
                            if 'uuid' in item and item.get('uuid') == video_info['uuid']:
                                event_id = str(item['ei'])
                                break

                    if not event_id:
                        # 如果找不到匹配的事件ID，使用合成ID
                        event_id = f"{game_id}_{idx}" if game_id else f"unknown_{idx}"

                    # 创建视频资产
                    video_asset = self._create_video_asset(event_id, video_info)
                    if video_asset:
                        video_assets[event_id] = video_asset
                        valid_count += 1
                    else:
                        invalid_count += 1
                except Exception as e:
                    self.logger.error(f"处理第{idx}个视频时出错: {e}")
                    invalid_count += 1

            self.logger.info(f"成功解析视频资产: {valid_count}个有效, {invalid_count}个无效")

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
        if not isinstance(data, dict):
            self.logger.error("响应数据不是字典类型")
            return False

        required_fields = ['resource', 'parameters', 'resultSets']
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            self.logger.error(f"响应数据缺少必要字段: {', '.join(missing_fields)}")
            return False

        # 验证resultSets包含Meta
        if 'Meta' not in data.get('resultSets', {}):
            self.logger.error("响应数据的resultSets缺少Meta字段")
            return False

        return True

    def _create_video_asset(self, event_id: str, video_data: Dict[str, Any]) -> Optional[VideoAsset]:
        """创建视频资产对象

        支持三种视频质量: sd (标准清晰度), md (中等清晰度), hd (高清)
        """
        try:
            if not 'uuid' in video_data:
                self.logger.warning(f"视频数据缺少uuid字段")
                return None

            qualities = {}

            # 标清视频
            if all(k in video_data for k in ['sdur', 'surl', 'sth']):
                qualities['sd'] = VideoQuality(
                    duration=round(video_data['sdur'] / 1000.0, 3),  # 转换为秒，保留3位小数
                    url=video_data['surl'],
                    thumbnail=video_data['sth']
                )

            # 中等质量视频
            if all(k in video_data for k in ['mdur', 'murl', 'mth']):
                qualities['md'] = VideoQuality(
                    duration=round(video_data['mdur'] / 1000.0, 3),
                    url=video_data['murl'],
                    thumbnail=video_data['mth']
                )

            # 高清视频
            if all(k in video_data for k in ['ldur', 'lurl', 'lth']):
                qualities['hd'] = VideoQuality(
                    duration=round(video_data['ldur'] / 1000.0, 3),
                    url=video_data['lurl'],
                    thumbnail=video_data['lth']
                )

            if not qualities:
                self.logger.warning(f"视频 {video_data.get('uuid', 'unknown')} 没有有效的质量选项")
                return None

            return VideoAsset(
                event_id=event_id,
                uuid=video_data['uuid'],
                qualities=qualities
            )

        except Exception as e:
            self.logger.error(f"创建视频资产失败: {e}", exc_info=True)
            return None