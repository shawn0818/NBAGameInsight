from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, List, Any, Union
from datetime import datetime
from enum import Enum

class GameStatus(Enum):
    """比赛状态枚举"""
    NOT_STARTED = 1
    IN_PROGRESS = 2
    FINISHED = 3

class BasePydanticModel(BaseModel):
    """基础 Pydantic 模型"""
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True

class PlayerStatistics(BasePydanticModel):
    """球员统计数据"""
    assists: Optional[int] = Field(0)
    blocks: Optional[int] = Field(0)
    blocksReceived: Optional[int] = Field(0)
    fieldGoalsAttempted: Optional[int] = Field(0)
    fieldGoalsMade: Optional[int] = Field(0)
    fieldGoalsPercentage: Optional[float] = Field(0.0)
    foulsOffensive: Optional[int] = Field(0)
    foulsDrawn: Optional[int] = Field(0)
    foulsPersonal: Optional[int] = Field(0)
    foulsTechnical: Optional[int] = Field(0)
    freeThrowsAttempted: Optional[int] = Field(0)
    freeThrowsMade: Optional[int] = Field(0)
    freeThrowsPercentage: Optional[float] = Field(0.0)
    points: Optional[int] = Field(0)
    reboundsDefensive: Optional[int] = Field(0)
    reboundsOffensive: Optional[int] = Field(0)
    reboundsTotal: Optional[int] = Field(0)
    steals: Optional[int] = Field(0)
    turnovers: Optional[int] = Field(0)
    minutes: Optional[str] = Field("")
    minutesCalculated: Optional[str] = Field("")
    threePointersAttempted: Optional[int] = Field(0)
    threePointersMade: Optional[int] = Field(0)
    threePointersPercentage: Optional[float] = Field(0.0)
    twoPointersAttempted: Optional[int] = Field(0)
    twoPointersMade: Optional[int] = Field(0)
    twoPointersPercentage: Optional[float] = Field(0.0)

class Player(BasePydanticModel):
    """球员信息"""
    status: Optional[str] = Field(None)
    order: Optional[int] = Field(None)
    personId: Optional[int] = Field(None)
    jerseyNum: Optional[str] = Field(None)
    position: Optional[str] = Field(None)
    starter: Optional[str] = Field("0")
    oncourt: Optional[str] = Field("0")
    played: Optional[str] = Field("0")
    statistics: Optional[PlayerStatistics] = Field(None)
    name: Optional[str] = Field(None)
    nameI: Optional[str] = Field(None)
    firstName: Optional[str] = Field(None)
    familyName: Optional[str] = Field(None)
    notPlayingReason: Optional[str] = Field(None)
    notPlayingDescription: Optional[str] = Field(None)

    @validator('personId')
    def validate_person_id(cls, v):
        """确保 personId 是整数"""
        if v is not None and not isinstance(v, int):
            try:
                return int(v)
            except (ValueError, TypeError):
                raise ValueError('personId must be an integer')
        return v

class Period(BasePydanticModel):
    """比赛节次信息"""
    period: int = Field(...)
    periodType: str = Field(...)
    score: int = Field(...)

class TeamStats(BasePydanticModel):
    """球队统计数据"""
    teamId: int = Field(...)
    teamName: str = Field(...)
    teamCity: str = Field(...)
    teamTricode: str = Field(...)
    score: Optional[int] = Field(None)
    inBonus: Optional[str] = Field(None)
    timeoutsRemaining: Optional[int] = Field(None)
    periods: Optional[List[Period]] = Field([])
    players: Optional[List[Player]] = Field([])
    statistics: Optional[Dict[str, Any]] = Field(None)

class Arena(BasePydanticModel):
    """比赛场馆信息"""
    arenaId: int = Field(...)
    arenaName: str = Field(...)
    arenaCity: str = Field(...)
    arenaState: str = Field(...)
    arenaCountry: str = Field(...)
    arenaTimezone: str = Field(...)

class Official(BasePydanticModel):
    """裁判信息"""
    personId: int = Field(...)
    name: str = Field(...)
    nameI: str = Field(...)
    firstName: str = Field(...)
    familyName: str = Field(...)
    jerseyNum: str = Field(...)
    assignment: str = Field(...)

class GameData(BasePydanticModel):
    """比赛基本信息"""
    gameId: str = Field(...)
    gameTimeLocal: datetime = Field(...)
    gameTimeUTC: datetime = Field(...)
    gameTimeHome: datetime = Field(...)
    gameTimeAway: datetime = Field(...)
    gameEt: datetime = Field(...)
    duration: int = Field(...)
    gameCode: str = Field(...)
    gameStatusText: str = Field(...)
    gameStatus: int = Field(...)
    regulationPeriods: int = Field(...)
    period: int = Field(...)
    gameClock: str = Field(...)
    attendance: int = Field(...)
    sellout: str = Field(...)
    arena: Arena = Field(...)
    officials: List[Official] = Field(...)
    homeTeam: TeamStats = Field(...)
    awayTeam: TeamStats = Field(...)

class Game(BasePydanticModel):
    """完整比赛数据模型"""
    meta: Dict[str, Any] = Field(...)
    game: GameData = Field(...)

    @property
    def status(self) -> GameStatus:
        """获取比赛状态"""
        return GameStatus(self.game.gameStatus)

    @property
    def is_finished(self) -> bool:
        """判断比赛是否结束"""
        return self.status == GameStatus.FINISHED

    @property
    def is_in_progress(self) -> bool:
        """判断比赛是否正在进行"""
        return self.status == GameStatus.IN_PROGRESS

    def get_team_stats(self, is_home: bool = True) -> Optional[TeamStats]:
        """安全地获取球队统计数据"""
        try:
            return self.game.homeTeam if is_home else self.game.awayTeam
        except AttributeError:
            return None

    def get_player_stats(self, person_id: Union[str, int], is_home: bool = True) -> Optional[PlayerStatistics]:
        """获取指定球员的统计数据
        
        Args:
            person_id: 球员ID（可以是字符串或整数）
            is_home: 是否是主队
        
        Returns:
            Optional[PlayerStatistics]: 球员统计数据，如果未找到返回 None
        """
        team = self.get_team_stats(is_home)
        if not team or not team.players:
            return None

        try:
            person_id_int = int(person_id)
        except (ValueError, TypeError):
            return None

        for player in team.players:
            if player.personId == person_id_int:
                return player.statistics

        return None

    def get_team_score(self, is_home: bool = True) -> int:
        """获取球队得分"""
        team = self.get_team_stats(is_home)
        return team.score if team else 0

    def get_player_by_id(self, person_id: Union[str, int], is_home: bool = True) -> Optional[Player]:
        """根据ID获取球员信息
        
        Args:
            person_id: 球员ID（可以是字符串或整数）
            is_home: 是否是主队
            
        Returns:
            Optional[Player]: 球员信息，如果未找到返回 None
        """
        team = self.get_team_stats(is_home)
        if not team or not team.players:
            return None

        try:
            person_id_int = int(person_id)
        except (ValueError, TypeError):
            return None

        for player in team.players:
            if player.personId == person_id_int:
                return player

        return None

    def get_period_scores(self, is_home: bool = True) -> List[int]:
        """获取每节得分
        
        Args:
            is_home: 是否是主队
            
        Returns:
            List[int]: 每节得分列表
        """
        team = self.get_team_stats(is_home)
        if not team or not team.periods:
            return []
        return [period.score for period in team.periods]