# database/repositories/team_repository.py
from typing import Dict, List, Optional
from database.models.base_models import Team
from database.db_session import DBSession
from utils.logger_handler import AppLogger
from sqlalchemy import or_
from rapidfuzz import process, fuzz
import functools


class TeamRepository:
    """
    球队数据访问对象 - 专注于查询操作
    使用SQLAlchemy ORM进行数据访问，增强了模糊匹配功能
    """

    # 知名球队字典映射
    KNOWN_TEAMS = {
        "lakers": 1610612747,  # Los Angeles Lakers
        "celtics": 1610612738,  # Boston Celtics
        "warriors": 1610612744,  # Golden State Warriors
    }

    def __init__(self):
        """初始化球队数据访问对象"""
        self.db_session = DBSession.get_instance()
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')
        self._teams_cache = None
        self._last_cache_update = None

    @staticmethod
    def _to_dict(model_instance):
        """将模型实例转换为字典"""
        if model_instance is None:
            return None

        result = {}
        for column in model_instance.__table__.columns:
            result[column.name] = getattr(model_instance, column.name)
        return result

    def _get_teams_cache(self):
        """获取球队缓存，提高频繁查询性能"""
        from datetime import datetime, timedelta

        # 缓存有效期为1小时
        cache_valid = (self._teams_cache is not None and
                       self._last_cache_update is not None and
                       datetime.now() - self._last_cache_update < timedelta(hours=1))

        if not cache_valid:
            try:
                with self.db_session.session_scope('nba') as session:
                    self._teams_cache = session.query(Team).all()
                    self._last_cache_update = datetime.now()
            except Exception as e:
                self.logger.error(f"刷新球队缓存失败: {e}")
                # 如果刷新失败但缓存存在，继续使用旧缓存
                if self._teams_cache is None:
                    self._teams_cache = []

        return self._teams_cache

    def _get_dynamic_threshold(self, query: str) -> int:
        """根据查询字符串长度动态调整模糊匹配阈值"""
        length = len(query)

        # 单词越短，需要更严格的匹配度
        if length <= 3:
            return 85
        elif length <= 5:
            return 75
        elif length <= 8:
            return 65
        else:
            return 55

    def _exact_match(self, session, normalized_name: str) -> Optional[Team]:
        """尝试精确匹配球队名称"""
        return session.query(Team).filter(
            or_(
                Team.nickname.ilike(normalized_name),
                Team.city.ilike(normalized_name),
                Team.abbreviation.ilike(normalized_name),
                Team.team_slug.ilike(normalized_name)
            )
        ).first()

    def _fuzzy_match(self, session, normalized_name: str) -> List[Team]:
        """使用模糊匹配查找球队"""
        name_pattern = f"%{normalized_name}%"
        return session.query(Team).filter(
            or_(
                Team.nickname.ilike(name_pattern),
                Team.city.ilike(name_pattern),
                Team.abbreviation.ilike(name_pattern),
                Team.team_slug.ilike(name_pattern)
            )
        ).all()

    def _abbreviation_match(self, normalized_name: str) -> Optional[int]:
        """匹配球队缩写"""
        # 如果是3个字符，可能是缩写
        if len(normalized_name) == 3:
            # 检查是否直接匹配缩写映射
            if normalized_name.upper() in [k.upper() for k in self.KNOWN_TEAMS.keys()]:
                for key, value in self.KNOWN_TEAMS.items():
                    if key.upper() == normalized_name.upper():
                        return value

            # 尝试匹配缓存中的球队缩写
            teams = self._get_teams_cache()
            for team in teams:
                if team.abbreviation and team.abbreviation.upper() == normalized_name.upper():
                    return team.team_id

        return None

    def _select_best_match(self, normalized_name: str, matches: List[Team], threshold: int) -> Optional[int]:
        """从多个匹配中选择最佳匹配"""
        # 为每个匹配创建可能的字符串表示
        match_strings = []
        for match in matches:
            # 组合所有字段，确保不是None
            nickname = match.nickname or ""
            city = match.city or ""
            abbr = match.abbreviation or ""
            slug = match.team_slug or ""
            # 创建完整名称，如"Los Angeles Lakers"
            full_name = f"{city} {nickname}".strip()
            # 创建两种不同的匹配字符串
            full_match_str = f"{full_name} {nickname} {city} {abbr} {slug}".lower()

            # 添加一些常用别名
            aliases = []
            if "76ers" in nickname:
                aliases.append("sixers")
            if "Trail Blazers" in nickname:
                aliases.append("blazers")
            if "Mavericks" in nickname:
                aliases.append("mavs")

            alias_str = " ".join(aliases)
            match_strings.append((full_match_str, alias_str, match.team_id))

        # 先尝试WRatio（适合完整名称）
        best_match = process.extractOne(
            normalized_name,
            [m[0] for m in match_strings],
            scorer=fuzz.WRatio,
            score_cutoff=threshold
        )

        if best_match:
            idx = [m[0] for m in match_strings].index(best_match[0])
            return match_strings[idx][2]

        # 再尝试别名匹配
        for idx, (_, alias_str, team_id) in enumerate(match_strings):
            if alias_str and normalized_name in alias_str:
                return team_id

        # 最后尝试部分比较
        best_match = process.extractOne(
            normalized_name,
            [m[0] for m in match_strings],
            scorer=fuzz.partial_ratio,
            score_cutoff=threshold - 5  # 稍微降低阈值以提高匹配概率
        )

        if best_match:
            idx = [m[0] for m in match_strings].index(best_match[0])
            return match_strings[idx][2]

        return None

    @functools.lru_cache(maxsize=100)
    def get_team_id_by_name(self, name: str) -> Optional[int]:
        """
        通过名称、缩写或slug获取球队ID(支持模糊匹配)

        Args:
            name: 球队名称、缩写或slug

        Returns:
            Optional[int]: 球队ID，未找到时返回None
        """
        if not name:
            return None

        try:
            # 标准化输入
            normalized_name = name.lower().strip()

            # 1. 检查知名球队映射
            if normalized_name in self.KNOWN_TEAMS:
                return self.KNOWN_TEAMS[normalized_name]

            # 2. 尝试缩写匹配
            abbr_match = self._abbreviation_match(normalized_name)
            if abbr_match:
                return abbr_match

            with self.db_session.session_scope('nba') as session:
                # 3. 精确匹配
                team = self._exact_match(session, normalized_name)
                if team:
                    return team.team_id

                # 4. 模糊匹配
                matches = self._fuzzy_match(session, normalized_name)

                if not matches:
                    return None

                # 5. 如果只有一个匹配，直接返回
                if len(matches) == 1:
                    return matches[0].team_id

                # 6. 从多个匹配中选择最佳匹配
                threshold = self._get_dynamic_threshold(normalized_name)
                return self._select_best_match(normalized_name, matches, threshold)

        except Exception as e:
            self.logger.error(f"通过名称查询球队ID失败: {e}")
            return None

    def get_team_name_by_id(self, team_id: int, name_type: str = 'full') -> Optional[str]:
        """
        通过ID获取球队名称

        Args:
            team_id: 球队ID
            name_type: 返回的名称类型，可选值包括:
                      'full' - 完整名称 (城市+昵称)
                      'nickname' - 仅球队昵称
                      'city' - 仅城市名
                      'abbr' - 球队缩写

        Returns:
            Optional[str]: 球队名称，未找到时返回None
        """
        try:
            with self.db_session.session_scope('nba') as session:
                team = session.query(
                    Team.nickname, Team.city, Team.abbreviation
                ).filter(
                    Team.team_id == team_id
                ).first()

                if not team:
                    return None

                # 根据请求的名称类型返回不同格式
                if name_type.lower() == 'nickname':
                    return team.nickname
                elif name_type.lower() == 'city':
                    return team.city
                elif name_type.lower() == 'abbr':
                    return team.abbreviation
                else:  # 默认返回完整名称
                    return f"{team.city} {team.nickname}"

        except Exception as e:
            self.logger.error(f"通过ID获取球队名称失败: {e}")
            return None

    def get_team_by_id(self, team_id: int) -> Optional[Dict]:
        """
        通过ID获取球队信息

        Args:
            team_id: 球队ID

        Returns:
            Optional[Dict]: 球队信息字典，未找到时返回None
        """
        try:
            with self.db_session.session_scope('nba') as session:
                team = session.query(Team).filter(
                    Team.team_id == team_id
                ).first()

                if team:
                    return self._to_dict(team)
                return None

        except Exception as e:
            self.logger.error(f"获取球队(ID:{team_id})数据失败: {e}")
            return None

    def get_team_by_abbr(self, abbr: str) -> Optional[Dict]:
        """
        通过缩写获取球队信息

        Args:
            abbr: 球队缩写

        Returns:
            Optional[Dict]: 球队信息字典，未找到时返回None
        """
        try:
            with self.db_session.session_scope('nba') as session:
                team = session.query(Team).filter(
                    Team.abbreviation.ilike(abbr)
                ).first()

                if team:
                    return self._to_dict(team)
                return None

        except Exception as e:
            self.logger.error(f"获取球队(缩写:{abbr})数据失败: {e}")
            return None

    def get_team_by_name(self, name: str) -> Optional[Dict]:
        """
        通过名称获取球队信息(模糊匹配)

        Args:
            name: 球队名称(昵称或城市名)

        Returns:
            Optional[Dict]: 球队信息字典，未找到时返回None
        """
        try:
            # 先尝试通过名称获取球队ID
            team_id = self.get_team_id_by_name(name)
            if team_id:
                return self.get_team_by_id(team_id)

            # 如果没有找到ID，尝试老方法直接查询
            with self.db_session.session_scope('nba') as session:
                name_pattern = f"%{name}%"
                team = session.query(Team).filter(
                    or_(
                        Team.nickname.ilike(name_pattern),
                        Team.city.ilike(name_pattern)
                    )
                ).first()

                if team:
                    return self._to_dict(team)
                return None

        except Exception as e:
            self.logger.error(f"获取球队(名称:{name})数据失败: {e}")
            return None

    def get_all_teams(self) -> List[Dict]:
        """
        获取所有球队信息

        Returns:
            List[Dict]: 所有球队信息列表
        """
        try:
            with self.db_session.session_scope('nba') as session:
                teams = session.query(Team).order_by(
                    Team.city, Team.nickname
                ).all()

                return [self._to_dict(team) for team in teams]

        except Exception as e:
            self.logger.error(f"获取所有球队数据失败: {e}")
            return []

    def get_team_logo(self, team_id: int) -> Optional[bytes]:
        """
        获取球队logo数据

        Args:
            team_id: 球队ID

        Returns:
            Optional[bytes]: 二进制图像数据，未找到时返回None
        """
        try:
            with self.db_session.session_scope('nba') as session:
                team = session.query(Team.logo).filter(
                    Team.team_id == team_id
                ).first()

                return team.logo if team else None

        except Exception as e:
            self.logger.error(f"获取球队logo失败: {e}")
            return None

    def has_team_details(self, team_id: int) -> bool:
        """
        检查球队是否有详细信息

        Args:
            team_id: 球队ID

        Returns:
            bool: 是否有详细信息
        """
        try:
            with self.db_session.session_scope('nba') as session:
                team = session.query(Team.arena).filter(
                    Team.team_id == team_id
                ).first()

                return team is not None and team.arena is not None

        except Exception as e:
            self.logger.error(f"检查球队详细信息失败: {e}")
            return False