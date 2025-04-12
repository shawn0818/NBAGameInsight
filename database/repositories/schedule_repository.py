# database/repositories/schedule_repository.py
from datetime import datetime, date, timezone
from typing import Dict, List, Optional, Union
from sqlalchemy import or_,  desc
from database.models.base_models import Game
from database.db_session import DBSession
from utils.logger_handler import AppLogger


class ScheduleRepository:
    """
    赛程数据访问对象 - 专注于查询操作
    使用SQLAlchemy ORM进行数据访问
    """

    def __init__(self):
        """初始化赛程数据访问对象"""
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

    def get_game_id(self, team_id: int, date_query: Union[str, datetime.date, datetime, None] = 'today') -> Optional[str]:
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

                with self.db_session.session_scope('nba') as session:
                    game = session.query(Game.game_id).filter(
                        or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
                        Game.game_date == date_str
                    ).order_by(Game.game_date_time_utc).first()

                    return game.game_id if game else None

            return None

        except Exception as e:
            self.logger.error(f"获取比赛ID失败: {e}")
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
            # 将日期转换为string格式(YYYY-MM-DD)进行比较
            if isinstance(target_date, (date, datetime)):
                date_str = target_date.strftime('%Y-%m-%d')
            else:
                date_str = target_date

            with self.db_session.session_scope('nba') as session:
                games = session.query(Game).filter(
                    Game.game_date == date_str
                ).order_by(Game.game_date_time_utc).all()

                return [self._to_dict(game) for game in games]

        except Exception as e:
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
            with self.db_session.session_scope('nba') as session:
                games = session.query(Game).filter(
                    or_(Game.home_team_id == team_id, Game.away_team_id == team_id)
                ).order_by(desc(Game.game_date_time_utc)).limit(limit).all()

                return [self._to_dict(game) for game in games]

        except Exception as e:
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
            now = datetime.now(timezone.utc).isoformat()

            with self.db_session.session_scope('nba') as session:
                game = session.query(Game).filter(
                    or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
                    Game.game_date_time_utc > now,
                    Game.game_status == 1
                ).order_by(Game.game_date_time_utc).first()

                return self._to_dict(game) if game else None

        except Exception as e:
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
            now = datetime.now(timezone.utc).isoformat()
            with self.db_session.session_scope('nba') as session:
                game = session.query(Game).filter(
                    or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
                    Game.game_date_time_utc < now
                ).order_by(desc(Game.game_date_time_utc)).first()
                # 确保在会话内完成数据转换
                result = None
                if game:
                    result = self._to_dict(game)
                return result

        except Exception as e:
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
            with self.db_session.session_scope('nba') as session:
                query = session.query(Game).filter(Game.season_year == season)

                if game_type:
                    query = query.filter(Game.game_type == game_type)

                games = query.order_by(Game.game_date_time_utc).limit(limit).all()

                return [self._to_dict(game) for game in games]

        except Exception as e:
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
            with self.db_session.session_scope('nba') as session:
                count = session.query(Game).filter(Game.season_year == season).count()
                return count or 0

        except Exception as e:
            self.logger.error(f"获取赛季({season})赛程数量失败: {e}")
            return 0

    def format_game_time(self, game_data: Dict) -> str:
        """
        格式化比赛时间为易读字符串

        参数:
            game_data: 包含时间信息的比赛数据字典

        返回:
            str: 格式化后的时间字符串
        """
        if 'game_date_time_bjs' in game_data and game_data['game_date_time_bjs']:
            try:
                import re
                time_str = game_data['game_date_time_bjs']
                # 尝试解析ISO格式的时间字符串
                match = re.match(r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2}).*', time_str)
                if match:
                    date_part, time_part = match.groups()
                    dt = datetime.strptime(f"{date_part} {time_part}", '%Y-%m-%d %H:%M:%S')
                    return dt.strftime('%Y年%m月%d日 %H:%M')
                else:
                    dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                    return dt.strftime('%Y年%m月%d日 %H:%M')
            except Exception as e:
                self.logger.debug(f"日期解析失败: {e}, 使用原始值: {game_data['game_date_time_bjs']}")
                return game_data['game_date_time_bjs']
        elif ('game_date_bjs' in game_data and game_data['game_date_bjs']) and \
                ('game_time_bjs' in game_data and game_data['game_time_bjs']):
            try:
                # 使用分开存储的日期和时间
                dt = datetime.strptime(f"{game_data['game_date_bjs']} {game_data['game_time_bjs']}",
                                       '%Y-%m-%d %H:%M:%S')
                return dt.strftime('%Y年%m月%d日 %H:%M')
            except Exception:
                return f"{game_data['game_date_bjs']} {game_data['game_time_bjs']}"
        elif 'game_date_bjs' in game_data and game_data['game_date_bjs']:
            try:
                # 只有日期的情况
                dt = datetime.strptime(game_data['game_date_bjs'], '%Y-%m-%d')
                return dt.strftime('%Y年%m月%d日')
            except Exception:
                return game_data['game_date_bjs']
        else:
            # 没有北京时间，尝试使用原始game_date
            return game_data.get('game_date', '未知日期')

