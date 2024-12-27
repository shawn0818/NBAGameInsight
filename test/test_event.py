import asyncio
from typing import Tuple, Dict, List
from nba.services.game_data_service import NBAGameDataProvider
from nba.services.event_service import EventService
from nba.models.event_model import Event, EventType

def analyze_shooting_details(events: List[Event]) -> Dict:
    """
    分析投篮详情

    Args:
        events: 事件列表


    Returns:
        Dict: 包含投篮统计的字典
    """
    attempts = [e for e in events if e.actionType in ['2pt', '3pt']]
    made = [e for e in attempts if e.shotResult != "Missed"]
    paint_shots = [e for e in attempts if any(q == 'pointsinthepaint' for q in (e.qualifiers or []))]
    fast_break = [e for e in attempts if any(q == 'fastbreak' for q in (e.qualifiers or []))]
    
    return {
        'total_attempts': len(attempts),
        'made': len(made),
        'paint_shots': len(paint_shots),
        'paint_made': len([s for s in paint_shots if s.shotResult != "Missed"]),
        'fast_break': len(fast_break),
        'fast_break_made': len([s for s in fast_break if s.shotResult != "Missed"])
    }

def analyze_runs(team_events: List[Event]) -> List[Dict]:
    """
    分析得分高潮

    Args:
        team_events: 球队事件列表

    Returns:
        List[Dict]: 得分高潮列表
    """
    runs = []
    current_run = []
    last_score_time = None
    
    for event in sorted(team_events, key=lambda e: e.orderNumber):
        if event.actionType in ['2pt', '3pt', 'freethrow'] and event.shotResult != "Missed":
            if not last_score_time or (
                event.period == last_score_time[0] and 
                _time_difference(event.clock, last_score_time[1]) <= 60
            ):  # 60秒内的连续得分
                current_run.append(event)
            else:
                if len(current_run) >= 3:  # 连续三次以上得分视为高潮
                    runs.append({
                        'period': current_run[0].period,
                        'events': current_run.copy(),
                        'points': sum(
                            3 if e.actionType == '3pt' 
                            else 2 if e.actionType == '2pt' 
                            else 1 
                            for e in current_run
                        ),
                        'start_time': current_run[0].clock,
                        'end_time': current_run[-1].clock
                    })
                current_run = [event]
            last_score_time = (event.period, event.clock)
        
    return runs

def analyze_clutch_performance(events: List[Event]) -> Dict:
    """
    分析关键时刻表现

    Args:
        events: 事件列表

    Returns:
        Dict: 关键时刻统计数据
    """
    clutch_events = [
        e for e in events 
        if e.period == 4 and e.clock and _parse_game_clock(e.clock) <= 300  # 最后5分钟
    ]
    
    clutch_shots = [
        e for e in clutch_events 
        if e.actionType in ['2pt', '3pt']
    ]
    
    return {
        'shots_attempted': len(clutch_shots),
        'shots_made': len([s for s in clutch_shots if s.shotResult != "Missed"]),
        'points': sum(
            3 if e.actionType == '3pt' and e.shotResult != "Missed"
            else 2 if e.actionType == '2pt' and e.shotResult != "Missed"
            else 1 if e.actionType == 'freethrow' and e.shotResult != "Missed"
            else 0
            for e in clutch_events
        ),
        'rebounds': len([e for e in clutch_events if e.actionType == 'rebound']),
        'turnovers': len([e for e in clutch_events if e.actionType == 'turnover'])
    }

def analyze_matchups(events: List[Event]) -> Dict:
    """
    分析对抗数据

    Args:
        events: 事件列表

    Returns:
        Dict: 对抗统计数据
    """
    return {
        'blocks': len([e for e in events if e.actionType == 'block']),
        'steals': len([e for e in events if e.actionType == 'steal']),
        'fouls_drawn': len([e for e in events if e.actionType == 'foul' and e.personId in e.personIdsFilter]),
        'fouls_committed': len([e for e in events if e.actionType == 'foul'])
    }

def _parse_game_clock(clock_str: str) -> int:
    """将比赛时钟转换为秒数"""
    # 格式如 "PT11M52.00S"
    minutes = int(clock_str[2:clock_str.index('M')])
    seconds = float(clock_str[clock_str.index('M')+1:clock_str.index('S')])
    return int(minutes * 60 + seconds)

def _time_difference(clock1: str, clock2: str) -> int:
    """计算两个时间点之间的秒数差"""
    return abs(_parse_game_clock(clock1) - _parse_game_clock(clock2))

