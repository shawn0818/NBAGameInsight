# game_stats_service.py
from typing import Dict, List, Optional, Union
from datetime import datetime

from utils.logger_handler import AppLogger


class GameStatsService:
    """统一的比赛统计数据访问接口，负责数据同步和查询"""

    def __init__(self, db_path: Optional[str] = None, env: str = "default"):
        """
        初始化比赛统计数据服务

        Args:
            db_path: 数据库文件路径，如果为None则使用配置中的默认路径
            env: 环境名称，可以是 "default", "test", "development", "production"
        """
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        # 如果未提供db_path，则使用配置中的路径
        if db_path is None:
            from config import NBAConfig
            db_path = str(NBAConfig.DATABASE.get_db_path(env))

        # 导入并创建数据库管理器
        from nba.database.game_stats.game_stats_db_manager import GameStatsDBManager
        self.db_manager = GameStatsDBManager(db_path)

        # 创建同步管理器
        from nba.database.game_stats.game_stats_sync_manager import GameStatsSyncManager
        self.sync_manager = GameStatsSyncManager(self.db_manager)

        # 延迟初始化仓库对象
        self._statistics_repository = None
        self._events_repository = None

    def get_database_path(self) -> str:
        """获取当前使用的数据库文件路径"""
        return self.db_manager.db_path

    # 获取仓库对象的懒加载方法
    def get_boxscore_repository(self):
        if not self._statistics_repository:
            from nba.database.game_stats.statistics_repository import BoxscoreRepository
            self._statistics_repository = BoxscoreRepository(self.db_manager)
        return self._statistics_repository

    def get_playbyplay_repository(self):
        if not self._events_repository:
            from nba.database.game_stats.playbyplay_repository import PlayByPlayRepository
            self._events_repository = PlayByPlayRepository(self.db_manager)
        return self._events_repository

    # ======== 同步相关方法 ========

    def sync_game(self, game_id: str, force_update: bool = False) -> Dict:
        """
        同步指定比赛的统计数据、回合数据
        Args:
            game_id: 比赛ID
            force_update: 是否强制更新

        Returns:
            Dict: 同步结果
        """
        try:
            result = self.sync_manager.sync_game_data(game_id, force_update)
            return result
        except Exception as e:
            self.logger.error(f"同步比赛(ID:{game_id})数据失败: {e}")
            return {"status": "failed", "error": str(e)}

    def batch_sync_games(self, game_ids: List[str], force_update: bool = False) -> Dict:
        """
        批量同步多场比赛的数据

        Args:
            game_ids: 比赛ID列表
            force_update: 是否强制更新

        Returns:
            Dict: 同步结果
        """
        try:
            result = self.sync_manager.batch_sync_games(game_ids, force_update)
            return result
        except Exception as e:
            self.logger.error(f"批量同步比赛数据失败: {e}")
            return {"status": "failed", "error": str(e)}

    # ======== 查询统计数据方法 ========

    def get_boxscore(self, game_id: str) -> Optional[Dict]:
        """
        获取比赛统计数据

        Args:
            game_id: 比赛ID

        Returns:
            Optional[Dict]: 比赛统计数据，未找到时返回None
        """
        try:
            repo = self.get_boxscore_repository()
            return repo.get_boxscore(game_id)
        except Exception as e:
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
            repo = self.get_boxscore_repository()
            return repo.get_player_stats(game_id, player_id)
        except Exception as e:
            self.logger.error(f"获取球员统计数据失败: {e}")
            return []

    def get_player_history_stats(self, player_id: int, limit: Optional[int] = None) -> List[Dict]:
        """
        获取球员历史统计数据

        Args:
            player_id: 球员ID
            limit: 限制返回的比赛数量，不提供则返回所有

        Returns:
            List[Dict]: 球员历史统计数据列表
        """
        try:
            repo = self.get_boxscore_repository()
            query = """
                SELECT * FROM statistics 
                WHERE person_id = ? 
                ORDER BY game_date DESC
            """
            params = [player_id]

            if limit is not None and limit > 0:
                query += " LIMIT ?"
                params.append(limit)

            cursor = self.db_manager.conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"获取球员历史统计数据失败: {e}")
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
            repo = self.get_boxscore_repository()
            return repo.get_team_stats(game_id, team_id)
        except Exception as e:
            self.logger.error(f"获取球队统计数据失败: {e}")
            return []

    def get_team_history_stats(self, team_id: int, limit: Optional[int] = None) -> List[Dict]:
        """
        获取球队历史统计数据

        此方法返回球队在不同比赛中的统计数据汇总

        Args:
            team_id: 球队ID
            limit: 限制返回的比赛数量，不提供则返回所有

        Returns:
            List[Dict]: 球队历史统计数据列表
        """
        try:
            query = """
                SELECT 
                    game_id, 
                    game_date,
                    team_id,
                    COUNT(*) as player_count,
                    SUM(points) as total_points,
                    SUM(assists) as total_assists,
                    SUM(rebounds_total) as total_rebounds,
                    SUM(steals) as total_steals,
                    SUM(blocks) as total_blocks,
                    SUM(turnovers) as total_turnovers,
                    AVG(plus_minus_points) as avg_plus_minus
                FROM statistics 
                WHERE team_id = ? 
                GROUP BY game_id, game_date, team_id
                ORDER BY game_date DESC
            """
            params = [team_id]

            if limit is not None and limit > 0:
                query += " LIMIT ?"
                params.append(limit)

            cursor = self.db_manager.conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"获取球队历史统计数据失败: {e}")
            return []

    # ======== 查询回合数据方法 ========

    def get_playbyplay(self, game_id: str) -> Optional[Dict]:
        """
        获取比赛回合数据

        Args:
            game_id: 比赛ID

        Returns:
            Optional[Dict]: 比赛回合数据，未找到时返回None
        """
        try:
            repo = self.get_playbyplay_repository()
            return repo.get_playbyplay(game_id)
        except Exception as e:
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
            repo = self.get_playbyplay_repository()
            return repo.get_play_actions(game_id, period)
        except Exception as e:
            self.logger.error(f"获取比赛回合动作详情失败: {e}")
            return []

    def get_player_shots(self, player_id: int, limit: Optional[int] = None) -> List[Dict]:
        """
        获取球员的投篮数据

        从events表中获取球员的所有投篮记录

        Args:
            player_id: 球员ID
            limit: 限制返回的记录数量，不提供则返回所有

        Returns:
            List[Dict]: 球员投篮记录列表
        """
        try:
            query = """
                SELECT * FROM events 
                WHERE person_id = ? AND is_field_goal = 1
                ORDER BY game_id DESC, period ASC, action_number ASC
            """
            params = [player_id]

            if limit is not None and limit > 0:
                query += " LIMIT ?"
                params.append(limit)

            cursor = self.db_manager.conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"获取球员投篮数据失败: {e}")
            return []

    def close(self):
        """关闭数据库连接"""
        try:
            if self.db_manager:
                self.db_manager.close()
                self.logger.info("数据库连接已关闭")
        except Exception as e:
            self.logger.error(f"关闭数据库连接失败: {e}")