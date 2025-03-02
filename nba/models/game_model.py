from datetime import datetime
from enum import IntEnum, Enum
from typing import Optional, List, Dict, Any, Literal, Set
from pydantic import BaseModel, Field, model_validator, conint, confloat, ConfigDict

from utils.time_handler import  TimeHandler
from utils.logger_handler import AppLogger
logger = AppLogger.get_logger(__name__, app_name='nba')


# ===========================
# 1. 基础枚举类
# ===========================

class GameStatusEnum(IntEnum):
    """比赛状态"""
    NOT_STARTED = 1
    IN_PROGRESS = 2
    FINISHED = 3

class PlayerStatus(str, Enum):
    """球员状态"""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"

class NotPlayingReason(str, Enum):
    """球员缺阵原因"""
    INJURY = "INACTIVE_INJURY"
    PERSONAL = "INACTIVE_PERSONAL"
    GLEAGUE = "INACTIVE_GLEAGUE_TWOWAY"
    CONDITIONING = "DND_RETURN_TO_COMPETITION_RECONDITIONING"
    DND_INJURY = "DND_INJURY"  # 添加 DND_INJURY
    DNP_INJURY = "DNP_INJURY"  # 添加 DNP_INJURY
    GLEAGUE_ASSIGNMENT = "INACTIVE_GLEAGUE_ON_ASSIGNMENT"
    COACH = "INACTIVE_COACH"  # 添加这一行


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
    EJECTION = "ejection"
    GAME = "gamedata"


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
# 2. 基础设施模型
# ===========================

class Arena(BaseModel):
    """场馆信息"""
    arena_id: conint(ge=0) = Field(default=0, description="场馆ID", alias="arenaId")
    arena_name: str = Field(default="Unknown Arena", description="场馆名称", alias="arenaName")
    arena_city: str = Field(default="Unknown City", description="场馆城市", alias="arenaCity")
    arena_state: str = Field(default="Unknown State", description="场馆州", alias="arenaState")
    arena_country: str = Field(default="Unknown Country", description="场馆国家", alias="arenaCountry")
    arena_timezone: str = Field(default="America/Los_Angeles", description="场馆时区", alias="arenaTimezone")

    model_config = ConfigDict(from_attributes=True)


class Official(BaseModel):
    """裁判信息"""
    person_id: conint(ge=0) = Field(..., description="裁判ID", alias="personId")
    name: str = Field(..., description="裁判姓名", alias="name")
    name_i: str = Field(..., description="裁判姓名缩写", alias="nameI")
    first_name: str = Field(..., description="裁判名", alias="firstName")
    family_name: str = Field(..., description="裁判姓", alias="familyName")
    jersey_num: str = Field(..., description="裁判号码", alias="jerseyNum")
    assignment: str = Field(..., description="裁判职位", alias="assignment")

    model_config = ConfigDict(from_attributes=True)


class CourtPosition(BaseModel):
    """场上位置模型"""
    x: Optional[float] = Field(None, description="X坐标 (0-100)", alias="x")
    y: Optional[float] = Field(None, description="Y坐标 (0-100)", alias="y")
    area: Optional[str] = Field(None, description="场区", alias="area")
    area_detail: Optional[str] = Field(None, description="详细区域", alias="areaDetail")
    side: Optional[str] = Field(None, description="场地侧边", alias="side")
    x_legacy: Optional[int] = Field(None, description="投篮图坐标", alias="xLegacy")
    y_legacy: Optional[int] = Field(None, description="投篮图坐标", alias="yLegacy")

    model_config = ConfigDict(from_attributes=True)


# ===========================
# 3. 比赛统计数据模型
# ===========================

class PeriodScore(BaseModel):
    """每节比分"""
    period: conint(ge=1) = Field(..., description="节次", alias="period")
    period_type: str = Field(..., description="节次类型", alias="periodType")
    score: conint(ge=0) = Field(..., description="得分", alias="score")

    model_config = ConfigDict(from_attributes=True)

