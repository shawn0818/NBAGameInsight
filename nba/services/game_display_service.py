from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from abc import ABC, abstractmethod

from utils.ai_processor import AIProcessor, AIConfig
from utils.logger_handler import AppLogger
from nba.models.game_model import Game, TeamInGame, PlayerInGame, BaseEvent, GameStatusEnum


class DisplayMode(Enum):
    """展示模式"""
    ORIGINAL = "original"  # 原始数据
    TRANSLATED = "translated"  # 翻译模式
    PROFESSIONAL = "professional"  # 专业分析
    SOCIAL = "social"  # 社交媒体


class DisplayConfig(BaseModel):
    """显示配置"""
    mode: DisplayMode = DisplayMode.ORIGINAL
    ai_config: Optional[AIConfig] = Field(default_factory=AIConfig)


class ContentFormatter(ABC):
    """内容格式化器基类"""

    def __init__(self, ai_processor: Optional[AIProcessor] = None, config: DisplayConfig = None):
        self.ai_processor = ai_processor
        self.config = config or DisplayConfig()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

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

    @abstractmethod
    def format_events(self, events: List[BaseEvent]) -> List[Dict[str, Any]]:
        """格式化事件列表"""
        pass

    def _process_narrative(self, original_narrative: str) -> str:
        """统一的叙事处理方法"""
        if self.config.mode == DisplayMode.TRANSLATED:
            return self._process_with_ai(original_narrative, "translate")
        elif self.config.mode == DisplayMode.PROFESSIONAL:
            return self._process_with_ai(original_narrative, "analyze")
        elif self.config.mode == DisplayMode.SOCIAL:
            return self._process_with_ai(original_narrative, "social")
        else:  # DisplayMode.ORIGINAL
            return original_narrative

    def _process_with_ai(self, original_text: str, ai_method: str) -> str:
        """AI 处理逻辑"""
        if not self.ai_processor:
            return original_text
        try:
            result = {
                "translate": lambda: self.ai_processor.translate(original_text),
                "analyze": lambda: self.ai_processor.create_game_analysis({"narrative": original_text}),
                "social": lambda: self.ai_processor.create_social_content({"narrative": original_text})
            }[ai_method]()
            return result if result and result.strip() else original_text
        except Exception as e:
            self.logger.error(f"{ai_method} processing failed: {str(e)}")
            return original_text


