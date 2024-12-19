import logging
from typing import Optional, Tuple, Dict
from functools import lru_cache
import asyncio

from pydantic import ValidationError
from nba.fetcher.game import GameFetcher
from nba.parser.game_parser import GameDataParser
from nba.parser.schedule_parser import ScheduleParser
from nba.fetcher.team import TeamProfile
from nba.fetcher.schedule import ScheduleFetcher
from nba.models.game_model import Game
from nba.models.event_model import PlayByPlay

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

class GameDataService:
    """比赛数据服务类，用于获取和解析NBA比赛数据。"""
    
    def __init__(
        self,
        team_info: Optional[TeamProfile] = None,
        schedule_fetcher: Optional[ScheduleFetcher] = None,
        game_fetcher: Optional[GameFetcher] = None,
        schedule_parser: Optional[ScheduleParser] = None,
        game_parser: Optional[GameDataParser] = None
    ):
        """初始化GameDataService"""
        self.team_info = team_info or TeamProfile()
        self.schedule_fetcher = schedule_fetcher or ScheduleFetcher()
        self.game_fetcher = game_fetcher or GameFetcher()
        self.schedule_parser = schedule_parser or ScheduleParser()
        self.game_parser = game_parser or GameDataParser()

    @lru_cache(maxsize=128)
    def get_cached_game_id(self, team_id: int, game_date: str) -> Optional[str]:
        """缓存获取比赛ID的结果"""
        try:
            schedule_data = self.schedule_fetcher.get_schedule()
            schedule_df = self.schedule_parser.parse_raw_schedule(schedule_data)
            game_id = self.schedule_parser.get_game_id(schedule_df, team_id, game_date)
            logger.info(f"获取到的比赛ID: {game_id}")
            return game_id
        except Exception as e:
            logger.error(f"获取比赛ID时出错: {e}")
            return None

    async def fetch_game_data(self, game_id: str) -> Tuple[Optional[PlayByPlay], Optional[Game]]:
        """异步获取比赛数据"""
        try:
            logger.info(f"开始异步获取比赛数据，比赛ID: {game_id}")
            
            # 异步获取数据
            loop = asyncio.get_event_loop()
            pbp_data_future = loop.run_in_executor(None, self.game_fetcher.get_playbyplay, game_id)
            boxscore_data_future = loop.run_in_executor(None, self.game_fetcher.get_boxscore, game_id)

            pbp_data, boxscore_data = await asyncio.gather(pbp_data_future, boxscore_data_future)

            if not pbp_data or not boxscore_data:
                logger.error("无法获取完整的比赛数据")
                return None, None

            try:
                # 打印数据结构以便调试
                logger.debug(f"Boxscore data keys: {list(boxscore_data.keys())}")
                logger.debug(f"Game data keys: {list(boxscore_data.get('game', {}).keys())}")

                # 尝试解析数据
                playbyplay = PlayByPlay.parse_obj(pbp_data)
                game = Game.parse_obj(boxscore_data)

                # 验证关键数据
                if game.game:
                    logger.info(f"成功解析比赛数据，比赛ID: {game_id}")
                    logger.debug(f"主队得分: {game.game.homeTeam.score if game.game.homeTeam else 'N/A'}")
                    logger.debug(f"客队得分: {game.game.awayTeam.score if game.game.awayTeam else 'N/A'}")
                else:
                    logger.warning("解析的比赛数据不完整")

                return playbyplay, game

            except ValidationError as ve:
                logger.error(f"数据验证错误: {ve}")
                # 打印详细的验证错误信息
                for error in ve.errors():
                    logger.error(f"验证错误: {error}")
                return None, None

        except Exception as e:
            logger.error(f"获取或解析比赛数据时出错: {e}", exc_info=True)
            return None, None

    async def get_game_data(
        self, 
        team_name: str, 
        game_date: Optional[str] = "today", 
        game_id: Optional[str] = None
    ) -> Tuple[Optional[PlayByPlay], Optional[Game]]:
        """获取完整的比赛数据"""
        try:
            # 获取 game_id
            if not game_id:
                logger.info(f"获取球队ID: {team_name}")
                team_id = self.team_info.get_team_id(team_name)
                if not team_id:
                    raise ValueError(f"未找到球队: {team_name}")

                logger.info("获取并解析赛程数据...")
                game_id = self.get_cached_game_id(team_id, game_date)
                if not game_id:
                    raise ValueError(f"未找到 {team_name} 在 {game_date} 的比赛ID。")

            # 获取比赛数据
            playbyplay, game = await self.fetch_game_data(game_id)
            
            # 验证数据完整性
            if game and not game.get_team_stats(True):
                logger.warning("比赛数据中缺少主队统计数据")
            if game and not game.get_team_stats(False):
                logger.warning("比赛数据中缺少客队统计数据")

            return playbyplay, game

        except Exception as e:
            logger.error(f"获取或解析 {team_name} 在 {game_date} 的比赛数据时出错: {e}")
            return None, None

    def get_team_statistics(self, game: Game, is_home: bool = True) -> Dict:
        """获取球队统计数据的辅助方法"""
        try:
            team_stats = game.get_team_stats(is_home)
            if not team_stats:
                return {}
            
            return {
                "score": team_stats.score,
                "team_name": team_stats.teamName,
                "timeouts_remaining": team_stats.timeoutsRemaining,
                "period_scores": game.get_period_scores(is_home),
                "statistics": team_stats.statistics or {}
            }
        except Exception as e:
            logger.error(f"获取球队统计数据时出错: {e}")
            return {}


