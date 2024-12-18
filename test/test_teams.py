# tests/test_teams.py

import pytest
from nba.models.teams import Team, TeamInfo, TeamStatistics
from nba.config.nba_config import NBAConfig
from pathlib import Path
import pandas as pd

def test_team_from_dict():
    data = {
        'teamId': 'T1',
        'teamName': '龙队',
        'teamCity': '上海',
        'teamTricode': 'SHL',
        'score': 102,
        'periods': [
            {'period': 1, 'periodType': 'REGULAR', 'score': 25},
            {'period': 2, 'periodType': 'REGULAR', 'score': 30}
        ],
        'timeoutsRemaining': 3,
        'inBonus': True
    }
    team = Team.from_dict(data)
    assert team.team_id == 'T1'
    assert team.team_name == '龙队'
    assert team.team_city == '上海'
    assert team.team_tricode == 'SHL'
    assert team.team_score == 102
    assert len(team.team_periods) == 2
    assert team.team_timeouts_remaining == 3
    assert team.team_in_bonus is True
    assert team.full_name == '上海 龙队'

def test_team_info():
    # 模拟加载球队数据
    data = {
        'TEAM_ID': ['T1', 'T2'],
        'ABBREVIATION': ['SHL', 'BKN'],
        'NICKNAME_x': ['龙', '篮网'],
        'CITY_x': ['上海', '纽约'],
        'ARENA': ['上海体育馆', '巴克莱中心'],
        'ARENACAPACITY': [18000, 19000],
        'OWNER': ['张老板', '布朗'],
        'GENERALMANAGER': ['李经理', '迈克尔'],
        'HEADCOACH': ['王教练', '史蒂夫']
    }
    df = pd.DataFrame(data)
    csv_path = Path('/tmp/team_profile.csv')
    df.to_csv(csv_path, index=False)

    # 设置 NBAConfig
    NBAConfig.PATHS.DATA_DIR = Path('/tmp')

    team_info = TeamInfo()
    team_id = team_info.get_team_id('SHL')
    assert team_id == 'T1'

    team_id_nickname = team_info.get_team_id('篮网')
    assert team_id_nickname == 'T2'

    team_id_full = team_info.get_team_id('纽约 篮网')
    assert team_id_full == 'T2'

    team_logo_path = team_info.get_team_logo_path('SHL')
    assert team_logo_path == Path('/tmp/nba-team-logo/SHL logo.png')

    team_details = team_info.get_team_info('BKN')
    assert team_details['team_id'] == 'T2'
    assert team_details['abbreviation'] == 'BKN'
    assert team_details['nickname'] == '篮网'
    assert team_details['city'] == '纽约'
    assert team_details['arena'] == '巴克莱中心'
    assert team_details['arena_capacity'] == 19000
    assert team_details['owner'] == '布朗'
    assert team_details['general_manager'] == '迈克尔'
    assert team_details['head_coach'] == '史蒂夫'
    assert team_details['logo_path'] == Path('/tmp/nba-team-logo/BKN logo.png')
