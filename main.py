from pathlib import Path
import argparse
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import sys

from nba.services.game_data_service import NBAGameDataProvider, NBAGameDataError

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


def display_game_info(provider: NBAGameDataProvider) -> None:
    """显示比赛信息"""
    try:
        game, error = provider.get_game_safe()
        if error:
            logger.error(f"获取比赛数据失败: {error}")
            return
        if not game:
            logger.error("未找到比赛数据")
            return

        # 1. 基本信息
        print(f"\n{COLORS['yellow']}=== 比赛基本信息 ==={COLORS['reset']}")
        status_map = {
            1: "未开始",
            2: f"{COLORS['green']}进行中{COLORS['reset']}",
            3: "已结束"
        }
        print(f"状态: {status_map.get(game.game.gameStatus, '未知')}")
        
        # 2. 场馆信息
        arena = game.game.arena
        print(f"\n{COLORS['blue']}场馆信息:{COLORS['reset']}")
        print(f"场馆: {arena.arenaName}")
        print(f"地点: {arena.arenaCity}, {arena.arenaState}, {arena.arenaCountry}")
        print(f"时区: {arena.arenaTimezone}")

        # 3. 球队信息
        print(f"\n{COLORS['blue']}球队信息:{COLORS['reset']}")
        home_team = game.game.homeTeam
        away_team = game.game.awayTeam
        
        print("主队:")
        print(f"  {home_team.teamCity} {home_team.teamName} ({home_team.teamTricode})")
        print(f"  暂停剩余: {home_team.timeoutsRemaining}")
        print(f"  罚球次数: {'在罚球线内' if home_team.inBonus == '1' else '未在罚球线内'}")
        
        print("客队:")
        print(f"  {away_team.teamCity} {away_team.teamName} ({away_team.teamTricode})")
        print(f"  暂停剩余: {away_team.timeoutsRemaining}")
        print(f"  罚球次数: {'在罚球线内' if away_team.inBonus == '1' else '未在罚球线内'}")

        # 4. 比分信息
        print(f"\n{COLORS['blue']}比分信息:{COLORS['reset']}")
        home_color = COLORS['green'] if home_team.score > away_team.score else COLORS['red']
        away_color = COLORS['green'] if away_team.score > home_team.score else COLORS['red']
        print(f"当前比分: {home_color}{home_team.score}{COLORS['reset']} - "
              f"{away_color}{away_team.score}{COLORS['reset']}")

        # 5. 每节比分
        print("\n每节比分详情:")
        headers = []
        home_scores = []
        away_scores = []
        
        for p in home_team.periods:
            period_type = "加时" if p.period > 4 else f"第{p.period}节"
            headers.append(period_type.rjust(6))
            home_scores.append(str(p.score).rjust(6))
            away_scores.append(str(next(ap.score for ap in away_team.periods if ap.period == p.period)).rjust(6))

        print("      " + " ".join(headers))
        print(f"主队: {' '.join(home_scores)}")
        print(f"客队: {' '.join(away_scores)}")

        # 6. 裁判信息
        print(f"\n{COLORS['blue']}裁判信息:{COLORS['reset']}")
        for official in game.game.officials:
            print(f"{official.assignment}: {official.name} (#{official.jerseyNum})")

        # 7. 首发阵容
        print(f"\n{COLORS['blue']}首发阵容:{COLORS['reset']}")
        print("主队首发:")
        for player in home_team.players:
            if player.starter == "1":
                print(f"  #{player.jerseyNum} {player.name} ({player.position})")
        
        print("\n客队首发:")
        for player in away_team.players:
            if player.starter == "1":
                print(f"  #{player.jerseyNum} {player.name} ({player.position})")

        # 8. 当前在场球员
        if game.game.gameStatus == 2:  # 比赛进行中
            print(f"\n{COLORS['blue']}当前在场球员:{COLORS['reset']}")
            print("主队场上球员:")
            for player in home_team.players:
                if player.oncourt == "1":
                    print(f"  #{player.jerseyNum} {player.name}")
            
            print("\n客队场上球员:")
            for player in away_team.players:
                if player.oncourt == "1":
                    print(f"  #{player.jerseyNum} {player.name}")

    except Exception as e:
        logger.error(f"显示比赛信息时出错: {e}")
        if logger.level == logging.DEBUG:
            logger.debug("错误详情:", exc_info=True)


