"""
NBA 统一服务接口
整合了数据获取、统计展示和视频处理等功能

使用示例:

1. 基础初始化和数据获取
```python
from pathlib import Path
from nba.services.nba_unified_service import NBAService

# 初始化服务
nba_service = NBAService(
    default_team="Lakers",           # 设置默认球队
    default_player="LeBron James",   # 设置默认球员
    date_str="today",               # 设置默认日期
    cache_dir=Path("./cache"),      # 设置缓存目录
    video_output_dir=Path("./videos") # 设置视频输出目录
)

# 获取比赛概要信息
game_summary = nba_service.get_game_summary()
print(f"比赛: {game_summary.home_team} vs {game_summary.away_team}")
print(f"比分: {game_summary.home_score} - {game_summary.away_score}")

# 获取球员概要信息
player_summary = nba_service.get_player_summary()
print(f"{player_summary.name} 数据:")
print(f"得分: {player_summary.points}")
print(f"篮板: {player_summary.rebounds}")
print(f"助攻: {player_summary.assists}")
```

2. 获取并显示详细统计
```python
# 获取完整统计数据
stats = nba_service.get_detailed_stats(
    team="Warriors",
    player="Stephen Curry",
    date="2024-01-02"
)

# 显示比赛信息
nba_service.display_game_info()

# 显示球员统计
nba_service.display_player_stats()

# 显示球队统计
nba_service.display_team_stats()

# 一次性显示所有统计
nba_service.display_all()
```

3. 视频相关功能
```python
# 获取投篮命中视频
videos = nba_service.get_game_videos(
    player="Luka Doncic",
    action_type="FGM"  # 投篮命中视频
)

# 下载视频并转换为GIF
results = nba_service.download_videos(
    videos=videos,
    output_dir=Path("./highlights"),
    quality="hd",
    to_gif=True
)

# 使用便捷方法一步完成获取和下载
highlights = nba_service.get_and_download_videos(
    team="Celtics",
    player="Jayson Tatum",
    date="2024-01-02",
    action_type="FG3M",  # 三分命中视频
    to_gif=True
)
```

4. 高级用法
```python
# 自定义比赛回放分析
game = nba_service.get_game_summary(team="Bucks")
if game.status == "已结束":
    # 获取关键球员数据
    giannis_stats = nba_service.get_player_summary(player="Giannis Antetokounmpo")

    # 获取并下载精彩镜头
    highlights = nba_service.get_and_download_videos(
        player=giannis_stats.name,
        action_type="FGM",
        output_dir=Path(f"./highlights/{game.game_id}")
    )

    # 显示完整统计
    nba_service.display_all()

# 批量处理多个球员
players = ["Kevin Durant", "Devin Booker", "Bradley Beal"]
for player in players:
    stats = nba_service.get_player_summary(player=player)
    if stats and stats.points >= 30:  # 筛选得分超过30分的表现
        nba_service.get_and_download_videos(
            player=player,
            action_type="FGM",
            output_dir=Path(f"./highlights/{player.replace(' ', '_')}")
        )
```

各种功能说明:

1. 数据获取:
   - get_game_summary: 获取比赛概要信息
   - get_player_summary: 获取球员概要信息
   - get_detailed_stats: 获取详细统计数据

2. 数据显示:
   - display_game_info: 显示比赛基本信息
   - display_player_stats: 显示球员统计数据
   - display_team_stats: 显示球队统计数据
   - display_scoring_plays: 显示得分事件
   - display_all: 显示所有信息

3. 视频功能:
   - get_game_videos: 获取比赛视频
   - download_videos: 下载视频
   - get_and_download_videos: 获取并下载视频

4. 支持的动作类型:
   - FGM: 投篮命中
   - FGA: 投篮出手
   - FG3M: 三分命中
   - FG3A: 三分出手
   - AST: 助攻
   - BLK: 盖帽
   - STL: 抢断
"""
from dataclasses import dataclass
from pathlib import Path
import logging
from typing import Optional, Dict, Any, List, Tuple


