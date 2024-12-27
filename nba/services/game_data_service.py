"""
NBA 比赛数据提供服务。
封装了获取 NBA 比赛数据的所有必要功能。
(同步版本，去除 async/await)
"""

import logging
from typing import Optional, Tuple, Dict, Any, List
from functools import lru_cache
from pathlib import Path

from nba.fetcher.game import GameFetcher
from nba.parser.game_parser import GameDataParser
from nba.parser.schedule_parser import ScheduleParser
from nba.fetcher.team import TeamProfile
from nba.fetcher.player import PlayerFetcher
from nba.parser.player_parser import PlayerParser
from nba.fetcher.schedule import ScheduleFetcher
from nba.models.game_model import Game, PlayerStatistics
from nba.models.event_model import PlayByPlay, EventType
from nba.models.player_model import PlayerProfile


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NBAGameDataProvider:
    """
    NBA 比赛数据提供服务 (同步版本)

    - 查找指定球队和日期的比赛
    - 获取比赛的详细数据和回放数据
    - 获取球员和球队的统计数据
    - 不再使用 async/await，所有方法改为同步
    """

    def __init__(
        self,
        default_team: Optional[str] = None,
        default_player: Optional[str] = None,
        date_str: str = "today",
        cache_size: int = 128,
        cache_dir: Optional[Path] = None
    ):
        """
        初始化数据提供服务

        Args:
            default_team: 默认的球队名称
            default_player: 默认的球员名称
            date_str: 日期字符串，如 "today", "yesterday", "last", "next", 或 "YYYY-MM-DD"
            cache_size: 缓存大小
            cache_dir: 缓存目录路径，默认为 None 则不使用缓存
        """
        self.logger = logger.getChild(self.__class__.__name__)
        self.default_team = default_team
        self.default_player = default_player
        self.default_date = date_str
        self._cache_size = cache_size

        # 初始化服务组件
        self.team_info = TeamProfile()
        self.schedule_fetcher = ScheduleFetcher()
        self.game_fetcher = GameFetcher()
        self.schedule_parser = ScheduleParser()
        self.game_parser = GameDataParser()

        # 初始化球员数据组件
        self.player_fetcher = PlayerFetcher()
        self.player_parser = PlayerParser(cache_dir=cache_dir)
        self._initialize_player_data()

    def _initialize_player_data(self) -> None:
        """初始化球员数据，包括获取和解析球员信息"""
        try:
            raw_data = self.player_fetcher.get_player_profile()
            if not raw_data:
                self.logger.error("无法获取球员数据")
                return

            parsed_players = self.player_parser.parse_players(raw_data)
            if not parsed_players:
                self.logger.error("解析球员数据失败")
                return

            self.logger.info(f"成功初始化 {len(parsed_players)} 名球员的数据")

        except Exception as e:
            self.logger.error(f"初始化球员数据时出错: {e}")

    def _get_team_id(self, team_name: str) -> Optional[int]:
        """获取球队ID"""
        return self.team_info.get_team_id(team_name)

    def _get_player_id(self, player_name: str) -> Optional[int]:
        """获取球员ID"""
        try:
            return PlayerProfile.find_by_name(player_name)
        except Exception as e:
            self.logger.error(f"获取球员ID时出错: {e}")
            return None

    @lru_cache(maxsize=128)
    def _find_game_id(self, team_name: str, date_str: str) -> Optional[str]:
        """
        查找指定球队在特定日期的比赛ID (同步)
        """
        try:
            team_id = self._get_team_id(team_name)
            if not team_id:
                self.logger.warning(f"未找到球队: {team_name}")
                return None

            schedule_data = self.schedule_fetcher.get_schedule()
            if not schedule_data:
                self.logger.error("无法获取赛程数据")
                return None

            schedule_df = self.schedule_parser.parse_raw_schedule(schedule_data)
            game_id = self.schedule_parser.get_game_id(schedule_df, team_id, date_str)

            if game_id:
                self.logger.info(f"找到 {team_name} 的比赛: {game_id}")
            else:
                self.logger.warning(f"未找到 {team_name} 的比赛")

            return game_id

        except Exception as e:
            self.logger.error(f"查找比赛时出错: {e}")
            return None

    def _fetch_game_data_sync(self, game_id: str) -> Tuple[Optional[PlayByPlay], Optional[Game]]:
        """
        同步获取比赛的详细数据和回放数据
        """
        self.logger.info(f"开始获取比赛数据，比赛ID: {game_id}")
        try:
            # 同步调用，不再使用 asyncio.to_thread 或 asyncio.gather
            pbp_data = self.game_fetcher.get_playbyplay(game_id)
            boxscore_data = self.game_fetcher.get_boxscore(game_id)

            if not pbp_data or not boxscore_data:
                self.logger.error("无法获取完整的比赛数据")
                return None, None

            playbyplay = PlayByPlay.model_validate(pbp_data)
            game = Game.model_validate(boxscore_data)
            return playbyplay, game

        except Exception as e:
            self.logger.error(f"获取或解析比赛数据时出错: {e}")
            return None, None

    def _get_default_or_provided_team(self, team_name: Optional[str]) -> str:
        """
        获取默认或提供的球队名称 (同步)
        """
        team = team_name or self.default_team
        if not team:
            raise ValueError("必须提供球队名称或设置默认球队")
        return team

    def get_game(
        self,
        team_name: Optional[str] = None,
        date_str: Optional[str] = None
    ) -> Optional[Game]:
        """
        获取比赛数据 (同步)

        Args:
            team_name: 球队名称，如果未提供则使用默认球队
            date_str: 日期字符串，如果未提供则使用默认日期

        Returns:
            Optional[Game]: 比赛数据对象
        """
        try:
            team = self._get_default_or_provided_team(team_name)
            date = date_str or self.default_date

            game_id = self._find_game_id(team, date)
            if not game_id:
                return None

            _, game = self._fetch_game_data_sync(game_id)
            return game

        except Exception as e:
            self.logger.error(f"获取比赛数据时出错: {e}")
            return None

    def get_playbyplay(
        self,
        team_name: Optional[str] = None,
        date_str: Optional[str] = None
    ) -> Optional[PlayByPlay]:
        """
        获取比赛回放数据 (同步)
        """
        try:
            team = self._get_default_or_provided_team(team_name)
            date = date_str or self.default_date

            game_id = self._find_game_id(team, date)
            if not game_id:
                return None

            playbyplay, _ = self._fetch_game_data_sync(game_id)
            return playbyplay

        except Exception as e:
            self.logger.error(f"获取回放数据时出错: {e}")
            return None

    def get_player_id(
        self,
        player_name: Optional[str] = None,
        team_name: Optional[str] = None,
        date_str: Optional[str] = None
    ) -> Optional[int]:
        """
        获取球员ID (同步)

        Args:
            player_name: 球员名称，如果未提供则使用默认球员
            team_name: 球队名称，如果未提供则使用默认球队
            date_str: 日期字符串，如果未提供则使用默认日期

        Returns:
            Optional[int]: 球员ID
        """
        try:
            player = player_name or self.default_player
            if not player:
                raise ValueError("必须提供球员名称或设置默认球员")

            player_id = self._get_player_id(player)
            if not player_id:
                self.logger.warning(f"未找到球员: {player}")
                return None

            return player_id

        except Exception as e:
            self.logger.error(f"获取球员ID时出错: {e}")
            return None

    def get_player_stats(
        self,
        player_name: Optional[str] = None,
        team_name: Optional[str] = None,
        date_str: Optional[str] = None
    ) -> Optional[PlayerStatistics]:
        """
        获取球员统计数据 (同步)
        """
        try:
            player = player_name or self.default_player
            if not player:
                raise ValueError("必须提供球员名称或设置默认球员")

            player_id = self._get_player_id(player)
            if not player_id:
                self.logger.warning(f"未找到球员: {player}")
                return None

            game = self.get_game(team_name, date_str)
            if not game:
                return None

            # 在 boxscore 中查找该球员的统计
            stats = game.get_player_stats(player_id, is_home=True) or game.get_player_stats(player_id, is_home=False)
            if not stats:
                self.logger.warning(f"未找到球员 {player} 的比赛数据")
                return None

            return stats

        except Exception as e:
            self.logger.error(f"获取球员统计时出错: {e}")
            return None

    def get_scoring_plays(
        self,
        team_name: Optional[str] = None,
        player_name: Optional[str] = None,
        date_str: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取得分事件 (同步)

        Args:
            team_name: 球队名称，如果未提供则使用默认球队
            player_name: 球员名称（可选），如果提供则只返回该球员的得分事件
            date_str: 日期字符串，如果未提供则使用默认日期

        Returns:
            List[Dict[str, Any]]: 得分事件列表
        """
        try:
            team = self._get_default_or_provided_team(team_name)
            date = date_str or self.default_date

            game_id = self._find_game_id(team, date)
            if not game_id:
                return []

            playbyplay, _ = self._fetch_game_data_sync(game_id)
            if not playbyplay or not playbyplay.actions:
                return []

            # 如果指定了球员名字，则获取对应 ID
            if player_name:
                player_id = self._get_player_id(player_name)
                if not player_id:
                    self.logger.warning(f"未找到球员: {player_name}")
                    return []
            else:
                player_id = None

            scoring_plays = []
            for action in playbyplay.actions:
                if (
                    action.actionType
                    and EventType.is_scoring_event(EventType(action.actionType))
                    and (not player_id or action.personId == player_id)
                ):
                    scoring_plays.append({
                        'time': action.clock,
                        'period': action.period,
                        'player': action.playerName,
                        'team': action.teamTricode,
                        'points': (
                            action.scoreHome - action.scoreAway
                            if (action.scoreHome is not None and action.scoreAway is not None)
                            else None
                        ),
                        'description': action.description
                    })

            self.logger.info(f"找到 {len(scoring_plays)} 条得分事件")
            return scoring_plays

        except Exception as e:
            self.logger.error(f"获取得分事件时出错: {e}")
            return []
