import sqlite3
from datetime import datetime, date, timezone
from typing import Dict, List, Optional, Union
from utils.logger_handler import AppLogger


class ScheduleRepository:
    """
    赛程数据访问对象 - 专注于查询操作
    """

    def __init__(self, db_manager):
        """初始化赛程数据访问对象"""
        self.db_manager = db_manager
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def get_game_id(self, team_id: int, date_query: Union[str, datetime.date, datetime, None] = 'today') -> Optional[
        str]:
        """
        获取指定球队在特定日期的比赛ID

        Args:
            team_id: 球队ID
            date_query: 日期查询参数，可以是:
                        - 'today': 今天的比赛
                        - 'next': 下一场比赛
                        - 'last': 最近一场比赛
                        - 具体日期字符串('YYYY-MM-DD')
                        - datetime.date或datetime对象
                        - None: 默认为今天

        Returns:
            Optional[str]: 比赛ID，未找到时返回None
        """
        try:
            # 处理日期关键字查询
            if isinstance(date_query, str):
                date_query = date_query.lower()

                # 处理特殊关键字
                if date_query == 'next':
                    # 获取下一场比赛
                    next_game = self.get_team_next_schedule(team_id)
                    return next_game['game_id'] if next_game else None

                elif date_query == 'last':
                    # 获取上一场比赛
                    last_game = self.get_team_last_schedule(team_id)
                    return last_game['game_id'] if last_game else None

                elif date_query == 'today':
                    # 转换为今天的日期
                    date_query = datetime.now().date()
                else:
                    # 尝试解析为日期
                    try:
                        date_query = datetime.strptime(date_query, '%Y-%m-%d').date()
                    except ValueError:
                        self.logger.error(f"无效的日期格式: {date_query}")
                        return None

            # 处理日期对象
            if isinstance(date_query, datetime):
                date_query = date_query.date()

            # 此时date_query应该是一个日期对象
            if isinstance(date_query, date):
                # 转换为标准日期字符串
                date_str = date_query.strftime('%Y-%m-%d')

                cursor = self.db_manager.conn.cursor()
                cursor.execute("""
                SELECT game_id FROM games 
                WHERE (home_team_id = ? OR away_team_id = ?) 
                  AND game_date = ?
                ORDER BY game_date_time_utc
                LIMIT 1
                """, (team_id, team_id, date_str))

                result = cursor.fetchone()
                return result['game_id'] if result else None

            return None

        except sqlite3.Error as e:
            self.logger.error(f"获取比赛ID失败: {e}")
            return None

    def get_schedule_by_id(self, game_id: str) -> Optional[Dict]:
        """
        通过ID获取赛程信息

        Args:
            game_id: 比赛ID

        Returns:
            Optional[Dict]: 赛程信息字典，未找到时返回None
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("SELECT * FROM games WHERE game_id = ?", (game_id,))
            schedule = cursor.fetchone()

            if schedule:
                return dict(schedule)
            return None

        except sqlite3.Error as e:
            self.logger.error(f"获取赛程(ID:{game_id})数据失败: {e}")
            return None

    def get_schedules_by_date(self, target_date: Union[str, date, datetime]) -> List[Dict]:
        """
        获取指定日期的赛程

        Args:
            target_date: 目标日期，可以是日期对象或YYYY-MM-DD格式的字符串

        Returns:
            List[Dict]: 匹配的赛程信息列表
        """
        try:
            cursor = self.db_manager.conn.cursor()

            # 将日期转换为string格式(YYYY-MM-DD)进行比较
            if isinstance(target_date, (date, datetime)):
                date_str = target_date.strftime('%Y-%m-%d')
            else:
                date_str = target_date

            cursor.execute('''
            SELECT * FROM games 
            WHERE game_date = ? 
            ORDER BY game_date_time_utc
            ''', (date_str,))

            schedules = cursor.fetchall()
            return [dict(schedule) for schedule in schedules]

        except sqlite3.Error as e:
            self.logger.error(f"获取日期({target_date})赛程数据失败: {e}")
            return []

    def get_schedules_by_team(self, team_id: int, limit: int = 10) -> List[Dict]:
        """
        获取指定球队的赛程

        Args:
            team_id: 球队ID
            limit: 最大返回数量

        Returns:
            List[Dict]: 匹配的赛程信息列表
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute('''
            SELECT * FROM games 
            WHERE home_team_id = ? OR away_team_id = ? 
            ORDER BY game_date_time_utc DESC 
            LIMIT ?
            ''', (team_id, team_id, limit))

            schedules = cursor.fetchall()
            return [dict(schedule) for schedule in schedules]

        except sqlite3.Error as e:
            self.logger.error(f"获取球队(ID:{team_id})赛程数据失败: {e}")
            return []

    def get_team_next_schedule(self, team_id: int) -> Optional[Dict]:
        """
        获取指定球队的下一场比赛

        Args:
            team_id: 球队ID

        Returns:
            Optional[Dict]: 下一场比赛信息，无下一场比赛时返回None
        """
        try:
            cursor = self.db_manager.conn.cursor()
            # 使用 datetime.now(timezone.utc) 替代 datetime.utcnow()
            now = datetime.now(timezone.utc).isoformat()

            cursor.execute('''
            SELECT * FROM games 
            WHERE (home_team_id = ? OR away_team_id = ?) 
              AND game_date_time_utc > ? 
              AND game_status = 1 
            ORDER BY game_date_time_utc 
            LIMIT 1
            ''', (team_id, team_id, now))

            schedule = cursor.fetchone()
            return dict(schedule) if schedule else None

        except sqlite3.Error as e:
            self.logger.error(f"获取球队(ID:{team_id})下一场比赛失败: {e}")
            return None

    def get_team_last_schedule(self, team_id: int) -> Optional[Dict]:
        """
        获取指定球队的上一场比赛

        Args:
            team_id: 球队ID

        Returns:
            Optional[Dict]: 上一场比赛信息，无上一场比赛时返回None
        """
        try:
            cursor = self.db_manager.conn.cursor()
            # 使用 datetime.now(timezone.utc) 替代 datetime.utcnow()
            now = datetime.now(timezone.utc).isoformat()

            cursor.execute('''
            SELECT * FROM games 
            WHERE (home_team_id = ? OR away_team_id = ?) 
              AND game_date_time_utc < ? 
            ORDER BY game_date_time_utc DESC 
            LIMIT 1
            ''', (team_id, team_id, now))

            schedule = cursor.fetchone()
            return dict(schedule) if schedule else None

        except sqlite3.Error as e:
            self.logger.error(f"获取球队(ID:{team_id})上一场比赛失败: {e}")
            return None

    def get_schedules_by_season(self, season: str, game_type: Optional[str] = None, limit: int = 1000) -> List[Dict]:
        """
        获取指定赛季的赛程

        Args:
            season: 赛季标识，如"2024-25"
            game_type: 比赛类型（季前赛、常规赛、季后赛等）
            limit: 最大返回数量

        Returns:
            List[Dict]: 匹配的赛程信息列表
        """
        try:
            cursor = self.db_manager.conn.cursor()

            if game_type:
                cursor.execute('''
                SELECT * FROM games 
                WHERE season_year = ? AND game_type = ?
                ORDER BY game_date_time_utc 
                LIMIT ?
                ''', (season, game_type, limit))
            else:
                cursor.execute('''
                SELECT * FROM games 
                WHERE season_year = ? 
                ORDER BY game_date_time_utc 
                LIMIT ?
                ''', (season, limit))

            schedules = cursor.fetchall()
            return [dict(schedule) for schedule in schedules]

        except sqlite3.Error as e:
            self.logger.error(f"获取赛季({season})赛程数据失败: {e}")
            return []

    def get_schedules_count_by_season(self, season: str) -> int:
        """
        获取指定赛季的赛程数量

        Args:
            season: 赛季标识

        Returns:
            int: 赛程数量
        """
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM games WHERE season_year = ?", (season,))
            result = cursor.fetchone()
            return result[0] if result else 0
        except sqlite3.Error as e:
            self.logger.error(f"获取赛季({season})赛程数量失败: {e}")
            return 0