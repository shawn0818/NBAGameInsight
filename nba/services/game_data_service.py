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
from nba.models.game_model import Game, TeamStats, Player, GameData, PlayerStatistics
from nba.models.player_model import PlayerProfile
from nba.models.team_model import TeamProfile, get_team_id
from nba.fetcher.team_fetcher import TeamFetcher
from nba.parser.team_parser import TeamParser
from config.nba_config import NBAConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class ServiceConfig:
    """服务配置类"""
    default_team: Optional[str] = "Lakers"
    default_player: Optional[str] = "LeBron James"
    date_str: str = "last"
    cache_size: int = 128
    cache_dir: Path = NBAConfig.PATHS.CACHE_DIR
    auto_refresh: bool = True
    refresh_interval: int = NBAConfig.API.SCHEDULE_UPDATE_INTERVAL

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
        self.logger = logger.getChild(self.__class__.__name__)

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
        if self.config.auto_refresh:
            self._setup_auto_refresh()

    def _setup_auto_refresh(self) -> None:
        """设置自动刷新机制"""
        self.logger.info(f"启用自动刷新，间隔: {self.config.refresh_interval}秒")
        # TODO: 实现自动刷新逻辑，例如使用定时任务
        pass

    def refresh_all_data(self) -> None:
        """手动刷新所有数据"""
        self.logger.info("开始手动刷新所有数据")
        self._initialize_player_data(force_update=True)
        self._initialize_team_data(force_update=True)
        self.clear_cache()

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

            self.logger.info(f"获取到球队ID: {team_id}，球队: {team_name}")

            raw_data = self.team_fetcher.get_team_details(
                team_id=team_id,
                force_update=force_update
            )
            if not raw_data:
                self.logger.error(f"无法获取球队数据，球队: {team_name}")
                return

            team_data = self.team_parser.parse_team_details(raw_data)
            if not team_data:
                self.logger.error(f"解析球队数据失败，球队: {team_name}")
                return

            self.logger.info(f"成功初始化球队 {team_name} 的数据")

            if isinstance(team_data, list):
                self.teams = team_data
            else:
                self.teams = [team_data]

            if self.teams:
                self.team_id_map = {team.team_id: team for team in self.teams}
                self.team_name_map = {
                    f"{team.city} {team.nickname}".lower(): team
                    for team in self.teams
                }
            else:
                self.teams = []
                self.team_id_map = {}
                self.team_name_map = {}

        except Exception as e:
            self.logger.error(f"初始化球队数据时出错: {e}", exc_info=True)
            self.teams = []
            self.team_id_map = {}
            self.team_name_map = {}

    def get_game(self, team: Optional[str] = None,
                 date: Optional[str] = None,
                 force_refresh: bool = False) -> Optional[Game]:
        """获取比赛数据"""
        try:
            team_name = team or self.config.default_team
            if not team_name:
                raise ValueError("必须提供球队名称或设置默认球队")

            date_str = date or self.config.date_str

            game_id = self._find_game_id(team_name, date_str)
            if not game_id:
                return None

            return self._fetch_game_data_sync(game_id)
        except Exception as e:
            self.logger.error(f"获取比赛数据时出错: {e}", exc_info=True)
            return None

    def get_game_basic_info(self, game: Game) -> Dict[str, Any]:
        """获取比赛基本信息"""
        try:
            game_data: GameData = game.game
            return {
                "game_id": game_data.gameId,
                "game_time": game_data.gameTimeLocal,
                "status": game_data.gameStatusText,
                "duration": game_data.duration,
                "arena": {
                    "name": game_data.arena.arenaName,
                    "city": game_data.arena.arenaCity,
                    "state": game_data.arena.arenaState,
                    "attendance": game_data.attendance
                },
                "teams": {
                    "home": {
                        "id": game_data.homeTeam.teamId,
                        "name": game_data.homeTeam.teamName,
                        "city": game_data.homeTeam.teamCity,
                        "code": game_data.homeTeam.teamTricode
                    },
                    "away": {
                        "id": game_data.awayTeam.teamId,
                        "name": game_data.awayTeam.teamName,
                        "city": game_data.awayTeam.teamCity,
                        "code": game_data.awayTeam.teamTricode
                    }
                },
                "officials": [
                    {
                        "name": official.name,
                        "position": official.assignment
                    }
                    for official in game_data.officials
                ]
            }
        except Exception as e:
            self.logger.error(f"获取比赛基本信息时出错: {e}", exc_info=True)
            return {}


    def get_player_stats(self, player: Player) -> Dict[str, Any]:
        """获取球员统计数据"""
        stats: PlayerStatistics = player.statistics
        return {
            "name": player.name,
            "minutes": stats.minutes,
            "points": stats.points,
            "field_goals": f"{stats.fieldGoalsMade}/{stats.fieldGoalsAttempted}",
            "field_goals_pct": stats.fieldGoalsPercentage,
            "three_points": f"{stats.threePointersMade}/{stats.threePointersAttempted}",
            "three_points_pct": stats.threePointersPercentage,
            "rebounds": stats.reboundsTotal,
            "assists": stats.assists,
            "steals": stats.steals,
            "blocks": stats.blocks,
            "turnovers": stats.turnovers
        }

    def get_game_stats(self, game: Game) -> Dict[str, Any]:
        """获取比赛统计数据"""
        try:
            def format_team_stats(team: TeamStats) -> Dict[str, Any]:
                return {
                    "name": team.teamName,
                    "stats": {
                        "points": team.score,
                        "field_goals": f"{team.statistics.get('fieldGoalsMade', 0)}/{team.statistics.get('fieldGoalsAttempted', 0)}",
                        "field_goals_pct": team.statistics.get('fieldGoalsPercentage', 0.0),
                        "three_points": f"{team.statistics.get('threePointersMade', 0)}/{team.statistics.get('threePointersAttempted', 0)}",
                        "three_points_pct": team.statistics.get('threePointersPercentage', 0.0),
                        "rebounds": team.statistics.get('reboundsTotal', 0),
                        "assists": team.statistics.get('assists', 0),
                        "steals": team.statistics.get('steals', 0),
                        "blocks": team.statistics.get('blocks', 0),
                        "turnovers": team.statistics.get('turnovers', 0)
                    },
                    "players": [
                        self.get_player_stats(p)
                        for p in team.players
                    ]
                }

            return {
                "home_team": format_team_stats(game.game.homeTeam),
                "away_team": format_team_stats(game.game.awayTeam)
            }

        except Exception as e:
            self.logger.error(f"获取比赛统计数据时出错: {e}", exc_info=True)
            return {}

    def get_filtered_events(
            self,
            game: Game,
            player_id: Optional[int] = None,
            event_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取过滤后的比赛事件

        Args:
            game: 比赛数据
            player_id: 球员ID,用于筛选特定球员的事件
            event_type: 事件类型,用于筛选特定类型的事件

        Returns:
            过滤后的比赛事件列表
        """
        try:
            if not game.playByPlay or not game.playByPlay.actions:
                return []

            events = []
            for action in game.playByPlay.actions:
                # 根据条件筛选
                if player_id and action.personId != player_id:
                    continue
                if event_type and action.actionType != event_type:
                    continue

                # 基础事件信息
                event = {
                    "period": action.period,
                    "clock": action.clock,
                    "action_type": action.actionType,
                    "description": action.description,
                    "team": action.teamTricode,
                    "player": {
                        "id": action.personId,
                        "name": action.playerName
                    } if action.personId else None,
                    "coordinates": {
                        "x": action.x,
                        "y": action.y
                    } if action.x is not None else None,
                    "score": {
                        "home": action.scoreHome,
                        "away": action.scoreAway
                    } if action.scoreHome is not None else None
                }

                # 根据事件类型添加特定信息
                if action.actionType in ["2pt", "3pt"]:
                    event.update({
                        "shot_info": {
                            "result": action.shotResult,
                            "distance": action.shotDistance,
                            "area": action.area
                        }
                    })
                elif action.actionType == "rebound":
                    event.update({
                        "rebound_type": action.subType
                    })
                elif action.actionType == "turnover":
                    event.update({
                        "turnover_type": action.subType
                    })

                events.append(event)

            return events

        except Exception as e:
            self.logger.error(f"获取过滤后的比赛事件时出错: {e}", exc_info=True)
            return []

    def get_player_info(self, identifier: Union[int, str]) -> Optional[PlayerProfile]:
        """
        获取球员详细信息。

        Args:
            identifier: 可以是球员ID或球员姓名

        Returns:
            PlayerProfile对象，如果未找到返回None
        """
        try:
            if isinstance(identifier, str):
                player_id = PlayerProfile.find_by_name(identifier)
                if player_id:
                    return PlayerProfile.find_by_id(player_id)
            else:
                return PlayerProfile.find_by_id(identifier)
            return None
        except Exception as e:
            self.logger.error(f"获取球员信息时出错: {e}", exc_info=True)
            return None

    def get_team_info(self, identifier: Union[int, str]) -> Optional[TeamProfile]:
        """
        获取球队详细信息。

        Args:
            identifier: 可以是球队ID或球队名称

        Returns:
            TeamProfile对象，如果未找到返回None
        """
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

    def clear_cache(self) -> None:
        """清理缓存数据"""
        try:
            if hasattr(self.get_game, 'cache_clear'):
                self.get_game.cache_clear()
                self.logger.info("成功清理 get_game 缓存")
        except Exception as e:
            self.logger.warning(f"清理缓存时出错: {e}")

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

    @lru_cache(maxsize=128)
    def _fetch_game_data_sync(self, game_id: str) -> Optional[Game]:
        """同步获取比赛数据"""
        self.logger.info(f"开始获取比赛数据，比赛ID: {game_id}")
        try:
            pbp_data = self.game_fetcher.get_playbyplay(
                game_id,
                force_update=self.config.auto_refresh
            )
            boxscore_data = self.game_fetcher.get_boxscore(
                game_id,
                force_update=self.config.auto_refresh
            )

            self.logger.debug(f"PlayByPlay数据: {pbp_data}")
            self.logger.debug(f"Boxscore数据: {boxscore_data}")

            if not pbp_data or not boxscore_data:
                self.logger.error("无法获取完整的比赛数据")
                return None

            try:
                if 'game' not in pbp_data:
                    self.logger.error("PlayByPlay数据缺少game字段")
                    return None

                if 'game' not in boxscore_data:
                    self.logger.error("Boxscore数据缺少game字段")
                    return None

                if 'homeTeam' not in boxscore_data['game'] or 'awayTeam' not in boxscore_data['game']:
                    self.logger.error("Boxscore数据缺少球队信息")
                    return None

                playbyplay = self.game_parser.parse_game_data(pbp_data)
                game = self.game_parser.parse_game_data(boxscore_data)

                if game.game and (game.game.homeTeam or game.game.awayTeam):
                    self.logger.info("成功解析比赛数据")
                    if game.game.homeTeam:
                        self.logger.info(f"主队球员数: {len(game.game.homeTeam.players)}")
                    if game.game.awayTeam:
                        self.logger.info(f"客队球员数: {len(game.game.awayTeam.players)}")
                else:
                    self.logger.error("球队数据解析失败")
                    return None

                game.playByPlay = playbyplay
                return game

            except ValueError as ve:
                self.logger.error(f"数据验证错误: {ve}", exc_info=True)
                return None
            except Exception as e:
                self.logger.error(f"数据解析错误: {e}", exc_info=True)
                return None

        except Exception as e:
            self.logger.error(f"获取或解析比赛数据时出错: {e}", exc_info=True)
            return None