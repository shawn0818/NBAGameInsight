from typing import Dict, List, Optional, Any
import logging
from datetime import datetime
from dataclasses import dataclass

@dataclass
class PlayerBasicInfo:
    """球员基础信息"""
    person_id: str
    name: str
    team_info: Dict[str, str]
    position: str
    height: str
    weight: str
    jersey: str
    draft_info: Dict[str, Any]
    career_info: Dict[str, str]
    college: str
    country: str

@dataclass
class PlayerStats:
    """球员统计数据"""
    points: float = 0.0
    rebounds: float = 0.0
    assists: float = 0.0
    steals: float = 0.0
    blocks: float = 0.0
    turnovers: float = 0.0
    field_goals_made: int = 0
    field_goals_attempted: int = 0
    three_points_made: int = 0
    three_points_attempted: int = 0
    free_throws_made: int = 0
    free_throws_attempted: int = 0
    games_played: int = 0
    minutes: float = 0.0

    @property
    def field_goal_percentage(self) -> float:
        """计算投篮命中率"""
        return round((self.field_goals_made / self.field_goals_attempted * 100) 
                    if self.field_goals_attempted > 0 else 0.0, 1)

    @property
    def three_point_percentage(self) -> float:
        """计算三分命中率"""
        return round((self.three_points_made / self.three_points_attempted * 100)
                    if self.three_points_attempted > 0 else 0.0, 1)

    @property
    def free_throw_percentage(self) -> float:
        """计算罚球命中率"""
        return round((self.free_throws_made / self.free_throws_attempted * 100)
                    if self.free_throws_attempted > 0 else 0.0, 1)

class PlayerDataParser:
    """球员数据解析器"""
    
    def __init__(self):
        """初始化解析器"""
        self.logger = logging.getLogger(__name__)

    def parse_player_list(self, data: Dict) -> List[PlayerBasicInfo]:
        """
        解析球员列表数据
        
        Args:
            data: PlayerFetcher.get_player_profile() 返回的原始JSON数据
            
        Returns:
            List[PlayerBasicInfo]: 解析后的球员基础信息列表
        """
        players = []
        try:
            if not data or 'resultSets' not in data:
                return players

            player_set = data['resultSets'][0]
            headers = player_set['headers']
            rows = player_set['rowSet']

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
                players.append(player)

            return players

        except Exception as e:
            self.logger.error(f"Error parsing player list: {e}")
            return players

    def parse_career_stats(self, data: Dict) -> Optional[Dict[str, PlayerStats]]:
        """
        解析球员生涯数据
        
        Args:
            data: PlayerFetcher.get_career_stats() 返回的原始JSON数据
            
        Returns:
            Optional[Dict[str, PlayerStats]]: 包含常规赛和季后赛数据的字典
        """
        try:
            if not data or 'resultSets' not in data:
                return None

            stats = {}
            for result_set in data['resultSets']:
                if result_set['name'] == 'CareerTotalsRegularSeason':
                    stats['regular_season'] = self._parse_stats_row(result_set)
                elif result_set['name'] == 'CareerTotalsPostSeason':
                    stats['playoffs'] = self._parse_stats_row(result_set)

            return stats

        except Exception as e:
            self.logger.error(f"Error parsing career stats: {e}")
            return None

    def parse_season_stats(self, data: Dict) -> Optional[PlayerStats]:
        """
        解析球员赛季数据
        
        Args:
            data: PlayerFetcher.get_season_stats() 返回的原始JSON数据
            
        Returns:
            Optional[PlayerStats]: 赛季统计数据
        """
        try:
            if not data or 'resultSets' not in data:
                return None

            game_logs = data['resultSets'][0]
            if not game_logs.get('rowSet'):
                return None

            # 初始化赛季数据
            season_stats = PlayerStats()
            headers = game_logs['headers']

            # 累计所有比赛数据
            for row in game_logs['rowSet']:
                game_data = dict(zip(headers, row))
                season_stats.games_played += 1
                season_stats.points += float(game_data.get('PTS', 0))
                season_stats.rebounds += float(game_data.get('REB', 0))
                season_stats.assists += float(game_data.get('AST', 0))
                season_stats.steals += float(game_data.get('STL', 0))
                season_stats.blocks += float(game_data.get('BLK', 0))
                season_stats.turnovers += float(game_data.get('TOV', 0))
                season_stats.field_goals_made += int(game_data.get('FGM', 0))
                season_stats.field_goals_attempted += int(game_data.get('FGA', 0))
                season_stats.three_points_made += int(game_data.get('FG3M', 0))
                season_stats.three_points_attempted += int(game_data.get('FG3A', 0))
                season_stats.free_throws_made += int(game_data.get('FTM', 0))
                season_stats.free_throws_attempted += int(game_data.get('FTA', 0))
                
                # 解析分钟数
                minutes_str = game_data.get('MIN', '0:00')
                if ':' in minutes_str:
                    minutes, seconds = map(int, minutes_str.split(':'))
                    season_stats.minutes += minutes + seconds/60

            return season_stats

        except Exception as e:
            self.logger.error(f"Error parsing season stats: {e}")
            return None

    def _parse_stats_row(self, result_set: Dict) -> Optional[PlayerStats]:
        """解析单行统计数据"""
        try:
            if not result_set.get('rowSet'):
                return None

            headers = result_set['headers']
            row = result_set['rowSet'][0]
            data = dict(zip(headers, row))

            return PlayerStats(
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
                minutes=float(data.get('MIN', 0))
            )

        except Exception as e:
            self.logger.error(f"Error parsing stats row: {e}")
            return None

    def find_player_by_id(self, players: List[PlayerBasicInfo], player_id: str) -> Optional[PlayerBasicInfo]:
        """
        通过ID查找特定球员
        
        Args:
            players: 球员列表
            player_id: 球员ID
            
        Returns:
            Optional[PlayerBasicInfo]: 找到的球员信息
        """
        try:
            return next((p for p in players if p.person_id == player_id), None)
        except Exception as e:
            self.logger.error(f"Error finding player {player_id}: {e}")
            return None