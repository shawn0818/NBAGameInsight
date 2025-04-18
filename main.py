# main.py
"""NBA 数据服务主程序 - 重构版

实现以下核心功能：
1. 比赛基础信息查询
2. 投篮图表生成 (半场/全场/球员影响力)
3. 视频处理功能 (球队/球员/回合GIF)
4. 发布内容到微博 (利用AI生成内容)
5. AI分析比赛/球员数据 (显示)
6. 核心数据同步管理 (比赛统计/新赛季/球员详情)

用法:
    python main.py [options]
"""
import argparse
import re
import sys
import logging
from pathlib import Path
from enum import Enum
from typing import List, Dict, Any, Optional, Set, Union
from dataclasses import dataclass, field
from dotenv import load_dotenv, find_dotenv

from ai.ai_context_preparer import AIContextPreparer
from config import NBAConfig
# 导入服务
from nba.services.nba_service import NBAService, NBAServiceConfig, ServiceNotAvailableError, InitializationError
from nba.services.game_video_service import VideoConfig
from utils.video_converter import VideoProcessConfig
from utils.logger_handler import AppLogger
from ai.ai_processor import AIConfig
from weibo.weibo_post_service import WeiboPostService
from ai.ai_service import AIService

# 导入命令模块
from commands.base_command import NBACommand, AppError, CommandExecutionError, DataFetchError
from commands.command_factory import NBACommandFactory


# ============1. 基础配置和枚举===============

class RunMode(Enum):
    """应用程序运行模式"""
    # 基础功能模式
    INFO = "info"  # 只显示比赛信息
    CHART = "chart"  # 生成半场图表 (球队和球员)
    FULL_COURT_CHART = "full-court-chart" # 生成全场图表 (新)
    IMPACT_CHART = "impact-chart" # 生成球员影响力图表 (新)
    VIDEO = "video"  # 处理所有视频
    VIDEO_TEAM = "video-team"  # 只处理球队视频
    VIDEO_PLAYER = "video-player"  # 只处理球员视频
    VIDEO_ROUNDS = "video-rounds"  # 处理球员视频的回合GIF
    AI = "ai"  # 只运行AI分析 (显示)

    # 微博相关模式
    WEIBO = "weibo"  # 执行所有微博发布功能
    WEIBO_TEAM = "weibo-team"  # 只发布球队集锦视频
    WEIBO_PLAYER = "weibo-player"  # 只发布球员集锦视频
    WEIBO_CHART = "weibo-chart"  # 只发布球员投篮图
    WEIBO_TEAM_CHART = "weibo-team-chart"  # 只发布球队投篮图
    WEIBO_ROUND = "weibo-round"  # 只发布球员回合解说和GIF
    WEIBO_TEAM_RATING = "weibo-team-rating" # 只发布球队赛后评级 (保持)

    # 综合模式
    ALL = "all"  # 执行所有功能 (不含同步)

    # 同步相关模式 (精简后)
    SYNC = "sync"  # 增量并行同步比赛统计数据 (gamedb)
    SYNC_NEW_SEASON = "sync-new-season"  # 手动触发新赛季核心数据更新 (nba.db)
    SYNC_PLAYER_DETAILS = "sync-player-details"  # 同步球员详细信息

    @classmethod
    def get_weibo_modes(cls) -> Set["RunMode"]:
        """获取所有微博相关模式"""
        return {
            cls.WEIBO, cls.WEIBO_TEAM, cls.WEIBO_PLAYER,
            cls.WEIBO_CHART, cls.WEIBO_TEAM_CHART,
            cls.WEIBO_ROUND, cls.WEIBO_TEAM_RATING, cls.ALL # ALL 模式可能触发微博
        }

    @classmethod
    def get_ai_modes(cls) -> Set["RunMode"]:
        """获取所有需要AI功能的模式"""
        # AI 分析模式和所有微博模式都需要AI
        return {cls.AI}.union(cls.get_weibo_modes())

    @classmethod
    def get_sync_modes(cls) -> Set["RunMode"]:
        """获取所有数据同步相关模式"""
        return {
            cls.SYNC,
            cls.SYNC_NEW_SEASON,
            cls.SYNC_PLAYER_DETAILS
        }


@dataclass
class AppConfig:
    """应用程序配置类"""
    # 基础配置
    team: str = "Lakers"
    player: str = "LeBron James"
    date: str = "last"
    mode: RunMode = RunMode.ALL
    debug: bool = False
    no_weibo: bool = False

    # 同步相关配置
    force_update: bool = False # 主要用于 sync 模式强制更新统计数据
    max_workers: int = 8
    batch_size: int = 50

    # 路径相关配置
    config_file: Optional[Path] = None
    root_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent)

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "AppConfig":
        """从命令行参数创建配置"""
        return cls(
            team=args.team,
            player=args.player,
            date=args.date,
            mode=RunMode(args.mode),
            debug=args.debug,
            no_weibo=args.no_weibo,
            force_update=args.force_update,
            max_workers=args.max_workers,
            batch_size=args.batch_size,
            config_file=Path(args.config) if args.config else None
        )


