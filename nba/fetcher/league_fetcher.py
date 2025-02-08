import json
import logging
from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig,CacheManager
from config.nba_config import NBAConfig


@dataclass
class NBAMappingConfig:
    """NBA ID映射配置类"""
    CACHE_PATH: Path = Path(NBAConfig.PATHS.LEAGUE_CACHE_DIR)
    CACHE_DURATION: timedelta = timedelta(days=30)

    # 球队信息映射
    TEAM_MAPPING: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        'lakers': {'id': 1610612747, 'city': 'Los Angeles', 'variants': ['la lakers', 'lal', 'los angeles lakers']},
        'clippers': {'id': 1610612746, 'city': 'Los Angeles',
                     'variants': ['la clippers', 'lac', 'los angeles clippers']},
        'warriors': {'id': 1610612744, 'city': 'Golden State', 'variants': ['gsw', 'dubs', 'golden state warriors']},
        'celtics': {'id': 1610612738, 'city': 'Boston', 'variants': ['bos', 'boston celtics']},
        'nets': {'id': 1610612751, 'city': 'Brooklyn', 'variants': ['bkn', 'brooklyn nets']},
        'knicks': {'id': 1610612752, 'city': 'New York', 'variants': ['ny', 'nyk', 'new york knicks']},
        'sixers': {'id': 1610612755, 'city': 'Philadelphia', 'variants': ['76ers', 'phi', 'philadelphia 76ers']},
        'raptors': {'id': 1610612761, 'city': 'Toronto', 'variants': ['tor', 'toronto raptors']},
        'bulls': {'id': 1610612741, 'city': 'Chicago', 'variants': ['chi', 'chicago bulls']},
        'cavaliers': {'id': 1610612739, 'city': 'Cleveland', 'variants': ['cavs', 'cle', 'cleveland cavaliers']},
        'pistons': {'id': 1610612765, 'city': 'Detroit', 'variants': ['det', 'detroit pistons']},
        'pacers': {'id': 1610612754, 'city': 'Indiana', 'variants': ['ind', 'indiana pacers']},
        'bucks': {'id': 1610612749, 'city': 'Milwaukee', 'variants': ['mil', 'milwaukee bucks']},
        'hawks': {'id': 1610612737, 'city': 'Atlanta', 'variants': ['atl', 'atlanta hawks']},
        'hornets': {'id': 1610612766, 'city': 'Charlotte', 'variants': ['cha', 'charlotte hornets']},
        'heat': {'id': 1610612748, 'city': 'Miami', 'variants': ['mia', 'miami heat']},
        'magic': {'id': 1610612753, 'city': 'Orlando', 'variants': ['orl', 'orlando magic']},
        'wizards': {'id': 1610612764, 'city': 'Washington', 'variants': ['wiz', 'was', 'washington wizards']},
        'nuggets': {'id': 1610612743, 'city': 'Denver', 'variants': ['den', 'denver nuggets']},
        'timberwolves': {'id': 1610612750, 'city': 'Minnesota',
                         'variants': ['wolves', 'min', 'minnesota timberwolves']},
        'thunder': {'id': 1610612760, 'city': 'Oklahoma City', 'variants': ['okc', 'oklahoma city thunder']},
        'blazers': {'id': 1610612757, 'city': 'Portland',
                    'variants': ['trail blazers', 'por', 'portland trail blazers']},
        'jazz': {'id': 1610612762, 'city': 'Utah', 'variants': ['uta', 'utah jazz']},
        'mavericks': {'id': 1610612742, 'city': 'Dallas', 'variants': ['mavs', 'dal', 'dallas mavericks']},
        'rockets': {'id': 1610612745, 'city': 'Houston', 'variants': ['hou', 'houston rockets']},
        'grizzlies': {'id': 1610612763, 'city': 'Memphis', 'variants': ['griz', 'mem', 'memphis grizzlies']},
        'pelicans': {'id': 1610612740, 'city': 'New Orleans', 'variants': ['nola', 'nop', 'new orleans pelicans']},
        'spurs': {'id': 1610612759, 'city': 'San Antonio', 'variants': ['sas', 'san antonio spurs']},
        'suns': {'id': 1610612756, 'city': 'Phoenix', 'variants': ['phx', 'phoenix suns']},
        'kings': {'id': 1610612758, 'city': 'Sacramento', 'variants': ['sac', 'sacramento kings']}
    })

    # 联盟和分区的映射
    CONFERENCE_DIVISION_MAPPING: Dict[str, Dict[str, List[str]]] = field(
        default_factory=lambda: {
            'eastern': {
                'atlantic': ['celtics', 'nets', 'knicks', '76ers', 'raptors'],
                'central': ['bulls', 'cavaliers', 'pistons', 'pacers', 'bucks'],
                'southeast': ['hawks', 'hornets', 'heat', 'magic', 'wizards']
            },
            'western': {
                'northwest': ['nuggets', 'timberwolves', 'thunder', 'trail blazers', 'jazz'],
                'pacific': ['warriors', 'clippers', 'lakers', 'suns', 'kings'],
                'southwest': ['mavericks', 'rockets', 'grizzlies', 'pelicans', 'spurs']
            }
        }
    )


