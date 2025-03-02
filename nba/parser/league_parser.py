from typing import Dict, Optional, List, Union, Any
import unicodedata
from dataclasses import dataclass, field
from datetime import timedelta, datetime
# 导入 fuzzywuzzy 模块
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

from nba.fetcher.base_fetcher import BaseCacheConfig, CacheManager
from nba.fetcher.league_fetcher import LeagueFetcher
from config.nba_config import NBAConfig
from utils.logger_handler import AppLogger


class NameNormalizer:
    """名称标准化工具"""

    COMMON_SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv'}
    NAME_SEPARATORS = {'.', '-', "'", ' '}

    @classmethod
    def normalize_name(cls, name: str) -> str:
        """标准化名称的通用方法"""
        if not name:
            return ""

        name = ' '.join(name.lower().split())
        for sep in cls.NAME_SEPARATORS:
            name = name.replace(sep, ' ')
        return ' '.join(name.split())

    @classmethod
    def normalize_player_name(cls, name: str) -> str:
        """增强的球员名字标准化处理"""
        if not name:
            return ""

        normalized = unicodedata.normalize('NFKD', name)
        normalized = ''.join(c for c in normalized if not unicodedata.combining(c))
        normalized = cls.normalize_name(normalized)

        name_parts = normalized.split()
        if name_parts and name_parts[-1].lower().strip('.') in cls.COMMON_SUFFIXES:
            name_parts.pop()

        return ' '.join(name_parts)

    @classmethod
    def normalize_slug(cls, slug: str) -> str:
        """标准化 slug 格式的名称"""
        return ' '.join(slug.replace('-', ' ').lower().split())

@dataclass
class ParserConfig:
    """解析器配置"""
    MAPPING_CACHE_DURATION: timedelta = timedelta(days=30)
    MAPPING_CACHE_PATHS: Dict[str, str] = field(default_factory=lambda: {
        'teams': NBAConfig.PATHS.TEAM_CACHE_DIR,
        'players': NBAConfig.PATHS.PLAYER_CACHE_DIR
    })


#  ---  新增: 硬编码的球队 abbv 字典  ---
HARDCODED_TEAM_ABBRS = {
    1610612737: "ATL",  # Hawks
    1610612738: "BOS",  # Celtics
    1610612739: "CLE",  # Cavaliers
    1610612740: "NOP",  # Pelicans
    1610612741: "CHI",  # Bulls
    1610612742: "DAL",  # Mavericks
    1610612743: "DEN",  # Nuggets
    1610612744: "GSW",  # Warriors
    1610612745: "HOU",  # Rockets
    1610612746: "LAC",  # Clippers
    1610612747: "LAL",  # Lakers
    1610612748: "MIA",  # Heat
    1610612749: "MIL",  # Bucks
    1610612750: "MIN",  # Timberwolves
    1610612751: "BKN",  # Nets
    1610612752: "NYK",  # Knicks
    1610612753: "ORL",  # Magic
    1610612754: "IND",  # Pacers
    1610612755: "PHI",  # Sixers
    1610612756: "PHX",  # Suns
    1610612757: "POR",  # Blazers
    1610612758: "SAC",  # Kings
    1610612759: "SAS",  # Spurs
    1610612760: "OKC",  # Thunder
    1610612761: "TOR",  # Raptors
    1610612762: "UTA",  # Jazz
    1610612763: "MEM",  # Grizzlies
    1610612764: "WAS",  # Wizards
    1610612765: "DET",  # Pistons
    1610612766: "CHA"   # Hornets
}


