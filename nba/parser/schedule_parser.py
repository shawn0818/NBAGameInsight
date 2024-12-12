from typing import Dict, Optional, List
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from pytz import timezone

from utils.time_helper import TimeConverter
from config.nba_config import NBAConfig

class ScheduleParser:
    """
    NBA赛程数据解析器
    主要职责：
    1. 解析原始赛程数据（处理UTC与北京时间转换）
    2. 获取比赛ID（作为连接赛程和比赛详情的桥梁）
    3. 提供基本的赛程查询功能
    """

    @staticmethod
    def parse_raw_schedule(schedule_data: Dict) -> pd.DataFrame:
        """解析原始赛程数据为DataFrame，并处理时区转换"""
        try:
            df = pd.json_normalize(
                schedule_data,
                record_path=["leagueSchedule", "gameDates", "games"],
                errors="ignore",
                sep='_'
            )
            
            if not df.empty:
                # 处理UTC时间
                df['gameDateUTC'] = pd.to_datetime(df['gameDateUTC']).dt.date
                df['gameDateTimeUTC'] = pd.to_datetime(df['gameDateTimeUTC'])
                
                # 添加北京时间列（使用TimeConverter）
                df['gameTimeBJS'] = df['gameDateTimeUTC'].apply(TimeConverter.to_beijing_time)
                df['gameDateBJS'] = df['gameDateTimeUTC'].apply(
                    lambda x: TimeConverter.adjust_to_beijing_date(x)
                )
            
            return df
            
        except Exception as e:
            logging.error(f"Error parsing raw schedule: {e}")
            return pd.DataFrame()

    @staticmethod
    def filter_team_schedule(schedule_df: pd.DataFrame, team_id: Optional[int] = None, 
                           game_date: Optional[str] = None, future_only: bool = True) -> pd.DataFrame:
        """
        筛选球队赛程
        
        Args:
            schedule_df: 赛程DataFrame
            team_id: 球队ID（可选）
            game_date: 北京时间日期字符串（可选）
            future_only: 是否只返回未来比赛
        """
        try:
            if schedule_df.empty:
                return pd.DataFrame()

            filtered_df = schedule_df.copy()
            
            # 球队筛选
            if team_id:
                team_filter = (
                    (filtered_df['homeTeam_teamId'] == int(team_id)) | 
                    (filtered_df['awayTeam_teamId'] == int(team_id))
                )
                filtered_df = filtered_df[team_filter].copy()
                
                # 添加主客场标识
                filtered_df['home_or_away'] = np.where(
                    filtered_df['homeTeam_teamId'] == int(team_id),
                    'home', 'away'
                )

            # 日期筛选
            if game_date:
                # 解析输入的北京时间日期
                parsed_date = TimeConverter.parse_date(game_date)
                if parsed_date:
                    filtered_df = filtered_df[filtered_df['gameDateBJS'] == parsed_date]
            elif future_only:
                # 使用北京时间判断未来比赛
                beijing_now = datetime.now(TimeConverter.BEIJING_TZ)
                filtered_df = filtered_df[
                    filtered_df['gameDateTimeUTC'] >= beijing_now.astimezone(TimeConverter.UTC_TZ)
                ]

            return filtered_df.reset_index(drop=True)
            
        except Exception as e:
            logging.error(f"Error filtering team schedule: {e}")
            return pd.DataFrame()

    @staticmethod
    def get_game_id(schedule_df: pd.DataFrame, team_id: int, 
                    game_date: Optional[str] = None) -> Optional[str]:
        """获取指定球队在特定日期的比赛ID（基于北京时间）"""
        try:
            filtered_df = ScheduleParser.filter_team_schedule(
                schedule_df=schedule_df,
                team_id=team_id,
                game_date=game_date,
                future_only=False
            )
            
            if not filtered_df.empty:
                return str(filtered_df.iloc[0]['gameId'])
            return None
            
        except Exception as e:
            logging.error(f"Error getting game ID: {e}")
            return None

    @staticmethod
    def get_team_games(schedule_df: pd.DataFrame, team_id: int, 
                      days: int = 7, future_only: bool = True) -> List[Dict]:
        """获取球队近期比赛信息"""
        try:
            filtered_df = ScheduleParser.filter_team_schedule(
                schedule_df=schedule_df,
                team_id=team_id,
                future_only=future_only
            )
            
            if filtered_df.empty:
                return []

            # 基于北京时间进行日期范围筛选
            beijing_now = datetime.now(TimeConverter.BEIJING_TZ)
            date_range = pd.date_range(
                start=beijing_now.date() - pd.Timedelta(days=days),
                end=beijing_now.date() + pd.Timedelta(days=days)
            )
            
            filtered_df = filtered_df[
                filtered_df['gameDateBJS'].isin(date_range)
            ].sort_values('gameDateTimeUTC')
            
            return [{
                'game_id': str(row['gameId']),
                'date_bjs': row['gameDateBJS'],
                'time_bjs': row['gameTimeBJS'],
                'home_team_id': row['homeTeam_teamId'],
                'away_team_id': row['awayTeam_teamId'],
                'home_or_away': row['home_or_away']
            } for _, row in filtered_df.iterrows()]
            
        except Exception as e:
            logging.error(f"Error getting team games: {e}")
            return []

    @staticmethod
    def get_live_game_ids(schedule_df: pd.DataFrame) -> List[str]:
        """获取当前正在进行的比赛ID列表（基于北京时间）"""
        try:
            beijing_now = datetime.now(TimeConverter.BEIJING_TZ)
            today_games = schedule_df[
                schedule_df['gameDateBJS'] == beijing_now.date()
            ]
            return today_games['gameId'].astype(str).tolist() if not today_games.empty else []
            
        except Exception as e:
            logging.error(f"Error getting live game IDs: {e}")
            return []

    @staticmethod
    def get_last_game_id(schedule_df: pd.DataFrame, team_id: int) -> Optional[str]:
        """
        获取球队过去最近一场比赛的ID（基于北京时间）
        
        Args:
            schedule_df: 赛程DataFrame
            team_id: 球队ID
            
        Returns:
            str or None: 最近一场比赛的ID，如果没有找到则返回None
        """
        try:
            # 获取当前北京时间
            beijing_now = datetime.now(TimeConverter.BEIJING_TZ)
            
            # 筛选球队的所有比赛
            team_games = ScheduleParser.filter_team_schedule(
                schedule_df=schedule_df,
                team_id=team_id,
                future_only=False
            )
            
            if team_games.empty:
                return None
                
            # 筛选过去的比赛并按时间排序
            past_games = team_games[
                team_games['gameDateTimeUTC'] < beijing_now.astimezone(TimeConverter.UTC_TZ)
            ].sort_values('gameDateTimeUTC')
            
            if not past_games.empty:
                return str(past_games.iloc[-1]['gameId'])
            return None
            
        except Exception as e:
            logging.error(f"Error getting last game ID: {e}")
            return None