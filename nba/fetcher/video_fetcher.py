from datetime import timedelta
from typing import Optional, Dict, Any, List
from config import NBAConfig
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig, RetryConfig
from nba.models.video_model import ContextMeasure


class VideoConfig:
    """视频数据配置"""
    BASE_URL: str = "https://stats.nba.com/stats"
    CACHE_PATH = NBAConfig.PATHS.VIDEOURL_CACHE_DIR
    CACHE_DURATION: timedelta = timedelta(days=100)

    # API端点
    ENDPOINTS: Dict[str, str] = {
        'VIDEO_DETAILS': 'videodetailsasset',
        'VIDEO_EVENTS': 'videoeventsasset'
    }

    # 请求头配置 - 只包含视频特有的请求头
    VIDEO_SPECIFIC_HEADERS: Dict[str, str] = {
        "host": "stats.nba.com",
        "origin": "https://www.nba.com",
        "referer": "https://www.nba.com/",
        "x-nba-stats-token": "true",
        "x-nba-stats-origin": "stats",
    }

    # 视频请求特有的批处理参数
    BATCH_CONFIG = {
        "batch_size": 5,  # 批量请求大小
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

    def build(self) -> Dict:
        """构建NBA API参数"""
        params = {
            'AheadBehind': '',
            'CFID': '',
            'CFPARAMS': '',
            'ClutchTime': '',
            'Conference': '',
            'ContextFilter': '',
            'ContextMeasure': self.context_measure.value if self.context_measure else '',
            'DateFrom': '',
            'DateTo': '',
            'Division': '',
            'EndPeriod': 0,
            'EndRange': 28800,
            'GROUP_ID': '',
            'GameEventID': '',
            'GameID': self.game_id,
            'GameSegment': '',
            'GroupID': '',
            'GroupMode': '',
            'GroupQuantity': 5,
            'LastNGames': 0,
            'LeagueID': "00",
            'Location': '',
            'Month': 0,
            'OnOff': '',
            'OppPlayerID': '',
            'OpponentTeamID': 0,
            'Outcome': '',
            'PORound': 0,
            'Period': 0,
            'PlayerID': int(self.player_id) if self.player_id else 0,
            'PlayerID1': '',
            'PlayerID2': '',
            'PlayerID3': '',
            'PlayerID4': '',
            'PlayerID5': '',
            'PlayerPosition': '',
            'PointDiff': '',
            'Position': '',
            'RangeType': 0,
            'RookieYear': '',
            'Season': self.season,
            'SeasonSegment': '',
            'SeasonType': self.season_type,
            'ShotClockRange': '',
            'StartPeriod': 0,
            'StartRange': 0,
            'StarterBench': '',
            'TeamID': int(self.team_id) if self.team_id else 0,
            'VsConference': '',
            'VsDivision': '',
            'VsPlayerID1': '',
            'VsPlayerID2': '',
            'VsPlayerID3': '',
            'VsPlayerID4': '',
            'VsPlayerID5': '',
            'VsTeamID': ''
        }
        return params


class VideoEventParams:
    """视频事件参数构建器

    用于获取具体事件视频，如特定进球的回放
    必需参数: game_id, event_id
    """

    def __init__(self, game_id: str, event_id: int):
        """初始化视频事件参数构建器

        Args:
            game_id: 比赛ID
            event_id: 事件ID
        """
        if not game_id:
            raise ValueError("game_id cannot be empty")
        if not str(event_id).isdigit() or event_id <= 0:
            raise ValueError("event_id must be a positive integer")

        self.game_id = game_id
        self.event_id = event_id

    def build(self) -> Dict:
        """构建参数字典"""
        return {
            'GameID': self.game_id,
            'GameEventID': self.event_id
        }


class VideoFetcher(BaseNBAFetcher):
    """视频数据获取器"""

    def __init__(self, custom_config: Optional[VideoConfig] = None,
                 disable_cache: bool = False):
        """初始化视频数据获取器

        Args:
            custom_config: 自定义配置
            disable_cache: 是否完全禁用缓存
        """
        self.video_config = custom_config or VideoConfig()

        # 配置缓存
        cache_duration = timedelta(seconds=0) if disable_cache else self.video_config.CACHE_DURATION
        cache_config = BaseCacheConfig(
            duration=cache_duration,
            root_path=self.video_config.CACHE_PATH
        )

        # 为视频请求创建特定的重试配置
        video_retry_config = RetryConfig(
            max_retries=3,
            base_delay=10.0,
            max_delay=180.0,
            backoff_factor=3.0,
            jitter_factor=0.15
        )

        # 创建基础请求配置
        base_config = BaseRequestConfig(
            base_url=self.video_config.BASE_URL,
            cache_config=cache_config,
            retry_config=video_retry_config,
            request_timeout=60
        )

        # 初始化基类
        super().__init__(base_config)

        # 自定义HTTP管理器参数
        self.http_manager.adjust_request_rate(
            min_delay=8.0,
            max_delay=15.0,
            min_interval=5.0
        )

        # 更新请求头
        self.http_manager.headers.update(self.video_config.VIDEO_SPECIFIC_HEADERS)

    def _build_cache_key(self, prefix: str, **kwargs) -> str:
        """构建一致的缓存键

        Args:
            prefix: 缓存键前缀
            **kwargs: 键值对参数

        Returns:
            str: 格式化的缓存键
        """
        # 过滤掉None值和空字符串
        parts = [prefix]
        for key, value in sorted(kwargs.items()):
            if value is not None and value != "":
                parts.append(f"{key}_{value}")

        return "_".join(parts)

    def _log_request_info(self, info_dict: Dict[str, Any], log_level: str = "info") -> None:
        """统一的请求信息日志记录

        Args:
            info_dict: 包含请求信息的字典
            log_level: 日志级别
        """
        info_str = ", ".join([f"{k}:{v}" for k, v in info_dict.items() if v])

        if log_level == "info":
            self.logger.info(f"请求信息: {info_str}")
        elif log_level == "debug":
            self.logger.debug(f"请求信息: {info_str}")
        elif log_level == "warning":
            self.logger.warning(f"请求信息: {info_str}")

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
            # 1. 构建和验证请求参数
            params = VideoRequestParams(
                game_id=game_id,
                player_id=player_id,
                team_id=team_id,
                context_measure=context_measure
            ).build()

            # 2. 构建请求信息字典（用于日志）
            request_info = {
                "比赛ID": game_id,
                "球员ID": player_id,
                "球队ID": team_id,
                "视频类型": context_measure.value if context_measure else None
            }

            self._log_request_info(request_info)

            # 3. 构建缓存键
            cache_key = self._build_cache_key(
                "game_video",
                game=game_id,
                player=player_id,
                team=team_id,
                type=context_measure.value if context_measure else None
            )

            # 4. 使用基类的fetch_data方法获取数据
            endpoint = self.video_config.ENDPOINTS['VIDEO_DETAILS']
            raw_data = self.fetch_data(
                endpoint=endpoint,
                params=params,
                cache_key=cache_key,
                force_update=force_refresh
            )

            # 5. 验证响应数据
            if not raw_data:
                self.logger.warning(f"获取的原始视频数据为空")
                return None

            if not isinstance(raw_data, dict) or not all(
                    k in raw_data for k in ['resource', 'parameters', 'resultSets']):
                self.logger.warning(f"原始数据结构不完整")
                return None

            # 6. 提取和验证视频URLs
            video_urls = raw_data.get('resultSets', {}).get('Meta', {}).get('videoUrls', [])
            url_count = len(video_urls)

            self.logger.info(f"视频数据获取成功，包含{url_count}个视频URL")

            if url_count == 0:
                self.logger.warning(f"比赛视频数据集为空，可能是比赛刚结束，或者是本场比赛没有该类型的数据")

            return raw_data

        except ValueError as e:
            self.logger.error(f"参数验证失败: {e}")
            return None
        except Exception as e:
            self.logger.error(f"获取视频链接数据失败: {e}")
            return None

    def get_event_video_url(self,
                            game_id: str,
                            event_id: int,
                            force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """获取特定事件的视频数据

        Args:
            game_id: 比赛ID
            event_id: 事件ID
            force_refresh: 是否强制刷新缓存

        Returns:
            Optional[Dict[str, Any]]: 视频事件数据，失败时返回None
        """
        try:
            # 1. 构建参数
            params = VideoEventParams(game_id=game_id, event_id=event_id).build()

            # 2. 构建日志信息
            request_info = {
                "比赛ID": game_id,
                "事件ID": event_id
            }
            self._log_request_info(request_info)

            # 3. 构建缓存键
            cache_key = self._build_cache_key("event_video", game=game_id, event=event_id)

            # 4. 使用基类的fetch_data方法获取数据
            endpoint = self.video_config.ENDPOINTS['VIDEO_EVENTS']
            raw_data = self.fetch_data(
                endpoint=endpoint,
                params=params,
                cache_key=cache_key,
                force_update=force_refresh
            )

            # 5. 验证响应数据
            if not raw_data:
                self.logger.warning(f"获取的事件视频数据为空，比赛ID: {game_id}, 事件ID: {event_id}")
                return None

            if not isinstance(raw_data, dict):
                self.logger.warning(f"响应数据格式不正确，比赛ID: {game_id}, 事件ID: {event_id}")
                return None

            # 6. 验证视频URLs是否存在
            video_urls = raw_data.get('resultSets', {}).get('Meta', {}).get('videoUrls', [])
            url_count = len(video_urls)

            self.logger.info(f"事件视频获取成功，包含{url_count}个视频URL")

            return raw_data

        except ValueError as e:
            self.logger.error(f"参数验证失败: {e}")
            return None
        except Exception as e:
            self.logger.error(f"获取事件视频数据失败，比赛ID: {game_id}, 事件ID: {event_id}, 错误: {e}")
            return None

    def batch_get_games_video_urls(self,
                                   game_ids: List[str],
                                   batch_size: Optional[int] = None) -> Dict[str, Any]:
        """批量获取多个比赛的视频数据

        Args:
            game_ids: 比赛ID列表
            batch_size: 批处理大小，不指定则使用配置中的默认值

        Returns:
            Dict[str, Any]: 以game_id为键的视频数据字典
        """
        # 使用配置中的默认批处理大小，或者使用传入的值
        if batch_size is None:
            batch_size = self.video_config.BATCH_CONFIG["batch_size"]

        self.logger.info(f"开始批量获取{len(game_ids)}个比赛的视频数据，批处理大小: {batch_size}")

        # 创建获取单个比赛视频的函数 - 不添加额外延迟，依赖基类的速率控制
        def fetch_single_game(game_id: str) -> Optional[Dict[str, Any]]:
            return self.get_game_video_urls(game_id=game_id)

        # 使用基类的批量获取方法
        results = self.batch_fetch(
            ids=game_ids,
            fetch_func=fetch_single_game,
            task_name="game_videos",
            batch_size=batch_size
        )

        self.logger.info(f"批量获取完成，成功获取{len(results)}/{len(game_ids)}个比赛的视频数据")
        return results

    def batch_get_video_events(self,
                               game_id: str,
                               event_ids: List[int],
                               batch_size: Optional[int] = None) -> Dict[str, Any]:
        """批量获取同一场比赛的多个事件视频

        Args:
            game_id: 比赛ID
            event_ids: 事件ID列表
            batch_size: 批处理大小，不指定则使用配置中的默认值

        Returns:
            Dict[str, Any]: 以event_id为键的视频数据字典
        """
        # 使用配置中的默认批处理大小
        if batch_size is None:
            batch_size = self.video_config.BATCH_CONFIG["batch_size"]

        self.logger.info(f"开始批量获取比赛(ID:{game_id})的{len(event_ids)}个事件视频，批处理大小: {batch_size}")

        # 创建获取单个事件视频的函数
        def fetch_single_event(event_id: int) -> Optional[Dict[str, Any]]:
            return self.get_event_video_url(game_id=game_id, event_id=event_id)

        # 使用基类的批量获取方法
        results = self.batch_fetch(
            ids=event_ids,
            fetch_func=fetch_single_event,
            task_name=f"game_{game_id}_events",
            batch_size=batch_size
        )

        self.logger.info(f"批量获取比赛事件视频完成，成功获取{len(results)}/{len(event_ids)}个事件")
        return results

    def clear_cache(self, prefix: Optional[str] = None, age: Optional[timedelta] = None):
        """清除缓存

        Args:
            prefix: 缓存前缀，如果为None则清除所有视频相关缓存
            age: 如果提供，只清除早于指定时间的缓存
        """
        if prefix:
            self.logger.info(f"正在清除'{prefix}'视频数据缓存")
            self.cache_manager.clear(prefix=f"{self.__class__.__name__.lower()}_{prefix}", age=age)
        else:
            self.logger.info("正在清除所有视频数据缓存")
            self.cache_manager.clear(prefix=self.__class__.__name__.lower(), age=age)

        self.logger.info("视频数据缓存已清除")