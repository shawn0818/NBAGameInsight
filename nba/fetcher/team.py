from pathlib import Path
import pandas as pd
from nba.models.team_model import TeamProfile
from config.nba_config import NBAConfig

def load_team_data() -> pd.DataFrame:
    """加载球队CSV数据并返回DataFrame"""
    csv_path = Path(NBAConfig.PATHS.DATA_DIR) / 'nba_team_profile.csv'
    df = pd.read_csv(csv_path)
    return df.set_index('TEAM_ID')

def parse_team_row(team_id: int, row: pd.Series) -> TeamProfile:
    """将DataFrame的一行数据解析为TeamProfile对象"""
    return TeamProfile(
        team_id=team_id,
        abbreviation=row['ABBREVIATION'],
        nickname=row['NICKNAME_x'],
        city=row['CITY_x'],
        arena=row['ARENA'],
        arena_capacity=row['ARENACAPACITY'],
        year_founded=row['YEARFOUNDED_x'],
        owner=row['OWNER'],
        general_manager=row['GENERALMANAGER'],
        head_coach=row['HEADCOACH']
    )