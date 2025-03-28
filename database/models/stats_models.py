# stats_models.py
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

# 创建基础模型类 - 用于game.db
Base = declarative_base()


class Statistics(Base):
    """球员比赛统计数据模型"""
    __tablename__ = 'statistics'

    # 主键
    game_id = Column(String, primary_key=True, index=True)
    person_id = Column(Integer, primary_key=True)
    team_id = Column(Integer, index=True)

    # 比赛基本信息字段
    home_team_id = Column(Integer, index=True)
    away_team_id = Column(Integer, index=True)
    home_team_tricode = Column(String)
    away_team_tricode = Column(String)
    home_team_name = Column(String)
    home_team_city = Column(String)
    away_team_name = Column(String)
    away_team_city = Column(String)
    game_status = Column(Integer, index=True)
    home_team_score = Column(Integer)
    away_team_score = Column(Integer)
    game_time = Column(String)
    game_date = Column(String, index=True)
    period = Column(Integer)
    video_available = Column(Integer, default=0)

    # 球员个人信息
    first_name = Column(String)
    family_name = Column(String)
    name_i = Column(String)
    player_slug = Column(String)
    position = Column(String, index=True)
    jersey_num = Column(String)
    comment = Column(String)
    is_starter = Column(Integer, default=0)

    # 球员统计数据
    minutes = Column(String)
    field_goals_made = Column(Integer, default=0)
    field_goals_attempted = Column(Integer, default=0)
    field_goals_percentage = Column(Float, default=0)
    three_pointers_made = Column(Integer, default=0)
    three_pointers_attempted = Column(Integer, default=0)
    three_pointers_percentage = Column(Float, default=0)
    free_throws_made = Column(Integer, default=0)
    free_throws_attempted = Column(Integer, default=0)
    free_throws_percentage = Column(Float, default=0)
    rebounds_offensive = Column(Integer, default=0)
    rebounds_defensive = Column(Integer, default=0)
    rebounds_total = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    steals = Column(Integer, default=0)
    blocks = Column(Integer, default=0)
    turnovers = Column(Integer, default=0)
    fouls_personal = Column(Integer, default=0)
    points = Column(Integer, default=0, index=True)
    plus_minus_points = Column(Float, default=0)

    # 元数据
    last_updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 索引
    __table_args__ = (
        Index('idx_statistics_name', 'first_name', 'family_name'),
    )

    def __repr__(self):
        return f"<Statistics {self.game_id} {self.person_id} {self.points}pts>"


class Event(Base):
    """比赛回合动作数据模型"""
    __tablename__ = 'events'

    # 主键
    game_id = Column(String, primary_key=True, index=True)
    action_number = Column(Integer, primary_key=True)

    # 回合动作信息
    clock = Column(String)
    period = Column(Integer, index=True)
    team_id = Column(Integer, index=True)
    team_tricode = Column(String)
    person_id = Column(Integer, index=True)
    player_name = Column(String)
    player_name_i = Column(String)
    x_legacy = Column(Integer)
    y_legacy = Column(Integer)
    shot_distance = Column(Integer)
    shot_result = Column(String, index=True)
    is_field_goal = Column(Integer, default=0)
    score_home = Column(String)
    score_away = Column(String)
    points_total = Column(Integer, default=0)
    location = Column(String)
    description = Column(Text)
    action_type = Column(String, index=True)
    sub_type = Column(String)
    video_available = Column(Integer, default=0)
    shot_value = Column(Integer, default=0)
    action_id = Column(Integer)

    # 元数据
    last_updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<Event {self.game_id} #{self.action_number} {self.action_type}>"


class GameStatsSyncHistory(Base):
    """比赛统计数据同步历史记录"""
    __tablename__ = 'game_stats_sync_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_type = Column(String, nullable=False)
    game_id = Column(String, index=True)
    status = Column(String, nullable=False)
    items_processed = Column(Integer)
    items_succeeded = Column(Integer)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    details = Column(Text)
    error_message = Column(Text)

    def __repr__(self):
        return f"<SyncHistory {self.id} {self.sync_type} {self.status}>"