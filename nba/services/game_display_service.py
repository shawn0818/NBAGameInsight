from typing import Optional, Dict, Any
from utils.logger_handler import AppLogger
from nba.models.game_model import Game, TeamInGame, PlayerInGame, GameStatusEnum


class GameDisplayService:
    """比赛数据展示服务 - 简化版"""

    def __init__(self):
        """初始化服务"""
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def display_game(self, game: Game, player_id: Optional[int] = None) -> Dict[str, Any]:
        """显示比赛数据

        Args:
            game: 比赛对象
            player_id: 可选的球员ID，用于筛选特定球员数据

        Returns:
            Dict[str, Any]: 包含结构化比赛数据的字典
        """
        try:
            return self.prepare_ai_data(game, player_id)
        except Exception as e:
            self.logger.error(f"处理比赛数据失败: {str(e)}")
            return {"error": "处理比赛数据失败"}

    def prepare_ai_data(self, game: Game, player_id: Optional[int] = None) -> Dict[str, Any]:
        """准备用于AI分析的结构化数据

        提供结构化数据格式，专为AI模型分析设计。
        保留原始数据结构，同时添加必要的上下文信息。

        Args:
            game: 比赛对象
            player_id: 可选的球员ID，用于筛选特定球员数据

        Returns:
            Dict[str, Any]: 包含结构化数据的字典
        """
        if not game.game_data:
            self.logger.error("比赛数据不完整")
            return {"error": "比赛数据不完整或不可用"}

        try:
            # 1. 创建一个处理上下文字典以减少重复查询
            context = {
                # 存储球队名称映射，避免重复生成
                "team_names": {
                    "home": {
                        "full_name": f"{game.game_data.home_team.team_city} {game.game_data.home_team.team_name}",
                        "short_name": game.game_data.home_team.team_name,
                        "tricode": game.game_data.home_team.team_tricode,
                        "team_id": game.game_data.home_team.team_id
                    },
                    "away": {
                        "full_name": f"{game.game_data.away_team.team_city} {game.game_data.away_team.team_name}",
                        "short_name": game.game_data.away_team.team_name,
                        "tricode": game.game_data.away_team.team_tricode,
                        "team_id": game.game_data.away_team.team_id
                    }
                },
                # 存储日期时间信息，避免重复格式化
                "dates": {
                    "utc": {
                        "date": game.game_data.game_time_utc.strftime('%Y-%m-%d'),
                        "time": game.game_data.game_time_utc.strftime('%H:%M')
                    },
                    "beijing": {
                        "date": game.game_data.game_time_beijing.strftime('%Y-%m-%d'),
                        "time": game.game_data.game_time_beijing.strftime('%H:%M')
                    }
                },
                # 存储比赛状态信息
                "game_status": game.get_game_status()
            }

            # 2. 准备完整的数据结构，使用上下文字典
            return {
                "game_info": GameDisplayService._prepare_ai_game_info(game, context),
                "game_status": GameDisplayService._prepare_ai_game_status(context),
                "game_result": GameDisplayService._prepare_ai_game_result(game, context),
                "team_stats": GameDisplayService._prepare_ai_team_stats(game, context),
                "player_stats": GameDisplayService._prepare_ai_player_stats(game, player_id),
                "events": GameDisplayService._prepare_ai_events(game, player_id)
            }
        except Exception as e:
            self.logger.error(f"准备AI数据失败: {str(e)}")
            return {"error": f"准备AI数据失败: {str(e)}"}

    @staticmethod
    def _prepare_ai_game_info(game: Game, context: Dict[str, Any]) -> Dict[str, Any]:
        """准备比赛基本信息的AI友好格式"""
        game_data = game.game_data

        # 直接从上下文中获取球队和日期信息
        home_team_full = context["team_names"]["home"]["full_name"]
        away_team_full = context["team_names"]["away"]["full_name"]

        # 构建场馆信息和上下文说明
        arena_info = {
            "name": game_data.arena.arena_name,
            "city": game_data.arena.arena_city,
            "state": game_data.arena.arena_state,
            "full_location": f"{game_data.arena.arena_name}, {game_data.arena.arena_city}, {game_data.arena.arena_state}"
        }

        context_text = f"{home_team_full}主场迎战{away_team_full}，比赛于北京时间{context['dates']['beijing']['date']} {context['dates']['beijing']['time']}在{arena_info['name']}进行"

        # 直接使用字典字面量返回
        return {
            "game_id": game_data.game_id,
            "teams": {
                "home": context["team_names"]["home"],
                "away": context["team_names"]["away"]
            },
            "date": {
                "utc": context["dates"]["utc"]["date"],
                "time_utc": context["dates"]["utc"]["time"],
                "beijing": context["dates"]["beijing"]["date"],
                "time_beijing": context["dates"]["beijing"]["time"]
            },
            "arena": arena_info,
            "context": context_text
        }

    @staticmethod
    def _prepare_ai_game_status(context: Dict[str, Any]) -> Dict[str, Any]:
        """准备比赛状态的AI友好格式"""
        game_status = context["game_status"]
        score_diff = abs(game_status['home_score'] - game_status['away_score'])

        # 构建状态上下文
        if game_status['status_text'] == '进行中':
            if game_status['current_period'] <= 2:
                phase = "上半场"
            elif game_status['current_period'] <= 4:
                phase = "下半场"
            else:
                phase = "加时赛"

            leader = context["team_names"]["home"]["tricode"] if game_status['home_score'] > game_status[
                'away_score'] else context["team_names"]["away"]["tricode"]
            status_context = f"比赛{phase}{game_status['period_name']}，{leader}领先{score_diff}分，剩余时间{game_status['time_remaining']}"
        else:
            status_context = f"比赛已{game_status['status_text']}"

        # 直接使用字典字面量返回
        return {
            "status": game_status['status_text'],
            "period": {
                "current": game_status['current_period'],
                "name": game_status['period_name']
            },
            "time_remaining": game_status['time_remaining'],
            "score": {
                "home": {
                    "team": context["team_names"]["home"]["tricode"],
                    "points": game_status['home_score']
                },
                "away": {
                    "team": context["team_names"]["away"]["tricode"],
                    "points": game_status['away_score']
                },
                "leader": "home" if game_status['home_score'] > game_status['away_score'] else "away",
                "differential": score_diff
            },
            "bonus": {
                "home": game_status['home_bonus'],
                "away": game_status['away_bonus']
            },
            "timeouts": {
                "home": game_status['home_timeouts'],
                "away": game_status['away_timeouts']
            },
            "context": status_context
        }

    @staticmethod
    def _prepare_ai_game_result(game: Game, context: Dict[str, Any]) -> Dict[str, Any]:
        """准备比赛结果的AI友好格式"""
        game_data = game.game_data

        # 如果比赛未结束，返回空
        if game_data.game_status != GameStatusEnum.FINISHED:
            return {}

        # 从上下文获取主队和客队信息
        home_team = context["team_names"]["home"]
        away_team = context["team_names"]["away"]

        home_score = int(game_data.home_team.score)
        away_score = int(game_data.away_team.score)

        # 确定获胜方
        if home_score > away_score:
            winner = {
                "team_id": home_team["team_id"],
                "team_tricode": home_team["tricode"],
                "team_name": home_team["full_name"],
                "score": home_score
            }
            loser = {
                "team_id": away_team["team_id"],
                "team_tricode": away_team["tricode"],
                "team_name": away_team["full_name"],
                "score": away_score
            }
        else:
            winner = {
                "team_id": away_team["team_id"],
                "team_tricode": away_team["tricode"],
                "team_name": away_team["full_name"],
                "score": away_score
            }
            loser = {
                "team_id": home_team["team_id"],
                "team_tricode": home_team["tricode"],
                "team_name": home_team["full_name"],
                "score": home_score
            }

        # 计算比分差距
        point_diff = winner["score"] - loser["score"]

        result_context = f"{winner['team_name']} {winner['score']}-{loser['score']} 战胜 {loser['team_name']}"

        # 直接使用字典字面量返回
        return {
            "winner": winner,
            "loser": loser,
            "score_difference": point_diff,
            "final_score": f"{winner['team_tricode']} {winner['score']} - {loser['team_tricode']} {loser['score']}",
            "attendance": {
                "count": game_data.attendance,
                "sellout": game_data.sellout == "1"
            },
            "duration": game_data.duration,
            "context": result_context
        }

    @staticmethod
    def _prepare_ai_team_stats(game: Game, context: Dict[str, Any]) -> Dict[str, Any]:
        """准备球队统计数据的AI友好格式"""
        game_data = game.game_data

        # 准备主队统计数据
        home_stats = GameDisplayService._prepare_single_team_ai_stats(game_data.home_team, True, context)
        # 准备客队统计数据
        away_stats = GameDisplayService._prepare_single_team_ai_stats(game_data.away_team, False, context)

        # 直接使用字典字面量返回
        return {
            "home": home_stats,
            "away": away_stats
        }

    @staticmethod
    def _prepare_single_team_ai_stats(team: TeamInGame, is_home: bool, context: Dict[str, Any]) -> Dict[str, Any]:
        """准备单个球队的AI友好统计数据"""
        stats = team.statistics
        team_context = context["team_names"]["home" if is_home else "away"]

        # 直接使用字典字面量返回
        return {
            "basic": {
                "team_id": team_context["team_id"],
                "team_name": team_context["full_name"],
                "team_tricode": team_context["tricode"],
                "is_home": is_home,
                "points": stats.points,
                "points_against": stats.points_against
            },
            "shooting": {
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
                },
                "true_shooting_percentage": stats.true_shooting_percentage
            },
            "rebounds": {
                "total": stats.rebounds_total,
                "offensive": stats.rebounds_offensive,
                "defensive": stats.rebounds_defensive,
                "team": stats.rebounds_team,
                "team_offensive": stats.rebounds_team_offensive,
                "team_defensive": stats.rebounds_team_defensive,
                "personal": stats.rebounds_personal
            },
            "offense": {
                "assists": stats.assists,
                "assists_turnover_ratio": stats.assists_turnover_ratio,
                "bench_points": stats.bench_points,
                "points_in_the_paint": {
                    "points": stats.points_in_the_paint,
                    "made": stats.points_in_the_paint_made,
                    "attempted": stats.points_in_the_paint_attempted,
                    "percentage": stats.points_in_the_paint_percentage
                },
                "fast_break_points": {
                    "points": stats.points_fast_break,
                    "made": stats.fast_break_points_made,
                    "attempted": stats.fast_break_points_attempted,
                    "percentage": stats.fast_break_points_percentage
                },
                "second_chance_points": {
                    "points": stats.points_second_chance,
                    "made": stats.second_chance_points_made,
                    "attempted": stats.second_chance_points_attempted,
                    "percentage": stats.second_chance_points_percentage
                },
                "points_from_turnovers": stats.points_from_turnovers
            },
            "defense": {
                "steals": stats.steals,
                "blocks": stats.blocks,
                "blocks_received": stats.blocks_received,
                "turnovers": {
                    "total": stats.turnovers_total,
                    "personal": stats.turnovers,
                    "team": stats.turnovers_team
                }
            },
            "fouls": {
                "personal": stats.fouls_personal,
                "offensive": stats.fouls_offensive,
                "technical": stats.fouls_technical,
                "team": stats.fouls_team,
                "team_technical": stats.fouls_team_technical
            },
            "lead_data": {
                "time_leading": stats.time_leading_calculated,
                "biggest_lead": stats.biggest_lead,
                "biggest_lead_score": stats.biggest_lead_score,
                "biggest_scoring_run": stats.biggest_scoring_run,
                "biggest_scoring_run_score": stats.biggest_scoring_run_score,
                "lead_changes": stats.lead_changes
            }
        }

    @staticmethod
    def _prepare_ai_player_stats(game: Game, player_id: Optional[int] = None) -> Dict[str, Any]:
        """准备球员统计数据的AI友好格式"""
        game_data = game.game_data
        result = {"home": [], "away": []}

        # 如果指定了球员ID
        if player_id:
            player = game.get_player_stats(player_id)
            if player and player.played == "1":
                is_home = player in game_data.home_team.players
                team_type = "home" if is_home else "away"
                player_data = GameDisplayService._prepare_single_player_ai_stats(player)
                result[team_type].append(player_data)
        else:
            # 处理主队球员
            for player in game_data.home_team.players:
                if player.played == "1":  # 只处理参与比赛的球员
                    result["home"].append(GameDisplayService._prepare_single_player_ai_stats(player))

            # 处理客队球员
            for player in game_data.away_team.players:
                if player.played == "1":  # 只处理参与比赛的球员
                    result["away"].append(GameDisplayService._prepare_single_player_ai_stats(player))

            # 按得分排序
            result["home"] = sorted(result["home"], key=lambda x: x["basic"]["points"], reverse=True)
            result["away"] = sorted(result["away"], key=lambda x: x["basic"]["points"], reverse=True)

        return result

    @staticmethod
    def _prepare_single_player_ai_stats(player: PlayerInGame) -> Dict[str, Any]:
        """准备单个球员的AI友好统计数据"""
        stats = player.statistics
        starter_status = "首发" if player.starter == "1" else "替补"
        on_court_status = "场上" if player.on_court == "1" else "场下"

        # 直接使用字典字面量返回
        return {
            "basic": {
                "name": player.name,
                "player_id": player.person_id,
                "jersey_num": player.jersey_num,
                "position": player.position or "N/A",
                "starter": starter_status,
                "on_court": on_court_status,
                "minutes": stats.minutes_calculated,
                "points": stats.points,
                "plus_minus": stats.plus_minus_points,
                "rebounds": stats.rebounds_total,
                "assists": stats.assists
            },
            "shooting": {
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
            },
            "rebounds": {
                "total": stats.rebounds_total,
                "offensive": stats.rebounds_offensive,
                "defensive": stats.rebounds_defensive
            },
            "other_stats": {
                "assists": stats.assists,
                "steals": stats.steals,
                "blocks": stats.blocks,
                "blocks_received": stats.blocks_received,
                "turnovers": stats.turnovers,
                "fouls": {
                    "personal": stats.fouls_personal,
                    "drawn": stats.fouls_drawn,
                    "offensive": stats.fouls_offensive,
                    "technical": stats.fouls_technical
                },
                "scoring_breakdown": {
                    "paint_points": stats.points_in_the_paint,
                    "fast_break_points": stats.points_fast_break,
                    "second_chance_points": stats.points_second_chance
                }
            }
        }

    @staticmethod
    def _prepare_ai_events(game: Game, player_id: Optional[int] = None) -> Dict[str, Any]:
        """准备比赛事件的AI友好格式，使用Game模型的filter_events方法"""
        if not game.play_by_play or not game.play_by_play.actions:
            return {"data": [], "count": 0}

        # 使用Game模型的filter_events方法直接获取筛选后的事件
        filtered_events = game.filter_events(player_id=player_id)

        # 将事件转换为字典格式
        events_data = []
        for event in filtered_events:
            # 创建基础事件数据
            event_dict = {
                "action_number": event.action_number,
                "period": event.period,
                "clock": event.clock,
                "time_actual": event.time_actual,
                "action_type": event.action_type,
                "sub_type": getattr(event, "sub_type", None),
                "description": event.description,
                "team_id": getattr(event, "team_id", None),
                "team_tricode": getattr(event, "team_tricode", None),
                "player_id": getattr(event, "person_id", None),
                "player_name": getattr(event, "player_name", None),
                "player_name_i": getattr(event, "player_name_i", None),
                "score_home": getattr(event, "score_home", None),
                "score_away": getattr(event, "score_away", None),
                "x": getattr(event, "x", None),
                "y": getattr(event, "y", None),
                "x_legacy": getattr(event, "x_legacy", None),
                "y_legacy": getattr(event, "y_legacy", None)
            }

            # 根据事件类型添加特定属性
            action_type = event.action_type

            if action_type in ["2pt", "3pt"]:  # 投篮事件
                event_dict.update({
                    "shot_result": getattr(event, "shot_result", None),
                    "shot_distance": getattr(event, "shot_distance", None),
                    "area": getattr(event, "area", None),
                    "area_detail": getattr(event, "area_detail", None),
                    "side": getattr(event, "side", None),
                    "is_field_goal": getattr(event, "is_field_goal", 1),
                    "qualifiers": getattr(event, "qualifiers", [])
                })

                # 助攻信息
                if hasattr(event, "assist_person_id") and event.assist_person_id:
                    event_dict["assist_person_id"] = event.assist_person_id
                    event_dict["assist_player_name_initial"] = getattr(event, "assist_player_name_initial", None)

                # 盖帽信息
                if hasattr(event, "block_person_id") and event.block_person_id:
                    event_dict["block_person_id"] = event.block_person_id
                    event_dict["block_player_name"] = getattr(event, "block_player_name", None)

            elif action_type == "freethrow":  # 罚球事件
                event_dict.update({
                    "shot_result": getattr(event, "shot_result", None),
                    "is_field_goal": getattr(event, "is_field_goal", 0),
                    "points_total": getattr(event, "points_total", None)
                })

            elif action_type == "rebound":  # 篮板事件
                event_dict.update({
                    "rebound_total": getattr(event, "rebound_total", None),
                    "rebound_defensive_total": getattr(event, "rebound_defensive_total", None),
                    "rebound_offensive_total": getattr(event, "rebound_offensive_total", None),
                    "shot_action_number": getattr(event, "shot_action_number", None)
                })

            elif action_type == "turnover":  # 失误事件
                event_dict.update({
                    "turnover_total": getattr(event, "turnover_total", None),
                    "descriptor": getattr(event, "descriptor", None)
                })

                # 抢断信息
                if hasattr(event, "steal_person_id") and event.steal_person_id:
                    event_dict["steal_person_id"] = event.steal_person_id
                    event_dict["steal_player_name"] = getattr(event, "steal_player_name", None)

            elif action_type == "foul":  # 犯规事件
                event_dict.update({
                    "descriptor": getattr(event, "descriptor", None)
                })

                # 被犯规信息
                if hasattr(event, "foul_drawn_person_id") and event.foul_drawn_person_id:
                    event_dict["foul_drawn_person_id"] = event.foul_drawn_person_id
                    event_dict["foul_drawn_player_name"] = getattr(event, "foul_drawn_player_name", None)

                # 裁判信息
                if hasattr(event, "official_id") and event.official_id:
                    event_dict["official_id"] = event.official_id

            elif action_type == "violation":  # 违例事件
                if hasattr(event, "official_id") and event.official_id:
                    event_dict["official_id"] = event.official_id

            elif action_type == "substitution":  # 换人事件
                event_dict.update({
                    "incoming_person_id": getattr(event, "incoming_person_id", None),
                    "incoming_player_name": getattr(event, "incoming_player_name", None),
                    "incoming_player_name_i": getattr(event, "incoming_player_name_i", None),
                    "outgoing_person_id": getattr(event, "outgoing_person_id", None),
                    "outgoing_player_name": getattr(event, "outgoing_player_name", None),
                    "outgoing_player_name_i": getattr(event, "outgoing_player_name_i", None)
                })

            elif action_type == "jumpball":  # 跳球事件
                event_dict.update({
                    "jump_ball_won_person_id": getattr(event, "jump_ball_won_person_id", None),
                    "jump_ball_won_player_name": getattr(event, "jump_ball_won_player_name", None),
                    "jump_ball_lost_person_id": getattr(event, "jump_ball_lost_person_id", None),
                    "jump_ball_lost_player_name": getattr(event, "jump_ball_lost_player_name", None),
                    "jump_ball_recovered_person_id": getattr(event, "jump_ball_recovered_person_id", None),
                    "jump_ball_recovered_name": getattr(event, "jump_ball_recovered_name", None)
                })

            events_data.append(event_dict)

        # 按照时间顺序排序（先按照节数，再按比赛时钟）
        events_data.sort(key=lambda x: (x["period"], x["clock"], x["action_number"]))

        return {
            "data": events_data,
            "count": len(events_data)
        }