import sqlite3
from typing import Dict, List
from datetime import datetime
from nba.fetcher.player_fetcher import PlayerFetcher
from utils.logger_handler import AppLogger


class PlayerSync:
    """
    球员数据同步器
    负责从NBA API获取数据、转换并写入数据库
    """

    def __init__(self, db_manager, player_repository=None, player_fetcher=None):
        """初始化球员数据同步器"""
        self.db_manager = db_manager
        self.player_repository = player_repository  # 可选，用于查询
        self.player_fetcher = player_fetcher or PlayerFetcher()
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')

    def sync_players(self, force_update: bool = False) -> bool:
        """
        同步球员数据

        Args:
            force_update: 是否强制更新所有数据

        Returns:
            bool: 同步是否成功
        """
        try:
            # 如果不强制更新，检查是否有数据
            if not force_update and self.player_repository:
                players = self.player_repository.get_all_players()
                if players:
                    self.logger.info(f"数据库中已有{len(players)}名球员数据，跳过同步")
                    return True

            # 获取球员名册数据
            players_data = self.player_fetcher.get_all_players_info()
            if not players_data:
                self.logger.error("获取球员名册数据失败")
                return False

            # 解析球员数据
            parsed_players = self._parse_players_data(players_data)
            if not parsed_players:
                self.logger.error("解析球员数据失败")
                return False

            # 直接写入数据库
            success_count = self._import_players(parsed_players)
            self.logger.info(f"成功同步{success_count}名球员数据")

            return success_count > 0

        except Exception as e:
            self.logger.error(f"同步球员数据失败: {e}")
            return False

    def _import_players(self, players_data: List[Dict]) -> int:
        """
        将球员数据写入数据库

        Args:
            players_data: 球员数据列表

        Returns:
            int: 成功写入的记录数
        """
        success_count = 0
        conn = self.db_manager.conn

        try:
            cursor = conn.cursor()

            for player_data in players_data:
                try:
                    person_id = player_data.get('person_id')
                    if not person_id:
                        continue

                    # 添加更新时间
                    player_data['updated_at'] = datetime.now().isoformat()

                    # 检查是否已存在该球员
                    cursor.execute("SELECT person_id FROM players WHERE person_id = ?", (person_id,))
                    exists = cursor.fetchone()

                    if exists:
                        # 更新现有记录
                        placeholders = ", ".join([f"{k} = ?" for k in player_data.keys() if k != 'person_id'])
                        values = [v for k, v in player_data.items() if k != 'person_id']
                        values.append(person_id)  # WHERE条件的值

                        cursor.execute(f"UPDATE players SET {placeholders} WHERE person_id = ?", values)
                    else:
                        # 插入新记录
                        placeholders = ", ".join(["?"] * len(player_data))
                        columns = ", ".join(player_data.keys())
                        values = list(player_data.values())

                        cursor.execute(f"INSERT INTO players ({columns}) VALUES ({placeholders})", values)

                    success_count += 1

                except Exception as e:
                    self.logger.error(f"处理球员记录失败: {e}")
                    # 继续处理下一条记录

            conn.commit()
            self.logger.info(f"成功保存{success_count}/{len(players_data)}名球员数据")

        except sqlite3.Error as e:
            conn.rollback()
            self.logger.error(f"批量保存球员数据失败: {e}")

        return success_count

    def _parse_players_data(self, players_data: Dict) -> List[Dict]:
        """
        解析球员名册数据

        Args:
            players_data: 原始球员数据

        Returns:
            List[Dict]: 解析后的球员数据列表
        """
        parsed_players = []

        try:
            if 'resultSets' not in players_data or not players_data['resultSets']:
                self.logger.error("球员数据格式不正确")
                return []

            players_set = players_data['resultSets'][0]
            headers = {name: idx for idx, name in enumerate(players_set['headers'])}

            for player in players_set['rowSet']:
                # 使用数据库表中的字段名
                player_data = {
                    'person_id': player[headers['PERSON_ID']],
                    'display_last_comma_first': player[headers.get('DISPLAY_LAST_COMMA_FIRST', '')],
                    'display_first_last': player[headers.get('DISPLAY_FIRST_LAST', '')],
                    'roster_status': player[headers.get('ROSTERSTATUS')],
                    'from_year': player[headers.get('FROM_YEAR')],
                    'to_year': player[headers.get('TO_YEAR')],
                    'player_slug': player[headers.get('PLAYERCODE', '')],
                    'team_id': player[headers.get('TEAM_ID')],
                    'games_played_flag': player[headers.get('GAMES_PLAYED_FLAG', '')]
                }

                # 如果team_id为0，设置为None
                if player_data['team_id'] == 0:
                    player_data['team_id'] = None

                parsed_players.append(player_data)

            return parsed_players

        except Exception as e:
            self.logger.error(f"解析球员数据失败: {e}")
            return []