class PlayerStatistics(BaseModel):
    """球员统计数据"""

    # 时间数据
    minutes: str = Field("PT00M00.00S", description="比赛时间(ISO格式字符串)", alias="minutes")
    minutes_calculated: float = Field(0.0, description="计算后的比赛时间(分钟)")

    # 得分数据
    points: conint(ge=0) = Field(0, description="得分", alias="points")
    points_fast_break: conint(ge=0) = Field(0, description="快攻得分", alias="pointsFastBreak")
    points_in_the_paint: conint(ge=0) = Field(0, description="禁区得分", alias="pointsInThePaint")
    points_second_chance: conint(ge=0) = Field(0, description="二次进攻得分", alias="pointsSecondChance")

    # 投篮数据
    field_goals_attempted: conint(ge=0) = Field(0, description="投篮出手数", alias="fieldGoalsAttempted")
    field_goals_made: conint(ge=0) = Field(0, description="投篮命中数", alias="fieldGoalsMade")
    field_goals_percentage: Optional[confloat(ge=0.0, le=1.0)] = Field(None, description="投篮命中率", alias="fieldGoalsPercentage")

    # 三分数据
    three_pointers_attempted: conint(ge=0) = Field(0, description="三分出手数", alias="threePointersAttempted")
    three_pointers_made: conint(ge=0) = Field(0, description="三分命中数", alias="threePointersMade")
    three_pointers_percentage: Optional[confloat(ge=0.0, le=1.0)] = Field(None, description="三分命中率", alias="threePointersPercentage")

    # 两分数据
    two_pointers_attempted: conint(ge=0) = Field(0, description="两分出手数", alias="twoPointersAttempted")
    two_pointers_made: conint(ge=0) = Field(0, description="两分命中数", alias="twoPointersMade")
    two_pointers_percentage: Optional[confloat(ge=0.0, le=1.0)] = Field(None, description="两分命中率", alias="twoPointersPercentage")

    # 罚球数据
    free_throws_attempted: conint(ge=0) = Field(0, description="罚球出手数", alias="freeThrowsAttempted")
    free_throws_made: conint(ge=0) = Field(0, description="罚球命中数", alias="freeThrowsMade")
    free_throws_percentage: Optional[confloat(ge=0.0, le=1.0)] = Field(None, description="罚球命中率", alias="freeThrowsPercentage")

    # 篮板数据
    rebounds_offensive: conint(ge=0) = Field(0, description="进攻篮板", alias="reboundsOffensive")
    rebounds_defensive: conint(ge=0) = Field(0, description="防守篮板", alias="reboundsDefensive")
    rebounds_total: conint(ge=0) = Field(0, description="总篮板", alias="reboundsTotal")

    # 助攻/抢断/盖帽/失误
    assists: conint(ge=0) = Field(0, description="助攻", alias="assists")
    steals: conint(ge=0) = Field(0, description="抢断", alias="steals")
    blocks: conint(ge=0) = Field(0, description="盖帽", alias="blocks")
    blocks_received: conint(ge=0) = Field(0, description="被盖帽", alias="blocksReceived")
    turnovers: conint(ge=0) = Field(0, description="失误", alias="turnovers")

    # 犯规数据
    fouls_personal: conint(ge=0) = Field(0, description="个人犯规", alias="foulsPersonal")
    fouls_technical: conint(ge=0) = Field(0, description="技术犯规", alias="foulsTechnical")
    fouls_offensive: conint(ge=0) = Field(0, description="进攻犯规", alias="foulsOffensive")
    fouls_drawn: conint(ge=0) = Field(0, description="造成犯规", alias="foulsDrawn")

    # 正负值数据
    plus_minus_points: float = Field(0.0, description="正负值", alias="plusMinusPoints")
    plus: float = Field(0.0, description="正值", alias="plus")
    minus: float = Field(0.0, description="负值", alias="minus")

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def calculate_seconds(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        将ISO格式时间字符串转换为秒数和分钟数

        Args:
            data: 包含时间信息的数据字典

        Returns:
            Dict: 添加了seconds_played和计算后分钟数的数据字典
        """
        minutes_str = data.get('minutes', 'PT00M00.00S')
        try:
            # 计算秒数
            seconds = TimeHandler.parse_duration(minutes_str)
            data['seconds_played'] = seconds
            # 计算分钟数（保留2位小数）
            data['minutes_calculated'] = round(seconds / 60.0, 2)
        except ValueError as e:
            logger.warning(f"解析时间字符串失败: {minutes_str}, 设置 minutes_calculated 为 0.0, 错误: {e}")
            data['seconds_played'] = 0
            data['minutes_calculated'] = 0.0
        return data



class PlayerInGame(BaseModel):
    """球员比赛数据模型"""
    status: PlayerStatus = Field(..., description="球员状态")
    order: conint(ge=0) = Field(..., description="球员顺序")
    person_id: conint(ge=0) = Field(..., description="球员ID", alias="personId")
    jersey_num: str = Field(..., description="球衣号码", alias="jerseyNum")
    position: Optional[str] = Field(None, description="位置")
    starter: str = Field("0", description="是否首发")
    on_court: str = Field("0", description="是否在场上", alias="oncourt")
    played: str = Field("0", description="是否参与比赛")
    statistics: PlayerStatistics = Field(default_factory=PlayerStatistics, description="球员统计数据")
    name: str = Field(..., description="球员姓名")
    name_i: str = Field(..., description="球员姓名缩写", alias="nameI")
    first_name: str = Field(..., description="球员名", alias="firstName")
    family_name: str = Field(..., description="球员姓", alias="familyName")
    not_playing_reason: Optional[NotPlayingReason] = Field(None,description="不参赛原因",alias="notPlayingReason")
    not_playing_description: Optional[str] = Field(None, description="不参赛具体描述", alias="notPlayingDescription")

    model_config = ConfigDict(from_attributes=True)


class TeamStatistics(BaseModel):
    """球队统计数据模型"""

    # 时间数据
    minutes: str = Field("PT00M00.00S", description="比赛时间(ISO格式字符串)", alias="minutes")
    minutes_calculated: float = Field(0.0, description="计算后的比赛时间(分钟)")
    time_leading: str = Field("PT00M00.00S", description="领先时间(ISO格式字符串)", alias="timeLeading")
    time_leading_calculated: float = Field(0.0, description="计算后的领先时间(分钟)")

    # 助攻和得分效率
    assists: conint(ge=0) = Field(0, description="助攻数", alias="assists")
    assists_turnover_ratio: float = Field(0.0, description="助攻失误比", alias="assistsTurnoverRatio")
    bench_points: conint(ge=0) = Field(0, description="替补得分", alias="benchPoints")

    # 领先数据
    biggest_lead: conint(ge=0) = Field(0, description="最大领先", alias="biggestLead")
    biggest_lead_score: str = Field("", description="最大领先时的比分", alias="biggestLeadScore")
    biggest_scoring_run: conint(ge=0) = Field(0, description="最大得分高潮", alias="biggestScoringRun")
    biggest_scoring_run_score: str = Field("", description="最大得分高潮时的比分", alias="biggestScoringRunScore")
    lead_changes: conint(ge=0) = Field(0, description="领先变换次数", alias="leadChanges")

    # 盖帽数据
    blocks: conint(ge=0) = Field(0, description="盖帽数", alias="blocks")
    blocks_received: conint(ge=0) = Field(0, description="被盖帽数", alias="blocksReceived")

    # 快攻数据
    fast_break_points_attempted: conint(ge=0) = Field(0, description="快攻出手数", alias="fastBreakPointsAttempted")
    fast_break_points_made: conint(ge=0) = Field(0, description="快攻命中数", alias="fastBreakPointsMade")
    fast_break_points_percentage: float = Field(0.0, description="快攻命中率", alias="fastBreakPointsPercentage")

    # 投篮数据
    field_goals_attempted: conint(ge=0) = Field(0, description="投篮出手数", alias="fieldGoalsAttempted")
    field_goals_made: conint(ge=0) = Field(0, description="投篮命中数", alias="fieldGoalsMade")
    field_goals_percentage: Optional[confloat(ge=0.0, le=1.0)] = Field(None, description="投篮命中率", alias="fieldGoalsPercentage")
    field_goals_effective_adjusted: Optional[confloat(ge=0.0, le=1.0)] = Field(None, description="有效投篮调整率", alias="fieldGoalsEffectiveAdjusted")

    # 犯规数据
    fouls_offensive: conint(ge=0) = Field(0, description="进攻犯规", alias="foulsOffensive")
    fouls_drawn: conint(ge=0) = Field(0, description="造成犯规", alias="foulsDrawn")
    fouls_personal: conint(ge=0) = Field(0, description="个人犯规", alias="foulsPersonal")
    fouls_team: conint(ge=0) = Field(0, description="团队犯规", alias="foulsTeam")
    fouls_technical: conint(ge=0) = Field(0, description="技术犯规", alias="foulsTechnical")
    fouls_team_technical: conint(ge=0) = Field(0, description="团队技术犯规", alias="foulsTeamTechnical")

    # 罚球数据
    free_throws_attempted: conint(ge=0) = Field(0, description="罚球出手数", alias="freeThrowsAttempted")
    free_throws_made: conint(ge=0) = Field(0, description="罚球命中数", alias="freeThrowsMade")
    free_throws_percentage: Optional[confloat(ge=0.0, le=1.0)] = Field(None, description="罚球命中率", alias="freeThrowsPercentage")

    # 得分数据
    points: conint(ge=0) = Field(0, description="总得分", alias="points")
    points_against: conint(ge=0) = Field(0, description="失分", alias="pointsAgainst")
    points_fast_break: conint(ge=0) = Field(0, description="快攻得分", alias="pointsFastBreak")
    points_from_turnovers: conint(ge=0) = Field(0, description="失误转换得分", alias="pointsFromTurnovers")
    points_in_the_paint: conint(ge=0) = Field(0, description="禁区得分", alias="pointsInThePaint")
    points_in_the_paint_attempted: conint(ge=0) = Field(0, description="禁区出手数", alias="pointsInThePaintAttempted")
    points_in_the_paint_made: conint(ge=0) = Field(0, description="禁区命中数", alias="pointsInThePaintMade")
    points_in_the_paint_percentage: float = Field(0.0, description="禁区命中率", alias="pointsInThePaintPercentage")
    points_second_chance: conint(ge=0) = Field(0, description="二次进攻得分", alias="pointsSecondChance")

    # 篮板数据
    rebounds_defensive: conint(ge=0) = Field(0, description="防守篮板", alias="reboundsDefensive")
    rebounds_offensive: conint(ge=0) = Field(0, description="进攻篮板", alias="reboundsOffensive")
    rebounds_personal: conint(ge=0) = Field(0, description="个人篮板", alias="reboundsPersonal")
    rebounds_team: conint(ge=0) = Field(0, description="团队篮板", alias="reboundsTeam")
    rebounds_team_defensive: conint(ge=0) = Field(0, description="团队防守篮板", alias="reboundsTeamDefensive")
    rebounds_team_offensive: conint(ge=0) = Field(0, description="团队进攻篮板", alias="reboundsTeamOffensive")
    rebounds_total: conint(ge=0) = Field(0, description="总篮板", alias="reboundsTotal")

    # 二次进攻数据
    second_chance_points_attempted: conint(ge=0) = Field(0, description="二次进攻出手数", alias="secondChancePointsAttempted")
    second_chance_points_made: conint(ge=0) = Field(0, description="二次进攻命中数", alias="secondChancePointsMade")
    second_chance_points_percentage: float = Field(0.0, description="二次进攻命中率", alias="secondChancePointsPercentage")

    # 抢断数据
    steals: conint(ge=0) = Field(0, description="抢断数", alias="steals")

    # 球队投篮
    team_field_goal_attempts: conint(ge=0) = Field(0, description="团队投篮出手数", alias="teamFieldGoalAttempts")

    # 三分数据
    three_pointers_attempted: conint(ge=0) = Field(0, description="三分出手数", alias="threePointersAttempted")
    three_pointers_made: conint(ge=0) = Field(0, description="三分命中数", alias="threePointersMade")
    three_pointers_percentage: Optional[confloat(ge=0.0, le=1.0)] = Field(None, description="三分命中率", alias="threePointersPercentage")

    # 真实命中率
    true_shooting_attempts: float = Field(0.0, description="真实命中率出手数", alias="trueShootingAttempts")
    true_shooting_percentage: float = Field(0.0, description="真实命中率", alias="trueShootingPercentage")

    # 失误数据
    turnovers: conint(ge=0) = Field(0, description="失误数", alias="turnovers")
    turnovers_team: conint(ge=0) = Field(0, description="团队失误", alias="turnoversTeam")
    turnovers_total: conint(ge=0) = Field(0, description="总失误", alias="turnoversTotal")

    # 两分数据
    two_pointers_attempted: conint(ge=0) = Field(0, description="两分出手数", alias="twoPointersAttempted")
    two_pointers_made: conint(ge=0) = Field(0, description="两分命中数", alias="twoPointersMade")
    two_pointers_percentage: Optional[confloat(ge=0.0, le=1.0)] = Field(None, description="两分命中率", alias="twoPointersPercentage")

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def calculate_times(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算各种时间的分钟数

        Args:
            data: 包含时间信息的数据字典

        Returns:
            Dict: 添加了minutes_calculated和time_leading_calculated的数据字典
        """
        # 计算比赛时间
        minutes_str = data.get('minutes', 'PT00M00.00S')
        try:
            seconds = TimeHandler.parse_duration(minutes_str)
            data['minutes_calculated'] = round(seconds / 60.0, 2)
        except ValueError as e:
            logger.warning(f"解析时间字符串失败: {minutes_str}, 设置 minutes_calculated 为 0.0, 错误: {e}")
            data['minutes_calculated'] = 0.0

        # 计算领先时间
        leading_str = data.get('timeLeading', 'PT00M00.00S')  # 注意这里使用timeLeading而不是time_leading
        try:
            seconds = TimeHandler.parse_duration(leading_str)
            data['time_leading_calculated'] = round(seconds / 60.0, 2)
            logger.debug(f"领先时间解析: {leading_str} -> {data['time_leading_calculated']} 分钟")
        except ValueError as e:
            logger.warning(f"解析领先时间字符串失败: {leading_str}, 设置 time_leading_calculated 为 0.0, 错误: {e}")
            data['time_leading_calculated'] = 0.0

        return data


class TeamInGame(BaseModel):
    """球队比赛数据模型"""
    team_id: conint(ge=0) = Field(..., description="球队ID", alias="teamId")
    team_name: str = Field(..., description="球队名称", alias="teamName")
    team_city: str = Field(..., description="球队城市", alias="teamCity")
    team_tricode: str = Field(..., description="球队三字母代码", alias="teamTricode")
    score: conint(ge=0) = Field(..., description="球队得分")
    in_bonus: str = Field(..., description="是否在罚球线内", alias="inBonus")
    timeouts_remaining: conint(ge=0) = Field(..., description="剩余暂停次数", alias="timeoutsRemaining")
    periods: List[PeriodScore] = Field(default_factory=list, description="各节得分")
    players: List[PlayerInGame] = Field(default_factory=list, description="球队球员列表")
    statistics: TeamStatistics = Field(default_factory=TeamStatistics, description="球队统计数据")

    model_config = ConfigDict(from_attributes=True)


# ===========================
# 4. 比赛事件模型
# ===========================

class BaseEvent(BaseModel):
    """基础事件类"""
    action_number: int = Field(..., description="事件序号", alias="actionNumber")
    clock: str = Field(..., description="比赛时钟")
    time_actual: str = Field(..., description="实际时间", alias="timeActual")
    period: int = Field(..., description="比赛节数")
    team_id: Optional[int] = Field(None, description="球队ID", alias="teamId")
    team_tricode: Optional[str] = Field(None, description="球队三字码", alias="teamTricode")
    action_type: str = Field(..., description="事件类型", alias="actionType")
    sub_type: Optional[str] = Field(None, description="子类型", alias="subType")
    description: str = Field(..., description="事件描述")
    person_id: Optional[int] = Field(None, description="球员ID", alias="personId")
    player_name: Optional[str] = Field(None, description="球员姓名", alias="playerName")
    player_name_i: Optional[str] = Field(None, description="球员简称", alias="playerNameI")
    x: Optional[float] = Field(None, description="X坐标")
    y: Optional[float] = Field(None, description="Y坐标")
    x_legacy: Optional[int] = Field(None, description="传统X坐标", alias="xLegacy")
    y_legacy: Optional[int] = Field(None, description="传统Y坐标", alias="yLegacy")
    score_home: Optional[str] = Field(None, description="主队得分", alias="scoreHome")
    score_away: Optional[str] = Field(None, description="客队得分", alias="scoreAway")

    model_config = ConfigDict(from_attributes=True, extra='allow')

    @classmethod
    def filter_by_team(cls, events: List["BaseEvent"], team_id: int) -> List["BaseEvent"]:
        """按球队ID筛选事件"""
        return [event for event in events if event.team_id == team_id]

    @classmethod
    def filter_by_player(cls, events: List["BaseEvent"], player_id: int) -> List["BaseEvent"]:
        """按球员ID筛选事件"""
        return [event for event in events if event.person_id == player_id]

    @classmethod
    def filter_by_period(cls, events: List["BaseEvent"], period: int) -> List["BaseEvent"]:
        """按节数筛选事件"""
        return [event for event in events if event.period == period]

    @classmethod
    def filter_by_clutch_time(cls, events: List["BaseEvent"], minutes: int = 2) -> List["BaseEvent"]:
        """筛选关键时刻事件(第四节或加时赛最后几分钟)"""
        return [
            event for event in events
            if (event.period >= 4 and ":" in event.clock and
                int(event.clock.split(":")[0]) <= minutes)
        ]

    @classmethod
    def filter_multi(cls,
                     events: List["BaseEvent"],
                     team_id: Optional[int] = None,
                     player_id: Optional[int] = None,
                     period: Optional[int] = None,
                     is_clutch: bool = False,
                     clutch_minutes: int = 2) -> List["BaseEvent"]:
        """多条件筛选"""
        filtered = events

        if team_id is not None:
            filtered = cls.filter_by_team(filtered, team_id)

        if player_id is not None:
            filtered = cls.filter_by_player(filtered, player_id)

        if period is not None:
            filtered = cls.filter_by_period(filtered, period)

        if is_clutch:
            filtered = cls.filter_by_clutch_time(filtered, clutch_minutes)

        return filtered

    def calculate_importance(self) -> int:
        """计算事件重要性(0-5)"""
        importance = 0

        # 事件类型重要性
        high_importance_types = {"2pt", "3pt", "dunk", "block", "steal"}
        medium_importance_types = {"rebound", "assist", "foul"}

        if self.action_type.lower() in high_importance_types:
            importance += 3
        elif self.action_type.lower() in medium_importance_types:
            importance += 2

        # 关键时刻加分
        if self.period >= 4 and ":" in self.clock:
            minutes = int(self.clock.split(":")[0])
            if minutes <= 2:
                importance += 1

        # 比分接近加分
        if self.score_home and self.score_away:
            score_diff = abs(int(self.score_home) - int(self.score_away))
            if score_diff <= 5:
                importance += 1

        return min(importance, 5)

    @property
    def score_difference(self) -> Optional[int]:
        """计算比分差值"""
        if self.score_home and self.score_away:
            return int(self.score_home) - int(self.score_away)
        return None



class GameEvent(BaseEvent):
    """比赛事件(开始/结束)"""
    action_type: Literal["game"] = Field(..., description="事件类型", alias="actionType")
    sub_type: Literal["start", "end"] = Field(..., description="子类型", alias="subType")
    description: str = Field(..., description="事件描述")


class PeriodEvent(BaseEvent):
    """比赛节开始/结束事件"""
    action_type: Literal["period"] = Field(..., description="事件类型", alias="actionType")
    sub_type: Literal["start", "end"] = Field(..., description="子类型", alias="subType")


class JumpBallEvent(BaseEvent):
    """跳球事件"""
    action_type: Literal["jumpball"] = Field(..., description="事件类型", alias="actionType")
    jump_ball_won_person_id: int = Field(..., description="跳球获胜者ID", alias="jumpBallWonPersonId")
    jump_ball_won_player_name: str = Field(..., description="跳球获胜者姓名", alias="jumpBallWonPlayerName")
    jump_ball_lost_person_id: int = Field(..., description="跳球失败者ID", alias="jumpBallLostPersonId")
    jump_ball_lost_player_name: str = Field(..., description="跳球失败者姓名", alias="jumpBallLostPlayerName")
    jump_ball_recovered_person_id: Optional[int] = Field(None, description="获得球权者ID", alias="jumpBallRecoveredPersonId")
    jump_ball_recovered_name: Optional[str] = Field(None, description="获得球权者姓名", alias="jumpBallRecoveredName")


class ShotEvent(BaseEvent):
    """投篮事件"""
    action_type: Literal["2pt", "3pt"] = Field(..., description="事件类型", alias="actionType")
    sub_type: str = Field(..., description="投篮类型", alias="subType")
    area: str = Field(..., description="投篮区域")
    area_detail: Optional[str] = Field(None, description="详细区域", alias="areaDetail")
    side: Optional[str] = Field(None, description="场地侧边")
    shot_distance: float = Field(..., description="投篮距离", alias="shotDistance")
    shot_result: ShotResult = Field(..., description="投篮结果", alias="shotResult")
    is_field_goal: Optional[int] = Field(1, description="是否为投篮", alias="isFieldGoal")
    qualifiers: List[str] = Field(default_factory=list, description="限定词")
    assist_person_id: Optional[int] = Field(None, description="助攻者ID", alias="assistPersonId")
    assist_player_name_initial: Optional[str] = Field(None, description="助攻者简称", alias="assistPlayerNameInitial")
    block_person_id: Optional[int] = Field(None, description="盖帽者ID", alias="blockPersonId")
    block_player_name: Optional[str] = Field(None, description="盖帽者姓名", alias="blockPlayerName")

    @classmethod
    def filter_by_result(cls, events: List["ShotEvent"], result: ShotResult) -> List["ShotEvent"]:
        """按投篮结果筛选"""
        return [event for event in events if event.shot_result == result]


class TwoPointEvent(ShotEvent):
    """两分球事件"""
    action_type: Literal["2pt"] = Field(..., description="事件类型", alias="actionType")


class ThreePointEvent(ShotEvent):
    """三分球事件"""
    action_type: Literal["3pt"] = Field(..., description="事件类型", alias="actionType")


class AssistEvent(BaseEvent):
    """助攻事件"""
    action_type: Literal["assist"] = Field(..., description="事件类型", alias="actionType")
    assist_total: int = Field(..., description="助攻总数", alias="assistTotal")
    description: str = Field(..., description="事件描述")
    player_name: str = Field(..., description="助攻者姓名", alias="playerName")
    player_name_i: str = Field(..., description="助攻者简称", alias="playerNameI")
    scoring_player_name: str = Field(..., description="得分者姓名", alias="scoringPlayerName")
    scoring_player_name_i: str = Field(..., description="得分者简称", alias="scoringPlayerNameI")
    scoring_person_id: int = Field(..., description="得分者ID", alias="scoringPersonId")


class FreeThrowEvent(BaseEvent):
    """罚球事件"""
    action_type: Literal["freethrow"] = Field(..., description="事件类型", alias="actionType")
    sub_type: str = Field(..., description="罚球类型", alias="subType")
    is_field_goal: Optional[int] = Field(0, description="是否为投篮", alias="isFieldGoal")
    shot_result: ShotResult = Field(..., description="罚球结果", alias="shotResult")
    description: str = Field(..., description="事件描述")
    player_name: str = Field(..., description="罚球者姓名", alias="playerName")
    player_name_i: str = Field(..., description="罚球者简称", alias="playerNameI")
    points_total: Optional[int] = Field(None, description="得分", alias="pointsTotal")


class ReboundEvent(BaseEvent):
    """篮板事件"""
    action_type: Literal["rebound"] = Field(..., description="事件类型", alias="actionType")
    sub_type: Literal["offensive", "defensive"] = Field(..., description="篮板类型", alias="subType")
    rebound_total: int = Field(..., description="篮板总数", alias="reboundTotal")
    rebound_defensive_total: int = Field(..., description="防守篮板总数", alias="reboundDefensiveTotal")
    rebound_offensive_total: int = Field(..., description="进攻篮板总数", alias="reboundOffensiveTotal")
    description: str = Field(..., description="事件描述")
    player_name: str = Field(..., description="篮板球员姓名", alias="playerName")
    player_name_i: str = Field(..., description="篮板球员简称", alias="playerNameI")
    shot_action_number: Optional[int] = Field(None, description="相关投篮事件编号", alias="shotActionNumber")



class BlockEvent(BaseEvent):
    """盖帽事件"""
    action_type: Literal["block"] = Field(..., description="事件类型", alias="actionType")
    player_name: str = Field(..., description="盖帽者姓名", alias="playerName")
    player_name_i: str = Field(..., description="盖帽者简称", alias="playerNameI")


class StealEvent(BaseEvent):
    """抢断事件"""
    action_type: Literal["steal"] = Field(..., description="事件类型", alias="actionType")
    sub_type: str = Field("", description="子类型", alias="subType")
    description: str = Field(..., description="事件描述")
    player_name: str = Field(..., description="抢断者姓名", alias="playerName")
    player_name_i: str = Field(..., description="抢断者简称", alias="playerNameI")



class TurnoverEvent(BaseEvent):
    """失误事件"""
    action_type: Literal["turnover"] = Field(..., description="事件类型", alias="actionType")
    sub_type: str = Field(..., description="失误类型", alias="subType")
    descriptor: Optional[str] = Field(None, description="描述词")
    turnover_total: int = Field(..., description="失误总数", alias="turnoverTotal")
    description: str = Field(..., description="事件描述")
    player_name: str = Field(..., description="失误者姓名", alias="playerName")
    player_name_i: str = Field(..., description="失误者简称", alias="playerNameI")
    steal_person_id: Optional[int] = Field(None, description="抢断者ID", alias="stealPersonId")
    steal_player_name: Optional[str] = Field(None, description="抢断者姓名", alias="stealPlayerName")


class FoulEvent(BaseEvent):
    """犯规事件"""
    action_type: Literal["foul"] = Field(..., description="事件类型", alias="actionType")
    sub_type: str = Field(..., description="犯规类型", alias="subType")
    descriptor: Optional[str] = Field(None, description="描述词")
    foul_drawn_player_name: Optional[str] = Field(None, description="被犯规球员姓名", alias="foulDrawnPlayerName")
    foul_drawn_person_id: Optional[int] = Field(None, description="被犯规球员ID", alias="foulDrawnPersonId")
    official_id: Optional[int] = Field(None, description="裁判ID", alias="officialId")
    description: str = Field(..., description="事件描述")
    player_name: str = Field(..., description="犯规者姓名", alias="playerName")
    player_name_i: str = Field(..., description="犯规者简称", alias="playerNameI")


class ViolationEvent(BaseEvent):
    """违例事件"""
    action_type: Literal["violation"] = Field(..., description="事件类型", alias="actionType")
    sub_type: str = Field(..., description="违例类型", alias="subType")
    description: str = Field(..., description="事件描述")
    official_id: Optional[int] = Field(None, description="裁判ID", alias="officialId")
    player_name: str = Field(..., description="违例者姓名", alias="playerName")
    player_name_i: str = Field(..., description="违例者简称", alias="playerNameI")

class EjectionEvent(BaseEvent):
    """驱逐出场事件"""
    action_type: Literal["ejection"] = Field(..., description="事件类型", alias="actionType")
    sub_type: str = Field(..., description="驱逐类型", alias="subType")
    official_id: Optional[int] = Field(None, description="裁判ID", alias="officialId")
    description: str = Field(..., description="事件描述")
    player_name: str = Field(..., description="被驱逐球员姓名", alias="playerName")
    player_name_i: str = Field(..., description="被驱逐球员简称", alias="playerNameI")

class TimeoutEvent(BaseEvent):
    """暂停事件"""
    action_type: Literal["timeout"] = Field(..., description="事件类型", alias="actionType")
    sub_type: str = Field(..., description="暂停类型", alias="subType")
    description: str = Field(..., description="事件描述")


class SubstitutionEvent(BaseEvent):
    """换人事件"""
    action_type: Literal["substitution"] = Field(..., description="事件类型", alias="actionType")
    sub_type: Optional[str] = Field(None, description="换人类型", alias="subType")
    incoming_player_name: str = Field(..., description="替补上场球员姓名", alias="incomingPlayerName")
    incoming_player_name_i: str = Field(..., description="替补上场球员简称", alias="incomingPlayerNameI")
    incoming_person_id: int = Field(..., description="替补上场球员ID", alias="incomingPersonId")
    outgoing_player_name: str = Field(..., description="替补下场球员姓名", alias="outgoingPlayerName")
    outgoing_player_name_i: str = Field(..., description="替补下场球员简称", alias="outgoingPlayerNameI")
    outgoing_person_id: int = Field(..., description="替补下场球员ID", alias="outgoingPersonId")
    description: str = Field(..., description="事件描述")


# ===========================
# 5. 比赛核心数据模型
# ===========================

class PlayByPlay(BaseModel):
    """比赛回放数据"""
    game: Dict[str, Any] = Field(..., description="比赛信息")
    meta: Optional[Dict[str, Any]] = Field(None, description="元数据")
    actions: List[BaseEvent] = Field(default_factory=list, description="所有事件列表")

    model_config = ConfigDict(from_attributes=True)


class GameData(BaseModel):
    """比赛详细数据模型"""
    game_id: str = Field(default="", description="比赛ID", alias="gameId")
    game_time_local: datetime = Field(default_factory=datetime.now, description="本地时间", alias="gameTimeLocal")
    game_time_utc: datetime = Field(default_factory=datetime.now, description="UTC时间", alias="gameTimeUTC")
    game_time_home: datetime = Field(default_factory=datetime.now, description="主队时间", alias="gameTimeHome")
    game_time_away: datetime = Field(default_factory=datetime.now, description="客队时间", alias="gameTimeAway")
    game_et: datetime = Field(default_factory=datetime.now, description="东部时间", alias="gameEt")
    # 修改北京时间字段，不设置默认值，由UTC计算
    game_time_beijing: datetime = Field(default=None,description="北京时间")
    duration: conint(ge=0) = Field(default=0, description="比赛时长（分钟）")
    game_code: str = Field(default="", description="比赛代码", alias="gameCode")
    game_status: GameStatusEnum = Field(default=GameStatusEnum.NOT_STARTED, description="比赛状态", alias="gameStatus")
    game_status_text: str = Field(default="Not Started", description="比赛状态文本", alias="gameStatusText")
    period: conint(ge=1) = Field(default=1, description="当前节次")
    regulation_periods: conint(ge=1) = Field(default=4, description="常规赛节次", alias="regulationPeriods")
    game_clock: str = Field(default="PT12M00.00S", description="比赛时钟", alias="gameClock")
    attendance: conint(ge=0) = Field(default=0, description="观众人数")
    sellout: str = Field(default="0", description="是否售罄")
    arena: Arena = Field(default_factory=Arena, description="场馆信息")
    officials: List[Official] = Field(default_factory=list, description="裁判列表")
    home_team: TeamInGame = Field(..., description="主队数据", alias="homeTeam")
    away_team: TeamInGame = Field(..., description="客队数据", alias="awayTeam")
    statistics: Optional[Dict[str, Any]] = Field(None, description="比赛统计数据")

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='after')
    def validate_beijing_time(self):
        """确保北京时间始终基于UTC时间计算"""
        if hasattr(self, 'game_time_utc') and self.game_time_utc:
            self.game_time_beijing = TimeHandler.to_beijing(self.game_time_utc)
        return self

