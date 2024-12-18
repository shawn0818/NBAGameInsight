# nba/models/players.py

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

@dataclass
class PlayerStatistics:
    assists: int = 0
    blocks: int = 0
    blocks_received: int = 0
    field_goals_attempted: int = 0
    field_goals_made: int = 0
    field_goals_percentage: float = 0.0
    fouls_offensive: int = 0
    fouls_drawn: int = 0
    fouls_personal: int = 0
    fouls_technical: int = 0
    free_throws_attempted: int = 0
    free_throws_made: int = 0
    free_throws_percentage: float = 0.0
    minus: float = 0.0
    minutes: str = 'PT00M00.00S'
    minutes_calculated: str = 'PT00M'
    plus: float = 0.0
    plus_minus_points: float = 0.0
    points: int = 0
    points_fast_break: int = 0
    points_in_the_paint: int = 0
    points_second_chance: int = 0
    rebounds_defensive: int = 0
    rebounds_offensive: int = 0
    rebounds_total: int = 0
    steals: int = 0
    three_pointers_attempted: int = 0
    three_pointers_made: int = 0
    three_pointers_percentage: float = 0.0
    turnovers: int = 0
    two_pointers_attempted: int = 0
    two_pointers_made: int = 0
    two_pointers_percentage: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict) -> "PlayerStatistics":
        return cls(
            assists=int(data.get('assists', 0)),
            blocks=int(data.get('blocks', 0)),
            blocks_received=int(data.get('blocksReceived', 0)),
            field_goals_attempted=int(data.get('fieldGoalsAttempted', 0)),
            field_goals_made=int(data.get('fieldGoalsMade', 0)),
            field_goals_percentage=float(data.get('fieldGoalsPercentage', 0.0)),
            fouls_offensive=int(data.get('foulsOffensive', 0)),
            fouls_drawn=int(data.get('foulsDrawn', 0)),
            fouls_personal=int(data.get('foulsPersonal', 0)),
            fouls_technical=int(data.get('foulsTechnical', 0)),
            free_throws_attempted=int(data.get('freeThrowsAttempted', 0)),
            free_throws_made=int(data.get('freeThrowsMade', 0)),
            free_throws_percentage=float(data.get('freeThrowsPercentage', 0.0)),
            minus=float(data.get('minus', 0.0)),
            minutes=data.get('minutes', 'PT00M00.00S'),
            minutes_calculated=data.get('minutesCalculated', 'PT00M'),
            plus=float(data.get('plus', 0.0)),
            plus_minus_points=float(data.get('plusMinusPoints', 0.0)),
            points=int(data.get('points', 0)),
            points_fast_break=int(data.get('pointsFastBreak', 0)),
            points_in_the_paint=int(data.get('pointsInThePaint', 0)),
            points_second_chance=int(data.get('pointsSecondChance', 0)),
            rebounds_defensive=int(data.get('reboundsDefensive', 0)),
            rebounds_offensive=int(data.get('reboundsOffensive', 0)),
            rebounds_total=int(data.get('reboundsTotal', 0)),
            steals=int(data.get('steals', 0)),
            three_pointers_attempted=int(data.get('threePointersAttempted', 0)),
            three_pointers_made=int(data.get('threePointersMade', 0)),
            three_pointers_percentage=float(data.get('threePointersPercentage', 0.0)),
            turnovers=int(data.get('turnovers', 0)),
            two_pointers_attempted=int(data.get('twoPointersAttempted', 0)),
            two_pointers_made=int(data.get('twoPointersMade', 0)),
            two_pointers_percentage=float(data.get('twoPointersPercentage', 0.0)),
        )

@dataclass
class PlayerBasicInfo:
    """球员基础信息"""
    person_id: str
    name: str
    position: str
    height: str
    weight: str
    jersey: str
    team_info: Dict[str, str]
    draft_info: Dict[str, Any]
    career_info: Dict[str, str]
    college: str
    country: str

    @staticmethod
    def normalize_name(name: str) -> str:
        """标准化球员姓名格式"""
        special_prefixes = ['de', 'le', 'la', 'mc', 'van', 'von']
        words = name.lower().split()
        normalized = []

        for word in words:
            for prefix in special_prefixes:
                if word.startswith(prefix) and len(word) > len(prefix):
                    word = word[:len(prefix)] + word[len(prefix)].upper() + word[len(prefix)+1:]
                    break

            if not any(word.startswith(prefix) for prefix in special_prefixes):
                word = word.capitalize()
            normalized.append(word)

        return " ".join(normalized)

    @property
    def headshot_url(self) -> str:
        """获取球员头像URL"""
        return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{self.person_id}.png"

    @property
    def first_name(self) -> str:
        """获取球员名"""
        return self.name.split()[0] if self.name else ""

    @property
    def last_name(self) -> str:
        """获取球员姓"""
        return self.name.split()[-1] if self.name else ""

    def __post_init__(self):
        """初始化后处理"""
        self.name = self.normalize_name(self.name)

