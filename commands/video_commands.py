"""
视频处理命令模块 - 处理视频下载、合并和GIF生成相关功能
"""
from typing import Dict

from commands.base_command import NBACommand, error_handler


class BaseVideoCommand(NBACommand):
    """视频处理命令基类"""

    def _log_video_result(self, app, videos: Dict, video_type: str, key: str) -> None:
        """记录视频处理结果"""
        if not videos:
            print(f"× 获取 {video_type.replace('_', ' ')} 视频数据失败或无结果")
            return

        if key in videos and videos[key]:
            path = videos[key]
            app.video_paths[video_type] = path
            print(f"✓ 已生成 {video_type.replace('_', ' ')} 合并视频: {path}")
        elif "videos" in videos and videos["videos"]:
            count = len(videos["videos"])
            print(f"✓ 获取到 {count} 个 {video_type.replace('_', ' ')} 视频片段")
        elif "gifs" in videos and videos["gifs"]:
            count = len(videos["gifs"])
            print(f"✓ 获取到 {count} 个 {video_type.replace('_', ' ')} GIF")
            # 存储整个字典
            app.round_gifs = videos["gifs"]
        else:
            print(f"✓ 处理 {video_type.replace('_', ' ')} 完成，但未找到预期的输出文件 (key: {key})")


class VideoCommand(BaseVideoCommand):
    """所有视频处理命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("视频处理 (全部)")

        team_success = self._process_team_video(app)
        player_success = self._process_player_video(app)
        rounds_success = self._process_round_gifs(app)

        # 只要有一部分成功就视为成功
        if team_success or player_success or rounds_success:
            print("\n视频处理完成 (可能部分成功)。")
            return True
        else:
            print("\n所有视频处理均失败。")
            return False

    def _process_team_video(self, app) -> bool:
        print("\n--- 处理球队集锦 ---")
        try:
            team_videos = app.nba_service.get_team_highlights(team=app.config.team, merge=True)
            self._log_video_result(app, team_videos, "team_video", "merged")
            return bool(team_videos)
        except Exception as e:
            app.logger.error(f"处理球队集锦视频时发生错误: {e}", exc_info=True)
            print(f"× 处理球队集锦视频时发生错误: {e}")
            return False

    def _process_player_video(self, app) -> bool:
        if not app.config.player:
            print("跳过球员视频处理 (未指定球员)")
            return True  # 未指定球员不算失败

        print("\n--- 处理球员集锦 ---")
        try:
            player_videos = app.nba_service.get_player_highlights(
                player_name=app.config.player,
                team=app.config.team,  # 提供球队上下文
                merge=True,
                output_format="video"  # 只需要视频
            )
            self._log_video_result(app, player_videos, "player_video", "video_merged")
            return bool(player_videos)
        except Exception as e:
            app.logger.error(f"处理球员集锦视频时发生错误: {e}", exc_info=True)
            print(f"× 处理球员集锦视频时发生错误: {e}")
            return False

    def _process_round_gifs(self, app) -> bool:
        if not app.config.player:
            print("跳过球员回合GIF处理 (未指定球员)")
            return True  # 未指定球员不算失败

        print("\n--- 处理球员回合 GIF ---")
        try:
            app.round_gifs = app.nba_service.get_player_round_gifs(
                player_name=app.config.player,
                team=app.config.team  # 提供球队上下文
            )
            if app.round_gifs:
                print(f"✓ 已生成 {len(app.round_gifs)} 个球员回合 GIF")
                return True
            else:
                print("✓ 未找到或生成球员回合 GIF (可能无符合条件的回合)")
                return True  # 无GIF也不算失败
        except Exception as e:
            app.logger.error(f"处理球员回合GIF时发生错误: {e}", exc_info=True)
            print(f"× 处理球员回合GIF时发生错误: {e}")
            return False


class VideoTeamCommand(BaseVideoCommand):
    """球队视频处理命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("处理球队集锦视频")
        team_videos = app.nba_service.get_team_highlights(team=app.config.team, merge=True)
        self._log_video_result(app, team_videos, "team_video", "merged")
        return bool(team_videos)


class VideoPlayerCommand(BaseVideoCommand):
    """球员视频处理命令"""

    @error_handler
    def execute(self, app) -> bool:
        if not app.config.player:
            print("× 请使用 --player 指定球员名称")
            return False

        self._log_section(f"处理球员 {app.config.player} 集锦视频")
        player_videos = app.nba_service.get_player_highlights(
            player_name=app.config.player,
            merge=True,
            output_format="video"
        )
        self._log_video_result(app, player_videos, "player_video", "video_merged")
        return bool(player_videos)


class VideoRoundsCommand(BaseVideoCommand):
    """球员回合GIF处理命令"""

    @error_handler
    def execute(self, app) -> bool:
        if not app.config.player:
            print("× 请使用 --player 指定球员名称")
            return False

        self._log_section(f"处理球员 {app.config.player} 回合 GIF")
        app.round_gifs = app.nba_service.get_player_round_gifs(
            player_name=app.config.player,
        )
        if app.round_gifs:
            print(f"✓ 已生成 {len(app.round_gifs)} 个球员回合 GIF")
            return True
        else:
            print("✓ 未找到或生成球员回合 GIF (可能无符合条件的回合)")
            return True  # 无错误就算成功