class GameFormatter(ContentFormatter):
    """比赛内容格式化器"""

    def format_game(self, game: Game) -> str:
        """生成比赛叙事"""
        original_narrative = self._format_original_game(game)
        return self._process_narrative(original_narrative)

    def format_team(self, team: TeamInGame, is_home: bool) -> str:
        """生成球队叙事"""
        original_narrative = self._format_original_team(team, is_home)
        return self._process_narrative(original_narrative)

    def format_player(self, player: PlayerInGame) -> str:
        """生成球员叙事"""
        original_narrative = self._format_original_player(player)
        return self._process_narrative(original_narrative)

    def format_events(self, events: List[BaseEvent]) -> List[str]: 
        """"格式化事件列表, 返回字符串列表"""
        event_narratives: List[str] = [] # Initialize as a list of strings

        for event in events:
            event_dict = event.model_dump() # Use model_dump() to convert BaseEvent to dictionary (for Pydantic V2+)
            formatted_narrative = self._format_original_single_event(event_dict) # Call _format_original_single_event with the dictionary
            event_narratives.append(formatted_narrative) # Append the formatted string to the list

        return event_narratives


    ##=================生成比赛信息原始叙事================

    def _format_original_game(self, game: Game) -> str:
        """生成比赛原始叙事 (根据比赛状态选择不同格式)"""
        game_status_enum = game.game_data.game_status

        if game_status_enum == GameStatusEnum.NOT_STARTED:
            return self._format_basic_game_info(game)  # 未开始，只显示基本信息
        elif game_status_enum == GameStatusEnum.IN_PROGRESS:
            basic_info = self._format_basic_game_info(game)
            status_info = self._format_game_status_info(game)
            return f"{basic_info} {status_info}"  # 进行中，显示基本信息 + 状态信息
        elif game_status_enum == GameStatusEnum.FINISHED:
            return self._format_game_summary_info(game)  # 已结束，显示总结信息
        else:
            # 默认情况，或者处理未知状态
            return self._format_basic_game_info(game)  # Fallback to basic info

    def _format_basic_game_info(self, game: Game) -> str:
        """生成比赛基本信息叙事 (时间, 地点, 球队)"""
        game_data = game.game_data
        narrative_parts = [
            f"On {game_data.game_time_utc.strftime('%Y-%m-%d')},",  # 简化日期格式
            f"at {game_data.game_time_utc.strftime('%H:%M')} UTC,",  # 简化时间格式
            f"in {game_data.arena.arena_name} ({game_data.arena.arena_city}),",
            f"{game_data.away_team.team_city} {game_data.away_team.team_name} vs",  # 调整为 "Team A vs Team B" 格式
            f"{game_data.home_team.team_city} {game_data.home_team.team_name}."
        ]
        return " ".join(narrative_parts).strip()

    def _format_game_status_info(self, game: Game) -> str:
        """生成比赛状态信息叙事 (节数, 时钟, 比分, 暂停)"""
        game_data = game.game_data
        game_status = game.get_game_status()  # 复用 Game 模型中已有的方法
        narrative_parts = [
            f"Status: {game_status['status_text']}.",
            f"Period: {game_status['period_name']} ({game_status['current_period']}).",  # 显示节数名称和数字
            f"Time Remaining: {game_status['time_remaining']}.",
            f"Score: {game_data.away_team.team_tricode} {game_status['away_score']} - {game_data.home_team.team_tricode} {game_status['home_score']}.",
            # 使用球队 Tricode 简化显示
            f"Timeouts Remaining: {game_data.away_team.team_tricode} {game_status['away_timeouts']}, {game_data.home_team.team_tricode} {game_status['home_timeouts']}."
        ]
        if game_status['home_bonus']:  # 添加 Bonus 状态信息
            narrative_parts.append(f"{game_data.home_team.team_tricode} is in bonus.")
        if game_status['away_bonus']:
            narrative_parts.append(f"{game_data.away_team.team_tricode} is in bonus.")

        return " ".join(narrative_parts).strip()

    def _format_game_summary_info(self, game: Game) -> str:
        """生成比赛总结信息叙事 (基本信息 + 最终比分)"""
        basic_info = self._format_basic_game_info(game)  # 复用基本信息格式化方法
        game_data = game.game_data
        home_score = int(game_data.home_team.score)
        away_score = int(game_data.away_team.score)
        winner = game_data.home_team.team_tricode if home_score > away_score else game_data.away_team.team_tricode  # 使用 Tricode
        loser = game_data.away_team.team_tricode if home_score > away_score else game_data.home_team.team_tricode  # 使用 Tricode

        summary_parts = [
            basic_info,
            f"Final Score: {winner} {max(home_score, away_score)} - {loser} {min(home_score, away_score)}.",  # 简化比分显示
            f"The {winner} secured the victory."
        ]
        return " ".join(summary_parts).strip()

    ##=================生成球队统计信息原始叙事================

    def _format_original_team(self, team: TeamInGame, is_home: bool) -> str:
        """生成球队原始叙事"""
        team_type = "Home" if is_home else "Visiting"
        stats = team.statistics

        narrative_parts = [
            f"**{team_type} Team: {team.team_city} {team.team_name} - Data Summary**\n",

            "**Time Statistics:**",
            f"-  **Minutes Played:** {stats.minutes_calculated:.2f} minutes",
            f"-  **Time Leading:** {stats.time_leading_calculated:.2f} minutes",

            "\n**Scoring and Efficiency:**",
            f"-  **Total Points:** {stats.points}",
            f"-  **Points Against:** {stats.points_against}",
            f"-  **Assists:** {stats.assists}",
            f"-  **Assists/Turnover Ratio:** {stats.assists_turnover_ratio:.2f}",
            f"-  **Bench Points:** {stats.bench_points}",

            "\n**Lead Statistics:**",
            f"-  **Biggest Lead:** {stats.biggest_lead}",
            f"-  **Biggest Lead Score:** {stats.biggest_lead_score}",
            f"-  **Biggest Scoring Run:** {stats.biggest_scoring_run}",
            f"-  **Biggest Scoring Run Score:** {stats.biggest_scoring_run_score}",
            f"-  **Lead Changes:** {stats.lead_changes}",

            "\n**Shooting Statistics:**",
            f"-  **Field Goals:** {stats.field_goals_made}/{stats.field_goals_attempted} ({stats.field_goals_percentage:.1%})",
            f"-  **Three Pointers:** {stats.three_pointers_made}/{stats.three_pointers_attempted} ({stats.three_pointers_percentage:.1%})",
            f"-  **Two Pointers:** {stats.two_pointers_made}/{stats.two_pointers_attempted} ({stats.two_pointers_percentage:.1%})",
            f"-  **Free Throws:** {stats.free_throws_made}/{stats.free_throws_attempted} ({stats.free_throws_percentage:.1%})",

            "\n**Paint Points:**",
            f"-  **Points in the Paint:** {stats.points_in_the_paint_made}/{stats.points_in_the_paint_attempted} ({stats.points_in_the_paint_percentage:.1%})",
            f"-  **Total Paint Points:** {stats.points_in_the_paint}",

            "\n**Fast Break Points:**",
            f"-  **Fast Break Points:** {stats.fast_break_points_made}/{stats.fast_break_points_attempted} ({stats.fast_break_points_percentage:.1%})",
            f"-  **Points Fast Break:** {stats.points_fast_break}",

            "\n**Second Chance Points:**",
            f"-  **Second Chance Points:** {stats.second_chance_points_made}/{stats.second_chance_points_attempted} ({stats.second_chance_points_percentage:.1%})",
            f"-  **Points Second Chance:** {stats.points_second_chance}",
            f"-  **Points from Turnovers:** {stats.points_from_turnovers}",

            "\n**Rebounds:**",
            f"-  **Total Rebounds:** {stats.rebounds_total}",
            f"-  **Offensive Rebounds:** {stats.rebounds_offensive}",
            f"-  **Defensive Rebounds:** {stats.rebounds_defensive}",
            f"-  **Team Rebounds:** {stats.rebounds_team}",
            f"-  **Team Offensive Rebounds:** {stats.rebounds_team_offensive}",
            f"-  **Team Defensive Rebounds:** {stats.rebounds_team_defensive}",
            f"-  **Personal Rebounds:** {stats.rebounds_personal}",

            "\n**Defense:**",
            f"-  **Blocks:** {stats.blocks}",
            f"-  **Blocks Received:** {stats.blocks_received}",
            f"-  **Steals:** {stats.steals}",

            "\n**Turnovers:**",
            f"-  **Turnovers:** {stats.turnovers}",
            f"-  **Team Turnovers:** {stats.turnovers_team}",
            f"-  **Total Turnovers:** {stats.turnovers_total}",

            "\n**Fouls:**",
            f"-  **Personal Fouls:** {stats.fouls_personal}",
            f"-  **Team Fouls:** {stats.fouls_team}",
            f"-  **Technical Fouls:** {stats.fouls_technical}",
            f"-  **Team Technical Fouls:** {stats.fouls_team_technical}",
            f"-  **Offensive Fouls:** {stats.fouls_offensive}",
            f"-  **Fouls Drawn:** {stats.fouls_drawn}"
        ]

        return "\n".join(narrative_parts).strip()

    ##=================生成球员统计信息原始叙事================

    def _format_original_player(self, player: PlayerInGame) -> str:
        """生成球员原始叙事 (更偏数据还原版 - 英文叙事风格)"""
        stats = player.statistics
        starter_status = "Starter" if player.starter == "1" else "Reserve"

        narrative_parts = [
            f"**Player Performance: {player.name} (#{player.jersey_num}, {player.position}) - Data Summary ({starter_status})**\n",

            "**Playing Time & Scoring:**",
            f"-  **Minutes Played:** {stats.minutes_calculated:.2f} minutes",
            f"-  **Points:** {stats.points}",
            f"-  **Plus/Minus:** {stats.plus_minus_points:+.1f}\n",

            "**Shooting Metrics:**",
            f"-  **Field Goals:** Made {stats.field_goals_made} of {stats.field_goals_attempted} (Percentage: {stats.field_goals_percentage:.1%})",
            f"-  **Three-Point Field Goals:** Made {stats.three_pointers_made} of {stats.three_pointers_attempted} (Percentage: {stats.three_pointers_percentage:.1%})",
            f"-  **Two-Point Field Goals:** Made {stats.two_pointers_made} of {stats.two_pointers_attempted} (Percentage: {stats.two_pointers_percentage:.1%})",
            f"-  **Free Throws:** Made {stats.free_throws_made} of {stats.free_throws_attempted} (Percentage: {stats.free_throws_percentage:.1%})\n",

            "**Rebounding Metrics:**",
            f"-  **Total Rebounds:** {stats.rebounds_total}",
            f"-  **Offensive Rebounds:** {stats.rebounds_offensive}",
            f"-  **Defensive Rebounds:** {stats.rebounds_defensive}\n",

            "**Assists & Ball Control:**",
            f"-  **Assists:** {stats.assists}",
            f"-  **Turnovers:** {stats.turnovers}\n",

            "**Defensive Metrics:**",
            f"-  **Steals:** {stats.steals}",
            f"-  **Blocks:** {stats.blocks}",
            f"-  **Blocks Received:** {stats.blocks_received}\n",

            "**Fouls:**",
            f"-  **Personal Fouls:** {stats.fouls_personal}",
            f"-  **Fouls Drawn:** {stats.fouls_drawn}",
            f"-  **Offensive Fouls:** {stats.fouls_offensive}",
            f"-  **Technical Fouls:** {stats.fouls_technical}\n",

            "**Points Breakdown:**",
            f"-  **Fast Break Points:** {stats.points_fast_break}",
            f"-  **Points in the Paint:** {stats.points_in_the_paint}",
            f"-  **Second Chance Points:** {stats.points_second_chance}"
        ]

        return "\n".join(narrative_parts).strip()

    ##=================生成比赛事件信息原始叙事================

    def _format_original_single_event(self, event: Dict[str, Any]) -> str:
        """生成单个事件原始叙述"""
        # 基础信息
        narrative_parts = [
            f"**Action Number:** {event['action_number']}",
            f"**Period:** {event['period']}",
            f"**Game Clock:** {event['clock']}",
            f"**Time:** {event['time_actual']}",
            f"**Action Type:** {event['action_type']}"
        ]

        # 球队信息
        if event.get('team_tricode'):
            narrative_parts.append(f"**Team:** {event['team_tricode']}")

        # 基础球员信息
        if event.get('player_name'):
            player_info = f"**Player:** {event['player_name']}"
            if event.get('player_name_i'):
                player_info += f" ({event['player_name_i']})"
            narrative_parts.append(player_info)

        # 比分信息
        if event.get('score_home') is not None and event.get('score_away') is not None:
            narrative_parts.append(f"**Score:** Home {event['score_home']} - Away {event['score_away']}")

        # 子类型（如果有）
        if event.get('sub_type'):
            narrative_parts.append(f"**Sub Type:** {event['sub_type']}")

        # 根据事件类型添加特定信息
        action_type = event['action_type']

        if action_type in ["2pt", "3pt"]:  # 投篮事件
            narrative_parts.extend([
                f"**Shot Result:** {event.get('shot_result')}",
                f"**Shot Distance:** {event.get('shot_distance')} ft",
                f"**Area:** {event.get('area')}",
                f"**Area Detail:** {event.get('area_detail', 'N/A')}"
            ])
            if event.get('assist_player_name_initial'):
                narrative_parts.append(f"**Assist By:** {event['assist_player_name_initial']}")
            if event.get('block_player_name'):
                narrative_parts.append(f"**Blocked By:** {event['block_player_name']}")
            if event.get('qualifiers'):
                narrative_parts.append(f"**Qualifiers:** {', '.join(event['qualifiers'])}")

        elif action_type == "rebound":  # 篮板事件
            narrative_parts.extend([
                f"**Rebound Type:** {event['sub_type']}",
                f"**Rebound Total:** {event['rebound_total']}",
                f"**Defensive Total:** {event.get('rebound_defensive_total', 'N/A')}",
                f"**Offensive Total:** {event.get('rebound_offensive_total', 'N/A')}"
            ])

        elif action_type == "turnover":  # 失误事件
            narrative_parts.extend([
                f"**Turnover Type:** {event['sub_type']}",
                f"**Turnover Total:** {event['turnover_total']}"
            ])
            if event.get('steal_player_name'):
                narrative_parts.append(f"**Steal By:** {event['steal_player_name']}")

        elif action_type == "foul":  # 犯规事件
            narrative_parts.extend([
                f"**Foul Type:** {event['sub_type']}"
            ])
            if event.get('foul_drawn_player_name'):
                narrative_parts.append(f"**Foul Drawn By:** {event['foul_drawn_player_name']}")
            if event.get('official_id'):
                narrative_parts.append(f"**Official ID:** {event['official_id']}")

        elif action_type == "substitution":  # 换人事件
            narrative_parts.extend([
                f"**Incoming Player:** {event['incoming_player_name']} ({event['incoming_player_name_i']})",
                f"**Outgoing Player:** {event['outgoing_player_name']} ({event['outgoing_player_name_i']})"
            ])

        elif action_type == "jumpball":  # 跳球事件
            narrative_parts.extend([
                f"**Won By:** {event['jump_ball_won_player_name']}",
                f"**Lost By:** {event['jump_ball_lost_player_name']}"
            ])
            if event.get('jump_ball_recovered_name'):
                narrative_parts.append(f"**Recovered By:** {event['jump_ball_recovered_name']}")

        # 添加事件描述
        narrative_parts.append(f"**Description:** {event['description']}")

        return "\n".join(narrative_parts)

