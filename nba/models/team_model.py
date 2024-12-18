# nba/models/teams.py

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Union, List
from pathlib import Path
import pandas as pd
from nba.config.nba_config import NBAConfig

@dataclass
class Period:
    """比赛节次信息"""
    period_number: int
    period_type: str
    period_score: int

    @classmethod
    def from_dict(cls, data: Dict) -> "Period":
        return cls(
            period_number=int(data.get('period', 0)),
            period_type=data.get('periodType', 'REGULAR'),
            period_score=int(data.get('score', 0))
        )

@dataclass
class TeamStatistics:
    assists: int = 0
    assists_turnover_ratio: float = 0.0
    bench_points: int = 0
    biggest_lead: int = 0
    biggest_lead_score: str = ''
    biggest_scoring_run: int = 0
    biggest_scoring_run_score: str = ''
    blocks: int = 0
    blocks_received: int = 0
    fast_break_points_attempted: int = 0
    fast_break_points_made: int = 0
    fast_break_points_percentage: float = 0.0
    field_goals_attempted: int = 0
    field_goals_effective_adjusted: float = 0.0
    field_goals_made: int = 0
    field_goals_percentage: float = 0.0
    fouls_offensive: int = 0
    fouls_drawn: int = 0
    fouls_personal: int = 0
    fouls_team: int = 0
    fouls_technical: int = 0
    fouls_team_technical: int = 0
    free_throws_attempted: int = 0
    free_throws_made: int = 0
    free_throws_percentage: float = 0.0
    lead_changes: int = 0
    minutes: str = 'PT240M00.00S'
    minutes_calculated: str = 'PT240M'
    points: int = 0
    points_against: int = 0
    points_fast_break: int = 0
    points_from_turnovers: int = 0
    points_in_the_paint: int = 0
    points_in_the_paint_attempted: int = 0
    points_in_the_paint_made: int = 0
    points_in_the_paint_percentage: float = 0.0
    points_second_chance: int = 0
    rebounds_defensive: int = 0
    rebounds_offensive: int = 0
    rebounds_personal: int = 0
    rebounds_team: int = 0
    rebounds_team_defensive: int = 0
    rebounds_team_offensive: int = 0
    rebounds_total: int = 0
    second_chance_points_attempted: int = 0
    second_chance_points_made: int = 0
    second_chance_points_percentage: float = 0.0
    steals: int = 0
    team_field_goal_attempts: int = 0
    three_pointers_attempted: int = 0
    three_pointers_made: int = 0
    three_pointers_percentage: float = 0.0
    time_leading: str = 'PT00M00.00S'
    times_tied: int = 0
    true_shooting_attempts: float = 0.0
    true_shooting_percentage: float = 0.0
    turnovers: int = 0
    turnovers_team: int = 0
    turnovers_total: int = 0
    two_pointers_attempted: int = 0
    two_pointers_made: int = 0
    two_pointers_percentage: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict) -> "TeamStatistics":
        return cls(
            assists=int(data.get('assists', 0)),
            assists_turnover_ratio=float(data.get('assistsTurnoverRatio', 0.0)),
            bench_points=int(data.get('benchPoints', 0)),
            biggest_lead=int(data.get('biggestLead', 0)),
            biggest_lead_score=data.get('biggestLeadScore', ''),
            biggest_scoring_run=int(data.get('biggestScoringRun', 0)),
            biggest_scoring_run_score=data.get('biggestScoringRunScore', ''),
            blocks=int(data.get('blocks', 0)),
            blocks_received=int(data.get('blocksReceived', 0)),
            fast_break_points_attempted=int(data.get('fastBreakPointsAttempted', 0)),
            fast_break_points_made=int(data.get('fastBreakPointsMade', 0)),
            fast_break_points_percentage=float(data.get('fastBreakPointsPercentage', 0.0)),
            field_goals_attempted=int(data.get('fieldGoalsAttempted', 0)),
            field_goals_effective_adjusted=float(data.get('fieldGoalsEffectiveAdjusted', 0.0)),
            field_goals_made=int(data.get('fieldGoalsMade', 0)),
            field_goals_percentage=float(data.get('fieldGoalsPercentage', 0.0)),
            fouls_offensive=int(data.get('foulsOffensive', 0)),
            fouls_drawn=int(data.get('foulsDrawn', 0)),
            fouls_personal=int(data.get('foulsPersonal', 0)),
            fouls_team=int(data.get('foulsTeam', 0)),
            fouls_technical=int(data.get('foulsTechnical', 0)),
            fouls_team_technical=int(data.get('foulsTeamTechnical', 0)),
            free_throws_attempted=int(data.get('freeThrowsAttempted', 0)),
            free_throws_made=int(data.get('freeThrowsMade', 0)),
            free_throws_percentage=float(data.get('freeThrowsPercentage', 0.0)),
            lead_changes=int(data.get('leadChanges', 0)),
            minutes=data.get('minutes', 'PT240M00.00S'),
            minutes_calculated=data.get('minutesCalculated', 'PT240M'),
            points=int(data.get('points', 0)),
            points_against=int(data.get('pointsAgainst', 0)),
            points_fast_break=int(data.get('pointsFastBreak', 0)),
            points_from_turnovers=int(data.get('pointsFromTurnovers', 0)),
            points_in_the_paint=int(data.get('pointsInThePaint', 0)),
            points_in_the_paint_attempted=int(data.get('pointsInThePaintAttempted', 0)),
            points_in_the_paint_made=int(data.get('pointsInThePaintMade', 0)),
            points_in_the_paint_percentage=float(data.get('pointsInThePaintPercentage', 0.0)),
            points_second_chance=int(data.get('pointsSecondChance', 0)),
            rebounds_defensive=int(data.get('reboundsDefensive', 0)),
            rebounds_offensive=int(data.get('reboundsOffensive', 0)),
            rebounds_personal=int(data.get('reboundsPersonal', 0)),
            rebounds_team=int(data.get('reboundsTeam', 0)),
            rebounds_team_defensive=int(data.get('reboundsTeamDefensive', 0)),
            rebounds_team_offensive=int(data.get('reboundsTeamOffensive', 0)),
            rebounds_total=int(data.get('reboundsTotal', 0)),
            second_chance_points_attempted=int(data.get('secondChancePointsAttempted', 0)),
            second_chance_points_made=int(data.get('secondChancePointsMade', 0)),
            second_chance_points_percentage=float(data.get('secondChancePointsPercentage', 0.0)),
            steals=int(data.get('steals', 0)),
            team_field_goal_attempts=int(data.get('teamFieldGoalAttempts', 0)),
            three_pointers_attempted=int(data.get('threePointersAttempted', 0)),
            three_pointers_made=int(data.get('threePointersMade', 0)),
            three_pointers_percentage=float(data.get('threePointersPercentage', 0.0)),
            time_leading=data.get('timeLeading', 'PT00M00.00S'),
            times_tied=int(data.get('timesTied', 0)),
            true_shooting_attempts=float(data.get('trueShootingAttempts', 0.0)),
            true_shooting_percentage=float(data.get('trueShootingPercentage', 0.0)),
            turnovers=int(data.get('turnovers', 0)),
            turnovers_team=int(data.get('turnoversTeam', 0)),
            turnovers_total=int(data.get('turnoversTotal', 0)),
            two_pointers_attempted=int(data.get('twoPointersAttempted', 0)),
            two_pointers_made=int(data.get('twoPointersMade', 0)),
            two_pointers_percentage=float(data.get('twoPointersPercentage', 0.0)),
        )

