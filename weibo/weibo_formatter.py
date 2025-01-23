"""
微博内容格式化模块
负责将NBA比赛数据格式化为适合微博发布的文本格式
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from nba.models.game_model import Game, PlayerStatistics
from nba.models.team_model import TeamProfile

logger = logging.getLogger(__name__)

class WeiboFormatter:
    """微博内容格式化器"""

    def __init__(self):
        self.max_text_length = 140  # 微博文本长度限制
        self.logger = logging.getLogger(self.__class__.__name__)

    def format_game_summary(self, game_data: Dict[str, Any]) -> str:
        """
        格式化比赛概要数据
        
        Args:
            game_data: 比赛数据字典
            
        Returns:
            str: 格式化后的微博文本
        """
        try:
            if not game_data:
                return ""
                
            return (
                f"🏀 {game_data['teams']['home']['name']} "
                f"{game_data['teams']['home']['score']} - "
                f"{game_data['teams']['away']['score']} "
                f"{game_data['teams']['away']['name']}\n"
                f"📍 {game_data['basic_info']['arena']['name']}\n"
                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"#NBA#{game_data['teams']['home']['name']}#{game_data['teams']['away']['name']}#"
            )
            
        except Exception as e:
            self.logger.error(f"格式化比赛概要时出错: {e}")
            return "格式化比赛数据失败"

    def format_player_stats(
        self, 
        player_stats: Dict[str, Any],
        player_name: str
    ) -> str:
        """
        格式化球员统计数据
        
        Args:
            player_stats: 球员统计数据字典
            player_name: 球员名称
            
        Returns:
            str: 格式化后的微博文本
        """
        try:
            if not player_stats:
                return ""
                
            basic = player_stats['basic']
            shooting = player_stats['shooting']
            
            return (
                f"📊 {player_name} 数据统计\n"
                f"⏱️ 上场时间: {basic['minutes']}\n"
                f"得分: {basic['points']} 篮板: {basic['rebounds']} "
                f"助攻: {basic['assists']}\n"
                f"投篮: {shooting['field_goals']['made']}/{shooting['field_goals']['attempted']} "
                f"三分: {shooting['three_pointers']['made']}/{shooting['three_pointers']['attempted']}\n"
                f"#{player_name}#"
            )
            
        except Exception as e:
            self.logger.error(f"格式化球员统计时出错: {e}")
            return "格式化球员数据失败"

    def format_team_stats(
        self,
        team_stats: Dict[str, Any],
        team_name: str
    ) -> str:
        """
        格式化球队统计数据
        
        Args:
            team_stats: 球队统计数据字典
            team_name: 球队名称
            
        Returns:
            str: 格式化后的微博文本
        """
        try:
            if not team_stats:
                return ""
                
            return (
                f"📊 {team_name} 球队数据\n"
                f"得分: {team_stats['basic']['points']}\n"
                f"篮板: {team_stats['other']['rebounds']}\n"
                f"助攻: {team_stats['other']['assists']}\n"
                f"投篮: {team_stats['shooting']['field_goals']['percentage']}\n"
                f"三分: {team_stats['shooting']['three_pointers']['percentage']}\n"
                f"#{team_name}#"
            )
            
        except Exception as e:
            self.logger.error(f"格式化球队统计时出错: {e}")
            return "格式化球队数据失败"

    def format_game_raw(self, game: Game) -> str:
        """
        格式化原始比赛数据对象
        
        Args:
            game (Game): 比赛数据对象
            
        Returns:
            str: 格式化后的微博文本
        """
        try:
            home_team = game.game.homeTeam
            away_team = game.game.awayTeam
            
            # 获取球队完整信息
            home_profile = TeamProfile.from_id(home_team.teamId)
            away_profile = TeamProfile.from_id(away_team.teamId)
            
            # 构建比赛状态文本
            status_text = "比赛结束" if game.game.gameStatus == 3 else "进行中"
            
            # 构建比分文本
            score_text = (
                f"{away_team.teamCity} {away_team.teamName} "
                f"{away_team.score} - {home_team.score} "
                f"{home_team.teamCity} {home_team.teamName}"
            )
            
            # 添加球队标签
            team_tags = f"#{away_team.teamName}# #{home_team.teamName}# #NBA#"
            
            # 组合完整文本
            text = f"🏀 {status_text}\n{score_text}\n{team_tags}"
            
            return self.truncate_text(text)
            
        except Exception as e:
            self.logger.error(f"格式化原始比赛数据时出错: {e}")
            return "格式化比赛数据失败"

    def truncate_text(self, text: str) -> str:
        """
        截断文本到微博字数限制
        
        Args:
            text (str): 原始文本
            
        Returns:
            str: 截断后的文本
        """
        if len(text) <= self.max_text_length:
            return text
        return text[:self.max_text_length-3] + "..."
