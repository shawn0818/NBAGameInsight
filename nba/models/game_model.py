import logging
from pydantic import BaseModel, Field, validator, model_validator, ValidationError
from typing import Optional, List, Any, Dict, Literal
from datetime import datetime
from enum import IntEnum, Enum
from nba.models.player_model import PlayerProfile, PlayerRegistry
from nba.models.team_model import TeamProfile


# 1. 基础枚举类
class EventCategory(str, Enum):
    PERIOD_START = "period"
    JUMPBALL = "jumpball"
    TWO_POINT = "2pt"
    THREE_POINT = "3pt"
    FREE_THROW = "freethrow"
    REBOUND = "rebound"
    TURNOVER = "turnover"
    BLOCK = "block"
    STEAL = "steal"
    ASSIST = "assist"
    TIMEOUT = "timeout"
    SUBSTITUTION = "substitution"
    FOUL = "foul"
    VIOLATION = "violation"


class TwoPointSubType(str, Enum):
    """2分球类型"""
    JUMP_SHOT = "Jump Shot"
    LAYUP = "Layup"
    HOOK = "Hook"
    DUNK = "Dunk"
    FLOATING = "Floating"          # 漂移投篮
    FINGER_ROLL = "Finger Roll"    # 上篮
    PUTBACK = "Putback"           # 补篮
    REVERSE = "Reverse"           # 反手上篮


class ThreePointSubType(str, Enum):
    JUMP_SHOT = "Jump Shot"


class ReboundSubType(str, Enum):
    OFFENSIVE = "offensive"
    DEFENSIVE = "defensive"


class TurnoverSubType(str, Enum):
    LOST_BALL = "lost ball"
    BAD_PASS = "bad pass"
    OFFENSIVE_FOUL = "offensive foul"
    OUT_OF_BOUNDS = "out-of-bounds"
    SHOT_CLOCK = "shot clock"


class FoulSubType(str, Enum):
    OFFENSIVE = "offensive"
    PERSONAL = "personal"
    SHOOTING = "shooting"
    LOOSE_BALL = "loose ball"


class ShotQualifier(str, Enum):
    """投篮限定词"""
    # 位置相关
    POINTS_IN_PAINT = "pointsinthepaint"  # 在油漆区内得分
    ABOVE_THE_BREAK_3 = "abovethebreak3"  # 底角三分
    CORNER_3 = "corner3"                  # 底角三分
    
    # 进攻方式
    SECOND_CHANCE = "2ndchance"           # 二次进攻机会
    FAST_BREAK = "fastbreak"              # 快攻
    FROM_TURNOVER = "fromturnover"        # 来自对方失误
    
    # 投篮动作
    DRIVING = "driving"                   # 突破
    FADEAWAY = "fadeaway"                 # 后仰跳投
    HOOK = "hook"                         # 勾手
    PULLUP = "pullup"                     # 急停跳投
    STEPBACK = "stepback"                 # 后撤步
    TURNAROUND = "turnaround"             # 转身跳投
    ALLEY_OOP = "alleyoop"               # 空接
    TIP = "tip"                          # 补篮
    CUTTING = "cutting"                   # 切入
    
    # 防守情况
    DEFENDED = "defended"                 # 有防守
    UNDEFENDED = "undefended"             # 无防守
    CONTESTED = "contested"               # 受干扰
    UNCONTESTED = "uncontested"           # 未受干扰
    
    # 其他
    AND_ONE = "andone"                    # 打成2+1
    BLOCKED = "blocked"                   # 被盖帽


class GameStatusEnum(IntEnum):
    NOT_STARTED = 1
    IN_PROGRESS = 2
    FINISHED = 3


# 2. 基础数据模型
class Arena(BaseModel):
    arenaId: int = Field(..., description="场馆ID")
    arenaName: str = Field(..., description="场馆名称")
    arenaCity: str = Field(..., description="场馆城市")
    arenaState: str = Field(..., description="场馆州")
    arenaCountry: str = Field(..., description="场馆国家")
    arenaTimezone: str = Field(..., description="场馆时区")


