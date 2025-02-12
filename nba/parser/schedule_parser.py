from typing import Dict, Optional, Union
from datetime import datetime
import pandas as pd
import logging

from utils.logger_handler import AppLogger
from utils.time_handler import NBATimeHandler

class ScheduleParser:
    """NBA赛程数据解析器"""
    # 定义为类属性
    DATE_KEYWORDS = {'today', 'next', 'last'}

    def __init__(self):
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def parse_raw_schedule(self, schedule_data: Dict) -> pd.DataFrame:
        """解析原始赛程数据为DataFrame"""
        try:
            # 添加数据验证
            if not isinstance(schedule_data, dict):
                self.logger.error("输入数据不是字典类型")
                return pd.DataFrame()

            if 'leagueSchedule' not in schedule_data:
                self.logger.error("数据中没有leagueSchedule字段")
                return pd.DataFrame()

            league_schedule = schedule_data['leagueSchedule']
            if 'gameDates' not in league_schedule:
                self.logger.error("leagueSchedule中没有gameDates字段")
                return pd.DataFrame()

            # 添加调试日志
            self.logger.debug(f"Game dates count: {len(league_schedule['gameDates'])}")

            df = pd.json_normalize(
                schedule_data,
                record_path=["leagueSchedule", "gameDates", "games"],
                errors="ignore",
                sep='_'
            )

            if df.empty:
                self.logger.warning("解析后的赛程数据为空")
                # 添加更多调试信息
                self.logger.debug(f"Raw data structure: {schedule_data.keys()}")
                return df

            # 处理时区
            df = self._process_timezone(df)
            self.logger.info(f"解析赛程数据成功，共 {len(df)} 场比赛")
            return df

        except Exception as e:
            self.logger.error(f"Error parsing raw schedule: {e}")
            return pd.DataFrame()

    def _process_timezone(self, df: pd.DataFrame) -> pd.DataFrame:
        """统一处理时区转换"""
        if df.empty:
            return df

        df['gameDateUTC'] = pd.to_datetime(df['gameDateUTC'])
        df['gameDateTimeUTC'] = pd.to_datetime(df['gameDateTimeUTC'])

        # 处理UTC时区
        if not df['gameDateTimeUTC'].dt.tz:
            df['gameDateTimeUTC'] = df['gameDateTimeUTC'].dt.tz_localize(NBATimeHandler.UTC_TZ)
        elif df['gameDateTimeUTC'].dt.tz != NBATimeHandler.UTC_TZ:
            df['gameDateTimeUTC'] = df['gameDateTimeUTC'].dt.tz_convert(NBATimeHandler.UTC_TZ)

        # 转换为北京时间
        df['gameTimeBJS'] = df['gameDateTimeUTC'].dt.tz_convert(NBATimeHandler.BEIJING_TZ)
        df['gameDateBJS'] = df['gameTimeBJS'].dt.date
        
        return df

    def get_game_id(
        self,
        schedule_df: pd.DataFrame,
        team_id: int,
        date_query: Union[str, datetime.date, datetime, None] = 'today'
    ) -> Optional[str]:
        """获取比赛ID"""
        try:
            if schedule_df.empty:
                return None

            # 获取过滤后的球队比赛数据
            team_games = self._filter_team_games(schedule_df, team_id)
            if team_games.empty:
                return None

            # 处理日期查询
            if isinstance(date_query, str):
                game_id = self._handle_date_keyword(team_games, date_query)
            else:
                game_id = self._handle_date_object(team_games, date_query)
            
            if game_id:
                self.logger.info(f"找到比赛ID: {game_id}")
            return game_id

        except Exception as e:
            self.logger.error(f"获取比赛ID失败: {e}")
            return None

    def _filter_team_games(self, df: pd.DataFrame, team_id: int) -> pd.DataFrame:
        """过滤指定球队的比赛"""
        team_filter = (
            (df['homeTeam_teamId'] == team_id) | 
            (df['awayTeam_teamId'] == team_id)
        )
        return df[team_filter].copy()

    def _handle_date_keyword(self, team_games: pd.DataFrame, keyword: str) -> Optional[str]:
        """处理日期关键字查询"""
        try:
            keyword = keyword.lower()
            if keyword not in self.DATE_KEYWORDS:
                try:
                    date_query = datetime.strptime(keyword, '%Y-%m-%d').date()
                    return self._get_game_by_date(team_games, date_query)
                except ValueError:
                    self.logger.error(f"无效的日期格式: {keyword}")
                    return None

            if keyword == 'next':
                return self._get_next_game(team_games)
            elif keyword == 'last':
                return self._get_last_game(team_games)
            else:  # today
                return self._get_game_by_date(
                    team_games, 
                    datetime.now(NBATimeHandler.BEIJING_TZ).date()
                )
        except Exception as e:
            self.logger.error(f"处理日期关键字时出错: {e}")
            return None

    def _handle_date_object(
        self,
        team_games: pd.DataFrame, 
        date_query: Union[datetime.date, datetime, None] = None
    ) -> Optional[str]:
        """处理日期对象查询"""
        try:
            if date_query:
                if isinstance(date_query, datetime):
                    date_query = date_query.date()
                return self._get_game_by_date(team_games, date_query)

            # 没有日期参数时，获取最近结束的比赛
            now_utc = NBATimeHandler.get_current_utc()
            games = team_games[team_games['gameDateTimeUTC'] < now_utc]
            return self._get_first_game_id(
                games.sort_values('gameDateTimeUTC', ascending=False)
            )
        except Exception as e:
            self.logger.error(f"处理日期对象时出错: {e}")
            return None

    def _get_game_by_date(self, games: pd.DataFrame, date: datetime.date) -> Optional[str]:
        """获取指定日期的比赛ID"""
        try:
            games = games[games['gameDateBJS'] == date]
            return self._get_first_game_id(games)
        except Exception as e:
            self.logger.error(f"获取指定日期比赛时出错: {e}")
            return None

    def _get_next_game(self, games: pd.DataFrame) -> Optional[str]:
        """获取下一场比赛ID"""
        try:
            now = datetime.now(NBATimeHandler.UTC_TZ)
            upcoming_games = games[
                (games['gameDateTimeUTC'] > now) & 
                (games['gameStatus'] == 1)
            ].sort_values('gameDateTimeUTC')
            return self._get_first_game_id(upcoming_games)
        except Exception as e:
            self.logger.error(f"获取下一场比赛时出错: {e}")
            return None

    def _get_last_game(self, games: pd.DataFrame) -> Optional[str]:
        """获取最近一场已结束的比赛ID"""
        try:
            now = datetime.now(NBATimeHandler.UTC_TZ)
            finished_games = games[
                games['gameDateTimeUTC'] < now
            ].sort_values('gameDateTimeUTC', ascending=False)
            return self._get_first_game_id(finished_games)
        except Exception as e:
            self.logger.error(f"获取最近一场比赛时出错: {e}")
            return None

    def _get_first_game_id(self, games: pd.DataFrame) -> Optional[str]:
        """获取第一场比赛的ID"""
        try:
            return str(games.iloc[0]['gameId']) if not games.empty else None
        except Exception:
            return None