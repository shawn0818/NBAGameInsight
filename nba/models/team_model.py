from typing import Optional
from pathlib import Path
import pandas as pd
from pydantic import BaseModel
from functools import lru_cache
from config.nba_config import NBAConfig

class TeamProfile(BaseModel):
    """球队基本信息模型"""
    team_id: Optional[int] = None
    abbreviation: Optional[str] = None
    nickname: Optional[str] = None
    city:  Optional[str] = None
    arena: Optional[str] = None
    arena_capacity: Optional[int] = None
    year_founded: Optional[int] = None
    owner: Optional[str] = None
    general_manager: Optional[str] = None
    head_coach: Optional[str] = None
    
    @property
    def full_name(self) -> str:
        """获取球队全名"""
        return f"{self.city} {self.nickname}"
    
    @classmethod
    @lru_cache(maxsize=None)
    def get_teams_data(cls) -> pd.DataFrame:
        """加载并缓存球队数据"""
        csv_path = Path(NBAConfig.PATHS.DATA_DIR) / 'nba_team_profile.csv'
        print(f"Loading data from: {csv_path}")
        df = pd.read_csv(csv_path)
        # 去除重复行
        df = df.drop_duplicates(subset=['TEAM_ID'], keep='first')
        df = df.set_index('TEAM_ID')
        print(f"Loaded {len(df)} unique teams")
        return df
    
    @classmethod
    def from_id(cls, team_id: int) -> Optional['TeamProfile']:
        """通过ID获取球队信息"""
        try:
            df = cls.get_teams_data()
            if team_id not in df.index:
                print(f"Team ID {team_id} not found in index")
                return None
                
            row = df.loc[team_id]
            print(f"Found team: {row['NICKNAME_x']} ({row['ABBREVIATION']})")
            
            return cls(
                team_id=team_id,
                abbreviation=str(row['ABBREVIATION']),
                nickname=str(row['NICKNAME_x']),
                city=str(row['CITY_x']),
                arena=str(row['ARENA']),
                arena_capacity=int(row['ARENACAPACITY']) if pd.notna(row['ARENACAPACITY']) else None,
                year_founded=int(row['YEARFOUNDED_x']),
                owner=str(row['OWNER']) if pd.notna(row['OWNER']) else None,
                general_manager=str(row['GENERALMANAGER']) if pd.notna(row['GENERALMANAGER']) else None,
                head_coach=str(row['HEADCOACH']) if pd.notna(row['HEADCOACH']) else None
            )
        except Exception as e:
            import traceback
            print(f"Error loading team data: {e}")
            print("Traceback:", traceback.format_exc())
            return None
    
    @classmethod
    def from_name(cls, team_name: str) -> Optional['TeamProfile']:
        """通过名称获取球队信息"""
        team_name = team_name.lower()
        print(f"\nLooking for team name: {team_name}")
        df = cls.get_teams_data()
        
        # 尝试不同的匹配方式
        for _, row in df.iterrows():
            if (team_name == str(row['ABBREVIATION']).lower() or
                team_name == str(row['NICKNAME_x']).lower() or
                team_name == f"{row['CITY_x']} {row['NICKNAME_x']}".lower()):
                return cls.from_id(int(row.name))
        
        print("No matching teams found")
        return None
    
    @classmethod
    def get_team_id(cls, team_name: str) -> Optional[int]:
        """通过名称获取球队ID"""
        team = cls.from_name(team_name)
        return team.team_id if team else None

    def get_logo_path(self) -> Optional[Path]:
        """获取球队logo路径"""
        logo_path = Path(NBAConfig.PATHS.DATA_DIR) / "nba-team-logo" / f"{self.abbreviation} logo.png"
        return logo_path if logo_path.exists() else None