class Official(BaseModel):
    personId: int = Field(..., description="裁判ID")
    name: str = Field(..., description="裁判姓名")
    nameI: str = Field(..., description="裁判姓名缩写")
    firstName: str = Field(..., description="裁判名")
    familyName: str = Field(..., description="裁判姓")
    jerseyNum: str = Field(..., description="裁判号码")
    assignment: str = Field(..., description="裁判职位")


class PeriodScore(BaseModel):
    period: int = Field(..., description="节次")
    periodType: str = Field(..., description="节次类型")
    score: int = Field(..., description="得分")


class PlayerStatistics(BaseModel):
    assists: int = Field(0)
    blocks: int = Field(0)
    blocksReceived: int = Field(0)
    fieldGoalsAttempted: int = Field(0)
    fieldGoalsMade: int = Field(0)
    fieldGoalsPercentage: float = Field(0.0)
    foulsOffensive: int = Field(0)
    foulsDrawn: int = Field(0)
    foulsPersonal: int = Field(0)
    foulsTechnical: int = Field(0)
    freeThrowsAttempted: int = Field(0)
    freeThrowsMade: int = Field(0)
    freeThrowsPercentage: float = Field(0.0)
    points: int = Field(0)
    pointsFastBreak: int = Field(0)
    pointsInThePaint: int = Field(0)
    pointsSecondChance: int = Field(0)
    reboundsDefensive: int = Field(0)
    reboundsOffensive: int = Field(0)
    reboundsTotal: int = Field(0)
    steals: int = Field(0)
    turnovers: int = Field(0)
    minutes: str = Field("")
    threePointersMade: int = Field(0)
    threePointersAttempted: int = Field(0)
    threePointersPercentage: float = Field(0.0)


class Player(BaseModel):
    """球员游戏数据模型，继承并扩展PlayerProfile"""
    status: str = Field(..., description="球员状态")
    order: int = Field(..., description="球员顺序")
    personId: int = Field(..., description="球员ID")
    jerseyNum: str = Field(..., description="球衣号码")
    position: Optional[str] = Field(None, description="位置")
    starter: str = Field("0", description="是否首发")
    oncourt: str = Field("0", description="是否在场上")
    played: str = Field("0", description="是否参与比赛")
    statistics: PlayerStatistics = Field(..., description="球员统计数据")
    name: str = Field(..., description="球员姓名")
    nameI: str = Field(..., description="球员姓名缩写")
    firstName: str = Field(..., description="球员名")
    familyName: str = Field(..., description="球员姓")
    notPlayingReason: Optional[str] = Field(None, description="不参赛原因")
    notPlayingDescription: Optional[str] = Field(None, description="不参赛描述")
    
    @validator('name', 'firstName', 'familyName', pre=True)
    def register_player(cls, v, values):
        if all(k in values for k in ['personId', 'firstName', 'familyName']):
            PlayerRegistry.get_instance().register(
                values['personId'],
                values['firstName'],
                values['familyName']
            )
        return v

    @property
    def profile(self) -> Optional[PlayerProfile]:
        """获取球员完整信息"""
        return PlayerProfile.find_by_id(self.personId)


