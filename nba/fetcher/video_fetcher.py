from enum import Enum
from typing import Optional, Dict, Any
from urllib.parse import urlencode
from dataclasses import dataclass
from functools import lru_cache
from config.nba_config import NBAConfig

from .base_fetcher import BaseNBAFetcher


class ContextMeasure(str, Enum):
    """视频查询的上下文度量类型"""
    FG3M = "FG3M"  # 三分命中
    FG3A = "FG3A"  # 三分出手
    FGM = "FGM"  # 投篮命中
    FGA = "FGA"  # 投篮出手
    OREB = "OREB"  # 进攻篮板
    DREB = "DREB"  # 防守篮板
    REB = "REB"  # 总篮板
    AST = "AST"  # 助攻
    STL = "STL"  # 抢断
    BLK = "BLK"  # 盖帽
    TOV = "TOV"  # 失误


@dataclass
class VideoRequestParams:
    """视频查询参数构建器"""
    game_id: str
    player_id: Optional[str] = None
    team_id: Optional[str] = None
    context_measure: ContextMeasure = ContextMeasure.FGM
    season: str = "2024-25"
    season_type: str = "Regular Season"

    def validate(self) -> bool:
        """验证参数有效性"""
        if not self.game_id or not isinstance(self.game_id, str):
            return False
        if self.player_id and not str(self.player_id).isdigit():
            return False
        if self.team_id and not str(self.team_id).isdigit():
            return False
        return True

    def build(self) -> dict:
        """构建查询参数"""
        if not self.validate():
            raise ValueError("Invalid parameters")

        return {
            'LeagueID': "00",
            'Season': self.season,
            'SeasonType': self.season_type,
            'TeamID': int(self.team_id) if self.team_id else 0,
            'PlayerID': int(self.player_id) if self.player_id else 0,
            'GameID': self.game_id,
            'ContextMeasure': self.context_measure.value,
            'Outcome': '',
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
            'EndRange': 28800,
            'ContextFilter': '',
            'OppPlayerID': ''
        }


class VideoFetcher(BaseNBAFetcher):
    """视频链接数据获取器"""
    CACHE_DURATION = 3600  # 1小时缓存

    def __init__(self):
        super().__init__()
        self.base_url = "https://stats.nba.com/stats"

    @lru_cache(maxsize=100)
    def get_game_videos_raw(self, game_id: str, context_measure: ContextMeasure = ContextMeasure.FGM,
                            player_id: Optional[int] = None, team_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """获取比赛视频数据"""
        try:
            params = VideoRequestParams(
                game_id=game_id,
                player_id=str(player_id) if player_id else None,
                team_id=str(team_id) if team_id else None,
                context_measure=context_measure
            ).build()

            url = f"{self.base_url}/videoevents?" + urlencode(params)

            # 使用NBAConfig中定义的缓存路径
            cache_config = {
                'key': f'video_{game_id}_{player_id}_{team_id}_{context_measure.value}',
                'file': NBAConfig.PATHS.CACHE_DIR / 'videos.json',
                'interval': self.CACHE_DURATION
            }

            return self.fetch_data(url=url, cache_config=cache_config)

        except Exception as e:
            self.logger.error(f"获取视频数据失败: {e}", exc_info=True)
            return None