"""
NBA 比赛视频下载脚本
"""

import logging
from pathlib import Path
import argparse
from typing import Optional, Dict
from dataclasses import dataclass
import sys

from nba.models.video_model import ContextMeasure
from nba.services.game_data_service import NBAGameDataProvider
from nba.services.game_video_service import GameVideoService
from config.nba_config import NBAConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class DownloadConfig:
    """下载配置"""
    team_name: str
    player_name: Optional[str] = None
    date_str: str = "today"
    action_type: Optional[str] = None   # 如 "FGM", "FG3M" 等
    to_gif: bool = False
    quality: str = "hd"
    output_dir: Optional[Path] = None


class VideoDownloader:
    """NBA比赛视频下载器"""

    def __init__(self,
                 data_provider: Optional[NBAGameDataProvider] = None,
                 video_service: Optional[GameVideoService] = None,
                 output_dir: Optional[Path] = None):
        """
        初始化视频下载器

        Args:
            data_provider (Optional[NBAGameDataProvider]): 比赛数据提供者
            video_service (Optional[GameVideoService]): 视频服务
            output_dir (Optional[Path]): 输出目录
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.data_provider = data_provider or NBAGameDataProvider()
        self.video_service = video_service or GameVideoService()
        self.output_dir = output_dir or NBAConfig.PATHS.VIDEO_DIR

    def download_game_videos(self, config: DownloadConfig) -> None:
        """
        下载比赛视频的主流程

        Args:
            config (DownloadConfig): 下载配置
        """
        try:
            # 1. 获取比赛数据
            game = self.data_provider.get_game(
                team_name=config.team_name,
                date_str=config.date_str
            )
            if not game:
                self.logger.error("未找到比赛数据")
                return
            game_id = game.game.gameId
            self.logger.info(f"找到比赛: {game_id}")

            # 2. 获取球员ID（可选）
            player_id = None
            if config.player_name:
                player_id = self.data_provider.get_player_id(
                    player_name=config.player_name,
                    team_name=config.team_name,
                    date_str=config.date_str
                )
                if not player_id:
                    self.logger.error(f"未找到球员 {config.player_name} 的ID")
                    return
                self.logger.info(f"找到球员ID: {player_id}")

            # 3. 确定 context_measure
            if config.action_type:
                try:
                    context_measure = ContextMeasure[config.action_type]
                    self.logger.info(f"使用动作类型: {context_measure}")
                except KeyError:
                    context_measure = ContextMeasure.FGM
                    self.logger.warning(f"未知的动作类型 {config.action_type}，使用默认值 FGM")
            else:
                context_measure = ContextMeasure.FGM
                self.logger.info("使用默认动作类型: FGM")

            # 4. 获取视频数据
            videos = self.video_service.get_game_videos(
                game_id=game_id,
                context_measure=context_measure,
                player_id=player_id
            )

            if not videos:
                self.logger.error("未找到视频数据")
                return

            self.logger.info(f"找到 {len(videos)} 个视频")

            # 5. 创建输出目录
            final_output_dir = self.output_dir / f"{game_id}"
            if config.player_name:
                final_output_dir = final_output_dir / config.player_name.replace(" ", "_")
            final_output_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"创建输出目录: {final_output_dir}")

            # 6. 批量下载视频
            results = self.video_service.batch_download(
                videos=videos,
                output_dir=final_output_dir,
                quality=config.quality,
                to_gif=config.to_gif,
                compress=False  # 根据需求可调整
            )

            # 7. 输出结果
            success_count = len(results)
            total_count = len(videos)
            self.logger.info(f"下载完成: {success_count}/{total_count} 个视频成功")
            for event_id, path in results.items():
                self.logger.info(f"视频已保存: {path}")

        except Exception as e:
            self.logger.error(f"下载视频时出错: {str(e)}", exc_info=True)
            raise

    def download_game_videos_programmatically(self, config: DownloadConfig) -> Dict[str, Path]:
        """
        通过代码调用下载比赛视频

        Args:
            config (DownloadConfig): 下载配置

        Returns:
            Dict[str, Path]: 下载结果字典 {event_id: Path}
        """
        try:
            # 1. 获取比赛数据
            game = self.data_provider.get_game(
                team_name=config.team_name,
                date_str=config.date_str
            )
            if not game:
                self.logger.error("未找到比赛数据")
                return {}
            game_id = game.game.gameId
            self.logger.info(f"找到比赛: {game_id}")

            # 2. 获取球员ID（可选）
            player_id = None
            if config.player_name:
                player_id = self.data_provider.get_player_id(
                    player_name=config.player_name,
                    team_name=config.team_name,
                    date_str=config.date_str
                )
                if not player_id:
                    self.logger.error(f"未找到球员 {config.player_name} 的ID")
                    return {}
                self.logger.info(f"找到球员ID: {player_id}")

            # 3. 确定 context_measure
            if config.action_type:
                try:
                    context_measure = ContextMeasure[config.action_type]
                    self.logger.info(f"使用动作类型: {context_measure}")
                except KeyError:
                    context_measure = ContextMeasure.FGM
                    self.logger.warning(f"未知的动作类型 {config.action_type}，使用默认值 FGM")
            else:
                context_measure = ContextMeasure.FGM
                self.logger.info("使用默认动作类型: FGM")

            # 4. 获取视频数据
            videos = self.video_service.get_game_videos(
                game_id=game_id,
                context_measure=context_measure,
                player_id=player_id
            )

            if not videos:
                self.logger.error("未找到视频数据")
                return {}

            self.logger.info(f"找到 {len(videos)} 个视频")

            # 5. 创建输出目录
            final_output_dir = self.output_dir / f"{game_id}"
            if config.player_name:
                final_output_dir = final_output_dir / config.player_name.replace(" ", "_")
            final_output_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"创建输出目录: {final_output_dir}")

            # 6. 批量下载视频
            results = self.video_service.batch_download(
                videos=videos,
                output_dir=final_output_dir,
                quality=config.quality,
                to_gif=config.to_gif,
                compress=False  # 根据需求可调整
            )

            # 7. 输出结果
            success_count = len(results)
            total_count = len(videos)
            self.logger.info(f"下载完成: {success_count}/{total_count} 个视频成功")
            for event_id, path in results.items():
                self.logger.info(f"视频已保存: {path}")

            return results

        except Exception as e:
            self.logger.error(f"下载视频时出错: {str(e)}", exc_info=True)
            raise


def parse_args() -> DownloadConfig:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="NBA比赛视频下载工具")
    parser.add_argument("--team", required=True, help="球队名称")
    parser.add_argument("--player", help="球员名称（可选）")
    parser.add_argument("--date", default="today", help="比赛日期 (YYYY-MM-DD，默认为today)")
    parser.add_argument("--action", help="动作类型（如FGM, FG3M, AST等）")
    parser.add_argument("--output", type=Path, help="输出目录")
    parser.add_argument("--to-gif", action="store_true", help="转换为GIF格式")
    parser.add_argument("--quality", choices=["sd", "hd"], default="hd", help="视频质量")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")

    args = parser.parse_args()

    return DownloadConfig(
        team_name=args.team,
        player_name=args.player,
        date_str=args.date,
        action_type=args.action,
        to_gif=args.to_gif,
        quality=args.quality,
        output_dir=args.output
    )


def main():
    # 解析命令行
    config = parse_args()

    # 设置日志级别
    if config is not None and '--debug' in sys.argv:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger('nba').setLevel(logging.DEBUG)
        logging.getLogger('utils').setLevel(logging.DEBUG)

    # 创建下载器并执行下载
    downloader = VideoDownloader(output_dir=config.output_dir)
    downloader.download_game_videos(config)


if __name__ == "__main__":
    main()

'''
from pathlib import Path
from nba.services.game_video_service import GameVideoService
from nba.services.game_data_service import NBAGameDataProvider
from download_nba_videos import VideoDownloader, DownloadConfig, ContextMeasure

# 自定义配置
config = DownloadConfig(
    team_name="Lakers",
    player_name="LeBron James",
    date_str="2024-12-25",
    action_type="FGM",
    to_gif=True,
    quality="hd",
    output_dir=Path("./downloaded_videos")
)

# 实例化 VideoDownloader（可以注入自定义的服务组件）
downloader = VideoDownloader()

# 执行下载
downloader.download_game_videos_programmatically(config)

'''