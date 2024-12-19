import unittest
import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from nba.models.team_model import TeamProfile

class TestTeam(unittest.TestCase):
    """测试球队相关功能"""
    
    def setUp(self):
        """测试初始化"""
        print("\nSetting up test...")
        self.lakers_id = 1610612747
        self.warriors_id = 1610612744
        self.test_teams = TeamProfile.get_teams_data()
        print(f"Loaded {len(self.test_teams)} teams")
    
    def test_team_from_id(self):
        """测试通过ID获取球队"""
        print("\nTesting team lookup by ID...")
        # 测试有效ID
        lakers = TeamProfile.from_id(self.lakers_id)
        print(f"Found team: {lakers.full_name if lakers else 'None'}")
        self.assertIsNotNone(lakers)
        self.assertEqual(lakers.team_id, self.lakers_id)
        self.assertEqual(lakers.city, "Los Angeles")
        self.assertEqual(lakers.nickname, "Lakers")
        self.assertEqual(lakers.abbreviation, "LAL")
        
        # 测试无效ID
        invalid_team = TeamProfile.from_id(99999)
        print(f"Invalid team test result: {invalid_team}")
        self.assertIsNone(invalid_team)
    
    def test_team_from_name(self):
        """测试通过名称获取球队"""
        print("\nTesting team lookup by name...")
        # 测试不同形式的名称
        for name in ["Warriors", "GSW", "Golden State Warriors"]:
            print(f"Looking up team: {name}")
            warriors = TeamProfile.from_name(name)
            print(f"Found team: {warriors.full_name if warriors else 'None'}")
            self.assertIsNotNone(warriors)
            self.assertEqual(warriors.team_id, self.warriors_id)
        
        # 测试无效名称
        print("Testing invalid team name...")
        invalid_team = TeamProfile.from_name("Invalid Team")
        print(f"Invalid team test result: {invalid_team}")
        self.assertIsNone(invalid_team)
    
    def test_team_properties(self):
        """测试球队属性"""
        print("\nTesting team properties...")
        lakers = TeamProfile.from_id(self.lakers_id)
        self.assertIsNotNone(lakers)
        
        print(f"Team name: {lakers.full_name}")
        print(f"Abbreviation: {lakers.abbreviation}")
        print(f"Arena: {lakers.arena}")
        
        # 测试logo路径
        logo_path = lakers.get_logo_path()
        print(f"Logo path: {logo_path}")
        self.assertIsInstance(logo_path, Path)

if __name__ == '__main__':
    print("Starting team tests...")
    unittest.main(verbosity=2)