class TeamStats(BaseModel):
    """球队比赛统计数据模型"""
    teamId: int = Field(..., description="球队ID")
    teamName: str = Field(..., description="球队名称")
    teamCity: str = Field(..., description="球队城市")
    teamTricode: str = Field(..., description="球队三字母代码")
    score: int = Field(..., description="球队得分")
    inBonus: str = Field(..., description="是否在罚球线内")
    timeoutsRemaining: int = Field(..., description="剩余暂停次数")
    periods: List[PeriodScore] = Field(..., description="各节得分")
    players: List[Player] = Field(..., description="球队球员列表")
    statistics: Dict[str, Any] = Field(default_factory=dict, description="球队统计数据")
    
    @property
    def profile(self) -> Optional[TeamProfile]:
        """获取球队完整信息"""
        return TeamProfile.from_id(self.teamId)
    
    @property
    def logo_path(self) -> Optional[str]:
        """获取球队logo路径"""
        team_profile = self.profile
        return str(team_profile.get_logo_path()) if team_profile else None

    def get_stat(self, key: str, default: Any = 0) -> Any:
        """获取指定的统计数据"""
        return self.statistics.get(key, default)

    @property
    def field_goals(self) -> tuple[int, int, float]:
        """获取投篮命中率数据"""
        made = self.get_stat('fieldGoalsMade', 0)
        attempted = self.get_stat('fieldGoalsAttempted', 0)
        percentage = self.get_stat('fieldGoalsPercentage', 0.0)
        return made, attempted, percentage

    @property
    def three_pointers(self) -> tuple[int, int, float]:
        """获取三分球命中率数据"""
        made = self.get_stat('threePointersMade', 0)
        attempted = self.get_stat('threePointersAttempted', 0)
        percentage = self.get_stat('threePointersPercentage', 0.0)
        return made, attempted, percentage

    @property
    def free_throws(self) -> tuple[int, int, float]:
        """获取罚球命中率数据"""
        made = self.get_stat('freeThrowsMade', 0)
        attempted = self.get_stat('freeThrowsAttempted', 0)
        percentage = self.get_stat('freeThrowsPercentage', 0.0)
        return made, attempted, percentage


class GameData(BaseModel):
    """比赛数据"""
    gameId: str = Field(..., description="比赛ID")
    gameTimeLocal: datetime = Field(..., description="本地时间")
    gameTimeUTC: datetime = Field(..., description="UTC时间")
    gameTimeHome: datetime = Field(..., description="主队时间")
    gameTimeAway: datetime = Field(..., description="客队时间")
    gameEt: datetime = Field(..., description="东部时间")
    duration: int = Field(..., description="比赛时长（分钟）")
    gameCode: str = Field(..., description="比赛代码")
    gameStatusText: str = Field(..., description="比赛状态文本")
    gameStatus: GameStatusEnum = Field(..., description="比赛状态")
    regulationPeriods: int = Field(..., description="常规赛节次")
    period: int = Field(..., description="当前节次")
    gameClock: str = Field(..., description="比赛时钟")
    attendance: int = Field(..., description="观众人数")
    sellout: str = Field(..., description="是否售罄")
    arena: Arena = Field(..., description="场馆信息")
    officials: List[Official] = Field(..., description="裁判列表")
    homeTeam: TeamStats = Field(..., description="主队信息")
    awayTeam: TeamStats = Field(..., description="客队信息")
    statistics: Optional[Dict[str, Any]] = Field(None, description="比赛统计数据")

    def get_player_stats(self, player_id: int, is_home: bool = True) -> Optional[PlayerStatistics]:
        """获取指定球员的统计数据"""
        team = self.homeTeam if is_home else self.awayTeam
        for player in team.players:
            if player.personId == player_id:
                return player.statistics
        return None
    
    def get_team_stats(self, is_home: bool = True) -> Optional[Dict[str, Any]]:
        """获取球队统计数据"""
        team = self.homeTeam if is_home else self.awayTeam
        return team.statistics
    
    def get_player_by_id(self, player_id: int) -> Optional[Player]:
        """通过ID查找球员"""
        for player in self.homeTeam.players + self.awayTeam.players:
            if player.personId == player_id:
                return player
        return None

    def is_player_on_court(self, player_id: int) -> bool:
        """检查球员是否在场上"""
        player = self.get_player_by_id(player_id)
        return bool(player and player.oncourt == "1")

    def get_team_score(self, is_home: bool = True) -> int:
        """获取球队得分"""
        return self.homeTeam.score if is_home else self.awayTeam.score

    def get_score_difference(self) -> int:
        """获取比分差值（主队减客队）"""
        return self.homeTeam.score - self.awayTeam.score

    @model_validator(mode='after')
    def check_game_integrity(self) -> 'GameData':
        if not self.gameId:
            raise ValueError("Missing gameId")

        if not self.homeTeam or not self.homeTeam.teamId or not self.homeTeam.teamName:
            raise ValueError("Missing homeTeam information")
        if not self.awayTeam or not self.awayTeam.teamId or not self.awayTeam.teamName:
            raise ValueError("Missing awayTeam information")

        if self.gameStatus in {GameStatusEnum.IN_PROGRESS, GameStatusEnum.FINISHED}:
            if not isinstance(self.homeTeam.score, int) or \
                    not isinstance(self.awayTeam.score, int):
                raise ValueError("Invalid score data")

        return self


