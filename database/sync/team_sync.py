# database/sync/team_sync.py
from datetime import datetime
from typing import Dict, List, Optional
from database.models.base_models import Team
from nba.fetcher.team_fetcher import TeamFetcher
from utils.logger_handler import AppLogger
from utils.http_handler import HTTPRequestManager
from database.db_session import DBSession


class TeamSync:
    """
    球队数据同步器
    负责从NBA API获取数据、转换并写入数据库
    使用SQLAlchemy ORM进行数据操作
    """

    def __init__(self, team_fetcher=None):
        """初始化球队数据同步器"""
        self.db_session = DBSession.get_instance()
        self.team_fetcher = team_fetcher or TeamFetcher()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def sync_team_details(self, force_update: bool = True) -> bool:
        """同步所有球队的详细信息

        Args:
            force_update: 是否强制更新所有数据

        Returns:
            bool: 同步是否成功
        """
        try:
            # 直接使用 TeamConfig 中的所有球队 ID 列表
            team_ids = self.team_fetcher.team_config.ALL_TEAM_LIST
            self.logger.info(f"开始同步 {len(team_ids)} 支球队的详细信息")

            # 使用批量获取方法获取多个球队的详情
            teams_details = self.team_fetcher.get_multiple_teams_details(team_ids, force_update)

            # 处理获取的结果
            if not teams_details:
                self.logger.warning("未获取到任何球队详情")
                return False

            teams_data = []
            for team_id, details in teams_details.items():
                if not details:
                    continue

                # 解析球队详细信息
                team_data = self._parse_team_details(details, team_id)
                if team_data:
                    teams_data.append(team_data)

            # 批量导入数据库
            success_count = self._import_teams(teams_data) if teams_data else 0

            self.logger.info(f"成功同步 {success_count}/{len(team_ids)} 支球队的详细信息")
            return success_count > 0

        except Exception as e:
            self.logger.error(f"同步球队详细信息失败: {e}")
            return False

    def sync_team_logos(self, force_update: bool = False) -> bool:
        """同步所有球队的Logo

        Args:
            force_update: 是否强制更新

        Returns:
            bool: 同步是否成功
        """
        try:
            # 使用SQLAlchemy会话查询所有球队
            with self.db_session.session_scope('nba') as session:
                teams = session.query(Team).order_by(Team.city, Team.nickname).all()
                team_ids = [team.team_id for team in teams]

            self.logger.info(f"开始同步{len(team_ids)}支球队Logo")

            # 使用TeamFetcher批量获取Logo
            logos_data = self.team_fetcher.get_multiple_team_logos(team_ids, force_update)

            # 处理获取的结果
            if not logos_data:
                self.logger.warning("未获取到任何球队Logo")
                return False

            success_count = 0
            for team_id, logo_data in logos_data.items():
                if logo_data and self._import_team_logo(team_id, logo_data):
                    success_count += 1

            self.logger.info(f"成功同步{success_count}/{len(team_ids)}支球队的Logo")
            return success_count > 0

        except Exception as e:
            self.logger.error(f"同步球队Logo失败: {e}")
            return False

    def _import_teams(self, teams_data: List[Dict]) -> int:
        """
        将球队数据写入数据库

        Args:
            teams_data: 球队数据列表

        Returns:
            int: 成功写入的记录数
        """
        success_count = 0

        try:
            with self.db_session.session_scope('nba') as session:
                for team_data in teams_data:
                    try:
                        team_id = team_data.get('team_id')
                        if not team_id:
                            continue

                        # 查询现有球队
                        team = session.query(Team).filter(Team.team_id == team_id).first()

                        if team:
                            # 更新现有记录
                            for key, value in team_data.items():
                                if key != 'team_id' and hasattr(team, key):
                                    setattr(team, key, value)
                            team.updated_at = datetime.now()
                            self.logger.debug(f"更新球队: {team_data.get('nickname')} (ID: {team_id})")
                        else:
                            # 创建新记录
                            new_team = Team()
                            for key, value in team_data.items():
                                if hasattr(new_team, key):
                                    setattr(new_team, key, value)
                            new_team.updated_at = datetime.now()
                            session.add(new_team)
                            self.logger.info(f"新增球队: {team_data.get('nickname')} (ID: {team_id})")

                        success_count += 1

                    except Exception as e:
                        self.logger.error(f"处理球队记录失败: {e}")
                        # 继续处理下一条记录，但不回滚整个事务

                self.logger.info(f"成功保存{success_count}/{len(teams_data)}支球队数据")

        except Exception as e:
            self.logger.error(f"批量保存球队数据失败: {e}")

        return success_count

    def _import_team_logo(self, team_id: int, logo_data: bytes) -> bool:
        """
        将球队logo数据写入数据库

        Args:
            team_id: 球队ID
            logo_data: 二进制图像数据

        Returns:
            bool: 操作是否成功
        """
        try:
            with self.db_session.session_scope('nba') as session:
                team = session.query(Team).filter(Team.team_id == team_id).first()
                if team:
                    team.logo = logo_data
                    team.updated_at = datetime.now()
                    self.logger.debug(f"保存球队(ID:{team_id})logo成功")
                    return True
                else:
                    self.logger.warning(f"未找到球队(ID:{team_id})，无法保存logo")
                    return False
        except Exception as e:
            self.logger.error(f"保存球队logo失败: {e}")
            return False



    def _parse_team_details(self, team_details: Dict, team_id: int) -> Optional[Dict]:
        """
        解析从API获取的球队详细信息

        Args:
            team_details: 从API获取的球队详情数据
            team_id: 球队ID

        Returns:
            Optional[Dict]: 解析后的球队数据字典
        """
        try:
            if not team_details or 'resultSets' not in team_details:
                self.logger.error(f"球队(ID:{team_id})详细信息格式异常")
                return None

            # 查找 TeamBackground 结果集
            team_info_set = None
            for result_set in team_details['resultSets']:
                if result_set['name'] == 'TeamBackground':
                    team_info_set = result_set
                    break

            if not team_info_set or not team_info_set.get('rowSet'):
                self.logger.error(f"球队(ID:{team_id})没有TeamBackground数据")
                return None

            # 解析表头和数据
            headers = team_info_set['headers']
            team_row = team_info_set['rowSet'][0]

            # 构建原始数据字典（字段名为 API 返回的形式）
            raw_data = {headers[i]: team_row[i] for i in range(len(headers))}

            # 建立 API 字段与数据库字段的映射关系
            mapping = {
                "TEAM_ID": "team_id",
                "ABBREVIATION": "abbreviation",
                "NICKNAME": "nickname",
                "YEARFOUNDED": "year_founded",
                "CITY": "city",
                "ARENA": "arena",
                "ARENACAPACITY": "arena_capacity",
                "OWNER": "owner",
                "GENERALMANAGER": "general_manager",
                "HEADCOACH": "head_coach",
                "DLEAGUEAFFILIATION": "dleague_affiliation"
            }

            # 根据映射转换字段名称
            team_data = {}
            for key, value in raw_data.items():
                if key in mapping:
                    team_data[mapping[key]] = value
                else:
                    # 若没有明确映射，则转换为小写
                    team_data[key.lower()] = value

            # 保留或生成 team_slug 字段
            with self.db_session.session_scope('nba') as session:
                db_team = session.query(Team).filter(Team.team_id == team_id).first()
                if db_team and db_team.team_slug:
                    team_data['team_slug'] = db_team.team_slug
                else:
                    nickname = team_data.get('nickname', '')
                    team_data['team_slug'] = nickname.lower().replace(' ', '-') if nickname else ''

            return team_data

        except Exception as e:
            self.logger.error(f"解析球队(ID:{team_id})详细信息失败: {e}")
            return None