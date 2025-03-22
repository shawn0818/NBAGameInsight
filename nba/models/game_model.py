from datetime import datetime
from enum import IntEnum, Enum
from typing import Optional, List, Dict, Any, Literal
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
    LEAGUE_SUSPENSION = "INACTIVE_LEAGUE_SUSPENSION"


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

    @property
    def has_played(self) -> bool:
        """判断球员是否参与过本场比赛

        Returns:
            bool: 参与比赛返回True，否则返回False
        """
        return self.played == "1"

    @property
    def is_on_court(self) -> bool:
        """判断球员是否当前在场上

        Returns:
            bool: 在场上返回True，否则返回False
        """
        return self.on_court == "1"

    @property
    def is_starter(self) -> bool:
        """判断球员是否是首发

        Returns:
            bool: 是首发返回True，否则返回False
        """
        return self.starter == "1"

    @property
    def playing_status(self) -> str:
        """获取球员上场状态的描述

        Returns:
            str: 球员上场状态的中文描述
        """
        if not self.has_played:
            if self.not_playing_reason:
                reason = self.not_playing_reason.value
                return f"未上场 - {reason}"
            return "未上场"
        elif self.is_starter:
            return "首发" + ("，场上" if self.is_on_court else "，场下")
        else:
            return "替补" + ("，场上" if self.is_on_court else "，场下")


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
# 5. 双方本赛季交手信息模型
# ===========================

class TeamRivalryInfo(BaseModel):
    """球队本赛季交手历史信息"""
    game_id: str = Field(..., description="当前比赛ID", alias="gameId")

    # 基本对阵信息
    home_team_id: int = Field(..., description="主队ID", alias="homeTeamId")
    visitor_team_id: int = Field(..., description="客队ID", alias="visitorTeamId")
    game_date_est: datetime = Field(..., description="比赛日期(EST)", alias="gameDateEst")

    # 赛季系列赛信息
    home_team_wins: int = Field(..., description="主队在本赛季常规赛双方交手中的胜场数", alias="homeTeamWins")
    home_team_losses: int = Field(..., description="主队在本赛季常规赛双方交手中的负场数", alias="homeTeamLosses")
    series_leader: Optional[str] = Field(None, description="本赛季常规赛双方交手中的领先方", alias="seriesLeader")

    # 上次交手信息
    last_game_id: str = Field(..., description="上次比赛ID", alias="lastGameId")
    last_game_date_est: datetime = Field(..., description="上次比赛日期(EST)", alias="lastGameDateEst")
    last_game_home_team_id: int = Field(..., description="上次比赛主队ID", alias="lastGameHomeTeamId")
    last_game_home_team_city: str = Field(..., description="上次比赛主队城市", alias="lastGameHomeTeamCity")
    last_game_home_team_name: str = Field(..., description="上次比赛主队名称", alias="lastGameHomeTeamName")
    last_game_home_team_abbreviation: str = Field(..., description="上次比赛主队缩写",
                                                  alias="lastGameHomeTeamAbbreviation")
    last_game_home_team_points: int = Field(..., description="上次比赛主队得分", alias="lastGameHomeTeamPoints")
    last_game_visitor_team_id: int = Field(..., description="上次比赛客队ID", alias="lastGameVisitorTeamId")
    last_game_visitor_team_city: str = Field(..., description="上次比赛客队城市", alias="lastGameVisitorTeamCity")
    last_game_visitor_team_name: str = Field(..., description="上次比赛客队名称", alias="lastGameVisitorTeamName")
    last_game_visitor_team_abbreviation: str = Field(..., description="上次比赛客队缩写",
                                                     alias="lastGameVisitorTeamAbbreviation")
    last_game_visitor_team_points: int = Field(..., description="上次比赛客队得分", alias="lastGameVisitorTeamPoints")

    model_config = ConfigDict(from_attributes=True)

    # 一些辅助属性和方法
    @property
    def last_meeting_winner(self) -> str:
        """获取上次比赛的获胜方"""
        return "home" if self.last_game_home_team_points > self.last_game_visitor_team_points else "visitor"

    @property
    def season_status(self) -> str:
        """获取本赛季常规赛双方交手状态的描述"""
        if self.home_team_wins == self.home_team_losses:
            return "平局"
        return f"{self.series_leader}领先"  # 保留原变量名，但意义是常规赛领先方

    def get_last_meeting_summary(self) -> Dict[str, Any]:
        """获取上次比赛的简要概述"""
        winner = self.last_meeting_winner
        winner_name = self.last_game_home_team_name if winner == "home" else self.last_game_visitor_team_name
        winner_points = self.last_game_home_team_points if winner == "home" else self.last_game_visitor_team_points
        loser_name = self.last_game_visitor_team_name if winner == "home" else self.last_game_home_team_name
        loser_points = self.last_game_visitor_team_points if winner == "home" else self.last_game_home_team_points

        return {
            "date": self.last_game_date_est.strftime("%Y-%m-%d"),
            "winner": {
                "name": winner_name,
                "points": winner_points
            },
            "loser": {
                "name": loser_name,
                "points": loser_points
            },
            "summary": f"{winner_name} {winner_points}-{loser_points} {loser_name}"
        }

    def get_series_summary(self, home_team_name: str, away_team_name: str) -> Dict[str, Any]:
        """获取双方本赛季常规赛交手的简要概述"""
        return {
            "home_team": home_team_name,
            "visitor_team": away_team_name,
            "home_team_wins": self.home_team_wins,
            "home_team_losses": self.home_team_losses,
            "series_leader": self.series_leader,  # 变量名保持一致，意义为常规赛领先方
            "series_summary": f"{home_team_name} {self.home_team_wins}-{self.home_team_losses} {away_team_name}"
        }

