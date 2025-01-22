import logging
from typing import Optional, Dict, Any, Union, List
from functools import lru_cache
from pathlib import Path
from dataclasses import dataclass

from nba.fetcher.game_fetcher import GameFetcher
from nba.parser.game_parser import GameDataParser
from nba.parser.schedule_parser import ScheduleParser
from nba.fetcher.player_fetcher import PlayerFetcher
from nba.parser.player_parser import PlayerParser
from nba.fetcher.schedule_fetcher import ScheduleFetcher
from nba.models.game_model import Game, TeamStats, Player, GameData, PlayerStatistics, BaseEvent
from nba.models.player_model import PlayerProfile
from nba.models.team_model import TeamProfile, get_team_id
from nba.fetcher.team_fetcher import TeamFetcher
from nba.parser.team_parser import TeamParser
from config.nba_config import NBAConfig


@dataclass
class ServiceConfig:
    """服务配置类"""
    default_team: Optional[str] = "Lakers"
    default_player: Optional[str] = "LeBron James"
    date_str: str = "last"
    cache_size: int = 128
    cache_dir: Path = NBAConfig.PATHS.CACHE_DIR
    auto_refresh: bool = False
    use_pydantic_v2: bool = True

class NBAGameDataProvider:
    """NBA比赛数据提供服务"""

    def __init__(
            self,
            config: Optional[ServiceConfig] = None,
            schedule_fetcher: Optional[ScheduleFetcher] = None,
            schedule_parser: Optional[ScheduleParser] = None,
            player_fetcher: Optional[PlayerFetcher] = None,
            player_parser: Optional[PlayerParser] = None,
            team_fetcher: Optional[TeamFetcher] = None,
            team_parser: Optional[TeamParser] = None,
            game_fetcher: Optional[GameFetcher] = None,
            game_parser: Optional[GameDataParser] = None
    ):
        """初始化数据提供服务"""
        self.config = config or ServiceConfig()
        self.logger = logging.getLogger(self.__class__.__name__)

        # 添加调试日志
        self.logger.info(f"ServiceConfig初始化完成，配置信息：")
        self.logger.info(f"default_team: {self.config.default_team}")
        self.logger.info(f"default_player: {self.config.default_player}")

        # 注入或初始化组件
        self.schedule_fetcher = schedule_fetcher or ScheduleFetcher()
        self.schedule_parser = schedule_parser or ScheduleParser()
        self.player_fetcher = player_fetcher or PlayerFetcher()
        self.player_parser = player_parser or PlayerParser(cache_dir=self.config.cache_dir)
        self.team_fetcher = team_fetcher or TeamFetcher()
        self.team_parser = team_parser or TeamParser()
        self.game_fetcher = game_fetcher or GameFetcher()
        self.game_parser = game_parser or GameDataParser()

        # 初始化数据存储
        self.players: List[PlayerProfile] = []
        self.player_id_map: Dict[int, PlayerProfile] = {}
        self.player_name_map: Dict[str, PlayerProfile] = {}
        self.teams: List[TeamProfile] = []
        self.team_id_map: Dict[int, TeamProfile] = {}
        self.team_name_map: Dict[str, TeamProfile] = {}

        # 初始化数据
        self._initialize_services()

    def _initialize_services(self) -> None:
        """初始化所有服务组件"""
        self._initialize_player_data()
        self._initialize_team_data()


    def refresh_all_data(self) -> None:
        """
        重新初始化所有数据。
        注意：这个方法应该只在需要重置服务状态时使用，
        正常的数据更新应该依赖 fetcher 层的缓存机制。
        """
        self.logger.warning("正在执行完整的数据重新初始化...")
        self._initialize_services()

    # 数据初始化相关方法
    def _initialize_data(
            self,
            fetcher_func,
            parser_func,
            success_msg: str,
            failure_msg: str,
            force_update: bool = False
    ) -> Optional[Any]:
        """通用的数据初始化方法"""
        try:
            raw_data = fetcher_func(force_update=force_update)
            if not raw_data:
                self.logger.error(failure_msg)
                return None
            parsed_data = parser_func(raw_data)
            if not parsed_data:
                self.logger.error(failure_msg)
                return None
            if '{}' in success_msg:
                self.logger.info(success_msg.format(len(parsed_data)))
            else:
                self.logger.info(success_msg)
            return parsed_data
        except Exception as e:
            self.logger.error(f"{failure_msg}时出错: {e}", exc_info=True)
            return None

    def _initialize_player_data(self, force_update: bool = False) -> None:
        """初始化球员数据"""
        self.players = self._initialize_data(
            fetcher_func=self.player_fetcher.get_player_profile,
            parser_func=self.player_parser.parse_players,
            success_msg="成功初始化 {} 名球员的数据",
            failure_msg="无法获取或解析球员数据",
            force_update=force_update
        )
        if self.players:
            self.player_id_map = {player.person_id: player for player in self.players}
            self.player_name_map = {
                f"{player.first_name} {player.last_name}".lower(): player
                for player in self.players
            }
        else:
            self.player_id_map = {}
            self.player_name_map = {}

    def _initialize_team_data(self, force_update: bool = False) -> None:
        """初始化球队数据"""
        try:
            team_name = self.config.default_team
            self.logger.info(f"正在初始化球队数据，默认球队: {team_name}")

            team_id = self._get_team_id(team_name)
            if not team_id:
                self.logger.error(f"无法获取球队ID，球队名称: {team_name}")
                return

            raw_data = self.team_fetcher.get_team_details(
                team_id=team_id,
                force_update=force_update
            )
            if raw_data:
                team_data = self.team_parser.parse_team_details(raw_data)
                if team_data:
                    self.logger.info(f"成功初始化球队 {team_name} 的数据")
                    self.teams = [team_data] if not isinstance(team_data, list) else team_data
                    self.team_id_map = {team.team_id: team for team in self.teams}
                    self.team_name_map = {
                        f"{team.city} {team.nickname}".lower(): team
                        for team in self.teams
                    }
                    return

            self.logger.error(f"初始化球队数据失败，球队: {team_name}")
            self.teams = []
            self.team_id_map = {}
            self.team_name_map = {}

        except Exception as e:
            self.logger.error(f"初始化球队数据时出错: {e}", exc_info=True)
            self.teams = []
            self.team_id_map = {}
            self.team_name_map = {}

    # 比赛数据获取相关方法
    def get_game(self, team: Optional[str] = None,
                 date: Optional[str] = None) -> Optional[Game]:
        """获取比赛数据"""
        try:
            team_name = team or self.config.default_team
            if not team_name:
                raise ValueError("必须提供球队名称或设置默认球队")

            date_str = date or self.config.date_str
            game_id = self._find_game_id(team_name, date_str)
            
            if game_id:
                return self._fetch_game_data_sync(game_id)
            return None

        except Exception as e:
            self.logger.error(f"获取比赛数据时出错: {e}", exc_info=True)
            return None


    def get_game_basic_info(self, game: Game) -> GameData:
        """获取比赛基本信息"""
        return game.game

    def get_player_stats(self, player: Player) -> PlayerStatistics:
        """获取球员统计数据"""
        return player.statistics

    def get_game_stats(self, game: Game) -> Dict[str, Any]:
        """获取比赛统计数据"""
        try:
            if not game or not game.game:
                return {}

            return {
                "home_team": game.game.homeTeam if hasattr(game.game, 'homeTeam') else None,
                "away_team": game.game.awayTeam if hasattr(game.game, 'awayTeam') else None
            }
        except Exception as e:
            self.logger.error(f"获取比赛统计数据时出错: {str(e)}")
            return {}

    def get_game_events(self, game: Game) -> List[BaseEvent]:
        """获取比赛事件列表
        
        直接返回原始事件列表，让调用方决定如何处理事件。
        事件类型和筛选可以由调用方基于 BaseEvent 的类型系统来处理。
        
        Args:
            game: Game 对象
            
        Returns:
            List[BaseEvent]: 比赛事件列表
        """
        try:
            # 修改这里：确保传入的是 Game 对象而不是 GameData
            if not isinstance(game, Game):
                self.logger.warning("传入的不是 Game 对象")
                return []

            if not game.playByPlay:
                self.logger.warning("没有找到比赛回放数据")
                return []
                
            return game.playByPlay.actions

        except Exception as e:
            self.logger.error(f"获取比赛事件时出错: {e}", exc_info=True)
            return []


    def get_team_info(self, identifier: Union[int, str]) -> Optional[TeamProfile]:
        """获取球队详细信息"""
        try:
            if isinstance(identifier, int):
                return TeamProfile.get_team_by_id(identifier)
            else:
                team_id = get_team_id(identifier)
                if team_id:
                    return TeamProfile.get_team_by_id(team_id[0])
            return None
        except Exception as e:
            self.logger.error(f"获取球队信息时出错: {e}", exc_info=True)
            return None

    def _get_team_id(self, team_name: str) -> Optional[int]:
        """获取球队ID"""
        try:
            if not team_name:
                return None
            result = get_team_id(team_name)
            return result[0] if result else None
        except Exception as e:
            self.logger.error(f"获取球队ID时出错: {str(e)}", exc_info=True)
            return None

    def _find_game_id(self, team_name: str, date_str: str) -> Optional[str]:
        """查找指定球队在特定日期的比赛ID"""
        try:
            team_id = self._get_team_id(team_name)
            if not team_id:
                self.logger.warning(f"未找到球队: {team_name}")
                return None

            schedule_data = self.schedule_fetcher.get_schedule(
                force_update=self.config.auto_refresh
            )
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
            self.logger.error(f"查找比赛时出错: {e}", exc_info=True)
            return None

    @lru_cache(maxsize=128)
    def _fetch_game_data_sync(self, game_id: str) -> Optional[Game]:
        """同步获取比赛数据

        Args:
            game_id: 比赛ID

        Returns:
            Optional[Game]: 完整的比赛数据对象
        """
        self.logger.info(f"开始获取比赛数据，比赛ID: {game_id}")
        try:
            # 1. 获取 boxscore 数据
            boxscore_data = self.game_fetcher.get_boxscore(
                game_id,
                force_update=self.config.auto_refresh
            )
            if not boxscore_data:
                self.logger.warning("无法获取 boxscore 数据")
                return None

            # 2. 创建基础 game 对象
            game = self.game_parser.parse_game_data(boxscore_data)
            if not game:
                self.logger.warning("解析 boxscore 数据失败")
                return None

            # 3. 获取 playbyplay 数据
            try:
                pbp_data = self.game_fetcher.get_playbyplay(
                    game_id,
                    force_update=self.config.auto_refresh
                )

                # 如果获取到了 playbyplay 数据，尝试解析
                if pbp_data:
                    # 直接调用解析方法
                    playbyplay = self.game_parser._parse_playbyplay(pbp_data)
                    if playbyplay:
                        game.playByPlay = playbyplay
                        self.logger.debug(f"成功添加回放数据，包含 {len(playbyplay.actions)} 个事件")
                    else:
                        self.logger.warning("回放数据解析失败，跳过处理")
                else:
                    self.logger.warning("未获取到回放数据，跳过处理")

            except Exception as e:
                self.logger.error(f"处理回放数据时出错: {e}")
                # 即使回放数据处理失败，仍然返回基础比赛数据
                self.logger.warning("回放数据处理失败，继续返回基础比赛数据")

            return game

        except Exception as e:
            self.logger.error(f"获取比赛数据时出错: {e}")
            return None

    def clear_cache(self) -> None:
        """清理缓存数据"""
        try:
            if hasattr(self.get_game, 'cache_clear'):
                self.get_game.cache_clear()
                self.logger.info("成功清理 get_game 缓存")

        except Exception as e:
            self.logger.warning(f"清理缓存时出错: {e}")

    def __enter__(self):
            """上下文管理器入口"""
            return self

    def __exit__(self, exc_type, exc_val, exc_tb):
            """上下文管理器退出"""
            self.clear_cache()