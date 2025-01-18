# main.py

"""
NBA数据分析主程序
提供比赛、球员、球队数据的分析和可视化。
"""

import logging
import os
from pathlib import Path

from nba.services.nba_service import NBAService, NBAServiceConfig
from config.nba_config import NBAConfig

logger = logging.getLogger(__name__)


def print_game_info(game_info: dict) -> None:
    """打印比赛信息"""
    if not game_info:
        logger.warning("无比赛信息")
        return

    # 打印基本信息
    print("\n=== 比赛基本信息 ===")
    if basic_info := game_info.get('basic_info'):
        print(basic_info)

    # 打印实时状态
    print("\n=== 比赛实时状态 ===")
    if live_status := game_info.get('live_status'):
        print(live_status)

    # 打印统计数据
    print("\n=== 比赛统计 ===")
    if stats := game_info.get('statistics'):
        home_team = stats.get('home_team', {})
        away_team = stats.get('away_team', {})

        print(f"主队 {home_team.get('name')}:")
        _print_team_stats(home_team.get('stats', {}))

        print(f"\n客队 {away_team.get('name')}:")
        _print_team_stats(away_team.get('stats', {}))

    # 打印AI分析
    if ai_analysis := game_info.get('ai_analysis'):
        print("\n=== AI 分析 ===")
        print(ai_analysis)


def print_player_stats(player_stats: dict) -> None:
    """打印球员统计"""
    if not player_stats:
        logger.warning("无球员数据")
        return

    print(f"\n=== {player_stats.get('name', '未知球员')} 统计 ===")
    if stats := player_stats.get('stats'):
        print(stats)


def _print_team_stats(stats: dict) -> None:
    """打印球队统计数据"""
    if not stats:
        print("暂无统计数据")
        return

    # 投篮数据
    shooting_stats = [
        ('投篮', 'field_goals', 'field_goals_pct'),
        ('三分', 'three_points', 'three_points_pct')
    ]
    for label, attempts_key, pct_key in shooting_stats:
        attempts = stats.get(attempts_key, '0/0')
        pct = stats.get(pct_key, 0.0)
        print(f"{label}: {attempts} ({pct:.1%})")

    # 其他数据
    other_stats = [
        ('助攻', 'assists'),
        ('篮板', 'rebounds'),
        ('抢断', 'steals'),
        ('盖帽', 'blocks'),
        ('失误', 'turnovers')
    ]
    for label, key in other_stats:
        value = stats.get(key, 0)
        print(f"{label}: {value}")


def main():
    """主函数"""
    # 基础配置
    TEAM = "Lakers"
    PLAYER = "LeBron James"

    # 获取API密钥
    api_key = os.getenv("OPENAI_API_KEY")

    # 创建服务配置
    config = NBAServiceConfig(
        default_team=TEAM,
        default_player=PLAYER,
        display_language="zh_CN",
        show_advanced_stats=True,
        enable_ai=bool(api_key),
        ai_api_key=api_key,
        output_dir=Path(NBAConfig.PATHS.PICTURES_DIR),
        log_level=logging.INFO
    )

    try:
        with NBAService(config) as nba:
            logger.info(f"正在查询 {TEAM} 的比赛数据...")

            # 1. 获取并分析比赛信息
            game_info = nba.get_game_info(
                team=TEAM,
                include_ai_analysis=bool(api_key)
            )
            print_game_info(game_info)

            if not game_info:
                logger.info(f"{TEAM} 暂无比赛数据")
                return

            # 以下分析只在有比赛数据时进行
            logger.info("比赛数据分析完成")

            # 2. 获取并分析球员数据
            logger.info(f"开始分析 {PLAYER} 的表现...")
            player_stats = nba.get_player_stats(
                player_name=PLAYER,
                team=TEAM
            )
            print_player_stats(player_stats)
            logger.info("球员数据分析完成")

            # 3. 获取并分析球队数据
            logger.info(f"开始分析 {TEAM} 的团队表现...")
            team_stats = nba.get_team_stats(team=TEAM)
            if team_stats:
                print(f"\n=== {TEAM} 团队统计 ===")
                _print_team_stats(team_stats)
            logger.info("球队数据分析完成")

            # 4. 生成投篮图表
            logger.info("开始生成投篮分布图...")

            # 球队投篮图
            team_chart_path = nba.create_shot_chart(team=TEAM)
            if team_chart_path:
                logger.info(f"球队投篮图已保存至: {team_chart_path}")

            # 球员投篮图
            player_chart_path = nba.create_shot_chart(
                team=TEAM,
                player_name=PLAYER
            )
            if player_chart_path:
                logger.info(f"球员投篮图已保存至: {player_chart_path}")

    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}", exc_info=True)
    else:
        logger.info("数据分析完成")
    finally:
        logger.info("程序运行结束")


if __name__ == "__main__":
    # 确保配置初始化
    NBAConfig.initialize()
    main()