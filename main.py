# main.py
"""NBA 数据服务主程序 - 精简同步版

实现以下核心功能：
1. 比赛基础信息查询
2. 投篮图表生成
3. 视频处理功能
4. 发布内容到微博
5. AI分析比赛数据
6. 球队赛后评级
7. 核心数据同步管理

用法:
    python main.py [options]
"""
import argparse
import re
import sys
import logging
from pathlib import Path
from enum import Enum
from typing import List, Dict, Any, Optional, Set
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import wraps
from dotenv import load_dotenv

from config import NBAConfig
# 导入业务逻辑函数和服务
from nba.services.nba_service import NBAService, NBAServiceConfig, ServiceNotAvailableError
from nba.services.game_video_service import VideoConfig
from utils.video_converter import VideoProcessConfig
from utils.logger_handler import AppLogger
from utils.ai_processor import AIProcessor, AIConfig
from weibo.weibo_post_service import WeiboPostService
from weibo.weibo_content_generator import WeiboContentGenerator, ContentType


# ============1. 基础配置和枚举===============

class RunMode(Enum):
    """应用程序运行模式"""
    # 基础功能模式
    INFO = "info"  # 只显示比赛信息
    CHART = "chart"  # 只生成图表
    VIDEO = "video"  # 处理所有视频
    VIDEO_TEAM = "video-team"  # 只处理球队视频
    VIDEO_PLAYER = "video-player"  # 只处理球员视频
    VIDEO_ROUNDS = "video-rounds"  # 处理球员视频的回合GIF
    AI = "ai"  # 只运行AI分析

    # 微博相关模式
    WEIBO = "weibo"  # 执行所有微博发布功能
    WEIBO_TEAM = "weibo-team"  # 只发布球队集锦视频
    WEIBO_PLAYER = "weibo-player"  # 只发布球员集锦视频
    WEIBO_CHART = "weibo-chart"  # 只发布球员投篮图
    WEIBO_TEAM_CHART = "weibo-team-chart"  # 只发布球队投篮图
    WEIBO_ROUND = "weibo-rounds"  # 只发布球员回合解说和GIF
    WEIBO_TEAM_RATING = "weibo-team-rating"  # 只发布球队赛后评级

    # 综合模式
    ALL = "all"  # 执行所有功能 (不含同步)

    # 同步相关模式 (精简后)
    SYNC = "sync"  # 增量并行同步比赛统计数据 (gamedb)
    SYNC_NEW_SEASON = "sync-new-season"  # 手动触发新赛季核心数据更新 (nba.db)
    SYNC_PLAYER_DETAILS = "sync-player-details"  # 同步球员详细信息

    @classmethod
    def get_weibo_modes(cls) -> Set["RunMode"]:
        """获取所有微博相关模式"""
        return {
            cls.WEIBO, cls.WEIBO_TEAM, cls.WEIBO_PLAYER,
            cls.WEIBO_CHART, cls.WEIBO_TEAM_CHART,
            cls.WEIBO_ROUND, cls.WEIBO_TEAM_RATING, cls.ALL
        }

    @classmethod
    def get_ai_modes(cls) -> Set["RunMode"]:
        """获取所有需要AI功能的模式"""
        return {cls.AI}.union(cls.get_weibo_modes())

    @classmethod
    def get_sync_modes(cls) -> Set["RunMode"]:
        """获取所有数据同步相关模式"""
        return {
            cls.SYNC,
            cls.SYNC_NEW_SEASON
        }


@dataclass
class AppConfig:
    """应用程序配置类"""
    # 基础配置
    team: str = "Lakers"
    player: str = "LeBron James"
    date: str = "last"
    mode: RunMode = RunMode.ALL
    debug: bool = False
    no_weibo: bool = False

    # 同步相关配置
    force_update: bool = False # 主要用于 sync 模式强制更新统计数据
    max_workers: int = 2
    batch_size: int = 6

    # 路径相关配置
    config_file: Optional[Path] = None
    root_dir: Path = field(default_factory=lambda: Path(__file__).parent)

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "AppConfig":
        """从命令行参数创建配置"""
        return cls(
            team=args.team,
            player=args.player,
            date=args.date,
            mode=RunMode(args.mode),
            debug=args.debug,
            no_weibo=args.no_weibo,
            force_update=args.force_update,
            max_workers=args.max_workers,
            batch_size=args.batch_size,
            config_file=Path(args.config) if args.config else None
        )


# ============2. 异常与错误处理===============

class AppError(Exception):
    """应用程序异常基类"""
    pass


class ServiceInitError(AppError):
    """服务初始化失败异常"""
    pass


class CommandExecutionError(AppError):
    """命令执行失败异常"""
    pass


class DataFetchError(AppError):
    """数据获取失败异常"""
    pass


def error_handler(func):
    """错误处理装饰器，统一处理命令执行中的异常"""

    @wraps(func)
    def wrapper(self, app, *args, **kwargs):
        try:
            return func(self, app, *args, **kwargs)
        except ServiceNotAvailableError as e:
            service_name = str(e).split(" ")[0] if " " in str(e) else "未知服务"
            app.logger.error(f"服务不可用: {e}")
            print(f"× {service_name}不可用: {e}")
            app.try_restart_service(service_name)
            return False
        except Exception as e:
            command_name = self.__class__.__name__
            app.logger.error(f"{command_name}执行失败: {e}", exc_info=True)
            print(f"× {command_name.replace('Command', '')}执行失败: {e}")
            return False

    return wrapper


# ============3. 命令模式实现===============

class NBACommand(ABC):
    """NBA命令基类"""

    @abstractmethod
    def execute(self, app: 'NBACommandLineApp') -> bool:
        """执行命令，返回是否成功执行"""
        pass

    def _log_section(self, title: str) -> None:
        """打印分节标题"""
        print(f"\n=== {title} ===")


