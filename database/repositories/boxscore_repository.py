# database/repositories/boxscore_repository.py
from typing import List, Optional, Dict, Tuple, Union
from sqlalchemy import desc, func, and_, distinct, case
from database.models.stats_models import Statistics
from database.db_session import DBSession
from utils.logger_handler import AppLogger


class BoxscoreRepository:
    """
    比赛数据访问对象 - 专注于查询操作
    支持内部会话和外部传入会话两种模式
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

        if hasattr(model_instance, 'to_dict') and callable(model_instance.to_dict):
            return model_instance.to_dict()

        result = {}
        for column in model_instance.__table__.columns:
            result[column.name] = getattr(model_instance, column.name)
        return result

    def get_boxscore(self, game_id: str, session=None) -> Optional[Statistics]:
        """
        获取比赛基本统计信息

        Args:
            game_id: 比赛ID
            session: 可选的外部会话对象

        Returns:
            Optional[Statistics]: 比赛统计信息，未找到时返回None
        """
        try:
            if session is not None:
                # 使用外部会话
                return session.query(Statistics).filter(
                    Statistics.game_id == game_id
                ).first()
            else:
                # 使用内部会话
                with self.db_session.session_scope('game') as internal_session:
                    return internal_session.query(Statistics).filter(
                        Statistics.game_id == game_id
                    ).first()

        except Exception as e:
            self.logger.error(f"获取比赛统计数据失败: {e}")
            return None

    def get_player_stats(self, game_id: str, player_id: Optional[int] = None, session=None) -> Union[
        List[Statistics], List[Dict]]:
        """
        获取比赛中球员的统计数据

        Args:
            game_id: 比赛ID
            player_id: 可选的球员ID，如果提供则只返回该球员的数据
            session: 可选的外部会话对象

        Returns:
            List[Statistics]或List[Dict]: 球员统计数据列表
        """
        try:
            if session is not None:
                # 使用外部会话
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

                return query.all()  # 直接返回ORM对象
            else:
                # 使用内部会话
                with self.db_session.session_scope('game') as internal_session:
                    query = internal_session.query(Statistics).filter(
                        Statistics.game_id == game_id
                    )

                    if player_id:
                        query = query.filter(Statistics.person_id == player_id)
                    else:
                        query = query.order_by(
                            Statistics.team_id,
                            desc(Statistics.points)
                        )

                    # 在会话内转换为字典
                    stats = query.all()
                    return [self._to_dict(stat) for stat in stats]

        except Exception as e:
            self.logger.error(f"获取球员统计数据失败: {e}")
            return []

    def get_team_stats(self, game_id: str, team_id: Optional[int] = None, session=None) -> Union[
        List[Statistics], List[Dict]]:
        """
        获取比赛中球队的统计数据

        Args:
            game_id: 比赛ID
            team_id: 可选的球队ID，如果提供则只返回该球队的数据
            session: 可选的外部会话对象

        Returns:
            List[Statistics]或List[Dict]: 球队统计数据列表
        """
        try:
            if session is not None:
                # 使用外部会话
                query = session.query(Statistics).filter(
                    Statistics.game_id == game_id
                )

                if team_id:
                    query = query.filter(Statistics.team_id == team_id)

                return query.all()
            else:
                # 使用内部会话
                with self.db_session.session_scope('game') as internal_session:
                    query = internal_session.query(Statistics).filter(
                        Statistics.game_id == game_id
                    )

                    if team_id:
                        query = query.filter(Statistics.team_id == team_id)

                    # 在会话内转换为字典
                    stats = query.all()
                    return [self._to_dict(stat) for stat in stats]

        except Exception as e:
            self.logger.error(f"获取球队统计数据失败: {e}")
            return []

    # 以下方法类似修改，仅展示一部分关键方法
    def get_top_scorers(self, game_id: str, limit: int = 5, session=None) -> Union[List[Statistics], List[Dict]]:
        """获取比赛中得分最高的球员"""
        try:
            if session is not None:
                return session.query(Statistics).filter(
                    Statistics.game_id == game_id
                ).order_by(
                    desc(Statistics.points)
                ).limit(limit).all()
            else:
                with self.db_session.session_scope('game') as internal_session:
                    stats = internal_session.query(Statistics).filter(
                        Statistics.game_id == game_id
                    ).order_by(
                        desc(Statistics.points)
                    ).limit(limit).all()
                    return [self._to_dict(stat) for stat in stats]

        except Exception as e:
            self.logger.error(f"获取顶级得分手失败: {e}")
            return []

    def get_player_stats_by_criteria(self, game_id: str,
                                     min_points: Optional[int] = None,
                                     min_rebounds: Optional[int] = None,
                                     min_assists: Optional[int] = None,
                                     position: Optional[str] = None,
                                     session=None) -> Union[List[Statistics], List[Dict]]:
        """根据多种条件获取球员统计数据"""
        try:
            if session is not None:
                query = session.query(Statistics).filter(
                    Statistics.game_id == game_id
                )

                if min_points is not None:
                    query = query.filter(Statistics.points >= min_points)

                if min_rebounds is not None:
                    query = query.filter(Statistics.rebounds_total >= min_rebounds)

                if min_assists is not None:
                    query = query.filter(Statistics.assists >= min_assists)

                if position:
                    query = query.filter(Statistics.position == position)

                return query.all()
            else:
                with self.db_session.session_scope('game') as internal_session:
                    query = internal_session.query(Statistics).filter(
                        Statistics.game_id == game_id
                    )

                    if min_points is not None:
                        query = query.filter(Statistics.points >= min_points)

                    if min_rebounds is not None:
                        query = query.filter(Statistics.rebounds_total >= min_rebounds)

                    if min_assists is not None:
                        query = query.filter(Statistics.assists >= min_assists)

                    if position:
                        query = query.filter(Statistics.position == position)

                    stats = query.all()
                    return [self._to_dict(stat) for stat in stats]

        except Exception as e:
            self.logger.error(f"根据条件获取球员统计数据失败: {e}")
            return []

    # 以下是已经返回字典的聚合方法，只需添加session参数并根据情况使用
    def get_player_season_averages(self, player_id: int,
                                   season: Optional[str] = None,
                                   is_regular_season: Optional[bool] = True,
                                   session=None) -> Dict:
        """获取球员的场均数据，按照常规赛/季后赛和赛季分组"""
        try:
            if session is not None:
                # 使用外部会话的实现
                query = session.query(
                    func.count(distinct(Statistics.game_id)).label('games_played'),
                    func.avg(Statistics.points).label('ppg'),
                    # ... 其他字段保持不变
                ).filter(Statistics.person_id == player_id)

                # 根据赛季筛选和其他条件的代码保持不变...

                result = query.first()

                # 构建返回字典的代码保持不变...

                return {}  # 返回构建的字典
            else:
                # 原有实现不变
                with self.db_session.session_scope('game') as internal_session:
                    # 原有代码...
                    pass
        except Exception as e:
            self.logger.error(f"获取球员赛季场均数据失败: {e}")
            return {}

