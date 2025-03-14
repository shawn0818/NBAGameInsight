import sqlite3
from typing import Dict, List, Optional
from utils.logger_handler import AppLogger


class TeamRepository:
    """
    球队数据访问对象 - 专注于查询操作
    """

    def __init__(self, db_manager):
        """初始化球队数据访问对象"""
        self.db_manager = db_manager
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def get_team_id_by_name(self, name: str) -> Optional[int]:
        """
        通过名称、缩写或slug获取球队ID(支持模糊匹配)

        Args:
            name: 球队名称、缩写或slug

        Returns:
            Optional[int]: 球队ID，未找到时返回None
        """
        if not name:
            return None

        try:
            # 标准化输入
            normalized_name = name.lower().strip()
            cursor = self.db_manager.conn.cursor()

            # 1. 精确匹配 - 首先尝试精确匹配
            cursor.execute("""
            SELECT team_id FROM team 
            WHERE LOWER(nickname) = ? OR 
                  LOWER(city) = ? OR 
                  LOWER(abbreviation) = ? OR 
                  LOWER(team_slug) = ?
            LIMIT 1
            """, (normalized_name, normalized_name, normalized_name, normalized_name))

            result = cursor.fetchone()
            if result:
                return result['team_id']

            # 2. 模糊匹配 - 如果精确匹配失败，尝试模糊匹配
            name_pattern = f"%{normalized_name}%"
            cursor.execute("""
            SELECT team_id, nickname, city, abbreviation, team_slug FROM team 
            WHERE LOWER(nickname) LIKE ? OR 
                  LOWER(city) LIKE ? OR 
                  LOWER(abbreviation) LIKE ? OR 
                  LOWER(team_slug) LIKE ?
            """, (name_pattern, name_pattern, name_pattern, name_pattern))

            matches = cursor.fetchall()
            if not matches:
                return None

            # 如果只有一个匹配，直接返回
            if len(matches) == 1:
                return matches[0]['team_id']

            # 3. 如果有多个匹配，使用fuzzywuzzy进一步确定最佳匹配
            from fuzzywuzzy import process

            # 为每个匹配创建一个包含所有可能匹配字段的组合字符串
            match_strings = []
            for match in matches:
                # 组合所有字段，确保不是None
                nickname = match['nickname'] or ""
                city = match['city'] or ""
                abbr = match['abbreviation'] or ""
                slug = match['team_slug'] or ""
                # 创建完整名称，如"Los Angeles Lakers"
                full_name = f"{city} {nickname}".strip()
                # 组合所有可能的匹配字符串
                match_str = f"{full_name} {nickname} {city} {abbr} {slug}".lower()
                match_strings.append((match_str, match['team_id']))

            # 使用fuzzywuzzy找出最佳匹配
            best_match = process.extractOne(normalized_name, [m[0] for m in match_strings])
            if best_match and best_match[1] >= 50:  # 设置一个合理的匹配阈值
                idx = [m[0] for m in match_strings].index(best_match[0])
                return match_strings[idx][1]

            # 如果没有找到合适的匹配
            return None

        except sqlite3.Error as e:
            self.logger.error(f"通过名称查询球队ID失败: {e}")
            return None

    def get_team_name_by_id(self, team_id: int, name_type: str = 'full') -> Optional[str]:
        """
        通过ID获取球队名称

        Args:
            team_id: 球队ID
            name_type: 返回的名称类型，可选值包括:
                      'full' - 完整名称 (城市+昵称)
                      'nickname' - 仅球队昵称
                      'city' - 仅城市名
                      'abbr' - 球队缩写

        Returns:
            Optional[str]: 球队名称，未找到时返回None
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("""
            SELECT nickname, city, abbreviation
            FROM team
            WHERE team_id = ?
            """, (team_id,))

            team = cursor.fetchone()
            if not team:
                return None

            # 根据请求的名称类型返回不同格式
            if name_type.lower() == 'nickname':
                return team['nickname']
            elif name_type.lower() == 'city':
                return team['city']
            elif name_type.lower() == 'abbr':
                return team['abbreviation']
            else:  # 默认返回完整名称
                return f"{team['city']} {team['nickname']}"

        except sqlite3.Error as e:
            self.logger.error(f"通过ID获取球队名称失败: {e}")
            return None

    def get_team_by_id(self, team_id: int) -> Optional[Dict]:
        """
        通过ID获取球队信息

        Args:
            team_id: 球队ID

        Returns:
            Optional[Dict]: 球队信息字典，未找到时返回None
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("SELECT * FROM team WHERE team_id = ?", (team_id,))
            team = cursor.fetchone()

            if team:
                return dict(team)
            return None

        except sqlite3.Error as e:
            self.logger.error(f"获取球队(ID:{team_id})数据失败: {e}")
            return None

    def get_team_by_abbr(self, abbr: str) -> Optional[Dict]:
        """
        通过缩写获取球队信息

        Args:
            abbr: 球队缩写

        Returns:
            Optional[Dict]: 球队信息字典，未找到时返回None
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("SELECT * FROM team WHERE abbreviation = ? COLLATE NOCASE", (abbr,))
            team = cursor.fetchone()

            if team:
                return dict(team)
            return None

        except sqlite3.Error as e:
            self.logger.error(f"获取球队(缩写:{abbr})数据失败: {e}")
            return None

    def get_team_by_name(self, name: str) -> Optional[Dict]:
        """
        通过名称获取球队信息(模糊匹配)

        Args:
            name: 球队名称(昵称或城市名)

        Returns:
            Optional[Dict]: 球队信息字典，未找到时返回None
        """
        try:
            cursor = self.db_manager.conn.cursor()
            name_pattern = f"%{name}%"

            cursor.execute('''
            SELECT * FROM team 
            WHERE nickname LIKE ? COLLATE NOCASE 
               OR city LIKE ? COLLATE NOCASE
            LIMIT 1
            ''', (name_pattern, name_pattern))

            team = cursor.fetchone()

            if team:
                return dict(team)
            return None

        except sqlite3.Error as e:
            self.logger.error(f"获取球队(名称:{name})数据失败: {e}")
            return None

    def get_all_teams(self) -> List[Dict]:
        """
        获取所有球队信息

        Returns:
            List[Dict]: 所有球队信息列表
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("SELECT * FROM team ORDER BY city, nickname")

            teams = cursor.fetchall()
            return [dict(team) for team in teams]

        except sqlite3.Error as e:
            self.logger.error(f"获取所有球队数据失败: {e}")
            return []

    def get_team_logo(self, team_id: int) -> Optional[bytes]:
        """
        获取球队logo数据

        Args:
            team_id: 球队ID

        Returns:
            Optional[bytes]: 二进制图像数据，未找到时返回None
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("SELECT logo FROM team WHERE team_id = ?", (team_id,))
            result = cursor.fetchone()
            return result['logo'] if result else None
        except sqlite3.Error as e:
            self.logger.error(f"获取球队logo失败: {e}")
            return None

    def has_team_details(self, team_id: int) -> bool:
        """
        检查球队是否有详细信息

        Args:
            team_id: 球队ID

        Returns:
            bool: 是否有详细信息
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("SELECT arena FROM team WHERE team_id = ?", (team_id,))
            result = cursor.fetchone()
            return result is not None and result['arena'] is not None
        except sqlite3.Error as e:
            self.logger.error(f"检查球队详细信息失败: {e}")
            return False