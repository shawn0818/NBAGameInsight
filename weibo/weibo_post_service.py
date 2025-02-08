# weibo/weibo_post_service.py
import logging
import time
from typing import Optional, List, Dict, Any
from pathlib import Path
from nba.services.nba_service import NBAService
from weibo.weibo_publisher import WeiboPublisher
from weibo.weibo_model import WeiboPost, WeiboResponse


class NBAWeiboService:
    def __init__(self, nba_service: NBAService):
        self.nba = nba_service
        self.weibo = WeiboPublisher()
        self.logger = logging.getLogger(__name__)

    def is_ready(self) -> bool:
        """检查服务是否准备就绪"""
        return hasattr(self, 'nba') and hasattr(self, 'weibo')

    def publish_game_analysis(self, content: Dict[str, Any], with_video: bool = False) -> WeiboResponse:
        """发布比赛分析
        Args:
            content: 预先准备好的内容
            with_video: 是否包含视频集锦
        """
        try:
            text = content.get("analysis") or self._format_game_analysis(content["game_info"])

            images = []
            if with_video and content.get("videos"):
                if "gifs" in content["videos"]:
                    gifs = list(content["videos"]["gifs"].values())[:4]
                    if gifs:
                        images.extend(gifs)
                        highlight_text = self._format_game_highlights(content["game_info"])
                        if highlight_text:
                            text = f"{text}\n\n{highlight_text}"

            post = WeiboPost(text=text, images=images)
            success = self.weibo.publish(post)

            return WeiboResponse(
                success=success,
                message="发布成功" if success else "发布失败"
            )

        except Exception as e:
            self.logger.error(f"发布比赛分析失败: {e}")
            return WeiboResponse(False, str(e))

    def _format_game_analysis(self, game_info: Dict) -> str:
        """格式化比赛分析文本，重点关注比赛进程分析"""
        try:
            basic_info = game_info.get("basic_info", {})
            events_analysis = game_info.get("events_analysis", {})

            # 1. 基础信息
            text = (f"{basic_info['home_team']['name']} VS {basic_info['away_team']['name']}\n"
                    f"比分：{basic_info['home_team']['score']}-{basic_info['away_team']['score']}\n\n")

            # 2. AI 分析赛程
            events_by_period = events_analysis.get("events_by_period", {})
            ai_analysis = events_analysis.get("ai_analysis")

            if ai_analysis:
                text += f"{ai_analysis}\n\n"

            # 3. 关键转折点
            key_plays = events_analysis.get("key_plays", [])
            if key_plays:
                text += "【比赛转折点】\n"
                prev_score_diff = 0
                for play in key_plays:
                    if play.get('score'):
                        home_score, away_score = map(int, play['score'].split('-'))
                        score_diff = home_score - away_score
                        # 分差变化超过5分或最后2分钟的关键球
                        if (abs(score_diff - prev_score_diff) >= 5 or
                                (play['period'] >= 4 and play['time'] <= "02:00")):
                            text += (f"• {play['period']}节 {play['time']} "
                                     f"{play['description']} [{play['score']}]\n")
                            prev_score_diff = score_diff

            # 4. 末节关键时刻分析
            event_timeline = events_analysis.get("event_timeline", [])
            if event_timeline:
                last_period_events = [
                    e for e in event_timeline
                    if e['period'] == max(e['period'] for e in event_timeline)
                       and e['time'] <= "05:00"  # 只关注最后5分钟
                ]

                if last_period_events:
                    text += "\n【末节关键进程】\n"
                    for event in last_period_events:
                        if event.get('score'):  # 只关注涉及得分的事件
                            text += (f"{event['time']} {event['description']} "
                                     f"[{event['score']}]\n")

            return text.strip()
        except Exception as e:
            self.logger.error(f"格式化比赛分析失败: {e}")
            return "比赛分析生成失败"

    def _format_game_highlights(self, game_info: Dict) -> str:
        """格式化比赛集锦文本，突出精彩进程"""
        try:
            events_analysis = game_info.get("events_analysis", {})
            key_plays = events_analysis.get("key_plays", [])

            text = "【精彩时刻】\n"
            if key_plays:
                # 按得分影响力和时间节点筛选关键进球
                significant_plays = [
                    play for play in key_plays
                    if ((play['type'] == 'score' and play.get('points', 0) >= 3) or  # 三分球
                        (play['type'] in ['block', 'steal'] and play['period'] >= 4) or  # 末节关键防守
                        (play['type'] == 'assist' and play['period'] >= 4))  # 末节关键助攻
                ]

                for play in significant_plays[:4]:  # 限制展示4个，与GIF数量对应
                    text += (f"[{play['period']}节 {play['time']}] "
                             f"{play['description']}")
                    if play.get('score'):
                        text += f" [{play['score']}]"
                    text += "\n"

            return text.strip()
        except Exception as e:
            self.logger.error(f"格式化比赛集锦失败: {e}")
            return "比赛集锦生成失败"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'weibo'):
            del self.weibo