from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod


from nba.models.game_model import Game, BaseEvent, TeamInGame, PlayerInGame
from utils.ai_processor import AIProcessor, AIConfig, AIProvider
from utils.logger_handler import AppLogger


class DisplayMode(Enum):
    """展示模式"""
    ORIGINAL = "original"  # 原始数据
    TRANSLATED = "translated"  # 翻译模式
    PROFESSIONAL = "professional"  # 专业分析
    SOCIAL = "social"  # 社交媒体


@dataclass
class DisplayConfig:
    """显示配置"""
    mode: DisplayMode = DisplayMode.ORIGINAL
    ai_config: Optional[AIConfig] = field(
        default_factory=lambda: AIConfig(
            provider=AIProvider.DEEPSEEK,
            enable_translation=False,  # 开启翻译功能
            enable_creation=False  # 默认不开启创作功能
        )
    )


class ContentFormatter(ABC):
    """内容格式化器基类"""

    def __init__(self, ai_processor: Optional[AIProcessor] = None):
        self.ai_processor = ai_processor
        self.logger = AppLogger.get_logger(__name__)

    @abstractmethod
    def format_game(self, game: Game) -> str:
        """生成比赛叙事"""
        pass

    @abstractmethod
    def format_team(self, team: TeamInGame, is_home: bool) -> str:
        """生成球队叙事"""
        pass

    @abstractmethod
    def format_player(self, player: PlayerInGame) -> str:
        """生成球员叙事"""
        pass

    def format_events(self, events: List[BaseEvent]) -> List[Dict[str, Any]]:
        """格式化事件列表"""
        formatted_events = []
        for event in events:
            formatted_event = self._format_single_event(event)
            if formatted_event:
                formatted_events.append(formatted_event)
        return formatted_events

    def _format_single_event(self, event: BaseEvent) -> Dict[str, Any]:
        """格式化单个事件

        Args:
            event: 比赛事件

        Returns:
            Dict[str, Any]: 格式化后的事件数据
        """
        try:
            return {
                "event_id": event.action_number,
                "clock": event.clock,
                "period": event.period,
                "action_type": event.action_type,
                "description": event.description,
                "team": event.team_tricode if hasattr(event, "team_tricode") else None,
                "player": event.player_name if hasattr(event, "player_name") else None,
                "score": (f"{event.score_home}-{event.score_away}"
                          if hasattr(event, "score_home") and hasattr(event, "score_away")
                          else None),
                "importance": self._calculate_event_importance(event)
            }
        except Exception as e:
            self.logger.error(f"格式化事件失败: {str(e)}")
            return {}

    def _calculate_event_importance(self, event: BaseEvent) -> int:
        """计算事件重要性（0-5）"""
        importance = 0

        # 根据事件类型判断重要性
        high_importance_types = {"shot", "3pt", "dunk", "block", "steal"}
        medium_importance_types = {"rebound", "assist", "foul"}

        event_type = event.action_type.lower()
        if any(type_str in event_type for type_str in high_importance_types):
            importance += 3
        elif any(type_str in event_type for type_str in medium_importance_types):
            importance += 2

        # 重要时刻（第四节或加时赛后半段）
        if event.period >= 4 and ":" in event.clock:
            minutes = int(event.clock.split(":")[0])
            if minutes <= 2:
                importance += 1

        # 比分接近
        if hasattr(event, "score_home") and hasattr(event, "score_away"):
            score_diff = abs(int(event.score_home) - int(event.score_away))
            if score_diff <= 5:
                importance += 1

        return min(importance, 5)

    def _format_percentage(self, made: int, attempted: int) -> str:
        """格式化百分比

        Args:
            made: 命中数
            attempted: 出手数

        Returns:
            str: 格式化的百分比字符串
        """
        if attempted == 0:
            return "0.0"
        return f"{(made / attempted * 100):.1f}"


