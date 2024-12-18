import logging
from nba.models.game_model import Game

class DisplayService:
    """
    负责显示比赛相关信息的服务类
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def display_game_summary(self, game: Game):
        """
        显示比赛摘要信息

        Args:
            game (Game): 解析后的比赛数据
        """
        arena_name = game.info.arena.arena_name
        attendance = game.info.attendance
        sellout = "是" if game.info.sellout else "否"
        game_status = game.info.progress.game_status_text
        home_team = game.stats.home_team.team.team_name
        away_team = game.stats.away_team.team.team_name
        home_score = game.stats.home_team.statistics.points
        away_score = game.stats.away_team.statistics.points

        print(f"比赛场馆: {arena_name}")
        print(f"观众人数: {attendance}")
        print(f"是否售罄: {sellout}")
        print(f"比赛状态: {game_status}")
        print(f"{home_team} vs {away_team}")
        print(f"最终比分: {home_team} {home_score} - {away_team} {away_score}")

    def display_team_stats(self, game: Game):
        """
        显示球队统计数据

        Args:
            game (Game): 解析后的比赛数据
        """
        for team_side, team_stats in [('主队', game.stats.home_team), ('客队', game.stats.away_team)]:
            team_name = team_stats.team.team_name
            stats = team_stats.statistics
            print(f"\n{team_side}：{team_name}")
            print(f"得分: {stats.points}")
            print(f"助攻: {stats.assists}")
            print(f"篮板: {stats.rebounds_total}")
            print(f"抢断: {stats.steals}")
            print(f"盖帽: {stats.blocks}")
            print(f"失误: {stats.turnovers}")
            print(f"三分命中率: {stats.three_pointers_percentage:.2%}")
            print(f"罚球命中率: {stats.free_throws_percentage:.2%}")

    def display_player_stats(self, game: Game, team_side: str):
        """
        显示指定球队的球员统计数据

        Args:
            game (Game): 解析后的比赛数据
            team_side (str): 'home' 或 'away'，指定要显示哪个球队的球员
        """
        team_stats = game.stats.home_team if team_side == 'home' else game.stats.away_team
        team_name = team_stats.team.team_name
        print(f"\n{team_side.capitalize()}队球员统计：{team_name}")
        for player in team_stats.players:
            stats = player.statistics.statistics
            print(f"姓名: {player.first_name} {player.family_name}, 得分: {stats.get('points', 0)}, 助攻: {stats.get('assists', 0)}, 篮板: {stats.get('reboundsTotal', 0)}")
