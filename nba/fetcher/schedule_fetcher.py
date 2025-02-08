from typing import Dict, Optional, Any
from datetime import timedelta
from pathlib import Path
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config.nba_config import NBAConfig


class ScheduleConfig:
    """赛程数据配置"""
    SCHEDULE_URL: str = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"
    CACHE_PATH: Path = Path(NBAConfig.PATHS.SCHEDULE_CACHE_DIR)
    CACHE_DURATION: timedelta = timedelta(days=1)  # 赛程数据每天更新


class ScheduleFetcher(BaseNBAFetcher):
    """NBA赛程数据获取器"""

    def __init__(self, custom_config: Optional[ScheduleConfig] = None):
        """初始化赛程数据获取器"""
        self.schedule_config = custom_config or ScheduleConfig()

        # 配置缓存
        cache_config = BaseCacheConfig(
            duration=self.schedule_config.CACHE_DURATION,
            root_path=self.schedule_config.CACHE_PATH
        )

        # 创建基础请求配置 -  base_url 这里不再实际使用，但 BaseRequestConfig 需要一个 base_url
        base_config = BaseRequestConfig(
            base_url="https://www.nba.com",  # 使用一个占位符 URL
            cache_config=cache_config
        )

        # 初始化基类
        super().__init__(base_config)

    def get_schedule(self, force_update: bool = False) -> Optional[Dict[str, Any]]:
        """获取NBA赛程数据

        1. 使用基类的 fetch_data 方法
        2. 直接使用 SCHEDULE_URL，不再构建URL
        3. 简化了缓存处理逻辑
        4. 优化了错误处理
        """
        try:
            # 构建缓存键
            cache_key = "schedule"

            # 获取数据，直接使用 SCHEDULE_URL
            data = self.fetch_data(
                url=self.schedule_config.SCHEDULE_URL,  # 直接传递 url 参数
                cache_key=cache_key,
                force_update=force_update
            )

            return data

        except Exception as e:
            self.logger.error(f"获取赛程数据失败: {e}")
            return None

    def cleanup_cache(self, older_than: Optional[timedelta] = None) -> None:
        """清理缓存数据
        1. 使用基类的缓存清理机制
        2. 简化了参数处理

        Args:
            older_than: 清理早于指定时间的缓存。
                        默认为 `ScheduleConfig.CACHE_DURATION`，即清理早于赛程数据缓存有效期的缓存。
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