class OriginalFormatter(ContentFormatter):
    """原始内容格式化器"""

    def format_game(self, game: Game) -> str:
        """生成比赛叙事"""
        game_data = game.game_data

        # 基本比赛信息
        utc_time = game_data.game_time_utc
        narrative = f"""
        On {utc_time.strftime('%Y-%m-%d')} at {utc_time.strftime('%H:%M')} UTC, 
        in {game_data.arena.arena_name} ({game_data.arena.arena_city}), 
        the {game_data.home_team.team_city} {game_data.home_team.team_name} hosted 
        the {game_data.away_team.team_city} {game_data.away_team.team_name}.
        """

        # 比赛状态叙事
        if game_data.game_status_text == "Final":
            home_score = int(game_data.home_team.score)
            away_score = int(game_data.away_team.score)
            winner = "home team" if home_score > away_score else "visiting team"
            narrative += f"""
            The game has ended with a final score of {home_score}-{away_score}, 
            with the {winner} securing the victory.
            """
        else:
            period_suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(game_data.period, 'th')
            narrative += f"""
            Currently in the {game_data.period}{period_suffix} period, 
            the score is {game_data.home_team.score}-{game_data.away_team.score}.
            """

        # 比赛数据概览
        home_stats = game_data.home_team.statistics
        away_stats = game_data.away_team.statistics

        narrative += f"""
        The home team's shooting performance: 
        {home_stats.field_goals_made}/{home_stats.field_goals_attempted} FG ({self._format_percentage(home_stats.field_goals_made, home_stats.field_goals_attempted)}%), 
        {home_stats.three_pointers_made}/{home_stats.three_pointers_attempted} 3PT ({self._format_percentage(home_stats.three_pointers_made, home_stats.three_pointers_attempted)}%), 
        {home_stats.free_throws_made}/{home_stats.free_throws_attempted} FT ({self._format_percentage(home_stats.free_throws_made, home_stats.free_throws_attempted)}%).

        The visiting team's shooting performance: 
        {away_stats.field_goals_made}/{away_stats.field_goals_attempted} FG ({self._format_percentage(away_stats.field_goals_made, away_stats.field_goals_attempted)}%), 
        {away_stats.three_pointers_made}/{away_stats.three_pointers_attempted} 3PT ({self._format_percentage(away_stats.three_pointers_made, away_stats.three_pointers_attempted)}%), 
        {away_stats.free_throws_made}/{away_stats.free_throws_attempted} FT ({self._format_percentage(away_stats.free_throws_made, away_stats.free_throws_attempted)}%).
        """

        return narrative.strip()

    def format_team(self, team: TeamInGame, is_home: bool) -> str:
        """生成球队叙事"""
        team_type = "home" if is_home else "visiting"
        stats = team.statistics

        narrative = f"""
        The {team_type} team {team.team_city} {team.team_name} performance breakdown:

        Shooting efficiency:
        Field Goals: {stats.field_goals_made}/{stats.field_goals_attempted} ({self._format_percentage(stats.field_goals_made, stats.field_goals_attempted)}%)
        Three Pointers: {stats.three_pointers_made}/{stats.three_pointers_attempted} ({self._format_percentage(stats.three_pointers_made, stats.three_pointers_attempted)}%)
        Free Throws: {stats.free_throws_made}/{stats.free_throws_attempted} ({self._format_percentage(stats.free_throws_made, stats.free_throws_attempted)}%)

        Ball control and defense:
        Rebounds: {int(stats.rebounds_total)} total ({int(stats.rebounds_offensive)} offensive, {int(stats.rebounds_defensive)} defensive)
        Assists: {int(stats.assists)}
        Steals: {int(stats.steals)}
        Blocks: {int(stats.blocks)}
        Turnovers: {int(stats.turnovers)}
        Personal Fouls: {int(stats.fouls_personal)}
        """

        return narrative.strip()

    def format_player(self, player: PlayerInGame) -> str:
        """生成球员叙事"""
        stats = player.statistics
        starter_status = "starter" if player.starter == "1" else "reserve"

        narrative = f"""
        {player.name} ({starter_status}) Performance Summary:

        Playing Time and Scoring:
        Minutes: {stats.minutes_calculated:.1f}
        Points: {int(stats.points)}
        Plus/Minus: {stats.plus_minus_points:+.1f}

        Shooting Breakdown:
        Field Goals: {stats.field_goals_made}/{stats.field_goals_attempted} ({self._format_percentage(stats.field_goals_made, stats.field_goals_attempted)}%)
        Three Pointers: {stats.three_pointers_made}/{stats.three_pointers_attempted} ({self._format_percentage(stats.three_pointers_made, stats.three_pointers_attempted)}%)
        Free Throws: {stats.free_throws_made}/{stats.free_throws_attempted} ({self._format_percentage(stats.free_throws_made, stats.free_throws_attempted)}%)

        Other Statistics:
        Rebounds: {int(stats.rebounds_total)} ({int(stats.rebounds_offensive)} OFF, {int(stats.rebounds_defensive)} DEF)
        Assists: {int(stats.assists)}
        Steals: {int(stats.steals)}
        Blocks: {int(stats.blocks)}
        Turnovers: {int(stats.turnovers)}
        Personal Fouls: {int(stats.fouls_personal)}
        """

        return narrative.strip()