class InfoCommand(NBACommand):
    """比赛信息查询命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("比赛基本信息")

        # 获取比赛数据
        game = app.get_game_data()
        if not game:
            return False

        # 使用nbaservice中的适配器获取结构化数据
        game_data = app.get_game_ai_data(game)
        if not game_data or "error" in game_data:
            print(f"× 获取AI友好数据失败: {game_data.get('error', '未知错误')}")
            return False

        # 显示比赛基本信息
        self._display_game_basic_info(game_data)

        # 显示首发阵容和伤病名单
        self._display_team_rosters(game_data)

        # 显示比赛状态和结果
        self._display_game_status_and_result(game_data)

        # 显示球队统计对比
        self._display_team_stats_comparison(game_data)

        # 如果指定了球员，显示球员统计数据
        if app.config.player:
            self._display_player_stats(app, game)

        # 显示比赛事件时间线
        self._display_game_timeline(game_data)

        return True

    def _display_game_basic_info(self, game_data: Dict) -> None:
        """显示比赛基本信息"""
        game_info = game_data.get("game_info", {})
        if not game_info:
            return

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

    def _display_team_rosters(self, game_data: Dict) -> None:
        """显示球队阵容信息"""
        # 获取球队信息
        game_info = game_data.get("game_info", {})
        basic_info = game_info.get("basic", {})
        teams = basic_info.get("teams", {})

        # 显示首发阵容
        starters = game_data.get("starters", {})
        print("\n首发阵容:")

        # 主队首发
        home_tricode = teams.get('home', {}).get('tricode', 'N/A')
        print(f"  {home_tricode}首发:")
        home_starters = starters.get("home", [])
        for i, player in enumerate(home_starters, 1):
            print(
                f"    {i}. {player.get('name', 'N/A')} - {player.get('position', 'N/A')} #{player.get('jersey_num', 'N/A')}")

        # 客队首发
        away_tricode = teams.get('away', {}).get('tricode', 'N/A')
        print(f"  {away_tricode}首发:")
        away_starters = starters.get("away", [])
        for i, player in enumerate(away_starters, 1):
            print(
                f"    {i}. {player.get('name', 'N/A')} - {player.get('position', 'N/A')} #{player.get('jersey_num', 'N/A')}")

        # 显示伤病名单
        injuries = game_data.get("injuries", {})
        print("\n伤病名单:")

        # 主队伤病
        home_injuries = injuries.get("home", [])
        if home_injuries:
            print(f"  {home_tricode}伤病球员:")
            for i, player in enumerate(home_injuries, 1):
                reason = player.get('reason', 'Unknown')
                description = player.get('description', '')
                desc_text = f" - {description}" if description else ""
                print(f"    {i}. {player.get('name', 'N/A')} ({reason}){desc_text}")
        else:
            print(f"  {home_tricode}无伤病球员")

        # 客队伤病
        away_injuries = injuries.get("away", [])
        if away_injuries:
            print(f"  {away_tricode}伤病球员:")
            for i, player in enumerate(away_injuries, 1):
                reason = player.get('reason', 'Unknown')
                description = player.get('description', '')
                desc_text = f" - {description}" if description else ""
                print(f"    {i}. {player.get('name', 'N/A')} ({reason}){desc_text}")
        else:
            print(f"  {away_tricode}无伤病球员")

    def _display_game_status_and_result(self, game_data: Dict) -> None:
        """显示比赛状态和结果"""
        game_info = game_data.get("game_info", {})

        # 显示比赛状态
        status = game_info.get("status", {})
        print("\n比赛状态:")
        print(f"  当前状态: {status.get('state', 'N/A')}")
        print(f"  当前节数: {status.get('period', {}).get('name', 'N/A')}")
        print(f"  剩余时间: {status.get('time_remaining', 'N/A')}")

        score = status.get("score", {})
        print(f"  比分: {score.get('home', {}).get('team', 'N/A')} {score.get('home', {}).get('points', 0)} - "
              f"{score.get('away', {}).get('team', 'N/A')} {score.get('away', {}).get('points', 0)}")

        # 检查比赛是否结束，显示比赛结果
        game_status = status.get("state", "").lower()
        if game_status in ["finished", "end", "final", "ended"]:
            result = game_info.get("result", {})
            print("\n比赛结果:")
            print(f"  最终比分: {result.get('final_score', 'N/A')}")
            print(
                f"  获胜方: {result.get('winner', {}).get('team_name', 'N/A')} ({result.get('winner', {}).get('score', 0)}分)")
            print(
                f"  失利方: {result.get('loser', {}).get('team_name', 'N/A')} ({result.get('loser', {}).get('score', 0)}分)")
            print(f"  分差: {result.get('score_difference', 0)}分")
            print(f"  观众数: {result.get('attendance', {}).get('count', 'N/A')}")
            print(f"  比赛时长: {result.get('duration', 'N/A')}分钟")

    def _display_team_stats_comparison(self, game_data: Dict) -> None:
        """显示球队统计数据对比"""
        team_stats = game_data.get("team_stats", {})
        if not team_stats:
            return

        print("\n球队统计数据对比:")
        home = team_stats.get("home", {})
        away = team_stats.get("away", {})

        # 获取球队缩写
        game_info = game_data.get("game_info", {})
        home_tricode = game_info.get("basic", {}).get("teams", {}).get("home", {}).get("tricode", "主队")
        away_tricode = game_info.get("basic", {}).get("teams", {}).get("away", {}).get("tricode", "客队")
        print(f"  {home_tricode} vs {away_tricode}")

        # 显示投篮数据
        home_shooting = home.get("shooting", {})
        away_shooting = away.get("shooting", {})

        # 常规投篮
        home_fg = home_shooting.get("field_goals", {})
        away_fg = away_shooting.get("field_goals", {})
        home_fg_pct = home_fg.get("percentage", 0)
        away_fg_pct = away_fg.get("percentage", 0)
        print(f"  投篮: {home_fg.get('made', 0)}/{home_fg.get('attempted', 0)} ({home_fg_pct:.1%}) vs "
              f"{away_fg.get('made', 0)}/{away_fg.get('attempted', 0)} ({away_fg_pct:.1%})")

        # 三分球
        home_3pt = home_shooting.get("three_pointers", {})
        away_3pt = away_shooting.get("three_pointers", {})
        home_3pt_pct = home_3pt.get("percentage", 0)
        away_3pt_pct = away_3pt.get("percentage", 0)
        print(f"  三分: {home_3pt.get('made', 0)}/{home_3pt.get('attempted', 0)} ({home_3pt_pct:.1%}) vs "
              f"{away_3pt.get('made', 0)}/{away_3pt.get('attempted', 0)} ({away_3pt_pct:.1%})")

        # 显示其他统计数据
        home_rebounds = home.get("rebounds", {})
        away_rebounds = away.get("rebounds", {})
        home_offense = home.get("offense", {})
        away_offense = away.get("offense", {})
        home_defense = home.get("defense", {})
        away_defense = away.get("defense", {})

        print(f"  篮板: {home_rebounds.get('total', 0)} vs {away_rebounds.get('total', 0)}")
        print(f"  助攻: {home_offense.get('assists', 0)} vs {away_offense.get('assists', 0)}")
        print(
            f"  失误: {home_defense.get('turnovers', {}).get('total', 0)} vs {away_defense.get('turnovers', {}).get('total', 0)}")
        print(f"  抢断: {home_defense.get('steals', 0)} vs {away_defense.get('steals', 0)}")
        print(f"  盖帽: {home_defense.get('blocks', 0)} vs {away_defense.get('blocks', 0)}")

    def _display_player_stats(self, app: 'NBACommandLineApp', game: Any) -> None:
        """显示特定球员的统计数据"""
        player_name = app.config.player
        print(f"\n=== {player_name} 球员详细数据 ===")

        # 获取球员ID
        player_id = app.get_player_id(player_name)
        if not player_id:
            print(f"× 未找到球员 {player_name}")
            return

        # 获取球员数据
        player_data = app.get_player_data(game, player_id)
        if not player_data or "error" in player_data:
            error_msg = player_data.get("error", "未知错误") if player_data else "获取数据失败"
            print(f"× 获取 {player_name} 的数据失败: {error_msg}")
            return

        player_info = player_data.get("player_info", {})
        if not player_info:
            print(f"× 未找到 {player_name} 的完整数据")
            return

        # 检查球员是否上场
        if player_info.get("basic", {}).get("played", False):
            # 显示球员基础数据
            basic = player_info.get("basic", {})
            print(f"\n{basic.get('name', 'N/A')} 基本数据:")
            print(f"  位置: {basic.get('position', 'N/A')} | 球衣号: {basic.get('jersey_num', 'N/A')}")
            print(
                f"  上场时间: {basic.get('minutes', 'N/A')} | 首发/替补: {'首发' if basic.get('starter', False) else '替补'}")
            print(
                f"  得分: {basic.get('points', 0)} | 篮板: {basic.get('rebounds', 0)} | 助攻: {basic.get('assists', 0)}")
            print(f"  +/-: {basic.get('plus_minus', 0)}")

            # 显示投篮数据
            shooting = player_info.get("shooting", {})
            print("\n投篮数据:")

            # 常规投篮
            fg = shooting.get("field_goals", {})
            print(f"  投篮: {fg.get('made', 0)}/{fg.get('attempted', 0)} ({fg.get('percentage', 0) or 0:.1%})")

            # 三分球
            three = shooting.get("three_pointers", {})
            print(f"  三分: {three.get('made', 0)}/{three.get('attempted', 0)} ({three.get('percentage', 0) or 0:.1%})")

            # 罚球
            ft = shooting.get("free_throws", {})
            print(f"  罚球: {ft.get('made', 0)}/{ft.get('attempted', 0)} ({ft.get('percentage', 0) or 0:.1%})")

            # 显示其他数据
            other = player_info.get("other_stats", {})
            print("\n其他数据:")
            print(f"  抢断: {other.get('steals', 0)} | 盖帽: {other.get('blocks', 0)}")
            print(f"  失误: {other.get('turnovers', 0)} | 个人犯规: {other.get('fouls', {}).get('personal', 0)}")

            # 显示得分分布
            scoring = other.get("scoring_breakdown", {})
            print("\n得分分布:")
            print(f"  禁区得分: {scoring.get('paint_points', 0)} | 快攻得分: {scoring.get('fast_break_points', 0)} | "
                  f"二次进攻: {scoring.get('second_chance_points', 0)}")

        else:
            # 球员未上场
            injury_status = player_info.get("injury_status", {})
            not_playing_reason = injury_status.get("reason", "未知原因")
            description = f" - {injury_status.get('description', '')}" if injury_status.get("description") else ""
            print(f"\n{player_info.get('name', 'N/A')} 未参与本场比赛")
            print(f"  原因: {not_playing_reason}{description}")

    def _display_game_timeline(self, game_data: Dict) -> None:
        """显示比赛事件时间线"""
        events = game_data.get("events", {}).get("data", [])
        if not events:
            return

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

                    print(f"    {i}. 第{period}节 {clock} - {description}, 比分: {score}")


class ChartCommand(NBACommand):
    """图表生成命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("投篮图表演示")

        # 生成图表
        app.chart_paths = app.nba_service.generate_shot_charts(
            team=app.config.team,
            player_name=app.config.player,
            chart_type="both",  # 同时生成球队和球员图表
            shot_outcome="made_only",  # 默认仅显示命中的投篮
            impact_type="full_impact"  # 默认显示完整的得分影响力
        )

        if app.chart_paths:
            print(f"✓ 成功生成 {len(app.chart_paths)} 个投篮图表")
            for chart_type, chart_path in app.chart_paths.items():
                print(f"  - {chart_type}: {chart_path}")
            return True
        else:
            print("× 图表生成失败")
            return False