def display_player_stats(provider: NBAGameDataProvider) -> None:
    """显示球员统计"""
    try:
        player_id = provider.get_player_id()
        if not player_id:
            return

        game = provider.get_game()
        if not game:
            return

        stats = game.get_player_stats(player_id)
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

        # 1. 得分细节
        print(f"\n{COLORS['blue']}得分细节:{COLORS['reset']}")
        points_detail = {
            '总得分': stats.points,
            '油漆区得分': stats.pointsInThePaint,
            '二次进攻得分': stats.pointsSecondChance,
            '快攻得分': stats.pointsFastBreak,
        }
        for key, value in points_detail.items():
            print(f"{key}: {value}")

        # 2. 投篮位置分布
        print(f"\n{COLORS['blue']}投篮位置分布:{COLORS['reset']}")
        shot_stats = [
            ('总投篮', stats.fieldGoalsMade, stats.fieldGoalsAttempted, stats.fieldGoalsPercentage),
            ('三分球', stats.threePointersMade, stats.threePointersAttempted, stats.threePointersPercentage),
            ('罚球', stats.freeThrowsMade, stats.freeThrowsAttempted, stats.freeThrowsPercentage)
        ]
        for name, made, attempted, percentage in shot_stats:
            if attempted > 0:
                print(f"{name}: {made}/{attempted} ({format_percentage(percentage)})")

        # 3. 进阶数据
        print(f"\n{COLORS['blue']}进阶数据:{COLORS['reset']}")
        advanced_stats = {
            '真实命中率': getattr(stats, 'trueShootingPercentage', 0.0),
            '有效命中率': getattr(stats, 'effectiveFieldGoalPercentage', 0.0),
            '使用率': getattr(stats, 'usagePercentage', 0.0),
            '助攻率': getattr(stats, 'assistPercentage', 0.0),
            '篮板率': getattr(stats, 'reboundPercentage', 0.0),
        }
        for key, value in advanced_stats.items():
            print(f"{key}: {format_percentage(value)}")

        # 4. 防守数据
        print(f"\n{COLORS['blue']}防守数据:{COLORS['reset']}")
        defense_stats = {
            '防守篮板': getattr(stats, 'reboundsDefensive', 0),
            '抢断': getattr(stats, 'steals', 0),
            '盖帽': getattr(stats, 'blocks', 0),
            '防守犯规': getattr(stats, 'foulsDrawn', 0),
        }
        for key, value in defense_stats.items():
            print(f"{key}: {value}")

        # 5. 其他数据
        print(f"\n{COLORS['blue']}其他数据:{COLORS['reset']}")
        other_stats = {
            '失误': getattr(stats, 'turnovers', 0),
            '犯规': getattr(stats, 'foulsPersonal', 0),
            '技术犯规': getattr(stats, 'foulsTechnical', 0),
            '+/-': getattr(stats, 'plusMinusPoints', 0),
        }
        for key, value in other_stats.items():
            print(f"{key}: {value}")

    except Exception as e:
        logger.error(f"显示球员统计时出错: {str(e)}")
        if logger.level == logging.DEBUG:
            logger.debug("错误详情:", exc_info=True)


def display_team_stats(provider: NBAGameDataProvider) -> None:
    """显示球队统计"""
    try:
        game = provider.get_game()
        if not game:
            return

        team_name = provider.default_team
        team_id = provider._get_team_id(team_name)
        if not team_id:
            logger.error(f"未找到球队 {team_name}")
            return

        is_home = game.game.homeTeam.teamId == team_id
        team = game.game.homeTeam if is_home else game.game.awayTeam
        team_stats = game.get_team_stats(is_home)

        if not team_stats:
            logger.error(f"未找到球队统计数据")
            return

        print(f"\n{COLORS['yellow']}=== {team.teamCity} {team.teamName} 球队统计 ==={COLORS['reset']}")
        
        # 1. 得分分布
        print(f"\n{COLORS['blue']}得分分布:{COLORS['reset']}")
        print(f"总得分: {team.score}")
        print(f"油漆区得分: {team.get_stat('pointsInThePaint', 0)}")
        print(f"快攻得分: {team.get_stat('pointsFastBreak', 0)}")
        print(f"二次进攻得分: {team.get_stat('pointsSecondChance', 0)}")
        print(f"最大领先: {team.get_stat('leadLargest', 0)}")

        # 2. 投篮数据
        print(f"\n{COLORS['blue']}投篮数据:{COLORS['reset']}")
        made, attempted, percentage = team.field_goals
        print(f"总投篮: {made}/{attempted} ({format_percentage(percentage)})")
        
        made, attempted, percentage = team.three_pointers
        print(f"三分球: {made}/{attempted} ({format_percentage(percentage)})")
        
        made, attempted, percentage = team.free_throws
        print(f"罚球: {made}/{attempted} ({format_percentage(percentage)})")

        # 3. 篮板数据
        print(f"\n{COLORS['blue']}篮板数据:{COLORS['reset']}")
        print(f"总篮板: {team.get_stat('reboundsTotal')}")
        print(f"前场篮板: {team.get_stat('reboundsOffensive')}")
        print(f"后场篮板: {team.get_stat('reboundsDefensive')}")

        # 4. 其他数据
        print(f"\n{COLORS['blue']}其他数据:{COLORS['reset']}")
        other_stats = {
            '助攻': team.get_stat('assists'),
            '抢断': team.get_stat('steals'),
            '盖帽': team.get_stat('blocks'),
            '失误': team.get_stat('turnovers'),
            '犯规': team.get_stat('foulsPersonal'),
            '技术犯规': team.get_stat('foulsTechnical')
        }
        max_key_length = max(len(key) for key in other_stats.keys())
        for key, value in other_stats.items():
            print(f"{key.rjust(max_key_length)}: {value}")

        # 5. 替补席数据
        print(f"\n{COLORS['blue']}替补席得分:{COLORS['reset']}")
        bench_points = sum(p.statistics.points for p in team.players if p.starter != "1")
        print(f"替补得分: {bench_points}")

    except Exception as e:
        logger.error(f"显示球队统计时出错: {e}")
        if logger.level == logging.DEBUG:
            logger.debug("错误详情:", exc_info=True)


