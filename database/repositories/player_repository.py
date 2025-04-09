# database/repositories/player_repository.py
from typing import Optional, List, Dict, Any, Union
from sqlalchemy import or_, func
from database.models.base_models import Player
from database.db_session import DBSession
from utils.logger_handler import AppLogger
from rapidfuzz import process, fuzz
import functools

class PlayerRepository:
    """
    球员数据访问对象
    负责Player模型的CRUD操作，增强了模糊查询功能
    """

    # 知名球员字典映射
    KNOWN_PLAYERS = {
        "lebron": 2544,  # LeBron James
        "james": 2544,  # LeBron James (姓)
        "curry": 201939,  # Stephen Curry
        "steph": 201939,  # Stephen Curry (名的简称)
        "kd": 201142,  # Kevin Durant
        "durant": 201142,  # Kevin Durant (姓)
    }

    def __init__(self):
        """初始化球员数据访问对象"""
        self.db_session = DBSession.get_instance()
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')
        self._players_cache = None
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

    def _get_players_cache(self):
        """获取球员缓存，提高频繁查询性能"""
        from datetime import datetime, timedelta

        # 缓存有效期为1小时
        cache_valid = (self._players_cache is not None and
                       self._last_cache_update is not None and
                       datetime.now() - self._last_cache_update < timedelta(hours=1))

        if not cache_valid:
            try:
                with self.db_session.session_scope('nba') as session:
                    self._players_cache = session.query(Player).all()
                    self._last_cache_update = datetime.now()
            except Exception as e:
                self.logger.error(f"刷新球员缓存失败: {e}")
                # 如果刷新失败但缓存存在，继续使用旧缓存
                if self._players_cache is None:
                    self._players_cache = []

        return self._players_cache

    def _parse_name_parts(self, name: str) -> Dict[str, Any]:
        """解析名字，判断输入的是名、姓还是全名"""
        normalized_name = name.lower().strip()
        result = {
            "is_single_term": False,
            "is_likely_first_name": False,
            "is_likely_last_name": False,
            "normalized_name": normalized_name
        }

        parts = normalized_name.split()
        if len(parts) == 1:
            result["is_single_term"] = True

            # 常见名字列表
            common_first_names = ["lebron", "stephen", "kevin", "james", "kobe", "michael",
                                  "kyrie", "giannis", "luka", "nikola", "anthony", "damian",
                                  "joel", "paul", "kawhi", "devin", "jayson", "ja", "zion"]
            # 常见姓氏列表
            common_last_names = ["james", "curry", "durant", "harden", "bryant", "jordan",
                                 "irving", "antetokounmpo", "doncic", "jokic", "davis",
                                 "lillard", "embiid", "george", "leonard", "booker",
                                 "tatum", "morant", "williamson"]

            if parts[0] in common_first_names:
                result["is_likely_first_name"] = True
            if parts[0] in common_last_names:
                result["is_likely_last_name"] = True

        return result

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

    def _exact_match(self, session, normalized_name: str) -> Optional[Player]:
        """尝试精确匹配球员名称"""
        return session.query(Player).filter(
            or_(
                func.lower(Player.display_first_last) == normalized_name,
                func.lower(Player.display_last_comma_first) == normalized_name,
                func.lower(Player.player_slug) == normalized_name
            )
        ).first()

    def _single_term_match(self, session, term: str, is_likely_first: bool, is_likely_last: bool) -> Optional[int]:
        """处理单个词的匹配，可能是名或姓"""
        # 如果在知名球员映射中，直接返回
        if term in self.KNOWN_PLAYERS:
            return self.KNOWN_PLAYERS[term]

        matches = []

        # 根据名字特征优先尝试可能性更高的匹配类型
        if is_likely_first and not is_likely_last:
            # 先尝试作为名字匹配
            matches = session.query(Player).filter(
                func.lower(Player.display_first_last).like(f"{term}%")
            ).all()

            # 如果没有匹配，再尝试作为姓氏匹配
            if not matches:
                matches = session.query(Player).filter(
                    or_(
                        func.lower(Player.display_first_last).like(f"% {term}%"),
                        func.lower(Player.display_last_comma_first).like(f"{term},%")
                    )
                ).all()
        else:
            # 先尝试作为姓氏匹配
            matches = session.query(Player).filter(
                or_(
                    func.lower(Player.display_first_last).like(f"% {term}%"),
                    func.lower(Player.display_last_comma_first).like(f"{term},%")
                )
            ).all()

            # 如果没有匹配，再尝试作为名字匹配
            if not matches:
                matches = session.query(Player).filter(
                    func.lower(Player.display_first_last).like(f"{term}%")
                ).all()

        # 处理匹配结果
        if not matches:
            return None

        # 如果只有一个匹配结果，直接返回
        if len(matches) == 1:
            return matches[0].person_id

        # 如果有多个匹配，使用RapidFuzz进一步选择
        match_strings = []
        for match in matches:
            display_first_last = match.display_first_last or ""
            match_strings.append((display_first_last.lower(), match.person_id))

        # 使用RapidFuzz的部分比较
        best_match = process.extractOne(
            term,
            [m[0] for m in match_strings],
            scorer=fuzz.partial_ratio,  # 部分比较更适合单词匹配
            score_cutoff=75  # 单词匹配需要更高的相似度
        )

        if best_match:
            idx = [m[0] for m in match_strings].index(best_match[0])
            return match_strings[idx][1]

        return None

    def _fuzzy_match(self, session, normalized_name: str) -> List[Player]:
        """使用模糊匹配查找球员"""
        name_pattern = f"%{normalized_name}%"
        return session.query(Player).filter(
            or_(
                func.lower(Player.display_first_last).like(name_pattern),
                func.lower(Player.display_last_comma_first).like(name_pattern),
                func.lower(Player.player_slug).like(name_pattern)
            )
        ).all()

    def _initial_match(self, name: str) -> Optional[int]:
        """处理首字母缩写匹配，如'LBJ'匹配'LeBron James'"""
        if not (2 <= len(name) <= 4 and name.upper() == name):
            return None

        # 获取所有球员
        players = self._get_players_cache()
        initial_matches = []

        for player in players:
            if not player.display_first_last:
                continue

            # 获取名字的首字母
            full_name = player.display_first_last
            initials = ''.join(part[0].upper() for part in full_name.split() if part)

            if name.upper() == initials:
                initial_matches.append((player.person_id, full_name))

        # 处理匹配结果
        if not initial_matches:
            return None
        if len(initial_matches) == 1:
            return initial_matches[0][0]

        # 如果有多个匹配，优先返回知名球员
        for player_id, full_name in initial_matches:
            # 检查是否是知名球员（可以扩展这个列表）
            if "lebron james" in full_name.lower() and name.upper() == "LBJ":
                return player_id
            elif "michael jordan" in full_name.lower() and name.upper() == "MJ":
                return player_id
            # 可以添加更多知名球员的缩写匹配

        # 默认返回第一个匹配
        return initial_matches[0][0]

    def _select_best_match(self, normalized_name: str, matches: List[Player], threshold: int) -> Optional[int]:
        """从多个匹配中选择最佳匹配"""
        # 为每个匹配创建一个包含所有可能匹配字段的组合字符串
        match_strings = []
        for match in matches:
            # 组合所有字段，确保不是None
            display_first_last = match.display_first_last or ""
            display_last_comma_first = match.display_last_comma_first or ""
            player_slug = match.player_slug or ""
            # 创建两种不同的匹配字符串，分别优化完整名称和部分名称匹配
            full_match_str = f"{display_first_last} {display_last_comma_first} {player_slug}".lower()
            # 分解名字为单词，便于部分匹配
            words = []
            if display_first_last:
                words.extend(part.lower() for part in display_first_last.split())
            if display_last_comma_first:
                words.extend(part.lower() for part in display_last_comma_first.replace(',', ' ').split())

            match_strings.append((full_match_str, ' '.join(words), match.person_id))

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

        # 再尝试部分比较（适合部分名称）
        best_match = process.extractOne(
            normalized_name,
            [m[1] for m in match_strings],
            scorer=fuzz.partial_ratio,
            score_cutoff=threshold
        )

        if best_match:
            idx = [m[1] for m in match_strings].index(best_match[0])
            return match_strings[idx][2]

        return None

    @functools.lru_cache(maxsize=1000)
    def get_player_id_by_name(self, name: str) -> Optional[int]:
        """
        通过球员名称查询ID，支持增强的模糊匹配
        增强了单个名字或姓氏的匹配能力

        Args:
            name: 球员名称(全名、姓、名、缩写、昵称等)

        Returns:
            Optional[int]: 球员ID，未找到或模糊匹配度不足时返回None
        """
        if not name:
            return None

        try:
            # 1. 名字预处理和解析
            name_info = self._parse_name_parts(name)
            normalized_name = name_info["normalized_name"]

            # 2. 检查知名球员映射
            if normalized_name in self.KNOWN_PLAYERS:
                return self.KNOWN_PLAYERS[normalized_name]

            # 3. 尝试首字母缩写匹配（如LBJ, MJ等）
            initial_match = self._initial_match(name)
            if initial_match:
                return initial_match

            with self.db_session.session_scope('nba') as session:
                # 4. 精确匹配
                player = self._exact_match(session, normalized_name)
                if player:
                    return player.person_id

                # 5. 单个词匹配
                if name_info["is_single_term"]:
                    player_id = self._single_term_match(
                        session,
                        normalized_name,
                        name_info["is_likely_first_name"],
                        name_info["is_likely_last_name"]
                    )
                    if player_id:
                        return player_id

                # 6. 模糊匹配
                matches = self._fuzzy_match(session, normalized_name)

                if not matches:
                    return None

                # 7. 如果只有一个匹配，直接返回
                if len(matches) == 1:
                    return matches[0].person_id

                # 8. 从多个匹配中选择最佳匹配
                threshold = self._get_dynamic_threshold(normalized_name)
                return self._select_best_match(normalized_name, matches, threshold)

        except Exception as e:
            self.logger.error(f"通过名称查询球员ID失败: {e}")
            return None

    def get_player_name_by_id(self, player_id: int, name_type: str = 'full') -> Optional[str]:
        """
        通过ID获取球员名称

        Args:
            player_id: 球员ID
            name_type: 返回的名称类型，可选值:
                      'full' - 完整名称(名姓格式，如 LeBron James)
                      'last_first' - 姓名格式(如 James, LeBron)
                      'first' - 仅名字(从完整名称中提取第一部分)
                      'last' - 仅姓氏(从完整名称中提取最后部分)
                      'short' - 简短形式(如 L. James)

        Returns:
            Optional[str]: 球员名称，未找到时返回None
        """
        try:
            with self.db_session.session_scope('nba') as session:
                player = session.query(Player).filter(Player.person_id == player_id).first()

                if not player:
                    return None

                # 根据请求的名称类型返回不同格式
                if name_type.lower() == 'last_first':
                    return player.display_last_comma_first
                elif name_type.lower() == 'first':
                    full_name = player.display_first_last
                    return full_name.split(' ')[0] if ' ' in full_name else full_name
                elif name_type.lower() == 'last':
                    full_name = player.display_first_last
                    return full_name.split(' ')[-1] if ' ' in full_name else ''
                elif name_type.lower() == 'short':
                    # 返回简短形式，如 L. James
                    return player.short_name()
                else:  # 默认返回完整名称 (full)
                    return player.display_first_last

        except Exception as e:
            self.logger.error(f"通过ID获取球员名称失败: {e}")
            return None