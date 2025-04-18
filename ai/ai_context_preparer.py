#ai/ai_context_preparer.py
from typing import Dict, Any, Optional, List, Protocol
from pydantic import BaseModel
from nba.models.game_model import Game
from utils.logger_handler import AppLogger
from nba.services.game_data_service import GameDataService


# 定义领域数据提取器协议
class DomainExtractor(Protocol):
    """领域数据提取器接口"""

    def extract(self, game: 'Game', **kwargs) -> Dict[str, Any]:
        """提取特定领域的数据"""
        ...


# 基础数据模型
class GameInfoModel(BaseModel):
    """比赛基本信息模型"""
    game_id: str
    teams: Dict[str, Any]
    date: Dict[str, Any]
    arena: Dict[str, Any]
    status: Dict[str, Any]


class PlayerStatusModel(BaseModel):
    """球员状态模型"""
    player_id: int
    name: str
    is_active: bool = True
    has_played: bool = False
    is_starter: bool = False
    is_on_court: bool = False
    injury: Optional[Dict[str, Any]] = None
    team_id: Optional[int] = None
    team_type: Optional[str] = None


# 数据提取器实现
class GameInfoExtractor:
    """比赛信息提取器"""

    def extract(self, game, **kwargs) -> Dict[str, Any]:
        """提取比赛基本信息"""
        if not game:
            return {}

        # 提取比赛基础数据
        game_data = game.game_data

        # 基本信息
        basic = {
            "game_id": game_data.game_id,
            "teams": {
                "home": {
                    "id": game_data.home_team.team_id,
                    "name": game_data.home_team.team_name,
                    "city": game_data.home_team.team_city,
                    "full_name": f"{game_data.home_team.team_city} {game_data.home_team.team_name}",
                    "tricode": game_data.home_team.team_tricode
                },
                "away": {
                    "id": game_data.away_team.team_id,
                    "name": game_data.away_team.team_name,
                    "city": game_data.away_team.team_city,
                    "full_name": f"{game_data.away_team.team_city} {game_data.away_team.team_name}",
                    "tricode": game_data.away_team.team_tricode
                }
            },
            "date": {
                "utc": game_data.game_time_utc.strftime('%Y-%m-%d %H:%M'),
                "beijing": game_data.game_time_beijing.strftime('%Y-%m-%d %H:%M'),
                "time_beijing": game_data.game_time_beijing.strftime('%H:%M')
            },
            "arena": {
                "name": game_data.arena.arena_name,
                "city": game_data.arena.arena_city,
                "state": game_data.arena.arena_state,
                "country": game_data.arena.arena_country,
                "full_location": f"{game_data.arena.arena_name}, {game_data.arena.arena_city}"
            }
        }

        # 比赛状态
        status = {
            "state": game_data.game_status_text,
            "period": {
                "number": game_data.period,
                "name": f"第{game_data.period}节"
            },
            "time_remaining": str(game_data.game_clock),
            "score": {
                "home": {
                    "team": game_data.home_team.team_tricode,
                    "points": int(game_data.home_team.score)
                },
                "away": {
                    "team": game_data.away_team.team_tricode,
                    "points": int(game_data.away_team.score)
                }
            }
        }

        # 比赛结果(如果已结束)
        result = None
        if game_data.game_status == 3:  # FINISHED
            result = {
                "duration": game_data.duration,
                "attendance": {
                    "count": game_data.attendance,
                    "sellout": game_data.sellout == "1"
                },
                "final_score": f"{game_data.away_team.team_tricode} {game_data.away_team.score} - {game_data.home_team.team_tricode} {game_data.home_team.score}",
                "winner": {
                    "team_id": game_data.home_team.team_id if int(game_data.home_team.score) > int(
                        game_data.away_team.score) else game_data.away_team.team_id,
                    "team_name": game_data.home_team.team_name if int(game_data.home_team.score) > int(
                        game_data.away_team.score) else game_data.away_team.team_name,
                    "score": max(int(game_data.home_team.score), int(game_data.away_team.score))
                },
                "loser": {
                    "team_id": game_data.away_team.team_id if int(game_data.home_team.score) > int(
                        game_data.away_team.score) else game_data.home_team.team_id,
                    "team_name": game_data.away_team.team_name if int(game_data.home_team.score) > int(
                        game_data.away_team.score) else game_data.home_team.team_name,
                    "score": min(int(game_data.home_team.score), int(game_data.away_team.score))
                },
                "score_difference": abs(int(game_data.home_team.score) - int(game_data.away_team.score))
            }

        return {
            "basic": basic,
            "status": status,
            "result": result
        }


