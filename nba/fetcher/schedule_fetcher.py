from typing import Dict, Optional, Any, List
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

    def get_schedule_by_season(self, season: str, force_update: bool = False,
                               ) -> Optional[Dict[str, Any]]:
        """
        获取指定赛季的赛程数据

        Args:
            season: 赛季字符串，如"2024-25"
            force_update: 是否强制更新缓存


        Returns:
            赛程数据字典
        """
        try:
            cache_key = f"schedule_{season}"

            # 使用基类的 fetch_data 方法，简化请求和缓存处理
            params = {
                "LeagueID": "00",  # NBA
                "Season": season
            }

            self.logger.info(f"正在请求赛季{season}的数据...")
            response = self.fetch_data(
                url=self.schedule_config.SCHEDULE_URL,
                params=params,
                cache_key=cache_key,
                force_update=force_update
            )

            if not response:
                self.logger.error(f"请求赛季{season}失败，返回None")
                return None

            # 验证数据基本结构
            if not isinstance(response, dict) or 'leagueSchedule' not in response:
                self.logger.error(f"赛季{season}数据格式错误")
                return None

            return response

        except Exception as e:
            self.logger.error(f"获取赛季{season}赛程数据失败: {e}", exc_info=True)
            return None

    def get_schedules_for_seasons(self, seasons: List[str], force_update: bool = False) -> Dict[str, Any]:
        """
        批量获取多个赛季的赛程数据，支持断点续传

        Args:
            seasons: 赛季字符串列表
            force_update: 是否强制更新缓存

        Returns:
            Dict[str, Any]: 各赛季的数据字典，key为赛季，value为赛程数据
        """
        # 使用基类的 batch_fetch 方法实现断点续传
        self.logger.info(f"批量获取 {len(seasons)} 个赛季的赛程数据...")
        results = self.batch_fetch(
            ids=seasons,
            fetch_func=lambda season: self.get_schedule_by_season(season, force_update),
            task_name="schedules_for_seasons",
            batch_size=10  # 每批次处理10个赛季
        )

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