# database/repositories/playbyplay_repository.py
from typing import Dict, List, Optional
from sqlalchemy import and_
from database.models.stats_models import Event
from database.db_session import DBSession
from utils.logger_handler import AppLogger


class PlayByPlayRepository:
    """
    比赛回合数据访问对象 - 专注于查询操作
    使用SQLAlchemy ORM进行数据访问
    """

    def __init__(self):
        """初始化比赛回合数据访问对象"""
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
            with self.db_session.session_scope('game') as session:
                query = session.query(Event).filter(Event.game_id == game_id)

                if period:
                    query = query.filter(Event.period == period)

                if period:
                    query = query.order_by(Event.action_number)
                else:
                    query = query.order_by(Event.period, Event.action_number)

                actions = query.all()

                result = []
                for action in actions:
                    result.append(PlayByPlayRepository._to_dict(action))

                return result

        except Exception as e:
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
            with self.db_session.session_scope('game') as session:
                actions = session.query(Event).filter(
                    and_(
                        Event.game_id == game_id,
                        Event.person_id == player_id
                    )
                ).order_by(Event.period, Event.action_number).all()

                result = []
                for action in actions:
                    result.append(PlayByPlayRepository._to_dict(action))

                return result

        except Exception as e:
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
            with self.db_session.session_scope('game') as session:
                actions = session.query(Event).filter(
                    and_(
                        Event.game_id == game_id,
                        Event.is_field_goal == 1,
                        Event.shot_result == 'Made'
                    )
                ).order_by(Event.period, Event.action_number).all()

                result = []
                for action in actions:
                    result.append(PlayByPlayRepository._to_dict(action))

                return result

        except Exception as e:
            self.logger.error(f"获取比赛得分回合失败: {e}")
            return []

