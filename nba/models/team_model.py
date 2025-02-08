from typing import Optional,  List,  Union
from pydantic import BaseModel, Field


class TeamSocialSite(BaseModel):
    """球队社交媒体信息"""
    account_type: str
    website_link: str

class TeamAward(BaseModel):
    """球队荣誉信息

    Attributes:
        year_awarded: 获奖年份
        opposite_team: 对手球队名称（如果适用）
    """
    year_awarded: int
    opposite_team: Optional[str] = None

class TeamHofPlayer(BaseModel):
    """名人堂球员信息

    Attributes:
        player_id: 球员ID
        player: 球员姓名
        position: 场上位置
        jersey: 球衣号码
        seasons_with_team: 效力球队的赛季
        year: 入选名人堂年份
    """
    player_id: Optional[int]
    player: str
    position: Optional[str]
    jersey: Optional[Union[str, int]]
    seasons_with_team: Optional[str]
    year: int

class TeamRetiredPlayer(BaseModel):
    """退役球衣球员信息

    Attributes:
        player_id: 球员ID
        player: 球员姓名
        position: 场上位置
        jersey: 退役的球衣号码
        seasons_with_team: 效力球队的赛季
        year: 球衣退役年份
    """
    player_id: Optional[int]
    player: str
    position: Optional[str]
    jersey: Optional[Union[str, int]]
    seasons_with_team: Optional[str]
    year: int

class TeamProfile(BaseModel):
    """球队详细信息模型

    包含球队的完整信息，包括：
    1. 基础信息（队名、城市、场馆等）
    2. 管理层信息（老板、总经理、主教练）
    3. 历史荣誉（总冠军、分区冠军等）
    4. 名人堂成员
    5. 退役球衣

    所有属性都是只读的，创建后不可修改。
    """
    # 基础信息
    team_id: Optional[int] = None
    abbreviation: Optional[str] = None
    nickname: Optional[str] = None
    year_founded: Optional[int] = None
    city: Optional[str] = None
    arena: Optional[str] = None
    arena_capacity: Optional[str] = None
    owner: Optional[str] = None
    general_manager: Optional[str] = None
    head_coach: Optional[str] = None
    dleague_affiliation: Optional[str] = None

    # 扩展信息
    championships: List[TeamAward] = Field(default_factory=list)
    conference_titles: List[TeamAward] = Field(default_factory=list)
    division_titles: List[TeamAward] = Field(default_factory=list)
    hof_players: List[TeamHofPlayer] = Field(default_factory=list)
    retired_numbers: List[TeamRetiredPlayer] = Field(default_factory=list)

    class Config:
        """Pydantic配置"""
        frozen = True

    @property
    def full_name(self) -> str:
        """获取球队全名（城市+昵称）"""
        return f"{self.city} {self.nickname}" if self.city else self.nickname

    @property
    def total_championships(self) -> int:
        """获取球队总冠军数"""
        return len(self.championships)

    @property
    def latest_championship(self) -> Optional[TeamAward]:
        """获取最近一次冠军信息"""
        return max(self.championships, key=lambda x: x.year_awarded) if self.championships else None



