"""NBA 数据服务主程序 - 重构优化版

实现以下核心功能：
1. 比赛基础信息查询
2. 投篮图表生成
3. 视频处理功能
4. 发布内容到微博
5. AI分析比赛数据

用法:
    python main.py [options]
"""
import argparse
import re
import sys
import logging
from pathlib import Path
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from abc import ABC, abstractmethod
from dotenv import load_dotenv

from config.nba_config import NBAConfig
# 导入业务逻辑函数和服务
from nba.services.nba_service import NBAService, NBAServiceConfig, ServiceStatus
from nba.services.game_video_service import VideoConfig
from utils.video_converter import VideoProcessConfig
from utils.logger_handler import AppLogger
from utils.ai_processor import AIProcessor, AIConfig, AIProvider, AIModel
from weibo.weibo_post_service import WeiboPostService
from weibo.weibo_content_generator import WeiboContentGenerator


# 定义运行模式
class RunMode(Enum):
    """应用程序运行模式"""
    INFO = "info"  # 只显示比赛信息
    CHART = "chart"  # 只生成图表
    VIDEO = "video"  # 处理所有视频
    VIDEO_TEAM = "video-team"  # 只处理球队视频
    VIDEO_PLAYER = "video-player"  # 只处理球员视频
    VIDEO_ROUNDS = "video-rounds"  # 处理球员视频的回合GIF
    WEIBO = "weibo"  # 执行所有微博发布功能
    WEIBO_TEAM = "weibo-team"  # 只发布球队集锦视频
    WEIBO_PLAYER = "weibo-player"  # 只发布球员集锦视频
    WEIBO_CHART = "weibo-chart"  # 只发布球员投篮图
    WEIBO_TEAM_CHART = "weibo-team-chart"  # 只发布球队投篮图
    WEIBO_ROUND = "weibo-round"  # 只发布球员回合解说和GIF
    AI = "ai"  # 只运行AI分析
    ALL = "all"  # 执行所有功能


# 命令模式的基类
class NBACommand(ABC):
    """NBA命令基类"""

    @abstractmethod
    def execute(self, app: 'NBACommandLineApp') -> None:
        """执行命令"""
        pass