# ===========================
# 6. 比赛核心数据模型
# ===========================

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
    rivalry_info: Optional[TeamRivalryInfo] = Field(None, description="球队对抗历史信息", alias="rivalryInfo")

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='after')
    def validate_beijing_time(self):
        """确保北京时间始终基于UTC时间计算"""
        if hasattr(self, 'game_time_utc') and self.game_time_utc:
            self.game_time_beijing = TimeHandler.to_beijing(self.game_time_utc)
        return self


class PlayByPlay(BaseModel):
    """比赛回放数据"""
    game: Dict[str, Any] = Field(..., description="比赛信息")
    meta: Optional[Dict[str, Any]] = Field(None, description="元数据")
    actions: List[BaseEvent] = Field(default_factory=list, description="所有事件列表")

    model_config = ConfigDict(from_attributes=True)

# ===========================
# 7. 完整的Game模型，并提供基本的数据接口
# ===========================


class Game(BaseModel):
    """完整比赛数据模型"""
    meta: Dict[str, Any] = Field(..., description="元数据")
    game_data: GameData = Field(..., description="比赛数据", alias="gameData")
    play_by_play: Optional[PlayByPlay] = Field(None, description="比赛回放数据", alias="playByPlay")

    model_config = ConfigDict(from_attributes=True)

    #=====model层提供清晰的数据访问接口,类似于数据库的功能，service层可以直接调用这些接口，代码更简洁=========

    def game_now(self) -> Dict[str, Any]:
        """获取比赛当前状态的快照信息"""
        result = {"status": self.game_data.game_status}

        # 获取基本信息
        home_team = self.game_data.home_team
        away_team = self.game_data.away_team

        # 根据比赛状态返回不同信息
        if self.game_data.game_status == GameStatusEnum.NOT_STARTED:
            # 未开始：返回比赛时间和地点
            result.update({
                "status_text": "未开始",
                "beijing_time": self.game_data.game_time_beijing.strftime("%Y-%m-%d %H:%M:%S"),
                "arena": {
                    "name": self.game_data.arena.arena_name,
                    "city": self.game_data.arena.arena_city,
                    "state": self.game_data.arena.arena_state,
                    "country": self.game_data.arena.arena_country
                },
                "teams": {
                    "home": {
                        "id": home_team.team_id,
                        "name": home_team.team_name,
                        "tricode": home_team.team_tricode
                    },
                    "away": {
                        "id": away_team.team_id,
                        "name": away_team.team_name,
                        "tricode": away_team.team_tricode
                    }
                }
            })

        elif self.game_data.game_status == GameStatusEnum.IN_PROGRESS:
            # 进行中：返回当前节次、时间、比分和场上球员
            # 获取当前场上球员 - 使用模型属性方法
            active_home_players = [
                {
                    "id": p.person_id,
                    "name": p.name,
                    "jersey": p.jersey_num,
                    "position": p.position,
                    "playing_status": p.playing_status  # 使用模型属性
                }
                for p in home_team.players if p.is_on_court  # 使用模型属性
            ]

            active_away_players = [
                {
                    "id": p.person_id,
                    "name": p.name,
                    "jersey": p.jersey_num,
                    "position": p.position,
                    "playing_status": p.playing_status  # 使用模型属性
                }
                for p in away_team.players if p.is_on_court  # 使用模型属性
            ]

            result.update({
                "status_text": "进行中",
                "period": self.game_data.period,
                "clock": self.game_data.game_clock,
                "score": {
                    "home": home_team.score,
                    "away": away_team.score
                },
                "teams": {
                    "home": {
                        "id": home_team.team_id,
                        "name": home_team.team_name,
                        "tricode": home_team.team_tricode,
                        "timeouts_remaining": home_team.timeouts_remaining,
                        "active_players": active_home_players
                    },
                    "away": {
                        "id": away_team.team_id,
                        "name": away_team.team_name,
                        "tricode": away_team.team_tricode,
                        "timeouts_remaining": away_team.timeouts_remaining,
                        "active_players": active_away_players
                    }
                }
            })

        elif self.game_data.game_status == GameStatusEnum.FINISHED:
            # 已结束：返回比赛时间和最终比分
            result.update({
                "status_text": "已结束",
                "beijing_time": self.game_data.game_time_beijing.strftime("%Y-%m-%d %H:%M:%S"),
                "duration": self.game_data.duration,
                "attendance": self.game_data.attendance,
                "teams": {
                    "home": {
                        "id": home_team.team_id,
                        "name": home_team.team_name,
                        "tricode": home_team.team_tricode,
                        "score": home_team.score
                    },
                    "away": {
                        "id": away_team.team_id,
                        "name": away_team.team_name,
                        "tricode": away_team.team_tricode,
                        "score": away_team.score
                    }
                },
                "winner": "home" if home_team.score > away_team.score else "away"
            })

        return result

    def get_season_matchup_history(self) -> Dict[str, Any]:
        """获取球队本赛季常规赛过往交手信息"""
        # 首先检查必要数据是否存在
        if not self.game_data or not hasattr(self.game_data, 'rivalry_info') or not self.game_data.rivalry_info:
            return {"available": False}

        try:
            rivalry = self.game_data.rivalry_info
            home_team_name = self.game_data.home_team.team_name
            away_team_name = self.game_data.away_team.team_name

            # 获取上次交手信息
            try:
                last_meeting = rivalry.get_last_meeting_summary()
            except (AttributeError, ValueError, KeyError) as e:
                logger.warning(f"获取上次交手信息失败: {str(e)}")
                last_meeting = {
                    "date": "未知",
                    "winner": {"name": "未知", "points": 0},
                    "loser": {"name": "未知", "points": 0},
                    "summary": "数据不完整"
                }

            # 获取常规赛交手信息
            try:
                season_record = rivalry.get_series_summary(home_team_name, away_team_name)
                # 修改键名以避免使用"系列赛"
                season_record["season_summary"] = season_record.pop("series_summary")
                season_record["leading_team"] = season_record.pop("series_leader")
            except (AttributeError, ValueError, KeyError) as e:
                logger.warning(f"获取常规赛交手记录失败: {str(e)}")
                season_record = {
                    "home_team": home_team_name,
                    "visitor_team": away_team_name,
                    "home_team_wins": 0,
                    "home_team_losses": 0,
                    "leading_team": "未知",
                    "season_summary": "数据不完整"
                }

            # 生成对抗历史的文本描述
            context_parts = []
            if "未知" not in last_meeting["date"]:
                context_parts.append(f"两队上次交手是在{last_meeting['date']}，结果是{last_meeting['summary']}。")

            if season_record["leading_team"] and "未知" not in season_record["leading_team"]:
                context_parts.append(f"本赛季常规赛交手记录为{season_record['season_summary']}，"
                                     f"{('目前' + season_record['leading_team'] + '领先') if season_record['leading_team'] else '双方战成平手'}。")

            return {
                "available": True,
                "last_meeting": last_meeting,
                "season_record": season_record,
                "context": " ".join(context_parts) if context_parts else "两队历史交手数据暂不完整。"
            }

        except Exception as e:
            logger.warning(f"获取球队对抗历史信息时出错: {str(e)}")
            return {"available": False}

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