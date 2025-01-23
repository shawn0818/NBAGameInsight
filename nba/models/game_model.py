from datetime import datetime
from enum import IntEnum, Enum
from typing import Optional, List, Dict, Any, Union, Literal
from pydantic import BaseModel, Field, model_validator, ValidationError, conint, confloat, ConfigDict
from nba.models.player_model import PlayerProfile
from nba.models.team_model import TeamProfile


# ===========================
# 1. 基础枚举类
# ===========================

class GameStatusEnum(IntEnum):
    """比赛状态"""
    NOT_STARTED = 1
    IN_PROGRESS = 2
    FINISHED = 3


class ShotResult(str, Enum):
    """投篮结果"""
    MADE = "Made"
    MISSED = "Missed"


class EventCategory(str, Enum):
    """比赛事件类型"""
    PERIOD_START = "period-start"
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
    GAME = "game"


class ShotQualifier(str, Enum):
    """投篮限定词"""
    POINTS_IN_PAINT = "pointsinthepaint"
    ABOVE_THE_BREAK_3 = "abovethebreak3"
    CORNER_3 = "corner3"
    SECOND_CHANCE = "2ndchance"
    FAST_BREAK = "fastbreak"
    FROM_TURNOVER = "fromturnover"
    DRIVING = "driving"
    FADEAWAY = "fadeaway"
    HOOK = "hook"
    PULLUP = "pullup"
    STEPBACK = "stepback"
    TURNAROUND = "turnaround"
    ALLEY_OOP = "alleyoop"
    TIP = "tip"
    CUTTING = "cutting"
    DEFENDED = "defended"
    UNDEFENDED = "undefended"
    CONTESTED = "contested"
    UNCONTESTED = "uncontested"
    AND_ONE = "andone"
    BLOCKED = "blocked"


# ===========================
# 2. 基础数据模型
# ===========================

class Arena(BaseModel):
    """场馆信息"""
    arenaId: conint(ge=0) = Field(default=0, description="场馆ID")
    arenaName: str = Field(default="Unknown Arena", description="场馆名称")
    arenaCity: str = Field(default="Unknown City", description="场馆城市")
    arenaState: str = Field(default="Unknown State", description="场馆州")
    arenaCountry: str = Field(default="Unknown Country", description="场馆国家")
    arenaTimezone: str = Field(default="America/Los_Angeles", description="场馆时区")

    model_config = ConfigDict(from_attributes=True)


class Official(BaseModel):
    """裁判信息"""
    personId: conint(ge=0) = Field(..., description="裁判ID")
    name: str = Field(..., description="裁判姓名")
    nameI: str = Field(..., description="裁判姓名缩写")
    firstName: str = Field(..., description="裁判名")
    familyName: str = Field(..., description="裁判姓")
    jerseyNum: str = Field(..., description="裁判号码")
    assignment: str = Field(..., description="裁判职位")

    model_config = ConfigDict(from_attributes=True)


class CourtPosition(BaseModel):
    """场上位置模型"""
    x: Optional[float] = Field(None, description="X坐标 (0-100)")
    y: Optional[float] = Field(None, description="Y坐标 (0-100)")
    area: Optional[str] = Field(None, description="场区")
    areaDetail: Optional[str] = Field(None, description="详细区域")
    side: Optional[str] = Field(None, description="场地侧边")
    xLegacy: Optional[int] = Field(None, description="旧版X坐标")
    yLegacy: Optional[int] = Field(None, description="旧版Y坐标")

    model_config = ConfigDict(from_attributes=True)


# ===========================
# 3. 统计数据模型
# ===========================

