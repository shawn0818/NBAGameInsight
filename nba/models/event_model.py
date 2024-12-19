from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

# 1. 定义枚举类

class ShotSubType(str, Enum):
    """投篮子类型"""
    JUMP_SHOT = "Jump Shot"    # 跳投
    LAYUP = "Layup"            # 上篮
    HOOK = "Hook"              # 勾手
    DUNK = "DUNK"              # 扣篮


class ShotQualifier(str, Enum):
    """投篮限定词"""
    POINTS_IN_PAINT = "pointsinthepaint"  # 在油漆区内得分
    SECOND_CHANCE = "2ndchance"           # 二次进攻机会
    FAST_BREAK = "fastbreak"              # 快攻
    FROM_TURNOVER = "fromturnover"        # 来自对方失误


class FreeThrowSubType(str, Enum):
    """罚球子类型"""
    ONE_OF_ONE = "1 of 1"    # 一罚
    ONE_OF_TWO = "1 of 2"    # 两罚第一次
    TWO_OF_TWO = "2 of 2"    # 两罚第二次


class ReboundSubType(str, Enum):
    """篮板子类型"""
    OFFENSIVE = "offensive"   # 进攻篮板
    DEFENSIVE = "defensive"   # 防守篮板


class ReboundQualifier(str, Enum):
    """篮板限定词"""
    TEAM = "team"             # 团队篮板


class FoulSubType(str, Enum):
    """犯规子类型"""
    OFFENSIVE = "offensive"   # 进攻犯规
    PERSONAL = "personal"     # 个人犯规


class FoulQualifier(str, Enum):
    """犯规限定词"""
    ONE_FREE_THROW = "1freethrow"    # 一次罚球机会
    TWO_FREE_THROW = "2freethrow"    # 两次罚球机会
    SHOOTING = "shooting"            # 投篮犯规
    IN_PENALTY = "inpenalty"         # 在加罚状态
    LOOSE_BALL = "loose ball"        # 争抢球犯规


class TurnoverSubType(str, Enum):
    """失误子类型"""
    LOST_BALL = "lost ball"                # 丢球
    BAD_PASS = "bad pass"                  # 传球失误
    OFFENSIVE_FOUL = "offensive foul"      # 进攻犯规
    OUT_OF_BOUNDS = "out-of-bounds"        # 出界
    SHOT_CLOCK = "shot clock"              # 24秒违例


class ViolationSubType(str, Enum):
    """违例子类型"""
    KICKED_BALL = "kicked ball"                  # 踢球违例
    DEFENSIVE_GOALTENDING = "defensive goaltending"  # 防守干扰球违例


class EventType(str, Enum):
    """比赛事件类型枚举"""
    # 得分事件 (Scoring Events)
    FIELD_GOAL_2PT = "2pt"             # 两分球 - 可以是跳投、上篮、勾手或扣篮
    FIELD_GOAL_3PT = "3pt"             # 三分球 - 通常是跳投
    FREE_THROW = "freethrow"           # 罚球 - 分为一罚、两罚第一次、两罚第二次

    # 攻防事件 (Action Events)
    BLOCK = "block"                    # 盖帽
    STEAL = "steal"                    # 抢断
    REBOUND = "rebound"                # 篮板 - 分为进攻篮板和防守篮板
    TURNOVER = "turnover"              # 失误 - 包括丢球、传球失误、进攻犯规等

    # 比赛控制事件 (Game Control Events)
    JUMP_BALL = "jumpball"             # 跳球 - 通常发生在节开始或争球情况
    TIMEOUT = "timeout"                # 暂停 - 可以是强制性的或球队主动请求
    SUBSTITUTION = "substitution"      # 换人 - 包括换上和换下
    PERIOD = "period"                  # 比赛节次 - 包括开始和结束
    GAME = "game"                      # 比赛状态 - 如比赛结束

    # 判罚事件 (Official Events)
    FOUL = "foul"                      # 犯规 - 包括个人犯规、进攻犯规等
    VIOLATION = "violation"            # 违例 - 如踢球、防守干扰球等

    @classmethod
    def is_field_goal(cls, event_type: 'EventType') -> bool:
        """判断是否为投篮(不含罚球)"""
        return event_type in [cls.FIELD_GOAL_2PT, cls.FIELD_GOAL_3PT]

    @classmethod
    def is_scoring_event(cls, event_type: 'EventType') -> bool:
        """判断是否为得分事件(包括罚球)"""
        return event_type in [cls.FIELD_GOAL_2PT, cls.FIELD_GOAL_3PT, cls.FREE_THROW]

    @classmethod
    def is_official_event(cls, event_type: 'EventType') -> bool:
        """判断是否为需要裁判判罚的事件"""
        return event_type in [cls.FOUL, cls.VIOLATION]

    @classmethod
    def get_valid_subtypes(cls, event_type: 'EventType') -> List[str]:
        """获取事件类型对应的有效子类型"""
        subtype_map = {
            cls.FIELD_GOAL_2PT: [st.value for st in ShotSubType],  # 两分球可以是任何投篮类型
            cls.FIELD_GOAL_3PT: [ShotSubType.JUMP_SHOT.value],     # 三分球通常只是跳投
            cls.FREE_THROW: [st.value for st in FreeThrowSubType], # 罚球的三种情况
            cls.REBOUND: [st.value for st in ReboundSubType],      # 进攻篮板和防守篮板
            cls.FOUL: [st.value for st in FoulSubType],            # 犯规的不同类型
            cls.TURNOVER: [st.value for st in TurnoverSubType],    # 失误的各种情况
            cls.VIOLATION: [st.value for st in ViolationSubType]   # 违例的类型
        }
        return subtype_map.get(event_type, [])