# ============2. 服务管理类===============

class ServiceManager:
    """服务管理器，负责初始化和管理各种服务"""

    def __init__(self, config: AppConfig, logger: logging.Logger):
        """
        初始化服务管理器。

        Args:
            config (AppConfig): 应用程序配置对象。
            logger (logging.Logger): 用于记录日志的记录器实例。
        """
        self.config = config
        self.logger = logger
        self._services: Dict[str, Any] = {} # 存储服务实例
        self._service_status: Dict[str, bool] = {} # 追踪服务初始化是否成功

    def init_services(self):
        """根据运行模式初始化所有必要服务。"""
        self.logger.info("开始初始化服务...")
        # 1. 始终初始化 NBA 服务 (核心)
        nba_service = self._init_nba_service()
        if not nba_service:
            raise InitializationError("NBA 服务初始化失败，无法继续。")
        self._services['nba_service'] = nba_service
        self._service_status['nba_service'] = True

        # --- 修改 AI 初始化逻辑 ---
        ai_preparer = None # 初始化为 None
        # 2. 尝试初始化 AI 上下文准备器 (Info 等模式需要)
        if nba_service and nba_service.data_service: # 确保 data_service 可用
            try:
                self.logger.info("初始化 AI 上下文准备器...")
                # 直接创建 Preparer 实例
                ai_preparer = AIContextPreparer(nba_service.data_service)
                self._services['ai_context_preparer'] = ai_preparer
                self._service_status['ai_context_preparer'] = True
                self.logger.info("AI 上下文准备器初始化成功。")
            except Exception as e:
                 self.logger.error(f"初始化 AI 上下文准备器失败: {e}", exc_info=True)
                 self._service_status['ai_context_preparer'] = False

        # 3. 仅在需要时初始化完整的 AI 服务 (用于生成内容)
        if self._needs_ai_service():
            if ai_preparer: # 如果 Preparer 初始化成功
                # 注意: _init_ai_service 现在接收 AIContextPreparer
                ai_service = self._init_ai_service(ai_preparer)
                if ai_service:
                    self._services['ai_service'] = ai_service
                    self._service_status['ai_service'] = True
                else:
                    self.logger.warning("AI 服务初始化失败，依赖 AI 生成的功能将不可用。")
                    self._service_status['ai_service'] = False
            else:
                 self.logger.warning("AI 上下文准备器未初始化，无法初始化 AI 服务。")
                 self._service_status['ai_service'] = False
        # --- 修改结束 ---

        # 4. 如果需要，初始化微博服务
        if self._needs_weibo_service():
            weibo_service = self._init_weibo_service()
            if weibo_service:
                self._services['weibo_service'] = weibo_service
                self._service_status['weibo_service'] = True
            else:
                self.logger.warning("微博服务初始化失败，微博发布功能将不可用。")
                self._service_status['weibo_service'] = False

        self.logger.info("服务初始化流程完成。")

    def _init_nba_service(self) -> Optional[NBAService]:
        """初始化核心 NBA 服务。"""
        try:
            self.logger.info("初始化 NBA 服务...")
            # 使用统一的基础输出目录
            base_output_dir = self.config.root_dir / NBAConfig.PATHS.STORAGE_DIR
            base_output_dir.mkdir(parents=True, exist_ok=True) # 确保目录存在

            # NBA 服务配置
            nba_config = NBAServiceConfig(
                default_team=self.config.team,
                default_player=self.config.player,
                base_output_dir=base_output_dir
            )
            # 视频服务配置
            video_config = VideoConfig(base_output_dir=base_output_dir)
            # 视频处理配置
            video_process_config = VideoProcessConfig()

            # 创建 NBA 服务实例
            service = NBAService(
                config=nba_config,
                video_config=video_config,
                video_process_config=video_process_config,
                env="default" # 或者根据需要传递环境参数
            )
            self.logger.info("NBA 服务初始化成功。")
            return service
        except InitializationError as e:
            # 捕获并记录核心初始化错误
            self.logger.error(f"NBA 服务核心初始化失败: {e}", exc_info=True)
            return None # 返回 None 表示失败
        except Exception as e:
            # 捕获其他意外错误
            self.logger.error(f"初始化 NBA 服务时发生意外错误: {e}", exc_info=True)
            return None # 返回 None 表示失败

    def _init_ai_service(self, context_preparer: AIContextPreparer) -> Optional[AIService]:
        """
        初始化 AI 服务 (核心)。

        Args:
            context_preparer (AIContextPreparer): 已初始化的 AI 上下文准备器实例。

        Returns:
            Optional[AIService]: 初始化成功则返回 AI 服务实例，否则返回 None。
        """
        if not context_preparer: # 检查依赖
             self.logger.error("AI 上下文准备器不可用，无法初始化 AI 服务。")
             return None
        try:
            self.logger.info("初始化 AI 服务 (核心)...")
            # AI 服务配置
            ai_config = AIConfig()
            # 从 Preparer 获取 GameDataService
            game_data_service = context_preparer.game_data_service

            # 创建 AI 服务实例
            ai_service = AIService(
                game_data_service=game_data_service, # 传递 GameDataService
                ai_config=ai_config
            )
            # 将 Preparer 实例关联到 AIService (如果 AIService 内部需要直接访问)
            ai_service.context_preparer = context_preparer

            self.logger.info("AI 服务 (核心) 初始化成功。")
            return ai_service
        except Exception as e:
            # 捕获初始化过程中的任何错误
            self.logger.error(f"初始化 AI 服务 (核心) 失败: {e}", exc_info=True)
            return None # 返回 None 表示失败

    def _init_weibo_service(self) -> Optional[WeiboPostService]:
        """初始化微博发布服务。"""
        try:
            self.logger.info("初始化微博发布服务...")
            # 创建微博服务实例
            weibo_service = WeiboPostService() # Cookie 会从环境变量或构造函数参数获取
            self.logger.info("微博发布服务初始化成功。")
            return weibo_service
        except ValueError as e:
            # 捕获配置错误 (例如缺少 Cookie)
             self.logger.error(f"微博服务初始化失败 (配置问题): {e}")
             # 向用户显示更友好的提示
             print(f"错误: 微博服务初始化失败 - {e}")
             print("请检查 WB_COOKIES 环境变量是否已设置。")
             return None # 返回 None 表示失败
        except Exception as e:
            # 捕获其他意外错误
            self.logger.error(f"初始化微博发布服务失败: {e}", exc_info=True)
            return None # 返回 None 表示失败

    def get_service(self, name: str) -> Optional[Any]:
        """
        获取一个已成功初始化的服务实例。

        Args:
            name (str): 服务的名称 (例如 'nba_service', 'ai_service', 'ai_context_preparer', 'weibo_service')。

        Returns:
            Optional[Any]: 如果服务已成功初始化，则返回服务实例；否则返回 None。
        """
        # 检查指定名称的服务是否已成功初始化
        if self._service_status.get(name, False):
             # 如果成功初始化，从字典中获取并返回服务实例
             return self._services.get(name)
        # 如果服务未成功初始化或不存在，记录警告并返回 None
        # 注意：对于非必需服务（如 AI, Weibo），在某些模式下未初始化是正常的，所以不总是记录警告
        # self.logger.warning(f"尝试访问未成功初始化的服务: {name}")
        return None

    def close_services(self) -> None:
        """关闭所有已管理的服务，释放资源。"""
        self.logger.info("开始关闭服务...")
        # 定义推荐的关闭顺序（通常与初始化顺序相反）
        close_order = ['weibo_service', 'ai_service', 'ai_context_preparer', 'nba_service']
        for service_name in close_order:
            # 获取服务实例
            service = self._services.get(service_name)
            # 检查服务实例是否存在，并且是否有 close 方法
            if service and hasattr(service, 'close') and callable(service.close):
                try:
                    self.logger.debug(f"正在关闭服务: {service_name}")
                    # 调用服务的 close 方法
                    service.close()
                    self.logger.info(f"服务 {service_name} 已关闭。")
                except Exception as e:
                    # 记录关闭过程中可能发生的错误
                    self.logger.error(f"关闭服务 {service_name} 时出错: {e}", exc_info=True)
        self.logger.info("服务关闭流程完成。")

    def _needs_ai_service(self) -> bool:
        """检查当前运行模式是否需要 AI 服务（用于内容生成）。"""
        # AI 分析模式和所有需要发布内容的微博模式都需要完整的 AI 服务
        return self.config.mode in RunMode.get_ai_modes()

    def _needs_weibo_service(self) -> bool:
        """检查当前运行模式是否需要微博发布服务。"""
        # 只有在微博相关模式下，并且没有通过 --no-weibo 命令行参数禁用时，才需要微博服务
        return self.config.mode in RunMode.get_weibo_modes() and not self.config.no_weibo