class LeagueMapper:
    def __init__(self, data_fetcher: LeagueFetcher, config: Optional[ParserConfig] = None):
        self.data_fetcher = data_fetcher
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.config = config or ParserConfig()

        self.team_cache = CacheManager(BaseCacheConfig(
            duration=self.config.MAPPING_CACHE_DURATION,
            root_path=self.config.MAPPING_CACHE_PATHS['teams']
        ))

        self.player_cache = CacheManager(BaseCacheConfig(
            duration=self.config.MAPPING_CACHE_DURATION,
            root_path=self.config.MAPPING_CACHE_PATHS['players']
        ))

        # 球员映射: {name/slug: player_id}
        self._player_name_to_id = {}
        # ID -> 球员全名
        self._player_id_to_name: Dict[int, str] = {}
        # ID -> 球员 slug
        self._player_id_to_slug: Dict[int, str] = {}

        # 球队映射: {name/slug/abbr: team_id}
        self._team_name_to_id = {}
        # ID -> 球队全名
        self._team_id_to_name: Dict[int, str] = {}
        # ID -> 球队 slug
        self._team_id_to_slug: Dict[int, str] = {}
        # ID -> 球队缩写
        self._team_id_to_abbr: Dict[int, str] = {}

        self._initialize_mappings()

    def _initialize_mappings(self):
        # 尝试从缓存加载
        team_mappings = self.team_cache.get('mapping', 'team_mappings')
        if team_mappings:
            self._team_name_to_id = team_mappings.get('name_to_id', {})
            self._team_id_to_name = team_mappings.get('id_to_name', {})
            self._team_id_to_slug = team_mappings.get('id_to_slug', {})
            self._team_id_to_abbr = team_mappings.get('id_to_abbr', {})
        else:
            self._update_team_mappings() # 如果缓存没有，先更新一次

        player_mappings = self.player_cache.get('mapping', 'player_mappings')
        if player_mappings:
            self._player_name_to_id = player_mappings.get('name_to_id', {})
            self._player_id_to_name = player_mappings.get('id_to_name', {})
            self._player_id_to_slug = player_mappings.get('id_to_slug', {})

        # 启动时检查/更新
        if not all([self._team_name_to_id, self._player_name_to_id,
                    self._team_id_to_name, self._player_id_to_name,
                    self._team_id_to_slug, self._player_id_to_slug,
                    self._team_id_to_abbr]):
            self._update_mappings()
        else:
            # 检查是否需要自动更新
            self._check_for_updates()

        #  ---  新增: 合并硬编码的 abbv  ---
        self._merge_hardcoded_team_abbreviations()


    #  ---  新增: 合并硬编码 abbv 的方法  ---
    def _merge_hardcoded_team_abbreviations(self):
        for team_id, abbr in HARDCODED_TEAM_ABBRS.items():
            if team_id in self._team_id_to_abbr: #  只在 team_id 存在时合并，避免错误
                self._team_id_to_abbr[team_id] = abbr
                team_name = self.get_team_name_by_id(team_id)
                if team_name:
                    self._team_name_to_id[NameNormalizer.normalize_name(abbr)] = team_id #  添加 abbr 到 name_to_id 映射


    def _check_for_updates(self):
        """检查是否需要自动更新映射数据"""
        team_metadata = self.team_cache.get('mapping', 'team_mappings_metadata')
        player_metadata = self.player_cache.get('mapping', 'player_mappings_metadata')

        now = datetime.now()
        update_interval = timedelta(days=7)  # 设置更新间隔，例如 7 天

        if team_metadata and 'last_updated' in team_metadata:
            last_updated = datetime.strptime(team_metadata['last_updated'], '%Y-%m-%d %H:%M:%S')
            if now - last_updated > update_interval:
                self.logger.info("Team mappings are outdated. Updating...")
                self._update_team_mappings()

        if player_metadata and 'last_updated' in player_metadata:
            last_updated = datetime.strptime(player_metadata['last_updated'], '%Y-%m-%d %H:%M:%S')
            if now - last_updated > update_interval:
                self.logger.info("Player mappings are outdated. Updating...")
                self._update_player_mappings()

    def _update_mappings(self):
        try:
            self._update_team_mappings()
            self._update_player_mappings()
        except Exception as e:
            self.logger.error(f"Error updating mappings: {e}")
            # 这里可以选择是否抛出异常，或者静默失败，继续使用旧的缓存
            # raise  # 如果你想在更新失败时停止程序，可以取消注释这一行

        # 缓存更新
        team_mappings = {
            'name_to_id': self._team_name_to_id,
            'id_to_name': self._team_id_to_name,
            'id_to_slug': self._team_id_to_slug,
            'id_to_abbr': self._team_id_to_abbr
        }
        team_metadata = {
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.team_cache.set('mapping', 'team_mappings', team_mappings, metadata=team_metadata)

        player_mappings = {
            'name_to_id': self._player_name_to_id,
            'id_to_name': self._player_id_to_name,
            'id_to_slug': self._player_id_to_slug
        }
        player_metadata = {
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.player_cache.set('mapping', 'player_mappings', player_mappings, metadata=player_metadata)

    def _update_team_mappings(self):
        try:
            standings_data = self.data_fetcher.get_standings_data()
            if not standings_data or 'resultSets' not in standings_data or not standings_data['resultSets']:
                self.logger.error("获取球队standings数据失败或数据格式不正确")
                return
            standings_set = standings_data['resultSets'][0]
            headers = {name: idx for idx, name in enumerate(standings_set['headers'])}

            self._team_name_to_id.clear()
            self._team_id_to_name.clear()
            self._team_id_to_slug.clear()
            self._team_id_to_abbr.clear()

            for team in standings_set['rowSet']:
                team_id = int(team[headers['TeamID']])
                city = team[headers['TeamCity']]
                name = team[headers['TeamName']]
                full_name = f"{city} {name}"
                # ---  移除从 standings_data 中获取 abbr 的代码 ---
                # abbr = team[headers['TEAM_ABBREVIATION']] #  不再尝试从 API 获取 abbr
                slug = team[headers['TeamSlug']]

                # 名称/Slug/Abbr -> ID
                self._team_name_to_id[NameNormalizer.normalize_name(full_name)] = team_id
                self._team_name_to_id[NameNormalizer.normalize_name(name)] = team_id
                # ---  不再从 API 获取 abbr，所以这里也不再处理 abbr  ---
                # if abbr:
                #     self._team_name_to_id[NameNormalizer.normalize_name(abbr)] = team_id
                if slug:
                    self._team_name_to_id[NameNormalizer.normalize_slug(slug)] = team_id

                # ID -> 各种名称
                self._team_id_to_name[team_id] = full_name
                if slug:
                    self._team_id_to_slug[team_id] = slug
                # ---  不再从 API 获取 abbr，所以这里也不再处理 abbr  ---
                # if abbr:
                #     self._team_id_to_abbr[team_id] = abbr

        except Exception as e:
            self.logger.error(f"Error updating team mappings: {e}", exc_info=True)
            # 不要清空缓存！

    def _update_player_mappings(self):
        try:
            players_data = self.data_fetcher.get_players_data()
            if not players_data or 'resultSets' not in players_data or not players_data['resultSets']:
                self.logger.error("获取球员数据失败或数据格式不正确")
                return
            players_set = players_data['resultSets'][0]
            headers = {name: idx for idx, name in enumerate(players_set['headers'])}

            self._player_name_to_id.clear()
            self._player_id_to_name.clear()
            self._player_id_to_slug.clear()

            for player in players_set['rowSet']:
                player_id = player[headers['PERSON_ID']]
                first_name = player[headers['PLAYER_FIRST_NAME']]
                last_name = player[headers['PLAYER_LAST_NAME']]
                full_name = f"{first_name} {last_name}"
                slug = player[headers['PLAYER_SLUG']]

                # 只存储完整名称和 slug
                normalized_full_name = NameNormalizer.normalize_player_name(full_name)
                self._player_name_to_id[normalized_full_name] = player_id

                if slug:
                    normalized_slug = NameNormalizer.normalize_slug(slug)
                    self._player_name_to_id[normalized_slug] = player_id

                # 存储 ID 到名称的映射
                self._player_id_to_name[player_id] = normalized_full_name
                if slug:
                    self._player_id_to_slug[player_id] = slug

        except Exception as e:
            self.logger.error(f"Error updating player mappings: {e}", exc_info=True)


    def _add_player_name_mapping(self, name, player_id):
        if name in self._player_name_to_id:
            if not isinstance(self._player_name_to_id[name], list):
                self._player_name_to_id[name] = [self._player_name_to_id[name]]
            self._player_name_to_id[name].append(player_id)
        else:
            self._player_name_to_id[name] = player_id

    # 查询方法 (输入)
    def get_team_id_by_name(self, name: str) -> Optional[int]:
        """
        通过名称、缩写或 slug 获取球队 ID (支持模糊匹配)。 使用 fuzzywuzzy 模糊匹配。
        """
        self.logger.info(f"开始查询球队: {name}")

        # 1. 尝试直接匹配原始输入
        team_id = self._team_name_to_id.get(name)
        if team_id is not None:
            return team_id

        # 2. 尝试 slug 格式
        team_id = self._team_name_to_id.get(NameNormalizer.normalize_slug(name))
        if team_id is not None:
            return team_id

        # 3. 尝试普通名称格式
        team_id = self._team_name_to_id.get(NameNormalizer.normalize_name(name))
        if team_id is not None:
            return team_id

        # 4. fuzzywuzzy 模糊匹配
        normalized_name = NameNormalizer.normalize_name(name)
        best_match, score = process.extractOne(normalized_name, self._team_name_to_id.keys(), scorer=fuzz.partial_ratio)

        fuzzy_match_threshold = 70  # 设置模糊匹配阈值，例如 70 分
        if best_match and score >= fuzzy_match_threshold:
            return self._team_name_to_id[best_match]

    def get_player_id_by_name(self, name: str) -> Optional[Union[int, List[int]]]:
        """
        通过名称获取球员 ID，支持部分名称匹配和大小写不敏感
        """
        self.logger.info(f"开始查询球员: {name}")

        # 1. 规范化输入名称（转小写）
        normalized_query = name.lower()

        # 2. 查找所有包含此名字的球员（大小写不敏感）
        matching_players = []
        for full_name, player_id in self._player_name_to_id.items():
            if normalized_query in full_name.lower():
                matching_players.append((full_name, player_id))

        if matching_players:
            self.logger.info(f"找到包含 '{name}' 的球员: {matching_players}")

            # 如果只有一个匹配，直接返回
            if len(matching_players) == 1:
                self.logger.info(f"唯一匹配，返回结果: {matching_players[0][1]}")
                return matching_players[0][1]

            # 如果多个条目指向同一个ID，返回该ID
            unique_ids = set(pid for _, pid in matching_players)
            if len(unique_ids) == 1:
                self.logger.info(f"多个条目指向同一ID，返回: {matching_players[0][1]}")
                return matching_players[0][1]

            # 如果有多个不同的匹配，用模糊匹配找出最佳结果
            best_match = process.extractOne(
                normalized_query,
                [name.lower() for name, _ in matching_players],  # 转小写进行比较
                scorer=fuzz.token_sort_ratio
            )

            if best_match and best_match[1] >= 50:
                idx = [name.lower() for name, _ in matching_players].index(best_match[0])
                result = matching_players[idx][1]
                self.logger.info(f"最佳匹配 '{matching_players[idx][0]}' 分数: {best_match[1]}, 返回ID: {result}")
                return result

        self.logger.info("没有找到匹配结果，返回 None")
        return None


    # 查询方法 (输出)
    def get_player_name_by_id(self, player_id: int) -> Optional[str]:
        """
        通过球员 ID 获取球员的全名。
        """
        return self._player_id_to_name.get(player_id)

    def get_player_slug_by_id(self, player_id: int) -> Optional[str]:
        """
        通过球员 ID 获取球员的 slug。
        """
        return self._player_id_to_slug.get(player_id)

    def get_team_name_by_id(self, team_id: int) -> Optional[str]:
        """
        通过球队 ID 获取球队的全名。
        """
        return self._team_id_to_name.get(team_id)

    def get_team_slug_by_id(self, team_id: int) -> Optional[str]:
        """
        通过球队 ID 获取球队的 slug。
        """
        return self._team_id_to_slug.get(team_id)

    def get_team_abbr_by_id(self, team_id: int) -> Optional[str]:
        """
        通过球队 ID 获取球队的缩写。
        """
        return self._team_id_to_abbr.get(team_id)

    def refresh_mappings(self):
        """ 刷新映射 (只刷新球员映射) """
        self._update_mappings()

class LeagueDataProvider:
    """联盟数据服务"""

    def __init__(self, config: Optional[ParserConfig] = None, data_fetcher: Optional[LeagueFetcher] = None): # LeagueFetcher 实例作为参数
        self.data_fetcher = data_fetcher or LeagueFetcher()
        self.data_mapper = LeagueMapper(self.data_fetcher, config=config) # ParserConfig 传递给 LeagueMapper
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def get_teams_enum(self) -> List[Dict[str, Union[int, str]]]:
        """
        获取所有球队的枚举列表，包含 id, name, abbv。
        从 LeagueMapper 中动态生成，并结合硬编码的 abbv。
        """
        teams_enum_list = []
        for team_id in HARDCODED_TEAM_ABBRS:  # 使用硬编码的team_id列表
            team_name = self.data_mapper.get_team_name_by_id(team_id)  # 使用公共方法
            team_abbr = self.data_mapper.get_team_abbr_by_id(team_id)

            if team_name and team_abbr:
                team_enum_dict = {
                    "id": team_id,
                    "name": team_name.split()[-1],
                    "abbv": team_abbr
                }
                teams_enum_list.append(team_enum_dict)
        return teams_enum_list

    def get_team_id_by_name(self, team_query: str) -> Optional[int]:
        """查询球队ID"""
        return self.data_mapper.get_team_id_by_name(team_query)
    def get_player_id_by_name(self, player_query: str) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """查询球员ID"""
        return self.data_mapper.get_player_id_by_name(player_query)
    def get_team_name_by_id(self, team_id: int) -> Optional[str]:
        """通过ID查询球队名称"""
        return self.data_mapper.get_team_name_by_id(team_id)
    def get_player_name_by_id(self, player_id: int) -> Optional[str]:
        """通过ID查询球员名称"""
        return self.data_mapper.get_player_name_by_id(player_id)
    def force_update_mappings(self):
        """强制更新数据 (只更新球员映射)"""
        self.data_mapper.refresh_mappings()