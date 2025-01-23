from typing import Dict, Optional
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig
from config.nba_config import NBAConfig


@dataclass
class LeagueConfig(BaseRequestConfig):
    """联盟数据配置"""
    BASE_URL: str = "https://stats.nba.com/stats"
    
    CACHE_PATH: str = NBAConfig.PATHS.LEAGUE_CACHE_DIR  # 使用全局配置的缓存目录
    CACHE_DURATION: timedelta = timedelta(days=7)  # 默认缓存7天

    # NBA ID配置
    LEAGUE_IDS = {
        'NBA': NBAConfig.LEAGUE.NBA_ID,
        'WNBA': NBAConfig.LEAGUE.WNBA_ID,
        'G_LEAGUE': NBAConfig.LEAGUE.G_LEAGUE_ID
    }

    # 赛季类型
    SEASON_TYPES = NBAConfig.LEAGUE.SEASON_TYPES

    # 数据统计模式
    PER_MODES =  NBAConfig.LEAGUE.PER_MODES

    # API端点
    ENDPOINTS = {
        'ALL_PLAYERS': 'commonallplayers',
        'PLAYOFF_PICTURE': 'playoffpicture',
        'LEAGUE_LEADERS': 'alltimeleadersgrids'
    }


class LeagueFetcher(BaseNBAFetcher):
    """NBA联盟数据获取器

    用于获取NBA联盟级别的数据，包括：
    1. 球员名册信息
    2. 季后赛形势
    3. 联盟数据统计领袖
    """

    league_config = LeagueConfig()

    def __init__(self):
        super().__init__()
       

    def _get_current_season(self) -> str:
        """获取当前赛季标识

        根据当前日期判断赛季，8月份作为赛季分界点

        Returns:
            赛季标识，格式如："2023-24"
        """
        current_date = datetime.now()
        year = current_date.year
        # 如果当前月份小于8月，说明还在上一个赛季
        if current_date.month < 8:
            year -= 1
        return f"{year}-{str(year + 1)[-2:]}"

    def get_all_players(self,
                        current_season_only: bool = False,
                        force_update: bool = False) -> Optional[Dict]:
        """获取球员名册信息

        Args:
            current_season_only: 是否只获取当前赛季球员
            force_update: 是否强制更新缓存

        Returns:
            球员信息数据，获取失败时返回None
        """
        try:
            cache_key = f"players_{'current' if current_season_only else 'all'}"

            return self.fetch_data(
                endpoint=self.league_config.ENDPOINTS['ALL_PLAYERS'],
                params={
                    'LeagueID': self.league_config.LEAGUE_IDS['NBA'],
                    'Season': self._get_current_season(),
                    'IsOnlyCurrentSeason': '1' if current_season_only else '0'
                },
                cache_config={
                    'key': cache_key,
                    'file': self.league_config.CACHE_PATH / "all_players_info.json",
                    'interval': int(self.league_config.CACHE_DURATION.total_seconds()),
                    'force_update': force_update
                }
            )
        except Exception as e:
            self.logger.error(f"Error fetching players data: {e}")
            return None

    def get_playoff_picture(self, force_update: bool = False) -> Optional[Dict]:
        """获取季后赛形势数据

        Returns:
            季后赛数据，获取失败时返回None
        """
        try:
            season_id = f"2{self._get_current_season().split('-')[0]}"

            return self.fetch_data(
                endpoint=self.league_config.ENDPOINTS['PLAYOFF_PICTURE'],
                params={
                    'LeagueID': self.league_config.LEAGUE_IDS['NBA'],
                    'SeasonID': season_id
                },
                cache_config={
                    'key': f"playoff_picture_{season_id}",
                    'file': self.league_config.CACHE_PATH / "playoff_picture.json",
                    'interval': int(self.league_config.CACHE_DURATION.total_seconds()),
                    'force_update': force_update
                }
            )
        except Exception as e:
            self.logger.error(f"Error fetching playoff picture: {e}")
            return None

    def get_league_leaders(self,
                           season_type: str = 'Regular Season',
                           per_mode: str = 'PerGame',
                           top_x: int = 10,
                           force_update: bool = False) -> Optional[Dict]:
        """获取联盟数据统计领袖

        Args:
            season_type: 赛季类型
            per_mode: 数据统计模式
            top_x: 返回前几名
            force_update: 是否强制更新缓存

        Returns:
            联盟领袖数据，获取失败时返回None
        """
        try:
            cache_key = f"leaders_{season_type}_{per_mode}_{top_x}"

            return self.fetch_data(
                endpoint=self.league_config.ENDPOINTS['LEAGUE_LEADERS'],
                params={
                    'LeagueID': self.league_config.LEAGUE_IDS['NBA'],
                    'SeasonType': season_type,
                    'PerMode': per_mode,
                    'TopX': str(top_x)
                },
                cache_config={
                    'key': cache_key,
                    'file': self.league_config.CACHE_PATH / "league_leaders.json",
                    'interval': int(self.league_config.CACHE_DURATION.total_seconds()),
                    'force_update': force_update
                }
            )
        except Exception as e:
            self.logger.error(f"Error fetching league leaders: {e}")
            return None