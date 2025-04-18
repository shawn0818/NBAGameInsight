"""
NBA应用命令模块 - 实现命令模式的各种功能命令

通过命令模式将应用功能组织为独立的命令类，便于扩展和维护。
主要包括数据查询、图表生成、视频处理、微博发布和数据同步等功能。
"""
# 导出基础组件
from commands.base_command import (
    NBACommand, error_handler,
    AppError, CommandExecutionError, DataFetchError
)

# 导出信息命令
from commands.info_command import InfoCommand

# 导出图表命令
from commands.chart_commands import (
    ChartCommand,
    FullCourtChartCommand,
    PlayerImpactChartCommand
)

# 导出视频命令
from commands.video_commands import (
    BaseVideoCommand, VideoCommand,
    VideoTeamCommand, VideoPlayerCommand, VideoRoundsCommand
)

# 导出AI命令
from commands.ai_command import AICommand

# 导出微博命令
from commands.weibo_commands import (
    WeiboCommand, WeiboTeamCommand, WeiboPlayerCommand,
    WeiboChartCommand, WeiboTeamChartCommand,
    WeiboRoundCommand, WeiboTeamRatingCommand
)

# 导出同步命令
from commands.sync_commands import (
    BaseSyncCommand, SyncCommand,
    NewSeasonCommand, SyncPlayerDetailsCommand
)

# 导出命令工厂
from commands.command_factory import NBACommandFactory, CompositeCommand