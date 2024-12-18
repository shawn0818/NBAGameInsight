# tests/test_players.py

import pytest
from nba.models.players import Player, PlayerBasicInfo, PlayerStatistics, PlayerNameMapping

def test_player_from_dict():
    data = {
        'status': 'active',
        'order': 1,
        'personId': 'P1',
        'jerseyNum': '23',
        'position': 'SG',
        'starter': True,
        'oncourt': True,
        'played': True,
        'statistics': {
            'assists': 5,
            'blocks': 1,
            'fieldGoalsAttempted': 10,
            'fieldGoalsMade': 5,
            'fieldGoalsPercentage': 50.0,
            # 其他统计数据...
        },
        'name': '张三',
        'nameI': 'Z.S.',
        'firstName': '张',
        'familyName': '三',
    }
    player = Player.from_dict(data)
    assert player.player_status == 'active'
    assert player.player_order == 1
    assert player.player_id == 'P1'
    assert player.player_jersey_number == '23'
    assert player.player_position == 'SG'
    assert player.player_starter is True
    assert player.player_oncourt is True
    assert player.player_played is True
    assert player.player_statistics.assists == 5
    assert player.player_statistics.blocks == 1
    assert player.player_name == '张三'
    assert player.full_name == '张 三'

def test_player_name_mapping():
    # 创建 PlayerBasicInfo 实例
    player_basic = PlayerBasicInfo(
        person_id='P1',
        name='张三',
        position='SG',
        height='6-5',
        weight='210',
        jersey='23',
        team_info={
            'id': 'T1',
            'city': '上海',
            'name': '龙队',
            'abbreviation': 'SHL'
        },
        draft_info={
            'year': '2020',
            'round': '1',
            'number': '15'
        },
        career_info={
            'from': '2020',
            'to': '2023'
        },
        college='上海大学',
        country='中国'
    )
    mapping = PlayerNameMapping()
    mapping.add_player(player_basic)
    assert mapping.get_player_id('张三') == 'P1'
    assert mapping.get_player_id('张') == 'P1'
    assert mapping.get_player_name('P1') == '张三'
