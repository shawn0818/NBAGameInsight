import time
import random
from datetime import timedelta
from typing import Optional, Dict, Any, List
from config import NBAConfig
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig, RetryConfig
from nba.models.video_model import ContextMeasure



class VideoConfig:
    """视频数据配置"""
    BASE_URL: str = "https://stats.nba.com/stats"
    CACHE_PATH = NBAConfig.PATHS.VIDEOURL_CACHE_DIR
    CACHE_DURATION: timedelta = timedelta(hours=1)

    # API端点
    ENDPOINTS: Dict[str, str] = {
        'VIDEO_DETAILS': 'videodetailsasset'
    }

    # 请求头配置 - 只包含视频特有的请求头
    VIDEO_SPECIFIC_HEADERS: Dict[str, str] = {
        "host": "stats.nba.com",
        "origin": "https://www.nba.com",
        "referer": "https://www.nba.com/",
    }

    # 视频请求特有的速率限制
    REQUEST_LIMITS = {
        "min_delay": 8.0,  # 最小请求间隔
        "max_delay": 15.0,  # 最大请求间隔
        "batch_size": 5,  # 批量请求大小
        "batch_interval": 10.0  # 批次间隔
    }


class VideoRequestParams:
    """视频查询参数构建器

    参数组合规则：
    1. 只传入game_id: 获取比赛全部视频  #目前没有FGM参数不返回数据了2025/03/20
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

    def build(self) -> Dict:
        """构建NBA API参数"""
        params = {
            'LeagueID': "00",
            'Season': self.season,
            'SeasonType': self.season_type,
            'TeamID': int(self.team_id) if self.team_id else 0,
            'PlayerID': int(self.player_id) if self.player_id else 0,
            'GameID': self.game_id,
            'ContextMeasure': self.context_measure.value if self.context_measure else '',
            'Outcome': '',  # 使用空字符串而不是None
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
            'EndRange': 31800,  # 更新为31800
            "GroupQuantity": 5,
            "PORound": 0,
            'ContextFilter': '',
            'OppPlayerID': ''
        }

        # 直接返回参数字典，不做转换处理
        return params

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
            # 创建零持续时间的缓存配置（实际禁用缓存）
            cache_config = BaseCacheConfig(
                duration=timedelta(seconds=0),
                root_path=self.video_config.CACHE_PATH
            )
        else:
            cache_config = BaseCacheConfig(
                duration=self.video_config.CACHE_DURATION,
                root_path=self.video_config.CACHE_PATH
            )

        # 为视频请求创建特定的重试配置
        video_retry_config = RetryConfig(
            max_retries=3,  # 减少最大重试次数
            base_delay=10.0,  # 增加基础延迟
            max_delay=180.0,  # 增加最大延迟
            backoff_factor=3.0,  # 增加退避因子
            jitter_factor=0.15  # 增加抖动因子
        )

        # 创建基础请求配置，并传入视频特定的重试配置
        base_config = BaseRequestConfig(
            base_url=self.video_config.BASE_URL,
            cache_config=cache_config,
            retry_config=video_retry_config,
            request_timeout=60  # 增加视频请求超时时间
        )

        # 初始化基类
        super().__init__(base_config)

        # 配置视频特定的请求限制
        self._configure_video_rate_limits()

        # 更新请求头（只添加视频特有的头）
        self.http_manager.headers.update(self.video_config.VIDEO_SPECIFIC_HEADERS)

    def _configure_video_rate_limits(self):
        """配置视频请求的特定限制"""
        # 设置更严格的间隔时间
        self.http_manager._min_delay = self.video_config.REQUEST_LIMITS["min_delay"]
        self.http_manager._max_delay = self.video_config.REQUEST_LIMITS["max_delay"]
        self.http_manager.min_request_interval = self.video_config.REQUEST_LIMITS["min_delay"]

    def _make_video_request(self, endpoint: str, params: Dict[str, str], force_refresh: bool = False) -> Optional[Dict]:
        """专用于视频请求的方法，带有额外限制"""
        # 在请求前添加额外随机延迟
        time.sleep(random.uniform(1.0, 3.0))

        # 使用原有fetch_data方法
        raw_data = self.fetch_data(
            endpoint=endpoint,
            params=params,
            force_update=force_refresh,
            # 可以为视频请求添加特定的缓存标识
            cache_status_key="video"
        )

        # 请求后额外延迟
        time.sleep(random.uniform(2.0, 4.0))

        return raw_data

    def get_game_video_urls(self,
                            game_id: str,
                            context_measure: Optional[ContextMeasure] = None,
                            player_id: Optional[int] = None,
                            team_id: Optional[int] = None,
                            force_refresh: bool = False) -> Optional[Dict[str, Any]]:
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

            # 使用端点和参数调用特定的视频请求方法
            endpoint = self.video_config.ENDPOINTS['VIDEO_DETAILS']

            # 使用专用视频请求方法
            raw_data = self._make_video_request(
                endpoint=endpoint,
                params=params,
                force_refresh=force_refresh
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

    def batch_get_games_video_urls(self, game_ids: List[str], batch_size: int = None) -> Dict[str, Any]:
        """批量获取多个比赛的视频数据

        Args:
            game_ids: 比赛ID列表
            batch_size: 批处理大小，不指定则使用配置中的默认值

        Returns:
            Dict[str, Any]: 以game_id为键的视频数据字典
        """
        # 使用配置中的默认批处理大小，或者使用传入的值（但不超过配置的限制）
        if batch_size is None:
            batch_size = self.video_config.REQUEST_LIMITS["batch_size"]
        else:
            batch_size = min(batch_size, self.video_config.REQUEST_LIMITS["batch_size"])

        self.logger.info(f"开始批量获取{len(game_ids)}个比赛的视频数据，批处理大小: {batch_size}")

        # 创建获取单个比赛视频的函数
        def fetch_single_game(game_id: str) -> Optional[Dict[str, Any]]:
            result = self.get_game_video_urls(game_id=game_id)
            # 每次请求后添加额外等待，减轻服务器负担
            batch_interval = self.video_config.REQUEST_LIMITS["batch_interval"]
            time.sleep(random.uniform(batch_interval * 0.8, batch_interval * 1.2))
            return result

        # 使用基类的批量获取方法
        results = self.batch_fetch(
            ids=game_ids,
            fetch_func=fetch_single_game,
            task_name="game_videos",
            batch_size=batch_size
        )

        self.logger.info(f"批量获取完成，成功获取{len(results)}/{len(game_ids)}个比赛的视频数据")
        return results

    def clear_cache(self):
        """清除缓存"""
        self.logger.info("正在清除视频数据缓存")
        if hasattr(self, 'cache_manager') and self.cache_manager:
            self.cache_manager.clear(prefix=self.__class__.__name__.lower())
            self.logger.info("视频数据缓存已清除")
        else:
            self.logger.info("没有缓存需要清除")