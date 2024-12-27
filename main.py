import asyncio
from pathlib import Path
import argparse
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import sys

from nba.services.game_data_service import NBAGameDataProvider

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ANSI颜色代码
COLORS = {
    'green': '\033[92m',
    'red': '\033[91m',
    'blue': '\033[94m',
    'yellow': '\033[93m',
    'reset': '\033[0m'
}


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='NBA数据查询工具')

    # 基本配置
    parser.add_argument('--team', type=str, help='球队名称')
    parser.add_argument('--player', type=str, help='球员名称')
    parser.add_argument('--date', type=str, default='today',
                        help='比赛日期 (YYYY-MM-DD/today/yesterday/last/next)')

    # 缓存配置
    parser.add_argument('--cache-dir', type=str, default='./cache',
                        help='缓存目录路径')
    parser.add_argument('--no-cache', action='store_true',
                        help='禁用缓存')
    parser.add_argument('--debug', action='store_true',
                        help='启用调试模式')

    # 数据查询选项
    parser.add_argument('--all', action='store_true',
                        help='显示所有可用数据')
    parser.add_argument('--game', action='store_true',
                        help='显示比赛数据')
    parser.add_argument('--player-stats', action='store_true',
                        help='显示球员统计')
    parser.add_argument('--team-stats', action='store_true',
                        help='显示球队统计')
    parser.add_argument('--scoring', action='store_true',
                        help='显示得分事件')

    return parser.parse_args()


def format_time(time_str: str) -> str:
    """格式化时间字符串"""
    time_str = time_str.replace('PT', '').replace('M', ':').replace('S', '')
    return time_str[:-3] if time_str.endswith('.00') else time_str


def format_percentage(value: float) -> str:
    """格式化百分比"""
    return f"{value:.1%}" if value is not None else "0.0%"


async def display_game_info(provider: NBAGameDataProvider) -> None:
    """显示比赛信息"""
    try:
        game = await provider.get_game()
        if not game:
            logger.error("未找到比赛数据")
            return

        status_map = {
            True: f"{COLORS['green']}进行中{COLORS['reset']}",
            False: "已结束"
        }

        print(f"\n{COLORS['yellow']}=== 比赛信息 ==={COLORS['reset']}")
        print(f"状态: {status_map.get(game.is_in_progress, '未知')}")
        print(f"主队: {game.game.homeTeam.teamCity} {game.game.homeTeam.teamName} ({game.game.homeTeam.teamTricode})")
        print(f"客队: {game.game.awayTeam.teamCity} {game.game.awayTeam.teamName} ({game.game.awayTeam.teamTricode})")

        # 使用颜色区分比分
        home_color = COLORS['green'] if game.game.homeTeam.score > game.game.awayTeam.score else COLORS['red']
        away_color = COLORS['green'] if game.game.awayTeam.score > game.game.homeTeam.score else COLORS['red']
        print(f"比分: {home_color}{game.game.homeTeam.score}{COLORS['reset']} - "
              f"{away_color}{game.game.awayTeam.score}{COLORS['reset']}")

        # 显示每节比分
        periods = game.get_period_scores(True)
        away_periods = game.get_period_scores(False)
        print("\n每节比分:")
        print("      " + " ".join(f"第{i + 1}节" for i in range(len(periods))))
        print(f"主队: {' '.join(str(score).rjust(3) for score in periods)}")
        print(f"客队: {' '.join(str(score).rjust(3) for score in away_periods)}")

    except Exception as e:
        logger.error(f"显示比赛信息时出错: {e}")


async def display_player_stats(provider: NBAGameDataProvider) -> None:
    """显示球员统计"""
    try:
        stats = await provider.get_player_stats()
        if not stats:
            logger.error(f"未找到球员 {provider.default_player} 的统计数据")
            return

        print(f"\n{COLORS['yellow']}=== {provider.default_player} 的统计数据 ==={COLORS['reset']}")

        # 基础数据
        minutes = getattr(stats, 'minutes', '0')
        minutes = minutes.replace('PT', '').replace('M', '') if 'PT' in minutes else minutes

        basic_stats = {
            '上场时间': f"{minutes}分钟",
            '得分': getattr(stats, 'points', 0),
            '篮板': getattr(stats, 'rebounds', 0),
            '助攻': getattr(stats, 'assists', 0),
            '抢断': getattr(stats, 'steals', 0),
            '盖帽': getattr(stats, 'blocks', 0),
        }

        # 显示基础数据
        max_key_length = max(len(key) for key in basic_stats.keys())
        for key, value in basic_stats.items():
            print(f"{key.rjust(max_key_length)}: {value}")

        # 投篮数据
        print(f"\n{COLORS['blue']}投篮数据:{COLORS['reset']}")
        shooting_stats = {
            '投篮': (
                getattr(stats, 'fieldGoalsMade', 0),
                getattr(stats, 'fieldGoalsAttempted', 0),
                getattr(stats, 'fieldGoalsPercentage', 0.0)
            ),
            '三分': (
                getattr(stats, 'threePointersMade', 0),
                getattr(stats, 'threePointersAttempted', 0),
                getattr(stats, 'threePointersPercentage', 0.0)
            ),
            '罚球': (
                getattr(stats, 'freeThrowsMade', 0),
                getattr(stats, 'freeThrowsAttempted', 0),
                getattr(stats, 'freeThrowsPercentage', 0.0)
            )
        }

        for key, (made, attempted, percentage) in shooting_stats.items():
            print(f"{key}: {made}/{attempted} ({format_percentage(percentage)})")

    except Exception as e:
        logger.error(f"显示球员统计时出错: {str(e)}")
        if logger.level == logging.DEBUG:
            logger.debug("错误详情:", exc_info=True)


