# database/repositories/team_repository.py
from typing import Dict, List, Optional, Union, Tuple
from database.models.base_models import Team
from database.db_session import DBSession
from utils.logger_handler import AppLogger
from sqlalchemy import or_
from rapidfuzz import process, fuzz
import functools


class TeamRepository:
    """
    球队数据访问对象 - 专注于查询操作
    使用SQLAlchemy ORM进行数据访问，增强了模糊匹配和拼音搜索功能
    """

    # 只保留拼音映射
    PINYIN_MAPPING = {
        # 完整拼音
        "huren": 1610612747,  # 湖人
        "kaierteren": 1610612738,  # 凯尔特人
        "yongshi": 1610612744,  # 勇士
        "huojian": 1610612745,  # 火箭
        "rehuo": 1610612748,  # 热火
        "gongniu": 1610612741,  # 公牛
        "kuaichuan": 1610612746,  # 快船
        "lanwang": 1610612751,  # 篮网
        "nikesi": 1610612752,  # 尼克斯
        "qishiliuren": 1610612755,  # 76人
        "maci": 1610612759,  # 马刺
        "leiting": 1610612760,  # 雷霆
        "taiyang": 1610612756,  # 太阳
        "menglong": 1610612761,  # 猛龙
        "jueshi": 1610612762,  # 爵士
        "qicai": 1610612764,  # 奇才
        "guowang": 1610612758,  # 国王
        "huosai": 1610612765,  # 活塞
        "buxingzhe": 1610612754,  # 步行者
        "tihu": 1610612740,  # 鹈鹕
        "senlinlang": 1610612750,  # 森林狼
        "juejin": 1610612743,  # 掘金
        "kaituozhe": 1610612757,  # 开拓者
        "huixiong": 1610612763,  # 灰熊
        "laoying": 1610612737,  # 老鹰
        "huangfeng": 1610612766,  # 黄蜂
        "qishi": 1610612739,  # 骑士
        "moshu": 1610612753,  # 魔术
        "xionglu": 1610612749,  # 雄鹿
        "duxingxia": 1610612742,  # 独行侠
    }

    def __init__(self):
        """初始化球队数据访问对象"""
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

    def _check_pinyin_match(self, query: str) -> Optional[int]:
        """
        检查是否匹配拼音，优化为返回最佳匹配

        Args:
            query: 查询字符串

        Returns:
            Optional[int]: 匹配的球队ID，未找到时返回None
        """
        # 转为小写以便匹配
        query = query.lower()

        # 直接查找完全匹配
        if query in self.PINYIN_MAPPING:
            return self.PINYIN_MAPPING[query]

        # 部分匹配 - 只处理较长的查询，避免过度匹配
        if len(query) >= 3:
            matches = []
            for pinyin, team_id in self.PINYIN_MAPPING.items():
                if query in pinyin:
                    # 计算匹配度 - 匹配字符串占拼音长度的比例
                    match_ratio = len(query) / len(pinyin)
                    matches.append((team_id, match_ratio))

            # 如果有匹配，返回匹配度最高的
            if matches:
                return sorted(matches, key=lambda x: x[1], reverse=True)[0][0]

        return None

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
        """尝试精确匹配球队名称，优先使用team_slug"""
        return session.query(Team).filter(
            or_(
                Team.team_slug.ilike(normalized_name),
                Team.nickname.ilike(normalized_name),
                Team.city.ilike(normalized_name),
                Team.abbreviation.ilike(normalized_name)
            )
        ).first()

    def _fuzzy_match(self, session, normalized_name: str) -> List[Team]:
        """使用模糊匹配查找球队，优先考虑team_slug"""
        name_pattern = f"%{normalized_name}%"
        return session.query(Team).filter(
            or_(
                Team.team_slug.ilike(name_pattern),
                Team.nickname.ilike(name_pattern),
                Team.city.ilike(name_pattern),
                Team.abbreviation.ilike(name_pattern)
            )
        ).all()

    def _select_best_match(self, normalized_name: str, matches: List[Team], threshold: int) -> Optional[int]:
        """
        从多个匹配中选择最佳匹配，使用综合评分机制

        Args:
            normalized_name: 标准化的查询名称
            matches: 匹配的球队列表
            threshold: 匹配阈值

        Returns:
            Optional[int]: 最佳匹配的球队ID，未找到时返回None
        """
        # 为每个匹配创建可能的字符串表示
        match_strings = []
        for match in matches:
            # 优先使用team_slug
            slug = match.team_slug or ""
            nickname = match.nickname or ""
            city = match.city or ""
            abbr = match.abbreviation or ""

            # 创建完整名称
            full_name = f"{city} {nickname}".strip()

            # 创建匹配字符串，注意team_slug放在首位
            full_match_str = f"{slug} {full_name} {nickname} {city} {abbr}".lower()

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

        # 使用综合评分机制
        best_matches = []
        for idx, str_to_match in enumerate([m[0] for m in match_strings]):
            w_score = fuzz.WRatio(normalized_name, str_to_match)
            p_score = fuzz.partial_ratio(normalized_name, str_to_match)

            # 综合得分 (可以调整权重)
            combined_score = w_score * 0.7 + p_score * 0.3

            if combined_score >= threshold:
                best_matches.append((match_strings[idx][2], combined_score))

        if best_matches:
            return sorted(best_matches, key=lambda x: x[1], reverse=True)[0][0]

        # 尝试别名匹配
        for idx, (_, alias_str, team_id) in enumerate(match_strings):
            if alias_str and normalized_name in alias_str:
                return team_id

        # 最后尝试部分比较
        best_match = process.extractOne(
            normalized_name,
            [m[0] for m in match_strings],
            scorer=fuzz.partial_ratio,
            score_cutoff=threshold - 5
        )

        if best_match:
            idx = [m[0] for m in match_strings].index(best_match[0])
            return match_strings[idx][2]

        return None

    @functools.lru_cache(maxsize=200)  # 增加缓存大小
    def get_team_id_by_name(self, name: str) -> Optional[int]:
        """
        通过名称、缩写、slug或拼音获取球队ID(支持模糊匹配)

        Args:
            name: 球队名称、缩写、slug或拼音

        Returns:
            Optional[int]: 球队ID，未找到时返回None
        """
        if not name:
            return None

        try:
            # 标准化输入
            normalized_name = name.lower().strip()

            # 1. 检查拼音匹配
            pinyin_match = self._check_pinyin_match(normalized_name)
            if pinyin_match:
                return pinyin_match

            # 2. 尝试数据库查询
            with self.db_session.session_scope('nba') as session:
                # 精确匹配
                team = self._exact_match(session, normalized_name)
                if team:
                    return team.team_id

                # 模糊匹配
                matches = self._fuzzy_match(session, normalized_name)

                if not matches:
                    return None

                # 如果只有一个匹配，直接返回
                if len(matches) == 1:
                    return matches[0].team_id

                # 从多个匹配中选择最佳匹配
                threshold = self._get_dynamic_threshold(normalized_name)
                return self._select_best_match(normalized_name, matches, threshold)

        except Exception as e:
            self.logger.error(f"通过名称查询球队ID失败: {e}")
            return None

    def get_team(self, identifier: Union[int, str]) -> Optional[Dict]:
        """
        统一的球队信息获取方法，支持ID、缩写、名称、拼音等多种查询方式

        Args:
            identifier: 球队标识符，可以是:
                        - 整数: 作为球队ID直接查询
                        - 字符串: 通过多种方式查询

        Returns:
            Optional[Dict]: 球队信息字典，未找到时返回None
        """
        try:
            # 根据标识符类型选择查询策略
            if isinstance(identifier, int):
                # 直接通过ID查询
                with self.db_session.session_scope('nba') as session:
                    team = session.query(Team).filter(
                        Team.team_id == identifier
                    ).first()
                    return self._to_dict(team) if team else None

            elif isinstance(identifier, str):
                identifier = identifier.strip()

                # 1. 尝试通过名称、拼音等获取ID
                team_id = self.get_team_id_by_name(identifier)
                if team_id:
                    # 使用ID查询完整信息
                    with self.db_session.session_scope('nba') as session:
                        team = session.query(Team).filter(
                            Team.team_id == team_id
                        ).first()
                        return self._to_dict(team) if team else None

                # 2. 最后尝试模糊匹配
                with self.db_session.session_scope('nba') as session:
                    name_pattern = f"%{identifier}%"
                    team = session.query(Team).filter(
                        or_(
                            Team.team_slug.ilike(name_pattern),
                            Team.nickname.ilike(name_pattern),
                            Team.city.ilike(name_pattern),
                            Team.abbreviation.ilike(name_pattern)
                        )
                    ).first()
                    return self._to_dict(team) if team else None

            return None

        except Exception as e:
            self.logger.error(f"获取球队信息失败(标识符:{identifier}): {e}")
            return None

    # 为了向后兼容，保留原方法但实现改为调用统一方法
    def get_team_by_id(self, team_id: int) -> Optional[Dict]:
        """通过ID获取球队信息"""
        return self.get_team(team_id)

    def get_team_by_abbr(self, abbr: str) -> Optional[Dict]:
        """通过缩写获取球队信息"""
        return self.get_team(abbr)

    def get_team_by_name(self, name: str) -> Optional[Dict]:
        """通过名称获取球队信息(模糊匹配)"""
        return self.get_team(name)

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

    def check_team_identifier(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """
        检查查询字符串是否以球队标识符开始

        Args:
            query: 查询字符串

        Returns:
            Tuple[Optional[str], Optional[str]]: (球队标识符, 剩余部分)，如果没有标识符则返回(None, 原始查询)
        """
        if not query:
            return None, query

        query = query.strip()
        words = query.split()

        # 逐步尝试可能的球队标识符
        # 先尝试第一个词
        if words:
            first_word = words[0]
            team_id = self.get_team_id_by_name(first_word)

            if team_id:
                # 找到了球队标识符
                remaining_part = query[len(first_word):].lstrip()
                return first_word, remaining_part

        # 再尝试前两个词(假设可能是"Los Angeles"这样的城市名)
        if len(words) >= 2:
            two_words = ' '.join(words[:2])
            team_id = self.get_team_id_by_name(two_words)

            if team_id:
                # 找到了球队标识符
                remaining_part = query[len(two_words):].lstrip()
                return two_words, remaining_part

        # 没有找到球队标识符
        return None, query