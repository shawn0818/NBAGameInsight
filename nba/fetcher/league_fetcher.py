from dataclasses import dataclass
from typing import Dict, Optional, Any, List
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

    def get_all_team_ids(self) -> List[int]:
        """从联盟排名数据中获取所有球队ID

        Returns:
            List[int]: 球队ID列表
        """
        try:
            # 获取排名数据
            standings_data = self.get_standings_data()
            if not standings_data or 'resultSets' not in standings_data:
                self.logger.error("获取排名数据失败，无法提取球队ID")
                return []

            # 找到Standings结果集
            standings_set = None
            for result_set in standings_data['resultSets']:
                if result_set['name'] == 'Standings':
                    standings_set = result_set
                    break

            if not standings_set or 'headers' not in standings_set or 'rowSet' not in standings_set:
                self.logger.error("排名数据格式异常，无法提取球队ID")
                return []

            # 获取TeamID的索引
            headers = standings_set['headers']
            team_id_index = headers.index('TeamID')

            # 提取所有球队ID
            team_ids = []
            for row in standings_set['rowSet']:
                if len(row) > team_id_index:
                    team_ids.append(int(row[team_id_index]))

            self.logger.info(f"成功提取{len(team_ids)}个球队ID: {team_ids}")
            return team_ids

        except Exception as e:
            self.logger.error(f"提取球队ID失败: {e}")
            return []

    def get_all_players_info(self, force_update: bool = False) -> Optional[Dict[str, Any]]:
        """
        获取所有NBA球员数据

        使用commonallplayers端点获取所有NBA球员的基本信息

        Args:
            force_update: 是否强制更新缓存数据

        Returns:
            所有球员的数据，获取失败时返回None
        """
        try:
            params = {
                "LeagueID": "00",  # 00表示NBA联盟
                "IsOnlyCurrentSeason": 0  # 获取所有球员，不仅是当前赛季
            }

            data = self.fetch_data(
                endpoint="commonallplayers",
                params=params,
                cache_key="all_players",
                force_update=force_update
            )

            return data

        except Exception as e:
            self.logger.error(f"获取所有球员数据失败: {e}")
            return None

