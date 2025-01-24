# weibo/weibo_post_service.py
import logging
import time
import random
from typing import Optional, List, Dict
from pathlib import Path
from nba.services.nba_service import NBAService
from weibo.weibo_publisher import WeiboPublisher
from weibo.weibo_model import WeiboPost, WeiboResponse

logger = logging.getLogger(__name__)


class NBAWeiboService:
    def __init__(self, nba_service: NBAService):
        self.nba = nba_service
        self.weibo = WeiboPublisher()
        self.logger = logging.getLogger(__name__)

    def publish_game_summary(self) -> WeiboResponse:
        try:
            game_info = self.nba.get_game_summary()
            if not game_info:
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

    def publish_player_stats_with_chart(self, player_name: Optional[str] = None) -> WeiboResponse:
        try:
            stats = self.nba.get_player_statistics(player_name=player_name)
            if not stats:
                return WeiboResponse(False, "获取球员统计失败")

            chart_path = self.nba.plot_player_scoring_impact()
            if not chart_path:
                return WeiboResponse(False, "生成图表失败")

            text = self.nba._ai_service.generate_weibo_post(
                stats,
                post_type="player_highlight"
            )
            post = WeiboPost(text=text, images=[str(chart_path)])
            success = self.weibo.publish(post)

            return WeiboResponse(success, "发布成功" if success else "发布失败")
        except Exception as e:
            self.logger.error(f"发布球员统计失败: {e}")
            return WeiboResponse(False, str(e))

    def publish_shot_events_series(self, min_interval: int = 5, max_interval: int = 10) -> List[WeiboResponse]:
        responses = []
        try:
            logger.info("开始获取比赛视频...")
            videos = self.nba.get_game_videos(context_measure="FGM")
            if not videos:
                return [WeiboResponse(False, "获取投篮视频失败")]

            for event_id, video_path in videos.items():
                try:
                    event = self.nba.get_game_highlights()
                    text = self.nba._ai_service.generate_weibo_post(
                        event,
                        post_type="shot_event"
                    )

                    if not Path(video_path).exists():
                        logger.error(f"视频文件不存在: {video_path}")
                        continue

                    post = WeiboPost(text=text, images=[str(video_path)])
                    success = self.weibo.publish(post)

                    response = WeiboResponse(success, f"Event {event_id} " + ("成功" if success else "失败"))
                    responses.append(response)
                    logger.info(f"事件 {event_id} 发布结果: {response.message}")

                    if success:
                        # 随机延迟5-10秒
                        sleep_time = random.uniform(min_interval, max_interval)
                        logger.info(f"等待 {sleep_time:.1f} 秒后继续...")
                        time.sleep(sleep_time)

                except Exception as e:
                    logger.error(f"处理事件 {event_id} 时出错: {e}")
                    responses.append(WeiboResponse(False, f"Event {event_id} 处理失败: {str(e)}"))

                # 每次发布后固定延迟2秒,防止触发频率限制
                time.sleep(2)

            return responses

        except Exception as e:
            logger.error(f"连续发布投篮事件失败: {e}")
            return [WeiboResponse(False, str(e))]

    def publish_shot_events_summary(self) -> WeiboResponse:
        try:
            videos = self.nba.get_game_videos(context_measure="FGM")
            if not videos:
                return WeiboResponse(False, "获取投篮视频失败")

            events = []
            video_paths = []
            for event_id, video_path in videos.items():
                event = self.nba.get_game_highlights()
                events.append(event)
                video_paths.append(str(video_path))

            summary = self.nba._ai_service.generate_shots_summary(events)
            text = self.nba._ai_service.generate_weibo_post(
                summary,
                post_type="shot_summary"
            )
            post = WeiboPost(text=text, images=video_paths[:9])
            success = self.weibo.publish(post)

            return WeiboResponse(success, "发布成功" if success else "发布失败")
        except Exception as e:
            logger.error(f"发布投篮总结失败: {e}")
            return WeiboResponse(False, str(e))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'weibo'):
            del self.weibo