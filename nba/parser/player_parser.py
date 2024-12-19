from typing import Dict, List, Optional, Any, Union
import logging
from datetime import datetime
from pydantic import ValidationError
from nba.models.player_model import PlayerProfile, PlayerDraft, PlayerCareer

class PlayerParser:
    """NBA球员数据解析器"""
    
    def __init__(self):
        """初始化解析器"""
        self.logger = logging.getLogger(self.__class__.__name__)

    def parse_players(self, raw_data: Dict[str, Any]) -> List[PlayerProfile]:
        """
        解析API响应数据为PlayerProfile对象列表

        Args:
            raw_data: 从API获取的原始JSON数据

        Returns:
            List[PlayerProfile]: 解析后的球员信息列表
        """
        players = []
        
        try:
            # 验证数据结构
            if not self._validate_raw_data(raw_data):
                return players

            player_set = raw_data['resultSets'][0]
            headers = player_set['headers']
            rows = player_set['rowSet']

            # 创建字段映射
            field_map = {header: idx for idx, header in enumerate(headers)}
            
            # 解析每一行数据
            for row in rows:
                try:
                    player_data = self._map_row_to_dict(row, field_map)
                    if player := self._parse_player(player_data):
                        players.append(player)
                except Exception as e:
                    self.logger.error(f"Error parsing player row: {str(e)}")
                    continue

            self.logger.info(f"Successfully parsed {len(players)} players")
            return players
            
        except Exception as e:
            self.logger.error(f"Error parsing player data: {str(e)}")
            return players

    def _validate_raw_data(self, data: Dict[str, Any]) -> bool:
        """
        验证原始数据的基本结构

        Args:
            data: 原始JSON数据

        Returns:
            bool: 数据结构是否有效
        """
        if not isinstance(data, dict):
            self.logger.error("Input data must be a dictionary")
            return False

        if 'resultSets' not in data or not data['resultSets']:
            self.logger.error("Missing or empty resultSets")
            return False

        player_set = data['resultSets'][0]
        if 'headers' not in player_set or 'rowSet' not in player_set:
            self.logger.error("Missing headers or rowSet in player data")
            return False

        required_fields = {
            'PERSON_ID', 'PLAYER_LAST_NAME', 'PLAYER_FIRST_NAME', 
            'PLAYER_SLUG', 'TEAM_ID', 'POSITION'
        }
        
        headers = set(player_set['headers'])
        missing_fields = required_fields - headers
        if missing_fields:
            self.logger.error(f"Missing required fields: {missing_fields}")
            return False

        return True

    def _map_row_to_dict(self, row: List[Any], field_map: Dict[str, int]) -> Dict[str, Any]:
        """
        将行数据映射为字典格式

        Args:
            row: 原始行数据
            field_map: 字段名到索引的映射

        Returns:
            Dict[str, Any]: 映射后的数据字典
        """
        return {
            field: row[idx] if idx < len(row) else None
            for field, idx in field_map.items()
        }

    def _parse_player(self, player_data: Dict[str, Any]) -> Optional[PlayerProfile]:
        """
        解析单个球员数据

        Args:
            player_data: 球员原始数据字典

        Returns:
            Optional[PlayerProfile]: 解析后的球员数据模型
        """
        try:
            # 解析基本信息
            parsed_data = {
                'person_id': self._parse_int(player_data.get('PERSON_ID')),
                'last_name': self._parse_str(player_data.get('PLAYER_LAST_NAME')),
                'first_name': self._parse_str(player_data.get('PLAYER_FIRST_NAME')),
                'player_slug': self._parse_str(player_data.get('PLAYER_SLUG')),
                'team_id': self._parse_int(player_data.get('TEAM_ID'), 0),
                'jersey_number': player_data.get('JERSEY_NUMBER'),
                'position': self._parse_str(player_data.get('POSITION')),
                'height': self._parse_str(player_data.get('HEIGHT')),
                'weight': self._parse_str(player_data.get('WEIGHT')),
                'college': player_data.get('COLLEGE'),
                'country': player_data.get('COUNTRY'),
                
                # 解析选秀信息
                'draft': {
                    'year': self._parse_int(player_data.get('DRAFT_YEAR')),
                    'round': self._parse_int(player_data.get('DRAFT_ROUND')),
                    'number': self._parse_int(player_data.get('DRAFT_NUMBER'))
                },
                
                # 解析状态
                'roster_status': self._parse_float(player_data.get('ROSTER_STATUS'), 1.0),
                
                # 解析生涯数据
                'career': {
                    'from_year': self._parse_str(player_data.get('FROM_YEAR')),
                    'to_year': self._parse_str(player_data.get('TO_YEAR')),
                    'points': self._parse_float(player_data.get('PTS')),
                    'rebounds': self._parse_float(player_data.get('REB')),
                    'assists': self._parse_float(player_data.get('AST')),
                    'stats_timeframe': self._parse_str(player_data.get('STATS_TIMEFRAME'), 'Season')
                }
            }

            # 验证必需字段
            if not all([parsed_data['person_id'], parsed_data['last_name'], parsed_data['first_name']]):
                self.logger.warning(f"Missing required fields for player {parsed_data.get('person_id')}")
                return None

            return PlayerProfile(**parsed_data)

        except ValidationError as ve:
            self.logger.error(f"Validation error parsing player: {str(ve)}")
            return None
        except Exception as e:
            self.logger.error(f"Error parsing player data: {str(e)}")
            return None

    @staticmethod
    def _parse_int(value: Any, default: Optional[int] = None) -> Optional[int]:
        """安全地解析整数值"""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _parse_float(value: Any, default: float = 0.0) -> float:
        """安全地解析浮点数值"""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _parse_str(value: Any, default: str = "") -> str:
        """安全地解析字符串值"""
        if value is None:
            return default
        return str(value)