@dataclass
class Player:
    """球员信息"""
    player_status: str
    player_order: int
    player_id: str
    player_jersey_number: str
    player_position: str
    player_starter: bool
    player_oncourt: bool
    player_played: bool
    player_statistics: PlayerStatistics
    player_name: str
    player_name_i: str
    player_first_name: str
    player_family_name: str
    player_not_playing_reason: Optional[str] = None
    player_not_playing_description: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "Player":
        return cls(
            player_status=data.get('status', ''),
            player_order=int(data.get('order', 0)),
            player_id=str(data.get('personId', '')),
            player_jersey_number=data.get('jerseyNum', ''),
            player_position=data.get('position', ''),
            player_starter=bool(data.get('starter', False)),
            player_oncourt=bool(data.get('oncourt', False)),
            player_played=bool(data.get('played', False)),
            player_statistics=PlayerStatistics.from_dict(data.get('statistics', {})),
            player_name=data.get('name', ''),
            player_name_i=data.get('nameI', ''),
            player_first_name=data.get('firstName', ''),
            player_family_name=data.get('familyName', ''),
            player_not_playing_reason=data.get('notPlayingReason'),
            player_not_playing_description=data.get('notPlayingDescription')
        )

    @property
    def full_name(self) -> str:
        return f"{self.player_first_name} {self.player_family_name}"

