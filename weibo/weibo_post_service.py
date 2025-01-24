# weibo/weibo_post_service.py

import logging
import time
import random
from typing import List, Dict, Optional
from pathlib import Path
from nba.services.nba_service import NBAService
from weibo.weibo_publisher import WeiboPublisher
from weibo.weibo_model import WeiboPost, WeiboResponse


class NBAWeiboService:
    """NBA微博发布服务"""

    def __init__(self, nba_service: NBAService):
        """
        初始化NBA微博服务

        Args:
            nba_service: NBA数据服务实例
        """
        self.nba = nba_service
        self.weibo = WeiboPublisher()
        self.logger = logging.getLogger(__name__)

        # 在初始化时获取比赛数据
        self.game_info = self.nba.get_game_summary()
        self.game_statistics = self.nba.get_player_statistics()
        self.game_highlights = self.nba.get_game_highlights()
        self.videos = self.nba.get_game_videos(context_measure="FGM")

    def publish_game_summary(self) -> WeiboResponse:
        """
        发布比赛概况

        Returns:
            WeiboResponse: 发布响应结果
        """
        try:
            if not self.game_info:
                return WeiboResponse(False, "获取比赛信息失败")

            text = self.nba._ai_service.generate_weibo_post(
                self.nba.format_game_content(content_type="brief"),
                post_type="game_summary"
            )

            post = WeiboPost(text=text)
            success = self.weibo.publish(post)

            return WeiboResponse(success, "发布成功" if success else "发布失败")

        except Exception as e:
            self.logger.error(f"发布比赛概况失败: {e}")
            return WeiboResponse(False, str(e))

    def publish_player_stats_with_chart(self, player_name: str = None) -> WeiboResponse:
        """
        发布球员数据统计和图表

        Args:
            player_name: 球员名称，为空时获取默认球员

        Returns:
            WeiboResponse: 发布响应结果
        """
        try:
            if not self.game_statistics:
                return WeiboResponse(False, "获取球员统计失败")

            chart_path = self.nba.plot_player_scoring_impact()
            if not chart_path:
                return WeiboResponse(False, "生成图表失败")

            text = self.nba._ai_service.generate_weibo_post(
                self.game_statistics,
                post_type="player_highlight"
            )

            post = WeiboPost(text=text, images=[str(chart_path)])
            success = self.weibo.publish(post)

            return WeiboResponse(success, "发布成功" if success else "发布失败")

        except Exception as e:
            self.logger.error(f"发布球员统计失败: {e}")
            return WeiboResponse(False, str(e))

    def publish_shot_events_series(self, min_interval: int = 5, max_interval: int = 10) -> List[WeiboResponse]:
        """
        连续发布投篮事件系列

        Args:
            min_interval: 最小发布间隔（秒）
            max_interval: 最大发布间隔（秒）

        Returns:
            List[WeiboResponse]: 所有发布结果列表
        """
        responses = []
        try:
            self.logger.info("开始处理比赛视频...")
            if not self.videos:
                return [WeiboResponse(False, "获取投篮视频失败")]

            for event_id, video_path in self.videos.items():
                try:
                    if not self.game_highlights:
                        responses.append(WeiboResponse(False, f"Event {event_id} 获取亮点失败"))
                        continue

                    text = self.nba._ai_service.generate_weibo_post(
                        self.game_highlights,
                        post_type="shot_event"
                    )

                    if not Path(video_path).exists():
                        self.logger.error(f"视频文件不存在: {video_path}")
                        continue

                    post = WeiboPost(text=text, images=[str(video_path)])
                    success = self.weibo.publish(post)

                    response = WeiboResponse(
                        success,
                        f"Event {event_id} " + ("发布成功" if success else "发布失败")
                    )
                    responses.append(response)
                    self.logger.info(f"事件 {event_id} 发布结果: {response.message}")

                    if success:
                        # 随机延迟
                        sleep_time = random.uniform(min_interval, max_interval)
                        self.logger.info(f"等待 {sleep_time:.1f} 秒后继续...")
                        time.sleep(sleep_time)

                except Exception as e:
                    self.logger.error(f"处理事件 {event_id} 时出错: {e}")
                    responses.append(
                        WeiboResponse(False, f"Event {event_id} 处理失败: {str(e)}")
                    )

                # 固定延迟2秒，防止频率限制
                time.sleep(2)

            return responses

        except Exception as e:
            self.logger.error(f"连续发布投篮事件失败: {e}")
            return [WeiboResponse(False, str(e))]

    def publish_shot_events_summary(self) -> WeiboResponse:
        """
        发布投篮事件总结

        Returns:
            WeiboResponse: 发布响应结果
        """
        try:
            if not self.videos:
                return WeiboResponse(False, "获取投篮视频失败")

            events = []
            video_paths = []
            for event_id, video_path in self.videos.items():
                if self.game_highlights:
                    events.append(self.game_highlights)
                    video_paths.append(str(video_path))

            summary = self.nba._ai_service.generate_shots_summary(events)
            text = self.nba._ai_service.generate_weibo_post(
                summary,
                post_type="shot_summary"
            )

            # 最多发送9张图片/视频
            post = WeiboPost(text=text, images=video_paths[:9])
            success = self.weibo.publish(post)

            return WeiboResponse(success, "发布成功" if success else "发布失败")

        except Exception as e:
            self.logger.error(f"发布投篮总结失败: {e}")
            return WeiboResponse(False, str(e))

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        if hasattr(self, 'weibo'):
            del self.weibo