# ============3. 应用上下文 (Singleton Implementation)===============
class AppContext:
    """管理 NBACommandLineApp 的单例实例"""
    _instance: Optional['NBACommandLineApp'] = None

    @classmethod
    def get_instance(cls, config: Optional[AppConfig] = None) -> 'NBACommandLineApp':
        """获取或创建 NBACommandLineApp 的唯一实例"""
        if cls._instance is None:
            if config is None:
                raise ValueError("首次获取 AppContext 实例时必须提供 AppConfig")
            cls._instance = NBACommandLineApp(config)
        return cls._instance

    @classmethod
    def _reset_for_testing(cls): # Helper for potential tests
         cls._instance = None


# ============4. 主应用类===============

class NBACommandLineApp:
    """NBA 数据服务命令行应用程序"""
    _game_data_cache: Optional[Any] = None # 缓存获取的原始 Game 对象
    _prepared_data_cache: Dict[str, Dict[str, Any]] = {} # 基于 game/player id 键缓存准备好的结构化数据
    _team_id_cache: Dict[str, Optional[int]] = {} # 缓存球队名称到 ID 的映射
    _player_id_cache: Dict[str, Optional[Union[int, List[Dict[str, Any]]]]] = {} # 缓存球员名称到 ID 或候选列表的映射

    def __init__(self, config: AppConfig):
        """
        初始化 NBA 命令行应用程序。

        Args:
            config (AppConfig): 应用程序配置对象。
        """
        self.config = config
        # 获取或创建日志记录器
        self.logger = AppLogger.get_logger("NBAApp", app_name='nba')
        # 根据配置设置日志级别
        self._setup_logging()
        self.logger.info(f"=== NBA数据服务程序启动 (模式: {config.mode.value}) ===")
        self.logger.debug(f"应用程序配置: {config}")

        # 加载环境变量
        self._load_environment()

        # 初始化服务管理器
        self.service_manager = ServiceManager(config, self.logger)

        # 服务实例将在 _init_services 中初始化
        self.nba_service: Optional[NBAService] = None
        self.ai_service: Optional[AIService] = None
        self.weibo_service: Optional[WeiboPostService] = None
        self.ai_context_preparer: Optional[AIContextPreparer] = None # AI 上下文准备器

        # 用于在命令之间共享状态或结果的属性
        self.video_paths: Dict[str, Path] = {} # 存储生成的视频文件路径
        self.chart_paths: Dict[str, Path] = {} # 存储生成的图表文件路径
        self.round_gifs: Dict[str, Path] = {} # 存储生成的回合 GIF 文件路径

    def _setup_logging(self):
        """根据配置设置日志级别。"""
        # 如果 debug 模式开启，设置为 DEBUG 级别，否则为 INFO
        level = logging.DEBUG if self.config.debug else logging.INFO
        self.logger.setLevel(level)
        # 确保所有处理器也设置了正确的级别
        for handler in self.logger.handlers:
            handler.setLevel(level)
        if self.config.debug:
            self.logger.debug("调试日志已启用。")

    def _load_environment(self) -> None:
        """从 .env 文件加载环境变量。"""
        # 查找并加载 .env 文件 (usecwd=True 表示从当前工作目录开始查找)
        loaded_path = load_dotenv(find_dotenv(usecwd=True))
        if loaded_path:
            self.logger.info(f"已从 {loaded_path} 加载环境变量。")
        else:
            self.logger.warning("未找到 .env 文件，将依赖系统环境变量。")
        # 尝试设置控制台输出编码为 UTF-8，以防止乱码
        try:
            if sys.stdout.encoding != 'utf-8':
                 sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
            if sys.stderr.encoding != 'utf-8':
                 sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)
        except Exception as e:
             self.logger.warning(f"设置 stdout/stderr 编码为 UTF-8 时出错: {e}")

    def _init_services(self):
        """使用服务管理器初始化所有必需的服务。"""
        self.service_manager.init_services()
        # 获取初始化后的服务实例引用
        self.nba_service = self.service_manager.get_service('nba_service')
        self.ai_service = self.service_manager.get_service('ai_service') # 在某些模式下可能为 None
        self.weibo_service = self.service_manager.get_service('weibo_service') # 在某些模式下可能为 None
        self.ai_context_preparer = self.service_manager.get_service('ai_context_preparer') # 获取准备器

        # 关键检查：确保核心 NBA 服务已成功初始化
        if not self.nba_service:
             raise InitializationError("核心 NBA 服务未能初始化，无法继续。")

        # 检查数据库状态 (仅在非同步模式下提示用户)
        if self.config.mode not in RunMode.get_sync_modes():
             self._check_database_status()

        # 检查 AI 上下文准备器状态（Info 等模式需要）
        if not self.ai_context_preparer:
            self.logger.warning("AI 上下文准备器未能初始化，Info 命令可能无法显示完整数据。")

    def _check_database_status(self) -> None:
        """检查数据库状态并向用户提供相关提示。"""
        # 确保核心服务和数据服务可用
        if not self.nba_service or not self.nba_service.data_service or not self.nba_service.data_service.db_service:
            self.logger.warning("数据服务或数据库服务不可用，无法检查状态。")
            return

        db_service = self.nba_service.data_service.db_service
        try:
            # 检查核心数据库 (nba.db) 是否为空
            if db_service._is_nba_database_empty():
                print("\n提示: 检测到核心数据库 (nba.db) 为空。")
                print("      程序将尝试在首次运行时自动同步核心数据。")
                print("      如果失败，请运行 'python main.py --mode sync-new-season --force-update'")
            # 检查统计数据库 (game.db) 的同步进度
            progress = db_service.get_sync_progress()
            if progress and "error" not in progress:
                remaining = progress.get("remaining_games", 0)
                if remaining > 0:
                    print(f"\n提示: 统计数据库 (game.db) 尚有 {remaining} 场比赛未同步。")
                    print("      建议运行 'python main.py --mode sync' 来更新。")
                elif progress.get("total_games", 0) > 0:
                    # 只有当总比赛数大于0时才显示“已同步”
                    print("\n✓ 统计数据库 (game.db) 数据已同步。")
            elif progress and "error" in progress:
                 # 如果获取进度出错，记录警告
                 self.logger.warning(f"检查统计数据库进度时出错: {progress['error']}")

        except Exception as e:
            # 捕获检查过程中可能发生的任何其他错误
            self.logger.warning(f"检查数据库状态时出错: {e}", exc_info=True)

    # --- 数据访问器方法 (带缓存) ---

    def get_game_data(self) -> Optional[Any]:
        """
        获取并缓存当前配置指定的比赛数据 (原始 Game 对象)。
        如果缓存中存在，则直接返回；否则调用 NBAService 获取。

        Returns:
            Optional[Any]: 比赛数据对象 (Game Model) 或 None (如果获取失败)。

        Raises:
            ServiceNotAvailableError: 如果 NBA 服务不可用。
            DataFetchError: 如果在获取数据过程中发生错误。
        """
        # 如果缓存为空
        if self._game_data_cache is None:
            self.logger.debug(f"缓存未命中，获取比赛数据 (球队: {self.config.team}, 日期: {self.config.date})...")
            # 确保 NBA 服务已初始化
            if not self.nba_service: raise ServiceNotAvailableError("NBA 服务")
            try:
                # 调用 NBA 服务获取比赛数据
                game = self.nba_service.get_game(self.config.team, date=self.config.date, force_update=self.config.force_update)
                if not game:
                    # 如果未找到比赛，记录错误并提示用户
                    self.logger.error(f"未能获取球队 '{self.config.team}' 在日期 '{self.config.date}' 的比赛数据。")
                    print(f"× 获取比赛数据失败: 未找到球队 '{self.config.team}' 在日期 '{self.config.date}' 的比赛。")
                    print("  请检查球队名称/日期或运行同步命令。")
                    return None # 返回 None 表示未找到
                # 将获取到的数据存入缓存
                self._game_data_cache = game
            except Exception as e:
                # 捕获获取过程中的错误
                self.logger.error(f"获取比赛数据时发生错误: {e}", exc_info=True)
                print(f"× 获取比赛数据时出错: {e}")
                # 抛出特定异常，以便上层可以处理
                raise DataFetchError(f"获取比赛数据失败: {e}")
        else:
             # 如果缓存命中，直接返回
             self.logger.debug("从缓存获取比赛数据。")
        return self._game_data_cache

    def get_prepared_data(self, game_id: str, team_id: Optional[int] = None, player_id: Optional[int] = None) -> Dict[str, Any]:
        """
        获取并缓存准备好的结构化数据 (用于 AI 上下文或 Info 显示)。
        此方法现在直接使用 AIContextPreparer。

        Args:
            game_id (str): 比赛的唯一 ID。
            team_id (Optional[int]): 目标球队的 ID (可选)。
            player_id (Optional[int]): 目标球员的 ID (可选)。

        Returns:
            Dict[str, Any]: 包含结构化数据的字典，如果准备失败则可能包含 'error' 键。
        """
        # 创建缓存键，包含所有影响数据准备的参数
        cache_key = f"game:{game_id}_team:{team_id}_player:{player_id}"
        # 检查缓存
        if cache_key not in self._prepared_data_cache:
            self.logger.debug(f"缓存未命中，准备结构化数据 (Key: {cache_key})...")
            # 确保 AI 上下文准备器可用
            if not self.ai_context_preparer:
                 self.logger.error("AI 上下文准备器不可用，无法准备数据。")
                 # 返回包含错误信息的字典
                 return {"error": "AI 上下文准备器不可用"}
            try:
                # 调用准备器的方法来获取数据
                data = self.ai_context_preparer.prepare_ai_data(
                    team_id=team_id,
                    game_id=game_id,
                    player_id=player_id,
                    force_update=self.config.force_update # 根据配置决定是否强制刷新
                )
                # 将准备好的数据存入缓存
                self._prepared_data_cache[cache_key] = data
            except Exception as e:
                 # 捕获准备过程中的错误
                 self.logger.error(f"准备结构化数据时出错: {e}", exc_info=True)
                 # 在缓存中存储错误信息
                 self._prepared_data_cache[cache_key] = {"error": f"准备数据失败: {e}"}
        else:
             # 如果缓存命中，记录日志
             self.logger.debug(f"从缓存获取结构化数据 (Key: {cache_key})。")
        # 返回缓存的数据（可能是成功准备的数据，也可能是错误信息）
        return self._prepared_data_cache[cache_key]

    def get_team_id(self, team_name: str) -> Optional[int]:
        """
        获取并缓存球队 ID。

        Args:
            team_name (str): 球队的名称、缩写或城市名。

        Returns:
            Optional[int]: 如果找到唯一的球队 ID，则返回该 ID；否则返回 None。

        Raises:
            ServiceNotAvailableError: 如果 NBA 服务不可用。
        """
        # 检查缓存
        if team_name not in self._team_id_cache:
            self.logger.debug(f"缓存未命中，获取球队ID ({team_name})...")
            # 确保 NBA 服务可用
            if not self.nba_service: raise ServiceNotAvailableError("NBA 服务")
            try:
                # 调用 NBA 服务的方法获取 ID
                team_id = self.nba_service.get_team_id_by_name(team_name)
                if team_id is None:
                     # 如果未找到，打印提示信息
                     print(f"× 未找到球队 '{team_name}' 的 ID。")
                # 将结果存入缓存 (即使是 None)
                self._team_id_cache[team_name] = team_id
            except Exception as e:
                 # 捕获获取过程中的错误
                 self.logger.error(f"获取球队 ID 时出错: {e}", exc_info=True)
                 print(f"× 获取球队 ID '{team_name}' 时出错: {e}")
                 # 在缓存中存储 None 表示获取失败
                 self._team_id_cache[team_name] = None
        else:
             # 如果缓存命中，记录日志
             self.logger.debug(f"从缓存获取球队ID ({team_name})。")
        # 从缓存获取结果
        result = self._team_id_cache[team_name]
        # 确保返回的是整数或 None
        return int(result) if isinstance(result, int) else None

    def get_player_id(self, player_name: str) -> Optional[int]:
        """
        获取并缓存球员 ID，处理模糊匹配可能返回的候选列表。

        Args:
            player_name (str): 球员的名称 (可能包含球队信息，例如 "Lakers LeBron James")。

        Returns:
            Optional[int]: 如果找到唯一的球员 ID，则返回该 ID；如果找到多个候选或未找到，则返回 None。

        Raises:
            ServiceNotAvailableError: 如果 NBA 服务不可用。
        """
        # 检查缓存
        if player_name not in self._player_id_cache:
            self.logger.debug(f"缓存未命中，获取球员ID ({player_name})...")
            # 确保 NBA 服务可用
            if not self.nba_service: raise ServiceNotAvailableError("NBA 服务")
            try:
                # 调用 NBA 服务的方法获取 ID (可能返回 int, list 或 None)
                result = self.nba_service.get_player_id_by_name(player_name)
                # 将结果存入缓存
                self._player_id_cache[player_name] = result
            except Exception as e:
                 # 捕获获取过程中的错误
                 self.logger.error(f"获取球员 ID 时出错: {e}", exc_info=True)
                 print(f"× 获取球员 ID '{player_name}' 时出错: {e}")
                 # 在缓存中存储 None 表示获取失败
                 self._player_id_cache[player_name] = None
        else:
             # 如果缓存命中，记录日志
             self.logger.debug(f"从缓存获取球员ID ({player_name})。")

        # 处理缓存中的结果
        result = self._player_id_cache[player_name]
        if isinstance(result, int):
             # 如果是整数，直接返回
             return result
        elif isinstance(result, list):
             # 如果是列表 (多个候选)，打印提示信息并返回 None
             print(f"× 找到多个可能的球员 '{player_name}':")
             for item in result:
                 print(f"  - ID: {item.get('id')}, 名称: {item.get('name')}, 匹配度: {item.get('score')}")
             print("  请提供更精确的名称或包含球队信息 (如 'Lakers LeBron James')。")
             return None
        else:
             # 如果是 None (未找到或获取失败)，打印提示信息并返回 None
             if result is None and player_name in self._player_id_cache: # 只有当缓存中有记录(表示确实查过)才提示未找到
                 print(f"× 未找到球员 '{player_name}' 的 ID。")
             return None

    def check_required_files_for_weibo(self, mode: RunMode) -> bool:
        """
        检查当前模式下执行微博发布所需的媒体文件（视频、图表、GIF）是否已存在或已缓存路径。

        Args:
            mode (RunMode): 当前的运行模式。

        Returns:
            bool: 如果所有必需的文件都存在，则返回 True；否则返回 False。
        """
        self.logger.info(f"检查模式 '{mode.value}' 的微博发布依赖文件...")
        required = True # 默认认为文件齐全

        # 检查球队视频 (WEIBO_TEAM 或 WEIBO 模式需要)
        if mode in [RunMode.WEIBO_TEAM, RunMode.WEIBO]:
             # 如果缓存中没有路径
             if not self.video_paths.get("team_video"):
                 print("  ! 检查球队视频文件...") # 提示用户正在检查
                 # 可以在这里添加实际的文件系统检查逻辑（如果需要）
                 # 例如:
                 # game = self.get_game_data() # 获取 game_id 等信息
                 # if game:
                 #    team_id = self.get_team_id(self.config.team)
                 #    game_id = game.game_data.game_id
                 #    expected_path = ... # 构建预期路径
                 #    if not expected_path.exists():
                 #       print("  - 缺失: 球队集锦视频 (team_video)")
                 #       required = False
                 # else: # 如果连 game 都获取不到，肯定无法发布
                 #    required = False

                 # 简化处理：如果缓存没有，就认为缺失
                 print("  - 缺失: 球队集锦视频路径未缓存 (请先运行 video 命令)")
                 required = False

        # 检查球员视频 (WEIBO_PLAYER 或 WEIBO 模式，且指定了球员时需要)
        if mode in [RunMode.WEIBO_PLAYER, RunMode.WEIBO] and self.config.player:
             if not self.video_paths.get("player_video"):
                 print("  ! 检查球员视频文件...")
                 # 简化处理
                 print("  - 缺失: 球员集锦视频路径未缓存 (请先运行 video 命令)")
                 required = False

        # 检查球员投篮图 (WEIBO_CHART 或 WEIBO 模式，且指定了球员时需要)
        if mode in [RunMode.WEIBO_CHART, RunMode.WEIBO] and self.config.player:
             if not self.chart_paths.get("player_chart"):
                 print("  ! 检查球员投篮图文件...")
                 # 简化处理
                 print("  - 缺失: 球员投篮图路径未缓存 (请先运行 chart 命令)")
                 required = False

        # 检查球队投篮图 (WEIBO_TEAM_CHART 或 WEIBO 模式需要)
        if mode in [RunMode.WEIBO_TEAM_CHART, RunMode.WEIBO]:
             if not self.chart_paths.get("team_chart"):
                 print("  ! 检查球队投篮图文件...")
                 # 简化处理
                 print("  - 缺失: 球队投篮图路径未缓存 (请先运行 chart 命令)")
                 required = False

        # 检查球员回合 GIF (WEIBO_ROUND 或 WEIBO 模式，且指定了球员时需要)
        if mode in [RunMode.WEIBO_ROUND, RunMode.WEIBO] and self.config.player:
             if not self.round_gifs: # 检查字典是否为空
                 print("  ! 检查球员回合 GIF 文件...")
                 # 简化处理
                 print("  - 缺失: 球员回合 GIF 路径未缓存 (请先运行 video-rounds 命令)")
                 required = False

        # 根据检查结果给出最终提示
        if not required:
             print("× 缺少必要的媒体文件。请先运行相应的生成命令 (chart, video, video-rounds) 或 'all' 模式。")
        else:
             self.logger.info("所需文件检查通过 (基于缓存状态)。")
        return required

    # --- 主要执行逻辑 ---

    def run(self) -> int:
        """运行应用程序的主逻辑。"""
        exit_code = 0 # 默认退出代码为 0 (成功)
        try:
            # 1. 初始化所有必需的服务
            self._init_services()

            # 2. 使用命令工厂创建与当前模式对应的命令对象
            command = NBACommandFactory.create_command(self.config.mode)
            if not command:
                # 如果找不到命令，记录错误并设置退出代码
                self.logger.error(f"无法为模式 '{self.config.mode.value}' 创建命令。")
                return 1 # 返回错误代码

            # 3. 执行命令
            self.logger.info(f"开始执行命令: {command.__class__.__name__}")
            # 将当前的 app 实例传递给命令的 execute 方法
            success = command.execute(self)
            self.logger.info(f"命令 {command.__class__.__name__} 执行 {'成功' if success else '失败'}。")
            # 如果命令执行失败，设置退出代码为 1
            if not success:
                exit_code = 1

        except InitializationError as e:
            # 捕获服务初始化期间的严重错误
            self.logger.critical(f"服务初始化失败: {e}", exc_info=False) # 不记录完整堆栈，因为信息已在日志中
            print(f"\n错误: 服务初始化失败 - {e}", file=sys.stderr)
            print("请检查配置、网络连接或依赖项。", file=sys.stderr)
            exit_code = 2 # 特定的初始化错误代码
        except DataFetchError as e:
             # 捕获关键数据获取失败的错误
             self.logger.error(f"关键数据获取失败: {e}", exc_info=True)
             print(f"\n错误: 获取关键数据失败 - {e}", file=sys.stderr)
             exit_code = 3 # 特定的数据获取错误代码
        except KeyboardInterrupt:
             # 捕获用户中断 (Ctrl+C)
             print("\n操作被用户中断。", file=sys.stderr)
             self.logger.warning("操作被用户中断。")
             exit_code = 130 # 标准的用户中断退出代码
        except Exception as e:
            # 捕获所有其他未预料到的异常
            self.logger.critical(f"应用程序发生未处理的异常: {e}", exc_info=True)
            print(f"\n发生意外错误: {e}", file=sys.stderr)
            exit_code = 1 # 通用错误代码
        finally:
             # 确保在退出前执行清理操作
             # 清理逻辑现在移到 main 函数中，在 run() 返回后执行
             pass

        # 记录最终的退出信息
        self.logger.info(f"应用程序运行结束，退出代码: {exit_code}")
        # 返回退出代码
        return exit_code

    def close(self):
        """通过服务管理器关闭所有已管理的服务，清理资源。"""
        self.service_manager.close_services()