# 3. 事件模型
class CourtPosition(BaseModel):
    """球场位置模型"""
    x: Optional[float] = Field(None, description="X坐标")
    y: Optional[float] = Field(None, description="Y坐标")
    area: Optional[str] = Field(None, description="区域")
    areaDetail: Optional[str] = Field(None, description="详细区域")
    side: Optional[str] = Field(None, description="场地侧边")
    xLegacy: Optional[int] = Field(None, description="旧版X坐标")
    yLegacy: Optional[int] = Field(None, description="旧版Y坐标")


class BaseEvent(BaseModel):
    """基础事件模型"""
    actionNumber: int = Field(..., description="事件编号")
    clock: str = Field(..., description="比赛时钟")
    timeActual: datetime = Field(..., description="事件发生的实际时间")
    period: int = Field(..., description="比赛节次")
    periodType: str = Field(..., description="比赛节类型")
    isTargetScoreLastPeriod: bool = Field(False, description="是否为最后一节目标分数制")
    orderNumber: int = Field(..., description="顺序号")
    
    # 可选字段
    teamId: Optional[int] = Field(None, description="球队ID")
    teamTricode: Optional[str] = Field(None, description="球队三字母代码")
    actionType: Optional[EventCategory] = Field(None, description="事件类型")
    qualifiers: List[ShotQualifier] = Field(default_factory=list, description="事件限定词列表")
    personId: Optional[int] = Field(None, description="球员ID")
    description: Optional[str] = Field(None, description="事件描述")
    playerName: Optional[str] = Field(None, description="球员姓名")
    playerNameI: Optional[str] = Field(None, description="球员姓名缩写")
    possession: Optional[int] = Field(None, description="球权")
    scoreHome: Optional[str] = Field(None, description="主队得分")
    scoreAway: Optional[str] = Field(None, description="客队得分")
    edited: Optional[datetime] = Field(None, description="编辑时间")
    
    # 使用 CourtPosition 模型
    position: Optional[CourtPosition] = None

    @validator('scoreHome', 'scoreAway', pre=True)
    def convert_score_to_int(cls, v):
        """将分数从字符串转换为整数"""
        return int(v) if v is not None else None

    @property
    def score_difference(self) -> Optional[int]:
        """计算比分差值"""
        if self.scoreHome is not None and self.scoreAway is not None:
            return self.scoreHome - self.scoreAway
        return None


class PeriodStartEvent(BaseEvent):
    """比赛节开始事件"""
    subType: Optional[str] = Field(None, description="子类型，例如 'start'")


class StealEvent(BaseEvent):
    """抢断事件"""
    stealPersonId: Optional[int] = Field(None, description="抢断者ID")
    stealPlayerName: Optional[str] = Field(None, description="抢断者姓名")
    playerNameI: Optional[str] = Field(None, description="被抢断者姓名")
    personIdsFilter: List[int] = Field(default_factory=list, description="抢断者和被抢断者ID")