async def analyze_game_highlights(team_name: str, date: str = "today") -> None:
    """
    分析比赛精彩集锦数据

    Args:
        team_name: 球队名称
        date: 比赛日期，默认为今天
    """
    # 初始化服务
    game_service = NBAGameDataProvider()
    
    # 获取比赛数据
    game_id, playbyplay, game = await game_service.get_game_info(team_name, date)
    if not playbyplay or not game:
        print("未能获取比赛数据")
        return
        
    # 初始化事件服务
    event_service = EventService(playbyplay)
    
    # 获取比赛基本信息
    print(f"\n=== {game.game.arena.arenaName} 比赛亮点 ===")
    home_team = game.game.homeTeam
    away_team = game.game.awayTeam
    print(f"{home_team.teamName} {home_team.score} - {away_team.score} {away_team.teamName}\n")
    
    # 分析得分表现
    for team in [home_team, away_team]:
        print(f"\n{team.teamName} ({team.teamTricode}) 精彩表现:")
        
        # 获取球队事件
        team_events = event_service.get_team_events(team.teamTricode)
        if not team_events:
            print(f"未找到 {team.teamTricode} 的比赛事件")
            continue

        # 球队整体分析
        shooting = analyze_shooting_details(team_events)
        print("\n球队整体表现:")
        if shooting['total_attempts'] > 0:
            print(f"整体投篮: {shooting['made']}/{shooting['total_attempts']} "
                  f"({shooting['made']/shooting['total_attempts']*100:.1f}%)")
        if shooting['paint_shots'] > 0:
            print(f"油漆区: {shooting['paint_made']}/{shooting['paint_shots']} "
                  f"({shooting['paint_made']/shooting['paint_shots']*100:.1f}%)")
        if shooting['fast_break'] > 0:
            print(f"快攻: {shooting['fast_break_made']}/{shooting['fast_break']} "
                  f"({shooting['fast_break_made']/shooting['fast_break']*100:.1f}%)")

        # 得分高潮
        runs = analyze_runs(team_events)
        if runs:
            print("\n得分高潮:")
            for run in runs:
                print(f"第{run['period']}节 {run['start_time']} 到 {run['end_time']}: "
                      f"{len(run['events'])}个回合轰下{run['points']}分")

        # 关键时刻表现
        clutch = analyze_clutch_performance(team_events)
        if clutch['shots_attempted'] > 0:
            print("\n关键时刻表现（最后5分钟）:")
            print(f"得分: {clutch['points']}分")
            print(f"投篮: {clutch['shots_made']}/{clutch['shots_attempted']} "
                  f"({clutch['shots_made']/clutch['shots_attempted']*100:.1f}%)")
            print(f"篮板: {clutch['rebounds']}")
            print(f"失误: {clutch['turnovers']}")

        # 对抗数据
        matchups = analyze_matchups(team_events)
        print("\n对抗数据:")
        print(f"盖帽: {matchups['blocks']}")
        print(f"抢断: {matchups['steals']}")
        print(f"造犯规: {matchups['fouls_drawn']}")
        print(f"犯规: {matchups['fouls_committed']}")
            
        # 三分球集锦
        three_pointers = [
            event for event in team_events 
            if event.actionType == '3pt' and event.shotResult != "Missed"
        ]
        if three_pointers:
            print("\n三分球集锦:")
            for event in three_pointers:
                shooter = next(
                    (p for p in team.players if p.personId == event.personId), 
                    None
                )
                if shooter:
                    print(f"🏀 第{event.period}节 {event.clock} - {shooter.name} 投中三分！")
        
        # 扣篮集锦
        dunks = [
            event for event in team_events 
            if event.actionType == '2pt' and 
            event.subType == "DUNK" and 
            event.shotResult != "Missed"
        ]
        if dunks:
            print("\n扣篮集锦:")
            for event in dunks:
                dunker = next(
                    (p for p in team.players if p.personId == event.personId), 
                    None
                )
                if dunker:
                    print(f"💥 第{event.period}节 {event.clock} - {dunker.name} 完成扣篮！")
        
        # 统计每节得分
        print("\n各节得分:")
        for period in range(1, 5):  # NBA常规赛有4节
            period_events = [e for e in team_events if e.period == period]
            points = sum(
                3 if e.actionType == '3pt' and e.shotResult != "Missed"
                else 2 if e.actionType == '2pt' and e.shotResult != "Missed"
                else 1 if e.actionType == 'freethrow' and e.shotResult != "Missed"
                else 0
                for e in period_events
            )
            print(f"第{period}节: {points}分")
        
        # 统计球员表现
        print("\n球员表现:")
        for player in team.players:
            if player.played == "1":  # 只统计上场球员
                player_events = event_service.get_player_events(player.personId)
                field_goals = [
                    e for e in player_events 
                    if e.actionType in ['2pt', '3pt']
                ]
                rebounds = [
                    e for e in player_events 
                    if e.actionType == 'rebound'
                ]
                
                made_shots = [e for e in field_goals if e.shotResult != "Missed"]
                player_stats = player.statistics
                
                if player_stats and (player_stats.points > 0 or len(rebounds) > 0):
                    print(f"\n{player.name}:")
                    print(f"得分: {player_stats.points}")
                    if field_goals:
                        fg_pct = len(made_shots) / len(field_goals) * 100
                        print(f"🎯 {len(made_shots)}/{len(field_goals)} 投篮命中率 ({fg_pct:.1f}%)")
                    if rebounds:
                        offensive = len([r for r in rebounds if r.subType == "offensive"])
                        print(f"🏀 {len(rebounds)} 个篮板 (进攻: {offensive})")

if __name__ == "__main__":
    team = "Lakers"
    date = "2024-12-09"
    asyncio.run(analyze_game_highlights(team, date))