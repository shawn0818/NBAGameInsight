from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import logging
from nba.models.game_model import (
    GameData, BaseEvent, Player,
    TwoPointEvent, ThreePointEvent, FreeThrowEvent
)
from utils.ai_processor import AIProcessor


@dataclass
class DisplayConfig:
    """显示配置类"""
    language: str = "zh_CN"
    cache_size: int = 128
    display_format: str = "json"  # text/json/markdown
    use_ai_translation: bool = True


class DisplayService:
    """比赛数据显示服务"""

    def __init__(
            self,
            display_config: DisplayConfig,
            ai_service: Optional[AIProcessor] = None
    ):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = display_config
        self.ai_service = ai_service
        self._translation_cache = {}

    def format_basic_game_info(self, game_data: GameData) -> Dict[str, Any]:
        """格式化基础比赛信息"""
        basic_info = {
            "game_id": game_data.gameId,
            "time": game_data.gameTimeLocal.strftime("%Y-%m-%d %H:%M"),
            "arena": {
                "name": game_data.arena.arenaName,
                "city": game_data.arena.arenaCity,
                "state": game_data.arena.arenaState,
            },
            "home_team": {
                "name": game_data.homeTeam.teamName,
                "score": game_data.homeTeam.score,
            },
            "away_team": {
                "name": game_data.awayTeam.teamName,
                "score": game_data.awayTeam.score,
            },
            "status": game_data.gameStatusText,
            "attendance": game_data.attendance,
        }

        if self.config.use_ai_translation and self.ai_service:
            try:
                # 尝试翻译关键信息
                for key in ["status"]:
                    if basic_info[key]:
                        translated = self.ai_service.translate(
                            basic_info[key], self.config.language
                        )
                        # 只有在翻译成功时才使用翻译结果
                        if translated and translated != "生成失败":
                            basic_info[key] = translated
            except Exception as e:
                self.logger.warning(f"翻译失败，使用原始英文: {e}")

        return basic_info

    def format_player_stats(self, player: Player) -> Dict[str, Any]:
        """格式化球员统计数据"""
        stats = player.statistics
        formatted_stats = {
            "name": player.name,
            "position": player.position,
            "minutes": stats.minutes,
            "points": stats.points,
            "shooting": {
                "field_goals": f"{stats.fieldGoalsMade}/{stats.fieldGoalsAttempted}",
                "field_goals_pct": f"{stats.fieldGoalsPercentage:.1%}" if stats.fieldGoalsPercentage else "-",
                "three_pointers": f"{stats.threePointersMade}/{stats.threePointersAttempted}",
                "three_pointers_pct": f"{stats.threePointersPercentage:.1%}" if stats.threePointersPercentage else "-",
                "free_throws": f"{stats.freeThrowsMade}/{stats.freeThrowsAttempted}",
                "free_throws_pct": f"{stats.freeThrowsPercentage:.1%}" if stats.freeThrowsPercentage else "-",
            },
            "rebounds": {
                "offensive": stats.reboundsOffensive,
                "defensive": stats.reboundsDefensive,
                "total": stats.reboundsTotal,
            },
            "other": {
                "assists": stats.assists,
                "steals": stats.steals,
                "blocks": stats.blocks,
                "turnovers": stats.turnovers,
                "fouls": stats.foulsPersonal,
            }
        }

        if self.config.use_ai_translation and self.ai_service:
            try:
                # 尝试翻译位置信息
                if formatted_stats["position"]:
                    translated = self.ai_service.translate(
                        formatted_stats["position"], self.config.language
                    )
                    # 只有在翻译成功时才使用翻译结果
                    if translated and translated != "生成失败":
                        formatted_stats["position"] = translated
            except Exception as e:
                self.logger.warning(f"翻译失败，使用原始英文: {e}")

        return formatted_stats

    def format_team_stats(self, game_data: GameData, team_type: str = "home") -> Dict[str, Any]:
        """格式化球队统计数据"""
        team = game_data.homeTeam if team_type == "home" else game_data.awayTeam

        formatted_stats = {
            "team_name": team.teamName,
            "score": team.score,
            "periods": [{"period": p.period, "score": p.score} for p in team.periods],
            "shooting": {
                "field_goals": f"{team.fieldGoalsMade}/{team.fieldGoalsAttempted}",
                "field_goals_pct": f"{team.fieldGoalsPercentage:.1%}",
            },
            "timeouts_remaining": team.timeoutsRemaining,
            "players": [
                self.format_player_stats(player)
                for player in team.players if player.has_played
            ]
        }
        return formatted_stats

    def analyze_game_events(self, events: List[BaseEvent]) -> Dict[str, Any]:
        """分析比赛事件
        只保留核心比赛事件用于AI分析
        """
        # 1. 定义核心事件类型
        core_event_types = {
            "2pt", "3pt", "freethrow",  # 得分事件
            "rebound", "assist",  # 进攻相关
            "block", "steal",  # 防守事件
            "turnover", "foul"  # 失误和犯规
        }

        # 过滤只保留核心事件
        filtered_events = [
            event for event in events
            if event.actionType in core_event_types
        ]

        # 2. 按节分组核心事件
        events_by_period = {}
        for event in filtered_events:
            if event.period not in events_by_period:
                events_by_period[event.period] = []
            events_by_period[event.period].append({
                "time": event.clock,
                "action_type": event.actionType,
                "sub_type": event.subType if hasattr(event, 'subType') else None,
                "description": event.description,
                "team": event.teamTricode if hasattr(event, 'teamTricode') else None,
                "player": event.playerName if hasattr(event, 'playerName') else None,
                "score": f"{event.scoreHome}-{event.scoreAway}" if hasattr(event, 'scoreHome') else None,
                "x": event.x if hasattr(event, 'x') else None,
                "y": event.y if hasattr(event, 'y') else None
            })

        # 3. 统计各类核心事件数量
        event_counts = {}
        for event in filtered_events:
            event_type = event.actionType
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        # 4. 提取关键事件
        key_plays = []
        for event in filtered_events:
            # 得分事件
            if isinstance(event, (TwoPointEvent, ThreePointEvent, FreeThrowEvent)):
                if hasattr(event, 'shotResult') and event.shotResult == "Made":
                    key_plays.append({
                        "type": "score",
                        "period": event.period,
                        "time": event.clock,
                        "player": event.playerName,
                        "team": event.teamTricode,
                        "points": 3 if isinstance(event, ThreePointEvent) else (
                            2 if isinstance(event, TwoPointEvent) else 1),
                        "description": event.description,
                        "score": f"{event.scoreHome}-{event.scoreAway}" if hasattr(event, 'scoreHome') else None,
                    })
            # 末节的关键防守
            elif event.actionType in ["block", "steal"] and event.period >= 4:
                key_plays.append({
                    "type": event.actionType,
                    "period": event.period,
                    "time": event.clock,
                    "player": event.playerName,
                    "team": event.teamTricode,
                    "description": event.description
                })
            # 末节的关键助攻
            elif event.actionType == "assist" and event.period >= 4:
                key_plays.append({
                    "type": "assist",
                    "period": event.period,
                    "time": event.clock,
                    "player": event.playerName,
                    "team": event.teamTricode,
                    "description": event.description
                })

        # 5. 生成最终返回数据
        result = {
            "events_by_period": events_by_period,  # 完整事件记录
            "event_counts": event_counts,  # 事件统计
            "key_plays": key_plays,  # 关键球
            "event_timeline": [  # 完整时间线
                {
                    "period": event.period,
                    "time": event.clock,
                    "type": event.actionType,
                    "description": event.description,
                    "team": event.teamTricode if hasattr(event, 'teamTricode') else None,
                    "player": event.playerName if hasattr(event, 'playerName') else None,
                    "score": f"{event.scoreHome}-{event.scoreAway}" if hasattr(event, 'scoreHome') else None
                }
                for event in filtered_events
            ]
        }


        # 6. 如果有AI服务，添加AI分析
        if self.ai_service:
            try:
                ai_result = self.ai_service.generate_summary(
                    str(result),
                    max_length=800
                )
                # 只有在AI分析成功时才添加分析结果
                if ai_result and ai_result != "生成失败":
                    result["ai_analysis"] = ai_result
                else:
                    self.logger.warning("AI分析失败，将只展示原始数据")
            except Exception as e:
                self.logger.warning(f"AI分析失败，使用原始数据: {e}")

        return result

    def display_game_info(self, game_data: GameData, events: Optional[List[BaseEvent]] = None) -> Dict[str, Any]:
        """显示完整比赛信息"""
        game_info = {
            "basic_info": self.format_basic_game_info(game_data),
            "home_team": self.format_team_stats(game_data, "home"),
            "away_team": self.format_team_stats(game_data, "away"),
        }

        if events:
            game_info["events_analysis"] = self.analyze_game_events(events)

        return game_info

    def clear_cache(self) -> None:
        """清理缓存"""
        self._translation_cache.clear()