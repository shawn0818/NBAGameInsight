# base_models.py
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, BLOB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

# 创建基础模型类 - 用于nba.db
Base = declarative_base()


class Team(Base):
    """球队模型"""
    __tablename__ = 'teams'

    team_id = Column(Integer, primary_key=True)
    abbreviation = Column(String, nullable=False, index=True)
    nickname = Column(String, nullable=False, index=True)
    year_founded = Column(Integer)
    city = Column(String, index=True)
    arena = Column(String)
    arena_capacity = Column(String)
    owner = Column(String)
    general_manager = Column(String)
    head_coach = Column(String)
    dleague_affiliation = Column(String)
    team_slug = Column(String, index=True)
    logo = Column(BLOB)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    players = relationship("Player", back_populates="team")
    home_games = relationship("Game", foreign_keys="Game.home_team_id", back_populates="home_team")
    away_games = relationship("Game", foreign_keys="Game.away_team_id", back_populates="away_team")

    def __repr__(self):
        return f"<Team {self.city} {self.nickname} ({self.team_id})>"

    def full_name(self):
        """返回球队全名"""
        return f"{self.city} {self.nickname}"


class Player(Base):
    """球员模型"""
    __tablename__ = 'players'

    person_id = Column(Integer, primary_key=True)
    display_last_comma_first = Column(String)
    display_first_last = Column(String, nullable=False, index=True)
    roster_status = Column(Integer, index=True)
    from_year = Column(String)
    to_year = Column(String)
    player_slug = Column(String, index=True)
    team_id = Column(Integer, ForeignKey('teams.team_id'))
    games_played_flag = Column(String)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    team = relationship("Team", back_populates="players")

    def __repr__(self):
        return f"<Player {self.display_first_last} ({self.person_id})>"

    def full_name(self):
        """返回球员全名"""
        return self.display_first_last

    def short_name(self):
        """返回球员简称"""
        if not self.display_first_last:
            return ""

        parts = self.display_first_last.split()
        if len(parts) >= 2:
            return f"{parts[0][0]}. {parts[-1]}"
        return self.display_first_last


class Game(Base):
    """比赛模型"""
    __tablename__ = 'games'

    game_id = Column(String, primary_key=True)
    game_code = Column(String)
    game_status = Column(Integer, index=True)
    game_status_text = Column(String)
    game_date_est = Column(String)
    game_time_est = Column(String)
    game_date_time_est = Column(String)
    game_date_utc = Column(String)
    game_time_utc = Column(String)
    game_date_time_utc = Column(String, index=True)
    game_date = Column(String, index=True)
    season_year = Column(String, index=True)
    week_number = Column(Integer)
    week_name = Column(String)
    series_game_number = Column(String)
    if_necessary = Column(String)
    series_text = Column(String)
    arena_name = Column(String)
    arena_city = Column(String)
    arena_state = Column(String)
    arena_is_neutral = Column(Boolean)

    # 主队信息
    home_team_id = Column(Integer, ForeignKey('teams.team_id'), index=True)
    home_team_name = Column(String)
    home_team_city = Column(String)
    home_team_tricode = Column(String)
    home_team_slug = Column(String)
    home_team_wins = Column(Integer)
    home_team_losses = Column(Integer)
    home_team_score = Column(Integer)
    home_team_seed = Column(Integer)

    # 客队信息
    away_team_id = Column(Integer, ForeignKey('teams.team_id'), index=True)
    away_team_name = Column(String)
    away_team_city = Column(String)
    away_team_tricode = Column(String)
    away_team_slug = Column(String)
    away_team_wins = Column(Integer)
    away_team_losses = Column(Integer)
    away_team_score = Column(Integer)
    away_team_seed = Column(Integer)

    # 得分领先者
    points_leader_id = Column(Integer, ForeignKey('players.person_id'))
    points_leader_first_name = Column(String)
    points_leader_last_name = Column(String)
    points_leader_team_id = Column(Integer, ForeignKey('teams.team_id'))
    points_leader_points = Column(Float)

    # 其他信息
    game_type = Column(String, index=True)
    game_sub_type = Column(String)
    game_label = Column(String)
    game_sub_label = Column(String)
    postponed_status = Column(String)

    # 北京时间
    game_date_bjs = Column(String, index=True)
    game_time_bjs = Column(String)
    game_date_time_bjs = Column(String)

    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    home_team = relationship("Team", foreign_keys=[home_team_id], back_populates="home_games")
    away_team = relationship("Team", foreign_keys=[away_team_id], back_populates="away_games")
    points_leader = relationship("Player", foreign_keys=[points_leader_id])
    points_leader_team = relationship("Team", foreign_keys=[points_leader_team_id])

    def __repr__(self):
        return f"<Game {self.game_id} {self.home_team_name} vs {self.away_team_name}>"

    def is_finished(self):
        """检查比赛是否已结束"""
        return self.game_status == 3

    def is_ongoing(self):
        """检查比赛是否正在进行"""
        return self.game_status == 2

    def is_scheduled(self):
        """检查比赛是否已排期但未开始"""
        return self.game_status == 1