import logging
from pathlib import Path
from typing import Optional, Dict, Union
from datetime import datetime, timedelta

from nba.services.game_data_service import get_game_data
from nba.services.game_video_service import VideoService
from nba.fetcher.team import TeamProfile
from nba.parser.schedule_parser import ScheduleParser
from nba.fetcher.schedule import ScheduleFetcher
from config.nba_config import NBAConfig
from utils.time_handler import NBATimeHandler



class NBAGameAnalyzer:
    """NBA比赛分析器"""
    
    def __init__(self):
        """初始化分析器"""
        # 配置日志
        self.logger = logging.getLogger(__name__)
        self.video_service = VideoService()
        self.team_info = TeamProfile()
        self.schedule_fetcher = ScheduleFetcher()
        self.schedule_parser = ScheduleParser()
        
    def find_game(self, team_name: str, date_str: str = "today") -> Optional[str]:
        """
        查找比赛ID

        Args:
            team_name: 球队名称
            date_str: 日期字符串（支持 'today', 'yesterday', 'YYYY-MM-DD' 等）

        Returns:
            Optional[str]: 比赛ID
        """
        try:
            # 获取球队ID
            team_id = self.team_info.get_team_id(team_name)
            if not team_id:
                raise ValueError(f"未找到球队: {team_name}")

            # 获取赛程数据
            schedule_data = self.schedule_fetcher.get_schedule()
            if not schedule_data:
                raise ValueError("无法获取赛程数据")

            # 解析赛程数据
            schedule_df = self.schedule_parser.parse_raw_schedule(schedule_data)
            if schedule_df.empty:
                raise ValueError("赛程数据为空")

            # 处理特殊日期
            game_date = None
            if date_str.lower() == "today":
                game_date = datetime.now(NBATimeHandler.BEIJING_TZ).date()
            elif date_str.lower() == "yesterday":
                game_date = (datetime.now(NBATimeHandler.BEIJING_TZ) - timedelta(days=1)).date()
            else:
                # 尝试解析具体日期
                try:
                    game_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    self.logger.warning(f"无法解析日期: {date_str}，将查找最近的比赛")

            # 如果指定了日期，先尝试获取该日期的比赛
            if game_date:
                game_id = self.schedule_parser.get_game_id(schedule_df, team_id, game_date)
                if game_id:
                    self.logger.info(f"找到 {team_name} 在 {game_date} 的比赛: {game_id}")
                    return game_id
                self.logger.info(f"{team_name} 在 {game_date} 没有比赛，搜索最近的比赛...")

            # 如果没找到，获取最近的已结束比赛
            game_id = self.schedule_parser.get_last_game_id(schedule_df, team_id)
            if game_id:
                self.logger.info(f"找到 {team_name} 最近的已结束比赛: {game_id}")
                return game_id

            self.logger.warning(f"未找到 {team_name} 的任何比赛")
            return None

        except Exception as e:
            self.logger.error(f"查找比赛时出错: {e}")
            return None
        
    def analyze_game(
        self,
        team_name: str,
        player_name: Optional[str] = None,
        action_type: Optional[str] = None,
        game_date: str = "today",
        game_id: Optional[str] = None,
        download_video: bool = False,
        video_format: str = 'mp4'
    ) -> Dict:
        """分析比赛数据并获取视频片段"""
        try:
            # 如果没有提供game_id，查找比赛
            if not game_id:
                game_id = self.find_game(team_name, game_date)
                if not game_id:
                    return {"error": f"未找到 {team_name} 的比赛"}

            # 获取比赛数据
            events, stats = get_game_data(team_name, game_id=game_id)
            if not events or not stats:
                return {"error": f"无法获取比赛数据: {game_id}"}

            result = {
                "game_id": events.game_id,
                "events_count": len(events.events),
                "game_stats": stats,
                "videos": None
            }

            # 如果指定了球员，获取视频数据
            if player_name and action_type:
                event_collection, error = self.video_service.get_player_videos(
                    player_name=player_name,
                    action_type=action_type,
                    game_id=game_id
                )
                
                if error:
                    result["video_error"] = error
                elif event_collection and len(event_collection.events) > 0:
                    result["videos"] = {
                        "count": len(event_collection.events),
                        "event_ids": [e.event_id for e in event_collection.events],
                        "events": event_collection.events  # 直接使用 GameEvent 对象
                    }
                    
                    # 如果需要下载视频
                    if download_video:
                        # 创建视频资源字典
                        video_assets = {}
                        for event in event_collection.events:
                            if event.video_url:  # 确保有视频URL
                                video_assets[event.event_id] = VideoAsset(
                                    uuid=event.event_id,  # 使用event_id作为uuid
                                    duration=0,  # 这个信息可能需要从其他地方获取
                                    urls={'hd': event.video_url},  # 假设video_url是HD质量
                                    thumbnails={},  # 如果有缩略图URL可以添加
                                    subtitles={},
                                    event_info={'event_id': event.event_id},
                                    game_event=event
                                )
                                
                        if video_assets:
                            download_results = self.video_service.batch_download_videos(
                                videos=video_assets,
                                player_name=player_name,
                                game_id=game_id,
                                output_format=video_format
                            )
                            result["downloads"] = download_results

            return result

        except Exception as e:
            error_msg = f"分析比赛数据时出错: {e}"
            self.logger.error(error_msg)
            return {"error": error_msg}
            

def main():
    """主函数"""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 初始化分析器
    analyzer = NBAGameAnalyzer()

    # 分析勇士队的比赛，并获取库里的三分球视频
    result = analyzer.analyze_game(
        team_name="lakers",
        player_name="anthony davis",
        action_type="FGM",
        game_date="today",
        download_video=True,
        video_format='gif'
    )

    # 处理结果
    if "error" in result:
        print(f"错误: {result['error']}")
        return

    # 打印比赛信息
    print(f"比赛ID: {result['game_id']}")
    print(f"事件总数: {result['events_count']}")

    # 打印比分
    stats = result['game_stats']
    print(f"比分: {stats.home_team.score} - {stats.away_team.score}")

    # 打印视频信息
    if result.get("videos"):
        print(f"找到视频片段: {result['videos']['count']} 个")
        
        # 如果下载了视频，打印下载结果
        if "downloads" in result:
            success_count = sum(1 for v in result["downloads"].values() if isinstance(v, Path))
            print(f"成功下载: {success_count} 个视频")
            
            # 打印下载失败的信息
            failures = {k: v for k, v in result["downloads"].items() if isinstance(v, str)}
            if failures:
                print("\n下载失败:")
                for event_id, error in failures.items():
                    print(f"  事件 {event_id}: {error}")


if __name__ == "__main__":
    main()