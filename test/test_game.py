import unittest
import sys
from pathlib import Path

# 将项目根目录添加到Python路径
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

import asyncio
from nba.services.game_data_service import GameDataService

async def analyze_team_performance(service: GameDataService, team_name: str, game_date: str):
    playbyplay, game = await service.get_game_data(team_name, game_date)
    
    if playbyplay is None or game is None:
        print("未能获取比赛数据。")
        return
    
    # 比赛基本信息
    print("\n=== 比赛基本信息 ===")
    print(f"比赛场馆: {game.game.arena.arenaName}")
    print(f"比赛时间: {game.game.gameTimeLocal}")
    print(f"比赛状态: {game.game.gameStatusText}")
    
    # 主队信息
    home_team = game.game.homeTeam
    away_team = game.game.awayTeam
    
    print("\n=== 比分信息 ===")
    print(f"主队 ({home_team.teamName}): {home_team.score}")
    print(f"客队 ({away_team.teamName}): {away_team.score}")
    
    # 每节比分
    print("\n=== 每节得分 ===")
    print("节次    主队    客队")
    for h_period, a_period in zip(home_team.periods, away_team.periods):
        print(f"{h_period.periodType:<8}{h_period.score:<8}{a_period.score}")
    
    # 球员数据
    print("\n=== 主要球员数据 ===")
    print(f"\n{home_team.teamName} 球员数据:")
    for player in home_team.players:
        if player.played == "1":  # 只显示上场球员
            stats = player.statistics
            print(f"\n{player.name} ({player.position}):")
            print(f"得分: {stats.points}, 篮板: {stats.reboundsTotal}, 助攻: {stats.assists}")
            print(f"上场时间: {stats.minutesCalculated}")
            print(f"投篮: {stats.fieldGoalsMade}/{stats.fieldGoalsAttempted} "
                  f"({stats.fieldGoalsPercentage:.1%})")
            print(f"三分: {stats.threePointersMade}/{stats.threePointersAttempted} "
                  f"({stats.threePointersPercentage:.1%})")
    
    print(f"\n{away_team.teamName} 球员数据:")
    for player in away_team.players:
        if player.played == "1":  # 只显示上场球员
            stats = player.statistics
            print(f"\n{player.name} ({player.position}):")
            print(f"得分: {stats.points}, 篮板: {stats.reboundsTotal}, 助攻: {stats.assists}")
            print(f"上场时间: {stats.minutesCalculated}")
            print(f"投篮: {stats.fieldGoalsMade}/{stats.fieldGoalsAttempted} "
                  f"({stats.fieldGoalsPercentage:.1%})")
            print(f"三分: {stats.threePointersMade}/{stats.threePointersAttempted} "
                  f"({stats.threePointersPercentage:.1%})")
    
    # 修改团队数据对比部分
    print("\n=== 团队数据对比 ===")
    print(f"{'指标':<15}{'主队':<10}{'客队'}")
    
    def format_percentage(value: float) -> str:
        """格式化百分比显示"""
        if value is None:
            return "0.0%"
        return f"{value*100:.1f}%"
    
    def format_number(value: int) -> str:
        """格式化数字显示"""
        if value is None:
            return "0"
        return str(value)

    # 获取统计数据
    home_stats = game.game.homeTeam.statistics
    away_stats = game.game.awayTeam.statistics
    
    # 输出各项统计
    stats_to_show = [
        ("投篮命中率", "fieldGoalsPercentage", format_percentage),
        ("三分命中率", "threePointersPercentage", format_percentage),
        ("罚球命中率", "freeThrowsPercentage", format_percentage),
        ("助攻", "assists", format_number),
        ("篮板", "reboundsTotal", format_number),
        ("失误", "turnovers", format_number),
        ("抢断", "steals", format_number),
        ("盖帽", "blocks", format_number)
    ]

    for label, key, formatter in stats_to_show:
        home_value = formatter(home_stats.get(key, 0))
        away_value = formatter(away_stats.get(key, 0))
        print(f"{label:<15}{home_value:<10}{away_value}")

if __name__ == "__main__":
    service = GameDataService()
    team = "Lakers"
    date = "2024-12-09"
    asyncio.run(analyze_team_performance(service, team, date))