class BaseVideoCommand(NBACommand):
    """视频处理命令基类"""

    def _log_video_result(self, videos: Dict, video_type: str, key: str) -> None:
        """记录视频处理结果"""
        if videos:
            if key in videos:
                self.app.video_paths[video_type] = videos[key]
                print(f"✓ 已生成{video_type.replace('_', ' ')}合并视频: {videos[key]}")
            else:
                print(f"✓ 获取到 {len(videos)} 个视频片段")
        else:
            print(f"× 获取{video_type.replace('_', ' ')}视频失败")


class VideoCommand(BaseVideoCommand):
    """所有视频处理命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self.app = app  # 保存app引用
        self._log_section("处理所有视频")

        # 处理各类视频
        team_success = self._process_team_video(app)
        player_success = self._process_player_video(app)
        rounds_success = self._process_round_gifs(app)

        # 至少有一种视频处理成功即视为成功
        return team_success or player_success or rounds_success

    def _process_team_video(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("处理球队集锦视频")
        try:
            team_videos = app.nba_service.get_team_highlights(team=app.config.team, merge=True)
            self._log_video_result(team_videos, "team_video", "merged")
            return bool(team_videos)
        except Exception as e:
            app.logger.error(f"处理球队集锦视频失败: {e}", exc_info=True)
            print(f"× 处理球队集锦视频失败: {e}")
            return False

    def _process_player_video(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("处理球员集锦视频")
        try:
            player_videos = app.nba_service.get_player_highlights(
                player_name=app.config.player,
                merge=True
            )
            self._log_video_result(player_videos, "player_video", "video_merged")
            return bool(player_videos)
        except Exception as e:
            app.logger.error(f"处理球员集锦视频失败: {e}", exc_info=True)
            print(f"× 处理球员集锦视频失败: {e}")
            return False

    def _process_round_gifs(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("处理球员回合GIF")
        try:
            app.round_gifs = app.nba_service.get_player_round_gifs(
                player_name=app.config.player
            )
            if app.round_gifs:
                print(f"✓ 已生成 {len(app.round_gifs)} 个球员回合GIF")
                return True
            else:
                print("× 生成球员回合GIF失败")
                return False
        except Exception as e:
            app.logger.error(f"处理球员回合GIF失败: {e}", exc_info=True)
            print(f"× 处理球员回合GIF失败: {e}")
            return False


class VideoTeamCommand(BaseVideoCommand):
    """球队视频处理命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self.app = app  # 保存app引用
        self._log_section("处理球队集锦视频")

        team_videos = app.nba_service.get_team_highlights(team=app.config.team, merge=True)
        self._log_video_result(team_videos, "team_video", "merged")
        return bool(team_videos)


class VideoPlayerCommand(BaseVideoCommand):
    """球员视频处理命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self.app = app  # 保存app引用
        self._log_section("处理球员集锦视频")

        player_videos = app.nba_service.get_player_highlights(
            player_name=app.config.player,
            merge=True
        )
        self._log_video_result(player_videos, "player_video", "video_merged")
        return bool(player_videos)


class VideoRoundsCommand(BaseVideoCommand):
    """球员回合GIF处理命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self.app = app  # 保存app引用
        self._log_section("处理球员回合GIF")

        app.round_gifs = app.nba_service.get_player_round_gifs(
            player_name=app.config.player
        )
        if app.round_gifs:
            print(f"✓ 已生成 {len(app.round_gifs)} 个球员回合GIF")
            return True
        else:
            print("× 生成球员回合GIF失败")
            return False

class AICommand(NBACommand):
    """AI分析命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("AI分析结果")

        if not app.ai_processor or not app.content_generator:
            print("× AI处理器或内容生成器未初始化，跳过分析")
            return False

        print("\n正在获取结构化数据并进行AI分析，这可能需要一些时间...")

        # 获取比赛数据
        game = app.get_game_data()
        if not game:
            print(f"× 获取比赛信息失败: 未找到{app.config.team}的比赛数据")
            return False

        # 获取球队ID和数据
        team_id = app.get_team_id(app.config.team)
        if not team_id:
            print(f"× 未能获取{app.config.team}的team_id")
            return False

        # 获取球队结构化数据
        team_data = app.get_team_data(game, team_id)
        if not team_data or "error" in team_data:
            error_msg = team_data.get("error", "未知错误") if team_data else "获取数据失败"
            print(f"× 获取球队数据失败: {error_msg}")
            return False

        # 使用内容生成器生成分析内容
        title = app.content_generator.generate_game_title(team_data)
        summary = app.content_generator.generate_game_summary(team_data)

        # 显示分析结果
        print("\n比赛标题:")
        print(f"  {title}")

        print("\n比赛摘要:")
        print(summary)

        # 如果指定了球员，则分析球员表现
        if app.config.player:
            self._analyze_player_performance(app, game, team_data)

        # 如果比赛已结束，显示球队赛后评级
        status = team_data.get("game_info", {}).get("status", {}).get("state", "").lower()
        if not app.config.player and status in ["finished", "final", "end", "ended"]:
            self._display_team_rating(app, team_data, team_id)

        print("\nAI分析完成!")
        return True

    def _analyze_player_performance(self, app, game, team_data):
        """分析球员表现"""
        player_id = app.get_player_id(app.config.player)
        if not player_id:
            print(f"× 未找到球员: {app.config.player}")
            return

        # 获取球员结构化数据
        player_data = app.get_player_data(game, player_id)
        if not player_data or "error" in player_data:
            error_msg = player_data.get("error", "未知错误") if player_data else "获取数据失败"
            print(f"× 获取球员数据失败: {error_msg}")
            return

        # 确保有足够的球队上下文信息
        player_data.update(team_data.get("game_info", {}))

        # 生成球员分析
        player_analysis = app.content_generator.generate_player_analysis(player_data)
        print(f"\n{app.config.player}表现分析:")
        print(player_analysis)

    def _display_team_rating(self, app, team_data, team_id):
        """显示球队赛后评级"""
        print(f"\n{app.config.team}赛后评级:")
        team_rating = app.content_generator.generate_team_performance_rating(
            team_data, team_id
        )
        # 移除微博标签后显示
        content = team_rating.get("content", "").replace("\n\n#NBA# #篮球# #Lakers#", "")
        print(content)


class BaseWeiboCommand(NBACommand):
    """微博发布命令基类"""

    def _check_required_files(self, app, mode: RunMode) -> bool:
        """检查微博发布所需的文件"""
        return app.check_required_files_for_weibo(mode)


class WeiboCommand(BaseWeiboCommand):
    """微博发布全部内容命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("微博发布")

        # 检查所需文件
        if not self._check_required_files(app, RunMode.WEIBO):
            return False

        # 获取游戏数据 - 获取原始Game对象
        game = app.get_game_data()
        if not game:
            print("× 获取比赛数据失败")
            return False

        # 获取team_id和player_id
        team_id = app.get_team_id(app.config.team)
        player_id = None
        if app.config.player:
            player_id = app.get_player_id(app.config.player)

        # 执行统一发布
        results = []

        # 发布球队集锦视频
        if "team_video" in app.video_paths:
            result = app.weibo_service.post_content(
                content_type="team_video",
                media_path=app.video_paths["team_video"],
                data=game,  # 传递原始Game对象
                team_id=team_id,
                team_name=app.config.team
            )
            results.append(result)
            print(
                f"  {'✓' if result.get('success') else '×'} 球队集锦视频发布{'成功' if result.get('success') else '失败'}")

        # 如果指定了球员，发布球员相关内容
        if player_id:
            # 发布球员集锦视频
            if "player_video" in app.video_paths:
                result = app.weibo_service.post_content(
                    content_type="player_video",
                    media_path=app.video_paths["player_video"],
                    data=game,  # 传递原始Game对象
                    player_id=player_id,
                    player_name=app.config.player
                )
                results.append(result)
                print(
                    f"  {'✓' if result.get('success') else '×'} 球员集锦视频发布{'成功' if result.get('success') else '失败'}")

            # 发布球员投篮图
            if "player_chart" in app.chart_paths:
                result = app.weibo_service.post_content(
                    content_type="player_chart",
                    media_path=app.chart_paths["player_chart"],
                    data=game,  # 传递原始Game对象
                    player_id=player_id,
                    player_name=app.config.player
                )
                results.append(result)
                print(
                    f"  {'✓' if result.get('success') else '×'} 球员投篮图发布{'成功' if result.get('success') else '失败'}")

        # 判断总体成功状态
        success_count = sum(1 for r in results if r.get("success"))
        if results and success_count > 0:
            print(f"  ✓ 成功发布 {success_count}/{len(results)} 个内容")
            return True
        else:
            print("  × 所有内容发布失败")
            return False


