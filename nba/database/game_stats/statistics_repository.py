# statistics_repository.py
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Union
from utils.logger_handler import AppLogger


class BoxscoreRepository:
    """
    比赛数据访问对象 - 专注于查询操作
    """

    def __init__(self, db_manager):
        """初始化比赛数据访问对象"""
        self.db_manager = db_manager
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def get_boxscore(self, game_id: str) -> Optional[Dict]:
        """
        获取比赛基本统计信息

        Args:
            game_id: 比赛ID

        Returns:
            Optional[Dict]: 比赛统计信息，未找到时返回None
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("SELECT * FROM statistics WHERE game_id = ?", (game_id,))
            boxscore = cursor.fetchone()

            if boxscore:
                return dict(boxscore)
            return None

        except sqlite3.Error as e:
            self.logger.error(f"获取比赛统计数据失败: {e}")
            return None

    def get_player_stats(self, game_id: str, player_id: Optional[int] = None) -> List[Dict]:
        """
        获取比赛中球员的统计数据

        Args:
            game_id: 比赛ID
            player_id: 可选的球员ID，如果提供则只返回该球员的数据

        Returns:
            List[Dict]: 球员统计数据列表
        """
        try:
            cursor = self.db_manager.conn.cursor()

            if player_id:
                cursor.execute("""
                SELECT * FROM statistics 
                WHERE game_id = ? AND person_id = ?
                """, (game_id, player_id))
            else:
                cursor.execute("""
                SELECT * FROM statistics 
                WHERE game_id = ?
                ORDER BY team_id, points DESC
                """, (game_id,))

            stats = cursor.fetchall()
            return [dict(stat) for stat in stats]

        except sqlite3.Error as e:
            self.logger.error(f"获取球员统计数据失败: {e}")
            return []

    def get_team_stats(self, game_id: str, team_id: Optional[int] = None) -> List[Dict]:
        """
        获取比赛中球队的统计数据

        Args:
            game_id: 比赛ID
            team_id: 可选的球队ID，如果提供则只返回该球队的数据

        Returns:
            List[Dict]: 球队统计数据列表
        """
        try:
            cursor = self.db_manager.conn.cursor()

            if team_id:
                cursor.execute("""
                SELECT * FROM statistics 
                WHERE game_id = ? AND team_id = ?
                """, (game_id, team_id))
            else:
                cursor.execute("""
                SELECT * FROM statistics 
                WHERE game_id = ?
                """, (game_id,))

            stats = cursor.fetchall()
            return [dict(stat) for stat in stats]

        except sqlite3.Error as e:
            self.logger.error(f"获取球队统计数据失败: {e}")
            return []

    def get_recent_games_by_player(self, player_id: int, limit: int = 10) -> List[Dict]:
        """
        获取球员最近的比赛统计数据

        Args:
            player_id: 球员ID
            limit: 返回的比赛数量

        Returns:
            List[Dict]: 比赛统计数据列表
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("""
            SELECT ps.*, b.game_date, b.home_team_id, b.away_team_id 
            FROM statistics ps
            JOIN statistics b ON ps.game_id = b.game_id
            WHERE ps.person_id = ?
            ORDER BY b.game_date DESC
            LIMIT ?
            """, (player_id, limit))

            stats = cursor.fetchall()
            return [dict(stat) for stat in stats]

        except sqlite3.Error as e:
            self.logger.error(f"获取球员最近比赛统计数据失败: {e}")
            return []

    def get_recent_games_by_team(self, team_id: int, limit: int = 10) -> List[Dict]:
        """
        获取球队最近的比赛统计数据

        Args:
            team_id: 球队ID
            limit: 返回的比赛数量

        Returns:
            List[Dict]: 比赛统计数据列表
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("""
            SELECT ts.*, b.game_date, b.home_team_id, b.away_team_id 
            FROM statistics ts
            JOIN statistics b ON ts.game_id = b.game_id
            WHERE ts.team_id = ?
            ORDER BY b.game_date DESC
            LIMIT ?
            """, (team_id, limit))

            stats = cursor.fetchall()
            return [dict(stat) for stat in stats]

        except sqlite3.Error as e:
            self.logger.error(f"获取球队最近比赛统计数据失败: {e}")
            return []