import sqlite3
from typing import Dict, List, Optional, Union
from utils.logger_handler import AppLogger


class PlayByPlayRepository:
    """
    比赛回合数据访问对象 - 专注于查询操作
    """

    def __init__(self, db_manager):
        """初始化比赛回合数据访问对象"""
        self.db_manager = db_manager
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def get_playbyplay(self, game_id: str) -> Optional[Dict]:
        """
        获取比赛回合数据

        Args:
            game_id: 比赛ID

        Returns:
            Optional[Dict]: 比赛回合数据，未找到时返回None
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("SELECT * FROM events WHERE game_id = ?", (game_id,))
            playbyplay = cursor.fetchone()

            if playbyplay:
                return dict(playbyplay)
            return None

        except sqlite3.Error as e:
            self.logger.error(f"获取比赛回合数据失败: {e}")
            return None

    def get_play_actions(self, game_id: str, period: Optional[int] = None) -> List[Dict]:
        """
        获取比赛回合动作详情

        Args:
            game_id: 比赛ID
            period: 可选的比赛节数，如果提供则只返回该节的数据

        Returns:
            List[Dict]: 回合动作详情列表
        """
        try:
            cursor = self.db_manager.conn.cursor()

            if period:
                cursor.execute("""
                SELECT * FROM events 
                WHERE game_id = ? AND period = ?
                ORDER BY action_number
                """, (game_id, period))
            else:
                cursor.execute("""
                SELECT * FROM events 
                WHERE game_id = ?
                ORDER BY period, action_number
                """, (game_id,))

            actions = cursor.fetchall()
            return [dict(action) for action in actions]

        except sqlite3.Error as e:
            self.logger.error(f"获取比赛回合动作详情失败: {e}")
            return []

    def get_player_actions(self, game_id: str, player_id: int) -> List[Dict]:
        """
        获取球员在比赛中的所有动作

        Args:
            game_id: 比赛ID
            player_id: 球员ID

        Returns:
            List[Dict]: 回合动作详情列表
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("""
            SELECT * FROM events 
            WHERE game_id = ? AND person_id = ?
            ORDER BY period, action_number
            """, (game_id, player_id))

            actions = cursor.fetchall()
            return [dict(action) for action in actions]

        except sqlite3.Error as e:
            self.logger.error(f"获取球员比赛动作失败: {e}")
            return []

    def get_scoring_plays(self, game_id: str) -> List[Dict]:
        """
        获取比赛中的所有得分回合

        Args:
            game_id: 比赛ID

        Returns:
            List[Dict]: 得分回合列表
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("""
            SELECT * FROM events 
            WHERE game_id = ? AND is_field_goal = 1 AND shot_result = 'Made'
            ORDER BY period, action_number
            """, (game_id,))

            actions = cursor.fetchall()
            return [dict(action) for action in actions]

        except sqlite3.Error as e:
            self.logger.error(f"获取比赛得分回合失败: {e}")
            return []