class WeiboTeamCommand(BaseWeiboCommand):
    """微博发布球队视频命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("微博发布球队集锦视频")

        # 检查所需文件
        if not self._check_required_files(app, RunMode.WEIBO_TEAM):
            return False

        # 获取基础数据 - 获取原始Game对象
        game = app.get_game_data()
        if not game:
            print("× 获取比赛信息失败")
            return False

        # 获取球队ID
        team_id = app.get_team_id(app.config.team)
        if not team_id:
            print(f"× 未找到球队ID: {app.config.team}")
            return False

        # 发布球队集锦视频 - 传递原始Game对象和team_id
        if "team_video" in app.video_paths:
            result = app.weibo_service.post_content(
                content_type="team_video",
                media_path=app.video_paths["team_video"],
                data=game,  # 传递原始Game对象
                team_id=team_id  # 传递team_id而不是已适配的数据
            )

            if result and result.get("success"):
                print(f"✓ 球队集锦视频发布成功: {result.get('message', '')}")
                return True
            else:
                print(f"× 球队集锦视频发布失败: {result.get('message', '未知错误')}")
                return False
        else:
            print("× 未找到球队视频路径")
            return False


class WeiboPlayerCommand(BaseWeiboCommand):
    """微博发布球员视频命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("微博发布球员集锦视频")

        # 检查所需文件
        if not self._check_required_files(app, RunMode.WEIBO_PLAYER):
            return False

        # 获取基础数据 - 获取原始Game对象
        game = app.get_game_data()
        if not game:
            print("× 获取比赛信息失败")
            return False

        # 获取球员ID
        player_id = app.get_player_id(app.config.player)
        if not player_id:
            print(f"× 未找到球员: {app.config.player}")
            return False

        # 发布球员集锦视频 - 传递原始Game对象和player_id
        if "player_video" in app.video_paths:
            result = app.weibo_service.post_content(
                content_type="player_video",
                media_path=app.video_paths["player_video"],
                data=game,  # 传递原始Game对象
                player_id=player_id,  # 传递player_id
                player_name=app.config.player
            )

            if result and result.get("success"):
                print(f"✓ 球员集锦视频发布成功: {result.get('message', '')}")
                return True
            else:
                print(f"× 球员集锦视频发布失败: {result.get('message', '未知错误')}")
                return False
        else:
            print("× 未找到球员视频路径")
            return False


class WeiboChartCommand(BaseWeiboCommand):
    """微博发布球员投篮图命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("微博发布球员投篮图")

        # 检查所需文件
        if not self._check_required_files(app, RunMode.WEIBO_CHART):
            return False

        # 获取基础数据 - 获取原始Game对象
        game = app.get_game_data()
        if not game:
            print("× 获取比赛信息失败")
            return False

        # 获取球员ID
        player_id = app.get_player_id(app.config.player)
        if not player_id:
            print(f"× 未找到球员: {app.config.player}")
            return False

        # 发布球员投篮图 - 传递原始Game对象和player_id
        if "player_chart" in app.chart_paths:
            result = app.weibo_service.post_content(
                content_type="player_chart",
                media_path=app.chart_paths["player_chart"],
                data=game,  # 传递原始Game对象
                player_id=player_id,
                player_name=app.config.player
            )

            if result and result.get("success"):
                print(f"✓ 球员投篮图发布成功: {result.get('message', '')}")
                return True
            else:
                print(f"× 球员投篮图发布失败: {result.get('message', '未知错误')}")
                return False
        else:
            print("× 未找到球员投篮图路径")
            return False


class WeiboTeamChartCommand(BaseWeiboCommand):
    """微博发布球队投篮图命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("微博发布球队投篮图")

        # 检查所需文件
        if not self._check_required_files(app, RunMode.WEIBO_TEAM_CHART):
            return False

        # 获取基础数据 - 获取原始Game对象
        game = app.get_game_data()
        if not game:
            print("× 获取比赛信息失败")
            return False

        # 获取球队ID
        team_id = app.get_team_id(app.config.team)
        if not team_id:
            print(f"× 未找到球队ID: {app.config.team}")
            return False

        # 发布球队投篮图 - 传递原始Game对象和team_id
        if "team_chart" in app.chart_paths:
            result = app.weibo_service.post_content(
                content_type="team_chart",
                media_path=app.chart_paths["team_chart"],
                data=game,  # 传递原始Game对象
                team_id=team_id,
                team_name=app.config.team
            )

            if result and result.get("success"):
                print(f"✓ 球队投篮图发布成功: {result.get('message', '')}")
                return True
            else:
                print(f"× 球队投篮图发布失败: {result.get('message', '未知错误')}")
                return False
        else:
            print("× 未找到球队投篮图路径")
            return False


class WeiboRoundCommand(BaseWeiboCommand):
    """微博发布球员回合解说和GIF命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("微博发布球员回合解说和GIF")

        # 检查所需文件
        if not self._check_required_files(app, RunMode.WEIBO_ROUND):
            return False

        # 获取基础数据 - 获取原始Game对象
        game = app.get_game_data()
        if not game:
            print("× 获取比赛信息失败")
            return False

        # 获取球员ID
        player_id = app.get_player_id(app.config.player)
        if not player_id:
            print(f"× 未找到球员: {app.config.player}")
            return False

        # 提取回合ID列表
        round_ids = [int(event_id) for event_id in app.round_gifs.keys() if event_id.isdigit()]

        # 发布球员回合解说和GIF - 传递原始Game对象、player_id和round_ids
        result = app.weibo_service.post_content(
            content_type="round_analysis",
            media_path=app.round_gifs,
            data=game,  # 传递原始Game对象
            player_id=player_id,
            player_name=app.config.player,
            nba_service=app.nba_service,
            round_ids=round_ids
        )

        if result and result.get("success"):
            print(f"✓ 球员回合解说和GIF发布成功: {result.get('message', '')}")
            return True
        else:
            print(f"× 球员回合解说和GIF发布失败: {result.get('message', '未知错误')}")
            return False


class WeiboTeamRatingCommand(BaseWeiboCommand):
    """微博发布球队赛后评级命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("微博发布球队赛后评级")

        # 获取基础数据 - 获取原始Game对象
        game = app.get_game_data()
        if not game:
            print("× 获取比赛信息失败")
            return False

        # 获取球队ID
        team_id = app.get_team_id(app.config.team)
        if not team_id:
            print(f"× 未能获取{app.config.team}的team_id")
            return False

        # 检查比赛是否已结束
        game_status = getattr(game.game_data, "game_status", 0)
        if game_status != 3:  # 3表示比赛已结束
            print("× 比赛尚未结束，无法生成赛后评级")
            return False

        # 发布球队赛后评级 - 传递原始Game对象和team_id
        result = app.weibo_service.post_content(
            content_type=ContentType.TEAM_RATING.value,
            media_path=None,  # 纯文本发布不需要媒体文件
            data=game,  # 传递原始Game对象
            team_id=team_id,
            team_name=app.config.team
        )

        if result and result.get("success"):
            print(f"✓ 球队赛后评级发布成功: {result.get('message', '')}")
            return True
        else:
            print(f"× 球队赛后评级发布失败: {result.get('message', '未知错误')}")
            return False


