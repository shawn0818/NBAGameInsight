from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import logging
from datetime import datetime
from utils.time_handler import TimeParser, BasketballGameTime
from nba.models.game_model import GameData, BaseEvent, TeamStats, Player, PlayerStatistics
from nba.services.ai_service import AIService


@dataclass
class DisplayConfig:
    """显示配置类"""
    language: str = "zh_CN"
    cache_size: int = 128
    use_ai: bool = False
    format_type: str = "translate"  #三种格式:"normal"(原始), "translate"(翻译), "summary"(总结)


class DisplayService:
    """比赛数据显示服务"""

    def __init__(
            self,
            display_config: DisplayConfig,
            ai_service: Optional[AIService] = None
    ):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.display_config = display_config
        self.ai_service = ai_service
        self._translation_cache = {}

    def format_game_basic_info(self, game_data: GameData) -> Optional[str]:
        """格式化比赛基本信息"""
        try:
            info_text = (
                f"📅 {game_data.gameTimeLocal.strftime('%Y-%m-%d %H:%M')}\n"
                f"🏀 {game_data.awayTeam.teamName} vs {game_data.homeTeam.teamName}\n"
                f"📍 {game_data.arena.arenaName}\n"
                f"📊 比分 {game_data.homeTeam.score}-{game_data.awayTeam.score}\n"
                f"👥 观众人数: {game_data.attendance:,}"
            )

            if self.display_config.format_type == "translate" and self.ai_service:
                return self.ai_service.translate(info_text, self.display_config.language)
            elif self.display_config.format_type == "summary" and self.ai_service:
                return self.ai_service.generate_summary(
                    content=info_text,
                    context="基础比赛信息",
                    max_length=100
                )
            return info_text

        except Exception as e:
            self.logger.error(f"格式化比赛信息失败: {str(e)}")
            return None

    def format_game_status(self, game_data: GameData) -> str:
        """格式化比赛状态"""
        try:
            status_text = (
                f"比赛状态: {game_data.gameStatusText}\n"
                f"主队得分: {game_data.homeTeam.score}\n"
                f"客队得分: {game_data.awayTeam.score}\n"
                f"当前节数: {game_data.period}\n"
                f"剩余时间: {game_data.gameClock}"
            )

            if self.display_config.format_type == "translate" and self.ai_service:
                return self.ai_service.translate(status_text, self.display_config.language)
            elif self.display_config.format_type == "summary" and self.ai_service:
                return self.ai_service.generate_summary(
                    content=status_text,
                    context="当前比赛状态",
                    max_length=50
                )
            return status_text

        except Exception as e:
            self.logger.error(f"格式化比赛状态失败: {str(e)}")
            return "格式化失败"

    def format_team_stats(self, home_team: TeamStats, away_team: TeamStats) -> str:
        """格式化球队统计数据"""
        try:
            stats_text = (
                f"球队统计数据对比:\n"
                f"{'指标':15} {'主队':>10} {'客队':>10}\n"
                f"{'得分':15} {home_team.score:>10} {away_team.score:>10}\n"
                f"{'投篮命中率':15} {home_team.statistics['fieldGoalsPercentage'] * 100:>10.1f}% "
                f"{away_team.statistics['fieldGoalsPercentage'] * 100:>10.1f}%\n"
                f"{'三分命中率':15} {home_team.statistics['threePointersPercentage'] * 100:>10.1f}% "
                f"{away_team.statistics['threePointersPercentage'] * 100:>10.1f}%\n"
                f"{'罚球命中率':15} {home_team.statistics['freeThrowsPercentage'] * 100:>10.1f}% "
                f"{away_team.statistics['freeThrowsPercentage'] * 100:>10.1f}%\n"
                f"{'篮板':15} {home_team.statistics['reboundsTotal']:>10} {away_team.statistics['reboundsTotal']:>10}\n"
                f"{'助攻':15} {home_team.statistics['assists']:>10} {away_team.statistics['assists']:>10}\n"
                f"{'抢断':15} {home_team.statistics['steals']:>10} {away_team.statistics['steals']:>10}\n"
                f"{'盖帽':15} {home_team.statistics['blocks']:>10} {away_team.statistics['blocks']:>10}\n"
                f"{'失误':15} {home_team.statistics['turnoversTotal']:>10} {away_team.statistics['turnoversTotal']:>10}"
            )

            if self.display_config.format_type == "translate" and self.ai_service:
                return self.ai_service.translate(stats_text, self.display_config.language)
            elif self.display_config.format_type == "summary" and self.ai_service:
                return self.ai_service.generate_summary(
                    content=stats_text,
                    context="球队数据对比",
                    max_length=150
                )
            return stats_text

        except Exception as e:
            self.logger.error(f"格式化球队统计失败: {str(e)}")
            return "格式化失败"

    def format_player_stats(self, player: Player, format_type: str = "normal") -> str:
        """格式化球员统计数据"""
        try:
            minutes = TimeParser.parse_iso8601_duration(player.statistics.minutes) // 60

            stats_text = (
                f"【{player.name}】\n"
                f"⌚️ {minutes}分钟\n"
                f"💫 {player.statistics.points}分 "
                f"{player.statistics.reboundsTotal}篮板 "
                f"{player.statistics.assists}助攻\n"
                f"🏀 投篮：{player.statistics.fieldGoalsMade}/{player.statistics.fieldGoalsAttempted} "
                f"三分：{player.statistics.threePointersMade}/{player.statistics.threePointersAttempted}\n"
                f"✨ 抢断：{player.statistics.steals} "
                f"盖帽：{player.statistics.blocks} "
                f"失误：{player.statistics.turnovers}"
            )

            if self.display_config.format_type == "translate" and self.ai_service:
                return self.ai_service.translate(stats_text, self.display_config.language)
            elif self.display_config.format_type == "summary" and self.ai_service:
                return self.ai_service.generate_summary(
                    content=stats_text,
                    context=f"{player.name}的比赛表现",
                    max_length=100
                )
            return stats_text

        except Exception as e:
            self.logger.error(f"格式化球员统计失败: {str(e)}")
            return "格式化失败"

    def format_game_timeline(self, game_data: GameData, events: List[BaseEvent]) -> str:
        """格式化完整比赛时间线"""
        try:
            if not events:
                return "暂无比赛事件"

            timeline_lines = []
            timeline_lines.append(f"🏀 {game_data.awayTeam.teamName} vs {game_data.homeTeam.teamName}\n")

            # 当前比分
            home_score = 0
            away_score = 0

            # 处理每个事件
            for event in events:
                try:
                    # 更新比分
                    if "made" in event.description.lower():
                        points = 3 if "3pt" in event.description.lower() else 2
                        if event.teamTricode == game_data.homeTeam.teamTricode:
                            home_score += points
                        else:
                            away_score += points
                    elif "free throw" in event.description.lower() and "made" in event.description.lower():
                        if event.teamTricode == game_data.homeTeam.teamTricode:
                            home_score += 1
                        else:
                            away_score += 1

                    # 格式化时间
                    actual_time = event.timeActual if event.timeActual else "N/A"  # 使用 timeActual 代替 gameTime
                    period_name = f"第{event.period}节" if event.period <= 4 else f"加时{event.period - 4}"
                    game_time = f"{period_name} {event.clock}"
                    score = f"{away_score}-{home_score}"

                    event_line = f"{actual_time} | {game_time:10} | {event.description:50} | {score}"
                    timeline_lines.append(event_line)

                except Exception as e:
                    self.logger.error(f"处理单个事件时出错: {str(e)}")
                    continue

            timeline_text = "\n".join(timeline_lines)

            if self.display_config.format_type == "translate" and self.ai_service:
                return self.ai_service.translate(timeline_text, self.display_config.language)
            elif self.display_config.format_type == "summary" and self.ai_service:
                return self.ai_service.generate_summary(
                    content=timeline_text,
                    context="比赛事件流程",
                    max_length=200
                )
            return timeline_text

        except Exception as e:
            self.logger.error(f"格式化比赛时间线失败: {str(e)}")
            return "格式化失败"

    def generate_game_report(self, game_data: GameData, events: Optional[List[BaseEvent]] = None) -> str:
        """生成完整比赛报告"""
        try:
            sections = [
                self.format_game_basic_info(game_data),
                self.format_game_status(game_data),
                self.format_team_stats(game_data.homeTeam, game_data.awayTeam),
                "\n关键球员表现:",
                *[self.format_player_stats(player)
                  for player in self._get_key_players(game_data)],
            ]

            # 仅当提供了events时才添加比赛事件部分
            if events:
                sections.extend([
                    "\n比赛事件:",
                    self.format_game_timeline(game_data, events)
                ])

            report = "\n\n".join(filter(None, sections))

            if self.display_config.format_type == "summary" and self.ai_service:
                return self.ai_service.generate_summary(
                    content=report,
                    context="完整比赛报告",
                    max_length=300
                )
            return report

        except Exception as e:
            self.logger.error(f"生成比赛报告失败: {str(e)}")
            return "生成报告失败"

    def _get_key_players(self, game_data: GameData) -> List[Player]:
        """获取关键球员(得分前三)"""
        all_players = game_data.homeTeam.players + game_data.awayTeam.players
        sorted_players = sorted(
            [p for p in all_players if p.statistics.points > 0],
            key=lambda x: x.statistics.points,
            reverse=True
        )
        return sorted_players[:3]

    def clear_cache(self) -> None:
        """清理缓存"""
        self._translation_cache.clear()