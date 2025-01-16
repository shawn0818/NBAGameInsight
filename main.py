# main.py

from pathlib import Path
import logging
from datetime import datetime

from nba.services.nba_service import NBAService
from config.nba_config import NBAConfig  # 导入NBAConfig类
from nba.services.game_charts_service import ShotChartVisualizer, TeamPerformanceVisualizer



# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)


def analyze_game(nba: NBAService, team: str) -> None:
    """分析比赛数据并生成可视化"""
    logger.info(f"开始分析 {team} 的比赛数据...")

    # 获取比赛报告
    game_info = nba.display_game_info(team=team, include_ai_analysis=True)
    if not game_info:
        logger.error(f"未找到 {team} 的比赛数据")
        return

    # 打印基本信息
    logger.info("比赛基本信息:")
    if 'basic_info' in game_info:
        info = game_info['basic_info']
        game_time = info.get('game_time', '未知时间')
        arena = info.get('arena', {})
        arena_name = arena.get('name', '未知场馆')
        arena_city = arena.get('city', '未知城市')
        attendance = arena.get('attendance', '未知观众数')
        print(f"比赛时间：{game_time}")
        print(f"场馆：{arena_name}，{arena_city}")
        print(f"观众：{attendance}")

    # 打印比分
    if 'statistics' in game_info:
        stats = game_info['statistics']
        score = stats.get('score', {})
        home_score = score.get('home', 'N/A')
        away_score = score.get('away', 'N/A')
        print(f"比分：主队 {home_score} - 客队 {away_score}")

    # 打印AI分析报告
    if 'ai_analysis' in game_info:
        print("\nAI 比赛分析:")
        print(game_info['ai_analysis'])


def analyze_player(nba: NBAService, player: str, team: str) -> None:
    """分析球员表现"""
    logger.info(f"开始分析 {player} 的表现...")

    # 获取球员统计数据
    stats = nba.display_player_stats(player=player, include_analysis=True)
    if not stats:
        logger.error(f"未找到 {player} 的统计数据")
        return

    # 打印统计数据
    if 'statistics' in stats:
        print("\n球员数据:")
        stat = stats['statistics']
        points = stat.get('points', 0)
        rebounds = stat.get('rebounds', 0)
        assists = stat.get('assists', 0)
        steals = stat.get('steals', 0)
        blocks = stat.get('blocks', 0)
        turnovers = stat.get('turnovers', 0)
        minutes = stat.get('minutes', 0)
        shooting = stat.get('shooting', {})
        fg = shooting.get('fg', '0/0')
        fg_pct = shooting.get('fg_pct', 0.0)
        three = shooting.get('three', '0/0')
        three_pct = shooting.get('three_pct', 0.0)
        ft = shooting.get('ft', '0/0')
        ft_pct = shooting.get('ft_pct', 0.0)

        print(f"得分: {points}")
        print(f"篮板: {rebounds}")
        print(f"助攻: {assists}")
        print(f"抢断: {steals}")
        print(f"盖帽: {blocks}")
        print(f"失误: {turnovers}")
        print(f"出场时间: {minutes:.1f} 分钟")

        print(f"投篮: {fg} ({fg_pct:.1%})")
        print(f"三分: {three} ({three_pct:.1%})")
        print(f"罚球: {ft} ({ft_pct:.1%})")

    # 生成图表
    current_date = datetime.now().strftime("%Y%m%d")

    # 投篮图表保存路径
    shot_chart_dir = NBAConfig.PATHS.PICTURES_DIR / current_date
    shot_chart_dir.mkdir(parents=True, exist_ok=True)
    shot_chart_path = shot_chart_dir / f"{player.replace(' ', '_')}_shot_chart.png"
    nba.create_shot_chart(
        player=player,
        team=team,
        date=None,  # 使用默认日期
        output_path=shot_chart_path,  # 传递 Path 对象
        show_misses=True,
        show_makes=True,
        annotate=True,
        add_player_photo=True,
        creator_info="数据由 LeBron Bot 提供"  # 添加creator_info参数
    )
    logger.info(f"投篮图表已保存至: {shot_chart_path}")

    # 表现时间线保存路径
    timeline_dir = NBAConfig.PATHS.PICTURES_DIR / current_date
    timeline_dir.mkdir(parents=True, exist_ok=True)
    timeline_path = timeline_dir / f"{player.replace(' ', '_')}_timeline.png"
    nba.create_player_performance_chart(
        player=player,
        team=team,
        date=None,  # 使用默认日期
        output_path=timeline_path
    )
    logger.info(f"表现时间线已保存至: {timeline_path}")

    # 打印AI分析
    if 'analysis' in stats:
        print("\nAI 表现分析:")
        print(stats['analysis'])