class InfoCommand(NBACommand):
    """比赛信息查询命令"""

    def execute(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 比赛基本信息 ===")

        # 初始化变量，防止引用前未定义的问题
        player_id = None

        # 获取比赛数据
        game = app.nba_service.data_service.get_game(app.nba_service.config.default_team)
        if not game:
            print(f"  获取比赛信息失败")
            return

        # 1. 准备上下文数据 - 供多个内部方法使用
        context = {
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
            "status": {
                "status_text": game.game_data.game_status_text,
                "period": game.game_data.period,
                "period_name": f"Period {game.game_data.period}",
                "clock": str(game.game_data.game_clock),
                "home_score": int(game.game_data.home_team.score),
                "away_score": int(game.game_data.away_team.score)
            }
        }

        # 2. 直接使用_prepare_ai_game_info获取比赛基本信息
        game_info = game._prepare_ai_game_info(context)

        # 显示比赛基本信息
        if game_info:
            basic_info = game_info.get("basic", {})
            print("\n比赛信息:")
            print(f"  比赛ID: {basic_info.get('game_id', 'N/A')}")
            teams = basic_info.get("teams", {})
            print(
                f"  对阵: {teams.get('home', {}).get('full_name', 'N/A')} vs {teams.get('away', {}).get('full_name', 'N/A')}")
            date_info = basic_info.get("date", {})
            print(f"  日期: {date_info.get('beijing', 'N/A')}")
            print(f"  时间: {date_info.get('time_beijing', 'N/A')}")
            arena = basic_info.get("arena", {})
            print(f"  场馆: {arena.get('full_location', 'N/A')}")

            # 显示首发阵容信息
            starters = game_info.get("starters", {})
            print("\n首发阵容:")
            print(f"  {teams.get('home', {}).get('tricode', 'N/A')}首发:")
            home_starters = starters.get("home", [])
            for i, player in enumerate(home_starters, 1):
                print(
                    f"    {i}. {player.get('name', 'N/A')} - {player.get('position', 'N/A')} #{player.get('jersey_num', 'N/A')}")

            print(f"  {teams.get('away', {}).get('tricode', 'N/A')}首发:")
            away_starters = starters.get("away", [])
            for i, player in enumerate(away_starters, 1):
                print(
                    f"    {i}. {player.get('name', 'N/A')} - {player.get('position', 'N/A')} #{player.get('jersey_num', 'N/A')}")

            # 显示伤病名单
            injuries = game_info.get("injuries", {})
            print("\n伤病名单:")
            home_injuries = injuries.get("home", [])
            if home_injuries:
                print(f"  {teams.get('home', {}).get('tricode', 'N/A')}伤病球员:")
                for i, player in enumerate(home_injuries, 1):
                    reason = player.get('reason', 'Unknown')
                    description = player.get('description', '')
                    desc_text = f" - {description}" if description else ""
                    print(f"    {i}. {player.get('name', 'N/A')} ({reason}){desc_text}")
            else:
                print(f"  {teams.get('home', {}).get('tricode', 'N/A')}无伤病球员")

            away_injuries = injuries.get("away", [])
            if away_injuries:
                print(f"  {teams.get('away', {}).get('tricode', 'N/A')}伤病球员:")
                for i, player in enumerate(away_injuries, 1):
                    reason = player.get('reason', 'Unknown')
                    description = player.get('description', '')
                    desc_text = f" - {description}" if description else ""
                    print(f"    {i}. {player.get('name', 'N/A')} ({reason}){desc_text}")
            else:
                print(f"  {teams.get('away', {}).get('tricode', 'N/A')}无伤病球员")

            # 显示比赛状态信息
            status = game_info.get("status", {})
            print("\n比赛状态:")
            print(f"  当前状态: {status.get('state', 'N/A')}")
            print(f"  当前节数: {status.get('period', {}).get('name', 'N/A')}")
            print(f"  剩余时间: {status.get('time_remaining', 'N/A')}")
            score = status.get("score", {})
            print(
                f"  比分: {score.get('home', {}).get('team', 'N/A')} {score.get('home', {}).get('points', 0)} - {score.get('away', {}).get('team', 'N/A')} {score.get('away', {}).get('points', 0)}")

        # 3. 直接使用_prepare_ai_game_result获取比赛结果
        game_result = game._prepare_ai_game_result(context)

        # 如果比赛已结束，显示比赛结果
        if game_result:
            print("\n比赛结果:")
            print(f"  最终比分: {game_result.get('final_score', 'N/A')}")
            print(
                f"  获胜方: {game_result.get('winner', {}).get('team_name', 'N/A')} ({game_result.get('winner', {}).get('score', 0)}分)")
            print(
                f"  失利方: {game_result.get('loser', {}).get('team_name', 'N/A')} ({game_result.get('loser', {}).get('score', 0)}分)")
            print(f"  分差: {game_result.get('score_difference', 0)}分")
            print(f"  观众数: {game_result.get('attendance', {}).get('count', 'N/A')}")
            print(f"  比赛时长: {game_result.get('duration', 'N/A')}分钟")

        # 4. 使用_prepare_single_team_ai_stats获取团队统计
        team_stats = {
            "home": game._prepare_single_team_ai_stats(game.game_data.home_team, True, context),
            "away": game._prepare_single_team_ai_stats(game.game_data.away_team, False, context)
        }

        # 显示球队统计对比
        print("\n球队统计数据对比:")
        home = team_stats["home"]
        away = team_stats["away"]
        print(f"  {context['team_names']['home']['tricode']} vs {context['team_names']['away']['tricode']}")
        print(
            f"  投篮: {home['shooting']['field_goals']['made']}/{home['shooting']['field_goals']['attempted']} ({home['shooting']['field_goals']['percentage'] or 0:.1%}) vs {away['shooting']['field_goals']['made']}/{away['shooting']['field_goals']['attempted']} ({away['shooting']['field_goals']['percentage'] or 0:.1%})")
        print(
            f"  三分: {home['shooting']['three_pointers']['made']}/{home['shooting']['three_pointers']['attempted']} ({home['shooting']['three_pointers']['percentage'] or 0:.1%}) vs {away['shooting']['three_pointers']['made']}/{away['shooting']['three_pointers']['attempted']} ({away['shooting']['three_pointers']['percentage'] or 0:.1%})")
        print(f"  篮板: {home['rebounds']['total']} vs {away['rebounds']['total']}")
        print(f"  助攻: {home['offense']['assists']} vs {away['offense']['assists']}")
        print(f"  失误: {home['defense']['turnovers']['total']} vs {away['defense']['turnovers']['total']}")
        print(f"  抢断: {home['defense']['steals']} vs {away['defense']['steals']}")
        print(f"  盖帽: {home['defense']['blocks']} vs {away['defense']['blocks']}")

        # 5. 如果指定了球员，显示球员统计数据
        if app.args.player:
            print(f"\n=== {app.args.player} 球员详细数据 ===")
            player_id = app.nba_service.get_player_id_by_name(app.args.player)

            if player_id:
                # 获取球员数据
                player_found = False
                for team_type, team in [('home', game.game_data.home_team), ('away', game.game_data.away_team)]:
                    for player in team.players:
                        if player.person_id == player_id:
                            if player.played == "1":
                                # 这里无需遍历，直接使用_prepare_single_player_ai_stats
                                player_stats = game._prepare_single_player_ai_stats(player)
                                player_found = True

                                # 显示球员统计
                                basic = player_stats["basic"]
                                print(f"\n{basic['name']} 基本数据:")
                                print(
                                    f"  位置: {basic.get('position', 'N/A')} | 球衣号: {basic.get('jersey_num', 'N/A')}")
                                print(
                                    f"  上场时间: {basic.get('minutes', 'N/A')} | 首发/替补: {'首发' if player.starter == '1' else '替补'}")
                                print(
                                    f"  得分: {basic.get('points', 0)} | 篮板: {basic.get('rebounds', 0)} | 助攻: {basic.get('assists', 0)}")
                                print(f"  +/-: {basic.get('plus_minus', 0)}")

                                shooting = player_stats.get("shooting", {})
                                print("\n投篮数据:")
                                fg = shooting.get("field_goals", {})
                                print(
                                    f"  投篮: {fg.get('made', 0)}/{fg.get('attempted', 0)} ({fg.get('percentage', 0) or 0:.1%})")
                                three = shooting.get("three_pointers", {})
                                print(
                                    f"  三分: {three.get('made', 0)}/{three.get('attempted', 0)} ({three.get('percentage', 0) or 0:.1%})")
                                ft = shooting.get("free_throws", {})
                                print(
                                    f"  罚球: {ft.get('made', 0)}/{ft.get('attempted', 0)} ({ft.get('percentage', 0) or 0:.1%})")

                                other = player_stats.get("other_stats", {})
                                print("\n其他数据:")
                                print(f"  抢断: {other.get('steals', 0)} | 盖帽: {other.get('blocks', 0)}")
                                print(
                                    f"  失误: {other.get('turnovers', 0)} | 个人犯规: {other.get('fouls', {}).get('personal', 0)}")

                                # 球员得分分布
                                scoring = other.get("scoring_breakdown", {})
                                print("\n得分分布:")
                                print(
                                    f"  禁区得分: {scoring.get('paint_points', 0)} | 快攻得分: {scoring.get('fast_break_points', 0)} | 二次进攻: {scoring.get('second_chance_points', 0)}")
                            else:
                                # 球员未上场
                                player_found = True
                                not_playing_reason = player.not_playing_reason.value if player.not_playing_reason else "未知原因"
                                description = f" - {player.not_playing_description}" if player.not_playing_description else ""
                                print(f"\n{player.name} 未参与本场比赛")
                                print(f"  原因: {not_playing_reason}{description}")
                            break
                    if player_found:
                        break

                if not player_found:
                    print(f"  未找到 {app.args.player} 的数据")
            else:
                print(f"  未找到球员 {app.args.player}")

        # 6. 使用_prepare_ai_events获取事件数据 - 直接调用内部方法，避免重复查询
        events_data = game._prepare_ai_events(player_id)
        events = events_data.get("data", [])

        if events:
            print("\n=== 比赛事件时间线 ===")
            print(f"\n共获取到 {len(events)} 个事件")

            # 事件分类
            events_by_type = {}
            for event in events:
                event_type = event.get("action_type", "unknown")
                if event_type not in events_by_type:
                    events_by_type[event_type] = []
                events_by_type[event_type].append(event)

            # 统计事件类型
            print("\n事件类型统计:")
            for event_type, event_list in sorted(events_by_type.items(), key=lambda x: len(x[1]), reverse=True):
                print(f"  {event_type}: {len(event_list)}个")

            # 显示重要得分事件
            scoring_events = []
            for event_type in ["2pt", "3pt"]:
                if event_type in events_by_type:
                    scoring_events.extend(events_by_type[event_type])

            if scoring_events:
                # 筛选命中的投篮
                made_shots = [e for e in scoring_events if e.get("shot_result") == "Made"]
                # 按时间排序并取前10个
                important_shots = sorted(made_shots, key=lambda x: (x.get("period", 0), x.get("clock", "")))[:10]

                if important_shots:
                    print("\n重要得分事件:")
                    for i, event in enumerate(important_shots, 1):
                        period = event.get("period", "")
                        clock = event.get("clock", "")
                        action_type = event.get("action_type", "")
                        player_name = event.get("player_name", "未知球员")
                        shot_distance = event.get("shot_distance", "")
                        score = f"{event.get('score_away', '')} - {event.get('score_home', '')}"

                        shot_type = "三分球" if action_type == "3pt" else "两分球"
                        description = f"{player_name} {shot_distance}英尺{shot_type}"

                        # 助攻信息
                        if event.get("assist_person_id"):
                            description += f" (由 {event.get('assist_player_name_initial', '')} 助攻)"

                        print(f"{i}. 第{period}节 {clock} - {description}, 比分: {score}")


class ChartCommand(NBACommand):
    """图表生成命令"""

    def execute(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 投篮图表演示 ===")

        app.chart_paths = app.nba_service.generate_shot_charts(
            team=app.args.team,
            player_name=app.args.player,
            chart_type="both",  # 同时生成球队和球员图表
            shot_outcome="made_only",  # 默认仅显示命中的投篮
            impact_type="full_impact"  # 默认显示完整的得分影响力
        )


class VideoCommand(NBACommand):
    """视频处理命令"""

    def execute(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 处理所有视频 ===")
        self._process_team_video(app)
        self._process_player_video(app)
        self._process_round_gifs(app)

    def _process_team_video(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 处理球队集锦视频 ===")
        team_videos = app.nba_service.get_team_highlights(team=app.args.team, merge=True)
        if team_videos:
            if "merged" in team_videos:
                app.video_paths["team_video"] = team_videos["merged"]
                print(f"✓ 已生成球队合并视频: {team_videos['merged']}")
            else:
                print(f"✓ 获取到 {len(team_videos)} 个球队视频片段")
        else:
            print("× 获取球队集锦视频失败")

    def _process_player_video(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 处理球员集锦视频 ===")
        player_videos = app.nba_service.get_player_highlights(
            player_name=app.args.player,
            merge=True
        )
        if player_videos:
            if "video_merged" in player_videos:
                app.video_paths["player_video"] = player_videos["video_merged"]
                print(f"✓ 已生成球员合并视频: {player_videos['video_merged']}")
            else:
                print(f"✓ 获取到 {len(player_videos.get('videos', {}))} 个分类视频")
        else:
            print("× 获取球员集锦视频失败")

    def _process_round_gifs(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 处理球员回合GIF ===")
        app.round_gifs = app.nba_service.get_player_round_gifs(
            player_name=app.args.player
        )


class VideoTeamCommand(NBACommand):
    """球队视频处理命令"""

    def execute(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 处理球队集锦视频 ===")
        team_videos = app.nba_service.get_team_highlights(team=app.args.team, merge=True)
        if team_videos:
            if "merged" in team_videos:
                app.video_paths["team_video"] = team_videos["merged"]
                print(f"✓ 已生成球队合并视频: {team_videos['merged']}")
            else:
                print(f"✓ 获取到 {len(team_videos)} 个球队视频片段")
        else:
            print("× 获取球队集锦视频失败")


class VideoPlayerCommand(NBACommand):
    """球员视频处理命令"""

    def execute(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 处理球员集锦视频 ===")
        player_videos = app.nba_service.get_player_highlights(
            player_name=app.args.player,
            merge=True
        )
        if player_videos:
            if "video_merged" in player_videos:
                app.video_paths["player_video"] = player_videos["video_merged"]
                print(f"✓ 已生成球员合并视频: {player_videos['video_merged']}")
            else:
                print(f"✓ 获取到 {len(player_videos.get('videos', {}))} 个分类视频")
        else:
            print("× 获取球员集锦视频失败")


class VideoRoundsCommand(NBACommand):
    """球员回合GIF处理命令"""

    def execute(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 处理球员回合GIF ===")
        app.round_gifs = app.nba_service.get_player_round_gifs(
            player_name=app.args.player
        )


class WeiboCommand(NBACommand):
    """微博发布命令"""

    def execute(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 微博发布 ===")

        # 检查微博发布所需的文件是否存在
        if not app._check_required_files_for_weibo(RunMode.WEIBO):
            print("× 微博发布所需文件不存在，请先生成相应文件")
            return

        # 执行统一发布 - 使用新的统一接口
        result = app.weibo_service.post_all_content(
            app.nba_service,
            app.video_paths,
            app.chart_paths,
            app.args.player
        )

        if result:
            print("\n✓ 所有内容已成功发布到微博!")
        else:
            print("\n× 部分或全部内容发布失败，请查看日志获取详细信息")


class WeiboTeamCommand(NBACommand):
    """微博发布球队视频命令"""

    def execute(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 微博发布球队集锦视频 ===")

        # 检查是否有球队视频
        if not app._check_required_files_for_weibo(RunMode.WEIBO_TEAM):
            return

        # 获取基础数据
        game_data = app.nba_service.data_service.get_game(app.nba_service.config.default_team)
        if not game_data:
            print(f"  获取比赛信息失败")
            return

        game_ai_data = game_data.prepare_ai_data()
        if "error" in game_ai_data:
            print(f"  获取AI友好数据失败: {game_ai_data['error']}")
            return

        # 使用统一接口发布球队集锦视频
        if "team_video" in app.video_paths:
            result = app.weibo_service.post_content(
                content_type="team_video",
                media_path=app.video_paths["team_video"],
                data=game_ai_data
            )

            if result and result.get("success"):
                print(f"✓ 球队集锦视频发布成功: {result.get('message', '')}")
            else:
                print(f"× 球队集锦视频发布失败: {result.get('message', '未知错误')}")


class WeiboPlayerCommand(NBACommand):
    """微博发布球员视频命令"""

    def execute(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 微博发布球员集锦视频 ===")

        # 检查是否有球员视频
        if not app._check_required_files_for_weibo(RunMode.WEIBO_PLAYER):
            return

        # 获取基础数据
        game_data = app.nba_service.data_service.get_game(app.nba_service.config.default_team)
        if not game_data:
            print(f"  获取比赛信息失败")
            return

        # 准备球员数据
        player_id = app.nba_service.get_player_id_by_name(app.args.player)
        if not player_id:
            print(f"  未找到球员: {app.args.player}")
            return

        player_data = game_data.prepare_ai_data(player_id=player_id)
        if "error" in player_data:
            print(f"  获取球员AI友好数据失败: {player_data['error']}")
            return

        # 使用统一接口发布球员集锦视频
        if "player_video" in app.video_paths:
            result = app.weibo_service.post_content(
                content_type="player_video",
                media_path=app.video_paths["player_video"],
                data=player_data,
                player_name=app.args.player
            )

            if result and result.get("success"):
                print(f"✓ 球员集锦视频发布成功: {result.get('message', '')}")
            else:
                print(f"× 球员集锦视频发布失败: {result.get('message', '未知错误')}")


class WeiboChartCommand(NBACommand):
    """微博发布球员投篮图命令"""

    def execute(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 微博发布球员投篮图 ===")

        # 检查是否有球员投篮图
        if not app._check_required_files_for_weibo(RunMode.WEIBO_CHART):
            return

        # 获取基础数据
        game_data = app.nba_service.data_service.get_game(app.nba_service.config.default_team)
        if not game_data:
            print(f"  获取比赛信息失败")
            return

        # 准备球员数据
        player_id = app.nba_service.get_player_id_by_name(app.args.player)
        if not player_id:
            print(f"  未找到球员: {app.args.player}")
            return

        player_data = game_data.prepare_ai_data(player_id=player_id)
        if "error" in player_data:
            print(f"  获取球员AI友好数据失败: {player_data['error']}")
            return

        # 使用统一接口发布球员投篮图
        if "player_chart" in app.chart_paths:
            result = app.weibo_service.post_content(
                content_type="player_chart",
                media_path=app.chart_paths["player_chart"],
                data=player_data,
                player_name=app.args.player
            )

            if result and result.get("success"):
                print(f"✓ 球员投篮图发布成功: {result.get('message', '')}")
            else:
                print(f"× 球员投篮图发布失败: {result.get('message', '未知错误')}")


class WeiboTeamChartCommand(NBACommand):
    """微博发布球队投篮图命令"""

    def execute(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 微博发布球队投篮图 ===")

        # 检查是否有球队投篮图
        if not app._check_required_files_for_weibo(RunMode.WEIBO_TEAM_CHART):
            return

        # 获取基础数据
        game_data = app.nba_service.data_service.get_game(app.nba_service.config.default_team)
        if not game_data:
            print(f"  获取比赛信息失败")
            return

        game_ai_data = game_data.prepare_ai_data()
        if "error" in game_ai_data:
            print(f"  获取AI友好数据失败: {game_ai_data['error']}")
            return

        # 使用统一接口发布球队投篮图
        if "team_chart" in app.chart_paths:
            result = app.weibo_service.post_content(
                content_type="team_chart",
                media_path=app.chart_paths["team_chart"],
                data=game_ai_data,
                team_name=app.args.team
            )

            if result and result.get("success"):
                print(f"✓ 球队投篮图发布成功: {result.get('message', '')}")
            else:
                print(f"× 球队投篮图发布失败: {result.get('message', '未知错误')}")


class WeiboRoundCommand(NBACommand):
    """微博发布球员回合解说和GIF命令"""

    def execute(self, app: 'NBACommandLineApp') -> None:
        print("\n=== 微博发布球员回合解说和GIF ===")

        # 检查是否有球员回合GIF
        if not app._check_required_files_for_weibo(RunMode.WEIBO_ROUND):
            return

        # 获取基础数据
        game_data = app.nba_service.data_service.get_game(app.nba_service.config.default_team)
        if not game_data:
            print(f"  获取比赛信息失败")
            return

        # 准备球员数据
        player_id = app.nba_service.get_player_id_by_name(app.args.player)
        if not player_id:
            print(f"  未找到球员: {app.args.player}")
            return

        player_data = game_data.prepare_ai_data(player_id=player_id)
        if "error" in player_data:
            print(f"  获取球员AI友好数据失败: {player_data['error']}")
            return

        # 使用统一接口发布球员回合解说和GIF
        result = app.weibo_service.post_content(
            content_type="round_analysis",
            media_path=app.round_gifs,
            data=player_data,
            player_name=app.args.player,
            nba_service=app.nba_service
        )

        if result and result.get("success"):
            print(f"✓ 球员回合解说和GIF发布成功: {result.get('message', '')}")
        else:
            print(f"× 球员回合解说和GIF发布失败: {result.get('message', '未知错误')}")


class AICommand(NBACommand):
    """AI分析命令"""

    def execute(self, app: 'NBACommandLineApp') -> None:
        print("\n=== AI分析结果 ===")

        if not app.ai_processor or not app.content_generator:
            print("  × AI处理器或内容生成器未初始化，跳过分析")
            return

        try:
            print("\n正在获取结构化数据并进行AI分析，这可能需要一些时间...")

            # 获取比赛数据
            game_data = app.nba_service.data_service.get_game(app.args.team)
            if not game_data:
                print(f"  获取比赛信息失败: 未找到{app.args.team}的比赛数据")
                return

            # 准备AI友好数据
            player_id = None
            if app.args.player:
                player_id = app.nba_service.get_player_id_by_name(app.args.player)

            ai_data = game_data.prepare_ai_data(player_id=player_id)

            if "error" in ai_data:
                print(f"  × 获取数据失败: {ai_data['error']}")
                return

            # 使用内容生成器进行分析
            title = app.content_generator.generate_game_title(ai_data)
            summary = app.content_generator.generate_game_summary(ai_data)

            if app.args.player:
                player_analysis = app.content_generator.generate_player_analysis(
                    ai_data, app.args.player
                )

                # 显示分析结果
                print("\n比赛标题:")
                print(f"  {title}")

                print("\n比赛摘要:")
                print(summary)

                print(f"\n{app.args.player}表现分析:")
                print(player_analysis)
            else:
                # 显示分析结果
                print("\n比赛标题:")
                print(f"  {title}")

                print("\n比赛摘要:")
                print(summary)

            print("\nAI分析完成!")

        except Exception as e:
            app.logger.error(f"AI分析功能执行失败: {e}", exc_info=True)
            print(f"  × AI分析失败: {e}")


class CompositeCommand(NBACommand):
    """组合命令，执行多个命令"""

    def __init__(self, commands: List[NBACommand]):
        self.commands = commands

    def execute(self, app: 'NBACommandLineApp') -> None:
        for command in self.commands:
            command.execute(app)


class NBACommandFactory:
    """NBA命令工厂"""

    @staticmethod
    def create_command(mode: RunMode) -> NBACommand:
        # 单一命令映射
        command_map = {
            RunMode.INFO: InfoCommand(),
            RunMode.CHART: ChartCommand(),
            RunMode.VIDEO: VideoCommand(),
            RunMode.VIDEO_TEAM: VideoTeamCommand(),
            RunMode.VIDEO_PLAYER: VideoPlayerCommand(),
            RunMode.VIDEO_ROUNDS: VideoRoundsCommand(),
            RunMode.WEIBO: WeiboCommand(),
            RunMode.WEIBO_TEAM: WeiboTeamCommand(),
            RunMode.WEIBO_PLAYER: WeiboPlayerCommand(),
            RunMode.WEIBO_CHART: WeiboChartCommand(),
            RunMode.WEIBO_TEAM_CHART: WeiboTeamChartCommand(),
            RunMode.WEIBO_ROUND: WeiboRoundCommand(),
            RunMode.AI: AICommand()
        }

        # ALL模式组合所有命令
        if mode == RunMode.ALL:
            return CompositeCommand([
                InfoCommand(),
                ChartCommand(),
                VideoCommand(),
                WeiboCommand() if not getattr(mode, 'no_weibo', False) else None,
                AICommand()
            ])

        return command_map.get(mode)


class NBACommandLineApp:
    """NBA 数据服务命令行应用程序"""

    def __init__(self):
        """初始化应用程序"""
        # 设置项目根目录
        self.root_dir = Path(__file__).parent

        # 初始化日志
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.logger.info("=== NBA数据服务初始化 ===")

        # 解析命令行参数
        self.args = self._parse_arguments()

        # 设置日志级别
        if self.args.debug:
            self._set_debug_logging()

        # 加载环境变量
        self._load_environment()

        # 初始化服务
        self.nba_service = None
        self.weibo_service = None
        self.ai_processor = None
        self.content_generator = None
        self.video_paths = {}
        self.chart_paths = {}
        self.round_gifs = {}

    def _parse_arguments(self) -> argparse.Namespace:
        """解析命令行参数"""
        parser = argparse.ArgumentParser(description="NBA 数据服务应用程序")

        parser.add_argument("--team", default="Lakers", help="指定默认球队，默认为 Lakers")
        parser.add_argument("--player", default="LeBron James", help="指定默认球员，默认为 LeBron James")
        parser.add_argument("--date", default="last", help="指定比赛日期，默认为 last 表示最近一场比赛")
        parser.add_argument("--mode", choices=[m.value for m in RunMode], default=RunMode.ALL.value,
                            help="指定运行模式，默认为 all")
        parser.add_argument("--no-weibo", action="store_true", help="不发布到微博")
        parser.add_argument("--debug", action="store_true", help="启用调试模式，输出详细日志")
        parser.add_argument("--config", help="指定配置文件")

        return parser.parse_args()

    def _set_debug_logging(self) -> None:
        """设置调试级别日志"""
        for handler in logging.root.handlers + self.logger.handlers:
            handler.setLevel(logging.DEBUG)
        self.logger.setLevel(logging.DEBUG)
        self.logger.debug("调试模式已启用")

    def _load_environment(self) -> None:
        """加载环境变量"""
        # 确保系统默认使用 UTF-8 编码
        import sys
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

        # 设置 Python 默认编码为 UTF-8
        import locale
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

        # 按优先级加载环境变量
        env_local = self.root_dir / '.env.local'
        env_default = self.root_dir / '.env'
        env_config = self.args.config and Path(self.args.config)

        if env_config and env_config.exists():
            load_dotenv(env_config)
            self.logger.info(f"从 {env_config} 加载环境变量")
        elif env_local.exists():
            load_dotenv(env_local)
            self.logger.info("从 .env.local 加载环境变量")
        elif env_default.exists():
            load_dotenv(env_default)
            self.logger.info("从 .env 加载环境变量")
        else:
            self.logger.warning("未找到环境变量文件，使用默认配置")

    def init_services(self) -> None:
        """初始化所有服务"""
        try:
            # 初始化NBA服务
            self.nba_service = self._init_nba_service()
            self._verify_nba_service_status()

            # 初始化AI处理器（需要放在WeiboContentGenerator之前）
            if self._need_ai_services():
                self.ai_processor = self._init_ai_processor()

                # 初始化内容生成器（如果AI处理器可用）
                if self.ai_processor:
                    self.content_generator = WeiboContentGenerator(
                        ai_processor=self.ai_processor,
                        logger=self.logger
                    )
                    self.logger.info("微博内容生成器初始化成功")

            # 初始化微博服务，并传入内容生成器
            if self._need_weibo_services():
                self.weibo_service = self._init_weibo_service()

            # 验证微博发布所需组件是否完整
            if self._need_weibo_services() and not self.args.no_weibo:
                if not self.weibo_service:
                    self.logger.warning("微博服务未初始化，将跳过发布功能")
                if not self.content_generator:
                    self.logger.warning("内容生成器未初始化，将跳过发布功能")

        except Exception as e:
            self.logger.error(f"服务初始化失败: {e}", exc_info=True)
            raise RuntimeError(f"服务初始化失败: {e}")

    def _need_ai_services(self) -> bool:
        """判断是否需要AI服务"""
        mode = RunMode(self.args.mode)
        ai_modes = [RunMode.AI, RunMode.WEIBO, RunMode.ALL,
                    RunMode.WEIBO_TEAM, RunMode.WEIBO_PLAYER,
                    RunMode.WEIBO_CHART, RunMode.WEIBO_ROUND,
                    RunMode.WEIBO_TEAM_CHART]
        return mode in ai_modes

    def _need_weibo_services(self) -> bool:
        """判断是否需要微博服务"""
        mode = RunMode(self.args.mode)
        weibo_modes = [RunMode.WEIBO, RunMode.ALL,
                       RunMode.WEIBO_TEAM, RunMode.WEIBO_PLAYER,
                       RunMode.WEIBO_CHART, RunMode.WEIBO_ROUND,
                       RunMode.WEIBO_TEAM_CHART]
        return mode in weibo_modes and not self.args.no_weibo

    def _init_nba_service(self) -> NBAService:
        """初始化 NBA 服务"""
        self.logger.info("初始化 NBA 服务...")

        # 基础配置
        nba_config = NBAServiceConfig(
            default_team=self.args.team,
            default_player=self.args.player,
            date_str=self.args.date
        )

        # 视频配置
        video_config = VideoConfig()

        # 视频处理配置
        video_process_config = VideoProcessConfig()

        return NBAService(
            config=nba_config,
            video_config=video_config,
            video_process_config=video_process_config
        )

    def _verify_nba_service_status(self) -> None:
        """验证关键服务状态"""
        if not self.nba_service:
            raise RuntimeError("NBA 服务未初始化")

        critical_services = {
            'data': "数据服务",
            'videodownloader': "视频服务",
            'video_processor': "视频处理器",
            'chart': "图表服务"
        }

        for service_name, display_name in critical_services.items():
            status = self.nba_service._service_status.get(service_name)
            if status:
                if status.status == ServiceStatus.AVAILABLE:
                    self.logger.info(f"{display_name}初始化成功")
                else:
                    self.logger.error(f"{display_name}初始化失败: {status.error_message}")
                    raise RuntimeError(f"{display_name}初始化失败")

    def _init_weibo_service(self):
        """初始化微博发布服务"""
        self.logger.info("初始化微博发布服务...")
        try:
            # 初始化时传入内容生成器
            weibo_service = WeiboPostService(content_generator=self.content_generator)
            self.logger.info("微博发布服务初始化成功")
            return weibo_service
        except Exception as e:
            self.logger.error(f"微博发布服务初始化失败: {e}")
            return None

    def _init_ai_processor(self):
        """初始化AI处理器"""
        self.logger.info("初始化AI处理器...")
        try:
            # 创建AI配置
            ai_config = AIConfig()

            # 初始化AI处理器
            ai_processor = AIProcessor(ai_config)
            self.logger.info("AI处理器初始化成功")
            return ai_processor
        except Exception as e:
            self.logger.error(f"AI处理器初始化失败: {e}")
            return None

    def run(self) -> int:
        """运行应用程序"""
        result = 0  # 默认返回值
        try:
            # 初始化服务
            self.init_services()

            # 创建并执行对应的命令
            mode = RunMode(self.args.mode)
            self.logger.info(f"以 {mode.value} 模式运行应用程序")

            command = NBACommandFactory.create_command(mode)
            if command:
                command.execute(self)
            else:
                self.logger.error(f"未找到对应模式的命令: {mode.value}")
                result = 1

            self.logger.info("=== 应用程序运行完成 ===")

        except Exception as e:
            self.logger.error(f"应用程序运行失败: {e}", exc_info=True)
            print(f"\n应用程序运行失败: {e}\n请查看日志获取详细信息")
            result = 1

        finally:
            self.cleanup()
            return result  # 在finally块中返回结果

    def _check_required_files_for_weibo(self, mode) -> bool:
        """检查微博发布所需的文件是否存在"""
        # 初始化检查结果
        result = True

        # 获取基础信息
        team_id = self.nba_service.get_team_id_by_name(self.args.team)
        player_id = self.nba_service.get_player_id_by_name(self.args.player)
        game = self.nba_service.data_service.get_game(self.args.team)
        game_id = game.game_data.game_id if game else None

        if not game_id:
            print("× 未找到比赛数据")
            return False

        # 查找已有的视频和图表文件
        if mode in (RunMode.WEIBO, RunMode.WEIBO_TEAM) and "team_video" not in self.video_paths:
            # 检查是否已经有球队视频
            team_video_dir = NBAConfig.PATHS.VIDEO_DIR / "team_videos" / f"team_{team_id}_{game_id}"
            if team_video_dir.exists():
                team_video = list(team_video_dir.glob(f"team_{team_id}_{game_id}.mp4"))
                if team_video:
                    self.video_paths["team_video"] = team_video[0]
                    print(f"√ 找到球队集锦视频: {team_video[0]}")
                else:
                    print("× 未找到球队集锦视频，请先运行 --mode video-team 生成视频")
                    result = False
            else:
                print("× 未找到球队视频目录，请先运行 --mode video-team 生成视频")
                result = False

        if mode in (RunMode.WEIBO, RunMode.WEIBO_PLAYER) and "player_video" not in self.video_paths:
            # 检查是否已经有球员视频
            player_video_dir = NBAConfig.PATHS.VIDEO_DIR / "player_videos" / f"player_{player_id}_{game_id}"
            if player_video_dir.exists():
                player_video = list(player_video_dir.glob(f"player_{player_id}_{game_id}.mp4"))
                if player_video:
                    self.video_paths["player_video"] = player_video[0]
                    print(f"√ 找到球员集锦视频: {player_video[0]}")
                else:
                    print("× 未找到球员集锦视频，请先运行 --mode video-player 生成视频")
                    result = False
            else:
                print("× 未找到球员视频目录，请先运行 --mode video-player 生成视频")
                result = False

        if mode in (RunMode.WEIBO, RunMode.WEIBO_CHART) and "player_chart" not in self.chart_paths:
            # 使用正确的图表目录路径
            storage_dir = NBAConfig.PATHS.PICTURES_DIR
            player_chart = list(storage_dir.glob(f"scoring_impact_{game_id}_{player_id}.png"))
            if player_chart:
                self.chart_paths["player_chart"] = player_chart[0]
                print(f"√ 找到球员投篮图: {player_chart[0]}")
            else:
                print("× 未找到球员投篮图，请先运行 --mode chart 生成图表")
                result = False

        # 检查球队投篮图
        if mode in (RunMode.WEIBO, RunMode.WEIBO_TEAM_CHART) and "team_chart" not in self.chart_paths:
            storage_dir = NBAConfig.PATHS.PICTURES_DIR
            team_chart = list(storage_dir.glob(f"team_shots_{game_id}_{team_id}.png"))
            if team_chart:
                self.chart_paths["team_chart"] = team_chart[0]
                print(f"√ 找到球队投篮图: {team_chart[0]}")
            else:
                print("× 未找到球队投篮图，请先运行 --mode chart 生成图表")
                result = False

        # 检查球员回合GIF
        if mode in (RunMode.WEIBO, RunMode.WEIBO_ROUND) and not self.round_gifs:
            # 检查是否已经有球员回合GIF
            gif_dir = NBAConfig.PATHS.GIF_DIR / f"player_{player_id}_{game_id}_rounds"
            if gif_dir.exists():
                gifs = list(gif_dir.glob(f"round_*_{player_id}.gif"))
                if gifs:
                    # 将找到的GIF添加到round_gifs字典中
                    for gif in gifs:
                        match = re.search(r'round_(\d+)_', gif.name)
                        if match:
                            event_id = match.group(1)
                            self.round_gifs[event_id] = gif
                    print(f"√ 找到 {len(self.round_gifs)} 个球员回合GIF")
                else:
                    print("× 未找到球员回合GIF，请先运行 --mode video-rounds 生成GIF")
                    result = False
            else:
                print("× 未找到球员回合GIF目录，请先运行 --mode video-rounds 生成GIF")
                result = False

        return result

    def cleanup(self) -> None:
        """清理资源，关闭所有服务"""
        if self.nba_service:
            try:
                self.nba_service.close()
                self.logger.info("NBA 服务已关闭")
            except Exception as e:
                self.logger.error(f"关闭 NBA 服务时发生错误: {e}")

        if self.weibo_service:
            try:
                self.weibo_service.close()
                self.logger.info("微博服务已关闭")
            except Exception as e:
                self.logger.error(f"关闭微博服务时发生错误: {e}")

        if self.ai_processor:
            try:
                if hasattr(self.ai_processor, 'close') and callable(self.ai_processor.close):
                    self.ai_processor.close()
                self.logger.info("AI处理器已关闭")
            except Exception as e:
                self.logger.error(f"关闭AI处理器时发生错误: {e}")

        self.logger.info("=== 服务结束 ===")


def main() -> int:
    """主程序入口"""
    app = NBACommandLineApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())