class BlockEvent(BaseEvent):
    """封盖事件"""
    blockPersonId: Optional[int] = Field(None, description="盖帽者ID")
    blockPlayerName: Optional[str] = Field(None, description="盖帽者姓名")
    playerNameI: Optional[str] = Field(None, description="被盖帽者姓名")
    personIdsFilter: List[int] = Field(default_factory=list, description="盖帽者和被盖帽者ID")
    shotActionNumber: Optional[int] = Field(None, description="关联投篮动作编号")


class FoulEvent(BaseEvent):
    """犯规事件"""
    subType: FoulSubType
    foulDrawnPersonId: Optional[int] = Field(None, description="被犯规者ID")
    foulDrawnPlayerName: Optional[str] = Field(None, description="被犯规者姓名")
    personIdsFilter: List[int] = Field(default_factory=list, description="犯规者和被犯规者ID")
    freeThrowsAwarded: Optional[int] = Field(None, description="获得罚球数")


class AssistEvent(BaseEvent):
    """助攻事件"""
    assistPersonId: Optional[int] = Field(None, description="助攻者ID")
    assistPlayerNameInitial: Optional[str] = Field(None, description="助攻者姓名缩写")
    playerNameI: Optional[str] = Field(None, description="得分者姓名")
    personIdsFilter: List[int] = Field(default_factory=list, description="助攻者和得分者ID")
    shotActionNumber: Optional[int] = Field(None, description="关联投篮动作编号")


class JumpBallEvent(BaseEvent):
    """跳球事件"""
    jumpBallWonPersonId: Optional[int] = Field(None, description="跳球获胜者ID")
    jumpBallLostPersonId: Optional[int] = Field(None, description="跳球失败者ID")
    jumpBallRecoveredPersonId: Optional[int] = Field(None, description="获得球权者ID")
    jumpBallWonPlayerName: Optional[str] = Field(None, description="跳球获胜者姓名")
    jumpBallLostPlayerName: Optional[str] = Field(None, description="跳球失败者姓名")
    jumpBallRecoveredName: Optional[str] = Field(None, description="获得球权者姓名")
    personIdsFilter: List[int] = Field(default_factory=list, description="所有相关球员ID")


class ShotEvent(BaseEvent):
    """投篮事件基类"""
    subType: Optional[str] = Field(None, description="投篮类型")
    shotResult: Optional[str] = Field(None, description="投篮结果")
    pointsTotal: Optional[int] = Field(None, description="总得分")
    shotDistance: Optional[float] = Field(None, description="投篮距离")
    shotActionNumber: Optional[int] = Field(None, description="投篮动作编号")
    
    # 使用 CourtPosition 模型记录投篮位置
    position: CourtPosition = Field(..., description="投篮位置")

    @property
    def is_made(self) -> bool:
        """判断是否命中"""
        return self.shotResult != "Missed"


class TwoPointEvent(ShotEvent):
    """2分球事件"""
    subType: TwoPointSubType
    pointsTotal: Literal[2] = 2
    
    @property
    def is_in_paint(self) -> bool:
        """是否在油漆区内"""
        return ShotQualifier.POINTS_IN_PAINT in self.qualifiers


class ThreePointEvent(ShotEvent):
    """3分球事件"""
    subType: ThreePointSubType
    pointsTotal: Literal[3] = 3


class FreeThrowEvent(ShotEvent):
    """罚球事件"""
    pointsTotal: Literal[1] = 1
    foulType: Optional[str] = Field(None, description="犯规类型")
    
    # 罚球不需要位置信息
    position: Optional[CourtPosition] = Field(None)


class ReboundEvent(BaseEvent):
    """篮板事件"""
    subType: ReboundSubType
    reboundTotal: Optional[int] = Field(None, description="篮板总数")
    reboundDefensiveTotal: Optional[int] = Field(None, description="防守篮板总数")
    reboundOffensiveTotal: Optional[int] = Field(None, description="进攻篮板总数")
    shotActionNumber: Optional[int] = Field(None, description="关联投篮动作编号")
    personIdsFilter: List[int] = Field(default_factory=list, description="篮板球员ID")


