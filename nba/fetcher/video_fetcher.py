from datetime import timedelta
from typing import Optional, Dict, Any, List
import json
import logging
from config.nba_config import NBAConfig
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from nba.models.video_model import ContextMeasure, VideoResponse


class VideoConfig:
    """视频数据配置"""
    BASE_URL: str = "https://stats.nba.com/stats"
    CACHE_PATH = NBAConfig.PATHS.VIDEOURL_CACHE_DIR
    CACHE_DURATION: timedelta = timedelta(hours=1)

    # 备用URL配置
    FALLBACK_URLS: Dict[str, str] = {
        "https://cdn.nba.com/static/json": "https://nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/NBA",
    }

    # API端点
    ENDPOINTS: Dict[str, str] = {
        'VIDEO_DETAILS': 'videodetailsasset'
    }

    # 请求头配置
    DEFAULT_HEADERS: Dict[str, str] = {
        'accept': '*/*',
        'accept-language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'accept-encoding': 'gzip, deflate, br, zstd',
        'connection': 'keep-alive',
        'dnt': '1',
        'host': 'stats.nba.com',
    }


class VideoRequestParams:
    """视频查询参数构建器

    参数组合规则：
    1. 只传入game_id: 获取比赛全部视频
    2. game_id + ContextMeasure: 获取特定类型的视频(如投篮)
    3. game_id + team_id: 等同于只传game_id
    4. game_id + team_id + ContextMeasure: 获取特定球队的特定类型视频
    5. game_id + player_id: 获取球员在该场比赛的所有视频
    6. game_id + player_id + ContextMeasure: 获取球员特定类型的视频
    """

    def __init__(
            self,
            game_id: str,
            player_id: Optional[int] = None,
            team_id: Optional[int] = None,
            context_measure: Optional[ContextMeasure] = None,
            season: str = "2024-25",
            season_type: str = "Regular Season"
    ):
        # 基础参数验证
        if not game_id:
            raise ValueError("game_id cannot be empty")
        if player_id and not str(player_id).isdigit():
            raise ValueError("player_id must be a positive integer")
        if team_id and not str(team_id).isdigit():
            raise ValueError("team_id must be a positive integer")
        if context_measure and not isinstance(context_measure, ContextMeasure):
            raise ValueError(f"Invalid context_measure: {context_measure}")

        self.game_id = game_id
        self.player_id = player_id
        self.team_id = team_id
        self.context_measure = context_measure
        self.season = season
        self.season_type = season_type

    def build(self) -> Dict[str, Any]:
        """构建NBA API参数"""
        return {
            'LeagueID': "00",
            'Season': self.season,
            'SeasonType': self.season_type,
            'TeamID': int(self.team_id) if self.team_id else 0,
            'PlayerID': int(self.player_id) if self.player_id else 0,
            'GameID': self.game_id,
            'ContextMeasure': self.context_measure.value if self.context_measure else '',
            'Outcome': '',
            'Location': '',
            'Month': 0,
            'SeasonSegment': '',
            'DateFrom': '',
            'DateTo': '',
            'OpponentTeamID': 0,
            'VsConference': '',
            'VsDivision': '',
            'Position': '',
            'RookieYear': '',
            'GameSegment': '',
            'Period': 0,
            'LastNGames': 0,
            'ClutchTime': '',
            'AheadBehind': '',
            'PointDiff': '',
            'RangeType': 0,
            'StartPeriod': 0,
            'EndPeriod': 0,
            'StartRange': 0,
            'EndRange': 28800,
            'ContextFilter': '',
            'OppPlayerID': ''
        }


class VideoFetcher(BaseNBAFetcher):
    """视频数据获取器"""

    def __init__(self, custom_config: Optional[VideoConfig] = None, disable_cache: bool = False):
        """初始化视频数据获取器

        Args:
            custom_config: 自定义配置
            disable_cache: 是否完全禁用缓存
        """
        self.video_config = custom_config or VideoConfig()

        # 配置缓存
        if disable_cache:
            cache_config = None  # 完全禁用缓存
        else:
            cache_config = BaseCacheConfig(
                duration=self.video_config.CACHE_DURATION,
                root_path=self.video_config.CACHE_PATH
            )

        # 创建基础请求配置
        base_config = BaseRequestConfig(
            base_url=self.video_config.BASE_URL,
            cache_config=cache_config
        )

        # 初始化基类
        super().__init__(base_config)

        # 更新请求头
        self.http_manager.headers.update(self.video_config.DEFAULT_HEADERS)

    def get_game_video_urls(self,
                            game_id: str,
                            context_measure: Optional[ContextMeasure] = None,
                            player_id: Optional[int] = None,
                            team_id: Optional[int] = None,
                            force_refresh: bool = True) -> Optional[Dict[str, Any]]:
        """获取比赛视频原始数据

        Args:
            game_id: 比赛ID
            context_measure: 上下文度量类型（如投篮、助攻等）
            player_id: 球员ID
            team_id: 球队ID
            force_refresh: 是否强制刷新缓存

        Returns:
            Optional[Dict[str, Any]]: 原始响应数据，获取失败则返回None
        """
        try:
            # 构建和验证请求参数
            params = VideoRequestParams(
                game_id=game_id,
                player_id=player_id,
                team_id=team_id,
                context_measure=context_measure
            ).build()

            request_info = f"比赛(ID:{game_id})"
            if player_id:
                request_info += f", 球员ID:{player_id}"
            if team_id:
                request_info += f", 球队ID:{team_id}"
            if context_measure:
                request_info += f", 类型:{context_measure.value}"

            self.logger.info(f"正在获取{request_info}的视频数据")

            # 获取数据，可选强制刷新
            raw_data = self.fetch_data(
                endpoint=self.video_config.ENDPOINTS['VIDEO_DETAILS'],
                params=params,
                force_update=force_refresh
            )

            # 简单数据有效性检查
            if not raw_data:
                self.logger.warning(f"获取的原始视频数据为空")
                return None

            # 检查原始数据是否包含基本结构
            if not isinstance(raw_data, dict) or not all(
                    k in raw_data for k in ['resource', 'parameters', 'resultSets']):
                self.logger.warning(f"原始数据结构不完整")
                return None

            # 检查是否有视频URLs
            video_urls = raw_data.get('resultSets', {}).get('Meta', {}).get('videoUrls', [])
            url_count = len(video_urls)

            self.logger.info(f"成功获取{request_info}的原始视频数据，包含{url_count}个视频URL")

            if url_count == 0:
                self.logger.warning(f"比赛视频数据集为空，可能是比赛刚结束，或者是本场比赛没有该类型的数据")

            # 返回原始数据，交由上层服务使用解析器处理
            return raw_data

        except ValueError as e:
            self.logger.error(f"参数验证失败: {e}")
            return None
        except Exception as e:
            self.logger.error(f"获取视频链接数据失败: {e}")
            return None

    def clear_cache(self):
        """清除缓存"""
        self.logger.info("正在清除视频数据缓存")
        if hasattr(self, 'cache_manager') and self.cache_manager:
            self.cache_manager.clear(prefix=self.__class__.__name__.lower())
            self.logger.info("视频数据缓存已清除")
        else:
            self.logger.info("没有缓存需要清除")