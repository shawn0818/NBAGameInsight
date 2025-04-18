"""
命令工厂模块 - 创建和管理命令实例

负责根据运行模式创建对应的命令对象，以及组合多个命令。
"""
from typing import List, Set
from enum import Enum

from commands.base_command import NBACommand
from commands.info_command import InfoCommand
from commands.chart_commands import ChartCommand, FullCourtChartCommand, PlayerImpactChartCommand
from commands.video_commands import VideoCommand, VideoTeamCommand, VideoPlayerCommand, VideoRoundsCommand
from commands.ai_command import AICommand
from commands.weibo_commands import (
    WeiboTeamCommand, WeiboPlayerCommand, WeiboChartCommand,
    WeiboTeamChartCommand, WeiboRoundCommand, WeiboTeamRatingCommand
)
from commands.sync_commands import SyncCommand, NewSeasonCommand, SyncPlayerDetailsCommand


class CompositeCommand(NBACommand):
    """组合命令，执行多个命令"""

    def __init__(self, commands: List[NBACommand]):
        self.commands = commands

    def execute(self, app) -> bool:
        results = []
        print("\n--- 开始执行组合命令 ---")
        for i, command in enumerate(self.commands, 1):
            command_name = command.__class__.__name__.replace('Command', '')
            print(f"\n[{i}/{len(self.commands)}] 执行命令: {command_name}")
            result = command.execute(app)
            results.append(result)
            if not result:
                print(f"  ! 命令 {command_name} 执行失败或未完成。")
            print(f"--- 命令 {command_name} 执行结束 ---")

        # 全部成功才算成功
        overall_success = all(results)
        print(f"\n--- 组合命令执行结束 ({'成功' if overall_success else '部分失败/全部失败'}) ---")
        return overall_success


class NBACommandFactory:
    """NBA命令工厂，负责创建对应的命令对象"""

    @staticmethod
    def create_command(mode: Enum) -> NBACommand:
        """根据运行模式创建对应的命令

        Args:
            mode: 运行模式枚举

        Returns:
            NBACommand: 对应的命令实例
        """
        command_map = {
            # 基础功能命令
            'info': InfoCommand(),
            'chart': ChartCommand(),
            'full-court-chart': FullCourtChartCommand(),
            'impact-chart': PlayerImpactChartCommand(),
            'video': VideoCommand(),
            'video-team': VideoTeamCommand(),
            'video-player': VideoPlayerCommand(),
            'video-rounds': VideoRoundsCommand(),
            'ai': AICommand(),
            # 微博命令
            'weibo-team': WeiboTeamCommand(),
            'weibo-player': WeiboPlayerCommand(),
            'weibo-chart': WeiboChartCommand(),
            'weibo-team-chart': WeiboTeamChartCommand(),
            'weibo-round': WeiboRoundCommand(),
            'weibo-team-rating': WeiboTeamRatingCommand(),
            # 同步命令
            'sync': SyncCommand(),
            'sync-new-season': NewSeasonCommand(),
            'sync-player-details': SyncPlayerDetailsCommand(),
        }

        # 获取模式值作为查找键
        mode_value = mode.value if hasattr(mode, 'value') else str(mode)

        # 处理组合模式
        if mode_value in ["all", "weibo"]:
            # 基础命令 - 适用于 ALL 和 WEIBO 模式
            base_commands = [
                InfoCommand(),
                ChartCommand(),
                FullCourtChartCommand(),
                PlayerImpactChartCommand(),
                VideoCommand(),
                AICommand()
            ]

            # 获取微博模式判断逻辑
            weibo_modes = getattr(mode.__class__, 'get_weibo_modes', lambda: set([mode_value]))()

            # 微博命令 - 只有当模式在微博相关模式集合中且未禁用微博时才添加
            weibo_commands = []
            if mode_value in [m.value if hasattr(m, 'value') else str(m) for m in weibo_modes]:
                # 微博命令添加顺序是重要的
                weibo_commands = [
                    WeiboTeamCommand(),
                    WeiboPlayerCommand(),
                    WeiboChartCommand(),
                    WeiboTeamChartCommand(),
                    WeiboRoundCommand(),
                    WeiboTeamRatingCommand()
                ]

            # 合并命令 - ALL和WEIBO模式都执行所有命令(包括微博命令)
            # 实际禁用微博由App对象控制
            all_commands = base_commands + weibo_commands
            return CompositeCommand(all_commands)

        # 处理单个命令
        command = command_map.get(mode_value)
        if command:
            return command
        else:
            raise ValueError(f"未知的运行模式: {mode_value}")