# repositories/playbyplay_repository.py
from typing import Dict, List, Optional
from sqlalchemy import and_
from database.models.stats_models import Event
from database.db_session import DBSession
from utils.logger_handler import AppLogger


class PlayByPlayRepository:
    """
    比赛回合数据访问对象 - 专注于查询操作
    """

    def __init__(self):
        """初始化比赛回合数据访问对象"""
        self.db_session = DBSession.get_instance()
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
            with self.db_session.session_scope('game') as session:
                event = session.query(Event).filter(Event.game_id == game_id).first()

                if event:
                    # 将ORM对象转换为字典
                    return {c.name: getattr(event, c.name) for c in event.__table__.columns}
                return None

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
            with self.db_session.session_scope('game') as session:
                query = session.query(Event).filter(Event.game_id == game_id)

                if period:
                    query = query.filter(Event.period == period)

                if period:
                    query = query.order_by(Event.action_number)
                else:
                    query = query.order_by(Event.period, Event.action_number)

                actions = query.all()

                # 将ORM对象转换为字典
                result = []
                for action in actions:
                    action_dict = {c.name: getattr(action, c.name) for c in action.__table__.columns}
                    result.append(action_dict)

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

                # 将ORM对象转换为字典
                result = []
                for action in actions:
                    action_dict = {c.name: getattr(action, c.name) for c in action.__table__.columns}
                    result.append(action_dict)

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

                # 将ORM对象转换为字典
                result = []
                for action in actions:
                    action_dict = {c.name: getattr(action, c.name) for c in action.__table__.columns}
                    result.append(action_dict)

                return result

        except Exception as e:
            self.logger.error(f"获取比赛得分回合失败: {e}")
            return []