class TurnoverEvent(BaseEvent):
    """失误事件"""
    subType: TurnoverSubType
    turnoverTotal: Optional[int] = Field(None, description="失误总数")
    stealPlayerName: Optional[str] = Field(None, description="抢断球员姓名")
    stealPersonId: Optional[int] = Field(None, description="抢断球员ID")
    personIdsFilter: List[int] = Field(default_factory=list, description="失误球员ID")


class SubstitutionEvent(BaseEvent):
    """换人事件"""
    subType: Optional[str] = Field(None, description="换人类型")
    incomingPlayer: Optional[str] = Field(None, description="换上球员姓名")
    incomingPlayerId: Optional[int] = Field(None, description="换上球员ID")
    outgoingPlayer: Optional[str] = Field(None, description="换下球员姓名")
    outgoingPlayerId: Optional[int] = Field(None, description="换下球员ID")
    personIdsFilter: List[int] = Field(default_factory=list, description="换人涉及的球员ID")


class TimeoutEvent(BaseEvent):
    """暂停事件"""
    subType: Optional[str] = Field(None, description="暂停类型")
    timeoutsRemaining: Optional[int] = Field(None, description="剩余暂停数")


class ViolationEvent(BaseEvent):
    """违例事件"""
    subType: Optional[str] = Field(None, description="违例类型")
    violationTotal: Optional[int] = Field(None, description="违例总数")
    personIdsFilter: List[int] = Field(default_factory=list, description="违例球员ID")


class PlayByPlay(BaseModel):
    """比赛回放数据"""
    game: Dict[str, Any] = Field(..., description="比赛信息")
    meta: Optional[Dict[str, Any]] = Field(None, description="元数据")

    @property
    def actions(self) -> List[Dict[str, Any]]:
        """获取所有事件"""
        return self.game.get('actions', [])

    def get_event_stats(self) -> Dict[str, int]:
        """获取各类事件的统计数据"""
        stats = {}
        for action in self.actions:
            event_type = action.get('actionType')
            if event_type:
                stats[event_type] = stats.get(event_type, 0) + 1
        return stats


class Game(BaseModel):
    """完整比赛数据模型"""
    meta: Dict[str, Any] = Field(..., description="元数据")
    game: GameData = Field(..., description="比赛数据")
    playByPlay: Optional[PlayByPlay] = Field(None, description="比赛回放数据")

    def get_player_stats(self, player_id: int, is_home: bool = True) -> Optional[PlayerStatistics]:
        """获取球员统计数据的便捷方法"""
        return self.game.get_player_stats(player_id, is_home)
    
    def get_team_stats(self, is_home: bool = True) -> Optional[Dict[str, Any]]:
        """获取球队统计数据的便捷方法"""
        return self.game.get_team_stats(is_home)
    
    def get_scoring_plays(self, player_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取得分事件列表"""
        if not self.playByPlay:
            return []
        
        scoring_plays = []
        for action in self.playByPlay.actions_parsed:
            if (hasattr(action, 'shotActionNumber') and 
                (not player_id or action.personId == player_id)):
                scoring_plays.append({
                    'time': action.clock,
                    'period': action.period,
                    'player': action.playerName,
                    'team': action.teamTricode,
                    'score_diff': action.scoreHome - action.scoreAway if all(x is not None for x in [action.scoreHome, action.scoreAway]) else None,
                    'description': action.description
                })
        
        return scoring_plays

    def get_player_on_court_status(self) -> Dict[int, bool]:
        """获取所有球员的在场状态"""
        status = {}
        for player in self.game.homeTeam.players + self.game.awayTeam.players:
            status[player.personId] = player.oncourt == "1"
        return status