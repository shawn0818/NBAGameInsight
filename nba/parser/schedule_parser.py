from typing import Dict, Optional, Union
from datetime import datetime
import pandas as pd
import numpy as np
import logging
from utils.time_handler import NBATimeHandler

logger = logging.getLogger(__name__)

class ScheduleParser:
    """NBA赛程数据解析器"""
    
    # 特殊日期关键字
    DATE_KEYWORDS = {
        'today': 'today',    # 今天的比赛
        'next': 'next',      # 下一场比赛
        'last': 'last',      # 上一场比赛
    }

    @staticmethod
    def parse_raw_schedule(schedule_data: Dict) -> pd.DataFrame:
        """解析原始赛程数据为DataFrame，并处理时区转换"""
        logger = logging.getLogger(__name__)
        try:
            df = pd.json_normalize(
                schedule_data,
                record_path=["leagueSchedule", "gameDates", "games"],
                errors="ignore",
                sep='_'
            )
            
            if not df.empty:
                # 处理UTC时间
                df['gameDateUTC'] = pd.to_datetime(df['gameDateUTC'])
                df['gameDateTimeUTC'] = pd.to_datetime(df['gameDateTimeUTC'])

                # 检查时区信息
                if not df['gameDateTimeUTC'].dt.tz:
                    df['gameDateTimeUTC'] = df['gameDateTimeUTC'].dt.tz_localize(NBATimeHandler.UTC_TZ)
                elif df['gameDateTimeUTC'].dt.tz != NBATimeHandler.UTC_TZ:
                    df['gameDateTimeUTC'] = df['gameDateTimeUTC'].dt.tz_convert(NBATimeHandler.UTC_TZ)
                
                # 转换为北京时间
                df['gameTimeBJS'] = df['gameDateTimeUTC'].dt.tz_convert(NBATimeHandler.BEIJING_TZ)
                df['gameDateBJS'] = df['gameTimeBJS'].dt.date  # 获取日期部分
                
                logger.info(f"解析赛程数据成功，共 {len(df)} 场比赛")
            else:
                logger.warning("解析后的赛程数据为空")
            
            return df
        
        except Exception as e:
            logger.error(f"Error parsing raw schedule: {e}")
            return pd.DataFrame()

    @staticmethod
    def get_game_id(
        schedule_df: pd.DataFrame,
        team_id: int,
        date_query: Union[str, datetime.date, datetime, None] = 'today'
    ) -> Optional[str]:
        """
        获取比赛ID，支持多种日期查询方式
        
        Args:
            schedule_df: 赛程DataFrame
            team_id: 球队ID
            date_query: 日期查询参数，支持以下格式：
                - 'today': 今天的比赛
                - 'next': 下一场比赛
                - 'last': 上一场比赛
                - datetime.date对象: 指定日期的比赛
                - 字符串日期 (YYYY-MM-DD): 指定日期的比赛
                
        Returns:
            Optional[str]: 比赛ID，如果未找到返回None
        """
        try:
            if schedule_df.empty:
                return None

            # 处理特殊关键字
            if isinstance(date_query, str):
                date_query = date_query.lower()
                if date_query == ScheduleParser.DATE_KEYWORDS['next']:
                    return ScheduleParser.get_upcoming_game_id(schedule_df, team_id)
                elif date_query == ScheduleParser.DATE_KEYWORDS['last']:
                    return ScheduleParser.get_last_game_id(schedule_df, team_id)
                elif date_query == ScheduleParser.DATE_KEYWORDS['today']:
                    date_query = datetime.now(NBATimeHandler.BEIJING_TZ).date()
                else:
                    # 尝试解析日期字符串
                    try:
                        date_query = datetime.strptime(date_query, '%Y-%m-%d').date()
                    except ValueError:
                        logger.error(f"无效的日期格式: {date_query}")
                        return None
            
            # 如果是datetime对象，转换为date
            elif isinstance(date_query, datetime):
                date_query = date_query.date()

            # 过滤球队比赛
            team_filter = (
                (schedule_df['homeTeam_teamId'] == team_id) | 
                (schedule_df['awayTeam_teamId'] == team_id)
            )
            team_games = schedule_df[team_filter].copy()
            
            if date_query:
                # 按日期过滤
                games = team_games[team_games['gameDateBJS'] == date_query]
            else:
                # 没有日期参数时，获取最近的比赛
                now = datetime.now(NBATimeHandler.UTC_TZ)
                games = team_games[team_games['gameDateTimeUTC'] >= now]
                games = games.sort_values('gameDateTimeUTC')
            
            if games.empty:
                return None
                
            game_id = str(games.iloc[0]['gameId'])
            logger.info(f"找到比赛ID: {game_id}")
            return game_id
            
        except Exception as e:
            logger.error(f"获取比赛ID失败: {e}")
            return None

    @staticmethod
    def get_upcoming_game_id(schedule_df: pd.DataFrame, team_id: int) -> Optional[str]:
        """
        获取球队的下一场比赛ID
        
        Args:
            schedule_df: 赛程DataFrame
            team_id: 球队ID
            
        Returns:
            Optional[str]: 比赛ID，如果未找到返回None
        """
        try:
            if schedule_df.empty:
                return None
                
            # 过滤球队比赛
            team_filter = (
                (schedule_df['homeTeam_teamId'] == team_id) | 
                (schedule_df['awayTeam_teamId'] == team_id)
            )
            team_games = schedule_df[team_filter].copy()
            
            # 获取未开始的比赛
            now = datetime.now(NBATimeHandler.UTC_TZ)
            upcoming_games = team_games[
                (team_games['gameDateTimeUTC'] > now) & 
                (team_games['gameStatus'] == 1)  # 未开始的比赛
            ]
            
            if upcoming_games.empty:
                return None
                
            # 返回最近的一场
            next_game = upcoming_games.sort_values('gameDateTimeUTC').iloc[0]
            game_id = str(next_game['gameId'])
            logger.info(f"找到下一场比赛: {game_id}")
            return game_id
            
        except Exception as e:
            logger.error(f"获取下一场比赛ID失败: {e}")
            return None

    @staticmethod
    def get_last_game_id(schedule_df: pd.DataFrame, team_id: int) -> Optional[str]:
        """
        获取球队的上一场比赛ID
        
        Args:
            schedule_df: 赛程DataFrame
            team_id: 球队ID
            
        Returns:
            Optional[str]: 比赛ID，如果未找到返回None
        """
        try:
            if schedule_df.empty:
                return None
                
            # 过滤球队比赛
            team_filter = (
                (schedule_df['homeTeam_teamId'] == team_id) | 
                (schedule_df['awayTeam_teamId'] == team_id)
            )
            team_games = schedule_df[team_filter].copy()
            
            # 获取已结束的比赛
            now = datetime.now(NBATimeHandler.UTC_TZ)
            finished_games = team_games[
                (team_games['gameDateTimeUTC'] < now) & 
                (team_games['gameStatus'] == 3)  # 已结束的比赛
            ]
            
            if finished_games.empty:
                return None
                
            # 返回最近的一场
            last_game = finished_games.sort_values('gameDateTimeUTC', ascending=False).iloc[0]
            game_id = str(last_game['gameId'])
            logger.info(f"找到上一场比赛: {game_id}")
            return game_id
            
        except Exception as e:
            logger.error(f"获取上一场比赛ID失败: {e}")
            return None