# database/repositories/playbyplay_repository.py
from typing import Dict, List, Optional, Union
from sqlalchemy import and_
from database.models.stats_models import Event
from database.db_session import DBSession
from utils.logger_handler import AppLogger


class PlayByPlayRepository:
    """
    比赛回合数据访问对象 - 专注于查询操作
    支持内部会话和外部传入会话两种模式
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

        if hasattr(model_instance, 'to_dict') and callable(model_instance.to_dict):
            return model_instance.to_dict()

        result = {}
        for column in model_instance.__table__.columns:
            result[column.name] = getattr(model_instance, column.name)
        return result

    def get_play_actions(self, game_id: str, period: Optional[int] = None, session=None) -> Union[
        List[Event], List[Dict]]:
        """
        获取比赛回合动作详情

        Args:
            game_id: 比赛ID
            period: 可选的比赛节数，如果提供则只返回该节的数据
            session: 可选的外部会话对象

        Returns:
            List[Event]或List[Dict]: 回合动作详情列表
        """
        try:
            if session is not None:
                # 使用外部会话
                query = session.query(Event).filter(Event.game_id == game_id)

                if period:
                    query = query.filter(Event.period == period)

                if period:
                    query = query.order_by(Event.action_number)
                else:
                    query = query.order_by(Event.period, Event.action_number)

                return query.all()  # 直接返回ORM对象
            else:
                # 使用内部会话
                with self.db_session.session_scope('game') as internal_session:
                    query = internal_session.query(Event).filter(Event.game_id == game_id)

                    if period:
                        query = query.filter(Event.period == period)

                    if period:
                        query = query.order_by(Event.action_number)
                    else:
                        query = query.order_by(Event.period, Event.action_number)

                    actions = query.all()

                    # 在会话内转换为字典
                    result = []
                    for action in actions:
                        result.append(self._to_dict(action))

                    return result

        except Exception as e:
            self.logger.error(f"获取比赛回合动作详情失败: {e}")
            return []

    def get_player_actions(self, game_id: str, player_id: int, session=None) -> Union[List[Event], List[Dict]]:
        """
        获取球员在比赛中的所有动作

        Args:
            game_id: 比赛ID
            player_id: 球员ID
            session: 可选的外部会话对象

        Returns:
            List[Event]或List[Dict]: 回合动作详情列表
        """
        try:
            if session is not None:
                # 使用外部会话
                return session.query(Event).filter(
                    and_(
                        Event.game_id == game_id,
                        Event.person_id == player_id
                    )
                ).order_by(Event.period, Event.action_number).all()
            else:
                # 使用内部会话
                with self.db_session.session_scope('game') as internal_session:
                    actions = internal_session.query(Event).filter(
                        and_(
                            Event.game_id == game_id,
                            Event.person_id == player_id
                        )
                    ).order_by(Event.period, Event.action_number).all()

                    result = []
                    for action in actions:
                        result.append(self._to_dict(action))

                    return result

        except Exception as e:
            self.logger.error(f"获取球员比赛动作失败: {e}")
            return []

    def get_scoring_plays(self, game_id: str, session=None) -> Union[List[Event], List[Dict]]:
        """
        获取比赛中的所有得分回合

        Args:
            game_id: 比赛ID
            session: 可选的外部会话对象

        Returns:
            List[Event]或List[Dict]: 得分回合列表
        """
        try:
            if session is not None:
                # 使用外部会话
                return session.query(Event).filter(
                    and_(
                        Event.game_id == game_id,
                        Event.is_field_goal == 1,
                        Event.shot_result == 'Made'
                    )
                ).order_by(Event.period, Event.action_number).all()
            else:
                # 使用内部会话
                with self.db_session.session_scope('game') as internal_session:
                    actions = internal_session.query(Event).filter(
                        and_(
                            Event.game_id == game_id,
                            Event.is_field_goal == 1,
                            Event.shot_result == 'Made'
                        )
                    ).order_by(Event.period, Event.action_number).all()

                    result = []
                    for action in actions:
                        result.append(self._to_dict(action))

                    return result

        except Exception as e:
            self.logger.error(f"获取比赛得分回合失败: {e}")
            return []