class TranslatedFormatter(ContentFormatter):
    """翻译内容格式化器"""

    def format_game(self, game: Game) -> str:
        """翻译比赛叙事"""
        original = super().format_game(game)
        if not self.ai_processor:
            return original
        return self.ai_processor.translate(original)

    def format_team(self, team: TeamInGame, is_home: bool) -> str:
        """翻译球队叙事"""
        original = super().format_team(team, is_home)
        if not self.ai_processor:
            return original
        return self.ai_processor.translate(original)

    def format_player(self, player: PlayerInGame) -> str:
        """翻译球员叙事"""
        original = super().format_player(player)
        if not self.ai_processor:
            return original
        return self.ai_processor.translate(original)


class ProfessionalFormatter(ContentFormatter):
    """专业分析格式化器"""

    def format_game(self, game: Game) -> str:
        """生成比赛专业分析"""
        if not self.ai_processor:
            return super().format_game(game)
        game_narrative = super().format_game(game)
        return self.ai_processor.create_game_analysis({"narrative": game_narrative})

    def format_team(self, team: TeamInGame, is_home: bool) -> str:
        """生成球队专业分析"""
        if not self.ai_processor:
            return super().format_team(team, is_home)
        team_narrative = super().format_team(team, is_home)
        return self.ai_processor.create_game_analysis({"narrative": team_narrative})

    def format_player(self, player: PlayerInGame) -> str:
        """生成球员专业分析"""
        if not self.ai_processor:
            return super().format_player(player)
        player_narrative = super().format_player(player)
        return self.ai_processor.create_game_analysis({"narrative": player_narrative})


class SocialFormatter(ContentFormatter):
    """社交媒体格式化器"""

    def format_game(self, game: Game) -> str:
        """生成比赛社交媒体内容"""
        if not self.ai_processor:
            return super().format_game(game)
        game_narrative = super().format_game(game)
        return self.ai_processor.create_social_content({"narrative": game_narrative})

    def format_team(self, team: TeamInGame, is_home: bool) -> str:
        """生成球队社交媒体内容"""
        if not self.ai_processor:
            return super().format_team(team, is_home)
        team_narrative = super().format_team(team, is_home)
        return self.ai_processor.create_social_content({"narrative": team_narrative})

    def format_player(self, player: PlayerInGame) -> str:
        """生成球员社交媒体内容"""
        if not self.ai_processor:
            return super().format_player(player)
        player_narrative = super().format_player(player)
        return self.ai_processor.create_social_content({"narrative": player_narrative})


