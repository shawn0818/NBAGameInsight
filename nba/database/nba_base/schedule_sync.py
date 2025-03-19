import sqlite3
from typing import Dict, List, Optional, Any
from datetime import datetime

from nba.fetcher.schedule_fetcher import ScheduleFetcher
from utils.logger_handler import AppLogger
from utils.time_handler import TimeHandler


class ScheduleSync:
    """
    赛程数据同步器
    负责从NBA API获取数据、转换并写入数据库
    """

    def __init__(self, db_manager, schedule_fetcher = None, schedule_repository=None):
        """初始化赛程数据同步器"""
        self.db_manager = db_manager
        self.schedule_repository = schedule_repository  # 可选，用于查询
        self.schedule_fetcher = schedule_fetcher or ScheduleFetcher()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.time_handler = TimeHandler()

    def _get_existing_count(self, season: str) -> int:
        """获取数据库中指定赛季的比赛数量"""
        existing_count = 0
        if self.schedule_repository:
            existing_count = self.schedule_repository.get_schedules_count_by_season(season)
        else:
            # 如果没有提供 repository，直接查询数据库
            try:
                cursor = self.db_manager.conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM games WHERE season_year = ?", (season,))
                result = cursor.fetchone()
                existing_count = result[0] if result else 0
            except Exception as e:
                self.logger.error(f"查询赛季数据数量失败: {e}")
        return existing_count

    def sync_all_seasons(self, start_from_season: Optional[str] = None, force_update: bool = False) -> Dict[str, int]:
        """
        同步所有赛季的赛程数据，支持断点续传

        Args:
            start_from_season: 从哪个赛季开始同步，None表示从最早赛季开始
            force_update: 是否强制更新

        Returns:
            Dict[str, int]: 各赛季的同步结果，key为赛季，value为成功同步的比赛数
        """
        results = {}
        seasons = self.schedule_fetcher.get_all_seasons()

        # 如果指定了起始赛季，则只同步该赛季及之后的
        if start_from_season:
            try:
                start_idx = seasons.index(start_from_season)
                seasons = seasons[start_idx:]
            except ValueError:
                self.logger.error(f"找不到指定的起始赛季: {start_from_season}")

        if not force_update:
            # 过滤掉数据库中已有数据的赛季
            filtered_seasons = []
            for season in seasons:
                existing_count = self._get_existing_count(season)
                if existing_count > 0:
                    self.logger.info(f"赛季 {season} 已有 {existing_count} 场比赛数据，跳过同步")
                    results[season] = existing_count
                else:
                    filtered_seasons.append(season)

            seasons = filtered_seasons
            if not seasons:
                self.logger.info("所有赛季数据已存在，无需同步")
                return results

        # 直接使用批量获取功能，内部已实现断点续传和请求间隔控制
        self.logger.info(f"开始批量获取 {len(seasons)} 个赛季的数据...")
        schedule_data = self.schedule_fetcher.get_schedules_for_seasons(
            seasons=seasons,
            force_update=force_update
        )

        for i, season in enumerate(seasons):
            self.logger.info(f"正在处理赛季 {season} 的数据... ({i + 1}/{len(seasons)})")

            # 检查批量获取的结果
            if season not in schedule_data or not schedule_data[season]:
                self.logger.warning(f"赛季 {season} 数据获取失败或为空")
                # 检查数据库中是否已有该赛季数据
                existing_count = self._get_existing_count(season)
                if existing_count > 0:
                    results[season] = existing_count
                    self.logger.info(f"赛季 {season} 已有 {existing_count} 场比赛数据")
                else:
                    results[season] = 0
                continue

            # 解析并导入数据
            games_data = self._parse_schedule_data(schedule_data[season])
            if not games_data:
                self.logger.error(f"解析赛季 {season} 赛程数据失败")
                results[season] = 0
                continue

            # 将数据写入数据库
            success_count = self._import_schedules(games_data)
            results[season] = success_count
            self.logger.info(f"赛季 {season}: 成功同步 {success_count} 场比赛数据")

        return results

    def sync_current_season(self, force_update: bool = True) -> int:
        """
        同步当前赛季的赛程数据

        Args:
            force_update: 是否强制更新

        Returns:
            int: 成功同步的比赛数量
        """
        current_season = self.schedule_fetcher.schedule_config.current_season
        self.logger.info(f"开始同步当前赛季 {current_season} 的数据...")
        result_count = self.sync_season(current_season, force_update)

        # 如果返回 0，但数据已存在，则查询现有记录数
        if result_count == 0:
            existing_count = self._get_existing_count(current_season)
            if existing_count > 0:
                self.logger.info(f"赛季 {current_season} 数据已存在，无需更新")
                return existing_count

        return result_count

    def sync_season(self, season: str, force_update: bool = False) -> int:
        """
        同步指定赛季的赛程数据

        Args:
            season: 赛季字符串
            force_update: 是否强制更新


        Returns:
            int: 成功同步的比赛数量
        """
        try:
            # 获取赛程数据，HTTPRequestManager 内部已实现自适应请求间隔
            schedule_data = self.schedule_fetcher.get_schedule_by_season(
                season, force_update=force_update
            )
            if not schedule_data:
                self.logger.error(f"获取赛季 {season} 赛程数据失败")
                return 0

            # 解析赛程数据
            games_data = self._parse_schedule_data(schedule_data)
            if not games_data:
                self.logger.error(f"解析赛季 {season} 赛程数据失败")
                return 0

            # 将数据写入数据库
            success_count = self._import_schedules(games_data)

            # 如果没有处理任何记录，但数据可能已存在，则查询现有记录数
            if success_count == 0:
                existing_count = self._get_existing_count(season)
                if existing_count > 0:
                    self.logger.info(f"赛季 {season} 数据已存在，无需更新")
                    return existing_count

            self.logger.info(f"赛季 {season}: 成功同步 {success_count} 场比赛数据")
            return success_count

        except Exception as e:
            self.logger.error(f"同步赛季 {season} 赛程数据失败: {e}")
            return 0

    def _import_schedules(self, schedules_data: List[Dict]) -> int:
        """
        将赛程数据写入数据库

        Args:
            schedules_data: 赛程数据列表

        Returns:
            int: 成功写入的记录数
        """
        success_count = 0
        conn = self.db_manager.conn

        try:
            cursor = conn.cursor()

            for schedule_data in schedules_data:
                try:
                    game_id = schedule_data.get('game_id')

                    # 添加更新时间
                    schedule_data['updated_at'] = datetime.now().isoformat()

                    # 检查是否已存在该比赛
                    cursor.execute("SELECT game_id FROM games WHERE game_id = ?", (game_id,))
                    exists = cursor.fetchone()

                    if exists:
                        # 更新现有记录
                        placeholders = ", ".join([f"{k} = ?" for k in schedule_data.keys() if k != 'game_id'])
                        values = [v for k, v in schedule_data.items() if k != 'game_id']
                        values.append(game_id)  # WHERE条件的值

                        cursor.execute(f"UPDATE games SET {placeholders} WHERE game_id = ?", values)
                        self.logger.debug(f"更新赛程: {game_id}")
                    else:
                        # 插入新记录
                        placeholders = ", ".join(["?"] * len(schedule_data))
                        columns = ", ".join(schedule_data.keys())
                        values = list(schedule_data.values())

                        cursor.execute(f"INSERT INTO games ({columns}) VALUES ({placeholders})", values)
                        self.logger.debug(f"新增赛程: {game_id}")

                    success_count += 1

                except Exception as e:
                    self.logger.error(f"处理赛程记录失败: {e}")
                    # 继续处理下一条记录

            conn.commit()
            self.logger.info(f"成功保存{success_count}/{len(schedules_data)}条赛程数据")

        except sqlite3.Error as e:
            conn.rollback()
            self.logger.error(f"批量保存赛程数据失败: {e}")

        return success_count

    def _parse_schedule_data(self, schedule_data: Dict) -> List[Dict]:
        """
        解析赛程数据

        Args:
            schedule_data: 从API获取的原始数据

        Returns:
            List[Dict]: 解析后的比赛数据列表
        """
        games_data = []
        try:
            if 'leagueSchedule' not in schedule_data:
                self.logger.error("数据结构不包含leagueSchedule字段")
                return games_data  # 返回空列表而不是None

            league_schedule = schedule_data['leagueSchedule']
            season_year = league_schedule.get('seasonYear', '')

            # 辅助函数，提取队伍信息
            def extract_team_info(team_data: Dict) -> Dict[str, Any]:
                return {
                    'team_id': team_data.get('teamId', 0),
                    'team_name': team_data.get('teamName', ''),
                    'team_city': team_data.get('teamCity', ''),
                    'team_tricode': team_data.get('teamTricode', ''),
                    'team_slug': team_data.get('teamSlug', ''),
                    'team_wins': team_data.get('wins', 0),
                    'team_losses': team_data.get('losses', 0),
                    'team_score': team_data.get('score', 0),
                    'team_seed': team_data.get('seed', 0)
                }

            # 解析每个日期的比赛
            for game_date in league_schedule.get('gameDates', []):
                for game in game_date.get('games', []):
                    # 获取基本信息
                    game_id = game.get('gameId', '')
                    game_code = game.get('gameCode', '')
                    game_status = game.get('gameStatus', 0)
                    game_status_text = game.get('gameStatusText', '')

                    # 日期和时间
                    game_date_est = game.get('gameDateEst', '')
                    game_time_est = game.get('gameTimeEst', '')
                    game_date_time_est = game.get('gameDateTimeEst', '')
                    game_date_utc = game.get('gameDateUTC', '')
                    game_time_utc = game.get('gameTimeUTC', '')
                    game_date_time_utc = game.get('gameDateTimeUTC', '')

                    # 提取比赛日期
                    game_date_str = ""
                    if game_date_est:
                        try:
                            dt = datetime.fromisoformat(game_date_est.replace('Z', '+00:00'))
                            game_date_str = dt.strftime('%Y-%m-%d')
                        except (ValueError, TypeError):
                            game_date_str = game_date_est.split()[0]

                    # 赛季信息
                    week_number = game.get('weekNumber', 0)
                    week_name = game.get('weekName', '')
                    series_game_number = game.get('seriesGameNumber', '')
                    if_necessary = game.get('ifNecessary', 'false')
                    series_text = game.get('seriesText', '')

                    # 确定比赛类型
                    game_type = "Regular Season"  # 默认为常规赛
                    if series_text:
                        if "Preseason" in series_text:
                            game_type = "Preseason"
                        elif "Playoffs" in series_text or any(x in series_text for x in ["leads", "tied", "won"]):
                            game_type = "Playoffs"
                        elif "Play-In" in series_text:
                            game_type = "Play-In"
                        elif "All-Star" in series_text:
                            game_type = "All-Star"

                    # 场馆信息
                    arena_name = game.get('arenaName', '')
                    arena_city = game.get('arenaCity', '')
                    arena_state = game.get('arenaState', '')
                    arena_is_neutral = game.get('isNeutral', False)

                    # 使用辅助函数提取队伍信息
                    home_team_info = extract_team_info(game.get('homeTeam', {}))
                    away_team_info = extract_team_info(game.get('awayTeam', {}))

                    # 得分领先者
                    points_leader = {}
                    points_leaders = game.get('pointsLeaders', [])
                    if points_leaders and len(points_leaders) > 0:
                        points_leader = points_leaders[0]

                    points_leader_id = points_leader.get('personId', 0)
                    points_leader_first_name = points_leader.get('firstName', '')
                    points_leader_last_name = points_leader.get('lastName', '')
                    points_leader_team_id = points_leader.get('teamId', 0)
                    points_leader_points = points_leader.get('points', 0.0)

                    # 其他信息
                    game_sub_type = game.get('gameSubtype', '')
                    game_label = game.get('gameLabel', '')
                    game_sub_label = game.get('gameSubLabel', '')
                    postponed_status = game.get('postponedStatus', '')

                    # 转换UTC时间到北京时间
                    game_date_time_bjs = None
                    game_date_bjs = None
                    game_time_bjs = None

                    if game_date_time_utc:
                        try:
                            utc_dt = datetime.fromisoformat(game_date_time_utc.replace('Z', '+00:00'))
                            game_date_time_bjs = self.time_handler.to_beijing(utc_dt).isoformat()
                            game_date_bjs = self.time_handler.to_beijing(utc_dt).strftime('%Y-%m-%d')
                            game_time_bjs = self.time_handler.to_beijing(utc_dt).strftime('%H:%M:%S')
                        except (ValueError, TypeError) as e:
                            self.logger.warning(f"时间转换失败: {e}, 原始UTC时间: {game_date_time_utc}")

                    # 组装比赛数据
                    game_data = {
                        'game_id': game_id,
                        'game_code': game_code,
                        'game_status': game_status,
                        'game_status_text': game_status_text,
                        'game_date_est': game_date_est,
                        'game_time_est': game_time_est,
                        'game_date_time_est': game_date_time_est,
                        'game_date_utc': game_date_utc,
                        'game_time_utc': game_time_utc,
                        'game_date_time_utc': game_date_time_utc,
                        'game_date': game_date_str,
                        'season_year': season_year,
                        'week_number': week_number,
                        'week_name': week_name,
                        'series_game_number': series_game_number,
                        'if_necessary': if_necessary,
                        'series_text': series_text,
                        'arena_name': arena_name,
                        'arena_city': arena_city,
                        'arena_state': arena_state,
                        'arena_is_neutral': arena_is_neutral,
                        'home_team_id': home_team_info['team_id'],
                        'home_team_name': home_team_info['team_name'],
                        'home_team_city': home_team_info['team_city'],
                        'home_team_tricode': home_team_info['team_tricode'],
                        'home_team_slug': home_team_info['team_slug'],
                        'home_team_wins': home_team_info['team_wins'],
                        'home_team_losses': home_team_info['team_losses'],
                        'home_team_score': home_team_info['team_score'],
                        'home_team_seed': home_team_info['team_seed'],
                        'away_team_id': away_team_info['team_id'],
                        'away_team_name': away_team_info['team_name'],
                        'away_team_city': away_team_info['team_city'],
                        'away_team_tricode': away_team_info['team_tricode'],
                        'away_team_slug': away_team_info['team_slug'],
                        'away_team_wins': away_team_info['team_wins'],
                        'away_team_losses': away_team_info['team_losses'],
                        'away_team_score': away_team_info['team_score'],
                        'away_team_seed': away_team_info['team_seed'],
                        'points_leader_id': points_leader_id,
                        'points_leader_first_name': points_leader_first_name,
                        'points_leader_last_name': points_leader_last_name,
                        'points_leader_team_id': points_leader_team_id,
                        'points_leader_points': points_leader_points,
                        'game_type': game_type,
                        'game_sub_type': game_sub_type,
                        'game_label': game_label,
                        'game_sub_label': game_sub_label,
                        'postponed_status': postponed_status,
                        'game_date_bjs': game_date_bjs,
                        'game_time_bjs': game_time_bjs,
                        'game_date_time_bjs': game_date_time_bjs
                    }

                    games_data.append(game_data)

            self.logger.info(f"成功解析 {len(games_data)} 场比赛数据")
            return games_data

        except Exception as e:
            self.logger.error(f"解析赛程数据失败: {e}", exc_info=True)
            return games_data  # 返回空列表或已解析的数据