class PlayerStatistics(BaseModel):
    """球员统计数据"""
    minutes: str = Field("PT00M00.00S", description="比赛时间")
    seconds_played: float = Field(0.0, description="比赛时间（秒）")

    # 基础统计
    points: conint(ge=0) = Field(0, description="得分")
    assists: conint(ge=0) = Field(0, description="助攻")
    blocks: conint(ge=0) = Field(0, description="盖帽")
    blocksReceived: conint(ge=0) = Field(0, description="被盖帽")
    steals: conint(ge=0) = Field(0, description="抢断")
    turnovers: conint(ge=0) = Field(0, description="失误")

    # 投篮数据
    fieldGoalsAttempted: conint(ge=0) = Field(0, description="投篮出手数")
    fieldGoalsMade: conint(ge=0) = Field(0, description="投篮命中数")
    fieldGoalsPercentage: Optional[confloat(ge=0.0, le=1.0)] = Field(None, description="投篮命中率")
    threePointersAttempted: conint(ge=0) = Field(0, description="三分出手数")
    threePointersMade: conint(ge=0) = Field(0, description="三分命中数")
    threePointersPercentage: Optional[confloat(ge=0.0, le=1.0)] = Field(None, description="三分命中率")

    # 罚球数据
    freeThrowsAttempted: conint(ge=0) = Field(0, description="罚球出手数")
    freeThrowsMade: conint(ge=0) = Field(0, description="罚球命中数")
    freeThrowsPercentage: Optional[confloat(ge=0.0, le=1.0)] = Field(None, description="罚球命中率")

    # 篮板数据
    reboundsOffensive: conint(ge=0) = Field(0, description="进攻篮板")
    reboundsDefensive: conint(ge=0) = Field(0, description="防守篮板")
    reboundsTotal: conint(ge=0) = Field(0, description="总篮板")

    # 犯规数据
    foulsPersonal: conint(ge=0) = Field(0, description="个人犯规")
    foulsTechnical: conint(ge=0) = Field(0, description="技术犯规")
    foulsOffensive: conint(ge=0) = Field(0, description="进攻犯规")
    foulsDrawn: conint(ge=0) = Field(0, description="被犯规次数")

    # 其他数据
    pointsFastBreak: conint(ge=0) = Field(0, description="快攻得分")
    pointsInThePaint: conint(ge=0) = Field(0, description="油漆区得分")
    pointsSecondChance: conint(ge=0) = Field(0, description="二次进攻得分")

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def calculate_seconds(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """将时间字符串转换为秒数"""
        minutes_str = data.get('minutes', 'PT00M00.00S')
        try:
            minutes = float(minutes_str[2:-1].split('M')[0])
            seconds = float(minutes_str.split('M')[1][:-1])
            data['seconds_played'] = minutes * 60 + seconds
        except Exception:
            data['seconds_played'] = 0.0
        return data

    @model_validator(mode='after')
    def calculate_percentages(self) -> 'PlayerStatistics':
        """计算各项命中率"""
        # 投篮命中率
        fg_attempted = self.fieldGoalsAttempted
        self.fieldGoalsPercentage = (
            self.fieldGoalsMade / fg_attempted
            if fg_attempted > 0 else None
        )

        # 三分命中率
        three_attempted = self.threePointersAttempted
        self.threePointersPercentage = (
            self.threePointersMade / three_attempted
            if three_attempted > 0 else None
        )

        # 罚球命中率
        ft_attempted = self.freeThrowsAttempted
        self.freeThrowsPercentage = (
            self.freeThrowsMade / ft_attempted
            if ft_attempted > 0 else None
        )

        return self

    @model_validator(mode='after')
    def validate_statistics(self) -> 'PlayerStatistics':
        """验证统计数据的一致性"""
        # 验证投篮数据
        if self.fieldGoalsMade > self.fieldGoalsAttempted:
            raise ValueError("FieldGoalsMade cannot be greater than FieldGoalsAttempted")
        if self.threePointersMade > self.threePointersAttempted:
            raise ValueError("ThreePointersMade cannot be greater than ThreePointersAttempted")
        if self.freeThrowsMade > self.freeThrowsAttempted:
            raise ValueError("FreeThrowsMade cannot be greater than FreeThrowsAttempted")

        # 验证篮板数据
        total_rebounds = self.reboundsOffensive + self.reboundsDefensive
        if total_rebounds != self.reboundsTotal:
            raise ValueError("Total rebounds must equal offensive + defensive rebounds")

        # 验证得分计算
        calculated_points = (
                (self.fieldGoalsMade - self.threePointersMade) * 2 +
                self.threePointersMade * 3 +
                self.freeThrowsMade
        )
        if calculated_points != self.points:
            raise ValueError(f"Points calculation mismatch: {calculated_points} vs {self.points}")

        return self


class Player(BaseModel):
    """球员游戏数据模型"""
    status: str = Field(..., description="球员状态")
    order: conint(ge=0) = Field(..., description="球员顺序")
    personId: conint(ge=0) = Field(..., description="球员ID")
    jerseyNum: str = Field(..., description="球衣号码")
    position: Optional[str] = Field(None, description="位置")
    starter: str = Field("0", description="是否首发")
    oncourt: str = Field("0", description="是否在场上")
    played: str = Field("0", description="是否参与比赛")
    statistics: PlayerStatistics = Field(default_factory=PlayerStatistics, description="球员统计数据")
    name: str = Field(..., description="球员姓名")
    nameI: str = Field(..., description="球员姓名缩写")
    firstName: str = Field(..., description="球员名")
    familyName: str = Field(..., description="球员姓")
    notPlayingReason: Optional[str] = Field(None, description="不参赛原因")
    notPlayingDescription: Optional[str] = Field(None, description="不参赛描述")

    model_config = ConfigDict(from_attributes=True)

    @property
    def profile(self) -> Optional[PlayerProfile]:
        """获取球员完整信息"""
        return PlayerProfile.find_by_id(self.personId)

    @property
    def is_active(self) -> bool:
        """判断球员是否处于活跃状态"""
        return self.status == "ACTIVE" and self.notPlayingReason is None

    @property
    def is_on_court(self) -> bool:
        """判断球员是否在场上"""
        return self.oncourt == "1"

    @property
    def has_played(self) -> bool:
        """判断球员是否参与过比赛"""
        return self.played == "1"


class PeriodScore(BaseModel):
    """每节比分"""
    period: conint(ge=1) = Field(..., description="节次")
    periodType: str = Field(..., description="节次类型")
    score: conint(ge=0) = Field(..., description="得分")

    model_config = ConfigDict(from_attributes=True)


class TeamStats(BaseModel):
    """球队比赛统计数据"""
    teamId: conint(ge=0) = Field(..., description="球队ID")
    teamName: str = Field(..., description="球队名称")
    teamCity: str = Field(..., description="球队城市")
    teamTricode: str = Field(..., description="球队三字母代码")
    score: conint(ge=0) = Field(..., description="球队得分")
    inBonus: str = Field(..., description="是否在罚球线内")
    timeoutsRemaining: conint(ge=0) = Field(..., description="剩余暂停次数")
    periods: List[PeriodScore] = Field(default_factory=list, description="各节得分")
    players: List[Player] = Field(default_factory=list, description="球队球员列表")
    statistics: Dict[str, Any] = Field(default_factory=dict, description="球队统计数据")

    model_config = ConfigDict(from_attributes=True)

    @property
    def profile(self) -> Optional[TeamProfile]:
        """获取球队完整信息"""
        return TeamProfile.get_team_by_id(self.teamId)

    @property
    def fieldGoalsMade(self) -> int:
        return self.statistics.get('fieldGoalsMade', 0)

    @property
    def fieldGoalsAttempted(self) -> int:
        return self.statistics.get('fieldGoalsAttempted', 0)

    @property
    def fieldGoalsPercentage(self) -> float:
        return self.statistics.get('fieldGoalsPercentage', 0.0)

        # ... 其他属性类似


# ===========================
# 4. 事件模型
# ===========================

class BaseEvent(BaseModel):
    """基础事件类"""
    actionNumber: int = Field(..., description="事件序号")
    clock: str = Field(..., description="比赛时钟")
    timeActual: str = Field(..., description="实际时间")
    period: int = Field(..., description="比赛节数")
    teamId: Optional[int] = Field(None, description="球队ID")
    teamTricode: Optional[str] = Field(None, description="球队三字码")
    actionType: str = Field(..., description="事件类型")
    subType: Optional[str] = Field(None, description="子类型")
    description: str = Field(..., description="事件描述")
    personId: Optional[int] = Field(None, description="球员ID")
    playerName: Optional[str] = Field(None, description="球员姓名")
    playerNameI: Optional[str] = Field(None, description="球员简称")
    x: Optional[float] = Field(None, description="X坐标")
    y: Optional[float] = Field(None, description="Y坐标")
    xLegacy: Optional[int] = Field(None, description="传统X坐标")
    yLegacy: Optional[int] = Field(None, description="传统Y坐标")
    scoreHome: Optional[str] = Field(None, description="主队得分")
    scoreAway: Optional[str] = Field(None, description="客队得分")

    model_config = ConfigDict(from_attributes=True, extra='allow')


class GameEvent(BaseEvent):
    """比赛事件(开始/结束)"""
    actionType: Literal["game"] = Field(..., description="事件类型")
    subType: Literal["start", "end"] = Field(..., description="子类型")
    description: str = Field(..., description="事件描述")


class PeriodEvent(BaseEvent):
    """比赛节开始/结束事件"""
    actionType: Literal["period"] = Field(..., description="事件类型")
    subType: Literal["start", "end"] = Field(..., description="子类型")


class JumpBallEvent(BaseEvent):
    """跳球事件"""
    actionType: Literal["jumpball"] = Field(..., description="事件类型")
    jumpBallWonPersonId: int = Field(..., description="跳球获胜者ID")
    jumpBallWonPlayerName: str = Field(..., description="跳球获胜者姓名")
    jumpBallLostPersonId: int = Field(..., description="跳球失败者ID")
    jumpBallLostPlayerName: str = Field(..., description="跳球失败者姓名")
    jumpBallRecoveredPersonId: Optional[int] = Field(None, description="获得球权者ID")
    jumpBallRecoveredName: Optional[str] = Field(None, description="获得球权者姓名")


class ShotEvent(BaseEvent):
    """投篮事件"""
    actionType: Literal["2pt", "3pt"] = Field(..., description="事件类型")
    subType: str = Field(..., description="投篮类型")
    area: str = Field(..., description="投篮区域")
    areaDetail: Optional[str] = Field(None, description="详细区域")
    side: Optional[str] = Field(None, description="场地侧边")
    shotDistance: float = Field(..., description="投篮距离")
    shotResult: ShotResult = Field(..., description="投篮结果")
    isFieldGoal: Optional[int] = Field(1, description="是否为投篮")
    qualifiers: List[str] = Field(default_factory=list, description="限定词")
    assistPersonId: Optional[int] = Field(None, description="助攻者ID")
    assistPlayerNameInitial: Optional[str] = Field(None, description="助攻者简称")
    blockPersonId: Optional[int] = Field(None, description="盖帽者ID")
    blockPlayerName: Optional[str] = Field(None, description="盖帽者姓名")


class TwoPointEvent(ShotEvent):
    """两分球事件"""
    actionType: Literal["2pt"] = Field(..., description="事件类型")


class ThreePointEvent(ShotEvent):
    """三分球事件"""
    actionType: Literal["3pt"] = Field(..., description="事件类型")


class AssistEvent(BaseEvent):
    """助攻事件"""
    actionType: Literal["assist"] = Field(..., description="事件类型")
    assistTotal: int = Field(..., description="助攻总数")
    description: str = Field(..., description="事件描述")
    playerName: str = Field(..., description="助攻者姓名")
    playerNameI: str = Field(..., description="助攻者简称")
    scoringPlayerName: str = Field(..., description="得分者姓名")
    scoringPlayerNameI: str = Field(..., description="得分者简称")
    scoringPersonId: int = Field(..., description="得分者ID")


class FreeThrowEvent(BaseEvent):
    """罚球事件"""
    actionType: Literal["freethrow"] = Field(..., description="事件类型")
    subType: str = Field(..., description="罚球类型")
    isFieldGoal: Optional[int] = Field(0, description="是否为投篮")
    shotResult: ShotResult = Field(..., description="罚球结果")
    description: str = Field(..., description="事件描述")
    playerName: str = Field(..., description="罚球者姓名")
    playerNameI: str = Field(..., description="罚球者简称")
    pointsTotal: Optional[int] = Field(None, description="得分")


class ReboundEvent(BaseEvent):
    """篮板事件"""
    actionType: Literal["rebound"] = Field(..., description="事件类型")
    subType: Literal["offensive", "defensive"] = Field(..., description="篮板类型")
    reboundTotal: int = Field(..., description="篮板总数")
    reboundDefensiveTotal: int = Field(..., description="防守篮板总数")
    reboundOffensiveTotal: int = Field(..., description="进攻篮板总数")
    description: str = Field(..., description="事件描述")
    playerName: str = Field(..., description="篮板球员姓名")
    playerNameI: str = Field(..., description="篮板球员简称")
    shotActionNumber: Optional[int] = Field(None, description="相关投篮事件编号")


class BlockEvent(BaseEvent):
    """盖帽事件"""
    actionType: Literal["block"] = Field(..., description="事件类型")
    playerName: str = Field(..., description="盖帽者姓名")
    playerNameI: str = Field(..., description="盖帽者简称")


class StealEvent(BaseEvent):
    """抢断事件"""
    actionType: Literal["steal"] = Field(..., description="事件类型")
    subType: str = Field("", description="子类型")
    description: str = Field(..., description="事件描述")
    playerName: str = Field(..., description="抢断者姓名")
    playerNameI: str = Field(..., description="抢断者简称")


class TurnoverEvent(BaseEvent):
    """失误事件"""
    actionType: Literal["turnover"] = Field(..., description="事件类型")
    subType: str = Field(..., description="失误类型")
    descriptor: Optional[str] = Field(None, description="描述词")
    turnoverTotal: int = Field(..., description="失误总数")
    description: str = Field(..., description="事件描述")
    playerName: str = Field(..., description="失误者姓名")
    playerNameI: str = Field(..., description="失误者简称")
    stealPersonId: Optional[int] = Field(None, description="抢断者ID")
    stealPlayerName: Optional[str] = Field(None, description="抢断者姓名")


class FoulEvent(BaseEvent):
    """犯规事件"""
    actionType: Literal["foul"] = Field(..., description="事件类型")
    subType: str = Field(..., description="犯规类型")
    descriptor: Optional[str] = Field(None, description="描述词")
    foulDrawnPlayerName: Optional[str] = Field(None, description="被犯规球员姓名")
    foulDrawnPersonId: Optional[int] = Field(None, description="被犯规球员ID")
    officialId: Optional[int] = Field(None, description="裁判ID")
    description: str = Field(..., description="事件描述")
    playerName: str = Field(..., description="犯规者姓名")
    playerNameI: str = Field(..., description="犯规者简称")


class ViolationEvent(BaseEvent):
    """违例事件"""
    actionType: Literal["violation"] = Field(..., description="事件类型")
    subType: str = Field(..., description="违例类型")
    description: str = Field(..., description="事件描述")
    officialId: Optional[int] = Field(None, description="裁判ID")
    playerName: str = Field(..., description="违例者姓名")
    playerNameI: str = Field(..., description="违例者简称")


class TimeoutEvent(BaseEvent):
    """暂停事件"""
    actionType: Literal["timeout"] = Field(..., description="事件类型")
    subType: str = Field(..., description="暂停类型")
    description: str = Field(..., description="事件描述")


class SubstitutionEvent(BaseEvent):
    """换人事件"""
    actionType: Literal["substitution"] = Field(..., description="事件类型")
    subType: Optional[str] = Field(None, description="换人类型")
    incomingPlayerName: str = Field(..., description="替补上场球员姓名")
    incomingPlayerNameI: str = Field(..., description="替补上场球员简称")
    incomingPersonId: int = Field(..., description="替补上场球员ID")
    outgoingPlayerName: str = Field(..., description="替补下场球员姓名")
    outgoingPlayerNameI: str = Field(..., description="替补下场球员简称")
    outgoingPersonId: int = Field(..., description="替补下场球员ID")
    description: str = Field(..., description="事件描述")


# ===========================
# 5. 核心游戏类
# ===========================

class PlayByPlay(BaseModel):
    """比赛回放数据"""
    game: Dict[str, Any] = Field(..., description="比赛信息")
    meta: Optional[Dict[str, Any]] = Field(None, description="元数据")
    actions: List[BaseEvent] = Field(default_factory=list, description="所有事件列表")

    model_config = ConfigDict(from_attributes=True)


class GameData(BaseModel):
    """比赛详细数据模型"""
    gameId: str = Field(default="", description="比赛ID")
    gameTimeLocal: datetime = Field(default_factory=datetime.now, description="本地时间")
    gameTimeUTC: datetime = Field(default_factory=datetime.utcnow, description="UTC时间")
    gameTimeHome: datetime = Field(default_factory=datetime.now, description="主队时间")
    gameTimeAway: datetime = Field(default_factory=datetime.now, description="客队时间")
    gameEt: datetime = Field(default_factory=datetime.now, description="东部时间")
    duration: conint(ge=0) = Field(default=0, description="比赛时长（分钟）")
    gameCode: str = Field(default="", description="比赛代码")
    gameStatus: GameStatusEnum = Field(default=GameStatusEnum.NOT_STARTED, description="比赛状态")
    gameStatusText: str = Field(default="Not Started", description="比赛状态文本")
    period: conint(ge=1) = Field(default=1, description="当前节次")
    regulationPeriods: conint(ge=1) = Field(default=4, description="常规赛节次")
    gameClock: str = Field(default="PT12M00.00S", description="比赛时钟")
    attendance: conint(ge=0) = Field(default=0, description="观众人数")
    sellout: str = Field(default="0", description="是否售罄")
    arena: Arena = Field(default_factory=Arena, description="场馆信息")
    officials: List[Official] = Field(default_factory=list, description="裁判列表")
    homeTeam: TeamStats = Field(..., description="主队数据")
    awayTeam: TeamStats = Field(..., description="客队数据")
    statistics: Optional[Dict[str, Any]] = Field(None, description="比赛统计数据")

    model_config = ConfigDict(from_attributes=True)


class Game(BaseModel):
    """完整比赛数据模型"""
    meta: Dict[str, Any] = Field(..., description="元数据")
    game: GameData = Field(..., description="比赛数据")
    playByPlay: Optional[PlayByPlay] = Field(None, description="比赛回放数据")

    def get_shot_data(self, player_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取投篮数据

        Args:
            player_id: 球员ID，如果提供则只返回该球员的投篮数据

        Returns:
            List[Dict[str, Any]]: 投篮数据列表，包含是否被助攻的信息
        """
        shot_data = []
        if self.playByPlay and self.playByPlay.actions:
            for action in self.playByPlay.actions:
                if action.actionType in ["2pt", "3pt"]:
                    # 如果指定了球员ID，则只返回该球员的投篮
                    if player_id is not None and action.personId != player_id:
                        continue

                    shot_data.append({
                        'xLegacy': action.xLegacy if hasattr(action, 'xLegacy') else None,
                        'yLegacy': action.yLegacy if hasattr(action, 'yLegacy') else None,
                        'shotResult': action.shotResult if hasattr(action, 'shotResult') else None,
                        'description': action.description,
                        'player_id': action.personId,
                        'team_id': action.teamId,
                        'period': action.period,
                        'actionType': action.actionType,
                        'time': action.clock,
                        # 添加助攻相关信息
                        'assisted': True if hasattr(action,
                                                    'assistPersonId') and action.assistPersonId is not None else False,
                        'assist_player_id': getattr(action, 'assistPersonId', None),
                        'assist_player_name': getattr(action, 'assistPlayerNameInitial', None)
                    })
        return shot_data

    def get_assisted_shot_data(self, passer_id: int) -> List[Dict[str, Any]]:
        """获取特定球员的助攻导致的队友得分位置数据

        Args:
            passer_id: 传球者(助攻者)的ID

        Returns:
            List[Dict[str, Any]]: 经过该球员助攻的所有队友投篮数据
        """
        assisted_shots = []
        if self.playByPlay and self.playByPlay.actions:
            for action in self.playByPlay.actions:
                # 只关注投篮事件
                if action.actionType not in ["2pt", "3pt"]:
                    continue

                # 检查是否是该球员的助攻
                if (hasattr(action, "assistPersonId") and
                        action.assistPersonId == passer_id and
                        action.shotResult == "Made"):  # 只记录命中的球

                    assisted_shots.append({
                        'x': action.xLegacy if hasattr(action, 'xLegacy') else None,
                        'y': action.yLegacy if hasattr(action, 'yLegacy') else None,
                        'shot_type': action.actionType,
                        'shooter_id': action.personId,  # 投篮者ID
                        'shooter_name': action.playerName,  # 投篮者姓名
                        'team_id': action.teamId,
                        'period': action.period,
                        'time': action.clock,
                        'description': action.description,
                        'area': getattr(action, 'area', None),  # 投篮区域
                        'distance': getattr(action, 'shotDistance', None)  # 投篮距离
                    })

        return assisted_shots

    model_config = ConfigDict(from_attributes=True)