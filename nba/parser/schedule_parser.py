from typing import Dict, Optional, Union
from datetime import datetime
import pandas as pd
import logging
from utils.time_handler import NBATimeHandler

logger = logging.getLogger(__name__)

class ScheduleParser:
    """NBA赛程数据解析器"""
    
    DATE_KEYWORDS = {'today', 'next', 'last'}

    @staticmethod
    def parse_raw_schedule(schedule_data: Dict) -> pd.DataFrame:
        """解析原始赛程数据为DataFrame"""
        try:
            df = pd.json_normalize(
                schedule_data,
                record_path=["leagueSchedule", "gameDates", "games"],
                errors="ignore",
                sep='_'
            )
            
            if df.empty:
                logger.warning("解析后的赛程数据为空")
                return df

            # 统一处理时区转换
            df = ScheduleParser._process_timezone(df)
            logger.info(f"解析赛程数据成功，共 {len(df)} 场比赛")
            return df
            
        except Exception as e:
            logger.error(f"Error parsing raw schedule: {e}")
            return pd.DataFrame()

    @staticmethod
    def _process_timezone(df: pd.DataFrame) -> pd.DataFrame:
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

    @staticmethod
    def get_game_id(
        schedule_df: pd.DataFrame,
        team_id: int,
        date_query: Union[str, datetime.date, datetime, None] = 'today'
    ) -> Optional[str]:
        """获取比赛ID"""
        try:
            if schedule_df.empty:
                return None

            # 获取过滤后的球队比赛数据
            team_games = ScheduleParser._filter_team_games(schedule_df, team_id)
            if team_games.empty:
                return None

            # 处理日期查询
            if isinstance(date_query, str):
                game_id = ScheduleParser._handle_date_keyword(team_games, date_query)
            else:
                game_id = ScheduleParser._handle_date_object(team_games, date_query)
            
            if game_id:
                logger.info(f"找到比赛ID: {game_id}")
            return game_id

        except Exception as e:
            logger.error(f"获取比赛ID失败: {e}")
            return None

    @staticmethod
    def _filter_team_games(df: pd.DataFrame, team_id: int) -> pd.DataFrame:
        """过滤指定球队的比赛"""
        team_filter = (
            (df['homeTeam_teamId'] == team_id) | 
            (df['awayTeam_teamId'] == team_id)
        )
        return df[team_filter].copy()

    @staticmethod
    def _handle_date_keyword(team_games: pd.DataFrame, keyword: str) -> Optional[str]:
        """处理日期关键字查询"""
        keyword = keyword.lower()
        if keyword not in ScheduleParser.DATE_KEYWORDS:
            try:
                date_query = datetime.strptime(keyword, '%Y-%m-%d').date()
                return ScheduleParser._get_game_by_date(team_games, date_query)
            except ValueError:
                logger.error(f"无效的日期格式: {keyword}")
                return None

        if keyword == 'next':
            return ScheduleParser._get_next_game(team_games)
        elif keyword == 'last':
            return ScheduleParser._get_last_game(team_games)
        else:  # today
            return ScheduleParser._get_game_by_date(
                team_games, 
                datetime.now(NBATimeHandler.BEIJING_TZ).date()
            )

    @staticmethod
    def _handle_date_object(
        team_games: pd.DataFrame, 
        date_query: Union[datetime.date, datetime, None]
    ) -> Optional[str]:
        """处理日期对象查询"""
        if isinstance(date_query, datetime):
            date_query = date_query.date()
            
        if date_query:
            return ScheduleParser._get_game_by_date(team_games, date_query)
            
        # 没有日期参数时，获取最近的比赛
        now = datetime.now(NBATimeHandler.UTC_TZ)
        games = team_games[team_games['gameDateTimeUTC'] >= now]
        return ScheduleParser._get_first_game_id(games)

    @staticmethod
    def _get_game_by_date(games: pd.DataFrame, date: datetime.date) -> Optional[str]:
        """获取指定日期的比赛ID"""
        games = games[games['gameDateBJS'] == date]
        return ScheduleParser._get_first_game_id(games)

    @staticmethod
    def _get_next_game(games: pd.DataFrame) -> Optional[str]:
        """获取下一场比赛ID"""
        now = datetime.now(NBATimeHandler.UTC_TZ)
        upcoming_games = games[
            (games['gameDateTimeUTC'] > now) & 
            (games['gameStatus'] == 1)
        ].sort_values('gameDateTimeUTC')
        return ScheduleParser._get_first_game_id(upcoming_games)

    @staticmethod
    def _get_last_game(games: pd.DataFrame) -> Optional[str]:
        """获取上一场比赛ID"""
        now = datetime.now(NBATimeHandler.UTC_TZ)
        finished_games = games[
            (games['gameDateTimeUTC'] < now) & 
            (games['gameStatus'] == 3)
        ].sort_values('gameDateTimeUTC', ascending=False)
        return ScheduleParser._get_first_game_id(finished_games)

    @staticmethod
    def _get_first_game_id(games: pd.DataFrame) -> Optional[str]:
        """获取第一场比赛的ID"""
        return str(games.iloc[0]['gameId']) if not games.empty else None