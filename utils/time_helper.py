from datetime import datetime, timedelta
from typing import Optional
from pytz import timezone

class TimeConverter:
    """时间转换工具类"""
    
    UTC_TZ = timezone('UTC')
    BEIJING_TZ = timezone('Asia/Shanghai')
    
    @classmethod
    def to_beijing_time(cls, utc_time) -> str:
        """
        将UTC时间转换为北京时间字符串
        
        Args:
            utc_time: UTC时间（可以是字符串或datetime对象）
            
        Returns:
            str: 北京时间字符串，格式：YYYY-MM-DD HH:MM:SS
        """
        try:
            if isinstance(utc_time, str):
                utc_dt = datetime.fromisoformat(utc_time.replace('Z', '+00:00'))
            else:
                utc_dt = utc_time
                
            if not utc_dt.tzinfo:
                utc_dt = cls.UTC_TZ.localize(utc_dt)
                
            beijing_dt = utc_dt.astimezone(cls.BEIJING_TZ)
            return beijing_dt.strftime('%Y-%m-%d %H:%M:%S')
            
        except Exception as e:
            logging.error(f"Error converting time to Beijing time: {e}")
            return str(utc_time)

    @staticmethod
    def parse_date(date_str: str, formats=None) -> Optional[datetime.date]:
        """
        解析日期字符串
        
        Args:
            date_str: 日期字符串
            formats: 可选的日期格式列表
            
        Returns:
            Optional[datetime.date]: 解析后的日期对象
        """
        if not formats:
            formats = ["%Y-%m-%d", "%m/%d/%Y"]
            
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None

    @classmethod
    def adjust_to_beijing_date(cls, dt: datetime) -> datetime.date:
        """
        调整日期以匹配北京时间（通常需要减去一天）
        """
        return (dt - timedelta(days=1)).date()

    @classmethod
    def is_current_or_future(cls, dt, reference_tz=None) -> bool:
        """
        检查时间是否是当前或将来的时间
        
        Args:
            dt: 要检查的时间
            reference_tz: 参考时区（默认为UTC）
            
        Returns:
            bool: 是否是当前或将来的时间
        """
        if not reference_tz:
            reference_tz = cls.UTC_TZ
            
        now = datetime.now(reference_tz)
        
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            
        if not dt.tzinfo:
            dt = reference_tz.localize(dt)
            
        return dt >= now