def analyze_team(nba: NBAService, team: str) -> None:
    """分析球队表现"""
    logger.info(f"开始分析 {team} 的团队表现...")

    # 获取球队统计数据
    team_stats = nba.display_team_stats(team=team)
    if not team_stats:
        logger.error(f"未找到 {team} 的统计数据")
        return

    # 打印球队统计数据
    print("\n球队统计:")
    for team_side in ['home_team', 'away_team']:
        if team_side in team_stats:
            team_data = team_stats[team_side]
            team_name = team_data.get('name', '未知球队')
            statistics = team_data.get('statistics', {})
            print(f"\n{team_name}:")
            field_goals = statistics.get('field_goals', '0/0')
            field_goals_pct = statistics.get('field_goals_pct', 0.0)
            three_points = statistics.get('three_points', '0/0')
            three_points_pct = statistics.get('three_points_pct', 0.0)
            assists = statistics.get('assists', 0)
            rebounds = statistics.get('rebounds', 0)
            steals = statistics.get('steals', 0)
            blocks = statistics.get('blocks', 0)
            turnovers = statistics.get('turnovers', 0)
            fouls = statistics.get('fouls', 0)  # 假设统计中有犯规数据

            print(f"投篮: {field_goals} ({field_goals_pct:.1%})")
            print(f"三分: {three_points} ({three_points_pct:.1%})")
            print(f"助攻: {assists}")
            print(f"篮板: {rebounds}")
            print(f"抢断: {steals}")
            print(f"盖帽: {blocks}")
            print(f"失误: {turnovers}")
            print(f"犯规: {fouls}")

    # 打印助攻网络
    print("\n助攻网络:")
    assist_network = team_stats.get('assist_network', {})
    for assister, scorers in assist_network.items():
        for scorer, count in scorers.items():
            print(f"{assister} -> {scorer}: {count} 次助攻")

    # 打印抢断统计
    print("\n抢断统计:")
    steal_stats = team_stats.get('steal_stats', {})
    for player, steals in steal_stats.items():
        print(f"{player}: {steals} 次抢断")

    # 打印盖帽统计
    print("\n盖帽统计:")
    block_stats = team_stats.get('block_stats', {})
    for player, blocks in block_stats.items():
        print(f"{player}: {blocks} 次盖帽")

    # 打印犯规统计
    print("\n犯规统计:")
    foul_stats = team_stats.get('foul_stats', {})
    for player, fouls in foul_stats.items():
        print(f"{player}: {fouls} 次犯规")

    # 生成图表
    current_date = datetime.now().strftime("%Y%m%d")

    # 球队对比图保存路径
    comparison_dir = NBAConfig.PATHS.PICTURES_DIR / current_date
    comparison_dir.mkdir(parents=True, exist_ok=True)
    comparison_path = comparison_dir / f"{team}_comparison.png"
    nba.create_team_comparison(
        team=team,
        date=None,  # 使用默认日期
        output_path=comparison_path  # 传递 Path 对象
    )
    logger.info(f"球队对比图表已保存至: {comparison_path}")

    # 使用正确的可视化器创建助攻网络图
    nba.create_assist_network(
        team=team,
        output_path=str(Path(NBAConfig.PATHS.PICTURES_DIR) / f"{team}_assist_network.png")
    )
    logger.info(f"助攻网络图已保存至: {NBAConfig.PATHS.PICTURES_DIR}/{team}_assist_network.png")

    # 比赛流程图保存路径
    flow_dir = NBAConfig.PATHS.PICTURES_DIR / current_date
    flow_dir.mkdir(parents=True, exist_ok=True)
    flow_path = flow_dir / f"{team}_game_flow.png"
    nba.create_game_flow(
        team=team,
        date=None,  # 使用默认日期
        output_path=flow_path  # 传递 Path 对象
    )
    logger.info(f"比赛流程图已保存至: {flow_path}")

    # 分析关键时刻
    key_moments = nba.analyze_game_moments(team=team)
    print("\n比赛关键时刻分析:")
    print(key_moments)


def download_highlights(nba: NBAService, team: str, player: str) -> None:
    """下载比赛集锦"""
    logger.info(f"开始下载 {player} 的精彩表现...")

    try:
        # 设置输出目录
        current_date = datetime.now().strftime("%Y%m%d")
        highlights_dir = NBAConfig.PATHS.GIF_DIR / current_date
        highlights_dir.mkdir(parents=True, exist_ok=True)

        # 下载常规投篮
        fgm_results = nba.download_game_highlights(
            team=team,
            player=player,
            date=None,  # 使用默认日期
            action_type="FGM",
            to_gif=True,
            quality="hd",
            compress=True,
            output_dir=highlights_dir  # 传递 Path 对象
        )
        logger.info(f"下载了 {len(fgm_results)} 个投篮片段")

        # 下载三分球
        three_results = nba.download_game_highlights(
            team=team,
            player=player,
            date=None,  # 使用默认日期
            action_type="FG3M",
            to_gif=True,
            quality="hd",
            compress=True,
            output_dir=highlights_dir  # 传递 Path 对象
        )
        logger.info(f"下载了 {len(three_results)} 个三分球片段")

    except Exception as e:
        logger.error(f"下载精彩片段时出错: {e}")


def main():
    """主函数"""
    # 设置要分析的球队和球员
    TEAM = "Lakers"
    PLAYER = "LeBron James"

    try:
        # 使用上下文管理器初始化NBA服务
        with NBAService(
                default_team=TEAM,
                default_player=PLAYER,
                date_str=None,  # 使用默认日期（如最近一场比赛）
                display_language="zh_CN",
                enable_ai=True
        ) as nba:
            # 1. 分析比赛
            analyze_game(nba, TEAM)

            # 2. 分析球员
            analyze_player(nba, PLAYER, TEAM)

            # 3. 分析球队
            analyze_team(nba, TEAM)

            # 4. 下载集锦
            download_highlights(nba, TEAM, PLAYER)

    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}", exc_info=True)
    finally:
        logger.info("程序运行结束")


if __name__ == "__main__":
    main()
