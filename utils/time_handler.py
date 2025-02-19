from datetime import datetime
from typing import Union
from pytz import timezone
import re


class TimeHandler:
    """NBA时间处理工具类"""

    # 1. 基础常量定义
    # 时区定义
    UTC_TZ = timezone('UTC')
    BEIJING_TZ = timezone('Asia/Shanghai')

    # 比赛时间常量
    REGULAR_QUARTER_LENGTH = 12 * 60  # 常规节时长(秒)
    OVERTIME_LENGTH = 5 * 60  # 加时赛时长(秒)
    QUARTERS_IN_GAME = 4  # 常规比赛节数

    # 2. 基础时间解析方法
    @classmethod
    def parse_duration(cls, duration_str: str) -> int:
        """
        解析ISO 8601时长字符串为秒数
        例如: "PT12M00.00S" -> 720秒; "PT06M30.00S" -> 390秒

        Args:
            duration_str: ISO 8601格式的时长字符串

        Returns:
            int: 转换后的总秒数
        """
        pattern = r'^PT(\d+)M(\d+(\.\d+)?)S$'
        match = re.match(pattern, duration_str)

        if not match:
            raise ValueError(f"Invalid duration format: {duration_str}")

        minutes = int(match.group(1))
        seconds = float(match.group(2))
        return int(minutes * 60 + round(seconds))

    @classmethod
    def parse_datetime(cls, datetime_str: str) -> datetime:
        """
        解析ISO 8601格式的UTC时间字符串为datetime对象

        Args:
            datetime_str: ISO 8601格式的时间字符串

        Returns:
            datetime: 解析后的datetime对象
        """
        return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))

    # 3. 时区转换相关方法
    @classmethod
    def ensure_utc(cls, dt: Union[str, datetime]) -> datetime:
        """
        确保时间为UTC时间

        Args:
            dt: 字符串或datetime对象

        Returns:
            datetime: UTC时间
        """
        if isinstance(dt, str):
            dt = cls.parse_datetime(dt)

        if not dt.tzinfo:
            dt = cls.UTC_TZ.localize(dt)
        return dt.astimezone(cls.UTC_TZ)

    @classmethod
    def to_beijing(cls, dt: Union[str, datetime]) -> datetime:
        """
        转换为北京时间

        Args:
            dt: UTC时间（字符串或datetime）

        Returns:
            datetime: 北京时间
        """
        utc_time = cls.ensure_utc(dt)
        return utc_time.astimezone(cls.BEIJING_TZ)

    # 4. 时间格式化方法
    @classmethod
    def format_time(cls, dt: datetime, to_beijing: bool = True, format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
        """
        格式化时间

        Args:
            dt: datetime对象
            to_beijing: 是否转换为北京时间
            format_str: 格式化字符串

        Returns:
            str: 格式化后的时间字符串
        """
        if to_beijing:
            dt = cls.to_beijing(dt)
        return dt.strftime(format_str)

    # 5. 比赛时间处理方法
    @classmethod
    def get_minutes_played(cls, duration_str: str) -> float:
        """
        获取比赛时间（分钟）

        Args:
            duration_str: ISO 8601时长字符串

        Returns:
            float: 比赛时间（分钟）
        """
        seconds = cls.parse_duration(duration_str)
        return round(seconds / 60.0, 2)

    @classmethod
    def get_game_time_status(cls, period: int, time_str: str) -> dict:
        """
        获取比赛时间状态信息

        Args:
            period: 当前节数
            time_str: 比赛时钟时间 (如 "PT06M30.00S")

        Returns:
            dict: 返回比赛时间相关信息，包括：
                - total_seconds_left: 剩余总秒数
                - current_period_seconds: 当前节剩余秒数
                - is_overtime: 是否加时赛
                - period_name: 节次名称
                - period: 当前节次
        """
        seconds = cls.parse_duration(time_str)
        is_overtime = period > cls.QUARTERS_IN_GAME

        if period <= cls.QUARTERS_IN_GAME:
            remaining_periods = cls.QUARTERS_IN_GAME - period
            total_seconds = seconds + remaining_periods * cls.REGULAR_QUARTER_LENGTH
        else:
            total_seconds = seconds

        period_name = f"第{period}节" if period <= cls.QUARTERS_IN_GAME else f"第{period - cls.QUARTERS_IN_GAME}个加时"

        return {
            'total_seconds_left': total_seconds,
            'current_period_seconds': seconds,
            'is_overtime': is_overtime,
            'period_name': period_name,
            'period': period
        }

    @classmethod
    def is_future_game(cls, game_time: Union[str, datetime]) -> bool:
        """
        判断是否为未来的比赛（基于UTC时间判断）

        Args:
            game_time: 比赛时间（字符串或datetime）

        Returns:
            bool: 是否为未来的比赛
        """
        game_dt = cls.ensure_utc(game_time)
        current_dt = datetime.now(cls.UTC_TZ)
        return game_dt > current_dt