class GameDisplayService:
    """比赛数据展示服务"""

    def __init__(self, config: Optional[DisplayConfig] = None):
        self.config = config or DisplayConfig()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        self.ai_processor = None
        if self.config.ai_config:
            try:
                self.ai_processor = AIProcessor(self.config.ai_config)
                self.logger.info("AI enhancement initialized successfully")
            except Exception as e:
                self.logger.warning(f"AI enhancement initialization failed: {e}")

        self._init_formatter()

    def _init_formatter(self):
        """初始化格式化器"""
        self.formatter = GameFormatter(self.ai_processor, self.config)

    def display_game(self, game: Game, player_id: Optional[int] = None) -> Dict[str, Any]:
        """显示比赛数据"""
        try:
            result = {
                "game_narrative": "",
                "team_narratives": {"home": "", "away": ""},
                "player_narratives": {"home": [], "away": []},
                "events": []
            }

            # 如果没有传入完整的game_data，说明只需要处理events
            if not game.game_data:
                if game.play_by_play and game.play_by_play.actions:
                    result["events"] = self.formatter.format_events(game.play_by_play.actions)
                return result

            # 基础比赛叙事
            result["game_narrative"] = self.formatter.format_game(game)

            # 球队叙事
            result["team_narratives"] = {
                "home": self.formatter.format_team(game.game_data.home_team, True),
                "away": self.formatter.format_team(game.game_data.away_team, False)
            }

            # 球员叙事（如果有完整game数据才处理）
            if game.game_data:
                if player_id:
                    # 获取指定球员数据
                    player = game.get_player_stats(player_id)
                    if player:
                        # 根据球员所属球队放入对应列表
                        is_home = player in game.game_data.home_team.players
                        team_key = "home" if is_home else "away"
                        if player.played == "1":
                            result["player_narratives"][team_key].append(
                                self.formatter.format_player(player)
                            )
                else:
                    # 获取所有上场球员数据
                    result["player_narratives"] = {
                        "home": [
                            self.formatter.format_player(player)
                            for player in game.game_data.home_team.players
                            if player.played == "1"
                        ],
                        "away": [
                            self.formatter.format_player(player)
                            for player in game.game_data.away_team.players
                            if player.played == "1"
                        ]
                    }

            # 事件处理
            if game.play_by_play and game.play_by_play.actions:
                filtered_events = (
                    game.filter_events(player_id=player_id)
                    if player_id and game.game_data
                    else game.play_by_play.actions
                )
                result["events"] = self.formatter.format_events(filtered_events)

            return result

        except Exception as e:
            self.logger.error(f"Formatting game data failed: {str(e)}")
            return {
                "game_narrative": "",
                "team_narratives": {"home": "", "away": ""},
                "player_narratives": {"home": [], "away": []},
                "events": []
            }