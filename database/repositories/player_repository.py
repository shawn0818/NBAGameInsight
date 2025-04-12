# database/repositories/player_repository.py
from typing import Optional, List, Dict, Any, Union, Tuple
from sqlalchemy import or_, func, case
from database.models.base_models import Player
from database.db_session import DBSession
from utils.logger_handler import AppLogger
from rapidfuzz import process, fuzz
import functools
from metaphone import doublemetaphone  # 用于英文名字的发音编码
import jellyfish  # 提供soundex和其他发音算法
import re  # 用于正则表达式处理


class PlayerRepository:
    """
    球员数据访问对象
    负责Player模型的CRUD操作，提供球员查询与评分功能
    """

    def __init__(self):
        """初始化球员数据访问对象"""
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

    def get_player_by_id(self, player_id: int) -> Optional[Dict]:
        """通过ID获取球员信息"""
        try:
            with self.db_session.session_scope('nba') as session:
                player = session.query(Player).filter(Player.person_id == player_id).first()
                return self._to_dict(player) if player else None
        except Exception as e:
            self.logger.error(f"通过ID获取球员信息失败: {e}")
            return None

    def get_candidates_by_name(self, name: str, team_id: Optional[int] = None) -> List[Dict]:
        """
        根据名称获取候选球员列表，当有球队上下文时直接返回该球队所有活跃球员
        """
        try:
            normalized_name = name.lower().strip()
            candidates_dicts = []

            # 当提供球队ID时，直接返回该球队的所有活跃球员
            if team_id is not None:
                with self.db_session.session_scope('nba') as session:
                    # 获取该球队的所有活跃球员
                    active_players = session.query(Player).filter(
                        Player.team_id == team_id,
                        Player.is_active == True
                    ).all()

                    # 转换为字典列表并直接返回
                    candidates_dicts = [self._to_dict(player) for player in active_players]

                    # 简单记录一下返回了多少候选球员
                    self.logger.debug(f"从球队 ID:{team_id} 返回 {len(candidates_dicts)} 个活跃球员作为候选")

                    # 如果找到候选，直接返回
                    if candidates_dicts:
                        return candidates_dicts

            # 如果没有找到或未提供球队ID，则使用原有逻辑
            with self.db_session.session_scope('nba') as session:
                name_pattern = f"%{normalized_name}%"
                query = session.query(Player).filter(
                    or_(
                        Player.display_first_last.ilike(name_pattern),
                        Player.display_last_comma_first.ilike(name_pattern),
                        Player.first_name.ilike(name_pattern),
                        Player.last_name.ilike(name_pattern),
                        Player.player_slug.ilike(name_pattern)
                    )
                )

                if team_id is not None:
                    query = query.filter(Player.team_id == team_id)

                candidates_orm = query.limit(30).all()
                candidates_dicts = [self._to_dict(player) for player in candidates_orm if player]

            return candidates_dicts
        except Exception as e:
            self.logger.error(f"获取球员候选失败: {e}")
            return []

    def score_player_candidates(self, name: str, candidates: List[Dict]) -> List[Dict[str, Any]]:
        """优化的球员候选评分方法，增强单词匹配能力和发音相似性识别"""
        scored_results = []
        normalized_name = name.lower().strip()

        # 调整核心权重参数 - 进一步强化发音匹配
        ACTIVE_BONUS = 15
        NAME_MATCH_BONUS = 12
        FIRST_LETTER_BONUS = 15
        SIMILAR_LENGTH_BONUS = 6

        # 调整权重以进一步偏向发音匹配
        TEXT_MATCH_WEIGHT = 0.3
        PHONETIC_MATCH_WEIGHT = 0.7

        # 调整分数差异阈值
        TEAM_CONTEXT_THRESHOLD = 65  # 在球队上下文中的基本阈值
        SCORE_DIFF_THRESHOLD = 10  # 领先第二名的分差阈值

        if not normalized_name or not candidates:
            return []

        is_single_word = ' ' not in normalized_name

        # 预先计算输入名称的发音编码
        input_double_metaphone = doublemetaphone(normalized_name)
        input_soundex = jellyfish.soundex(normalized_name)
        input_nysiis = jellyfish.nysiis(normalized_name)

        # 首字母提取
        input_first_letter = normalized_name[0] if normalized_name else ''

        # 分割输入为单词列表，用于部分匹配
        input_words = re.findall(r'\w+', normalized_name)

        for player_dict in candidates:
            if not player_dict: continue

            # 获取球员名称相关字段
            full_name = (player_dict.get('display_first_last') or "").lower()
            last_first = (player_dict.get('display_last_comma_first') or "").lower().replace(',', ' ')
            first_name = (player_dict.get('first_name') or "").lower()
            last_name = (player_dict.get('last_name') or "").lower()
            slug = (player_dict.get('player_slug') or "").lower()
            is_active = player_dict.get('is_active', False)

            # ===== 文本相似度评分 =====
            if is_single_word:
                # 短姓名处理 - 增强对短名称的惩罚
                name_length_factor = min(1.0, 0.6 + (len(last_name) / 10))

                # 使用多种算法并取最高分
                ratio_scores = [
                    fuzz.ratio(normalized_name, last_name) * name_length_factor,
                    fuzz.partial_ratio(normalized_name, last_name) * name_length_factor,
                    fuzz.token_sort_ratio(normalized_name, last_name),
                    fuzz.QRatio(normalized_name, last_name)
                ]

                last_name_score = max(ratio_scores)
                first_name_score = fuzz.WRatio(normalized_name, first_name) * name_length_factor
                full_name_score = fuzz.WRatio(normalized_name, full_name)

                # 取最高分作为基础分
                text_score = max(last_name_score, first_name_score, full_name_score)
            else:
                # 定义all_fields为所有球员相关字段的组合
                all_fields = f"{full_name} {last_first} {first_name} {last_name} {slug}".lower()

                # 多词搜索使用全局评分
                w_score = fuzz.WRatio(normalized_name, full_name)
                t_score = fuzz.token_set_ratio(normalized_name, all_fields)
                text_score = w_score * 0.6 + t_score * 0.4

            # ===== 发音相似度评分 =====
            phonetic_score = 0

            # 计算球员名字的发音编码
            last_double_metaphone = doublemetaphone(last_name)
            first_double_metaphone = doublemetaphone(first_name)
            last_soundex = jellyfish.soundex(last_name)
            first_soundex = jellyfish.soundex(first_name)
            last_nysiis = jellyfish.nysiis(last_name)
            first_nysiis = jellyfish.nysiis(first_name)

            # Double Metaphone匹配检测 - 最精确的发音匹配
            metaphone_match = False
            for i in range(2):
                if input_double_metaphone[i] and (input_double_metaphone[i] == last_double_metaphone[i] or
                                                  input_double_metaphone[i] == first_double_metaphone[i]):
                    metaphone_match = True
                    phonetic_score += 50  # 增加双元音素匹配的权重
                    break

            # Soundex匹配检测 - 宽松的发音匹配
            soundex_match = input_soundex == last_soundex or input_soundex == first_soundex
            if soundex_match:
                phonetic_score += 40  # 增加Soundex匹配的权重

            # NYSIIS匹配检测 - 专为人名优化的算法
            nysiis_match = input_nysiis == last_nysiis or input_nysiis == first_nysiis
            if nysiis_match:
                phonetic_score += 45  # 增加NYSIIS匹配的权重

            # 计算Levenshtein发音距离相似度 - 处理细微发音差异
            if input_nysiis and last_nysiis:
                nysiis_distance = jellyfish.levenshtein_distance(input_nysiis, last_nysiis)
                # 如果发音编码相似度高（距离小）
                if 0 < nysiis_distance <= 2:
                    phonetic_score += 35 - (nysiis_distance * 10)  # 距离1加25分，距离2加15分

            # 部分发音匹配（对多词情况）
            partial_phonetic_match = False
            if not is_single_word:
                for word in input_words:
                    word_metaphone = doublemetaphone(word)
                    if (word_metaphone[0] and (word_metaphone[0] == last_double_metaphone[0] or
                                               word_metaphone[0] == first_double_metaphone[0])):
                        partial_phonetic_match = True
                        phonetic_score += 25
                        break

            # 首字母匹配检查
            first_letter_match = False
            if input_first_letter and (last_name.startswith(input_first_letter) or
                                       first_name.startswith(input_first_letter)):
                first_letter_match = True

            # 额外加分项
            bonus = 0

            # 活跃球员加分
            if is_active:
                bonus += ACTIVE_BONUS

            # 精确匹配加分
            if normalized_name == full_name or normalized_name == first_name or normalized_name == last_name:
                bonus += NAME_MATCH_BONUS

            # 首字母匹配加分 - 但对发音匹配高的情况降低要求
            if first_letter_match:
                bonus += FIRST_LETTER_BONUS
            else:
                # 首字母不匹配时的惩罚逻辑
                if (metaphone_match or soundex_match or nysiis_match):  # 如果任一发音匹配成功
                    text_score *= 0.95  # 轻微惩罚
                    bonus += 5  # 部分补偿不匹配的首字母
                else:
                    text_score *= 0.7  # 显著惩罚

            # 长度相似加分
            if last_name and abs(len(normalized_name) - len(last_name)) <= 2:
                bonus += SIMILAR_LENGTH_BONUS

            # 发音相似性强有力证据时的额外加分
            if (metaphone_match and soundex_match) or (metaphone_match and nysiis_match) or (
                    soundex_match and nysiis_match):
                bonus += 15  # 多种发音算法一致匹配时给予额外加分

            # 计算最终加权得分
            weighted_score = text_score * TEXT_MATCH_WEIGHT + phonetic_score * PHONETIC_MATCH_WEIGHT
            final_score = weighted_score + bonus

            # 详细的调试信息
            phonetic_info = (
                f"Metaphone: {'是' if metaphone_match else '否'}, "
                f"Soundex: {'是' if soundex_match else '否'}, "
                f"NYSIIS: {'是' if nysiis_match else '否'}, "
                f"部分匹配: {'是' if partial_phonetic_match else '否'}"
            )

            detail_info = (
                f"球员: {full_name}, 搜索: {normalized_name}, 最终得分: {final_score:.1f}\n"
                f"文本得分: {text_score:.1f} × {TEXT_MATCH_WEIGHT} = {text_score * TEXT_MATCH_WEIGHT:.1f}, "
                f"发音得分: {phonetic_score:.1f} × {PHONETIC_MATCH_WEIGHT} = {phonetic_score * PHONETIC_MATCH_WEIGHT:.1f}, "
                f"加分: {bonus}\n"
                f"首字母匹配: {'是' if first_letter_match else '否'}, "
                f"活跃球员: {'是' if is_active else '否'}\n"
                f"发音匹配: {phonetic_info}"
            )
            self.logger.debug(detail_info)

            scored_results.append({
                "player": player_dict,
                "score": final_score,
                "text_score": text_score,
                "phonetic_score": phonetic_score,
                "bonus": bonus
            })

        # 排序结果
        scored_results.sort(key=lambda x: x['score'], reverse=True)

        # 为get_player_id_by_name函数优化决策逻辑部分提供建议
        # 当前函数只返回排序结果，实际决策在调用函数中处理
        # 建议将TEAM_CONTEXT_THRESHOLD降低到65左右并保持SCORE_DIFF_THRESHOLD在10左右

        return scored_results

    def get_player_name_by_id(self, player_id: int, name_type: str = 'full') -> Optional[str]:
        """
        通过ID获取球员名称

        Args:
            player_id: 球员ID
            name_type: 返回的名称类型，可选值:
                      'full' - 完整名称(如 LeBron James)
                      'last_first' - 姓名格式(如 James, LeBron)
                      'first' - 仅名字
                      'last' - 仅姓氏
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
                    return player.first_name
                elif name_type.lower() == 'last':
                    return player.last_name
                elif name_type.lower() == 'short':
                    return player.short_name()
                else:  # 默认返回完整名称 (full)
                    return player.display_first_last

        except Exception as e:
            self.logger.error(f"通过ID获取球员名称失败: {e}")
            return None

    def get_team_players(self, team_id: int, active_only: bool = True) -> List[Dict]:
        """
        获取特定球队的球员列表

        Args:
            team_id: 球队ID
            active_only: 是否只返回活跃球员

        Returns:
            List[Dict]: 球员信息列表
        """
        try:
            with self.db_session.session_scope('nba') as session:
                query = session.query(Player).filter(Player.team_id == team_id)

                if active_only:
                    query = query.filter(Player.is_active == True)

                players = query.order_by(Player.display_first_last).all()
                # 在会话内部转换为字典
                players_dict = [self._to_dict(player) for player in players]

            return players_dict

        except Exception as e:
            self.logger.error(f"获取球队球员失败: {e}")
            return []