# ============5. 入口函数===============

def setup_logging(debug: bool):
    """Configures logging based on debug flag."""
    level = logging.DEBUG if debug else logging.INFO
    logging.getLogger('nba').setLevel(level) # Set level for the 'nba' namespace logger


def parse_arguments() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="NBA 数据服务应用程序",
        formatter_class=argparse.RawTextHelpFormatter # Keep formatting in help
    )

    parser.add_argument("--team", default="Lakers", help="指定默认球队 (默认: Lakers)")
    parser.add_argument("--player", default="LeBron James", help="指定默认球员 (默认: LeBron James)")
    parser.add_argument("--date", default="last", help="比赛日期 (YYYY-MM-DD 或 'last', 默认: last)")
    parser.add_argument(
        "--mode",
        choices=[m.value for m in RunMode],
        default=RunMode.ALL.value,
        help=f"""指定运行模式 (默认: all).
可用模式:
  info: 显示比赛/球员信息
  chart: 生成半场球队/球员投篮图
  full-court-chart: 生成全场投篮图
  impact-chart: 生成球员得分影响力图
  video: 处理所有视频 (球队/球员/回合)
  video-team: 仅处理球队集锦
  video-player: 仅处理球员集锦
  video-rounds: 仅处理球员回合GIF
  ai: 显示AI生成的比赛/球员分析
  weibo: 生成并发布所有内容到微博
  weibo-team: 发布球队视频
  weibo-player: 发布球员视频
  weibo-chart: 发布球员投篮图
  weibo-team-chart: 发布球队投篮图
  weibo-round: 发布球员回合GIF
  weibo-team-rating: 发布球队赛后评级
  all: 执行 info, chart(s), video, ai (及微博,除非禁用)
  sync: 增量同步比赛统计 (gamedb)
  sync-new-season: 同步新赛季核心数据 (nba.db)
  sync-player-details: 同步球员详细信息 (nba.db)
"""
    )
    parser.add_argument("--no-weibo", action="store_true", help="禁用微博发布 (即使在 weibo* 或 all 模式下)")
    parser.add_argument("--debug", action="store_true", help="启用详细调试日志")
    parser.add_argument("--config", help="指定 .env 配置文件路径")
    parser.add_argument("--force-update", action="store_true", help="强制更新数据 (用于 sync*, sync-player-details)")
    parser.add_argument("--max-workers", type=int, default=8, help="并行同步时的最大线程数 (默认: 8)")
    parser.add_argument("--batch-size", type=int, default=50, help="并行同步时的批处理大小 (默认: 50)")

    return parser.parse_args()


