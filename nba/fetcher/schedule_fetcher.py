from typing import Dict, Optional, Any, List
from datetime import timedelta, datetime
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config import NBAConfig


class ScheduleConfig:
    """赛程数据配置"""
    BASE_URL: str = "https://stats.nba.com/stats"  # 基础URL
    SCHEDULE_ENDPOINT: str = "scheduleleaguev2"  # 端点

    CACHE_PATH = NBAConfig.PATHS.SCHEDULE_CACHE_DIR
    # 修改：只定义过去赛季的缓存时长，当前赛季将不使用缓存
    PAST_SEASON_CACHE_DURATION: timedelta = timedelta(days=365 * 10)  # 过去赛季缓存10年

    START_SEASON = "1946-47"  # NBA首个赛季，首场正式比赛是0024600001

    @property
    def current_season(self) -> str:
        """
        根据当前日期动态计算当前NBA赛季
        NBA赛季通常从每年10月开始，一直持续到次年6月
        赛季表示为 "YYYY-YY" 格式，如 "2024-25"
        """
        now = datetime.now()
        current_year = now.year
        current_month = now.month

        # 如果当前月份是10-12月，那么赛季是当前年份开始
        # 如果当前月份是1-9月，那么赛季是前一年开始
        if current_month >= 10:  # 10、11、12月属于新赛季
            season_start_year = current_year
        else:  # 1-9月属于上一年开始的赛季
            season_start_year = current_year - 1

        # 赛季结束年份的后两位
        season_end_short = str(season_start_year + 1)[-2:]

        return f"{season_start_year}-{season_end_short}"

    # 静态方法来构建 API 参数
    @staticmethod
    def get_api_params(season: str) -> Dict[str, Any]:
        """构建 scheduleleaguev2 API 的请求参数"""
        return {
            "LeagueID": "00",  # NBA
            "Season": season
            # 如果未来有更多固定的参数，也可以加在这里
        }


class ScheduleFetcher(BaseNBAFetcher):
    def __init__(self, custom_config: Optional[ScheduleConfig] = None):
        """初始化赛程数据获取器"""
        self.schedule_config = custom_config or ScheduleConfig()

        cache_config = BaseCacheConfig(
            duration=self.schedule_config.PAST_SEASON_CACHE_DURATION,
            root_path=self.schedule_config.CACHE_PATH
        )

        # 使用 BASE_URL 而不是完整的 URL
        base_config = BaseRequestConfig(
            base_url=self.schedule_config.BASE_URL,
            cache_config=cache_config,
            request_timeout=60
        )

        super().__init__(base_config)

    def get_schedule_by_season(self, season: str) -> Optional[Dict[str, Any]]:
        """获取指定赛季的赛程数据"""
        try:
            cache_key = f"schedule_{season}"
            # 判断是否为当前赛季
            is_current_season = (season == self.schedule_config.current_season)

            # 对于非当前赛季，总是先尝试从缓存获取数据
            if not is_current_season:
                # 直接尝试从缓存获取
                cached_data = self.cache_manager.get(
                    prefix=self.__class__.__name__.lower(),
                    identifier=cache_key
                )
                if cached_data is not None:
                    return cached_data

            else:
                self.logger.debug(f"赛季同步策略 | season={season} | is_current=True | cache_policy=no_cache")

            # 当前赛季总是从API获取最新数据，过往赛季在缓存未命中时请求
            effective_force_update = is_current_season

            # 使用端点方式请求
            response = self.fetch_data(
                endpoint=self.schedule_config.SCHEDULE_ENDPOINT,
                params=self.schedule_config.get_api_params(season),
                cache_key=cache_key,
                force_update=effective_force_update
            )

            if not response:
                self.logger.error(f"请求赛季 {season} 失败，返回 None")
                return None

            # 验证数据基本结构
            if not isinstance(response, dict) or 'leagueSchedule' not in response:
                self.logger.error(f"赛季 {season} 数据格式错误")
                return None

            return response

        except Exception as e:
            self.logger.error(f"获取赛季{season}赛程数据失败: {e}", exc_info=True)
            return None

    def get_schedules_for_seasons(self, seasons: List[str]) -> Dict[str, Any]:
        """
        批量获取多个赛季的赛程数据，支持断点续传

        Args:
            seasons: 赛季字符串列表

        Returns:
            Dict[str, Any]: 各赛季的数据字典，key为赛季，value为赛程数据
        """
        self.logger.info(f"开始NBA赛季数据同步任务 | seasons_count={len(seasons)} | range={seasons[0]}-{seasons[-1]}")

        # 使用基类的 batch_fetch 方法实现断点续传
        results = self.batch_fetch(
            ids=seasons,
            fetch_func=lambda season: self.get_schedule_by_season(season),
            task_name="schedules_for_seasons",
            batch_size=10  # 每批次处理10个赛季
        )

        return results

    def get_all_seasons(self) -> List[str]:
        """获取所有需要处理的赛季列表"""
        try:
            start_year = int(self.schedule_config.START_SEASON.split('-')[0])
            # 使用动态计算的CURRENT_SEASON属性
            end_year = int(self.schedule_config.current_season.split('-')[0])

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
        """清理缓存数据 (只针对过去赛季的缓存)"""
        # 现在缓存只包含过去赛季的数据，清理逻辑相对简单
        try:
            # 如果不指定 older_than，默认清理比配置的过去赛季缓存时长更早的数据
            cache_age = older_than or self.schedule_config.PAST_SEASON_CACHE_DURATION
            self.logger.info(f"开始清理赛程缓存 | age_threshold={cache_age} | target=past_seasons")
            self.cache_manager.clear(
                prefix=self.__class__.__name__.lower(),
                age=cache_age
            )
            self.logger.info(f"赛程缓存清理完成 | age_threshold={cache_age}")
        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")