class PlayerStatusExtractor:
    """球员状态数据提取器"""

    def extract(self, game: 'Game', player_id: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        """提取球员状态信息，包括伤病、上场、首发等状态"""
        if not game:
            return {}

        # 如果指定了球员ID，获取单个球员状态
        if player_id:
            return self.get_player_status(game, player_id)

        # 否则获取所有相关球员状态(首发、伤病等)
        return {
            "starters": self.get_all_starters(game),
            "injuries": self.get_all_injuries(game)
        }

    def get_player_status(self, game: 'Game', player_id: int) -> Dict[str, Any]:
        """获取指定球员的状态信息"""
        # 查找球员
        for team_type in ["home", "away"]:
            team = getattr(game.game_data, f"{team_type}_team")
            for player in team.players:
                if player.person_id == player_id:
                    # 检查球员状态
                    if player.status == "INACTIVE" or (
                            hasattr(player, "not_playing_reason") and player.not_playing_reason):
                        # 构建伤病球员的状态信息
                        return {
                            "is_active": False,
                            "has_played": player.has_played,
                            "injury": {
                                "status": "injured",
                                "reason": player.not_playing_reason.value if hasattr(player,
                                                                                     "not_playing_reason") and player.not_playing_reason else "Unknown",
                                "description": player.not_playing_description if hasattr(player,
                                                                                         "not_playing_description") else "",
                                "detailed": player.playing_status  # 这是一个包含中文描述的属性
                            },
                            "player_id": player_id,
                            "name": player.name,
                            "position": player.position,
                            "team_id": team.team_id,
                            "team_type": team_type
                        }
                    else:
                        # 构建正常上场球员的状态信息
                        return {
                            "is_active": True,
                            "has_played": player.has_played,
                            "is_starter": player.is_starter,
                            "is_on_court": player.is_on_court,
                            "playing_status": player.playing_status,
                            "player_id": player_id,
                            "name": player.name,
                            "position": player.position,
                            "team_id": team.team_id,
                            "team_type": team_type
                        }

        # 未找到球员
        return {"not_found": True}

    def get_all_starters(self, game: 'Game') -> Dict[str, List[Dict[str, Any]]]:
        """获取所有首发球员信息"""
        starters = {"home": [], "away": []}

        # 处理主队首发
        for player in game.game_data.home_team.players:
            if player.is_starter:
                starters["home"].append({
                    "id": player.person_id,
                    "name": player.name,
                    "position": player.position,
                    "jersey_num": player.jersey_num
                })

        # 处理客队首发
        for player in game.game_data.away_team.players:
            if player.is_starter:
                starters["away"].append({
                    "id": player.person_id,
                    "name": player.name,
                    "position": player.position,
                    "jersey_num": player.jersey_num
                })

        return starters

    def get_all_injuries(self, game: 'Game') -> Dict[str, List[Dict[str, Any]]]:
        """获取所有伤病球员信息"""
        injuries = {"home": [], "away": []}

        # 处理主队伤病
        for player in game.game_data.home_team.players:
            if player.status == "INACTIVE" or (hasattr(player, "not_playing_reason") and player.not_playing_reason):
                injuries["home"].append({
                    "id": player.person_id,
                    "name": player.name,
                    "reason": player.not_playing_reason.value if hasattr(player,
                                                                         "not_playing_reason") and player.not_playing_reason else "Unknown",
                    "description": player.not_playing_description if hasattr(player, "not_playing_description") else "",
                    "detailed": player.playing_status
                })

        # 处理客队伤病
        for player in game.game_data.away_team.players:
            if player.status == "INACTIVE" or (hasattr(player, "not_playing_reason") and player.not_playing_reason):
                injuries["away"].append({
                    "id": player.person_id,
                    "name": player.name,
                    "reason": player.not_playing_reason.value if hasattr(player,
                                                                         "not_playing_reason") and player.not_playing_reason else "Unknown",
                    "description": player.not_playing_description if hasattr(player, "not_playing_description") else "",
                    "detailed": player.playing_status
                })

        return injuries


class TeamStatsExtractor:
    """球队统计数据提取器"""

    def extract(self, game, **kwargs) -> Dict[str, Any]:
        """提取球队统计数据"""
        if not game:
            return {}

        team_id = kwargs.get("team_id")

        # 如果没有指定球队ID，处理两支球队
        if not team_id:
            return {
                "home": self._extract_single_team(game.game_data.home_team, True),
                "away": self._extract_single_team(game.game_data.away_team, False)
            }

        # 处理指定球队
        is_home = game.game_data.home_team.team_id == team_id
        team = game.game_data.home_team if is_home else game.game_data.away_team

        return self._extract_single_team(team, is_home)

    def _extract_single_team(self, team, is_home) -> Dict[str, Any]:
        """提取单个球队的统计数据"""
        stats = team.statistics

        # 基础统计
        basic = {
            "team_id": team.team_id,
            "team_name": team.team_name,
            "team_tricode": team.team_tricode,
            "is_home": is_home,
            "score": team.score
        }

        # 投篮数据
        shooting = {
            "field_goals": {
                "made": stats.field_goals_made,
                "attempted": stats.field_goals_attempted,
                "percentage": stats.field_goals_percentage
            },
            "three_pointers": {
                "made": stats.three_pointers_made,
                "attempted": stats.three_pointers_attempted,
                "percentage": stats.three_pointers_percentage
            },
            "two_pointers": {
                "made": stats.two_pointers_made,
                "attempted": stats.two_pointers_attempted,
                "percentage": stats.two_pointers_percentage
            },
            "free_throws": {
                "made": stats.free_throws_made,
                "attempted": stats.free_throws_attempted,
                "percentage": stats.free_throws_percentage
            }
        }

        # 篮板数据
        rebounds = {
            "offensive": stats.rebounds_offensive,
            "defensive": stats.rebounds_defensive,
            "total": stats.rebounds_total,
            "team_total": stats.rebounds_team
        }

        # 进攻数据
        offense = {
            "assists": stats.assists,
            "points": stats.points,
            "fast_break_points": stats.points_fast_break,
            "points_in_paint": stats.points_in_the_paint,
            "second_chance_points": stats.points_second_chance,
            "points_from_turnovers": stats.points_from_turnovers,
            "bench_points": stats.bench_points
        }

        # 防守数据
        defense = {
            "steals": stats.steals,
            "blocks": stats.blocks,
            "blocks_received": stats.blocks_received,
            "turnovers": {
                "personal": stats.turnovers,
                "team": stats.turnovers_team,
                "total": stats.turnovers_total
            }
        }

        # 犯规数据
        fouls = {
            "personal": stats.fouls_personal,
            "team": stats.fouls_team,
            "technical": stats.fouls_technical,
            "team_technical": stats.fouls_team_technical
        }

        # 高级统计
        advanced = {
            "true_shooting_percentage": stats.true_shooting_percentage,
            "effective_field_goal_percentage": stats.field_goals_effective_adjusted,
            "assists_turnover_ratio": stats.assists_turnover_ratio,
            "time_leading": stats.time_leading_calculated
        }

        return {
            "basic": basic,
            "shooting": shooting,
            "rebounds": rebounds,
            "offense": offense,
            "defense": defense,
            "fouls": fouls,
            "advanced": advanced
        }


class PlayerStatsExtractor:
    """球员统计数据提取器"""

    def extract(self, game, **kwargs) -> Dict[str, Any]:
        """提取球员统计数据"""
        if not game:
            return {}

        player_id = kwargs.get("player_id")
        if not player_id:
            return {}

        # 查找球员
        for team_type in ["home", "away"]:
            team = getattr(game.game_data, f"{team_type}_team")
            for player in team.players:
                if player.person_id == player_id:
                    return self._extract_player_data(player, team, team_type == "home")

        return {}

    def _extract_player_data(self, player, team, is_home) -> Dict[str, Any]:
        """提取单个球员的数据"""
        stats = player.statistics

        # 基本信息
        basic = {
            "player_id": player.person_id,
            "name": player.name,
            "position": player.position,
            "jersey_num": player.jersey_num,
            "starter": player.is_starter,  # 使用模型属性
            "played": player.has_played,  # 使用模型属性
            "on_court": player.is_on_court,  # 使用模型属性
            "playing_status": player.playing_status,  # 使用模型属性
            "minutes": stats.minutes_calculated,
            "points": stats.points,
            "rebounds": stats.rebounds_total,
            "assists": stats.assists,
            "plus_minus": stats.plus_minus_points
        }

        # 投篮数据
        shooting = {
            "field_goals": {
                "made": stats.field_goals_made,
                "attempted": stats.field_goals_attempted,
                "percentage": stats.field_goals_percentage
            },
            "three_pointers": {
                "made": stats.three_pointers_made,
                "attempted": stats.three_pointers_attempted,
                "percentage": stats.three_pointers_percentage
            },
            "two_pointers": {
                "made": stats.two_pointers_made,
                "attempted": stats.two_pointers_attempted,
                "percentage": stats.two_pointers_percentage
            },
            "free_throws": {
                "made": stats.free_throws_made,
                "attempted": stats.free_throws_attempted,
                "percentage": stats.free_throws_percentage
            }
        }

        # 其他统计
        other_stats = {
            "steals": stats.steals,
            "blocks": stats.blocks,
            "turnovers": stats.turnovers,
            "fouls": {
                "personal": stats.fouls_personal,
                "technical": stats.fouls_technical,
                "offensive": stats.fouls_offensive,
                "drawn": stats.fouls_drawn
            },
            "rebounds": {
                "offensive": stats.rebounds_offensive,
                "defensive": stats.rebounds_defensive,
                "total": stats.rebounds_total
            },
            "scoring_breakdown": {
                "fast_break_points": stats.points_fast_break,
                "paint_points": stats.points_in_the_paint,
                "second_chance_points": stats.points_second_chance
            },
            "plus_minus": {
                "total": stats.plus_minus_points,
                "plus": stats.plus,
                "minus": stats.minus
            }
        }

        # 球员所属球队信息
        team_info = {
            "team_id": team.team_id,
            "team_name": team.team_name,
            "team_tricode": team.team_tricode,
            "is_home": is_home
        }

        return {
            "basic": basic,
            "shooting": shooting,
            "other_stats": other_stats,
            "team": team_info
        }


class EventsExtractor:
    """比赛事件提取器"""

    def extract(self, game, **kwargs) -> Dict[str, Any]:
        """提取比赛事件数据"""
        player_id = kwargs.get("player_id")
        data = kwargs.get("data")  # 如果数据已经在适配器中存在则使用现有数据

        # 如果提供了game对象，从game中提取
        if game and game.play_by_play and game.play_by_play.actions:
            all_events = game.play_by_play.actions
            if player_id:
                # 筛选与球员相关的事件
                player_events = self._filter_player_events(all_events, player_id)
                return {
                    "count": len(player_events),
                    "data": [self._event_to_dict(event) for event in player_events]
                }
            else:
                # 获取所有事件
                return {
                    "count": len(all_events),
                    "data": [self._event_to_dict(event) for event in all_events]
                }

        # 如果提供了数据字典，从数据字典中获取
        if data and "events" in data:
            return data["events"]

        # 默认返回空结果
        return {"count": 0, "data": []}

    def _filter_player_events(self, events, player_id):
        """筛选与球员相关的事件"""
        result = []
        for event in events:
            if self._is_event_related_to_player(event, player_id):
                result.append(event)

        # 按时间排序
        result.sort(key=lambda x: (getattr(x, 'period', 0), getattr(x, 'clock', '')))
        return result

    def _is_event_related_to_player(self, event, player_id):
        """判断事件是否与球员相关"""
        # 直接相关 - 球员是事件的主体
        if hasattr(event, 'person_id') and event.person_id == player_id:
            return True

        # 间接相关 - 球员是助攻者、被盖帽者等
        related_fields = [
            ('assist_person_id', player_id),
            ('block_person_id', player_id),
            ('steal_person_id', player_id),
            ('foul_drawn_person_id', player_id),
            ('scoring_person_id', player_id)
        ]

        for field, value in related_fields:
            if hasattr(event, field) and getattr(event, field) == value:
                return True

        return False

    def _event_to_dict(self, event):
        """将事件对象转换为字典"""
        # 使用 Pydantic 的 model_dump 方法或 dict 方法
        if hasattr(event, "model_dump"):  # Pydantic v2
            return event.model_dump()
        elif hasattr(event, "dict"):  # Pydantic v1
            return event.dict()
        else:
            # 回退到手动方式
            event_dict = {}
            for attr in dir(event):
                if not attr.startswith('_') and not callable(getattr(event, attr)):
                    event_dict[attr] = getattr(event, attr)
            return event_dict


class OfficialsExtractor:
    """裁判数据提取器"""

    def extract(self, game: 'Game', **kwargs) -> Dict[str, Any]:
        """提取裁判信息及影响分析"""
        if not game or not game.game_data:
            return {}

        officials_data = []
        for official in game.game_data.officials:
            officials_data.append({
                "name": official.name,
                "position": official.assignment,
                "id": official.person_id,
                "jersey_num": official.jersey_num
            })

        return {
            "officials": officials_data,
            "lead_official": officials_data[0] if officials_data else {}
        }


class GamePaceExtractor:
    """比赛节奏与转折点提取器"""

    def extract(self, game: 'Game', **kwargs) -> Dict[str, Any]:
        """提取比赛节奏与转折点数据"""
        if not game or not game.game_data:
            return {}

        home_team = game.game_data.home_team
        away_team = game.game_data.away_team

        home_stats = home_team.statistics
        away_stats = away_team.statistics

        return {
            "lead_changes": {
                "count": home_stats.lead_changes,
                "description": self._get_lead_changes_description(home_stats.lead_changes)
            },
            "team_control": {
                "home": {
                    "leading_time": home_stats.time_leading_calculated,
                    "biggest_lead": home_stats.biggest_lead,
                    "biggest_lead_score": home_stats.biggest_lead_score,
                    "biggest_run": home_stats.biggest_scoring_run,
                    "biggest_run_score": home_stats.biggest_scoring_run_score
                },
                "away": {
                    "leading_time": away_stats.time_leading_calculated,
                    "biggest_lead": away_stats.biggest_lead,
                    "biggest_lead_score": away_stats.biggest_lead_score,
                    "biggest_run": away_stats.biggest_scoring_run,
                    "biggest_run_score": away_stats.biggest_scoring_run_score
                }
            },
            "pacing": self._analyze_game_pacing(home_stats, away_stats)
        }

    def _get_lead_changes_description(self, count: int) -> str:
        """根据领先变换次数提供描述性文本"""
        if count < 5:
            return "比赛控制权变化较少，一方占据主导"
        elif count < 15:
            return "比赛有一定竞争性，双方交替领先"
        else:
            return "激烈对抗，领先权频繁易手"

    def _analyze_game_pacing(self, home_stats, away_stats) -> Dict[str, Any]:
        """分析比赛节奏"""
        # 通过快攻比例、投篮次数等计算比赛节奏
        fast_break_ratio = (home_stats.points_fast_break + away_stats.points_fast_break) / \
                           (home_stats.points + away_stats.points) if (home_stats.points + away_stats.points) > 0 else 0

        total_possessions = (home_stats.field_goals_attempted + away_stats.field_goals_attempted + \
                             (home_stats.turnovers_total + away_stats.turnovers_total) - \
                             (home_stats.rebounds_offensive + away_stats.rebounds_offensive)) / 2

        return {
            "pace_type": "快节奏" if fast_break_ratio > 0.15 else "中等节奏" if fast_break_ratio > 0.08 else "慢节奏",
            "fast_break_ratio": fast_break_ratio,
            "estimated_possessions": total_possessions
        }


class LineupAnalysisExtractor:
    """阵容分析提取器"""

    def extract(self, game: 'Game', **kwargs) -> Dict[str, Any]:
        """提取当前阵容和阵容效率数据"""
        if not game or not game.game_data:
            return {}

        # 提取当前在场阵容
        current_lineups = {"home": [], "away": []}

        # 主队在场阵容
        for player in game.game_data.home_team.players:
            if player.is_on_court:  # 使用属性方法
                current_lineups["home"].append({
                    "id": player.person_id,
                    "name": player.name,
                    "position": player.position,
                    "plus_minus": player.statistics.plus_minus_points
                })

        # 客队在场阵容
        for player in game.game_data.away_team.players:
            if player.is_on_court:  # 使用属性方法
                current_lineups["away"].append({
                    "id": player.person_id,
                    "name": player.name,
                    "position": player.position,
                    "plus_minus": player.statistics.plus_minus_points
                })

        # 计算当前阵容净效率
        home_lineup_plus_minus = sum(p.get("plus_minus", 0) for p in current_lineups["home"])
        away_lineup_plus_minus = sum(p.get("plus_minus", 0) for p in current_lineups["away"])

        return {
            "current_lineups": current_lineups,
            "lineup_analysis": {
                "home": {
                    "size": len(current_lineups["home"]),
                    "combined_plus_minus": home_lineup_plus_minus,
                    "avg_plus_minus": home_lineup_plus_minus / len(current_lineups["home"]) if current_lineups[
                        "home"] else 0
                },
                "away": {
                    "size": len(current_lineups["away"]),
                    "combined_plus_minus": away_lineup_plus_minus,
                    "avg_plus_minus": away_lineup_plus_minus / len(current_lineups["away"]) if current_lineups[
                        "away"] else 0
                }
            },
            "timeouts": {
                "home": game.game_data.home_team.timeouts_remaining,
                "away": game.game_data.away_team.timeouts_remaining
            },
            "bonus_situation": {
                "home": game.game_data.home_team.in_bonus == "1",
                "away": game.game_data.away_team.in_bonus == "1"
            }
        }


class PeriodPerformanceExtractor:
    """分节表现提取器"""

    def extract(self, game: 'Game', **kwargs) -> Dict[str, Any]:
        """提取各节得分表现和趋势"""
        if not game or not game.game_data:
            return {}

        home_periods = game.game_data.home_team.periods
        away_periods = game.game_data.away_team.periods

        # 整理各节数据
        period_data = []
        for i in range(max(len(home_periods), len(away_periods))):
            home_score = home_periods[i].score if i < len(home_periods) else 0
            away_score = away_periods[i].score if i < len(away_periods) else 0

            period_data.append({
                "period": i + 1,
                "home_score": home_score,
                "away_score": away_score,
                "difference": home_score - away_score,
                "winner": "home" if home_score > away_score else "away" if away_score > home_score else "tie"
            })

        # 找出强势节和弱势节
        home_best_period = max(period_data, key=lambda x: x["home_score"]) if period_data else {}
        home_worst_period = min(period_data, key=lambda x: x["home_score"]) if period_data else {}
        away_best_period = max(period_data, key=lambda x: x["away_score"]) if period_data else {}
        away_worst_period = min(period_data, key=lambda x: x["away_score"]) if period_data else {}

        # 分析趋势
        home_trend = "上升" if len(period_data) >= 2 and period_data[-1]["home_score"] > period_data[-2][
            "home_score"] else "下降"
        away_trend = "上升" if len(period_data) >= 2 and period_data[-1]["away_score"] > period_data[-2][
            "away_score"] else "下降"

        return {
            "period_details": period_data,
            "team_periods": {
                "home": {
                    "best_period": home_best_period,
                    "worst_period": home_worst_period,
                    "trend": home_trend,
                    "periods_won": sum(1 for p in period_data if p["winner"] == "home")
                },
                "away": {
                    "best_period": away_best_period,
                    "worst_period": away_worst_period,
                    "trend": away_trend,
                    "periods_won": sum(1 for p in period_data if p["winner"] == "away")
                }
            },
            "key_periods": [p for p in period_data if abs(p["difference"]) >= 10]
        }


class ScoringDetailsExtractor:
    """得分方式详情提取器"""

    def extract(self, game: 'Game', **kwargs) -> Dict[str, Any]:
        """提取得分方式详情"""
        if not game or not game.game_data:
            return {}

        result = {}
        team_id = kwargs.get("team_id")
        player_id = kwargs.get("player_id")

        # 团队得分方式
        if team_id:
            is_home = game.game_data.home_team.team_id == team_id
            team = game.game_data.home_team if is_home else game.game_data.away_team
            stats = team.statistics

            result["team_scoring"] = {
                "total_points": stats.points,
                "scoring_breakdown": {
                    "paint_points": {
                        "points": stats.points_in_the_paint,
                        "percentage": stats.points_in_the_paint / stats.points if stats.points else 0,
                        "made": stats.points_in_the_paint_made,
                        "attempted": stats.points_in_the_paint_attempted
                    },
                    "fast_break": {
                        "points": stats.points_fast_break,
                        "percentage": stats.points_fast_break / stats.points if stats.points else 0,
                        "made": stats.fast_break_points_made,
                        "attempted": stats.fast_break_points_attempted
                    },
                    "second_chance": {
                        "points": stats.points_second_chance,
                        "percentage": stats.points_second_chance / stats.points if stats.points else 0,
                        "made": stats.second_chance_points_made,
                        "attempted": stats.second_chance_points_attempted
                    },
                    "from_turnovers": {
                        "points": stats.points_from_turnovers,
                        "percentage": stats.points_from_turnovers / stats.points if stats.points else 0
                    }
                },
                "bench_contribution": {
                    "points": stats.bench_points,
                    "percentage": stats.bench_points / stats.points if stats.points else 0
                }
            }

        # 球员得分方式
        if player_id:
            player_found = False
            for team_type in ["home", "away"]:
                team = getattr(game.game_data, f"{team_type}_team")
                for player in team.players:
                    if player.person_id == player_id:
                        stats = player.statistics
                        player_found = True

                        result["player_scoring"] = {
                            "total_points": stats.points,
                            "scoring_breakdown": {
                                "paint_points": {
                                    "points": stats.points_in_the_paint,
                                    "percentage": stats.points_in_the_paint / stats.points if stats.points else 0
                                },
                                "fast_break": {
                                    "points": stats.points_fast_break,
                                    "percentage": stats.points_fast_break / stats.points if stats.points else 0
                                },
                                "second_chance": {
                                    "points": stats.points_second_chance,
                                    "percentage": stats.points_second_chance / stats.points if stats.points else 0
                                }
                            }
                        }
                        break
                if player_found:
                    break

        return result


class RivalryInfoExtractor:
    """球队对抗历史信息提取器"""

    def extract(self, game: 'Game', **kwargs) -> Dict[str, Any]:
        """提取球队对抗历史信息"""
        if not game or not hasattr(game, "get_season_matchup_history"):
            return {"available": False}

        # 使用Game模型提供的方法获取对抗历史
        return game.get_season_matchup_history()


class AIContextPreparer:
    """AI上下文准备器 - 处理和组织NBA数据用于AI分析"""

    def __init__(self, game_data_service: GameDataService, logger: Optional[Any] = None):
        """初始化AI上下文准备器

        Args:
            game_data_service: 游戏数据服务实例，用于获取比赛数据
            logger: 可选的日志记录器
        """
        self.logger = logger or AppLogger.get_logger(__name__, app_name='ai_services')
        self.game_data_service = game_data_service  # 保存GameDataService依赖

        # 初始化所有数据提取器
        self.extractors = {
            "game_info": GameInfoExtractor(),
            "team_stats": TeamStatsExtractor(),
            "player_stats": PlayerStatsExtractor(),
            "events": EventsExtractor(),
            "player_status": PlayerStatusExtractor(),
            "officials": OfficialsExtractor(),
            "game_pace": GamePaceExtractor(),
            "lineup": LineupAnalysisExtractor(),
            "periods": PeriodPerformanceExtractor(),
            "scoring_details": ScoringDetailsExtractor(),
            "rivalry_info": RivalryInfoExtractor()
        }

    def prepare_ai_data(self, team_id: Optional[int] = None,
                        game_id: Optional[str] = None,
                        player_id: Optional[int] = None,
                        force_update: bool = False) -> Dict[str, Any]:
        """为AI分析准备完整的结构化数据

        Args:
            team_id: 球队ID
            game_id: 比赛ID，如果提供则直接使用此ID获取数据
            player_id: 球员ID，如果提供则会添加球员特定数据
            force_update: 是否强制更新数据

        Returns:
            Dict[str, Any]: 结构化的数据字典
        """
        try:
            # 1. 获取比赛数据
            game = self._get_game(team_id, game_id, force_update)
            if not game:
                return {"error": "无法获取比赛数据"}

            # 2. 获取团队ID（如果有球员ID，则使用球员所在团队ID）
            if player_id and not team_id:
                player_status = self.extractors["player_status"].extract(game, player_id=player_id)
                if not player_status.get("not_found", False):
                    team_id = player_status.get("team_id")

            # 3. 提取所有核心数据
            data = self._extract_core_data(game, player_id=player_id, team_id=team_id)

            # 4. 添加增强数据
            if team_id:
                data["scoring_details"] = self.extractors["scoring_details"].extract(
                    game, team_id=team_id, player_id=player_id
                )
                data["game_pace"] = self.extractors["game_pace"].extract(game)
                data["periods"] = self.extractors["periods"].extract(game)

            # 5. 添加球员特定数据（如果有指定球员）
            if player_id:
                player_status = self.extractors["player_status"].extract(game, player_id=player_id)

                # 根据球员状态决定处理方式
                if not player_status.get("is_active", True):
                    data = self._enhance_injured_player_data(data, game, player_id, player_status)
                else:
                    data = self._enhance_active_player_data(data, game, player_id, player_status)

            # 6. 添加数据库补充信息
            self._enrich_with_db_data(data, game, team_id, player_id)

            return data
        except Exception as e:
            self.logger.error(f"准备AI数据失败: {str(e)}", exc_info=True)
            return {"error": f"准备AI数据失败: {str(e)}"}

    def _get_game(self, team_id: Optional[int], game_id: Optional[str], force_update: bool) -> Optional['Game']:
        """获取游戏数据

        Args:
            team_id: 球队ID
            game_id: 游戏ID
            force_update: 是否强制更新

        Returns:
            Optional[Game]: 游戏对象，如果获取失败则返回None
        """
        try:
            if game_id:
                return self.game_data_service.get_game_by_id(game_id, force_update=force_update)
            elif team_id:
                # 获取球队名称
                team_name = self.game_data_service.get_team_name_by_id(team_id)
                if not team_name:
                    self.logger.error(f"无法找到ID为 {team_id} 的球队名称")
                    return None
                # 使用"last"作为默认日期获取最近的比赛
                return self.game_data_service.get_game(team_name, "last", force_update=force_update)
            else:
                self.logger.error("必须提供 team_id 或 game_id 参数")
                return None
        except Exception as e:
            self.logger.error(f"获取比赛数据失败: {str(e)}", exc_info=True)
            return None

    def _extract_core_data(self, game: 'Game', **kwargs) -> Dict[str, Any]:
        """提取并组合所有核心数据"""
        result = {}

        # 1. 获取比赛基本信息
        result["game_info"] = self.extractors["game_info"].extract(game)

        # 2. 获取球队统计数据
        team_id = kwargs.get("team_id")
        result["team_stats"] = self.extractors["team_stats"].extract(game, team_id=team_id)

        # 3. 获取球员统计数据（如果指定了球员ID）
        player_id = kwargs.get("player_id")
        if player_id:
            result["player_info"] = self.extractors["player_stats"].extract(game, player_id=player_id)

        # 4. 获取球队对抗历史信息
        result["rivalry_info"] = self.extractors["rivalry_info"].extract(game)

        # 5. 获取首发和伤病情况
        status_data = self.extractors["player_status"].extract(game)
        result["starters"] = status_data.get("starters", {})
        result["injuries"] = status_data.get("injuries", {})

        return result

    def _enhance_injured_player_data(self, data: Dict[str, Any], game: 'Game', player_id: int,
                                     status: Dict[str, Any]) -> Dict[str, Any]:
        """为伤病球员增强数据"""
        # 1. 标记为伤病球员
        data["is_injured_player"] = True

        # 2. 添加伤病信息
        if "player_info" not in data:
            data["player_info"] = {
                "player_id": player_id,
                "name": status.get("name", ""),
                "position": status.get("position", ""),
                "injury_status": status.get("injury", {})
            }
        else:
            data["player_info"]["injury_status"] = status.get("injury", {})

        # 3. 添加球员所属球队信息
        team_id = status.get("team_id")
        team_type = status.get("team_type")

        if team_id and team_type:
            team = getattr(game.game_data, f"{team_type}_team")
            data["team_info"] = {
                "team_id": team_id,
                "team_name": team.team_name,
                "team_tricode": team.team_tricode,
                "is_home": team_type == "home"
            }

            # 获取对手球队
            opponent_type = "away" if team_type == "home" else "home"
            opponent = getattr(game.game_data, f"{opponent_type}_team")
            data["opponent_info"] = {
                "team_id": opponent.team_id,
                "team_name": opponent.team_name,
                "team_tricode": opponent.team_tricode,
                "is_home": opponent_type == "home"
            }

        # 4. 添加伤病描述
        injury = status.get("injury", {})
        data["injury_description"] = (
            f"{status.get('name', '球员')}因{injury.get('reason', '伤病')}缺席本场比赛。"
            f"{injury.get('description', '')}"
        )

        return data

    def _enhance_active_player_data(self, data: Dict[str, Any], game: 'Game', player_id: int, status: Dict[str, Any]) -> \
    Dict[str, Any]:
        """为常规球员增强数据"""
        # 1. 标记为常规球员
        data["is_injured_player"] = False

        # 2. 添加状态信息
        if "player_info" not in data:
            player_stats = self.extractors["player_stats"].extract(game, player_id=player_id)
            if not player_stats:
                return {"error": f"无法获取ID为 {player_id} 的球员统计数据"}
            data["player_info"] = player_stats

        data["player_info"]["status"] = status

        # 3. 添加球员所属球队信息
        team_id = status.get("team_id")
        team_type = status.get("team_type")

        if team_id and team_type:
            team = getattr(game.game_data, f"{team_type}_team")
            data["team_info"] = {
                "team_id": team_id,
                "team_name": team.team_name,
                "team_tricode": team.team_tricode,
                "is_home": team_type == "home"
            }

            # 获取对手球队
            opponent_type = "away" if team_type == "home" else "home"
            opponent = getattr(game.game_data, f"{opponent_type}_team")
            data["opponent_info"] = {
                "team_id": opponent.team_id,
                "team_name": opponent.team_name,
                "team_tricode": opponent.team_tricode,
                "is_home": opponent_type == "home"
            }

        # 4. 添加比赛结果
        if team_id:
            data["game_result"] = self._determine_game_result(game, team_id)

        return data

    def _determine_game_result(self, game: 'Game', team_id: int) -> Dict[str, Any]:
        """确定比赛结果，从团队角度"""
        # 获取比赛状态
        game_status = game.game_data.game_status

        # 如果比赛未结束，标记为进行中
        if game_status != 3:  # 3 = FINISHED
            return {"status": "in_progress"}

        # 获取比分
        home_score = int(game.game_data.home_team.score)
        away_score = int(game.game_data.away_team.score)

        # 判断是主队还是客队
        is_home = game.game_data.home_team.team_id == team_id
        team_score = home_score if is_home else away_score
        opponent_score = away_score if is_home else home_score

        # 判断胜负
        is_win = (is_home and home_score > away_score) or (not is_home and away_score > home_score)

        return {
            "status": "finished",
            "is_win": is_win,
            "score": {
                "team": team_score,
                "opponent": opponent_score,
                "difference": abs(team_score - opponent_score)
            },
            "description": f"{'胜' if is_win else '负'} {team_score}-{opponent_score}"
        }

    def _enrich_with_db_data(self, data: Dict[str, Any], game: 'Game',
                             team_id: Optional[int] = None, player_id: Optional[int] = None) -> None:
        """从数据库获取补充数据

        Args:
            data: 要补充的数据字典
            game: 游戏对象
            team_id: 球队ID
            player_id: 球员ID
        """
        try:
            # 获取球队历史数据
            if team_id:
                try:
                    team_history = self.game_data_service.db_service.team_repo.get_team_history(team_id)
                    if team_history:
                        data["team_history"] = team_history
                except Exception as e:
                    self.logger.warning(f"获取球队历史数据失败: {e}")

            # 获取球员历史数据
            if player_id:
                try:
                    player_history = self.game_data_service.db_service.player_repo.get_player_history(player_id)
                    if player_history:
                        data["player_history"] = player_history
                except Exception as e:
                    self.logger.warning(f"获取球员历史数据失败: {e}")

            # 可以根据需要添加更多数据库补充数据
        except Exception as e:
            self.logger.warning(f"从数据库获取补充数据失败: {e}")