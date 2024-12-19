import unittest
import sys
from pathlib import Path

# 将项目根目录添加到Python路径
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from nba.models.team_model import TeamProfile

class TestTeam(unittest.TestCase):
    """测试球队相关功能"""
    
    def setUp(self):
        """测试初始化"""
        self.lakers_id = 1610612747
        self.warriors_id = 1610612744
        self.celtics_id = 1610612738
    
    def test_team_id_mapping(self):
        """测试球队名称到ID的映射（核心功能）"""
        # 测试缩写
        self.assertEqual(TeamProfile.get_team_id("LAL"), self.lakers_id)
        self.assertEqual(TeamProfile.get_team_id("GSW"), self.warriors_id)
        self.assertEqual(TeamProfile.get_team_id("BOS"), self.celtics_id)
        
        # 测试昵称
        self.assertEqual(TeamProfile.get_team_id("Lakers"), self.lakers_id)
        self.assertEqual(TeamProfile.get_team_id("Warriors"), self.warriors_id)
        self.assertEqual(TeamProfile.get_team_id("Celtics"), self.celtics_id)
        
        # 测试全名
        self.assertEqual(TeamProfile.get_team_id("Los Angeles Lakers"), self.lakers_id)
        self.assertEqual(TeamProfile.get_team_id("Golden State Warriors"), self.warriors_id)
        self.assertEqual(TeamProfile.get_team_id("Boston Celtics"), self.celtics_id)
        
        # 测试大小写不敏感
        self.assertEqual(TeamProfile.get_team_id("lakers"), self.lakers_id)
        self.assertEqual(TeamProfile.get_team_id("WARRIORS"), self.warriors_id)
        self.assertEqual(TeamProfile.get_team_id("Boston CELTICS"), self.celtics_id)
        
        # 测试无效名称
        self.assertIsNone(TeamProfile.get_team_id("Invalid Team"))
        self.assertIsNone(TeamProfile.get_team_id(""))
        self.assertIsNone(TeamProfile.get_team_id("ABC"))
    
    def test_team_from_id(self):
        """测试通过ID获取球队"""
        # 测试有效ID
        lakers = TeamProfile.from_id(self.lakers_id)
        self.assertIsNotNone(lakers)
        self.assertEqual(lakers.team_id, self.lakers_id)
        self.assertEqual(lakers.city, "Los Angeles")
        self.assertEqual(lakers.nickname, "Lakers")
        self.assertEqual(lakers.abbreviation, "LAL")
        
        # 测试无效ID
        invalid_team = TeamProfile.from_id(99999)
        self.assertIsNone(invalid_team)
    
    def test_team_from_name(self):
        """测试通过名称获取球队完整信息"""
        # 测试不同形式的名称
        warriors = TeamProfile.from_name("Warriors")
        self.assertIsNotNone(warriors)
        self.assertEqual(warriors.team_id, self.warriors_id)
        self.assertEqual(warriors.city, "Golden State")
        self.assertEqual(warriors.nickname, "Warriors")
        
        celtics = TeamProfile.from_name("BOS")
        self.assertIsNotNone(celtics)
        self.assertEqual(celtics.team_id, self.celtics_id)
        self.assertEqual(celtics.abbreviation, "BOS")
        
        lakers = TeamProfile.from_name("Los Angeles Lakers")
        self.assertIsNotNone(lakers)
        self.assertEqual(lakers.team_id, self.lakers_id)
        self.assertEqual(lakers.full_name, "Los Angeles Lakers")
    
    def test_team_properties(self):
        """测试球队属性访问"""
        warriors = TeamProfile.from_id(self.warriors_id)
        self.assertIsNotNone(warriors)
        
        # 测试基本属性
        self.assertEqual(warriors.full_name, "Golden State Warriors")
        self.assertEqual(warriors.abbreviation, "GSW")
        self.assertIsInstance(warriors.year_founded, int)
        
        # 测试可选属性
        self.assertIsInstance(warriors.arena_capacity, (int, type(None)))
        self.assertIsInstance(warriors.owner, (str, type(None)))
        
        # 测试logo路径
        logo_path = warriors.get_logo_path()
        self.assertIsInstance(logo_path, Path)

if __name__ == '__main__':
    unittest.main(verbosity=2)