# ===========================
# 6. 完整的Game模型，并提供基本的数据接口
# ===========================


class Game(BaseModel):
    """完整比赛数据模型"""
    meta: Dict[str, Any] = Field(..., description="元数据")
    game_data: GameData = Field(..., description="比赛数据", alias="gameData")
    play_by_play: Optional[PlayByPlay] = Field(None, description="比赛回放数据", alias="playByPlay")

    model_config = ConfigDict(from_attributes=True)

    #=====model层提供清晰的数据访问接口,类似于数据库的功能，service层可以直接调用这些接口，代码更简洁=========

    ## 1.获取比赛基本信息
    def get_game_status(self) -> Dict[str, Any]:
        """
        获取比赛状态信息，返回字典

        Returns:
            Dict[str, Any]: 包含比赛状态信息的字典
        """
        game_data = self.game_data
        status_text = game_data.game_status_text
        period_name = f"Period {game_data.period}"  # 简化节数名称
        current_period = game_data.period
        time_remaining_str = str(game_data.game_clock)

        # 尝试解析时间，处理 'PT' 开头的 ISO 格式时间
        try:
            time_remaining = TimeHandler.parse_duration(time_remaining_str)
            minutes = time_remaining // 60
            seconds = time_remaining % 60
            time_remaining = f"{minutes:02d}:{seconds:02d}"  # 格式化为 MM:SS
        except ValueError:
            time_remaining = time_remaining_str  # 无法解析则直接使用原始字符串

        away_score = int(game_data.away_team.score)
        home_score = int(game_data.home_team.score)
        away_timeouts = game_data.away_team.timeouts_remaining
        home_timeouts = game_data.home_team.timeouts_remaining
        home_bonus = game_data.home_team.in_bonus == "1"  # 转换为布尔值
        away_bonus = game_data.away_team.in_bonus == "1"  # 转换为布尔值

        return {
            "status_text": status_text,
            "period_name": period_name,
            "current_period": current_period,
            "time_remaining": time_remaining,
            "away_score": away_score,
            "home_score": home_score,
            "away_timeouts": away_timeouts,
            "home_timeouts": home_timeouts,
            "home_bonus": home_bonus,
            "away_bonus": away_bonus
        }

    @staticmethod
    def _active_players(players: List[PlayerInGame]) -> List[Dict[str, Any]]:
        """获取场上球员"""
        return [
            {'id': p.person_id, 'name': p.name, 'position': p.position}
            for p in players if p.on_court == "1"
        ]

    def get_current_lineup(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取当前场上阵容"""
        return {
            'home': self._active_players(self.game_data.home_team.players),
            'away': self._active_players(self.game_data.away_team.players)
        }

    ##2.筛选球队的统计数据

    def get_team_stats(self, team_id: int) -> Optional[TeamInGame]:
        """获取指定球队的统计数据"""
        if self.game_data.home_team.team_id == team_id:
            return self.game_data.home_team
        elif self.game_data.away_team.team_id == team_id:
            return self.game_data.away_team
        return None

    ##2.筛选球员的统计数据
    def get_player_stats(self, player_id: int) -> Optional[PlayerInGame]:
        """获取指定球员的统计数据"""
        # 在主队中查找
        for player in self.game_data.home_team.players:
            if player.person_id == player_id:
                return player

        # 在客队中查找
        for player in self.game_data.away_team.players:
            if player.person_id == player_id:
                return player

        return None


    ##3.筛选事件
    def filter_events(self,
                      period: Optional[int] = None,
                      team_id: Optional[int] = None,
                      player_id: Optional[int] = None,
                      action_types: Optional[Set[str]] = None) -> List[BaseEvent]:
        """多维度筛选事件"""
        if not self.play_by_play or not self.play_by_play.actions:
            return []

        filtered_events = BaseEvent.filter_multi(
            self.play_by_play.actions,
            team_id=team_id,
            player_id=player_id,
            period=period
        )

        if action_types:  # 如果 action_types 参数被传入了值
            filtered_events = [
                event for event in filtered_events
                if event.action_type in action_types
            ]

        return filtered_events

    def calculate_scoring_efficiency(self, player_id: Optional[int] = None, team_id: Optional[int] = None) -> Dict[
        str, Any]:
        """计算进攻效率统计信息

        为特定球员或球队计算详细的进攻效率数据，如真实命中率、有效投篮率等。

        Args:
            player_id: 可选的球员ID
            team_id: 可选的球队ID

        Returns:
            Dict[str, Any]: 包含详细效率指标的字典
        """
        try:
            if player_id:
                # 获取球员数据
                player = self.get_player_stats(player_id)
                if not player:
                    return {"error": f"未找到ID为{player_id}的球员"}

                stats = player.statistics

                # 计算基础效率指标
                fg_pct = stats.field_goals_percentage or 0
                fg3_pct = stats.three_pointers_percentage or 0
                ft_pct = stats.free_throws_percentage or 0

                # 真实命中率
                tsa = stats.field_goals_attempted + 0.44 * stats.free_throws_attempted
                ts_pct = 0 if tsa == 0 else stats.points / (2 * tsa)

                # 有效投篮率
                efg_pct = 0
                if stats.field_goals_attempted > 0:
                    efg_pct = (stats.field_goals_made + 0.5 * stats.three_pointers_made) / stats.field_goals_attempted

                # 得分效率
                points_per_shot = 0 if stats.field_goals_attempted == 0 else stats.points / stats.field_goals_attempted

                return {
                    "name": player.name,
                    "team_id": None,  # 需要额外查询
                    "minutes": stats.minutes_calculated,
                    "basic_stats": {
                        "points": stats.points,
                        "field_goals": {"made": stats.field_goals_made, "attempted": stats.field_goals_attempted,
                                        "pct": fg_pct},
                        "three_pointers": {"made": stats.three_pointers_made,
                                           "attempted": stats.three_pointers_attempted, "pct": fg3_pct},
                        "free_throws": {"made": stats.free_throws_made, "attempted": stats.free_throws_attempted,
                                        "pct": ft_pct}
                    },
                    "advanced_stats": {
                        "true_shooting_pct": ts_pct,
                        "effective_fg_pct": efg_pct,
                        "points_per_shot": points_per_shot,
                        "points_per_possession": None  # 需要额外数据计算
                    }
                }

            elif team_id:
                # 获取球队数据
                team = self.get_team_stats(team_id)
                if not team:
                    return {"error": f"未找到ID为{team_id}的球队"}

                stats = team.statistics

                # 提取基础效率指标
                return {
                    "team_name": f"{team.team_city} {team.team_name}",
                    "team_id": team.team_id,
                    "basic_stats": {
                        "points": stats.points,
                        "points_against": stats.points_against,
                        "field_goals": {
                            "made": stats.field_goals_made,
                            "attempted": stats.field_goals_attempted,
                            "pct": stats.field_goals_percentage
                        }
                    },
                    "efficiency_stats": {
                        "points_per_possession": None,  # 需要额外数据
                        "true_shooting_pct": stats.true_shooting_percentage,
                        "assists_per_turnover": stats.assists_turnover_ratio
                    },
                    "scoring_breakdown": {
                        "paint_points": stats.points_in_the_paint,
                        "fast_break_points": stats.points_fast_break,
                        "second_chance_points": stats.points_second_chance,
                        "points_off_turnovers": stats.points_from_turnovers
                    }
                }

            return {"error": "必须提供球员ID或球队ID"}

        except Exception as e:
            logger.error(f"计算进攻效率时出错: {str(e)}")
            return {"error": f"计算进攻效率时出错: {str(e)}"}

    def get_game_summary(self) -> Dict[str, Any]:
        """获取比赛综合摘要信息

        Returns:
            Dict[str, Any]: 包含比赛关键信息的摘要字典
        """
        try:
            game_data = self.game_data

            # 获取主队和客队信息
            home_team = f"{game_data.home_team.team_city} {game_data.home_team.team_name}"
            away_team = f"{game_data.away_team.team_city} {game_data.away_team.team_name}"
            home_score = int(game_data.home_team.score)
            away_score = int(game_data.away_team.score)

            # 确定获胜方
            winner = home_team if home_score > away_score else away_team
            winning_score = home_score if home_score > away_score else away_score
            losing_score = away_score if home_score > away_score else home_score

            # 获取主队得分最高的球员
            home_players = sorted(game_data.home_team.players,
                                  key=lambda p: p.statistics.points,
                                  reverse=True)
            away_players = sorted(game_data.away_team.players,
                                  key=lambda p: p.statistics.points,
                                  reverse=True)

            home_top_scorer = home_players[0] if home_players else None
            away_top_scorer = away_players[0] if away_players else None

            # 创建汇总
            summary = {
                "game_id": game_data.game_id,
                "date": game_data.game_time_beijing.strftime('%Y-%m-%d'),
                "arena": f"{game_data.arena.arena_name}, {game_data.arena.arena_city}",
                "teams": {
                    "home": {
                        "name": home_team,
                        "score": home_score,
                        "top_scorer": {
                            "name": home_top_scorer.name if home_top_scorer else "N/A",
                            "points": home_top_scorer.statistics.points if home_top_scorer else 0
                        }
                    },
                    "away": {
                        "name": away_team,
                        "score": away_score,
                        "top_scorer": {
                            "name": away_top_scorer.name if away_top_scorer else "N/A",
                            "points": away_top_scorer.statistics.points if away_top_scorer else 0
                        }
                    }
                },
                "result": {
                    "winner": winner,
                    "score": f"{winning_score}-{losing_score}",
                    "differential": abs(home_score - away_score)
                },
                "status": game_data.game_status_text,
                "attendance": game_data.attendance
            }

            # 如果比赛已结束，添加亮点球员
            if game_data.game_status == GameStatusEnum.FINISHED:
                # 合并所有球员并按得分排序
                all_players = home_players + away_players
                top_scorers = sorted(all_players,
                                     key=lambda p: p.statistics.points,
                                     reverse=True)[:3]

                top_rebounders = sorted(all_players,
                                        key=lambda p: p.statistics.rebounds_total,
                                        reverse=True)[:3]

                top_assisters = sorted(all_players,
                                       key=lambda p: p.statistics.assists,
                                       reverse=True)[:3]

                summary["notable_performances"] = {
                    "scoring": [
                        {
                            "name": p.name,
                            "team": "home" if p in home_players else "away",
                            "points": p.statistics.points
                        } for p in top_scorers
                    ],
                    "rebounding": [
                        {
                            "name": p.name,
                            "team": "home" if p in home_players else "away",
                            "rebounds": p.statistics.rebounds_total
                        } for p in top_rebounders
                    ],
                    "assists": [
                        {
                            "name": p.name,
                            "team": "home" if p in home_players else "away",
                            "assists": p.statistics.assists
                        } for p in top_assisters
                    ]
                }

            return summary

        except Exception as e:
            logger.error(f"获取比赛摘要时出错: {str(e)}")
            return {"error": f"获取比赛摘要时出错: {str(e)}"}

    ##=========== 投篮分布图数据准备方法 ===========##

    def get_shot_data(self, player_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取投篮数据

        Args:
            player_id: 球员ID，如果提供则只返回该球员的投篮数据

        Returns:
            List[Dict[str, Any]]: 投篮数据列表，包含是否被助攻的信息
        """
        shot_data = []
        if self.play_by_play and self.play_by_play.actions:
            for action in self.play_by_play.actions:
                if action.action_type in ["2pt", "3pt"]:
                    # 如果指定了球员ID，则只返回该球员的投篮
                    if player_id is not None and action.person_id != player_id:
                        continue

                    shot_data.append({
                        'x_legacy': action.x_legacy if hasattr(action, 'x_legacy') else None,
                        'y_legacy': action.y_legacy if hasattr(action, 'y_legacy') else None,
                        'shot_result': action.shot_result if hasattr(action, 'shot_result') else None,
                        'description': action.description,
                        'player_id': action.person_id,
                        'team_id': action.team_id,
                        'period': action.period,
                        'action_type': action.action_type,
                        'time': action.clock,
                        'assisted': True if hasattr(action,
                                                    'assist_person_id') and action.assist_person_id is not None else False,
                        'assist_player_id': getattr(action, 'assist_person_id', None),
                        'assist_player_name': getattr(action, 'assist_player_name_initial', None)
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
        if self.play_by_play and self.play_by_play.actions:
            for action in self.play_by_play.actions:
                # 只关注投篮事件
                if action.action_type not in ["2pt", "3pt"]:
                    continue

                # 检查是否是该球员的助攻
                if (hasattr(action, "assist_person_id") and
                        action.assist_person_id == passer_id and
                        action.shot_result == "Made"):  # 只记录命中的球

                    assisted_shots.append({
                        'x': action.x_legacy if hasattr(action, 'x_legacy') else None,
                        'y': action.y_legacy if hasattr(action, 'y_legacy') else None,
                        'shot_type': action.action_type,
                        'shooter_id': action.person_id,
                        'shooter_name': action.player_name,
                        'team_id': action.team_id,
                        'period': action.period,
                        'time': action.clock,
                        'description': action.description,
                        'area': getattr(action, 'area', None),
                        'distance': getattr(action, 'shot_distance', None)
                    })

        return assisted_shots

    def get_team_shot_data(self, team_id: int) -> Dict[int, List[Dict[str, Any]]]:
        """获取指定球队所有球员的投篮数据

        Args:
            team_id: 球队ID

        Returns:
            Dict[int, List[Dict[str, Any]]]: 以球员ID为键,投篮数据列表为值的字典
        """
        team_shots = {}

        try:
            # 获取主队和客队
            home_team = self.game_data.home_team
            away_team = self.game_data.away_team

            # 确定目标球队
            target_team = None
            if home_team.team_id == team_id:
                target_team = home_team
            elif away_team.team_id == team_id:
                target_team = away_team

            if not target_team:
                logger.warning(f"未找到ID为 {team_id} 的球队")
                return {}

            # 获取球队所有球员的投篮数据
            if hasattr(target_team, 'players'):
                for player in target_team.players:
                    if player.played == "1":  # 只处理上场球员
                        shots = self.get_shot_data(player.person_id)
                        if shots:  # 只添加有投篮数据的球员
                            team_shots[player.person_id] = shots

            return team_shots

        except Exception as e:
            logger.error(f"获取球队投篮数据时出错: {str(e)}")
            return {}

    ##=========== AI数据准备方法 ===========##

    def prepare_ai_data(self, player_id: Optional[int] = None) -> Dict[str, Any]:
        """准备用于AI分析的结构化数据

        提供结构化数据格式，专为AI模型分析设计。
        保留原始数据结构，同时添加必要的上下文信息。

        Args:
            player_id: 可选的球员ID，用于筛选特定球员数据

        Returns:
            Dict[str, Any]: 包含结构化数据的字典
        """
        if not self.game_data:
            logger.error("比赛数据不完整")
            return {"error": "比赛数据不完整或不可用"}

        try:
            # 1. 创建一个处理上下文字典以减少重复查询
            context = {
                # 存储球队名称映射，避免重复生成
                "team_names": {
                    "home": {
                        "full_name": f"{self.game_data.home_team.team_city} {self.game_data.home_team.team_name}",
                        "short_name": self.game_data.home_team.team_name,
                        "tricode": self.game_data.home_team.team_tricode,
                        "team_id": self.game_data.home_team.team_id
                    },
                    "away": {
                        "full_name": f"{self.game_data.away_team.team_city} {self.game_data.away_team.team_name}",
                        "short_name": self.game_data.away_team.team_name,
                        "tricode": self.game_data.away_team.team_tricode,
                        "team_id": self.game_data.away_team.team_id
                    }
                },
                # 存储日期时间信息，避免重复格式化
                "dates": {
                    "utc": {
                        "date": self.game_data.game_time_utc.strftime('%Y-%m-%d'),
                        "time": self.game_data.game_time_utc.strftime('%H:%M')
                    },
                    "beijing": {
                        "date": self.game_data.game_time_beijing.strftime('%Y-%m-%d'),
                        "time": self.game_data.game_time_beijing.strftime('%H:%M')
                    }
                },
                # 存储比赛状态信息
                "game_status": self.get_game_status()
            }

            # 2. 准备完整的数据结构，使用上下文字典
            return {
                "game_info": self._prepare_ai_game_info(context),
                "game_status": self._prepare_ai_game_status(context),
                "game_result": self._prepare_ai_game_result(context),
                "team_stats": self._prepare_ai_team_stats(context),
                "player_stats": self._prepare_ai_player_stats(player_id),
                "events": self._prepare_ai_events(player_id)
            }
        except Exception as e:
            logger.error(f"准备AI数据失败: {str(e)}")
            return {"error": f"准备AI数据失败: {str(e)}"}

    def _prepare_ai_game_info(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """准备比赛基本信息的AI友好格式"""
        game_data = self.game_data

        # 直接从上下文中获取球队和日期信息
        home_team_full = context["team_names"]["home"]["full_name"]
        away_team_full = context["team_names"]["away"]["full_name"]

        # 构建场馆信息和上下文说明
        arena_info = {
            "name": game_data.arena.arena_name,
            "city": game_data.arena.arena_city,
            "state": game_data.arena.arena_state,
            "full_location": f"{game_data.arena.arena_name}, {game_data.arena.arena_city}, {game_data.arena.arena_state}"
        }

        context_text = f"{home_team_full}主场迎战{away_team_full}，比赛于北京时间{context['dates']['beijing']['date']} {context['dates']['beijing']['time']}在{arena_info['name']}进行"

        # 直接使用字典字面量返回
        return {
            "game_id": game_data.game_id,
            "teams": {
                "home": context["team_names"]["home"],
                "away": context["team_names"]["away"]
            },
            "date": {
                "utc": context["dates"]["utc"]["date"],
                "time_utc": context["dates"]["utc"]["time"],
                "beijing": context["dates"]["beijing"]["date"],
                "time_beijing": context["dates"]["beijing"]["time"]
            },
            "arena": arena_info,
            "context": context_text
        }

    def _prepare_ai_game_status(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """准备比赛状态的AI友好格式"""
        game_status = context["game_status"]
        score_diff = abs(game_status['home_score'] - game_status['away_score'])

        # 构建状态上下文
        if game_status['status_text'] == '进行中':
            if game_status['current_period'] <= 2:
                phase = "上半场"
            elif game_status['current_period'] <= 4:
                phase = "下半场"
            else:
                phase = "加时赛"

            leader = context["team_names"]["home"]["tricode"] if game_status['home_score'] > game_status[
                'away_score'] else context["team_names"]["away"]["tricode"]
            status_context = f"比赛{phase}{game_status['period_name']}，{leader}领先{score_diff}分，剩余时间{game_status['time_remaining']}"
        else:
            status_context = f"比赛已{game_status['status_text']}"

        # 直接使用字典字面量返回
        return {
            "status": game_status['status_text'],
            "period": {
                "current": game_status['current_period'],
                "name": game_status['period_name']
            },
            "time_remaining": game_status['time_remaining'],
            "score": {
                "home": {
                    "team": context["team_names"]["home"]["tricode"],
                    "points": game_status['home_score']
                },
                "away": {
                    "team": context["team_names"]["away"]["tricode"],
                    "points": game_status['away_score']
                },
                "leader": "home" if game_status['home_score'] > game_status['away_score'] else "away",
                "differential": score_diff
            },
            "bonus": {
                "home": game_status['home_bonus'],
                "away": game_status['away_bonus']
            },
            "timeouts": {
                "home": game_status['home_timeouts'],
                "away": game_status['away_timeouts']
            },
            "context": status_context
        }

    def _prepare_ai_game_result(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """准备比赛结果的AI友好格式"""
        game_data = self.game_data

        # 如果比赛未结束，返回空
        if game_data.game_status != GameStatusEnum.FINISHED:
            return {}

        # 从上下文获取主队和客队信息
        home_team = context["team_names"]["home"]
        away_team = context["team_names"]["away"]

        home_score = int(game_data.home_team.score)
        away_score = int(game_data.away_team.score)

        # 确定获胜方
        if home_score > away_score:
            winner = {
                "team_id": home_team["team_id"],
                "team_tricode": home_team["tricode"],
                "team_name": home_team["full_name"],
                "score": home_score
            }
            loser = {
                "team_id": away_team["team_id"],
                "team_tricode": away_team["tricode"],
                "team_name": away_team["full_name"],
                "score": away_score
            }
        else:
            winner = {
                "team_id": away_team["team_id"],
                "team_tricode": away_team["tricode"],
                "team_name": away_team["full_name"],
                "score": away_score
            }
            loser = {
                "team_id": home_team["team_id"],
                "team_tricode": home_team["tricode"],
                "team_name": home_team["full_name"],
                "score": home_score
            }

        # 计算比分差距
        point_diff = winner["score"] - loser["score"]

        result_context = f"{winner['team_name']} {winner['score']}-{loser['score']} 战胜 {loser['team_name']}"

        # 直接使用字典字面量返回
        return {
            "winner": winner,
            "loser": loser,
            "score_difference": point_diff,
            "final_score": f"{winner['team_tricode']} {winner['score']} - {loser['team_tricode']} {loser['score']}",
            "attendance": {
                "count": game_data.attendance,
                "sellout": game_data.sellout == "1"
            },
            "duration": game_data.duration,
            "context": result_context
        }

    def _prepare_ai_team_stats(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """准备球队统计数据的AI友好格式"""
        game_data = self.game_data

        # 准备主队统计数据
        home_stats = self._prepare_single_team_ai_stats(game_data.home_team, True, context)
        # 准备客队统计数据
        away_stats = self._prepare_single_team_ai_stats(game_data.away_team, False, context)

        # 直接使用字典字面量返回
        return {
            "home": home_stats,
            "away": away_stats
        }

    def _prepare_single_team_ai_stats(self, team: TeamInGame, is_home: bool, context: Dict[str, Any]) -> Dict[
        str, Any]:
        """准备单个球队的AI友好统计数据"""
        stats = team.statistics
        team_context = context["team_names"]["home" if is_home else "away"]

        # 直接使用字典字面量返回
        return {
            "basic": {
                "team_id": team_context["team_id"],
                "team_name": team_context["full_name"],
                "team_tricode": team_context["tricode"],
                "is_home": is_home,
                "points": stats.points,
                "points_against": stats.points_against
            },
            "shooting": {
                "field_goals": {
                    "made": stats.field_goals_made,
                    "attempted": stats.field_goals_attempted,
                    "percentage": stats.field_goals_percentage
                },
                "three_pointers": {
                    "made": stats.three_pointers_made,
                    "attempted": stats.three_pointers_attempted,
                    "percentage": stats.three_pointers_percentage
                },
                "two_pointers": {
                    "made": stats.two_pointers_made,
                    "attempted": stats.two_pointers_attempted,
                    "percentage": stats.two_pointers_percentage
                },
                "free_throws": {
                    "made": stats.free_throws_made,
                    "attempted": stats.free_throws_attempted,
                    "percentage": stats.free_throws_percentage
                },
                "true_shooting_percentage": stats.true_shooting_percentage
            },
            "rebounds": {
                "total": stats.rebounds_total,
                "offensive": stats.rebounds_offensive,
                "defensive": stats.rebounds_defensive,
                "team": stats.rebounds_team,
                "team_offensive": stats.rebounds_team_offensive,
                "team_defensive": stats.rebounds_team_defensive,
                "personal": stats.rebounds_personal
            },
            "offense": {
                "assists": stats.assists,
                "assists_turnover_ratio": stats.assists_turnover_ratio,
                "bench_points": stats.bench_points,
                "points_in_the_paint": {
                    "points": stats.points_in_the_paint,
                    "made": stats.points_in_the_paint_made,
                    "attempted": stats.points_in_the_paint_attempted,
                    "percentage": stats.points_in_the_paint_percentage
                },
                "fast_break_points": {
                    "points": stats.points_fast_break,
                    "made": stats.fast_break_points_made,
                    "attempted": stats.fast_break_points_attempted,
                    "percentage": stats.fast_break_points_percentage
                },
                "second_chance_points": {
                    "points": stats.points_second_chance,
                    "made": stats.second_chance_points_made,
                    "attempted": stats.second_chance_points_attempted,
                    "percentage": stats.second_chance_points_percentage
                },
                "points_from_turnovers": stats.points_from_turnovers
            },
            "defense": {
                "steals": stats.steals,
                "blocks": stats.blocks,
                "blocks_received": stats.blocks_received,
                "turnovers": {
                    "total": stats.turnovers_total,
                    "personal": stats.turnovers,
                    "team": stats.turnovers_team
                }
            },
            "fouls": {
                "personal": stats.fouls_personal,
                "offensive": stats.fouls_offensive,
                "technical": stats.fouls_technical,
                "team": stats.fouls_team,
                "team_technical": stats.fouls_team_technical
            },
            "lead_data": {
                "time_leading": stats.time_leading_calculated,
                "biggest_lead": stats.biggest_lead,
                "biggest_lead_score": stats.biggest_lead_score,
                "biggest_scoring_run": stats.biggest_scoring_run,
                "biggest_scoring_run_score": stats.biggest_scoring_run_score,
                "lead_changes": stats.lead_changes
            }
        }

    def _prepare_ai_player_stats(self, player_id: Optional[int] = None) -> Dict[str, Any]:
        """准备球员统计数据的AI友好格式"""
        game_data = self.game_data
        result = {"home": [], "away": []}

        # 如果指定了球员ID
        if player_id:
            player = self.get_player_stats(player_id)
            if player and player.played == "1":
                is_home = player in game_data.home_team.players
                team_type = "home" if is_home else "away"
                player_data = self._prepare_single_player_ai_stats(player)
                result[team_type].append(player_data)
        else:
            # 处理主队球员
            for player in game_data.home_team.players:
                if player.played == "1":  # 只处理参与比赛的球员
                    result["home"].append(self._prepare_single_player_ai_stats(player))

            # 处理客队球员
            for player in game_data.away_team.players:
                if player.played == "1":  # 只处理参与比赛的球员
                    result["away"].append(self._prepare_single_player_ai_stats(player))

            # 按得分排序
            result["home"] = sorted(result["home"], key=lambda x: x["basic"]["points"], reverse=True)
            result["away"] = sorted(result["away"], key=lambda x: x["basic"]["points"], reverse=True)

        return result

    def _prepare_single_player_ai_stats(self, player: PlayerInGame) -> Dict[str, Any]:
        """准备单个球员的AI友好统计数据"""
        stats = player.statistics
        starter_status = "首发" if player.starter == "1" else "替补"
        on_court_status = "场上" if player.on_court == "1" else "场下"

        # 直接使用字典字面量返回
        return {
            "basic": {
                "name": player.name,
                "player_id": player.person_id,
                "jersey_num": player.jersey_num,
                "position": player.position or "N/A",
                "starter": starter_status,
                "on_court": on_court_status,
                "minutes": stats.minutes_calculated,
                "points": stats.points,
                "plus_minus": stats.plus_minus_points,
                "rebounds": stats.rebounds_total,
                "assists": stats.assists
            },
            "shooting": {
                "field_goals": {
                    "made": stats.field_goals_made,
                    "attempted": stats.field_goals_attempted,
                    "percentage": stats.field_goals_percentage
                },
                "three_pointers": {
                    "made": stats.three_pointers_made,
                    "attempted": stats.three_pointers_attempted,
                    "percentage": stats.three_pointers_percentage
                },
                "two_pointers": {
                    "made": stats.two_pointers_made,
                    "attempted": stats.two_pointers_attempted,
                    "percentage": stats.two_pointers_percentage
                },
                "free_throws": {
                    "made": stats.free_throws_made,
                    "attempted": stats.free_throws_attempted,
                    "percentage": stats.free_throws_percentage
                }
            },
            "rebounds": {
                "total": stats.rebounds_total,
                "offensive": stats.rebounds_offensive,
                "defensive": stats.rebounds_defensive
            },
            "other_stats": {
                "assists": stats.assists,
                "steals": stats.steals,
                "blocks": stats.blocks,
                "blocks_received": stats.blocks_received,
                "turnovers": stats.turnovers,
                "fouls": {
                    "personal": stats.fouls_personal,
                    "drawn": stats.fouls_drawn,
                    "offensive": stats.fouls_offensive,
                    "technical": stats.fouls_technical
                },
                "scoring_breakdown": {
                    "paint_points": stats.points_in_the_paint,
                    "fast_break_points": stats.points_fast_break,
                    "second_chance_points": stats.points_second_chance
                }
            }
        }

    def _prepare_ai_events(self, player_id: Optional[int] = None) -> Dict[str, Any]:
        """准备比赛事件的AI友好格式，使用filter_events方法"""
        if not self.play_by_play or not self.play_by_play.actions:
            return {"data": [], "count": 0}

        # 使用filter_events方法直接获取筛选后的事件
        filtered_events = self.filter_events(player_id=player_id)

        # 将事件转换为字典格式
        events_data = []
        for event in filtered_events:
            # 创建基础事件数据
            event_dict = {
                "action_number": event.action_number,
                "period": event.period,
                "clock": event.clock,
                "time_actual": event.time_actual,
                "action_type": event.action_type,
                "sub_type": getattr(event, "sub_type", None),
                "description": event.description,
                "team_id": getattr(event, "team_id", None),
                "team_tricode": getattr(event, "team_tricode", None),
                "player_id": getattr(event, "person_id", None),
                "player_name": getattr(event, "player_name", None),
                "player_name_i": getattr(event, "player_name_i", None),
                "score_home": getattr(event, "score_home", None),
                "score_away": getattr(event, "score_away", None),
                "x": getattr(event, "x", None),
                "y": getattr(event, "y", None),
                "x_legacy": getattr(event, "x_legacy", None),
                "y_legacy": getattr(event, "y_legacy", None)
            }

            # 根据事件类型添加特定属性
            action_type = event.action_type

            if action_type in ["2pt", "3pt"]:  # 投篮事件
                event_dict.update({
                    "shot_result": getattr(event, "shot_result", None),
                    "shot_distance": getattr(event, "shot_distance", None),
                    "area": getattr(event, "area", None),
                    "area_detail": getattr(event, "area_detail", None),
                    "side": getattr(event, "side", None),
                    "is_field_goal": getattr(event, "is_field_goal", 1),
                    "qualifiers": getattr(event, "qualifiers", [])
                })

                # 助攻信息
                if hasattr(event, "assist_person_id") and event.assist_person_id:
                    event_dict["assist_person_id"] = event.assist_person_id
                    event_dict["assist_player_name_initial"] = getattr(event, "assist_player_name_initial", None)

                # 盖帽信息
                if hasattr(event, "block_person_id") and event.block_person_id:
                    event_dict["block_person_id"] = event.block_person_id
                    event_dict["block_player_name"] = getattr(event, "block_player_name", None)

            elif action_type == "freethrow":  # 罚球事件
                event_dict.update({
                    "shot_result": getattr(event, "shot_result", None),
                    "is_field_goal": getattr(event, "is_field_goal", 0),
                    "points_total": getattr(event, "points_total", None)
                })

            elif action_type == "rebound":  # 篮板事件
                event_dict.update({
                    "rebound_total": getattr(event, "rebound_total", None),
                    "rebound_defensive_total": getattr(event, "rebound_defensive_total", None),
                    "rebound_offensive_total": getattr(event, "rebound_offensive_total", None),
                    "shot_action_number": getattr(event, "shot_action_number", None)
                })

            elif action_type == "turnover":  # 失误事件
                event_dict.update({
                    "turnover_total": getattr(event, "turnover_total", None),
                    "descriptor": getattr(event, "descriptor", None)
                })

                # 抢断信息
                if hasattr(event, "steal_person_id") and event.steal_person_id:
                    event_dict["steal_person_id"] = event.steal_person_id
                    event_dict["steal_player_name"] = getattr(event, "steal_player_name", None)

            elif action_type == "foul":  # 犯规事件
                event_dict.update({
                    "descriptor": getattr(event, "descriptor", None)
                })

                # 被犯规信息
                if hasattr(event, "foul_drawn_person_id") and event.foul_drawn_person_id:
                    event_dict["foul_drawn_person_id"] = event.foul_drawn_person_id
                    event_dict["foul_drawn_player_name"] = getattr(event, "foul_drawn_player_name", None)

                # 裁判信息
                if hasattr(event, "official_id") and event.official_id:
                    event_dict["official_id"] = event.official_id

            elif action_type == "violation":  # 违例事件
                if hasattr(event, "official_id") and event.official_id:
                    event_dict["official_id"] = event.official_id

            elif action_type == "substitution":  # 换人事件
                event_dict.update({
                    "incoming_person_id": getattr(event, "incoming_person_id", None),
                    "incoming_player_name": getattr(event, "incoming_player_name", None),
                    "incoming_player_name_i": getattr(event, "incoming_player_name_i", None),
                    "outgoing_person_id": getattr(event, "outgoing_person_id", None),
                    "outgoing_player_name": getattr(event, "outgoing_player_name", None),
                    "outgoing_player_name_i": getattr(event, "outgoing_player_name_i", None)
                })

            elif action_type == "jumpball":  # 跳球事件
                event_dict.update({
                    "jump_ball_won_person_id": getattr(event, "jump_ball_won_person_id", None),
                    "jump_ball_won_player_name": getattr(event, "jump_ball_won_player_name", None),
                    "jump_ball_lost_person_id": getattr(event, "jump_ball_lost_person_id", None),
                    "jump_ball_lost_player_name": getattr(event, "jump_ball_lost_player_name", None),
                    "jump_ball_recovered_person_id": getattr(event, "jump_ball_recovered_person_id", None),
                    "jump_ball_recovered_name": getattr(event, "jump_ball_recovered_name", None)
                })

            events_data.append(event_dict)

        # 按照时间顺序排序（先按照节数，再按比赛时钟）
        events_data.sort(key=lambda x: (x["period"], x["clock"], x["action_number"]))

        return {
            "data": events_data,
            "count": len(events_data)
        }