class NBAMapper:
    """NBA ID映射管理器"""

    def __init__(self, custom_config: Optional[NBAMappingConfig] = None):
        self.config = custom_config or NBAMappingConfig()
        self.logger = logging.getLogger(self.__class__.__name__)
        # 创建 BaseCacheConfig 实例
        cache_config = BaseCacheConfig(
            duration=self.config.CACHE_DURATION,
            root_path=self.config.CACHE_PATH
        )
        
        # 使用 BaseCacheConfig 实例初始化 CacheManager
        self.cache_manager = CacheManager(config=cache_config)

    def _load_player_cache(self) -> None:
        """加载球员ID缓存"""
        try:
            cached_data = self.cache_manager.get(
                prefix="nba_mapper",
                identifier="player_id_mapping"
            )
            if cached_data:
                self._player_id_cache = cached_data
        except json.JSONDecodeError as e:
            self.logger.error(f"球员缓存JSON解析失败: {e}")
        except FileNotFoundError as e:
            self.logger.error(f"球员缓存文件未找到: {e}")
        except IOError as e:
            self.logger.error(f"读取球员缓存IO错误: {e}")
        except Exception as e:
            self.logger.error(f"加载球员缓存时发生未预期的错误: {e}")

    def update_player_cache(self, players_data: List[List[Any]]) -> None:
        """更新球员ID缓存

        Args:
            players_data: 包含球员信息的数据列表，来自get_all_players的结果
        """
        if not players_data:
            self.logger.warning("接收到空的球员数据")
            return

        try:
            player_mapping = {}
            for player in players_data:
                if len(player) < 3:
                    self.logger.warning(f"球员数据格式不正确: {player}")
                    continue

                player_name = player[2].lower()
                player_id = player[0]
                player_mapping[player_name] = player_id

                # 处理名字变体
                name_parts = player_name.split()
                if len(name_parts) > 1:
                    initial_variant = f"{name_parts[0][0]}. {' '.join(name_parts[1:])}"
                    player_mapping[initial_variant.lower()] = player_id

            self._player_id_cache.update(player_mapping)

            try:
                self.cache_manager.set(
                    prefix="nba_mapper",
                    identifier="player_id_mapping",
                    data=self._player_id_cache
                )
            except IOError as e:
                self.logger.error(f"写入球员缓存文件失败: {e}")
            except TypeError as e:
                self.logger.error(f"球员数据JSON序列化失败: {e}")
            except Exception as e:
                self.logger.error(f"保存球员缓存时发生未预期的错误: {e}")

        except (TypeError, AttributeError) as e:
            self.logger.error(f"处理球员数据时发生错误: {e}")
        except Exception as e:
            self.logger.error(f"更新球员缓存时发生未预期的错误: {e}")

    def get_player_id(self, player_name: str) -> Optional[int]:
        """获取球员ID"""
        player_name = player_name.lower().strip()

        # 直接匹配
        if player_name in self._player_id_cache:
            return self._player_id_cache[player_name]

        # 模糊匹配
        matches = []
        for name, player_id in self._player_id_cache.items():
            if player_name in name or name in player_name:
                matches.append((name, player_id, len(name)))

        if matches:
            return sorted(matches, key=lambda x: x[2])[0][1]

        return None

    def get_team_id(self, query: str) -> Optional[Tuple[int, str]]:
        """获取球队ID和标准名称"""
        query = query.lower().strip()

        # 直接匹配
        if query in self.config.TEAM_MAPPING:
            team_info = self.config.TEAM_MAPPING[query]
            return team_info['id'], f"{team_info['city']} {query.title()}"

        # 遍历所有可能的名称变体
        matches = []
        for team_name, team_info in self.config.TEAM_MAPPING.items():
            all_names = [team_name.lower(), team_info['city'].lower()] + [v.lower() for v in team_info['variants']]

            for name in all_names:
                if query == name:
                    return team_info['id'], f"{team_info['city']} {team_name.title()}"

                if name.startswith(query):
                    matches.append((team_name, team_info, len(name) - len(query)))
                elif query in name or name in query:
                    matches.append((team_name, team_info, len(name)))

        if matches:
            best_match = sorted(matches, key=lambda x: x[2])[0]
            team_name, team_info = best_match[0], best_match[1]
            return team_info['id'], f"{team_info['city']} {team_name.title()}"

        return None

    def get_division_rivals(self, team_name: str) -> List[str]:
        """获取同分区竞争对手"""
        result = self.get_team_id(team_name)
        if not result:
            return []

        _, standard_name = result
        standard_name = standard_name.lower()

        for conference in self.config.CONFERENCE_DIVISION_MAPPING.values():
            for division_teams in conference.values():
                if standard_name in division_teams:
                    return [team.title() for team in division_teams if team != standard_name]
        return []

    def get_conference_teams(self, conference: str) -> List[str]:
        """获取指定联盟的所有球队"""
        conf = conference.lower()
        if conf not in self.config.CONFERENCE_DIVISION_MAPPING:
            return []

        teams = []
        for division_teams in self.config.CONFERENCE_DIVISION_MAPPING[conf].values():
            teams.extend(division_teams)
        return [team.title() for team in teams]

    def are_division_rivals(self, team1: str, team2: str) -> bool:
        """判断两支球队是否为分区竞争对手"""
        rivals = self.get_division_rivals(team1)
        result = self.get_team_id(team2)
        return result is not None and result[1] in rivals


