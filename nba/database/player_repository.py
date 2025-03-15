import sqlite3
from typing import Dict, List, Optional
from utils.logger_handler import AppLogger


class PlayerRepository:
    """
    球员数据访问对象
    负责player表的CRUD操作
    """

    def __init__(self, db_manager):
        """初始化球员数据访问对象"""
        self.db_manager = db_manager
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def get_player_id_by_name(self, name: str) -> Optional[int]:
        """
        通过球员名称查询ID，支持模糊匹配
        增强了单个名字或姓氏的匹配能力

        Args:
            name: 球员名称(全名、姓、名、slug等)

        Returns:
            Optional[int]: 球员ID，未找到或模糊匹配度不足时返回None
        """
        if not name:
            return None

        try:
            # 标准化输入
            normalized_name = name.lower().strip()
            cursor = self.db_manager.conn.cursor()

            # 1. 精确匹配 - 首先尝试精确匹配全名
            cursor.execute("""
            SELECT person_id FROM player 
            WHERE LOWER(display_first_last) = ? OR 
                  LOWER(display_last_comma_first) = ? OR 
                  LOWER(player_slug) = ?
            LIMIT 1
            """, (normalized_name, normalized_name, normalized_name))

            result = cursor.fetchone()
            if result:
                return result['person_id']

            # 2. 如果输入是单个词（可能是姓或名），尝试单独匹配
            name_parts = normalized_name.split()
            if len(name_parts) == 1:
                single_term = name_parts[0]

                # 尝试匹配姓氏或名字（作为单独一部分）
                cursor.execute("""
                SELECT person_id, display_first_last 
                FROM player
                WHERE 
                    LOWER(display_first_last) LIKE ? OR
                    LOWER(display_last_comma_first) LIKE ?
                """, (f"% {single_term}", f"{single_term},%"))

                matches = cursor.fetchall()
                if matches:
                    # 如果只有一个匹配结果，直接返回
                    if len(matches) == 1:
                        return matches[0]['person_id']

                    # 对于知名球员，可以设置优先级
                    for match in matches:
                        full_name = match['display_first_last'].lower()
                        # 检查是否是知名球员（这里可以添加更多知名球员）
                        if (single_term == 'curry' and 'stephen curry' in full_name) or \
                                (single_term == 'james' and 'lebron james' in full_name) or \
                                (single_term == 'durant' and 'kevin durant' in full_name) or \
                                (single_term == 'antetokounmpo' and 'giannis antetokounmpo' in full_name):
                            return match['person_id']

            # 3. 常规模糊匹配 - 如果前面的匹配都失败，尝试模糊匹配
            name_pattern = f"%{normalized_name}%"
            cursor.execute("""
            SELECT person_id, display_first_last, display_last_comma_first, player_slug FROM player 
            WHERE LOWER(display_first_last) LIKE ? OR 
                  LOWER(display_last_comma_first) LIKE ? OR 
                  LOWER(player_slug) LIKE ?
            """, (name_pattern, name_pattern, name_pattern))

            matches = cursor.fetchall()
            if not matches:
                return None

            # 如果只有一个匹配，直接返回
            if len(matches) == 1:
                return matches[0]['person_id']

            # 4. 如果有多个匹配，使用fuzzywuzzy进一步确定最佳匹配
            from fuzzywuzzy import process

            # 为每个匹配创建一个包含所有可能匹配字段的组合字符串
            match_strings = []
            for match in matches:
                # 组合所有字段，确保不是None
                display_first_last = match['display_first_last'] or ""
                display_last_comma_first = match['display_last_comma_first'] or ""
                player_slug = match['player_slug'] or ""
                # 组合所有可能的匹配字符串
                match_str = f"{display_first_last} {display_last_comma_first} {player_slug}".lower()
                match_strings.append((match_str, match['person_id']))

            # 使用fuzzywuzzy找出最佳匹配
            best_match = process.extractOne(normalized_name, [m[0] for m in match_strings])
            if best_match and best_match[1] >= 50:  # 设置一个合理的匹配阈值
                idx = [m[0] for m in match_strings].index(best_match[0])
                return match_strings[idx][1]

            # 如果没有找到合适的匹配
            return None

        except sqlite3.Error as e:
            self.logger.error(f"通过名称查询球员ID失败: {e}")
            return None

    def get_player_name_by_id(self, player_id: int, name_type: str = 'full') -> Optional[str]:
        """
        通过ID获取球员名称

        Args:
            player_id: 球员ID
            name_type: 返回的名称类型，可选值:
                      'full' - 完整名称(名姓格式，如 LeBron James)
                      'last_first' - 姓名格式(如 James, LeBron)
                      'first' - 仅名字(从完整名称中提取第一部分)
                      'last' - 仅姓氏(从完整名称中提取最后部分)

        Returns:
            Optional[str]: 球员名称，未找到时返回None
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("""
            SELECT display_first_last, display_last_comma_first
            FROM player
            WHERE person_id = ?
            """, (player_id,))

            player = cursor.fetchone()
            if not player:
                return None

            # 根据请求的名称类型返回不同格式
            if name_type.lower() == 'last_first':
                return player['display_last_comma_first']
            elif name_type.lower() == 'first':
                full_name = player['display_first_last']
                return full_name.split(' ')[0] if ' ' in full_name else full_name
            elif name_type.lower() == 'last':
                full_name = player['display_first_last']
                return full_name.split(' ')[-1] if ' ' in full_name else ''
            else:  # 默认返回完整名称 (full)
                return player['display_first_last']

        except sqlite3.Error as e:
            self.logger.error(f"通过ID获取球员名称失败: {e}")
            return None

    def get_all_players(self) -> List[Dict]:
        """
        获取所有球员信息

        Returns:
            List[Dict]: 所有球员信息列表
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("SELECT * FROM player ORDER BY display_first_last")
            players = cursor.fetchall()
            return [dict(player) for player in players]

        except sqlite3.Error as e:
            self.logger.error(f"获取所有球员数据失败: {e}")
            return []