class BaseSyncCommand(NBACommand):
    """数据同步命令基类"""
    pass


class SyncCommand(BaseSyncCommand):
    """增量并行同步比赛统计数据命令 (gamedb)"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("增量并行同步比赛统计数据 (gamedb)")
        print("开始使用多线程并行同步未同步过的比赛统计数据...")
        print("这将优先处理最新的比赛。")
        if app.config.force_update:
            print("注意：已启用 --force-update，将强制重新同步所有找到的比赛，即使它们之前已同步。")

        # 获取并行配置
        max_workers = app.config.max_workers
        batch_size = app.config.batch_size
        print(f"最大线程数: {max_workers}, 批次大小: {batch_size}")

        # 调用并行同步方法
        result = app.nba_service.sync_remaining_data_parallel(
            force_update=app.config.force_update,
            max_workers=max_workers,
            batch_size=batch_size,
            reverse_order=True # 默认使用倒序处理
        )

        # 显示结果摘要
        if result.get("status") in ["success", "partially_failed", "completed"]: # "completed" is also a success state
            total_games = result.get("total_games", 0)
            synced_games = result.get("synced_games", 0)
            to_sync = result.get("games_to_sync", 0)
            no_playbyplay = result.get("no_playbyplay_data", 0)

            print(f"\n数据库状态:")
            print(f"总比赛数 : {total_games}场")
            print(f"已同步   : {synced_games}场 (含{no_playbyplay}场无PlayByPlay数据)")
            print(f"本次待同步: {to_sync}场")

            # Boxscore结果
            boxscore = result.get("details", {}).get("boxscore", {})
            successful_games = boxscore.get("successful_games", 0)
            failed_games = boxscore.get("failed_games", 0)
            skipped_games = boxscore.get("skipped_games", 0)

            print(f"\nBoxscore数据同步结果:")
            print(f"成功同步: {successful_games}场")
            print(f"已跳过  : {skipped_games}场 (因已同步且未强制更新)")
            print(f"同步失败: {failed_games}场")

            # PlayByPlay结果
            playbyplay = result.get("details", {}).get("playbyplay", {})
            pp_successful = playbyplay.get("successful_games", 0)
            pp_failed = playbyplay.get("failed_games", 0)
            pp_no_data = playbyplay.get("no_data_games", 0)
            pp_skipped = playbyplay.get("skipped_games", 0)


            print(f"\nPlay-by-Play数据同步结果:")
            print(f"成功同步: {pp_successful}场")
            print(f"无数据  : {pp_no_data}场")
            print(f"已跳过  : {pp_skipped}场")
            print(f"同步失败: {pp_failed}场")

            duration = result.get("duration", 0)
            print(f"\n总耗时  : {duration:.2f}秒")
            # 只要没有返回 "failed" 状态，就认为命令执行成功
            return result.get("status") != "failed"
        else:
            error = result.get("error", "未知错误")
            print(f"× 增量并行同步失败: {error}")
            return False


class NewSeasonCommand(BaseSyncCommand):
    """新赛季核心数据同步命令 (nba.db)"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("新赛季核心数据同步 (nba.db)")
        print("开始同步新赛季核心数据：强制更新球队、球员，并同步当前赛季赛程...")
        if not app.config.force_update:
             print("提示: 未使用 --force-update，将只更新不存在或需要更新的数据。建议新赛季使用 --force-update。")


        # 调用NBA服务同步新赛季核心数据
        # force_update 默认为 True，但允许命令行覆盖
        result = app.nba_service.db_service.sync_new_season_core_data(
            force_update=app.config.force_update
        )

        if result.get("status") in ["success", "partially_failed"]:
            # 显示球队同步结果
            teams_result = result.get("details", {}).get("teams", {})
            if teams_result.get("status") == "success":
                print("\n✓ 球队数据同步成功")
            else:
                print(f"\n× 球队数据同步失败: {teams_result.get('error', '未知错误')}")

            # 显示球员同步结果
            players_result = result.get("details", {}).get("players", {})
            if players_result.get("status") == "success":
                print("✓ 球员数据同步成功")
            else:
                print(f"× 球员数据同步失败: {players_result.get('error', '未知错误')}")

            # 显示赛程同步结果
            schedules_result = result.get("details", {}).get("schedules", {})
            current_season_detail = schedules_result.get("details", {}).get("current_season", {})
            schedules_count = current_season_detail.get("count", 0)

            if schedules_result.get("status") == "success":
                print(f"✓ 当前赛季赛程数据同步成功，共处理 {schedules_count} 场比赛")
            else:
                print(f"× 当前赛季赛程数据同步失败: {schedules_result.get('error', '未知错误')}")

            duration = result.get("duration", 0)
            print(f"\n总耗时: {duration:.2f}秒")
            return result.get("status") != "failed"
        else:
            error = result.get("error", "未知错误")
            print(f"× 新赛季核心数据同步失败: {error}")
            return False


class SyncPlayerDetailsCommand(BaseSyncCommand):
    """同步球员详细信息命令"""

    @error_handler
    def execute(self, app: 'NBACommandLineApp') -> bool:
        self._log_section("同步球员详细信息")
        print("开始同步球员详细信息...")

        # 是否只同步活跃球员
        only_active = not app.config.force_update
        if not only_active:
            print("注意：已启用 --force-update，将同步所有球员的详细信息，而不仅是可能活跃的球员")
        else:
            print("默认只同步可能活跃球员的详细信息（基于to_year判断），使用 --force-update 可同步所有球员")

        # 调用同步方法
        result = app.nba_service.db_service.sync_player_details(
            force_update=app.config.force_update,
            only_active=only_active
        )

        # 显示结果摘要
        if result.get("status") in ["success", "partially_completed"]:
            total = result.get("total", 0)
            success = result.get("success", 0)
            failed = result.get("failed", 0)

            print(f"\n同步结果:")
            print(f"总计: {total}名球员")
            print(f"成功: {success}名")
            print(f"失败: {failed}名")

            # 显示活跃状态统计
            active_count = sum(1 for detail in result.get("details", [])
                               if detail.get("is_active", False) and detail.get("status") == "success")
            inactive_count = success - active_count

            print(f"活跃球员: {active_count}名")
            print(f"非活跃球员: {inactive_count}名")

            duration = result.get("duration", 0)
            print(f"\n总耗时: {duration:.2f}秒")

            return result.get("status") == "success"
        else:
            error = result.get("error", "未知错误")
            print(f"× 同步球员详细信息失败: {error}")
            return False


class CompositeCommand(NBACommand):
    """组合命令，执行多个命令"""

    def __init__(self, commands: List[NBACommand]):
        self.commands = commands

    def execute(self, app: 'NBACommandLineApp') -> bool:
        results = []
        for command in self.commands:
            result = command.execute(app)
            results.append(result)

        # 只要有一个命令执行成功，就返回成功
        return any(results)


# ============4. 命令工厂===============

class NBACommandFactory:
    """NBA命令工厂，负责创建对应的命令对象"""

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
            RunMode.WEIBO_TEAM_RATING: WeiboTeamRatingCommand(),
            RunMode.AI: AICommand(),
            # 精简后的同步命令
            RunMode.SYNC: SyncCommand(),
            RunMode.SYNC_NEW_SEASON: NewSeasonCommand(),
            RunMode.SYNC_PLAYER_DETAILS: SyncPlayerDetailsCommand(),
        }

        # ALL模式组合所有非同步命令
        if mode == RunMode.ALL:
            commands = [
                InfoCommand(),
                ChartCommand(),
                VideoCommand(),
                AICommand()
            ]

            # 如果没有禁用微博，添加微博命令
            if not AppContext.get_instance().config.no_weibo:
                commands.append(WeiboCommand())

            return CompositeCommand(commands)

        return command_map.get(mode)


# ============5. 服务管理类===============

