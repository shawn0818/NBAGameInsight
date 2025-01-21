"""
game_display_service.py
比赛数据显示服务，负责格式化和展示比赛相关的各类信息
"""

from typing import Optional, List
from dataclasses import dataclass
import logging
from functools import lru_cache
import hashlib

from nba.services.ai_service import AIService
from nba.services.game_data_service import NBAGameDataProvider
from nba.models.game_model import GameData, PlayerStatistics, TeamStats, BaseEvent


@dataclass
class DisplayConfig:
    """显示配置类"""
    language: str = "zh_CN"
    show_advanced_stats: bool = True
    cache_size: int = 128
    use_ai: bool = False


class DisplayService:
    """比赛数据显示服务"""

    def __init__(
            self,
            game_data_service: NBAGameDataProvider,
            display_config: DisplayConfig,
            ai_service: Optional[AIService] = None
    ):
        """初始化显示服务

        Args:
            game_data_service: 数据服务实例
            display_config: 显示配置
            ai_service: AI服务实例(可选)
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.game_data_service = game_data_service
        self.display_config = display_config
        self.ai_service = ai_service
        self._translation_cache = {}

    @lru_cache(maxsize=128)
    def _get_translation(self, text: str, target_language: str) -> str:
        """获取或缓存翻译结果

        Args:
            text: 待翻译文本
            target_language: 目标语言

        Returns:
            翻译后的文本
        """
        if not self.ai_service:
            return text

        cache_key = hashlib.md5(f"{text}:{target_language}".encode()).hexdigest()
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]

        translated = self.ai_service.translate(text=text, target_language=target_language)
        self._translation_cache[cache_key] = translated
        return translated

    def format_game_basic_info(self, game_data: GameData) -> Optional[str]:
        """格式化比赛基本信息"""
        try:
            if not game_data:
                self.logger.warning("无比赛信息")
                return None

            # 添加安全的属性访问
            info_items = []

            if hasattr(game_data, 'gameId'):
                info_items.append(f"比赛编号: {game_data.gameId}")

            if hasattr(game_data, 'gameTimeLocal'):
                formatted_time = game_data.gameTimeLocal.strftime("%Y-%m-%d %H:%M")
                info_items.append(f"比赛时间: {formatted_time}")

            if hasattr(game_data, 'arena'):
                arena = game_data.arena
                if hasattr(arena, 'arenaName') and hasattr(arena, 'arenaCity'):
                    info_items.append(f"比赛地点: {arena.arenaName}, {arena.arenaCity}")

            if hasattr(game_data, 'homeTeam') and hasattr(game_data, 'awayTeam'):
                info_items.append(f"主队: {game_data.homeTeam.teamName}")
                info_items.append(f"客队: {game_data.awayTeam.teamName}")

            if hasattr(game_data, 'gameStatusText'):
                info_items.append(f"比赛状态: {game_data.gameStatusText}")

            if hasattr(game_data, 'attendance'):
                info_items.append(f"观众人数: {game_data.attendance}")

            if not info_items:
                return None

            return self._get_translation(
                "\n".join(info_items),
                self.display_config.language
            )
        except Exception as e:
            self.logger.error(f"格式化比赛信息时出错: {str(e)}", exc_info=True)
            return None

    def format_player_stats(self, stats: PlayerStatistics) -> Optional[str]:
        """格式化球员统计数据
        
        Args:
            stats: PlayerStatistics对象
            
        Returns:
            格式化的球员统计文本
        """
        try:
            basic_items = [
                f"上场时间: {stats.minutes}",
                f"得分: {stats.points}",
                f"篮板: {stats.reboundsTotal}",
                f"助攻: {stats.assists}",
                f"抢断: {stats.steals}",
                f"盖帽: {stats.blocks}",
                f"失误: {stats.turnovers}"
            ]

            shooting_items = [
                f"投篮: {stats.fieldGoalsMade}/{stats.fieldGoalsAttempted}",
                f"三分: {stats.threePointersMade}/{stats.threePointersAttempted}"
            ]

            if self.display_config.show_advanced_stats:
                advanced_items = [
                    "",
                    "进阶数据:",
                    f"投篮命中率: {stats.fieldGoalsPercentage:.1f}%" if stats.fieldGoalsPercentage else "投篮命中率: N/A",
                    f"三分命中率: {stats.threePointersPercentage:.1f}%" if stats.threePointersPercentage else "三分命中率: N/A"
                ]
            else:
                advanced_items = []

            all_items = basic_items + shooting_items + advanced_items
            return self._get_translation(
                "\n".join(all_items),
                self.display_config.language
            )
        except Exception as e:
            self.logger.error(f"格式化球员统计时出错: {str(e)}")
            return None

    def format_game_status(self, home_team: TeamStats, away_team: TeamStats) -> Optional[str]:
        """格式化比赛状态
        
        Args:
            home_team: 主队 TeamStats对象
            away_team: 客队 TeamStats对象
            
        Returns:
            格式化的比赛状态文本
        """
        try:
            status_items = [
                f"当前比分: {home_team.score} - {away_team.score}",
                "",
                f"主队 {home_team.teamName}:",
                f"本节得分: {home_team.periods[-1].score if home_team.periods else 0}",
                "",
                f"客队 {away_team.teamName}:",
                f"本节得分: {away_team.periods[-1].score if away_team.periods else 0}"
            ]

            return self._get_translation(
                "\n".join(status_items),
                self.display_config.language
            )
        except Exception as e:
            self.logger.error(f"格式化比赛状态时出错: {str(e)}")
            return None

    def format_event(self, event: BaseEvent) -> Optional[str]:
        """格式化比赛事件
        
        Args:
            event: BaseEvent对象
            
        Returns:
            格式化的事件描述
        """
        try:
            event_time = f"{event.period}节 {event.clock}"
            event_text = f"[{event_time}] {event.description}"
            
            return self._get_translation(
                event_text,
                self.display_config.language
            )
        except Exception as e:
            self.logger.error(f"处理比赛事件时出错: {str(e)}")
            return None

    def generate_game_summary(self, events: List[BaseEvent]) -> str:
        """生成比赛总结
        
        Args:
            events: 比赛事件列表
            
        Returns:
            比赛总结文本
        """
        try:
            if not self.ai_service:
                return f"比赛共有 {len(events)} 个事件"
            
            # 将事件转换为文本
            events_text = "\n".join([
                f"- [{e.period}节 {e.clock}] {e.description}"
                for e in events
            ])
            
            return self.ai_service.generate_summary(
                content=events_text,
                context="这是一场NBA比赛的事件记录",
                max_length=200
            )
        except Exception as e:
            self.logger.error(f"生成比赛总结时出错: {str(e)}")
            return "无法生成比赛总结"

    def clear_cache(self) -> None:
        """清理缓存数据"""
        try:
            self._translation_cache.clear()
            self._get_translation.cache_clear()
            self.logger.info("显示服务缓存已清理")
        except Exception as e:
            self.logger.warning(f"清理缓存时出错: {str(e)}")