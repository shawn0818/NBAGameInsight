from datetime import datetime
from typing import Dict, List, Optional
from nba.fetcher.league_fetcher import LeagueFetcher
from nba.fetcher.team_fetcher import TeamFetcher
from nba.database.team_repository import TeamRepository
from utils.logger_handler import AppLogger


class TeamSync:
    """
    球队数据同步器
    负责从NBA API获取数据并同步到本地数据库
    """

    def __init__(self, team_repository: TeamRepository, league_fetcher: Optional[LeagueFetcher] = None,
                 team_fetcher: Optional[TeamFetcher] = None):
        """初始化球队数据同步器"""
        self.team_repository = team_repository
        self.league_fetcher = league_fetcher or LeagueFetcher()
        self.team_fetcher = team_fetcher or TeamFetcher()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')


    def sync_team_details(self, force_update: bool = False) -> bool:
        """
        同步所有球队的详细信息

        Args:
            force_update: 是否强制更新所有数据

        Returns:
            bool: 同步是否成功
        """
        try:
            # 获取所有球队ID
            team_ids = self.league_fetcher.get_all_team_ids()
            if not team_ids:
                self.logger.error("无法获取球队ID列表")
                return False

            success_count = 0
            total_count = len(team_ids)

            # 遍历获取每个球队的详细信息
            for team_id in team_ids:
                # 如果不强制更新，检查数据库中是否已有详细信息
                if not force_update and self.team_repository.has_team_details(team_id):
                    self.logger.debug(f"球队(ID:{team_id})已有详细信息，跳过更新")
                    success_count += 1
                    continue

                # 获取球队详细信息
                team_details = self.team_fetcher.get_team_details(team_id, force_update=force_update)
                if not team_details:
                    self.logger.warning(f"获取球队(ID:{team_id})详细信息失败")
                    continue

                # 解析球队详细信息
                team_data = self._parse_team_details(team_details, team_id)
                if not team_data:
                    continue

                # 保存到数据库
                if self.team_repository.save_team(team_data):
                    success_count += 1
                    self.logger.info(f"更新球队详细信息成功: {team_data.get('NICKNAME', team_id)}")

            self.logger.info(f"成功同步{success_count}/{total_count}支球队的详细信息")
            return success_count > 0

        except Exception as e:
            self.logger.error(f"同步球队详细信息失败: {e}")
            return False

    def sync_team_logos(self) -> bool:
        """
        同步所有球队的Logo

        Returns:
            bool: 同步是否成功
        """
        try:
            success_count = self.team_repository.sync_team_logos()
            self.logger.info(f"成功同步{success_count}支球队的Logo")
            return success_count > 0
        except Exception as e:
            self.logger.error(f"同步球队Logo失败: {e}")
            return False

    def _parse_team_details(self, team_details: Dict, team_id: int) -> Optional[Dict]:
        """从team_details响应中解析球队详细信息

        Args:
            team_details: 球队详细信息响应
            team_id: 球队ID

        Returns:
            Optional[Dict]: 解析后的球队数据，解析失败返回None
        """
        try:
            if not team_details or 'resultSets' not in team_details:
                self.logger.error(f"球队(ID:{team_id})详细信息格式异常")
                return None

            # 查找TeamBackground结果集
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

            # 创建字典
            team_data = {headers[i]: team_row[i] for i in range(len(headers))}

            # 获取数据库中已有的team_slug信息（如果有）
            db_team = self.team_repository.get_team_by_id(team_id)
            if db_team and db_team.get('team_slug'):
                team_data['team_slug'] = db_team['team_slug']
            else:
                # 生成新的team_slug
                nickname = team_data.get('NICKNAME', '')
                team_data['team_slug'] = nickname.lower().replace(' ', '-') if nickname else ''

            return team_data

        except Exception as e:
            self.logger.error(f"解析球队(ID:{team_id})详细信息失败: {e}")
            return None