async def display_team_stats(provider: NBAGameDataProvider) -> None:
    """显示球队统计"""
    try:
        game = await provider.get_game()
        if not game:
            logger.error(f"未找到球队 {provider.default_team} 的比赛数据")
            return

        team_name = provider.default_team
        team_id = provider._get_team_id(team_name)
        if not team_id:
            logger.error(f"未找到球队 {team_name}")
            return

        # 判断球队是主场还是客场
        is_home = game.game.homeTeam.teamId == team_id
        team = game.game.homeTeam if is_home else game.game.awayTeam
        team_stats = game.get_team_stats(is_home)

        if not team_stats:
            logger.error(f"未找到球队统计数据")
            return

        print(f"\n{COLORS['yellow']}=== {team.teamCity} {team.teamName} 球队统计 ==={COLORS['reset']}")
        print(f"得分: {team.score}")

        # 显示每节得分
        periods = game.get_period_scores(is_home)
        print(f"每节得分: {periods}")

        # 显示详细统计
        print(f"\n{COLORS['blue']}详细统计:{COLORS['reset']}")
        stats_to_display = {
            '助攻': getattr(team_stats, 'assists', 0),
            '篮板': getattr(team_stats, 'reboundsTotal', 0),
            '抢断': getattr(team_stats, 'steals', 0),
            '盖帽': getattr(team_stats, 'blocks', 0),
            '失误': getattr(team_stats, 'turnovers', 0),
            '投篮': f"{getattr(team_stats, 'fieldGoalsMade', 0)}/{getattr(team_stats, 'fieldGoalsAttempted', 0)}",
            '三分': f"{getattr(team_stats, 'threePointersMade', 0)}/{getattr(team_stats, 'threePointersAttempted', 0)}",
            '罚球': f"{getattr(team_stats, 'freeThrowsMade', 0)}/{getattr(team_stats, 'freeThrowsAttempted', 0)}",
        }

        max_key_length = max(len(key) for key in stats_to_display.keys())
        for key, value in stats_to_display.items():
            print(f"{key.rjust(max_key_length)}: {value}")

    except Exception as e:
        logger.error(f"显示球队统计时出错: {e}")
        if logger.level == logging.DEBUG:
            logger.debug("错误详情:", exc_info=True)


async def display_scoring_plays(provider: NBAGameDataProvider) -> None:
    """显示得分事件"""
    try:
        plays = await provider.get_scoring_plays()
        if not plays:
            logger.error("未找到得分事件")
            return

        print(f"\n{COLORS['yellow']}=== 得分事件 ==={COLORS['reset']}")
        current_period = None

        for play in sorted(plays, key=lambda x: (x['period'], x['time'])):
            if 'MISS' in play['description']:
                continue

            if current_period != play['period']:
                current_period = play['period']
                print(f"\n{COLORS['blue']}第 {current_period} 节:{COLORS['reset']}")

            time_str = format_time(play['time'])
            team_color = COLORS['green'] if play['team'] == 'LAL' else COLORS['blue']

            print(f"{time_str:<7} - {team_color}{play['team']:<3}{COLORS['reset']} - "
                  f"{play['player']:<20} {play['description']}")

    except Exception as e:
        logger.error(f"显示得分事件时出错: {e}")


async def main():
    """主函数"""
    try:
        args = parse_args()

        # 设置日志级别
        if args.debug:
            logger.setLevel(logging.DEBUG)

        # 设置缓存
        cache_dir = None if args.no_cache else Path(args.cache_dir)
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

        # 初始化服务
        provider = NBAGameDataProvider(
            default_team=args.team or "Lakers",
            default_player=args.player or "LeBron James",
            date_str=args.date,
            cache_dir=cache_dir
        )

        # 确定要显示的数据
        show_all = args.all or not any([args.game, args.player_stats,
                                        args.team_stats, args.scoring])

        # 创建任务列表
        tasks = []
        if show_all or args.game:
            tasks.append(display_game_info(provider))
        if show_all or args.player_stats:
            tasks.append(display_player_stats(provider))
        if show_all or args.team_stats:
            tasks.append(display_team_stats(provider))
        if show_all or args.scoring:
            tasks.append(display_scoring_plays(provider))

        # 并发执行任务
        await asyncio.gather(*tasks)

    except KeyboardInterrupt:
        print(f"\n{COLORS['yellow']}程序被用户中断{COLORS['reset']}")
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序执行出错: {e}")
        if logger.level == logging.DEBUG:
            logger.debug("错误详情:", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())