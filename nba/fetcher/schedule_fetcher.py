from typing import Dict, Optional, Any
from datetime import timedelta
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config.nba_config import NBAConfig


class ScheduleConfig:
    """赛程数据配置"""
    SCHEDULE_URL: str = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
    CACHE_PATH = NBAConfig.PATHS.SCHEDULE_CACHE_DIR
    CACHE_DURATION: timedelta = timedelta(days=1)  # 赛程数据每天更新


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
        
    def get_schedule(self, force_update: bool = True) -> Optional[Dict[str, Any]]:
        try:
            cache_key = "schedule"
            if not force_update:
                cached_data = self.cache_manager.get(
                    prefix=self.__class__.__name__.lower(),
                    identifier=cache_key
                )
                if cached_data is not None:
                    self.logger.info("从缓存获取数据成功")
                    if not isinstance(cached_data, dict) or 'leagueSchedule' not in cached_data:
                        self.logger.error("缓存数据结构不正确")
                        return None
                    return cached_data

            response = self.http_manager.make_request(
                url=self.schedule_config.SCHEDULE_URL,
                method='GET'
            )

            if not response:
                self.logger.error("请求失败，返回None")
                return None

            # 验证数据基本结构
            if not isinstance(response, dict) or 'leagueSchedule' not in response:
                self.logger.error("数据格式错误")
                return None

            # 更新缓存
            try:
                self.cache_manager.set(
                    prefix=self.__class__.__name__.lower(),
                    identifier=cache_key,
                    data=response
                )
                self.logger.info("更新缓存成功")
            except Exception as e:
                self.logger.error(f"更新缓存失败: {e}")

            return response

        except Exception as e:
            self.logger.error(f"获取赛程数据失败: {e}", exc_info=True)
            return None

    def cleanup_cache(self, older_than: Optional[timedelta] = None) -> None:
        """清理缓存数据

        Args:
            older_than: 清理早于指定时间的缓存。默认使用配置的缓存时长。
        """
        try:
            cache_age = older_than or self.schedule_config.CACHE_DURATION
            self.logger.info(f"正在清理 {cache_age} 之前的缓存数据")
            self.cache_manager.clear(
                prefix=self.__class__.__name__.lower(),
                age=cache_age
            )
        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")