# 2. 定义辅助模型

class Score(BaseModel):
    """比分信息"""
    home: int = Field(..., description="主队当前得分")
    away: int = Field(..., description="客队当前得分")
    points: int = Field(0, description="当前事件得分（如投篮命中得2分或3分）")

    @property
    def difference(self) -> int:
        """计算主队和客队的分差（正数表示主队领先）"""
        return self.home - self.away


class PlayerRef(BaseModel):
    """球员引用信息，用于在事件中识别和引用球员"""
    person_id: int = Field(..., description="球员的唯一标识符")
    full_name: str = Field(..., description="球员的完整姓名")
    name_initial: str = Field(..., description="球员姓名缩写（如L. James）")
    jersey_num: Optional[str] = Field(None, description="球员的球衣号码")


# 3. 定义 Event 模型

class Event(BaseModel):
    """单个比赛事件"""
    actionNumber: Optional[int] = Field(None, description="事件编号")
    clock: Optional[str] = Field(None, description="比赛时钟")
    timeActual: Optional[datetime] = Field(None, description="事件发生的实际时间")
    period: Optional[int] = Field(None, description="比赛节次")
    periodType: Optional[str] = Field(None, description="比赛节类型（如REGULAR）")
    teamId: Optional[int] = Field(None, description="事件涉及的球队ID")
    teamTricode: Optional[str] = Field(None, description="事件涉及的球队三字母缩写")
    actionType: Optional[str] = Field(None, description="事件类型")
    subType: Optional[str] = Field(None, description="事件子类型")
    descriptor: Optional[str] = Field(None, description="事件描述符")
    qualifiers: Optional[List[str]] = Field(None, description="事件限定词列表")
    personId: Optional[int] = Field(None, description="涉及的球员ID")
    x: Optional[float] = Field(None, description="事件发生的X坐标")
    y: Optional[float] = Field(None, description="事件发生的Y坐标")
    area: Optional[str] = Field(None, description="事件区域")
    areaDetail: Optional[str] = Field(None, description="事件区域详细信息")
    side: Optional[str] = Field(None, description="事件发生的场地侧边")
    shotDistance: Optional[float] = Field(None, description="投篮距离")
    possession: Optional[int] = Field(None, description="拥有球权的球队ID")
    scoreHome: Optional[int] = Field(None, description="主队当前得分")
    scoreAway: Optional[int] = Field(None, description="客队当前得分")
    edited: Optional[datetime] = Field(None, description="数据编辑时间")
    orderNumber: Optional[int] = Field(None, description="事件顺序编号")
    isTargetScoreLastPeriod: Optional[bool] = Field(None, description="是否是上一节的目标得分")
    xLegacy: Optional[Any] = Field(None, description="遗留的X坐标（可能为int或None）")
    yLegacy: Optional[Any] = Field(None, description="遗留的Y坐标（可能为int或None）")
    isFieldGoal: Optional[int] = Field(None, description="是否为投篮（1是，0否）")
    shotResult: Optional[str] = Field(None, description="投篮结果（如Missed）")
    shotActionNumber: Optional[int] = Field(None, description="投篮动作编号")
    reboundTotal: Optional[int] = Field(None, description="篮板总数")
    reboundDefensiveTotal: Optional[int] = Field(None, description="防守篮板总数")
    reboundOffensiveTotal: Optional[int] = Field(None, description="进攻篮板总数")
    description: Optional[str] = Field(None, description="事件描述")
    playerName: Optional[str] = Field(None, description="球员姓名")
    playerNameI: Optional[str] = Field(None, description="球员姓名缩写")
    personIdsFilter: Optional[List[int]] = Field(None, description="涉及的球员ID列表")


class PlayByPlay(BaseModel):
    """比赛回放数据"""
    meta: Optional[Dict[str, Any]] = Field(None, description="元数据")
    game: Dict[str, Any] = Field(..., description="比赛信息，包含actions列表")

    @property
    def actions(self) -> List[Event]:
        """获取事件列表"""
        if 'actions' not in self.game:
            return []
        return [Event.parse_obj(action) for action in self.game['actions']]