@dataclass
class LeagueConfig:
    """联盟数据配置"""
    BASE_URL: str = "https://stats.nba.com"
    CACHE_PATH: Path = Path(NBAConfig.PATHS.LEAGUE_CACHE_DIR)
    CACHE_DURATION: timedelta = timedelta(days=7)

    # API端点配置
    ENDPOINTS: Dict[str, str] = field(default_factory=lambda: {
        'ALL_PLAYERS': 'stats/commonallplayers',
        'PLAYOFF_PICTURE': 'stats/playoffpicture',
        'LEAGUE_LEADERS': 'stats/alltimeleadersgrids',
        'PLAYER_INFO': 'stats/commonplayerinfo',
        'TEAM_INFO': 'stats/teaminfocommon'
    })

    # NBA ID配置
    LEAGUE_IDS: Dict[str, str] = field(default_factory=lambda: {
        'NBA': NBAConfig.LEAGUE.NBA_ID,
        'WNBA': NBAConfig.LEAGUE.WNBA_ID,
        'G_LEAGUE': NBAConfig.LEAGUE.G_LEAGUE_ID
    })

    # 赛季和统计类型配置
    SEASON_TYPES: list = field(default_factory=lambda: NBAConfig.LEAGUE.SEASON_TYPES)
    PER_MODES: list = field(default_factory=lambda: NBAConfig.LEAGUE.PER_MODES)


