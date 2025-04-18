from typing import Optional, Dict, Any, List
from nba.models.video_model import VideoAsset, VideoQuality, VideoResponse
from utils.logger_handler import AppLogger


class VideoParser:
    """NBA视频资源解析器

    支持解析两种端点的数据：
    1. videodetailsasset - 比赛视频集合
    2. videoeventsasset - 单个事件视频
    """

    def __init__(self):
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def parse_videos(self, response_data: Dict[str, Any], game_id: str = "") -> Optional[VideoResponse]:
        """解析视频响应数据 - 适用于videodetailsasset或videoeventsasset端点

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

            # 检测是哪种类型的响应
            is_event_response = 'GameEventID' in parameters

            # 记录数据来源类型
            source_type = "videoevents" if is_event_response else "videodetails"
            self.logger.info(f"解析{source_type}类型的视频数据 (game_id: {game_id})")

            video_urls = result_sets.get('Meta', {}).get('videoUrls', [])
            playlist = result_sets.get('playlist', [])

            if not video_urls:
                self.logger.warning(f"视频URL列表为空 (game_id: {game_id})")
                return VideoResponse(
                    resource=resource,
                    parameters=parameters,
                    resultSets={'video_assets': {}, 'playlist': {}}
                )

            # 根据不同端点类型处理视频资产
            if is_event_response:
                # videoeventsasset端点 - 通常只有一个视频
                video_assets = self._parse_video_events_to_asset(video_urls, parameters, game_id)
            else:
                # videodetailsasset端点 - 可能有多个视频
                video_assets = self._parse_video_details_to_asset(video_urls, playlist, game_id)

            # 创建播放列表索引
            playlist_index = {str(item['ei']): item for item in playlist} if playlist else {}

            # 记录解析结果
            valid_count = len(video_assets)
            self.logger.info(f"成功解析视频资产: {valid_count}个有效")

            return VideoResponse(
                resource=resource,
                parameters=parameters,
                resultSets={'video_assets': video_assets, 'playlist': playlist_index}
            )

        except Exception as e:
            self.logger.error(f"解析视频数据失败: {e}", exc_info=True)
            return None

    def _parse_video_events_to_asset(self, video_urls: List[Dict], parameters: Dict, game_id: str) -> Dict[str, VideoAsset]:
        """解析单个事件视频数据 (videoeventsasset端点)

        Args:
            video_urls: 视频URL列表
            parameters: 请求参数
            game_id: 比赛ID

        Returns:
            Dict[str, VideoAsset]: 以事件ID为键的视频资产字典
        """
        video_assets = {}
        event_id = str(parameters.get('GameEventID', 'unknown'))

        try:
            # 通常只有一个视频，但遍历以防有多个
            for idx, video_info in enumerate(video_urls):
                # 构建事件ID - 使用请求参数中的GameEventID
                asset_event_id = event_id

                # 创建视频资产
                video_asset = self._create_video_asset(asset_event_id, video_info)
                if video_asset:
                    video_assets[asset_event_id] = video_asset
                    self.logger.debug(f"解析事件视频成功: 事件ID {asset_event_id}")
                else:
                    self.logger.warning(f"无法创建事件视频: 事件ID {asset_event_id}")
        except Exception as e:
            self.logger.error(f"解析{game_id}单个事件视频时出错: {e}")

        return video_assets

    def _parse_video_details_to_asset(self, video_urls: List[Dict], playlist: List[Dict], game_id: str) -> Dict[
        str, VideoAsset]:
        """解析比赛视频集合数据 (videodetailsasset端点)

        Args:
            video_urls: 视频URL列表
            playlist: 播放列表数据
            game_id: 比赛ID

        Returns:
            Dict[str, VideoAsset]: 以事件ID为键的视频资产字典
        """
        video_assets = {}
        valid_count = 0
        invalid_count = 0

        # 创建播放列表索引用于快速查找
        playlist_index = {item.get('uuid', ''): item for item in playlist if 'uuid' in item}

        for idx, video_info in enumerate(video_urls):
            try:
                # 获取事件ID
                event_id = None

                # 1. 首先尝试从播放列表中匹配UUID
                uuid = video_info.get('uuid')
                if uuid and uuid in playlist_index:
                    event_id = str(playlist_index[uuid].get('ei', ''))

                # 2. 尝试通过索引位置匹配
                elif idx < len(playlist):
                    event_id = str(playlist[idx].get('ei', ''))

                # 3. 如果找不到匹配的事件ID，使用合成ID
                if not event_id:
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

        self.logger.debug(f"解析比赛视频: {valid_count}个有效, {invalid_count}个无效")
        return video_assets

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
            if self._has_valid_quality(video_data, 'sdur', 'surl', 'sth'):
                qualities['sd'] = VideoQuality(
                    duration=round(video_data['sdur'] / 1000.0, 3),  # 转换为秒，保留3位小数
                    url=video_data['surl'],
                    thumbnail=video_data['sth']
                )

            # 中等质量视频
            if self._has_valid_quality(video_data, 'mdur', 'murl', 'mth'):
                qualities['md'] = VideoQuality(
                    duration=round(video_data['mdur'] / 1000.0, 3),
                    url=video_data['murl'],
                    thumbnail=video_data['mth']
                )

            # 高清视频
            if self._has_valid_quality(video_data, 'ldur', 'lurl', 'lth'):
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

    @staticmethod
    def _has_valid_quality(video_data: Dict[str, Any], dur_key: str, url_key: str, thumb_key: str) -> bool:
        """检查视频数据是否包含有效的质量选项

        Args:
            video_data: 视频数据
            dur_key: 持续时间键
            url_key: URL键
            thumb_key: 缩略图键

        Returns:
            bool: 如果所有键都存在且值有效，则返回True
        """
        return (all(k in video_data for k in [dur_key, url_key, thumb_key]) and
                video_data[url_key] is not None and
                video_data[thumb_key] is not None)