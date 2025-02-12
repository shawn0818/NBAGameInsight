from typing import Dict, List, Optional, Any

from pydantic import ValidationError, BaseModel

from nba.models.player_model import PlayerInfo, CommonPlayerInfo, PlayerHeadlineStats, AvailableSeason
from utils.logger_handler import AppLogger


class PlayerParser:
    """NBA球员数据解析器 (单个球员信息)"""

    def __init__(self):
        """初始化解析器"""
        self.logger = AppLogger.get_logger(__name__, app_name='nba')


    def parse_player_info(self, raw_data: Dict[str, Any]) -> Optional[PlayerInfo]:
        """
        解析API响应数据为 PlayerInfo 对象

        Args:
            raw_data: 从 commonplayerinfo API 获取的原始 JSON 数据

        Returns:
            Optional[PlayerInfo]: 解析后的球员详细信息，解析失败时返回 None
        """
        try:
            # 验证数据结构
            if not self._validate_raw_data(raw_data):
                return None

            result_sets = raw_data['resultSets']
            parsed_data = {}

            # 解析 CommonPlayerInfo
            common_player_info_set = next((rs for rs in result_sets if rs['name'] == 'CommonPlayerInfo'), None)
            if common_player_info_set:
                common_player_info_list = self._parse_result_set(common_player_info_set, CommonPlayerInfo)
                parsed_data['common_player_info'] = common_player_info_list

            # 解析 PlayerHeadlineStats
            player_headline_stats_set = next((rs for rs in result_sets if rs['name'] == 'PlayerHeadlineStats'), None)
            if player_headline_stats_set:
                player_headline_stats_list = self._parse_result_set(player_headline_stats_set, PlayerHeadlineStats)
                parsed_data['player_headline_stats'] = player_headline_stats_list

            # 解析 AvailableSeasons
            available_seasons_set = next((rs for rs in result_sets if rs['name'] == 'AvailableSeasons'), None)
            if available_seasons_set:
                available_seasons_list = self._parse_result_set(available_seasons_set, AvailableSeason)
                parsed_data['available_seasons'] = available_seasons_list

            return PlayerInfo.model_validate(parsed_data)


        except Exception as e:
            self.logger.error(f"Error parsing player data: {str(e)}")
            return None

    def _validate_raw_data(self, data: Dict[str, Any]) -> bool:
        """验证原始数据的基本结构"""
        if not isinstance(data, dict):
            self.logger.error("Input data must be a dictionary")
            return False

        if 'resultSets' not in data or not data['resultSets']:
            self.logger.error("Missing or empty resultSets")
            return False
        return True


    def _parse_result_set(self, result_set: Dict, model_class: type) -> List[BaseModel]:
        """解析单个 resultSet"""
        items = []
        headers = result_set['headers']
        rows = result_set['rowSet']
        field_map = {header: idx for idx, header in enumerate(headers)}

        for row in rows:
            try:
                item_data = PlayerParser._map_row_to_dict(row, field_map)
                item = model_class.model_validate(item_data)
                items.append(item)
            except ValidationError as ve:
                self.logger.error(f"Validation error parsing {model_class.__name__} row: {str(ve)}")
            except Exception as e:
                self.logger.error(f"Error parsing {model_class.__name__} row: {str(e)}")
        return items

    @staticmethod
    def _map_row_to_dict(row: List[Any], field_map: Dict[str, int]) -> Dict[str, Any]:
        """
        将行数据映射为字典格式

        Args:
            row (List[Any]): 数据行
            field_map (Dict[str, int]): 字段名到索引的映射

        Returns:
            Dict[str, Any]: 字段名到值的映射字典

        Example:
            row = [1, "John", 25]
            field_map = {"id": 0, "name": 1, "age": 2}
            PlayerParser._map_row_to_dict(row, field_map)
            {'id': 1, 'name': 'John', 'age': 25}
        """
        return {
            field: row[idx] if idx < len(row) else None
            for field, idx in field_map.items()
        }


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