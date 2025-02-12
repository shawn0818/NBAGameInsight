from dataclasses import dataclass
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config.nba_config import NBAConfig


@dataclass
class LeagueConfig:
    """联盟基础配置"""
    BASE_URL: str = "https://stats.nba.com/stats"
    DATA_CACHE_DURATION: timedelta = timedelta(days=1) # 数据缓存时长 1 天

    # API端点
    ENDPOINTS = {
        'STANDINGS': 'leaguestandingsv3',
        'ALL_PLAYERS': 'commonallplayers',
    }

    # 使用预定义的联盟ID
    LEAGUE_IDS = {
        'NBA': NBAConfig.LEAGUE.NBA_ID,
        'WNBA': NBAConfig.LEAGUE.WNBA_ID,
        'G_LEAGUE': NBAConfig.LEAGUE.G_LEAGUE_ID
    }

    # 预定义的缓存路径 (只保留 league_data)
    CACHE_PATHS = {
        'league_data': NBAConfig.PATHS.LEAGUE_CACHE_DIR,
    }


class LeagueFetcher(BaseNBAFetcher):
    """联盟数据获取器"""

    def __init__(self, config: Optional[LeagueConfig] = None):
        self.league_config = config or LeagueConfig()

        # 配置数据缓存 (使用 LeagueConfig 中的 DATA_CACHE_DURATION)
        data_cache_config = BaseCacheConfig(
            duration=self.league_config.DATA_CACHE_DURATION,
            root_path=self.league_config.CACHE_PATHS['league_data']
        )

        # 配置 mapping 缓存 (不再在 LeagueFetcher 中创建 mapping_cache_config)
        # mapping_cache_config = BaseCacheConfig(
        #     duration=self.league_config.MAPPING_CACHE_DURATION,
        #     root_path=self.league_config.CACHE_PATHS['league_data']
        # )

        # 初始化基类配置 (使用 data_cache_config 进行数据请求的缓存)
        base_config = BaseRequestConfig(
            base_url=self.league_config.BASE_URL,
            cache_config=data_cache_config # 使用 data_cache_config 进行数据缓存
        )
        super().__init__(base_config)


    @staticmethod
    def _get_current_season() -> str:
        """获取当前赛季标识"""
        current_date = datetime.now()
        year = current_date.year - (1 if current_date.month < 8 else 0)
        return f"{year}-{str(year + 1)[-2:]}"

    def get_standings_data(self) -> Optional[Dict[str, Any]]:
        """获取联盟排名原始数据"""
        try:
            season = self._get_current_season()
            return self.fetch_data(
                endpoint=self.league_config.ENDPOINTS['STANDINGS'],
                params={
                    'LeagueID': self.league_config.LEAGUE_IDS['NBA'],
                    'Season': season,
                    'SeasonType': 'Regular Season'
                },
                cache_key=f"standings_{season}",
                cache_status_key="standings" # 可以添加 cache_status_key，虽然这里用处不大，但为了代码完整性
            )
        except Exception as e:
            self.logger.error(f"获取联盟排名数据失败: {e}")
            return None

    def get_players_data(self) -> Optional[Dict[str, Any]]:
        """获取球员名册原始数据"""
        try:
            url = "https://cdn.nba.com/static/json/staticData/playerIndex.json"
            season = self._get_current_season()
            return self.fetch_data(
                url=url,
                cache_key=f"players_{season}",
                cache_status_key="players" # 可以添加 cache_status_key，虽然这里用处不大，但为了代码完整性
            )
        except Exception as e:
            self.logger.error(f"获取球员数据失败: {e}")
            return None

