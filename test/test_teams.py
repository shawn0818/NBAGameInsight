"""测试球队相关功能"""

import pytest
from nba.models.team_model import get_team_id

def test_get_team_id():
    """测试球队ID获取"""
    # 测试完整名称
    assert get_team_id("Los Angeles Lakers")[0] == 1610612747
    
    # 测试缩写
    assert get_team_id("LAL")[0] == 1610612747
    
    # 测试模糊匹配
    assert get_team_id("lakers")[0] == 1610612747
    
    # 测试不存在的球队
    assert get_team_id("Invalid Team") is None