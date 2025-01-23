from typing import Dict, List, Optional, Any
import logging
from pathlib import Path
import json
from datetime import datetime, timedelta
from pydantic import ValidationError

from config.nba_config import NBAConfig
from nba.models.player_model import PlayerProfile


class PlayerParser:
    """NBA球员数据解析器"""

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        初始化解析器

        Args:
            cache_dir: 缓存目录路径，默认为None不使用缓存
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cache_dir = NBAConfig.PATHS.CACHE_DIR
        if cache_dir:
            self.cache_file = cache_dir / 'players.json'
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def parse_players(self, raw_data: Dict[str, Any], use_cache: bool = True) -> List[PlayerProfile]:
        """
        解析API响应数据为PlayerProfile对象列表

        Args:
            raw_data: 从API获取的原始JSON数据
            use_cache: 是否使用缓存，默认为True

        Returns:
            List[PlayerProfile]: 解析后的球员信息列表
        """
        # 如果启用缓存且缓存存在，尝试从缓存加载
        if use_cache and self.cache_dir and self._is_cache_valid():
            cached_data = self._load_from_cache()
            if cached_data:
                return cached_data

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

            # 如果启用缓存，保存解析结果
            if use_cache and self.cache_dir:
                self._save_to_cache(players)

            self.logger.info(f"Successfully parsed {len(players)} players")
            return players

        except Exception as e:
            self.logger.error(f"Error parsing player data: {str(e)}")
            return players

    def _validate_raw_data(self, data: Dict[str, Any]) -> bool:
        """验证原始数据的基本结构"""
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
            'PLAYER_SLUG', 'TEAM_ID'
        }

        headers = set(player_set['headers'])
        missing_fields = required_fields - headers
        if missing_fields:
            self.logger.error(f"Missing required fields: {missing_fields}")
            return False

        return True

    def _map_row_to_dict(self, row: List[Any], field_map: Dict[str, int]) -> Dict[str, Any]:
        """将行数据映射为字典格式"""
        return {
            field: row[idx] if idx < len(row) else None
            for field, idx in field_map.items()
        }

    def _parse_player(self, player_data: Dict[str, Any]) -> Optional[PlayerProfile]:
        """解析单个球员数据"""
        try:
            parsed_data = {
                'person_id': self._parse_int(player_data.get('PERSON_ID')),
                'last_name': player_data.get('PLAYER_LAST_NAME'),
                'first_name': player_data.get('PLAYER_FIRST_NAME'),
                'player_slug': player_data.get('PLAYER_SLUG'),
                'team_id': self._parse_int(player_data.get('TEAM_ID')),
                'team_slug': player_data.get('TEAM_SLUG'),
                'team_city': player_data.get('TEAM_CITY'),
                'team_name': player_data.get('TEAM_NAME'),
                'team_abbreviation': player_data.get('TEAM_ABBREVIATION'),
                'jersey_number': player_data.get('JERSEY_NUMBER'),
                'position': player_data.get('POSITION'),
                'height': player_data.get('HEIGHT'),
                'weight': player_data.get('WEIGHT'),
                'college': player_data.get('COLLEGE'),
                'country': player_data.get('COUNTRY'),
                'roster_status': self._parse_float(player_data.get('ROSTER_STATUS'), 1.0)
            }

            # 验证必需字段
            if not all([parsed_data['person_id'], parsed_data['last_name'], parsed_data['first_name']]):
                self.logger.warning(f"Missing required fields for player {parsed_data.get('person_id')}")
                return None

            return PlayerProfile.model_validate(parsed_data)

        except ValidationError as ve:
            self.logger.error(f"Validation error parsing player: {str(ve)}")
            return None
        except Exception as e:
            self.logger.error(f"Error parsing player data: {str(e)}")
            return None

    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效（默认24小时内有效）"""
        if not self.cache_file.exists():
            return False

        cache_time = datetime.fromtimestamp(self.cache_file.stat().st_mtime)
        return datetime.now() - cache_time < timedelta(hours=24)

    def _load_from_cache(self) -> Optional[List[PlayerProfile]]:
        """从缓存加载数据"""
        try:
            if not self.cache_file.exists():
                return None

            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [PlayerProfile.model_validate(p) for p in data]
        except Exception as e:
            self.logger.error(f"Error loading from cache: {str(e)}")
            return None

    def _save_to_cache(self, players: List[PlayerProfile]) -> None:
        """保存数据到缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump([p.model_dump() for p in players], f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving to cache: {str(e)}")

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