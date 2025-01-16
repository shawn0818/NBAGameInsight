import logging
from typing import Optional, Tuple, Dict, Any, List
from functools import lru_cache
from pathlib import Path
from dataclasses import dataclass

from nba.fetcher.game_fetcher import GameFetcher
from nba.parser.game_parser import GameDataParser
from nba.parser.schedule_parser import ScheduleParser
from nba.fetcher.player_fetcher import PlayerFetcher
from nba.parser.player_parser import PlayerParser
from nba.fetcher.schedule_fetcher import ScheduleFetcher
from nba.models.game_model import Game, PlayerStatistics, PlayByPlay, TeamStats
from nba.models.player_model import PlayerProfile
from nba.models.team_model import get_team_id, TeamProfile
from config.nba_config import NBAConfig
from nba.fetcher.team_fetcher import TeamFetcher
from nba.parser.team_parser import TeamParser

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
    """NBA比赛数据提供服务

    提供完整的NBA比赛数据访问功能，支持：
    1. 可配置的组件注入
    2. 自动数据刷新
    3. 灵活的缓存策略
    4. 错误处理和重试机制
    """

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
        """初始化数据提供服务

        Args:
            config: 服务配置对象
            schedule_fetcher: 赛程数据获取器
            schedule_parser: 赛程数据解析器
            player_fetcher: 球员数据获取器
            player_parser: 球员数据解析器
            team_fetcher: 球队数据获取器
            team_parser: 球队数据解析器
            game_fetcher: 比赛数据获取器
            game_parser: 比赛数据解析器
        """
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
        # 这里可以添加定时刷新的实现，比如使用 threading.Timer 或其他机制

    def refresh_all_data(self) -> None:
        """手动刷新所有数据"""
        self.logger.info("开始手动刷新所有数据")
        self._initialize_player_data(force_refresh=True)
        self._initialize_team_data(force_refresh=True)
        self.clear_cache()

    def _initialize_player_data(self, force_refresh: bool = False) -> None:
        """初始化球员数据

        Args:
            force_refresh: 是否强制刷新缓存数据
        """
        try:
            raw_data = self.player_fetcher.get_player_profile(force_update=force_refresh)
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

    def _initialize_team_data(self, force_refresh: bool = False) -> None:
        """初始化球队数据

        Args:
            force_refresh: 是否强制刷新缓存数据
        """
        try:
            # 确认默认球队设置
            team_name = self.config.default_team
            self.logger.info(f"正在初始化球队数据，默认球队: {team_name}")  # 添加日志来调试

            team_id = self._get_team_id(team_name)
            if not team_id:
                self.logger.error(f"无法获取球队ID，球队名称: {team_name}")
                return

            self.logger.info(f"获取到球队ID: {team_id}，球队: {team_name}")  # 添加日志来调试

            # 获取球队详情
            raw_data = self.team_fetcher.get_team_details(
                team_id=team_id,
                force_update=force_refresh
            )
            if not raw_data:
                self.logger.error(f"无法获取球队数据，球队: {team_name}")
                return

            # 解析球队数据
            team_data = self.team_parser.parse_team_details(raw_data)
            if not team_data:
                self.logger.error(f"解析球队数据失败，球队: {team_name}")
                return

            self.logger.info(f"成功初始化球队 {team_name} 的数据")

        except Exception as e:
            self.logger.error(f"初始化球队数据时出错: {e}")
            # 打印更详细的错误信息
            import traceback
            self.logger.error(traceback.format_exc())

    def clear_cache(self) -> None:
        """清除所有缓存数据"""
        # 清除 lru_cache 装饰的方法缓存
        self._find_game_id.cache_clear()
        self.get_game.cache_clear()
        self.logger.info("已清除所有缓存数据")

    @lru_cache(maxsize=128)
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
            self.logger.error(f"查找比赛时出错: {e}")
            return None

    def _get_team_id(self, team_name: str) -> Optional[int]:
        """获取球队ID"""
        try:
            if not team_name:
                return None

            result = get_team_id(team_name)
            return result[0] if result else None

        except Exception as e:
            self.logger.error(f"获取球队ID时出错: {str(e)}")
            return None

    def _get_player_id(self, player_name: str) -> Optional[int]:
        """获取球员ID"""
        try:
            return PlayerProfile.find_by_name(player_name)
        except Exception as e:
            self.logger.error(f"获取球员ID时出错: {e}")
            return None

    @lru_cache(maxsize=128)
    def get_game(
            self,
            team_name: Optional[str] = None,
            date_str: Optional[str] = None,
            force_update: bool = False
    ) -> Optional[Game]:
        """获取比赛数据"""
        try:
            team = team_name or self.config.default_team
            if not team:
                raise ValueError("必须提供球队名称或设置默认球队")

            date = date_str or self.config.date_str

            game_id = self._find_game_id(team, date)
            if not game_id:
                return None

            playbyplay, game = self._fetch_game_data_sync(game_id)
            return game

        except Exception as e:
            self.logger.error(f"获取比赛数据时出错: {e}")
            return None

    def _fetch_game_data_sync(
            self,
            game_id: str
    ) -> Tuple[Optional[PlayByPlay], Optional[Game]]:
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

            # 添加数据调试日志
            self.logger.debug(f"PlayByPlay数据: {pbp_data}")
            self.logger.debug(f"Boxscore数据: {boxscore_data}")

            if not pbp_data or not boxscore_data:
                self.logger.error("无法获取完整的比赛数据")
                return None, None

            try:
                # 添加数据格式验证
                if 'game' not in pbp_data:
                    self.logger.error("PlayByPlay数据缺少game字段")
                    return None, None

                if 'game' not in boxscore_data:
                    self.logger.error("Boxscore数据缺少game字段")
                    return None, None

                # 验证球员数据
                if 'homeTeam' not in boxscore_data['game'] or 'awayTeam' not in boxscore_data['game']:
                    self.logger.error("Boxscore数据缺少球队信息")
                    return None, None

                playbyplay = self.game_parser.parse_game_data(pbp_data)
                game = self.game_parser.parse_game_data(boxscore_data)

                # 验证解析后的数据
                if game.game and (game.game.homeTeam or game.game.awayTeam):
                    self.logger.info("成功解析比赛数据")
                    if game.game.homeTeam:
                        self.logger.info(f"主队球员数: {len(game.game.homeTeam.players)}")
                    if game.game.awayTeam:
                        self.logger.info(f"客队球员数: {len(game.game.awayTeam.players)}")
                else:
                    self.logger.error("球队数据解析失败")
                    return None, None

                return playbyplay, game

            except ValueError as ve:
                self.logger.error(f"数据验证错误: {ve}")
                return None, None
            except Exception as e:
                self.logger.error(f"数据解析错误: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                return None, None

        except Exception as e:
            self.logger.error(f"获取或解析比赛数据时出错: {e}")
            return None, None

    def get_game_basic_info(self, game: Game) -> Dict[str, Any]:
        """获取比赛基本信息"""
        try:
            return {
                "game_time": game.game.gameTimeLocal,
                "arena": {
                    "name": game.game.arena.arenaName,
                    "city": game.game.arena.arenaCity,
                    "attendance": game.game.attendance
                },
                "officials": [
                    {
                        "name": official.name,
                        "position": official.assignment
                    }
                    for official in game.game.officials
                ],
                "status": game.game.gameStatusText
            }
        except Exception as e:
            self.logger.error(f"获取比赛基本信息时出错: {e}")
            return {}

    def get_game_stats(self, game: Game) -> Dict[str, Any]:
        """获取比赛统计数据"""
        try:
            return {
                "score": {
                    "home": game.game.homeTeam.score,
                    "away": game.game.awayTeam.score
                },
                "home_team": {
                    "name": game.game.homeTeam.teamName,
                    "stats": self._get_team_stats(game.game.homeTeam),
                    "players": [
                        {
                            "name": p.name,
                            "stats": self._get_player_stats(p.statistics)
                        }
                        for p in game.game.homeTeam.players
                    ]
                },
                "away_team": {
                    "name": game.game.awayTeam.teamName,
                    "stats": self._get_team_stats(game.game.awayTeam),
                    "players": [
                        {
                            "name": p.name,
                            "stats": self._get_player_stats(p.statistics)
                        }
                        for p in game.game.awayTeam.players
                    ]
                }
            }
        except Exception as e:
            self.logger.error(f"获取比赛统计数据时出错: {e}")
            return {}

    def get_play_by_play(self, game: Game) -> List[Dict[str, Any]]:
        """获取比赛回合数据，处理成适合AI分析的格式"""
        try:
            if not game.playByPlay or not game.playByPlay.actions:
                return []

            plays = []
            for action in game.playByPlay.actions:
                # 基础事件信息
                play = {
                    "period": action.period,
                    "clock": action.clock,
                    "action_type": action.actionType,
                    "description": action.description,
                    "team": action.teamTricode,
                    "score": {
                        "home": action.scoreHome,
                        "away": action.scoreAway
                    } if action.scoreHome is not None else None
                }

                # 根据不同事件类型添加特定信息
                if isinstance(action, ShotEvent):
                    play.update({
                        "shot_type": action.subType,
                        "shot_area": action.area,
                        "shot_distance": action.shotDistance,
                        "shot_result": action.shotResult,
                        "points": action.pointsTotal,
                        "assist": {
                            "player_id": action.assistPersonId,
                            "player_name": action.assistPlayerNameInitial
                        } if action.assistPersonId else None,
                        "block": {
                            "player_id": action.blockPersonId,
                            "player_name": action.blockPlayerName
                        } if action.blockPersonId else None
                    })
                elif isinstance(action, FreeThrowEvent):
                    play.update({
                        "shot_type": "freethrow",
                        "shot_result": action.shotResult,
                        "points": action.pointsTotal,
                        "player_name": action.playerName
                    })
                elif isinstance(action, ReboundEvent):
                    play.update({
                        "rebound_type": action.subType,
                        "player_name": action.playerName,
                        "total_rebounds": action.reboundTotal,
                        "related_shot": action.shotActionNumber
                    })
                elif isinstance(action, TurnoverEvent):
                    play.update({
                        "turnover_type": action.subType,
                        "player_name": action.playerName,
                        "steal": {
                            "player_id": action.stealPersonId,
                            "player_name": action.stealPlayerName
                        } if action.stealPersonId else None
                    })
                elif isinstance(action, FoulEvent):
                    play.update({
                        "foul_type": action.subType,
                        "player_name": action.playerName,
                        "drawn_by": {
                            "player_id": action.foulDrawnPersonId,
                            "player_name": action.foulDrawnPlayerName
                        } if action.foulDrawnPersonId else None,
                        "official_id": action.officialId
                    })
                elif isinstance(action, SubstitutionEvent):
                    play.update({
                        "incoming_player": {
                            "id": action.incomingPersonId,
                            "name": action.incomingPlayerName
                        },
                        "outgoing_player": {
                            "id": action.outgoingPersonId,
                            "name": action.outgoingPlayerName
                        }
                    })
                elif isinstance(action, (TimeoutEvent, ViolationEvent)):
                    play.update({
                        "sub_type": action.subType
                    })
                elif isinstance(action, AssistEvent):
                    play.update({
                        "assist_total": action.assistTotal,
                        "player_name": action.playerName,
                        "scoring_player": {
                            "id": action.scoringPersonId,
                            "name": action.scoringPlayerName
                        }
                    })

                plays.append(play)

            return plays

        except Exception as e:
            self.logger.error(f"获取比赛回合数据时出错: {e}")
            return []

    def _get_player_stats(self, stats: PlayerStatistics) -> Dict[str, Any]:
        """格式化球员统计数据"""
        try:
            return {
                "points": stats.points,
                "rebounds": stats.reboundsTotal,
                "assists": stats.assists,
                "steals": stats.steals,
                "blocks": stats.blocks,
                "turnovers": stats.turnovers,
                "minutes": stats.seconds_played / 60,
                "shooting": {
                    "fg": f"{stats.fieldGoalsMade}/{stats.fieldGoalsAttempted}",
                    "fg_pct": stats.fieldGoalsPercentage,
                    "three": f"{stats.threePointersMade}/{stats.threePointersAttempted}",
                    "three_pct": stats.threePointersPercentage,
                    "ft": f"{stats.freeThrowsMade}/{stats.freeThrowsAttempted}",
                    "ft_pct": stats.freeThrowsPercentage
                }
            }
        except Exception as e:
            self.logger.error(f"格式化球员统计数据时出错: {e}")
            return {}

    def _get_team_stats(self, team: TeamStats) -> Dict[str, Any]:
        """格式化球队统计数据"""
        try:
            stats = team.statistics
            return {
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
        except Exception as e:
            self.logger.error(f"格式化球队统计数据时出错: {e}")
            return {}

    def get_game_data(self, game_id: str) -> Optional[Game]:
        """获取比赛数据"""
        try:
            # 获取比赛回放数据
            playbyplay_data = self.game_fetcher.fetch_playbyplay(game_id)
            self.logger.debug(f"获取到回放数据: {bool(playbyplay_data)}")
            if playbyplay_data:
                self.logger.debug(f"回放数据键: {playbyplay_data.keys()}")
            
            if not playbyplay_data:
                self.logger.error(f"获取比赛回放数据失败，比赛ID: {game_id}")
                return None

            # 获取比赛统计数据
            boxscore_data = self.game_fetcher.fetch_boxscore(game_id)
            self.logger.debug(f"获取到统计数据: {bool(boxscore_data)}")
            
            if not boxscore_data:
                self.logger.error(f"获取比赛统计数据失败，比赛ID: {game_id}")
                return None

            # 解析数据
            parsed_data = {
                'game': boxscore_data.get('game', {}),
                'meta': boxscore_data.get('meta', {}),
                'playByPlay': playbyplay_data
            }
            self.logger.debug(f"准备解析的数据键: {parsed_data.keys()}")
            
            game_data = self.game_parser.parse_game_data(parsed_data)

            if game_data:
                self.logger.info("成功解析比赛数据")
                self.logger.debug(f"回放数据是否存在: {hasattr(game_data, 'playByPlay')}")
                if hasattr(game_data, 'playByPlay') and game_data.playByPlay:
                    self.logger.debug(f"事件数量: {len(game_data.playByPlay.actions)}")
                self.logger.info(f"主队球员数: {len(game_data.game.homeTeam.players)}")
                self.logger.info(f"客队球员数: {len(game_data.game.awayTeam.players)}")
                return game_data
            else:
                self.logger.error("解析比赛数据失败")
                return None

        except Exception as e:
            self.logger.error(f"获取比赛数据时出错: {e}")
            return None
