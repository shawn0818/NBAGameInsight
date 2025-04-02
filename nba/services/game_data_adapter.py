from typing import Dict, Any, Optional, List,  Protocol
from pydantic import BaseModel
from nba.models.game_model import Game
from utils.logger_handler import AppLogger


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


# 增强版GameDataAdapter实现
class GameDataAdapter:
    """增强版游戏数据适配器 - 充分利用所有Game模型数据"""

    def __init__(self, logger=None):
        """初始化适配器"""
        self.logger = logger or AppLogger.get_logger(__name__, app_name='nba')

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

    def adapt_for_team_content(self, game: 'Game', team_id: int) -> Dict[str, Any]:
        """为球队内容生成适配数据 - 包含增强数据"""
        try:
            # 1. 提取核心数据
            data = self._extract_core_data(game, team_id=team_id)

            # 2. 提取增强数据
            data["officials"] = self.extractors["officials"].extract(game)
            data["game_pace"] = self.extractors["game_pace"].extract(game)
            data["lineup"] = self.extractors["lineup"].extract(game)
            data["periods"] = self.extractors["periods"].extract(game)
            data["scoring_details"] = self.extractors["scoring_details"].extract(game, team_id=team_id)

            # 3. 处理球队特定信息
            self._enhance_team_specific_data(data, game, team_id)

            return data
        except Exception as e:
            self.logger.error(f"适配球队内容数据失败: {str(e)}", exc_info=True)
            return {"error": f"适配失败: {str(e)}"}

    def adapt_for_player_content(self, game: 'Game', player_id: int) -> Dict[str, Any]:
        """为球员内容生成适配数据 - 包含增强数据"""
        try:
            # 1. 获取球员状态
            player_status = self.extractors["player_status"].extract(game, player_id=player_id)

            # 2. 检查球员是否存在
            if player_status.get("not_found", False):
                return {"error": f"找不到ID为 {player_id} 的球员"}

            # 3. 提取基础数据
            data = self._extract_core_data(game)

            # 4. 提取球员详细数据
            player_stats = self.extractors["player_stats"].extract(game, player_id=player_id)
            if player_stats:
                data["player_info"] = player_stats

            # 5. 提取得分详情
            data["scoring_details"] = self.extractors["scoring_details"].extract(game, player_id=player_id)

            # 6. 提取球员相关事件
            data["events"] = self.extractors["events"].extract(game, player_id=player_id)

            # 7. 根据球员是否有伤病情况进行专门处理
            if not player_status.get("is_active", True):
                data = self._enhance_injured_player_data(data, game, player_id, player_status)
            else:
                data = self._enhance_active_player_data(data, game, player_id, player_status)

            return data
        except Exception as e:
            self.logger.error(f"适配球员内容数据失败: {str(e)}", exc_info=True)
            return {"error": f"适配失败: {str(e)}"}

    def adapt_for_shot_chart(self, game: 'Game', entity_id: int, is_team: bool = False) -> Dict[str, Any]:
        """为投篮图内容生成适配数据"""
        try:
            # 确定目标ID是球队还是球员
            team_id = entity_id if is_team else None
            player_id = entity_id if not is_team else None

            # 1. 提取基础数据
            data = self._extract_core_data(game, team_id=team_id, player_id=player_id)

            # 2. 获取投篮数据
            if is_team:
                shot_data = game.get_team_shot_data(entity_id)
                data["shot_data"] = shot_data
                data["is_team_chart"] = True

                # 添加球队得分详情
                data["scoring_details"] = self.extractors["scoring_details"].extract(game, team_id=entity_id)
            else:
                shot_data = game.get_shot_data(entity_id)
                assisted_shots = game.get_assisted_shot_data(entity_id)
                data["shot_data"] = shot_data
                data["assisted_shots"] = assisted_shots
                data["is_team_chart"] = False

                # 添加球员得分详情
                data["scoring_details"] = self.extractors["scoring_details"].extract(game, player_id=entity_id)

            return data
        except Exception as e:
            self.logger.error(f"适配投篮图数据失败: {str(e)}", exc_info=True)
            return {"error": f"适配失败: {str(e)}"}

    def adapt_for_round_analysis(self, game: 'Game', player_id: int, round_ids: List[int]) -> Dict[str, Any]:
        """为回合分析生成适配数据"""
        try:
            # 1. 提取基础数据
            data = self._extract_core_data(game, player_id=player_id)

            # 2. 提取回合数据
            events_data = self.extractors["events"].extract(game, player_id=player_id)
            rounds = []

            # 3. 筛选指定回合并添加上下文
            all_events = events_data.get("data", [])
            for round_id in round_ids:
                round_data = self._find_round_event(all_events, round_id)
                if round_data:
                    # 添加相邻回合作为上下文
                    context = self._get_round_context(all_events, round_id)
                    round_data["context"] = context
                    rounds.append(round_data)

            data["rounds"] = rounds
            data["round_ids"] = round_ids

            return data
        except Exception as e:
            self.logger.error(f"适配回合分析数据失败: {str(e)}", exc_info=True)
            return {"error": f"适配失败: {str(e)}"}

    def prepare_ai_data(self, game: 'Game', player_id: Optional[int] = None) -> Dict[str, Any]:
        """为AI分析准备完整的结构化数据"""
        try:
            # 获取团队ID（如果有球员ID，则使用球员所在团队ID）
            team_id = None
            if player_id:
                player_status = self.extractors["player_status"].extract(game, player_id=player_id)
                if not player_status.get("not_found", False):
                    team_id = player_status.get("team_id")

            # 提取所有核心数据
            data = self._extract_core_data(game, player_id=player_id, team_id=team_id)

            # 添加增强数据
            if team_id:
                data["scoring_details"] = self.extractors["scoring_details"].extract(
                    game, team_id=team_id, player_id=player_id
                )
                data["game_pace"] = self.extractors["game_pace"].extract(game)
                data["periods"] = self.extractors["periods"].extract(game)

            # 添加球员特定数据（如果有指定球员）
            if player_id:
                player_status = self.extractors["player_status"].extract(game, player_id=player_id)

                # 根据球员状态决定处理方式
                if not player_status.get("is_active", True):
                    data = self._enhance_injured_player_data(data, game, player_id, player_status)
                else:
                    data = self._enhance_active_player_data(data, game, player_id, player_status)

            return data
        except Exception as e:
            self.logger.error(f"准备AI数据失败: {str(e)}", exc_info=True)
            return {"error": f"准备AI数据失败: {str(e)}"}

    # 内部辅助方法

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

    def _enhance_team_specific_data(self, data: Dict[str, Any], game: 'Game', team_id: int) -> None:
        """增强球队特定数据"""
        # 1. 查找团队在数据中的位置（主队或客队）
        is_home = game.game_data.home_team.team_id == team_id
        team = game.game_data.home_team if is_home else game.game_data.away_team
        opponent = game.game_data.away_team if is_home else game.game_data.home_team

        # 2. 添加球队基本信息
        data["team_info"] = {
            "team_id": team_id,
            "team_name": team.team_name,
            "team_city": team.team_city,
            "team_tricode": team.team_tricode,
            "is_home": is_home,
            "score": int(team.score)
        }

        # 3. 添加对手信息
        data["opponent_info"] = {
            "team_id": opponent.team_id,
            "team_name": opponent.team_name,
            "team_city": opponent.team_city,
            "team_tricode": opponent.team_tricode,
            "is_home": not is_home,
            "score": int(opponent.score)
        }

        # 4. 添加比赛结果分析
        data["game_result"] = self._determine_game_result(game, team_id)

        # 5. 提取表现最好的球员
        top_players = []
        for player in team.players:
            if player.has_played:
                stats = player.statistics
                top_players.append({
                    "id": player.person_id,
                    "name": player.name,
                    "position": player.position,
                    "jersey_num": player.jersey_num,
                    "points": stats.points,
                    "rebounds": stats.rebounds_total,
                    "assists": stats.assists,
                    "plus_minus": stats.plus_minus_points,
                    "minutes": stats.minutes_calculated
                })

        # 按得分排序
        top_players.sort(key=lambda x: x["points"], reverse=True)
        data["top_players"] = top_players[:5]  # 前5名

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

    def _find_round_event(self, events: List[Dict[str, Any]], round_id: int) -> Optional[Dict[str, Any]]:
        """在事件列表中查找指定回合ID的事件"""
        for event in events:
            if event.get("action_number") == round_id:
                return event
        return None

    def _get_round_context(self, events: List[Dict[str, Any]], round_id: int, context_size: int = 3) -> List[
        Dict[str, Any]]:
        """获取回合的上下文事件"""
        # 查找回合在事件列表中的位置
        event_index = -1
        for i, event in enumerate(events):
            if event.get("action_number") == round_id:
                event_index = i
                break

        if event_index == -1:
            return []

        # 获取前后各context_size个事件
        start = max(0, event_index - context_size)
        end = min(len(events), event_index + context_size + 1)

        # 不包含当前回合本身
        context = events[start:event_index] + events[event_index + 1:end]
        return context