class PlayerNameMapping:
    """球员姓名-ID映射管理器"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._name_to_id: Dict[str, str] = {}
        self._id_to_name: Dict[str, str] = {}
        self._normalized_name_to_id: Dict[str, str] = {}

    def add_player(self, player: PlayerBasicInfo) -> None:
        """添加球员映射"""
        try:
            # 添加标准格式的完整名字映射
            normalized_full_name = PlayerBasicInfo.normalize_name(player.name)
            self._name_to_id[normalized_full_name] = player.person_id
            self._id_to_name[player.person_id] = normalized_full_name

            # 添加小写形式的映射，用于不区分大小写的搜索
            self._normalized_name_to_id[normalized_full_name.lower()] = player.person_id

            # 添加姓氏映射（如果姓氏唯一）
            last_name = player.last_name.lower()
            if last_name not in self._normalized_name_to_id:
                self._normalized_name_to_id[last_name] = player.person_id

            self.logger.debug(f"Added player mapping: {normalized_full_name} -> {player.person_id}")
        except Exception as e:
            self.logger.error(f"Error adding player {player.name}: {e}")

    def get_player_id(self, name: str) -> Optional[str]:
        """通过球员姓名获取ID"""
        try:
            normalized_name = PlayerBasicInfo.normalize_name(name)
            player_id = self._name_to_id.get(normalized_name)
            if player_id:
                return player_id

            return self._normalized_name_to_id.get(normalized_name.lower())
        except Exception as e:
            self.logger.error(f"Error getting player ID for name '{name}': {e}")
            return None

    def get_player_name(self, player_id: str) -> Optional[str]:
        """通过球员ID获取全名"""
        try:
            return self._id_to_name.get(player_id)
        except Exception as e:
            self.logger.error(f"Error getting player name for ID '{player_id}': {e}")
            return None

    def clear(self) -> None:
        """清空映射数据"""
        self._name_to_id.clear()
        self._id_to_name.clear()
        self._normalized_name_to_id.clear()
        self.logger.debug("Cleared all player mappings.")

class PlayerDataParser:
    """球员数据解析器"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.name_mapping = PlayerNameMapping()

    def parse_player_list(self, data: Dict) -> List[PlayerBasicInfo]:
        """解析球员列表数据"""
        players = []
        try:
            if not data or 'resultSets' not in data:
                self.logger.warning("No resultSets found in player list data.")
                return players

            player_set = data['resultSets'][0]
            headers = player_set['headers']
            rows = player_set['rowSet']

            # 清空现有映射
            self.name_mapping.clear()

            # 使用列表推导和字典解包提高效率
            for row in rows:
                row_data = dict(zip(headers, row))
                player = PlayerBasicInfo(
                    person_id=str(row_data['PERSON_ID']),
                    name=f"{row_data['PLAYER_FIRST_NAME']} {row_data['PLAYER_LAST_NAME']}",
                    team_info={
                        'id': str(row_data['TEAM_ID']),
                        'city': row_data['TEAM_CITY'],
                        'name': row_data['TEAM_NAME'],
                        'abbreviation': row_data['TEAM_ABBREVIATION']
                    },
                    position=row_data['POSITION'],
                    height=row_data['HEIGHT'],
                    weight=row_data['WEIGHT'],
                    jersey=row_data['JERSEY_NUMBER'],
                    draft_info={
                        'year': row_data['DRAFT_YEAR'],
                        'round': row_data['DRAFT_ROUND'],
                        'number': row_data['DRAFT_NUMBER']
                    },
                    career_info={
                        'from': row_data['FROM_YEAR'],
                        'to': row_data['TO_YEAR']
                    },
                    college=row_data['COLLEGE'],
                    country=row_data['COUNTRY']
                )
                self.name_mapping.add_player(player)
                players.append(player)

            self.logger.debug(f"Parsed {len(players)} players from data.")
            return players

        except Exception as e:
            self.logger.error(f"Error parsing player list: {e}")
            return players

    def parse_career_stats(self, data: Dict) -> Optional[Dict[str, PlayerStats]]:
        """解析球员生涯数据"""
        try:
            if not data or 'resultSets' not in data:
                self.logger.warning("No resultSets found in career stats data.")
                return None

            stats = {}
            for result_set in data['resultSets']:
                if result_set['name'] == 'CareerTotalsRegularSeason':
                    stats['regular_season'] = self._parse_stats_row(result_set)
                elif result_set['name'] == 'CareerTotalsPostSeason':
                    stats['playoffs'] = self._parse_stats_row(result_set)

            self.logger.debug("Parsed career stats.")
            return stats if stats else None

        except Exception as e:
            self.logger.error(f"Error parsing career stats: {e}")
            return None

    def parse_season_stats(self, data: Dict) -> Optional[PlayerStats]:
        """解析球员赛季数据"""
        try:
            if not data or 'resultSets' not in data:
                self.logger.warning("No resultSets found in season stats data.")
                return None

            game_logs = data['resultSets'][0]
            if not game_logs.get('rowSet'):
                self.logger.warning("No game logs found in season stats data.")
                return None

            # 使用向量化操作累积赛季数据
            df = pd.DataFrame(game_logs['rowSet'], columns=game_logs['headers'])
            season_stats = PlayerStats(
                points=df['PTS'].astype(float).sum(),
                rebounds=df['REB'].astype(float).sum(),
                assists=df['AST'].astype(float).sum(),
                steals=df['STL'].astype(float).sum(),
                blocks=df['BLK'].astype(float).sum(),
                turnovers=df['TOV'].astype(float).sum(),
                field_goals_made=df['FGM'].astype(int).sum(),
                field_goals_attempted=df['FGA'].astype(int).sum(),
                three_points_made=df['FG3M'].astype(int).sum(),
                three_points_attempted=df['FG3A'].astype(int).sum(),
                free_throws_made=df['FTM'].astype(int).sum(),
                free_throws_attempted=df['FTA'].astype(int).sum(),
                games_played=df['GP'].astype(int).sum(),
                minutes=df['MIN'].apply(lambda x: self._parse_minutes(x)).sum()
            )

            self.logger.debug("Parsed season stats.")
            return season_stats

        except Exception as e:
            self.logger.error(f"Error parsing season stats: {e}")
            return None

    def _parse_stats_row(self, result_set: Dict) -> Optional[PlayerStats]:
        """解析单行统计数据"""
        try:
            if not result_set.get('rowSet'):
                self.logger.warning(f"No rowSet found in {result_set.get('name', 'unknown')} stats.")
                return None

            row = result_set['rowSet'][0]
            data = dict(zip(result_set['headers'], row))

            stats = PlayerStats(
                points=float(data.get('PTS', 0)),
                rebounds=float(data.get('REB', 0)),
                assists=float(data.get('AST', 0)),
                steals=float(data.get('STL', 0)),
                blocks=float(data.get('BLK', 0)),
                turnovers=float(data.get('TOV', 0)),
                field_goals_made=int(data.get('FGM', 0)),
                field_goals_attempted=int(data.get('FGA', 0)),
                three_points_made=int(data.get('FG3M', 0)),
                three_points_attempted=int(data.get('FG3A', 0)),
                free_throws_made=int(data.get('FTM', 0)),
                free_throws_attempted=int(data.get('FTA', 0)),
                games_played=int(data.get('GP', 0)),
                minutes=self._parse_minutes(data.get('MIN', '0:00'))
            )

            self.logger.debug("Parsed stats row.")
            return stats

        except Exception as e:
            self.logger.error(f"Error parsing stats row: {e}")
            return None

    def _parse_minutes(self, minutes_str: str) -> float:
        """解析分钟数字符串为浮点数"""
        try:
            if ':' in minutes_str:
                minutes, seconds = map(int, minutes_str.split(':'))
                return minutes + seconds / 60
            return float(minutes_str)
        except Exception as e:
            self.logger.error(f"Error parsing minutes string '{minutes_str}': {e}")
            return 0.0

    def find_player_by_id(self, players: List[PlayerBasicInfo], player_id: str) -> Optional[PlayerBasicInfo]:
        """通过ID查找特定球员"""
        try:
            player = next((p for p in players if p.person_id == player_id), None)
            if player:
                self.logger.debug(f"Found player by ID {player_id}: {player.name}")
            else:
                self.logger.warning(f"No player found with ID {player_id}.")
            return player
        except Exception as e:
            self.logger.error(f"Error finding player {player_id}: {e}")
            return None

    def find_player_by_name(self, name: str) -> Optional[str]:
        """通过姓名查找球员ID"""
        try:
            player_id = self.name_mapping.get_player_id(name)
            if player_id:
                self.logger.debug(f"Found player ID for name '{name}': {player_id}")
            else:
                self.logger.warning(f"No player ID found for name '{name}'.")
            return player_id
        except Exception as e:
            self.logger.error(f"Error finding player ID by name '{name}': {e}")
            return None
