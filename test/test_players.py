"""测试球员相关功能"""

import pytest
from unittest.mock import patch
from nba.fetcher.player_fetcher import PlayerFetcher

class TestPlayerFetcher:
    def test_get_player_profile(self):
        """测试获取球员信息"""
        with patch('nba.fetcher.base_fetcher.BaseNBAFetcher.fetch_data') as mock_fetch:
            mock_fetch.return_value = {'players': []}
            
            fetcher = PlayerFetcher()
            data = fetcher.get_player_profile()
            assert data is not None
            mock_fetch.assert_called_once()