def main() -> int:
    """主程序入口点"""
    # 1. Parse Arguments
    args = parse_arguments()

    # 2. Create Config
    config = AppConfig.from_args(args)

    # 3. Initialize App
    app_instance: Optional[NBACommandLineApp] = None
    exit_code = 0
    logger = None # Initialize logger variable

    try:
        # Create the app instance directly
        app_instance = NBACommandLineApp(config)
        logger = app_instance.logger # Get logger after app init

        # 4. Run the Application Logic
        exit_code = app_instance.run()

    except InitializationError as e:
         print(f"错误: 应用程序初始化失败 - {e}", file=sys.stderr)
         exit_code = 2
    except KeyboardInterrupt:
         print("\n操作被用户中断。", file=sys.stderr)
         if logger: logger.warning("操作被用户中断。")
         exit_code = 130 # Standard exit code for Ctrl+C
    except Exception as e:
         if logger:
             logger.critical(f"应用程序顶层发生未处理的异常: {e}", exc_info=True)
         print(f"\n发生严重错误: {e}", file=sys.stderr)
         exit_code = 1
    finally:
        # 5. Cleanup
        if app_instance:
             if logger: logger.info("正在执行清理...")
             app_instance.close()
             if logger: logger.info("清理完成。")

    return exit_code


if __name__ == "__main__":
    # Setup basic logging first in case App init fails
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    sys.exit(main())