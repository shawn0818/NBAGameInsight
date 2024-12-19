from typing import List, Optional
from nba.models.event_model import PlayByPlay, Event

class EventService:
    """比赛事件服务类，用于处理比赛事件流数据的分析。"""
    
    def __init__(self, playbyplay: PlayByPlay):
        """
        初始化事件服务
        
        Args:
            playbyplay (PlayByPlay): 比赛事件数据
        """
        self.playbyplay = playbyplay
        self._events = None

    @property
    def events(self) -> List[Event]:
        """获取所有事件"""
        if self._events is None:
            self._events = self.playbyplay.actions
        return self._events

    def get_player_events(self, player_id: int) -> List[Event]:
        """
        获取指定球员参与的所有事件
        
        Args:
            player_id (int): 球员ID
            
        Returns:
            List[Event]: 球员相关事件列表
        """
        return [
            event for event in self.events
            if (event.personId == player_id or 
                (event.personIdsFilter and player_id in event.personIdsFilter))
        ]

    def get_team_events(self, team_tricode: str) -> List[Event]:
        """
        获取指定球队的所有事件
        
        Args:
            team_tricode (str): 球队三字母代码 (如 "LAL")
            
        Returns:
            List[Event]: 球队相关事件列表
        """
        return [
            event for event in self.events
            if event.teamTricode == team_tricode
        ]

    def get_quarter_events(self, period: int) -> List[Event]:
        """
        获取指定节的所有事件
        
        Args:
            period (int): 比赛节次（1-4为常规时间，>4为加时赛）
            
        Returns:
            List[Event]: 该节的事件列表
        """
        return [event for event in self.events if event.period == period]

    def get_player_scoring_events(self, player_id: int) -> List[Event]:
        """
        获取球员的得分事件
        
        Args:
            player_id (int): 球员ID
            
        Returns:
            List[Event]: 得分事件列表
        """
        player_events = self.get_player_events(player_id)
        return [
            event for event in player_events
            if (event.actionType in ['2pt', '3pt', 'freethrow'] and
                event.shotResult != "Missed")
        ]

    def get_scoring_plays(self, team_tricode: Optional[str] = None) -> List[Event]:
        """
        获取得分回合
        
        Args:
            team_tricode (Optional[str]): 球队三字母代码，如果不提供则返回所有得分
            
        Returns:
            List[Event]: 得分事件列表
        """
        scoring_events = [
            event for event in self.events
            if (event.actionType in ['2pt', '3pt', 'freethrow'] and
                event.shotResult != "Missed")
        ]
        
        if team_tricode:
            scoring_events = [
                event for event in scoring_events 
                if event.teamTricode == team_tricode
            ]
            
        return scoring_events


'''Event Service 使用指南

EventService 提供了对 NBA 比赛事件流的详细分析功能。下面是一些常见的使用场景和示例代码。

1. 基本使用
```python
from nba.services.game_data_service import GameDataService
from nba.services.event_service import EventService

async def analyze_player_performance():
    # 初始化服务
    service = GameDataService()
    
    # 获取比赛数据
    playbyplay, game = await service.get_game_data("Lakers", "2024-12-09")
    
    # 创建事件服务实例
    event_service = EventService(playbyplay)
    
    # 获取某个球员的所有事件
    lebron_events = event_service.get_player_events(2544)  # LeBron的ID

    def analyze_player_shooting(events: List[Event]):
    # 获取所有投篮
    shots = [e for e in events 
            if e.actionType in ['2pt', '3pt']]
    
    # 统计三分球
    threes = [s for s in shots if s.actionType == '3pt']
    three_makes = [s for s in threes if s.shotResult != "Missed"]
    
    # 统计两分球
    twos = [s for s in shots if s.actionType == '2pt']
    two_makes = [s for s in twos if s.shotResult != "Missed"]
    
    print(f"两分球: {len(two_makes)}/{len(twos)}")
    print(f"三分球: {len(three_makes)}/{len(threes)}")
    print(f"总命中率: {(len(two_makes) + len(three_makes))/len(shots):.1%}")

    def analyze_matchup(events: List[Event], player1_id: int, player2_id: int):
    # 找到两个球员直接对位的事件
    matchup_events = [
        e for e in events
        if e.personIdsFilter and 
        player1_id in e.personIdsFilter and 
        player2_id in e.personIdsFilter
    ]
    
    # 分析具体对位情况
    blocks = [e for e in matchup_events if e.actionType == 'block']
    steals = [e for e in matchup_events if e.actionType == 'steal']
    fouls = [e for e in matchup_events if e.actionType == 'foul']

    def track_game_flow(events: List[Event]):
    score_changes = []
    for event in sorted(events, key=lambda e: e.orderNumber):
        if event.scoreHome and event.scoreAway:
            score_changes.append({
                'time': event.clock,
                'period': event.period,
                'home_score': int(event.scoreHome),
                'away_score': int(event.scoreAway),
                'action': event.actionType
            })
    return score_changes

    def analyze_team_chemistry(events: List[Event]):
    # 找出助攻
    assists = []
    for event in events:
        if event.actionType in ['2pt', '3pt'] and event.shotResult != "Missed":
            # 查找助攻者
            assist_event = next(
                (e for e in events 
                 if e.orderNumber < event.orderNumber and 
                 e.actionType == 'assist' and 
                 e.personId != event.personId),
                None
            )
            if assist_event:
                assists.append({
                    'scorer': event.personId,
                    'assister': assist_event.personId,
                    'points': 3 if event.actionType == '3pt' else 2
                })

                def analyze_clutch_time(events: List[Event]):
    # 获取最后5分钟的事件
    clutch_events = [
        e for e in events
        if e.period >= 4 and  # 第四节或加时
        e.clock and 
        int(e.clock[2:4]) <= 5  # 最后5分钟
    ]
    
    # 分析关键时刻表现
    clutch_shots = [
        e for e in clutch_events
        if e.actionType in ['2pt', '3pt']
    ]
'''