class LeagueFetcher(BaseNBAFetcher):
    """NBA联盟数据获取器"""

    def __init__(self,
                 custom_config: Optional[LeagueConfig] = None,
                 custom_mapper: Optional[NBAMapper] = None):
        """初始化联盟数据获取器"""
        self.league_config = custom_config or LeagueConfig()
        self.mapper = custom_mapper or NBAMapper()

        cache_config = BaseCacheConfig(
            duration=self.league_config.CACHE_DURATION,
            root_path=self.league_config.CACHE_PATH
        )

        base_config = BaseRequestConfig(
            base_url=self.league_config.BASE_URL,
            cache_config=cache_config
        )

        super().__init__(base_config)
        self._update_player_cache()

    def _update_player_cache(self) -> None:
        """更新球员ID缓存"""
        try:
            players_data = self.get_all_players()
            if players_data and 'resultSets' in players_data:
                players = players_data['resultSets'][0]['rowSet']
                self.mapper.update_player_cache(players)
        except Exception as e:
            self.logger.error(f"更新球员缓存失败: {e}")

    def get_all_players(self, current_season_only: bool = False,
                        force_update: bool = False) -> Optional[Dict[str, Any]]:
        """获取球员名册信息"""
        try:
            season = self._get_current_season()
            cache_key = f"players_{'current' if current_season_only else 'all'}"

            return self.fetch_data(
                endpoint=self.league_config.ENDPOINTS['ALL_PLAYERS'],
                params={
                    'LeagueID': self.league_config.LEAGUE_IDS['NBA'],
                    'Season': season,
                    'IsOnlyCurrentSeason': '1' if current_season_only else '0'
                },
                cache_key=cache_key,
                force_update=force_update
            )
        except Exception as e:
            self.logger.error(f"获取球员数据失败: {e}")
            return None

    def get_playoff_picture(self, force_update: bool = False) -> Optional[Dict[str, Any]]:
        """获取季后赛形势数据"""
        try:
            season = self._get_current_season()
            season_id = f"2{season.split('-')[0]}"
            cache_key = f"playoff_picture_{season_id}"

            return self.fetch_data(
                endpoint=self.league_config.ENDPOINTS['PLAYOFF_PICTURE'],
                params={
                    'LeagueID': self.league_config.LEAGUE_IDS['NBA'],
                    'SeasonID': season_id
                },
                cache_key=cache_key,
                force_update=force_update
            )
        except Exception as e:
            self.logger.error(f"获取季后赛数据失败: {e}")
            return None

    def get_league_leaders(self, season_type: str = 'Regular Season',
                           per_mode: str = 'PerGame',
                           top_x: int = 10,
                           force_update: bool = False) -> Optional[Dict[str, Any]]:
        """获取联盟数据统计领袖"""
        if season_type not in self.league_config.SEASON_TYPES:
            raise ValueError(f"Invalid season_type: {season_type}")
        if per_mode not in self.league_config.PER_MODES:
            raise ValueError(f"Invalid per_mode: {per_mode}")
        if not 0 < top_x <= 50:
            raise ValueError("top_x must be between 1 and 50")

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
                cache_key=cache_key,
                force_update=force_update
            )
        except Exception as e:
            self.logger.error(f"获取联盟领袖数据失败: {e}")
            return None

    def cleanup_cache(self, older_than: Optional[timedelta] = None) -> None:
        """清理缓存数据"""
        try:
            cache_age = older_than or self.league_config.CACHE_DURATION
            self.logger.info(f"正在清理{cache_age}之前的缓存数据")
            self.cache_manager.clear(
                prefix=self.__class__.__name__.lower(),
                age=cache_age
            )

            # 更新球员缓存
            self._update_player_cache()

        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")

    @staticmethod
    def _get_current_season() -> str:
        """获取当前赛季标识

        Returns:
            赛季标识字符串，如"2023-24"
        """
        current_date = datetime.now()
        year = current_date.year - (1 if current_date.month < 8 else 0)
        return f"{year}-{str(year + 1)[-2:]}"

    def get_mapper(self) -> NBAMapper:
        """获取ID映射器实例

        Returns:
            NBAMapper实例
        """
        return self.mapper