def display_scoring_plays(provider: NBAGameDataProvider) -> None:
    """显示得分事件"""
    try:
        # 获取比赛数据以确定主队三字母代码
        game = provider.get_game()
        if not game:
            return
        home_team_code = game.game.homeTeam.teamTricode

        plays = provider.get_scoring_plays()
        if not plays:
            logger.error("未找到得分事件")
            return

        print(f"\n{COLORS['yellow']}=== 得分事件分析 ==={COLORS['reset']}")
        
        # 1. 得分事件统计
        print(f"\n{COLORS['blue']}得分类型统计:{COLORS['reset']}")
        scoring_types = {
            '两分球': 0,
            '三分球': 0,
            '罚球': 0,
            '快攻': 0,
            '二次进攻': 0,
        }
        
        # 2. 得分时间分布
        period_scores = {}
        clutch_plays = []  # 关键时刻得分
        
        for play in plays:
            # 统计得分类型
            if '3PT' in play['description']:
                scoring_types['三分球'] += 1
            elif 'Free Throw' in play['description']:
                scoring_types['罚球'] += 1
            else:
                scoring_types['两分球'] += 1
                
            if 'fastbreak' in play.get('qualifiers', []):
                scoring_types['快攻'] += 1
            if '2ndchance' in play.get('qualifiers', []):
                scoring_types['二次进攻'] += 1
                
            # 记录每节得分
            period = play['period']
            if period not in period_scores:
                period_scores[period] = {'home': 0, 'away': 0}
            
            points = 3 if '3PT' in play['description'] else (1 if 'Free Throw' in play['description'] else 2)
            is_home = play['team'] == home_team_code
            period_scores[period]['home' if is_home else 'away'] += points
            
            # 检查关键时刻得分
            if (period >= 4 and 
                play['time'] <= "5:00" and 
                abs(play.get('score_diff', 0)) <= 5):
                clutch_plays.append(play)

        # 显示统计结果
        for score_type, count in scoring_types.items():
            if count > 0:
                print(f"{score_type}: {count}")

        # 显示每节得分分布
        if period_scores:
            print(f"\n{COLORS['blue']}每节得分分布:{COLORS['reset']}")
            for period, scores in sorted(period_scores.items()):
                period_name = f"第{period}节" if period <= 4 else f"加时{period-4}"
                print(f"{period_name}: 主队 {scores['home']} - {scores['away']} 客队")
            
        # 显示关键时刻表现
        if clutch_plays:
            print(f"\n{COLORS['blue']}关键时刻表现:{COLORS['reset']}")
            for play in clutch_plays:
                print(f"第{play['period']}节 {play['time']} - {play['description']}")

    except Exception as e:
        logger.error(f"显示得分事件时出错: {e}")
        if logger.level == logging.DEBUG:
            logger.debug("错误详情:", exc_info=True)


def main():
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

        # 顺序执行显示函数
        if show_all or args.game:
            display_game_info(provider)
        if show_all or args.player_stats:
            display_player_stats(provider)
        if show_all or args.team_stats:
            display_team_stats(provider)
        if show_all or args.scoring:
            display_scoring_plays(provider)

    except KeyboardInterrupt:
        print(f"\n{COLORS['yellow']}程序被用户中断{COLORS['reset']}")
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序执行出错: {e}")
        if logger.level == logging.DEBUG:
            logger.debug("错误详情:", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()