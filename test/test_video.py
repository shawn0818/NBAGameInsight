"""测试视频处理相关功能"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from nba.services.game_video_service import GameVideoService
from nba.models.video_model import VideoAsset, ContextMeasure

@pytest.fixture
def video_service():
    return GameVideoService()

class TestVideoService:
    def test_get_game_videos(self, video_service):
        """测试获取比赛视频"""
        with patch('nba.parser.video_query_parser.NBAVideoProcessor.get_videos_by_query') as mock_get:
            mock_videos = {'1': Mock(spec=VideoAsset)}
            mock_get.return_value = mock_videos
            
            videos = video_service.get_game_videos(
                game_id="0022300001",
                context_measure=ContextMeasure.FGM
            )
            assert videos == mock_videos

    def test_download_video(self, video_service):
        """测试下载视频"""
        mock_asset = Mock(spec=VideoAsset)
        mock_asset.qualities = {'hd': Mock(url='http://example.com/video.mp4')}
        
        with patch('utils.video_downloader.VideoDownloader.download') as mock_download:
            mock_download.return_value = True
            result = video_service.download_video(
                video_asset=mock_asset,
                output_path=Path("test.mp4")
            )
            assert result is not None
            mock_download.assert_called_once()