class GameDisplayService:
    """比赛数据展示服务"""

    def __init__(self, config: Optional[DisplayConfig] = None):
        """初始化显示服务

        Args:
            config: 显示配置，包含展示模式和AI配置（可选）
        """
        self.config = config or DisplayConfig()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        # 优先初始化基础功能
        self.formatter = OriginalFormatter(None)

        # 尝试初始化 AI 功能（如果配置了的话）
        if self.config.ai_config:
            try:
                self.ai_processor = AIProcessor(self.config.ai_config)
                self._init_formatter()  # 成功初始化 AI 后再设置对应的 formatter
                self.logger.info("AI 增强功能初始化成功")
            except Exception as e:
                self.logger.warning(f"AI 增强功能初始化失败: {e}, 将使用基础数据展示")
                self.ai_processor = None
                # 保持使用 OriginalFormatter

    def _init_formatter(self):
        """初始化对应的格式化器

        根据配置的展示模式和 AI 处理器状态选择合适的格式化器
        """
        formatters = {
            DisplayMode.ORIGINAL: OriginalFormatter,
            DisplayMode.TRANSLATED: TranslatedFormatter,
            DisplayMode.PROFESSIONAL: ProfessionalFormatter,
            DisplayMode.SOCIAL: SocialFormatter
        }

        formatter_class = formatters.get(self.config.mode, OriginalFormatter)
        self.formatter = formatter_class(self.ai_processor)

    def display_game(self, game: Game) -> Dict[str, Any]:
        """展示比赛数据

        Args:
            game: 比赛数据对象

        Returns:
            Dict[str, Any]: 格式化后的比赛数据，包含:
                - game_narrative: 比赛整体叙事
                - team_narratives: 球队表现叙事
                - player_narratives: 球员表现叙事
                - events: 比赛事件列表
        """
        try:
            # 生成比赛叙事
            game_narrative = self.formatter.format_game(game)

            # 生成球队叙事
            team_narratives = {
                "home": self.formatter.format_team(game.game_data.home_team, True),
                "away": self.formatter.format_team(game.game_data.away_team, False)
            }

            # 生成球员叙事
            player_narratives = {
                "home": [
                    self.formatter.format_player(player)
                    for player in game.game_data.home_team.players
                    if player.played == "1"  # 只包含上场球员
                ],
                "away": [
                    self.formatter.format_player(player)
                    for player in game.game_data.away_team.players
                    if player.played == "1"  # 只包含上场球员
                ]
            }

            # 格式化比赛事件
            events = []
            if game.play_by_play and game.play_by_play.actions:
                events = self.formatter.format_events(game.play_by_play.actions)

            return {
                "game_narrative": game_narrative,
                "team_narratives": team_narratives,
                "player_narratives": player_narratives,
                "events": events
            }

        except Exception as e:
            self.logger.error(f"展示比赛数据失败: {str(e)}")
            return {
                "game_narrative": "",
                "team_narratives": {"home": "", "away": ""},
                "player_narratives": {"home": [], "away": []},
                "events": []
            }

    def get_key_events(self, events: List[Dict[str, Any]], min_importance: int = 4) -> List[Dict[str, Any]]:
        """获取关键事件

        Args:
            events: 事件列表
            min_importance: 最小重要性级别，默认为4

        Returns:
            List[Dict[str, Any]]: 重要事件列表
        """
        return [
            event for event in events
            if event.get("importance", 0) >= min_importance
        ]

    def get_player_events(self, events: List[Dict[str, Any]], player_name: str) -> List[Dict[str, Any]]:
        """获取指定球员的事件

        Args:
            events: 事件列表
            player_name: 球员姓名

        Returns:
            List[Dict[str, Any]]: 球员相关事件列表
        """
        return [
            event for event in events
            if event.get("player") == player_name
        ]

    def get_team_events(self, events: List[Dict[str, Any]], team_code: str) -> List[Dict[str, Any]]:
        """获取指定球队的事件

        Args:
            events: 事件列表
            team_code: 球队代码

        Returns:
            List[Dict[str, Any]]: 球队相关事件列表
        """
        return [
            event for event in events
            if event.get("team") == team_code
        ]

    def get_period_events(self, events: List[Dict[str, Any]], period: int) -> List[Dict[str, Any]]:
        """获取指定节的事件

        Args:
            events: 事件列表
            period: 节数

        Returns:
            List[Dict[str, Any]]: 指定节的事件列表
        """
        return [
            event for event in events
            if event.get("period") == period
        ]