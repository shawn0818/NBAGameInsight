from datetime import timedelta
from typing import Optional, Dict, Any
from functools import lru_cache
from config.nba_config import NBAConfig
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from nba.models.video_model import ContextMeasure


class VideoConfig:
    """视频数据配置"""
    BASE_URL: str = "https://stats.nba.com/stats"
    CACHE_PATH = NBAConfig.PATHS.VIDEOURL_CACHE_DIR
    CACHE_DURATION: timedelta = timedelta(seconds=3600)

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
    """视频查询参数构建器"""

    def __init__(
            self,
            game_id: str,
            player_id: Optional[int] = None,
            team_id: Optional[int] = None,
            context_measure: ContextMeasure = ContextMeasure.FGM,
            season: str = "2024-25",
            season_type: str = "Regular Season"
    ):
        if not game_id:
            raise ValueError("game_id cannot be empty")
        if not isinstance(context_measure, ContextMeasure):
            raise ValueError(f"Invalid context_measure: {context_measure}")
        if player_id and not str(player_id).isdigit():
            raise ValueError("player_id must be a positive integer")
        if team_id and not str(team_id).isdigit():
            raise ValueError("team_id must be a positive integer")

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
            'ContextMeasure': self.context_measure.value,
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

    def __init__(self, custom_config: Optional[VideoConfig] = None):
        """初始化视频数据获取器"""
        self.video_config = custom_config or VideoConfig()

        # 配置缓存
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

    @staticmethod
    def _validate_cached_data(data: Optional[Dict]) -> bool:
        """验证缓存数据是否有效"""
        if not data:
            return False
        try:
            video_urls = data.get('resultSets', {}).get('Meta', {}).get('videoUrls', [])
            return bool(video_urls)  # 如果 videoUrls 不为空，返回 True
        except (AttributeError, TypeError):
            # 如果数据结构不正确（例如缺少 resultSets 或 Meta），也认为是无效的
            return False

    @lru_cache(maxsize=100)
    def get_game_videos_raw(self,
                            game_id: str,
                            context_measure: ContextMeasure = ContextMeasure.FGM,
                            player_id: Optional[int] = None,
                            team_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """获取比赛视频数据"""
        try:
            # 构建和验证请求参数
            params = VideoRequestParams(
                game_id=game_id,
                player_id=str(player_id) if player_id else None,
                team_id=str(team_id) if team_id else None,
                context_measure=context_measure
            ).build()

            # 构建缓存键
            cache_key_parts = list(filter(None, [
                'video',
                game_id,
                str(player_id) if player_id else None,
                str(team_id) if team_id else None,
                context_measure.value
            ]))
            cache_key = '_'.join(cache_key_parts)

            # 尝试从缓存获取数据
            cached_data = self.cache_manager.get(
                prefix=self.__class__.__name__.lower(),
                identifier=cache_key
            )

            # 验证缓存数据
            if cached_data and VideoFetcher._validate_cached_data(cached_data):
                self.logger.info(f"从缓存中获取比赛(ID:{game_id})的视频数据")
                return cached_data

            # 缓存未命中或数据无效，发起网络请求
            self.logger.info(f"正在获取比赛(ID:{game_id})的视频数据")
            data = self.fetch_data(
                endpoint=self.video_config.ENDPOINTS['VIDEO_DETAILS'],
                params=params,
                cache_key=cache_key
            )

            # 验证响应数据
            if data and VideoFetcher._validate_cached_data(data):  # 添加对新获取数据的验证
                self.logger.info(f"成功获取包含视频链接数据")
                return data
            else:
                self.logger.warning(f"获取的视频链接数据验证失败或为空")
                return None


        except ValueError as e:
            self.logger.error(f"参数验证失败: {e}")
            return None
        except Exception as e:
            self.logger.error(f"获取视频链接数据失败: {e}")
            return None



    def cleanup_cache(self, game_id: Optional[str] = None, older_than: Optional[timedelta] = None) -> None:
        """清理缓存数据"""
        try:
            prefix = self.__class__.__name__.lower()
            if game_id:
                cache_key = f"video_{game_id}"
                self.logger.info(f"正在清理比赛(ID:{game_id})的视频缓存")
                self.cache_manager.clear(prefix=prefix, identifier=cache_key)
            else:
                cache_age = older_than or self.video_config.CACHE_DURATION
                self.logger.info(f"正在清理{cache_age}之前的视频缓存")
                self.cache_manager.clear(prefix=prefix, age=cache_age)
        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")

    def clear_cache(self):
        """清除LRU缓存"""
        self.get_game_videos_raw.cache_clear()