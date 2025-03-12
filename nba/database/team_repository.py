import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
from utils.logger_handler import AppLogger


class TeamRepository:
    """
    球队数据访问对象
    负责team表的CRUD操作
    """

    def __init__(self, db_manager):
        """初始化球队数据访问对象"""
        self.db_manager = db_manager
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def save_team(self, team_data: Dict) -> bool:
        """
        保存或更新球队信息

        Args:
            team_data: 包含球队信息的字典，字段与API返回的TeamBackground保持一致
                {
                    'TEAM_ID': int,
                    'ABBREVIATION': str,
                    'NICKNAME': str,
                    'YEARFOUNDED': int,
                    'CITY': str,
                    'ARENA': str,
                    'ARENACAPACITY': str,
                    'OWNER': str,
                    'GENERALMANAGER': str,
                    'HEADCOACH': str,
                    'DLEAGUEAFFILIATION': str,
                    'team_slug': str,  # 额外的URL友好标识符
                }

        Returns:
            bool: 操作是否成功
        """
        try:
            conn = self.db_manager.conn
            cursor = conn.cursor()

            # 准备数据
            team_id = team_data.get('TEAM_ID')
            updated_at = datetime.now().isoformat()

            # 为team_slug字段生成值（如果不存在）
            if 'team_slug' not in team_data and 'NICKNAME' in team_data:
                team_data['team_slug'] = team_data['NICKNAME'].lower().replace(' ', '-')

            # 检查是否已存在该球队
            cursor.execute("SELECT TEAM_ID FROM team WHERE TEAM_ID = ?", (team_id,))
            exists = cursor.fetchone()

            if exists:
                # 更新现有记录
                set_clause = ", ".join(
                    [f"{key} = ?" for key in team_data.keys() if key != 'TEAM_ID']) + ", updated_at = ?"
                values = [team_data[key] for key in team_data.keys() if key != 'TEAM_ID'] + [updated_at, team_id]

                query = f"UPDATE team SET {set_clause} WHERE TEAM_ID = ?"
                cursor.execute(query, values)

                self.logger.debug(f"更新球队: {team_data.get('NICKNAME')} (ID: {team_id})")
            else:
                # 插入新记录
                fields = list(team_data.keys()) + ['updated_at']
                placeholders = ", ".join(["?"] * (len(fields)))
                values = [team_data[key] for key in team_data.keys()] + [updated_at]

                query = f"INSERT INTO team ({', '.join(fields)}) VALUES ({placeholders})"
                cursor.execute(query, values)

                self.logger.info(f"新增球队: {team_data.get('NICKNAME')} (ID: {team_id})")

            conn.commit()
            return True

        except sqlite3.Error as e:
            self.logger.error(f"保存球队数据失败: {e}")
            self.db_manager.conn.rollback()  # 直接使用db_manager的连接
            return False

    def batch_save_teams(self, teams_data: List[Dict]) -> int:
        """
        批量保存球队信息

        Args:
            teams_data: 球队数据列表

        Returns:
            int: 成功插入/更新的记录数
        """
        success_count = 0
        for team_data in teams_data:
            if self.save_team(team_data):
                success_count += 1

        self.logger.info(f"批量保存球队数据: {success_count}/{len(teams_data)} 成功")
        return success_count

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
            cursor.execute("SELECT * FROM team WHERE TEAM_ID = ?", (team_id,))
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
            cursor.execute("SELECT * FROM team WHERE ABBREVIATION = ? COLLATE NOCASE", (abbr,))
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
            WHERE NICKNAME LIKE ? COLLATE NOCASE 
               OR CITY LIKE ? COLLATE NOCASE
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
            cursor.execute("SELECT * FROM team ORDER BY CITY, NICKNAME")

            teams = cursor.fetchall()
            return [dict(team) for team in teams]

        except sqlite3.Error as e:
            self.logger.error(f"获取所有球队数据失败: {e}")
            return []

    def save_team_logo(self, team_id: int, logo_data: bytes) -> bool:
        """
        保存球队logo的二进制数据

        Args:
            team_id: 球队ID
            logo_data: 二进制图像数据

        Returns:
            bool: 操作是否成功
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("UPDATE team SET logo = ? WHERE TEAM_ID = ?",
                           (logo_data, team_id))
            self.db_manager.conn.commit()
            self.logger.debug(f"保存球队(ID:{team_id})logo成功")
            return True
        except sqlite3.Error as e:
            self.logger.error(f"保存球队logo失败: {e}")
            self.db_manager.conn.rollback()
            return False

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
            cursor.execute("SELECT logo FROM team WHERE TEAM_ID = ?", (team_id,))
            result = cursor.fetchone()
            return result['logo'] if result else None
        except sqlite3.Error as e:
            self.logger.error(f"获取球队logo失败: {e}")
            return None

    def sync_team_logos(self) -> int:
        """
        同步所有球队的logo

        Returns:
            int: 成功同步的logo数量
        """
        import requests

        success_count = 0
        teams = self.get_all_teams()
        for team in teams:
            team_id = team['TEAM_ID']

            # 尝试不同的logo格式
            logo_urls = [
                f"https://cdn.nba.com/logos/nba/{team_id}/global/L/logo.svg",
                f"https://cdn.nba.com/logos/nba/{team_id}/global/L/logo.png"
            ]

            for url in logo_urls:
                try:
                    response = requests.get(url, timeout=10)
                    if response.status_code == 200:
                        # 成功获取logo
                        logo_data = response.content
                        if self.save_team_logo(team_id, logo_data):
                            success_count += 1
                            self.logger.info(f"同步球队(ID:{team_id})logo成功")
                            break  # 成功获取一个格式后跳出内循环
                except Exception as e:
                    self.logger.error(f"获取球队(ID:{team_id})logo失败: {e}")

        return success_count

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
            cursor.execute("SELECT ARENA FROM team WHERE TEAM_ID = ?", (team_id,))
            result = cursor.fetchone()
            return result is not None and result['ARENA'] is not None
        except sqlite3.Error as e:
            self.logger.error(f"检查球队详细信息失败: {e}")
            return False