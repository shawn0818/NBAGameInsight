from datetime import datetime
from typing import Union
from pytz import timezone
import logging
import re


class TimeParser:
    """基础的时间解析工具类，专门处理 ISO8601 格式"""

    @staticmethod
    def parse_iso8601_duration(duration_str: str) -> int:
        """
        解析 ISO 8601 格式的时长字符串为秒数

        Args:
            duration_str: ISO 8601格式的时长字符串 (如 "PT12M00.00S")

        Returns:
            int: 转换后的总秒数

        Examples:
            >>> TimeParser.parse_iso8601_duration("PT12M00.00S")
            720
        """
        pattern = r'^PT(\d+)M(\d+(\.\d+)?)S$'
        match = re.match(pattern, duration_str)

        if not match:
            raise ValueError(f"Invalid ISO 8601 duration format: {duration_str}")

        minutes = int(match.group(1))
        seconds = float(match.group(2))
        return int(minutes * 60 + round(seconds))

    @staticmethod
    def parse_iso8601_datetime(datetime_str: str) -> datetime:
        """
        解析 ISO 8601 格式的时间字符串为 datetime 对象

        Args:
            datetime_str: ISO 8601格式的时间字符串 (如 "2024-12-09T02:40:38Z")

        Returns:
            datetime: 解析后的 datetime 对象
        """
        return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))


class NBATimeHandler:
    """NBA时间处理工具类"""

    UTC_TZ = timezone('UTC')
    BEIJING_TZ = timezone('Asia/Shanghai')

    @classmethod
    def get_current_utc(cls) -> datetime:
        """获取当前UTC时间"""
        return datetime.now(cls.UTC_TZ)

    @classmethod
    def ensure_tz_datetime(cls, dt: Union[str, datetime], tz=None) -> datetime:
        """
        确保datetime对象带有时区信息

        Args:
            dt: 时间对象或字符串
            tz: 指定时区（如果时间对象没有时区信息）
        """
        if isinstance(dt, str):
            dt = TimeParser.parse_iso8601_datetime(dt)

        if not dt.tzinfo:
            tz = tz or cls.UTC_TZ
            dt = tz.localize(dt)

        return dt

    @classmethod
    def local_to_utc(cls, local_time: datetime, local_tz=BEIJING_TZ) -> datetime:
        """
        将本地时间转换为UTC时间

        Args:
            local_time: 本地时间
            local_tz: 本地时区（默认为北京时区）

        Returns:
            datetime: UTC时间
        """
        if not local_time.tzinfo:
            local_time = local_tz.localize(local_time)
        return local_time.astimezone(cls.UTC_TZ)

    @classmethod
    def utc_to_local(cls, utc_time: Union[str, datetime], target_tz=BEIJING_TZ) -> datetime:
        """
        将UTC时间转换为目标时区时间

        Args:
            utc_time: UTC时间，可以是ISO8601字符串或datetime对象
            target_tz: 目标时区（默认为北京时区）

        Returns:
            datetime: 目标时区的datetime对象
        """
        dt = cls.ensure_tz_datetime(utc_time, cls.UTC_TZ)
        return dt.astimezone(target_tz)

    @classmethod
    def get_utc_date(cls, date_str: str, local_tz=BEIJING_TZ) -> datetime:
        """
        将日期字符串转换为UTC时间

        Args:
            date_str: 日期字符串 (格式: YYYY-MM-DD)
            local_tz: 输入日期的时区（默认为北京时区）

        Returns:
            datetime: UTC时间的datetime对象
        """
        local_dt = datetime.strptime(date_str, '%Y-%m-%d')
        local_dt = local_tz.localize(local_dt)
        return local_dt.astimezone(cls.UTC_TZ)

    @classmethod
    def format_time(cls, dt: datetime, format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
        """格式化datetime对象为字符串"""
        return dt.strftime(format_str)

    @classmethod
    def is_current_or_future(cls, dt: Union[str, datetime], reference_tz=None) -> bool:
        """
        检查给定时间是否为当前或将来的时间

        Args:
            dt: UTC时间，可以是ISO8601字符串或datetime对象
            reference_tz: 参考时区（默认为 UTC）

        Returns:
            bool: 是否为当前或将来的时间
        """
        if not reference_tz:
            reference_tz = cls.UTC_TZ

        try:
            dt = cls.ensure_tz_datetime(dt, reference_tz)
            return dt >= datetime.now(reference_tz)

        except Exception as e:
            logging.error(f"Error checking time: {e}")
            return False


class BasketballGameTime:
    """篮球比赛时间处理工具类"""

    REGULAR_QUARTER_LENGTH = 12 * 60  # 常规节时长(秒)
    OVERTIME_LENGTH = 5 * 60  # 加时赛时长(秒)
    QUARTERS_IN_GAME = 4  # 常规比赛节数

    @classmethod
    def get_seconds_left(cls, period: int, time_str: str) -> int:
        """
        计算比赛剩余时间（秒）

        Args:
            period: 当前节数（1-4为常规时间，>4为加时赛）
            time_str: ISO8601格式的时长字符串（如 "PT12M00.00S"）

        Returns:
            int: 比赛剩余总时间（秒）
        """
        total_seconds = TimeParser.parse_iso8601_duration(time_str)

        if period <= cls.QUARTERS_IN_GAME:
            remaining_periods = cls.QUARTERS_IN_GAME - period
            total_seconds += remaining_periods * cls.REGULAR_QUARTER_LENGTH

        return total_seconds

    @classmethod
    def is_overtime(cls, period: int) -> bool:
        """判断是否为加时赛"""
        return period > cls.QUARTERS_IN_GAME

    @classmethod
    def get_period_name(cls, period: int) -> str:
        """获取节数的显示名称"""
        if period <= cls.QUARTERS_IN_GAME:
            return f"第{period}节"
        else:
            ot_number = period - cls.QUARTERS_IN_GAME
            return f"第{ot_number}个加时"