"""比赛数据服务类，用于获取和解析NBA比赛数据。
    
    使用示例:
    ```python
    import asyncio
    from nba.services.game_data_service import GameDataService
    
    async def get_player_performance(player_name: str, team_name: str, game_date: str):
        # 初始化服务
        service = GameDataService()
        
        # 获取比赛数据
        playbyplay, game = await service.get_game_data(team_name, game_date)
        if not game:
            print("未能获取比赛数据")
            return
            
        # 获取主队数据
        home_team = game.game.homeTeam
        away_team = game.game.awayTeam
        
        # 在主队中查找球员
        for player in home_team.players:
            if player.name == player_name:
                stats = player.statistics
                print(f"\n{player.name} 的数据:")
                print(f"得分: {stats.points}")
                print(f"篮板: {stats.reboundsTotal}")
                print(f"助攻: {stats.assists}")
                print(f"投篮: {stats.fieldGoalsMade}/{stats.fieldGoalsAttempted}")
                print(f"三分: {stats.threePointersMade}/{stats.threePointersAttempted}")
                return
                
        # 在客队中查找球员
        for player in away_team.players:
            if player.name == player_name:
                stats = player.statistics
                print(f"\n{player.name} 的数据:")
                print(f"得分: {stats.points}")
                print(f"篮板: {stats.reboundsTotal}")
                print(f"助攻: {stats.assists}")
                print(f"投篮: {stats.fieldGoalsMade}/{stats.fieldGoalsAttempted}")
                print(f"三分: {stats.threePointersMade}/{stats.threePointersAttempted}")
                return
    
    async def get_team_stats(team_name: str, game_date: str):
        # 初始化服务
        service = GameDataService()
        
        # 获取比赛数据
        playbyplay, game = await service.get_game_data(team_name, game_date)
        if not game:
            print("未能获取比赛数据")
            return
            
        # 判断目标球队是主队还是客队
        home_team = game.game.homeTeam
        away_team = game.game.awayTeam
        is_home = home_team.teamName == team_name
        
        team = home_team if is_home else away_team
        opponent = away_team if is_home else home_team
        
        # 打印比赛基本信息
        print(f"比赛：{team.teamName} vs {opponent.teamName}")
        print(f"比分：{team.score} - {opponent.score}")
        
        # 打印球队统计数据
        stats = team.statistics
        print(f"\n球队数据:")
        print(f"投篮：{stats.get('fieldGoalsMade', 0)}/{stats.get('fieldGoalsAttempted', 0)}")
        print(f"三分：{stats.get('threePointersMade', 0)}/{stats.get('threePointersAttempted', 0)}")
        print(f"罚球：{stats.get('freeThrowsMade', 0)}/{stats.get('freeThrowsAttempted', 0)}")
        print(f"助攻：{stats.get('assists', 0)}")
        print(f"篮板：{stats.get('reboundsTotal', 0)}")
        print(f"抢断：{stats.get('steals', 0)}")
        print(f"盖帽：{stats.get('blocks', 0)}")
        print(f"失误：{stats.get('turnovers', 0)}")

    # 使用示例
    if __name__ == "__main__":
        # 查看球员数据
        asyncio.run(get_player_performance("LeBron James", "Lakers", "2024-12-09"))
        
        # 查看球队数据
        asyncio.run(get_team_stats("Lakers", "2024-12-09"))
    ```
    
    这个服务类提供了以下主要功能：
    1. 获取比赛ID（get_cached_game_id）
    2. 获取比赛数据（get_game_data）
    3. 异步获取比赛统计和回放数据（fetch_game_data）
    
    主要属性：
    - team_info: 球队信息服务
    - schedule_fetcher: 赛程获取服务
    - game_fetcher: 比赛数据获取服务
    - schedule_parser: 赛程解析服务
    - game_parser: 比赛数据解析服务
    
    数据模型：
    - Game: 完整的比赛数据模型
    - PlayByPlay: 比赛回放数据模型
    """