class ServiceManager:
    """服务管理器，负责初始化和管理各种服务"""

    def __init__(self, config: AppConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self._services = {}
        self._service_retry_count = {}
        self._max_retries = 3

    def init_nba_service(self) -> NBAService:
        """初始化NBA服务"""
        self.logger.info("初始化NBA服务...")

        # 使用统一的基础输出目录
        base_output_dir = Path(NBAConfig.PATHS.STORAGE_DIR)

        # 基础配置
        nba_config = NBAServiceConfig(
            default_team=self.config.team,
            default_player=self.config.player,
            auto_refresh=False,
            cache_size=128,
            base_output_dir=base_output_dir
        )

        # 视频配置
        video_config = VideoConfig() # 使用默认配置

        # 视频处理配置
        video_process_config = VideoProcessConfig()

        # 创建服务实例
        service = NBAService(
            config=nba_config,
            video_config=video_config,
            video_process_config=video_process_config,
            env="default",
            create_tables=True # 确保表结构存在
        )

        self._services['nba_service'] = service
        return service

    def init_ai_processor(self) -> Optional[AIProcessor]:
        """初始化AI处理器"""
        if not self._need_ai_service():
            return None

        self.logger.info("初始化AI处理器...")
        try:
            # 创建AI配置
            ai_config = AIConfig()

            # 初始化AI处理器
            ai_processor = AIProcessor(ai_config)
            self.logger.info("AI处理器初始化成功")
            self._services['ai_processor'] = ai_processor
            return ai_processor
        except Exception as e:
            self.logger.error(f"AI处理器初始化失败: {e}")
            return None

    def init_content_generator(self, ai_processor: AIProcessor) -> Optional[WeiboContentGenerator]:
        """初始化内容生成器"""
        if not self._need_ai_service() or not ai_processor:
            return None

        self.logger.info("初始化微博内容生成器...")
        try:
            # 初始化内容生成器
            content_generator = WeiboContentGenerator(
                ai_processor=ai_processor,
                logger=self.logger
            )
            self.logger.info("微博内容生成器初始化成功")
            self._services['content_generator'] = content_generator
            return content_generator
        except Exception as e:
            self.logger.error(f"微博内容生成器初始化失败: {e}")
            return None

    def init_weibo_service(self, content_generator: Optional[WeiboContentGenerator]) -> Optional[WeiboPostService]:
        """初始化微博服务"""
        if not self._need_weibo_service():
            return None

        self.logger.info("初始化微博发布服务...")
        try:
            # 初始化微博服务
            weibo_service = WeiboPostService(content_generator=content_generator)
            self.logger.info("微博发布服务初始化成功")
            self._services['weibo_service'] = weibo_service
            return weibo_service
        except Exception as e:
            self.logger.error(f"微博发布服务初始化失败: {e}")
            return None

    def try_restart_service(self, service_name: str) -> bool:
        """尝试重启服务"""
        # 检查重试次数
        retry_count = self._service_retry_count.get(service_name, 0)
        if retry_count >= self._max_retries:
            self.logger.warning(f"服务 {service_name} 已达到最大重试次数 ({self._max_retries})，不再尝试重启")
            return False

        self.logger.info(f"尝试重启服务: {service_name} (第 {retry_count + 1} 次重试)")

        # 更新重试计数
        self._service_retry_count[service_name] = retry_count + 1

        # 获取NBA服务
        nba_service = self._services.get('nba_service')
        if not nba_service:
            self.logger.error("NBA服务不可用，无法重启其他服务")
            return False

        # 尝试重启服务
        try:
            success = nba_service.restart_service(service_name)
            if success:
                self.logger.info(f"服务 {service_name} 重启成功")
                # 重置重试计数
                self._service_retry_count[service_name] = 0
            else:
                self.logger.error(f"服务 {service_name} 重启失败")
            return success
        except Exception as e:
            self.logger.error(f"重启服务 {service_name} 时出错: {e}", exc_info=True)
            return False

    def close(self) -> None:
        """关闭所有服务"""
        # 关闭NBA服务
        if 'nba_service' in self._services:
            try:
                self._services['nba_service'].close()
                self.logger.info("NBA服务已关闭")
            except Exception as e:
                self.logger.error(f"关闭NBA服务时发生错误: {e}")

        # 关闭微博服务
        if 'weibo_service' in self._services:
            try:
                self._services['weibo_service'].close()
                self.logger.info("微博服务已关闭")
            except Exception as e:
                self.logger.error(f"关闭微博服务时发生错误: {e}")

        # 关闭AI处理器
        if 'ai_processor' in self._services:
            try:
                ai_processor = self._services['ai_processor']
                if hasattr(ai_processor, 'close') and callable(ai_processor.close):
                    ai_processor.close()
                self.logger.info("AI处理器已关闭")
            except Exception as e:
                self.logger.error(f"关闭AI处理器时发生错误: {e}")

    def _need_ai_service(self) -> bool:
        """判断是否需要AI服务"""
        return self.config.mode in RunMode.get_ai_modes()

    def _need_weibo_service(self) -> bool:
        """判断是否需要微博服务"""
        return self.config.mode in RunMode.get_weibo_modes() and not self.config.no_weibo


# ============6. 应用上下文===============

class AppContext:
    """应用上下文，单例模式，提供全局访问点"""

    _instance = None

    @classmethod
    def get_instance(cls) -> 'AppContext':
        """获取单例实例"""
        if cls._instance is None:
            raise RuntimeError("AppContext尚未初始化")
        return cls._instance

    @classmethod
    def initialize(cls, config: AppConfig) -> 'AppContext':
        """初始化应用上下文"""
        if cls._instance is None:
            cls._instance = AppContext(config)
        return cls._instance

    def __init__(self, config: AppConfig):
        """初始化应用上下文"""
        if AppContext._instance is not None:
            raise RuntimeError("AppContext已经初始化，请使用get_instance获取实例")

        self.config = config
        self.logger = self._init_logger()

    def _init_logger(self) -> logging.Logger:
        """初始化日志器"""
        logger = AppLogger.get_logger(__name__, app_name='nba')

        # 设置日志级别
        if self.config.debug:
            for handler in logging.root.handlers + logger.handlers:
                handler.setLevel(logging.DEBUG)
            logger.setLevel(logging.DEBUG)
            logger.debug("调试模式已启用")

        return logger


# ============7. 主应用类===============

class NBACommandLineApp:
    """NBA 数据服务命令行应用程序"""

    def __init__(self, config: AppConfig):
        """初始化应用程序

        Args:
            config: 应用程序配置
        """
        # 保存配置
        self.config = config

        # 获取日志器
        self.logger = AppContext.get_instance().logger
        self.logger.info("=== NBA数据服务初始化 ===")

        # 加载环境变量
        self._load_environment()

        # 初始化服务管理器
        self.service_manager = ServiceManager(config, self.logger)

        # 初始化服务与数据
        self.nba_service: Optional[NBAService] = None
        self.weibo_service: Optional[WeiboPostService] = None
        self.ai_processor: Optional[AIProcessor] = None
        self.content_generator: Optional[WeiboContentGenerator] = None
        self.video_paths: Dict[str, Path] = {}
        self.chart_paths: Dict[str, Path] = {}
        self.round_gifs: Dict[str, Path] = {}

    def _load_environment(self) -> None:
        """加载环境变量"""
        # 确保系统默认使用 UTF-8 编码
        import sys
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

        # 设置 Python 默认编码为 UTF-8
        import locale
        try:
            # 尝试设置更通用的UTF-8 locale
            locale.setlocale(locale.LC_ALL, 'C.UTF-8')
        except locale.Error:
            try:
                # 回退到特定平台的UTF-8 locale
                locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
            except locale.Error:
                self.logger.warning("无法设置UTF-8 locale，可能导致编码问题")


        # 按优先级加载环境变量
        env_local = self.config.root_dir / '.env.local'
        env_default = self.config.root_dir / '.env'
        env_config = self.config.config_file

        if env_config and env_config.exists():
            load_dotenv(env_config, override=True) # 允许配置文件覆盖
            self.logger.info(f"从 {env_config} 加载环境变量")
        elif env_local.exists():
            load_dotenv(env_local, override=True) # 允许本地文件覆盖
            self.logger.info("从 .env.local 加载环境变量")
        elif env_default.exists():
            load_dotenv(env_default)
            self.logger.info("从 .env 加载环境变量")
        else:
            self.logger.warning("未找到环境变量文件，使用默认配置或系统环境变量")

    def init_services(self) -> None:
        """初始化所有服务"""
        try:
            # 初始化NBA服务
            self.nba_service = self.service_manager.init_nba_service()
            self._verify_nba_service_status()

            # 检查核心数据库状态 (仅在非同步模式下提示)
            if self.config.mode not in RunMode.get_sync_modes():
                self._check_database_status()

            # 初始化AI处理器
            self.ai_processor = self.service_manager.init_ai_processor()

            # 初始化内容生成器
            self.content_generator = self.service_manager.init_content_generator(self.ai_processor)

            # 初始化微博服务
            self.weibo_service = self.service_manager.init_weibo_service(self.content_generator)

            # 验证微博发布所需组件是否完整
            if self.config.mode in RunMode.get_weibo_modes() and not self.config.no_weibo:
                if not self.weibo_service:
                    self.logger.warning("微博服务未初始化，将跳过发布功能")
                if not self.content_generator:
                    self.logger.warning("内容生成器未初始化，将跳过发布功能")

        except Exception as e:
            self.logger.error(f"服务初始化失败: {e}", exc_info=True)
            raise ServiceInitError(f"服务初始化失败: {e}")

    def _verify_nba_service_status(self) -> None:
        """验证关键服务状态"""
        if not self.nba_service:
            raise ServiceInitError("NBA服务未初始化")

        # 获取服务健康状态
        health_status = self.nba_service.check_services_health()

        # 检查关键服务状态
        critical_services = {
            'db_service': "数据库服务",
            'data': "数据服务",
            'adapter': "数据适配器"
        }

        for service_name, display_name in critical_services.items():
            service_health = health_status.get(service_name, {})
            if service_health.get('is_available', False):
                self.logger.info(f"{display_name}状态正常")
            else:
                error_msg = service_health.get('error', '未知错误')
                self.logger.error(f"{display_name}不可用: {error_msg}")
                raise ServiceInitError(f"{display_name}不可用，无法继续执行")

        # 检查非关键服务
        optional_services = {
            'videodownloader': "视频服务",
            'video_processor': "视频处理器",
            'chart': "图表服务"
        }

        for service_name, display_name in optional_services.items():
            service_health = health_status.get(service_name, {})
            if service_health.get('is_available', False):
                self.logger.info(f"{display_name}状态正常")
            else:
                error_msg = service_health.get('error', '未知错误')
                self.logger.warning(f"{display_name}不可用: {error_msg}")

    def _check_database_status(self) -> None:
        """检查数据库状态，提供用户提示"""
        try:
            # 检查核心数据库是否为空
            if self.nba_service.db_service._is_nba_database_empty():
                print("\n提示: 检测到核心数据库(nbadb)为空。")
                print("      首次运行会自动进行初始化同步。")
                print("      如果初始化失败，请稍后手动运行 'sync-new-season' 模式。")


            # 检查统计数据库状态
            stats_progress = self.nba_service.db_service.get_sync_progress()
            if stats_progress and "error" not in stats_progress:
                total = stats_progress.get("total_games", 0)
                synced = stats_progress.get("synced_games", 0)
                remaining = stats_progress.get("remaining_games", 0)
                progress = stats_progress.get("progress_percentage", 0)

                if remaining > 0:
                    print(f"\n提示: 统计数据库(gamedb)同步进度: {progress:.1f}% ({synced}/{total})")
                    print(f"      剩余 {remaining} 场比赛未同步统计数据。")
                    print("      建议运行 'sync' 模式更新数据库：")
                    print("      python main.py --mode sync\n")
                else:
                     print("\n✓ 统计数据库(gamedb)已同步所有已完成比赛。")

        except Exception as e:
            self.logger.warning(f"检查数据库状态时出错: {e}")
            # 继续初始化，不中断流程

    def get_game_data(self) -> Any:
        """获取比赛数据"""
        try:
            game = self.nba_service.get_game(self.config.team, date=self.config.date)
            if not game:
                self.logger.error(f"获取比赛数据失败: 未找到{self.config.team}的比赛数据 (日期: {self.config.date})")
                print(f"× 获取比赛数据失败: 未找到球队 '{self.config.team}' 在日期 '{self.config.date}' 的比赛数据。")
                print("  请检查球队名称和日期是否正确，或运行 'sync' 模式更新赛程。")
            return game
        except Exception as e:
            self.logger.error(f"获取比赛数据失败: {e}", exc_info=True)
            raise DataFetchError(f"获取比赛数据失败: {e}")

    def get_game_ai_data(self, game) -> Dict[str, Any]:
        """获取比赛AI友好数据"""
        try:
            if not game:
                return {} # 返回空字典而不是None

            if not self.nba_service.adapter_service:
                self.logger.error("数据适配器服务不可用")
                return {"error": "数据适配器服务不可用"}

            return self.nba_service.adapter_service.prepare_ai_data(game)
        except Exception as e:
            self.logger.error(f"获取比赛AI友好数据失败: {e}", exc_info=True)
            raise DataFetchError(f"获取比赛AI友好数据失败: {e}")

    def get_team_id(self, team_name: str) -> Optional[int]:
        """获取球队ID"""
        try:
            team_id = self.nba_service.get_team_id_by_name(team_name)
            if not team_id:
                 print(f"× 未在数据库中找到球队 '{team_name}'。请确保球队名称正确或运行 'sync-new-season' 更新核心数据。")
            return team_id
        except Exception as e:
            self.logger.error(f"获取球队ID失败: {e}", exc_info=True)
            raise DataFetchError(f"获取球队ID失败: {e}")

    def get_player_id(self, player_name: str) -> Optional[int]:
        """获取球员ID"""
        try:
            player_id = self.nba_service.get_player_id_by_name(player_name)
            if not player_id:
                 print(f"× 未在数据库中找到球员 '{player_name}'。请确保球员名称正确或运行 'sync-new-season' 更新核心数据。")
            elif isinstance(player_id, list):
                 print(f"× 找到多个名为 '{player_name}' 的球员，请提供更精确的名称。")
                 return None # 不明确时返回None
            return player_id
        except Exception as e:
            self.logger.error(f"获取球员ID失败: {e}", exc_info=True)
            raise DataFetchError(f"获取球员ID失败: {e}")

    def get_team_data(self, game, team_id: int) -> Dict[str, Any]:
        """获取球队AI友好数据"""
        try:
            if not game or not team_id:
                return {}

            if not self.nba_service.adapter_service:
                self.logger.error("数据适配器服务不可用")
                return {"error": "数据适配器服务不可用"}

            return self.nba_service.adapter_service.adapt_for_team_content(game, team_id)
        except Exception as e:
            self.logger.error(f"获取球队AI友好数据失败: {e}", exc_info=True)
            raise DataFetchError(f"获取球队AI友好数据失败: {e}")

    def get_player_data(self, game, player_id: int) -> Dict[str, Any]:
        """获取球员AI友好数据"""
        try:
            if not game or not player_id:
                return {}

            if not self.nba_service.adapter_service:
                self.logger.error("数据适配器服务不可用")
                return {"error": "数据适配器服务不可用"}

            return self.nba_service.adapter_service.adapt_for_player_content(game, player_id)
        except Exception as e:
            self.logger.error(f"获取球员AI友好数据失败: {e}", exc_info=True)
            raise DataFetchError(f"获取球员AI友好数据失败: {e}")

    def get_shot_chart_data(self, game, entity_id: int, is_team: bool) -> Dict[str, Any]:
        """获取投篮图AI友好数据"""
        try:
            if not game or not entity_id:
                return {}

            if not self.nba_service.adapter_service:
                self.logger.error("数据适配器服务不可用")
                return {"error": "数据适配器服务不可用"}

            return self.nba_service.adapter_service.adapt_for_shot_chart(game, entity_id, is_team)
        except Exception as e:
            self.logger.error(f"获取投篮图AI友好数据失败: {e}", exc_info=True)
            raise DataFetchError(f"获取投篮图AI友好数据失败: {e}")

    def get_round_analysis_data(self, game, player_id: int, round_ids: List[int]) -> Dict[str, Any]:
        """获取回合分析AI友好数据"""
        try:
            if not game or not player_id or not round_ids:
                return {}

            if not self.nba_service.adapter_service:
                self.logger.error("数据适配器服务不可用")
                return {"error": "数据适配器服务不可用"}

            return self.nba_service.adapter_service.adapt_for_round_analysis(game, player_id, round_ids)
        except Exception as e:
            self.logger.error(f"获取回合分析AI友好数据失败: {e}", exc_info=True)
            raise DataFetchError(f"获取回合分析AI友好数据失败: {e}")

    def try_restart_service(self, service_name: str) -> bool:
        """尝试重启服务"""
        return self.service_manager.try_restart_service(service_name)

    def check_required_files_for_weibo(self, mode: RunMode) -> bool:
        """检查微博发布所需的文件是否存在"""
        # 对于球队评级模式，不需要检查媒体文件
        if mode == RunMode.WEIBO_TEAM_RATING:
            return True

        try:
            # 获取基础信息
            team_id = self.get_team_id(self.config.team)
            if not team_id:
                # get_team_id 内部已打印错误信息
                return False

            player_id = None
            if self.config.player and mode in [RunMode.WEIBO_PLAYER, RunMode.WEIBO_CHART, RunMode.WEIBO_ROUND]:
                player_id = self.get_player_id(self.config.player)
                if not player_id:
                    # get_player_id 内部已打印错误信息
                    return False

            # 获取比赛数据
            game = self.get_game_data()
            if not game:
                # get_game_data 内部已打印错误信息
                return False

            # 获取比赛ID
            game_data = self.get_game_ai_data(game)
            if not game_data or "error" in game_data:
                print(f"× 未能获取比赛结构化数据: {game_data.get('error', '未知错误')}")
                return False

            game_id = game_data.get("game_info", {}).get("basic", {}).get("game_id")
            if not game_id:
                print("× 未能获取比赛ID")
                return False

            # 根据不同模式检查文件
            result = True
            base_dir = self.nba_service.config.base_output_dir

            # 检查球队视频
            if mode in [RunMode.WEIBO, RunMode.WEIBO_TEAM] and "team_video" not in self.video_paths:
                team_video_dir = base_dir / "videos" / "team_videos" / f"team_{team_id}_{game_id}"
                if team_video_dir.exists():
                    team_video = list(team_video_dir.glob(f"team_{team_id}_{game_id}.mp4"))
                    if team_video:
                        self.video_paths["team_video"] = team_video[0]
                        print(f"✓ 找到球队集锦视频: {team_video[0]}")
                    else:
                        print("× 未找到球队集锦视频，请先运行 --mode video-team 生成视频")
                        result = False
                else:
                    print("× 未找到球队视频目录，请先运行 --mode video-team 生成视频")
                    result = False

            # 检查球员视频
            if mode in [RunMode.WEIBO, RunMode.WEIBO_PLAYER] and "player_video" not in self.video_paths and player_id:
                player_video_dir = base_dir / "videos" / "player_videos" / f"player_{player_id}_{game_id}"
                if player_video_dir.exists():
                    player_video = list(player_video_dir.glob(f"player_{player_id}_{game_id}.mp4"))
                    if player_video:
                        self.video_paths["player_video"] = player_video[0]
                        print(f"✓ 找到球员集锦视频: {player_video[0]}")
                    else:
                        print("× 未找到球员集锦视频，请先运行 --mode video-player 生成视频")
                        result = False
                else:
                    print("× 未找到球员视频目录，请先运行 --mode video-player 生成视频")
                    result = False

            # 检查球员投篮图
            if mode in [RunMode.WEIBO, RunMode.WEIBO_CHART] and "player_chart" not in self.chart_paths and player_id:
                pictures_dir = base_dir / "pictures"
                # 尝试两种可能的命名格式
                player_chart_files = list(pictures_dir.glob(f"player_impact_{game_id}_{player_id}.png")) + \
                                     list(pictures_dir.glob(f"player_shots_{game_id}_{player_id}.png"))
                if player_chart_files:
                    self.chart_paths["player_chart"] = player_chart_files[0] # 取找到的第一个
                    print(f"✓ 找到球员投篮图: {player_chart_files[0]}")
                else:
                    print("× 未找到球员投篮图，请先运行 --mode chart 生成图表")
                    result = False

            # 检查球队投篮图
            if mode in [RunMode.WEIBO, RunMode.WEIBO_TEAM_CHART] and "team_chart" not in self.chart_paths:
                pictures_dir = base_dir / "pictures"
                team_chart = list(pictures_dir.glob(f"team_shots_{game_id}_{team_id}.png"))
                if team_chart:
                    self.chart_paths["team_chart"] = team_chart[0]
                    print(f"✓ 找到球队投篮图: {team_chart[0]}")
                else:
                    print("× 未找到球队投篮图，请先运行 --mode chart 生成图表")
                    result = False

            # 检查球员回合GIF
            if mode in [RunMode.WEIBO, RunMode.WEIBO_ROUND] and not self.round_gifs and player_id:
                gif_dir = base_dir / "gifs" / f"player_{player_id}_{game_id}_rounds"
                if gif_dir.exists():
                    gifs = list(gif_dir.glob(f"event_*_game_{game_id}_player{player_id}_*.gif"))
                    if gifs:
                        # 将找到的GIF添加到round_gifs字典中
                        for gif in gifs:
                            match = re.search(r'event_(\d+)_game_', gif.name)
                            if match:
                                event_id = match.group(1)
                                self.round_gifs[event_id] = gif
                        print(f"✓ 找到 {len(self.round_gifs)} 个球员回合GIF")
                    else:
                        print("× 未找到球员回合GIF，请先运行 --mode video-rounds 生成GIF")
                        result = False
                else:
                    print("× 未找到球员回合GIF目录，请先运行 --mode video-rounds 生成GIF")
                    result = False

            return result

        except Exception as e:
            self.logger.error(f"检查微博发布所需文件时出错: {e}", exc_info=True)
            print(f"× 检查微博发布所需文件时出错: {e}")
            return False


    def run(self) -> int:
        """运行应用程序"""
        result_code = 0  # 默认返回成功
        try:
            # 初始化服务
            self.init_services()

            # 创建并执行对应的命令
            self.logger.info(f"以 {self.config.mode.value} 模式运行应用程序")

            command = NBACommandFactory.create_command(self.config.mode)
            if command:
                success = command.execute(self)
                if not success:
                    self.logger.warning(f"命令 {self.config.mode.value} 执行失败")
                    result_code = 1
            else:
                self.logger.error(f"未找到对应模式的命令: {self.config.mode.value}")
                result_code = 1

            self.logger.info("=== 应用程序运行完成 ===")

        except ServiceInitError as e:
             self.logger.critical(f"服务初始化失败，无法运行: {e}")
             print(f"\n错误: 服务初始化失败，无法运行: {e}")
             print("请检查配置和依赖项。")
             result_code = 1 # 服务初始化失败，返回错误码
        except Exception as e:
            self.logger.error(f"应用程序运行失败: {e}", exc_info=True)
            print(f"\n应用程序运行失败: {e}\n请查看日志获取详细信息")
            result_code = 1

        finally:
            self.cleanup()
            return result_code


    def cleanup(self) -> None:
        """清理资源，关闭所有服务"""
        self.service_manager.close()
        self.logger.info("=== 服务资源已清理完毕 ===")


# ============8. 入口函数===============

def parse_arguments() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="NBA 数据服务应用程序")

    parser.add_argument("--team", default="Lakers", help="指定默认球队，默认为 Lakers")
    parser.add_argument("--player", default="LeBron James", help="指定默认球员，默认为 LeBron James")
    parser.add_argument("--date", default="last", help="指定比赛日期 (YYYY-MM-DD 或 'last')，默认为 last")
    parser.add_argument("--mode", choices=[m.value for m in RunMode], default=RunMode.ALL.value,
                        help=f"指定运行模式 (默认为 all)。可用模式: {', '.join([m.value for m in RunMode])}")
    parser.add_argument("--no-weibo", action="store_true", help="禁用微博发布功能 (即使在 weibo* 或 all 模式下)")
    parser.add_argument("--debug", action="store_true", help="启用调试模式，输出详细日志")
    parser.add_argument("--config", help="指定 .env 配置文件路径")
    # 同步相关参数
    parser.add_argument("--force-update", action="store_true", help="强制更新数据 (主要用于 sync 和 sync-new-season 模式)")

    # 并行同步参数
    parser.add_argument("--max-workers", type=int, default=8, help="并行同步时的最大线程数 (默认为 8)")
    parser.add_argument("--batch-size", type=int, default=50, help="并行同步时的批处理大小 (默认为 50)")

    return parser.parse_args()


def main() -> int:
    """主程序入口"""
    # 解析命令行参数
    args = parse_arguments()

    # 创建应用配置
    config = AppConfig.from_args(args)

    # 初始化应用上下文
    AppContext.initialize(config)

    # 创建并运行应用
    app = NBACommandLineApp(config)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())