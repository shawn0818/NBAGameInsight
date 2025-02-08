from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class CommonPlayerInfo(BaseModel):
    """CommonPlayerInfo result set model"""
    person_id: int = Field(alias="PERSON_ID")
    first_name: str = Field(alias="FIRST_NAME")
    last_name: str = Field(alias="LAST_NAME")
    display_first_last: str = Field(alias="DISPLAY_FIRST_LAST")
    display_last_comma_first: str = Field(alias="DISPLAY_LAST_COMMA_FIRST")
    display_fi_last: str = Field(alias="DISPLAY_FI_LAST")
    player_slug: str = Field(alias="PLAYER_SLUG")
    birthdate: str = Field(alias="BIRTHDATE")
    school: Optional[str] = Field(alias="SCHOOL")
    country: str = Field(alias="COUNTRY")
    last_affiliation: str = Field(alias="LAST_AFFILIATION")
    height: str = Field(alias="HEIGHT")
    weight: str = Field(alias="WEIGHT")
    season_exp: int = Field(alias="SEASON_EXP")
    jersey: str = Field(alias="JERSEY")
    position: str = Field(alias="POSITION")
    rosterstatus: str = Field(alias="ROSTERSTATUS")
    games_played_current_season_flag: str = Field(alias="GAMES_PLAYED_CURRENT_SEASON_FLAG")
    team_id: int = Field(alias="TEAM_ID")
    team_name: str = Field(alias="TEAM_NAME")
    team_abbreviation: str = Field(alias="TEAM_ABBREVIATION")
    team_code: str = Field(alias="TEAM_CODE")
    team_city: str = Field(alias="TEAM_CITY")
    playercode: str = Field(alias="PLAYERCODE")
    from_year: int = Field(alias="FROM_YEAR")
    to_year: int = Field(alias="TO_YEAR")
    dleague_flag: str = Field(alias="DLEAGUE_FLAG")
    nba_flag: str = Field(alias="NBA_FLAG")
    games_played_flag: str = Field(alias="GAMES_PLAYED_FLAG")
    draft_year: str = Field(alias="DRAFT_YEAR")
    draft_round: str = Field(alias="DRAFT_ROUND")
    draft_number: str = Field(alias="DRAFT_NUMBER")
    greatest_75_flag: str = Field(alias="GREATEST_75_FLAG")


class PlayerHeadlineStats(BaseModel):
    """PlayerHeadlineStats result set model"""
    player_id: int = Field(alias="PLAYER_ID")
    player_name: str = Field(alias="PLAYER_NAME")
    time_frame: str = Field(alias="TimeFrame") # 注意 TimeFrame 字段的大小写
    pts: float = Field(alias="PTS")
    ast: float = Field(alias="AST")
    reb: float = Field(alias="REB")
    pie: float = Field(alias="PIE")


class AvailableSeason(BaseModel):
    """AvailableSeasons result set model"""
    season_id: str = Field(alias="SEASON_ID")


class PlayerInfo(BaseModel):
    """球员详细信息，包含多个 result set"""
    common_player_info: List[CommonPlayerInfo] = Field(alias="CommonPlayerInfo")
    player_headline_stats: List[PlayerHeadlineStats] = Field(alias="PlayerHeadlineStats")
    available_seasons: List[AvailableSeason] = Field(alias="AvailableSeasons")

    model_config = ConfigDict(populate_by_name=True)

    @property
    def full_name(self) -> str:
        """获取球员标准全名"""
        if self.common_player_info and self.common_player_info[0].first_name and self.common_player_info[0].last_name:
            player_info = self.common_player_info[0]
            return f"{player_info.first_name} {player_info.last_name}"
        return "Unknown Player"

    @property
    def headshot_url(self) -> str:
        """获取球员头像URL"""
        if self.common_player_info and self.common_player_info[0].person_id:
            player_info = self.common_player_info[0]
            return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_info.person_id}.png"
        return "" # 或者返回默认头像URL