from nba.models.video_model import VideoAsset, ContextMeasure
from nba.services.game_data_service import NBAGameDataProvider
from nba.services.game_video_service  import GameVideoService
from config.nba_config import NBAConfig
from nba.models.game_model import Game, PlayerStatistics

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ANSI颜色代码
COLORS = {
    'green': '\033[92m',
    'red': '\033[91m',
    'blue': '\033[94m',
    'yellow': '\033[93m',
    'reset': '\033[0m'
}


@dataclass
class GameSummary:
    """比赛概要信息"""
    game_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    status: str
    arena: str
    date: str


@dataclass
class PlayerSummary:
    """球员概要信息"""
    player_id: int
    name: str
    team: str
    points: int
    rebounds: int
    assists: int
    minutes: str


class NBAService:
    """
    NBA统一服务接口
    提供数据获取、统计展示和视频处理的完整功能
    """

    def __init__(
            self,
            default_team: Optional[str] = None,
            default_player: Optional[str] = None,
            date_str: str = "today",
            cache_dir: Optional[Path] = None,
            cache_size: int = 128,
            video_output_dir: Optional[Path] = None
    ):
        """
        初始化NBA服务

        Args:
            default_team: 默认球队
            default_player: 默认球员
            date_str: 默认日期
            cache_dir: 缓存目录
            cache_size: 缓存大小
            video_output_dir: 视频输出目录
        """
        self.logger = logger.getChild(self.__class__.__name__)

        # 初始化数据服务
        self._data_provider = NBAGameDataProvider(
            default_team=default_team,
            default_player=default_player,
            date_str=date_str,
            cache_dir=cache_dir,
            cache_size=cache_size
        )

        # 初始化视频服务
        self._video_service = GameVideoService()
        self._video_output_dir = video_output_dir or NBAConfig.PATHS.VIDEO_DIR

        # 存储默认值
        self.default_team = default_team
        self.default_player = default_player
        self.default_date = date_str

    def _format_percentage(self, value: float) -> str:
        """格式化百分比"""
        return f"{value:.1%}" if value is not None else "0.0%"

    def _format_time(self, time_str: str) -> str:
        """格式化时间字符串"""
        time_str = time_str.replace('PT', '').replace('M', ':').replace('S', '')
        return time_str[:-3] if time_str.endswith('.00') else time_str

    def get_game_summary(
            self,
            team: Optional[str] = None,
            date: Optional[str] = None
    ) -> Optional[GameSummary]:
        """
        获取比赛概要信息

        Args:
            team: 球队名称
            date: 日期字符串

        Returns:
            Optional[GameSummary]: 比赛概要信息
        """
        try:
            game = self._data_provider.get_game(team, date)
            if not game:
                return None

            return GameSummary(
                game_id=game.gameId,
                home_team=f"{game.game.homeTeam.teamCity} {game.game.homeTeam.teamName}",
                away_team=f"{game.game.awayTeam.teamCity} {game.game.awayTeam.teamName}",
                home_score=game.game.homeTeam.score,
                away_score=game.game.awayTeam.score,
                status=self._get_game_status(game.game.gameStatus),
                arena=game.game.arena.arenaName,
                date=game.gameCode
            )
        except Exception as e:
            self.logger.error(f"获取比赛概要时出错: {e}")
            return None

    def _get_game_status(self, status_code: int) -> str:
        """获取比赛状态描述"""
        status_map = {
            1: "未开始",
            2: "进行中",
            3: "已结束"
        }
        return status_map.get(status_code, "未知状态")

    def get_player_summary(
            self,
            player: Optional[str] = None,
            team: Optional[str] = None,
            date: Optional[str] = None
    ) -> Optional[PlayerSummary]:
        """
        获取球员概要信息

        Args:
            player: 球员名称
            team: 球队名称
            date: 日期字符串

        Returns:
            Optional[PlayerSummary]: 球员概要信息
        """
        try:
            stats = self._data_provider.get_player_stats(player, team, date)
            if not stats:
                return None

            game = self._data_provider.get_game(team, date)
            if not game:
                return None

            player_id = self._data_provider.get_player_id(player)
            player_team = None
            for team_obj in [game.game.homeTeam, game.game.awayTeam]:
                if any(p.personId == player_id for p in team_obj.players):
                    player_team = f"{team_obj.teamCity} {team_obj.teamName}"
                    break

            return PlayerSummary(
                player_id=player_id,
                name=player or self._data_provider.default_player,
                team=player_team,
                points=stats.points,
                rebounds=stats.rebounds,
                assists=stats.assists,
                minutes=self._format_time(stats.minutes)
            )
        except Exception as e:
            self.logger.error(f"获取球员概要时出错: {e}")
            return None

    def get_detailed_stats(
            self,
            team: Optional[str] = None,
            player: Optional[str] = None,
            date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取详细统计数据

        Args:
            team: 球队名称
            player: 球员名称
            date: 日期字符串

        Returns:
            Dict[str, Any]: 详细统计数据
        """
        try:
            result = {
                'game': None,
                'player': None,
                'team': None,
                'scoring': None
            }

            # 获取比赛数据
            game = self._data_provider.get_game(team, date)
            if game:
                result['game'] = self._get_game_details(game)

            # 获取球员统计
            if player or self.default_player:
                stats = self._data_provider.get_player_stats(player, team, date)
                if stats:
                    result['player'] = self._get_player_details(stats)

            # 获取球队统计
            if game:
                team_stats = self._get_team_details(game, team)
                if team_stats:
                    result['team'] = team_stats

            # 获取得分事件
            scoring = self._data_provider.get_scoring_plays(team, player, date)
            if scoring:
                result['scoring'] = self._process_scoring_plays(scoring)

            return result

        except Exception as e:
            self.logger.error(f"获取详细统计时出错: {e}")
            return {}

    def get_game_videos(
            self,
            game_id: Optional[str] = None,
            team: Optional[str] = None,
            player: Optional[str] = None,
            date: Optional[str] = None,
            action_type: str = "FGM"
    ) -> Dict[str, VideoAsset]:
        """
        获取比赛视频

        Args:
            game_id: 比赛ID（如果不提供则通过team和date获取）
            team: 球队名称
            player: 球员名称
            date: 日期字符串
            action_type: 动作类型（如FGM, FG3M, AST等）

        Returns:
            Dict[str, VideoAsset]: 视频资产字典
        """
        try:
            # 如果没有提供game_id，则通过team和date获取
            if not game_id:
                game = self._data_provider.get_game(team, date)
                if not game:
                    return {}
                game_id = game.gameId

            # 获取球员ID（如果需要）
            player_id = None
            if player:
                player_id = self._data_provider.get_player_id(player, team, date)

            # 转换动作类型
            try:
                context_measure = ContextMeasure[action_type]
            except KeyError:
                context_measure = ContextMeasure.FGM
                self.logger.warning(f"未知的动作类型 {action_type}，使用默认值 FGM")

            # 获取视频
            return self._video_service.get_game_videos(
                game_id=game_id,
                context_measure=context_measure,
                player_id=player_id
            )
        except Exception as e:
            self.logger.error(f"获取视频时出错: {e}")
            return {}

    def download_videos(
            self,
            videos: Dict[str, VideoAsset],
            output_dir: Optional[Path] = None,
            quality: str = "hd",
            to_gif: bool = False,
            compress: bool = False
    ) -> Dict[str, Path]:
        """
        下载视频

        Args:
            videos: 视频资产字典
            output_dir: 输出目录
            quality: 视频质量 ('sd' 或 'hd')
            to_gif: 是否转换为GIF
            compress: 是否压缩视频

        Returns:
            Dict[str, Path]: 下载文件的路径字典
        """
        try:
            final_output_dir = output_dir or self._video_output_dir
            return self._video_service.batch_download(
                videos=videos,
                output_dir=final_output_dir,
                quality=quality,
                to_gif=to_gif,
                compress=compress
            )
        except Exception as e:
            self.logger.error(f"下载视频时出错: {e}")
            return {}

    def get_and_download_videos(
            self,
            team: Optional[str] = None,
            player: Optional[str] = None,
            date: Optional[str] = None,
            action_type: str = "FGM",
            output_dir: Optional[Path] = None,
            quality: str = "hd",
            to_gif: bool = False
    ) -> Dict[str, Path]:
        """
        获取并下载视频的便捷方法

        Args:
            team: 球队名称
            player: 球员名称
            date: 日期字符串
            action_type: 动作类型
            output_dir: 输出目录
            quality: 视频质量
            to_gif: 是否转换为GIF

        Returns:
            Dict[str, Path]: 下载文件的路径字典
        """
        videos = self.get_game_videos(
            team=team,
            player=player,
            date=date,
            action_type=action_type
        )

        if not videos:
            return {}

        return self.download_videos(
            videos=videos,
            output_dir=output_dir,
            quality=quality,
            to_gif=to_gif
        )

    # ... [前面显示相关的方法保持不变] ...

    def _get_game_details(self, game: Game) -> Dict[str, Any]:
        """处理比赛详细数据"""
        return {
            'basic_info': {
                'game_id': game.gameId,
                'status': self._get_game_status(game.game.gameStatus),
                'arena': {
                    'name': game.game.arena.arenaName,
                    'city': game.game.arena.arenaCity,
                    'state': game.game.arena.arenaState,
                    'country': game.game.arena.arenaCountry
                }
            },
            'teams': {
                'home': {
                    'name': f"{game.game.homeTeam.teamCity} {game.game.homeTeam.teamName}",
                    'score': game.game.homeTeam.score,
                    'timeouts': game.game.homeTeam.timeoutsRemaining,
                    'bonus': game.game.homeTeam.inBonus == '1'
                },
                'away': {
                    'name': f"{game.game.awayTeam.teamCity} {game.game.awayTeam.teamName}",
                    'score': game.game.awayTeam.score,
                    'timeouts': game.game.awayTeam.timeoutsRemaining,
                    'bonus': game.game.awayTeam.inBonus == '1'
                }
            },
            'periods': self._process_period_scores(game),
            'officials': [
                {
                    'name': off.name,
                    'number': off.jerseyNum,
                    'assignment': off.assignment
                }
                for off in game.game.officials
            ]
        }

    def _get_player_details(self, stats: PlayerStatistics) -> Dict[str, Any]:
        """处理球员详细统计"""
        return {
            'basic': {
                'minutes': self._format_time(stats.minutes),
                'points': stats.points,
                'rebounds': stats.rebounds,
                'assists': stats.assists,
                'steals': stats.steals,
                'blocks': stats.blocks
            },
            'shooting': {
                'field_goals': {
                    'made': stats.fieldGoalsMade,
                    'attempted': stats.fieldGoalsAttempted,
                    'percentage': self._format_percentage(stats.fieldGoalsPercentage)
                },
                'three_pointers': {
                    'made': stats.threePointersMade,
                    'attempted': stats.threePointersAttempted,
                    'percentage': self._format_percentage(stats.threePointersPercentage)
                },
                'free_throws': {
                    'made': stats.freeThrowsMade,
                    'attempted': stats.freeThrowsAttempted,
                    'percentage': self._format_percentage(stats.freeThrowsPercentage)
                }
            },
            'advanced': {
                'true_shooting': self._format_percentage(stats.trueShootingPercentage),
                'effective_fg': self._format_percentage(stats.effectiveFieldGoalPercentage),
                'usage': self._format_percentage(stats.usagePercentage),
                'assist_percentage': self._format_percentage(stats.assistPercentage),
                'rebound_percentage': self._format_percentage(stats.reboundPercentage)
            }
        }

    def _get_team_details(self, game: Game, team: Optional[str] = None) -> Dict[str, Any]:
        """处理球队详细统计"""
        team_id = self._data_provider._get_team_id(team or self.default_team)
        is_home = game.game.homeTeam.teamId == team_id
        team_obj = game.game.homeTeam if is_home else game.game.awayTeam

        return {
            'basic': {
                'points': team_obj.score,
                'paint_points': team_obj.get_stat('pointsInThePaint', 0),
                'fast_break_points': team_obj.get_stat('pointsFastBreak', 0),
                'second_chance_points': team_obj.get_stat('pointsSecondChance', 0),
                'largest_lead': team_obj.get_stat('leadLargest', 0)
            },
            'shooting': {
                'field_goals': self._get_shooting_stats(team_obj.field_goals),
                'three_pointers': self._get_shooting_stats(team_obj.three_pointers),
                'free_throws': self._get_shooting_stats(team_obj.free_throws)
            },
            'other': {
                'assists': team_obj.get_stat('assists', 0),
                'rebounds': team_obj.get_stat('reboundsTotal', 0),
                'steals': team_obj.get_stat('steals', 0),
                'blocks': team_obj.get_stat('blocks', 0),
                'turnovers': team_obj.get_stat('turnovers', 0),
                'fouls': team_obj.get_stat('foulsPersonal', 0),
                'timeouts': team_obj.timeoutsRemaining
            }
        }

    def _get_shooting_stats(self, stats: Tuple[int, int, float]) -> Dict[str, Any]:
        """处理投篮统计数据"""
        made, attempted, percentage = stats
        return {
            'made': made,
            'attempted': attempted,
            'percentage': self._format_percentage(percentage if attempted > 0 else 0)
        }

    def _process_period_scores(self, game: Game) -> List[Dict[str, Any]]:
        """处理每节比分"""
        periods = []
        home_team = game.game.homeTeam
        away_team = game.game.awayTeam

        for p in home_team.periods:
            away_period = next(ap for ap in away_team.periods if ap.period == p.period)
            periods.append({
                'period': p.period,
                'period_type': "加时" if p.period > 4 else f"第{p.period}节",
                'home_score': p.score,
                'away_score': away_period.score
            })

        return periods

    def _process_scoring_plays(self, plays: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理得分事件"""
        return [
            {
                'period': play['period'],
                'time': play['time'],
                'score': play.get('score', ''),
                'team': play['team'],
                'description': play['description'],
                'points': play.get('points', 0),
                'is_clutch': self._is_clutch_play(play)
            }
            for play in plays
        ]

    def _is_clutch_play(self, play: Dict[str, Any]) -> bool:
        """判断是否为关键时刻得分"""
        return (play['period'] >= 4 and
                play['time'] <= "5:00" and
                abs(play.get('score_diff', 0)) <= 5)

    def display_all(
            self,
            team: Optional[str] = None,
            player: Optional[str] = None,
            date: Optional[str] = None
    ) -> None:
        """显示所有统计信息"""
        self.display_game_info(team, date)
        if player or self.default_player:
            self.display_player_stats(player, team, date)
        self.display_team_stats(team, date)
        self.display_scoring_plays(team, player, date)

    def display_game_info(
            self,
            team: Optional[str] = None,
            date: Optional[str] = None
    ) -> None:
        """显示比赛信息"""
        try:
            game = self._data_provider.get_game(team, date)
            if not game:
                self.logger.error("未找到比赛数据")
                return

            print(f"\n{COLORS['yellow']}=== 比赛基本信息 ==={COLORS['reset']}")
            status_map = {
                1: "未开始",
                2: f"{COLORS['green']}进行中{COLORS['reset']}",
                3: "已结束"
            }
            print(f"状态: {status_map.get(game.game.gameStatus, '未知')}")
            
            # 2. 场馆信息
            arena = game.game.arena
            print(f"\n{COLORS['blue']}场馆信息:{COLORS['reset']}")
            print(f"场馆: {arena.arenaName}")
            print(f"地点: {arena.arenaCity}, {arena.arenaState}, {arena.arenaCountry}")
            print(f"时区: {arena.arenaTimezone}")

            # 3. 球队信息
            print(f"\n{COLORS['blue']}球队信息:{COLORS['reset']}")
            home_team = game.game.homeTeam
            away_team = game.game.awayTeam
            
            print("主队:")
            print(f"  {home_team.teamCity} {home_team.teamName} ({home_team.teamTricode})")
            print(f"  暂停剩余: {home_team.timeoutsRemaining}")
            print(f"  罚球次数: {'在罚球线内' if home_team.inBonus == '1' else '未在罚球线内'}")
            
            print("客队:")
            print(f"  {away_team.teamCity} {away_team.teamName} ({away_team.teamTricode})")
            print(f"  暂停剩余: {away_team.timeoutsRemaining}")
            print(f"  罚球次数: {'在罚球线内' if away_team.inBonus == '1' else '未在罚球线内'}")

            # 4. 比分信息
            print(f"\n{COLORS['blue']}比分信息:{COLORS['reset']}")
            print(f"当前比分: {home_team.score} - {away_team.score}")

            # 5. 每节比分
            print("\n每节比分详情:")
            headers = []
            home_scores = []
            away_scores = []
            
            for p in home_team.periods:
                period_type = "加时" if p.period > 4 else f"第{p.period}节"
                headers.append(period_type.rjust(6))
                home_scores.append(str(p.score).rjust(6))
                away_scores.append(str(next(ap.score for ap in away_team.periods if ap.period == p.period)).rjust(6))

            print("      " + " ".join(headers))
            print(f"主队: {' '.join(home_scores)}")
            print(f"客队: {' '.join(away_scores)}")

            # 6. 裁判信息
            print(f"\n{COLORS['blue']}裁判信息:{COLORS['reset']}")
            for official in game.game.officials:
                print(f"{official.assignment}: {official.name} (#{official.jerseyNum})")

            # 7. 首发阵容
            print(f"\n{COLORS['blue']}首发阵容:{COLORS['reset']}")
            print("主队首发:")
            for player in home_team.players:
                if player.starter == "1":
                    print(f"  #{player.jerseyNum} {player.name} ({player.position})")
            
            print("\n客队首发:")
            for player in away_team.players:
                if player.starter == "1":
                    print(f"  #{player.jerseyNum} {player.name} ({player.position})")

        except Exception as e:
            self.logger.error(f"显示比赛信息时出错: {e}")
            if self.logger.level == logging.DEBUG:
                self.logger.debug("错误详情:", exc_info=True)

    def display_player_stats(
            self,
            player: Optional[str] = None,
            team: Optional[str] = None,
            date: Optional[str] = None
    ) -> None:
        """显示球员统计"""
        try:
            player_id = self._data_provider.get_player_id()
            if not player_id:
                return

            game = self._data_provider.get_game()
            if not game:
                return

            stats = game.get_player_stats(player_id)
            if not stats:
                self.logger.error(f"未找到球员 {self._data_provider.default_player} 的统计数据")
                return

            print(f"\n{COLORS['yellow']}=== {self._data_provider.default_player} 的统计数据 ==={COLORS['reset']}")

            # 基础数据
            print(f"上场时间: {stats.minutes}分钟")
            print(f"  得分: {stats.points}")
            print(f"  篮板: {stats.reboundsTotal}")
            print(f"  助攻: {stats.assists}")
            print(f"  抢断: {stats.steals}")
            print(f"  盖帽: {stats.blocks}")

            # 得分细节
            print(f"\n{COLORS['blue']}得分细节:{COLORS['reset']}")
            print(f"总得分: {stats.points}")
            print(f"油漆区得分: {stats.pointsInThePaint}")
            print(f"二次进攻得分: {stats.pointsSecondChance}")
            print(f"快攻得分: {stats.pointsFastBreak}")

            # 投篮位置分布
            print(f"\n{COLORS['blue']}投篮位置分布:{COLORS['reset']}")
            shot_stats = [
                ('总投篮', stats.fieldGoalsMade, stats.fieldGoalsAttempted, stats.fieldGoalsPercentage),
                ('三分球', stats.threePointersMade, stats.threePointersAttempted, stats.threePointersPercentage),
                ('罚球', stats.freeThrowsMade, stats.freeThrowsAttempted, stats.freeThrowsPercentage)
            ]
            for name, made, attempted, percentage in shot_stats:
                if attempted > 0:
                    print(f"{name}: {made}/{attempted} ({self.format_percentage(percentage)})")

            # 进阶数据
            print(f"\n{COLORS['blue']}进阶数据:{COLORS['reset']}")
            print(f"真实命中率: {self.format_percentage(stats.fieldGoalsPercentage)}")
            print(f"有效命中率: {self.format_percentage(stats.fieldGoalsPercentage)}")
            print(f"使用率: {self.format_percentage(stats.fieldGoalsPercentage)}")
            print(f"助攻率: {self.format_percentage(stats.fieldGoalsPercentage)}")
            print(f"篮板率: {self.format_percentage(stats.fieldGoalsPercentage)}")

            # 防守数据
            print(f"\n{COLORS['blue']}防守数据:{COLORS['reset']}")
            print(f"防守篮板: {stats.reboundsDefensive}")
            print(f"抢断: {stats.steals}")
            print(f"盖帽: {stats.blocks}")
            print(f"防守犯规: {stats.foulsPersonal}")

            # 其他数据
            print(f"\n{COLORS['blue']}其他数据:{COLORS['reset']}")
            print(f"失误: {stats.turnovers}")
            print(f"犯规: {stats.foulsPersonal}")
            print(f"技术犯规: {stats.foulsTechnical}")
            print(f"+/-: {stats.plusMinusPoints if hasattr(stats, 'plusMinusPoints') else 0}")

        except Exception as e:
            self.logger.error(f"显示球员统计时出错: {e}")
            if self.logger.level == logging.DEBUG:
                self.logger.debug("错误详情:", exc_info=True)

    def display_team_stats(
            self,
            team: Optional[str] = None,
            date: Optional[str] = None
    ) -> None:
        """显示球队统计"""
        try:
            game = self._data_provider.get_game(team, date)
            if not game:
                return

            team_id = self._data_provider._get_team_id(team or self.default_team)
            is_home = game.game.homeTeam.teamId == team_id
            team = game.game.homeTeam if is_home else game.game.awayTeam

            print(f"\n{COLORS['yellow']}=== {team.teamCity} {team.teamName} 球队统计 ==={COLORS['reset']}")
            
            # 1. 得分分布
            print(f"\n{COLORS['blue']}得分分布:{COLORS['reset']}")
            print(f"总得分: {team.score}")
            print(f"油漆区得分: {team.get_stat('pointsInThePaint', 0)}")
            print(f"快攻得分: {team.get_stat('pointsFastBreak', 0)}")
            print(f"二次进攻得分: {team.get_stat('pointsSecondChance', 0)}")
            print(f"最大领先: {team.get_stat('leadLargest', 0)}")

            # 2. 投篮数据
            print(f"\n{COLORS['blue']}投篮数据:{COLORS['reset']}")
            made, attempted, percentage = team.field_goals
            print(f"总投篮: {made}/{attempted} ({self.format_percentage(percentage)})")
            
            made, attempted, percentage = team.three_pointers
            print(f"三分球: {made}/{attempted} ({self.format_percentage(percentage)})")
            
            made, attempted, percentage = team.free_throws
            print(f"罚球: {made}/{attempted} ({self.format_percentage(percentage)})")

            # 3. 篮板数据
            print(f"\n{COLORS['blue']}篮板数据:{COLORS['reset']}")
            print(f"总篮板: {team.get_stat('reboundsTotal')}")
            print(f"前场篮板: {team.get_stat('reboundsOffensive')}")
            print(f"后场篮板: {team.get_stat('reboundsDefensive')}")

            # 4. 其他数据
            print(f"\n{COLORS['blue']}其他数据:{COLORS['reset']}")
            other_stats = {
                '助攻': team.get_stat('assists'),
                '抢断': team.get_stat('steals'),
                '盖帽': team.get_stat('blocks'),
                '失误': team.get_stat('turnovers'),
                '犯规': team.get_stat('foulsPersonal'),
                '技术犯规': team.get_stat('foulsTechnical')
            }
            max_key_length = max(len(key) for key in other_stats.keys())
            for key, value in other_stats.items():
                print(f"{key.rjust(max_key_length)}: {value}")

            # 5. 替补席数据
            print(f"\n{COLORS['blue']}替补席得分:{COLORS['reset']}")
            bench_points = sum(p.statistics.points for p in team.players if p.starter != "1")
            print(f"替补得分: {bench_points}")

        except Exception as e:
            self.logger.error(f"显示球队统计时出错: {e}")
            if self.logger.level == logging.DEBUG:
                self.logger.debug("错误详情:", exc_info=True)

    def display_scoring_plays(
            self,
            team: Optional[str] = None,
            player: Optional[str] = None,
            date: Optional[str] = None
    ) -> None:
        """显示得分事件"""
        try:
            # 获取比赛数据以确定主队三字母代码
            game = self._data_provider.get_game()
            if not game:
                return
            home_team_code = game.game.homeTeam.teamTricode

            plays = self._data_provider.get_scoring_plays()
            if not plays:
                self.logger.error("未找到得分事件")
                return

            print(f"\n{COLORS['yellow']}=== 得分事件分析 ==={COLORS['reset']}")
            
            # 1. 得分事件统计
            print(f"\n{COLORS['blue']}得分类型统计:{COLORS['reset']}")
            scoring_types = {
                '两分球': 0,
                '三分球': 0,
                '罚球': 0,
                '快攻': 0,
                '二次进攻': 0,
            }
            
            # 2. 得分时间分布
            period_scores = {}
            clutch_plays = []  # 关键时刻得分
            
            for play in plays:
                # 统计得分类型
                if '3PT' in play['description']:
                    scoring_types['三分球'] += 1
                elif 'Free Throw' in play['description']:
                    scoring_types['罚球'] += 1
                else:
                    scoring_types['两分球'] += 1
                    
                if 'fastbreak' in play.get('qualifiers', []):
                    scoring_types['快攻'] += 1
                if '2ndchance' in play.get('qualifiers', []):
                    scoring_types['二次进攻'] += 1
                    
                # 记录每节得分
                period = play['period']
                if period not in period_scores:
                    period_scores[period] = {'home': 0, 'away': 0}
                
                points = 3 if '3PT' in play['description'] else (1 if 'Free Throw' in play['description'] else 2)
                is_home = play['team'] == home_team_code
                period_scores[period]['home' if is_home else 'away'] += points
                
                # 检查关键时刻得分
                if (period >= 4 and 
                    play['time'] <= "5:00" and 
                    abs(play.get('score_diff', 0)) <= 5):
                    clutch_plays.append(play)

            # 显示统计结果
            for score_type, count in scoring_types.items():
                if count > 0:
                    print(f"{score_type}: {count}")

            # 显示每节得分分布
            if period_scores:
                print(f"\n{COLORS['blue']}每节得分分布:{COLORS['reset']}")
                for period, scores in sorted(period_scores.items()):
                    period_name = f"第{period}节" if period <= 4 else f"加时{period-4}"
                    print(f"{period_name}: 主队 {scores['home']} - {scores['away']} 客队")
                
            # 显示关键时刻表现
            if clutch_plays:
                print(f"\n{COLORS['blue']}关键时刻表现:{COLORS['reset']}")
                for play in clutch_plays:
                    print(f"第{play['period']}节 {play['time']} - {play['description']}")

        except Exception as e:
            self.logger.error(f"显示得分事件时出错: {e}")
            if self.logger.level == logging.DEBUG:
                self.logger.debug("错误详情:", exc_info=True)