@dataclass
class Team:
    """球队比赛信息"""
    team_id: str
    team_name: str
    team_city: str
    team_tricode: str
    team_score: int
    team_periods: List[Period] = field(default_factory=list)
    team_timeouts_remaining: int = 0
    team_in_bonus: bool = False

    @property
    def full_name(self) -> str:
        return f"{self.team_city} {self.team_name}"

    @classmethod
    def from_dict(cls, data: Dict) -> "Team":
        return cls(
            team_id=str(data.get('teamId', '')),
            team_name=data.get('teamName', ''),
            team_city=data.get('teamCity', ''),
            team_tricode=data.get('teamTricode', ''),
            team_score=int(data.get('score', 0)),
            team_periods=[Period.from_dict(p) for p in data.get('periods', [])],
            team_timeouts_remaining=int(data.get('timeoutsRemaining', 0)),
            team_in_bonus=bool(data.get('inBonus', False))
        )

class TeamInfo:
    """NBA球队信息处理类-能够根据球队名称获取球队 ID、获取球队详细信息及其 logo 文件路径。
    它支持通过多种方式（缩写、昵称、全名）查找球队，并使用缓存机制来提高查询效率"""

    def __init__(self):
        """初始化TeamInfo类"""
        self.logger = logging.getLogger(self.__class__.__name__)
        self._load_team_data()
        self._create_lookup_maps()

    def _load_team_data(self):
        """加载球队数据"""
        csv_path = Path(NBAConfig.PATHS.DATA_DIR) / 'team_profile.csv'  # 调整文件名如有必要
        try:
            self.team_data = pd.read_csv(csv_path)
            # 设置 TEAM_ID 为索引，便于快速查找
            self.team_data.set_index('TEAM_ID', inplace=True)
            self.logger.debug(f"成功加载球队数据，共 {len(self.team_data)} 支球队。")
        except FileNotFoundError:
            raise FileNotFoundError(
                f"找不到球队数据文件，请确保 team_profile.csv 文件位于以下目录：{NBAConfig.PATHS.DATA_DIR}"
            )
        except pd.errors.EmptyDataError:
            raise ValueError(f"球队数据文件 {csv_path} 是空的或格式错误。")
        except Exception as e:
            raise RuntimeError(f"加载球队数据时发生错误: {e}")

    def _create_lookup_maps(self):
        """创建球队名称到ID的映射"""
        # 将所有可能的键转换为小写，实现不区分大小写的查找
        mappings = []

        # 缩写
        abbrs = self.team_data['ABBREVIATION'].dropna().str.lower()
        team_ids_abbr = self.team_data.index[self.team_data['ABBREVIATION'].notna()]
        mappings.extend(zip(abbrs, team_ids_abbr))

        # 昵称
        nicknames = self.team_data['NICKNAME_x'].dropna().str.lower()
        team_ids_nick = self.team_data.index[self.team_data['NICKNAME_x'].notna()]
        mappings.extend(zip(nicknames, team_ids_nick))

        # 全名（城市 + 昵称）
        full_names = (self.team_data['CITY_x'].dropna() + ' ' + self.team_data['NICKNAME_x'].dropna()).str.lower()
        team_ids_full = self.team_data.index[self.team_data['CITY_x'].notna() & self.team_data['NICKNAME_x'].notna()]
        mappings.extend(zip(full_names, team_ids_full))

        # 创建映射字典
        self.team_maps = dict(mappings)
        self.logger.debug(f"创建了球队名称到ID的映射，共有 {len(self.team_maps)} 个条目。")

    def get_team_id(self, team_name: str) -> Optional[int]:
        """
        根据球队名称获取team_id

        Args:
            team_name (str): 球队名称（可以是缩写、昵称或全名）

        Returns:
            Optional[int]: 如果找到匹配的球队则返回team_id，否则返回None
        """
        team_id = self.team_maps.get(team_name.lower())
        if team_id is None:
            self.logger.warning(f"未找到球队名称: {team_name}")
        return team_id

    def get_team_logo_path(self, team_name: str) -> Optional[Path]:
        """
        获取球队logo的文件路径

        Args:
            team_name (str): 球队名称

        Returns:
            Optional[Path]: logo文件的路径，如果未找到返回None
        """
        team_id = self.get_team_id(team_name)
        if team_id is None:
            self.logger.error(f"无法获取球队ID，无法查找logo路径: {team_name}")
            return None

        try:
            # 获取对应的缩写
            abbr = self.team_data.at[team_id, 'ABBREVIATION']
            if pd.isna(abbr):
                self.logger.error(f"球队ID {team_id} 没有有效的缩写.")
                return None

            # 构建logo文件路径
            logo_path = Path(NBAConfig.PATHS.DATA_DIR) / "nba-team-logo" / f"{abbr} logo.png"

            if logo_path.exists():
                self.logger.debug(f"找到球队logo: {logo_path}")
                return logo_path
            else:
                self.logger.error(f"Logo文件不存在: {logo_path}")
                return None
        except KeyError:
            self.logger.error(f"球队ID {team_id} 不存在于球队数据中.")
            return None
        except Exception as e:
            self.logger.error(f"获取球队logo路径时出错: {e}")
            return None

    def get_team_info(self, team_name: str) -> Optional[Dict[str, Union[str, int, Path]]]:
        """
        获取球队的详细信息

        Args:
            team_name (str): 球队名称

        Returns:
            Optional[Dict]: 包含球队信息的字典，如果未找到返回None
        """
        team_id = self.get_team_id(team_name)
        if team_id is None:
            self.logger.error(f"无法获取球队信息，未找到球队ID: {team_name}")
            return None

        try:
            team_row = self.team_data.loc[team_id]
            team_info = {
                'team_id': team_id,
                'abbreviation': team_row['ABBREVIATION'],
                'nickname': team_row['NICKNAME_x'],
                'city': team_row['CITY_x'],
                'arena': team_row['ARENA'],
                'arena_capacity': team_row['ARENACAPACITY'],
                'owner': team_row['OWNER'],
                'general_manager': team_row['GENERALMANAGER'],
                'head_coach': team_row['HEADCOACH'],
                'logo_path': self.get_team_logo_path(team_name)
            }
            self.logger.debug(f"获取到球队信息: {team_info}")
            return team_info
        except KeyError:
            self.logger.error(f"球队ID {team_id} 在数据中不存在.")
            return None
        except Exception as e:
            self.logger.error(f"获取球队信息时出错: {e}")
            return None

    def __getitem__(self, team_name: str) -> Optional[int]:
        """
        允许使用字典语法获取team_id

        Example:
            team_info = TeamInfo()
            lakers_id = team_info['LAL']
        """
        return self.get_team_id(team_name)
