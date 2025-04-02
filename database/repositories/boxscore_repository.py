# database/repositories/boxscore_repository.py
from typing import Dict, List, Optional
from sqlalchemy import desc
from database.models.stats_models import Statistics
from database.db_session import DBSession
from utils.logger_handler import AppLogger


class BoxscoreRepository:
    """
    比赛数据访问对象 - 专注于查询操作
    使用SQLAlchemy ORM进行数据访问
    """

    def __init__(self):
        """初始化比赛数据访问对象"""
        self.db_session = DBSession.get_instance()
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')

    @staticmethod
    def _to_dict(model_instance):
        """将模型实例转换为字典"""
        if model_instance is None:
            return None

        result = {}
        for column in model_instance.__table__.columns:
            result[column.name] = getattr(model_instance, column.name)
        return result

    def get_boxscore(self, game_id: str) -> Optional[Dict]:
        """
        获取比赛基本统计信息

        Args:
            game_id: 比赛ID

        Returns:
            Optional[Dict]: 比赛统计信息，未找到时返回None
        """
        try:
            with self.db_session.session_scope('game') as session:
                boxscore = session.query(Statistics).filter(
                    Statistics.game_id == game_id
                ).first()

                if boxscore:
                    return BoxscoreRepository._to_dict(boxscore)
                return None

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
            with self.db_session.session_scope('game') as session:
                query = session.query(Statistics).filter(
                    Statistics.game_id == game_id
                )

                if player_id:
                    query = query.filter(Statistics.person_id == player_id)
                else:
                    query = query.order_by(
                        Statistics.team_id,
                        desc(Statistics.points)
                    )

                stats = query.all()
                return [BoxscoreRepository._to_dict(stat) for stat in stats]

        except Exception as e:
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
            with self.db_session.session_scope('game') as session:
                query = session.query(Statistics).filter(
                    Statistics.game_id == game_id
                )

                if team_id:
                    query = query.filter(Statistics.team_id == team_id)

                stats = query.all()
                return [self._to_dict(stat) for stat in stats]

        except Exception as e:
            self.logger.error(f"获取球队统计数据失败: {e}")
            return []

