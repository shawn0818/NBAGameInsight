from typing import Dict, Optional, Any, List
import random
import time
from datetime import timedelta
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config import NBAConfig


class ScheduleConfig:
    """赛程数据配置"""
    SCHEDULE_URL: str = "https://stats.nba.com/stats/scheduleleaguev2"
    CACHE_PATH = NBAConfig.PATHS.SCHEDULE_CACHE_DIR
    CACHE_DURATION: timedelta = timedelta(days=1)  # 赛程数据每天更新
    START_SEASON = "1970-71"  # 最早有数据统计的赛季
    CURRENT_SEASON = "2024-25"  # 当前赛季
    MIN_REQUEST_DELAY = 3  # 最小请求延迟（秒）
    MAX_REQUEST_DELAY = 10  # 最大请求延迟（秒）


class ScheduleFetcher(BaseNBAFetcher):

    def __init__(self, custom_config: Optional[ScheduleConfig] = None):
        """初始化赛程数据获取器"""
        self.schedule_config = custom_config or ScheduleConfig()

        cache_config = BaseCacheConfig(
            duration=self.schedule_config.CACHE_DURATION,
            root_path=self.schedule_config.CACHE_PATH
        )

        base_config = BaseRequestConfig(
            cache_config=cache_config,
            request_timeout=60  # 增加超时时间因为数据量大
        )

        super().__init__(base_config)

    def _apply_random_delay(self):
        """
        应用随机延迟以降低被API限流的风险
        延迟时间范围为MIN_REQUEST_DELAY到MAX_REQUEST_DELAY秒
        """
        delay = random.uniform(
            self.schedule_config.MIN_REQUEST_DELAY,
            self.schedule_config.MAX_REQUEST_DELAY
        )
        self.logger.info(f"应用随机延迟: {delay:.2f}秒")
        time.sleep(delay)

    def get_schedule_by_season(self, season: str, force_update: bool = False,
                               apply_delay: bool = True) -> Optional[Dict[str, Any]]:
        """
        获取指定赛季的赛程数据

        Args:
            season: 赛季字符串，如"2024-25"
            force_update: 是否强制更新缓存
            apply_delay: 是否在请求后应用随机延迟

        Returns:
            赛程数据字典
        """
        try:
            cache_key = f"schedule_{season}"
            if not force_update:
                cached_data = self.cache_manager.get(
                    prefix=self.__class__.__name__.lower(),
                    identifier=cache_key
                )
                if cached_data is not None:
                    self.logger.info(f"从缓存获取赛季{season}数据成功")
                    return cached_data

            # 构建请求参数
            params = {
                "LeagueID": "00",  # NBA
                "Season": season
            }

            self.logger.info(f"正在请求赛季{season}的数据...")
            response = self.http_manager.make_request(
                url=self.schedule_config.SCHEDULE_URL,
                method='GET',
                params=params
            )

            # 应用随机延迟，降低被限流风险
            if apply_delay:
                self._apply_random_delay()

            if not response:
                self.logger.error(f"请求赛季{season}失败，返回None")
                return None

            # 验证数据基本结构
            if not isinstance(response, dict) or 'leagueSchedule' not in response:
                self.logger.error(f"赛季{season}数据格式错误")
                return None

            # 更新缓存
            try:
                self.cache_manager.set(
                    prefix=self.__class__.__name__.lower(),
                    identifier=cache_key,
                    data=response
                )
                self.logger.info(f"赛季{season}更新缓存成功")
            except Exception as e:
                self.logger.error(f"赛季{season}更新缓存失败: {e}")

            return response

        except Exception as e:
            self.logger.error(f"获取赛季{season}赛程数据失败: {e}", exc_info=True)
            return None

    def get_schedules_for_seasons(self, seasons: List[str], force_update: bool = False) -> Dict[str, Any]:
        """
        批量获取多个赛季的赛程数据，自动应用随机延迟

        Args:
            seasons: 赛季字符串列表
            force_update: 是否强制更新缓存

        Returns:
            Dict[str, Any]: 各赛季的数据字典，key为赛季，value为赛程数据
        """
        results = {}
        total_seasons = len(seasons)

        for i, season in enumerate(seasons):
            self.logger.info(f"获取赛季 {season} 数据 ({i + 1}/{total_seasons})...")

            # 获取赛季数据，最后一个赛季不应用延迟
            apply_delay = (i < total_seasons - 1)
            data = self.get_schedule_by_season(season, force_update, apply_delay)

            if data:
                results[season] = data
            else:
                self.logger.warning(f"获取赛季 {season} 数据失败")

        return results

    def get_all_seasons(self) -> List[str]:
        """获取所有需要处理的赛季列表"""
        try:
            start_year = int(self.schedule_config.START_SEASON.split('-')[0])
            end_year = int(self.schedule_config.CURRENT_SEASON.split('-')[0])

            seasons = []
            for year in range(start_year, end_year + 1):
                # 格式化为"YYYY-YY"
                next_year_short = str(year + 1)[-2:]
                season = f"{year}-{next_year_short}"
                seasons.append(season)

            return seasons
        except Exception as e:
            self.logger.error(f"生成赛季列表失败: {e}")
            return []

    def cleanup_cache(self, older_than: Optional[timedelta] = None) -> None:
        """清理缓存数据"""
        try:
            cache_age = older_than or self.schedule_config.CACHE_DURATION
            self.logger.info(f"正在清理 {cache_age} 之前的缓存数据")
            self.cache_manager.clear(
                prefix=self.__class__.__name__.lower(),
                age=cache_age
            )
        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")