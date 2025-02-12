from typing import Dict, List, Optional
from nba.models.team_model import (
    TeamProfile, TeamHofPlayer, TeamRetiredPlayer,
    TeamAward
)
from utils.logger_handler import AppLogger


class TeamParser:
    """球队数据解析器

    负责将NBA API返回的原始数据解析为结构化的TeamProfile对象。
    支持解析：
    1. 球队基本信息
    2. 球队历史荣誉
    3. 名人堂成员
    4. 退役球衣
    """

    logger = AppLogger.get_logger(__name__, app_name='nba')

    @classmethod
    def parse_team_details(cls, api_response: Dict) -> Optional[TeamProfile]: # 返回类型改为 Optional[TeamProfile] 以处理解析错误
        """解析API返回的球队详细信息

        将API返回的JSON数据转换为结构化的TeamProfile对象，
        包括所有基础信息和扩展信息。

        Args:
            api_response: API返回的原始JSON数据

        Returns:
            Optional[TeamProfile]: 结构化的球队信息对象, 解析失败时返回 None

        """
        try:
            result_sets = {
                result["name"]: result["rowSet"]
                for result in api_response["resultSets"]
            }

            # 检查 result_sets 键是否存在
            required_result_sets = ["TeamBackground", "TeamAwardsChampionships", "TeamAwardsConf", "TeamAwardsDiv", "TeamHof", "TeamRetired"]
            for rs_name in required_result_sets:
                if rs_name not in result_sets:
                    raise ValueError(f"Missing result set: {rs_name} in API response")


            # 获取基本信息
            background = result_sets["TeamBackground"][0]

            # 创建TeamProfile实例
            return TeamProfile(
                team_id=background[0],
                abbreviation=background[1],
                nickname=background[2],
                year_founded=background[3],
                city=background[4],
                arena=background[5],
                arena_capacity=background[6],
                owner=background[7],
                general_manager=background[8],
                head_coach=background[9],
                dleague_affiliation=background[10],
                championships=cls._parse_awards(result_sets["TeamAwardsChampionships"]),
                conference_titles=cls._parse_awards(result_sets["TeamAwardsConf"]),
                division_titles=cls._parse_awards(result_sets["TeamAwardsDiv"]),
                hof_players=cls._parse_hof_players(result_sets["TeamHof"]),
                retired_numbers=cls._parse_retired_players(result_sets["TeamRetired"])
            )
        except KeyError as e: # 捕获 KeyError 异常，处理 api_response 中键缺失的情况
            return cls._handle_parsing_error(e, "KeyError 解析球队详细信息时出错")
        except ValueError as e: # 捕获 ValueError 异常，处理 result_sets 缺失的情况
            return cls._handle_parsing_error(e, "ValueError 解析球队详细信息时出错")
        except Exception as e: # 捕获其他异常，处理解析过程中未预期的错误
            return cls._handle_parsing_error(e, "Unexpected error 解析球队详细信息时出错")


    @staticmethod
    def _parse_awards(rows: List[List]) -> List[TeamAward]:
        """解析球队荣誉数据

        Args:
            rows: API返回的荣誉数据行列表

        Returns:
            List[TeamAward]: 球队荣誉对象列表
        """
        return [
            TeamAward(
                year_awarded=row[0],
                opposite_team=row[1]
            )
            for row in rows
        ]

    @staticmethod
    def _parse_hof_players(rows: List[List]) -> List[TeamHofPlayer]:
        """解析名人堂球员数据

        Args:
            rows: API返回的名人堂球员数据行列表

        Returns:
            List[TeamHofPlayer]: 名人堂球员对象列表
        """
        return [
            TeamHofPlayer(
                player_id=row[0],
                player=row[1],
                position=row[2],
                jersey=row[3],
                seasons_with_team=row[4],
                year=row[5]
            )
            for row in rows
        ]

    @staticmethod
    def _parse_retired_players(rows: List[List]) -> List[TeamRetiredPlayer]:
        """解析退役球衣球员数据

        Args:
            rows: API返回的退役球衣数据行列表

        Returns:
            List[TeamRetiredPlayer]: 退役球衣球员对象列表
        """
        return [
            TeamRetiredPlayer(
                player_id=row[0],
                player=row[1],
                position=row[2],
                jersey=row[3],
                seasons_with_team=row[4],
                year=row[5]
            )
            for row in rows
        ]

    @classmethod # 将 _handle_parsing_error 定义为类方法
    def _handle_parsing_error(cls, e: Exception, message_prefix: str) -> None: # MODIFIED: 添加辅助方法处理错误
        """处理解析错误，记录日志并返回 None"""
        cls.logger.error(f"{message_prefix}: {e}", exc_info=True)
        return None