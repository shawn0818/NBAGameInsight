"""NBA 数据服务主程序 - 优化精简版

实现以下核心功能：
1. 比赛基础信息查询
2. 投篮图表生成
3. 视频处理功能
4. 发布内容到微博
5. AI分析比赛数据

用法:
    python main.py [options]
"""
import argparse
import sys
import logging
from pathlib import Path
from enum import Enum
from dotenv import load_dotenv

# 导入业务逻辑函数
from nba.services.nba_service import NBAService, NBAServiceConfig, ServiceStatus
from nba.services.game_video_service import VideoConfig
from utils.video_converter import VideoProcessConfig
from utils.logger_handler import AppLogger
from utils.ai_processor import AIProcessor, AIConfig, AIProvider, AIModel
from weibo.weibo_post_service import WeiboPostService
from weibo.weibo_content_generator import WeiboContentGenerator

# 导入已抽象出的业务逻辑函数
from nba_functions import (
    get_game_info, get_game_narrative, get_events_timeline,
    generate_shot_charts, process_player_video, process_team_video,
    process_player_round_gifs, run_ai_analysis, prepare_game_data, prepare_player_data
)
from weibo_functions import (
    post_team_video, post_player_video, post_player_chart,
    post_player_rounds, post_all_content, post_team_chart
)


# 定义运行模式
class RunMode(Enum):
    """应用程序运行模式"""
    INFO = "info"  # 只显示比赛信息
    CHART = "chart"  # 只生成图表
    VIDEO = "video"  # 处理所有视频
    VIDEO_TEAM = "video-team"  # 只处理球队视频
    VIDEO_PLAYER = "video-player"  # 只处理球员视频
    VIDEO_ROUNDS = "video-rounds"  # 处理球员视频的回合GIF
    WEIBO = "weibo"  # 执行所有微博发布功能
    WEIBO_TEAM = "weibo-team"  # 只发布球队集锦视频
    WEIBO_PLAYER = "weibo-player"  # 只发布球员集锦视频
    WEIBO_CHART = "weibo-chart"  # 只发布球员投篮图
    WEIBO_TEAM_CHART = "weibo-team-chart"  # 只发布球队投篮图
    WEIBO_ROUND = "weibo-round"  # 只发布球员回合解说和GIF
    AI = "ai"  # 只运行AI分析
    ALL = "all"  # 执行所有功能


class NBAApplication:
    """NBA 数据服务应用程序类"""

    def __init__(self):
        """初始化应用程序"""
        # 设置项目根目录
        self.root_dir = Path(__file__).parent

        # 初始化日志
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.logger.info("=== NBA数据服务初始化 ===")

        # 解析命令行参数
        self.args = self._parse_arguments()

        # 设置日志级别
        if self.args.debug:
            self._set_debug_logging()

        # 加载环境变量
        self._load_environment()

        # 初始化服务
        self.nba_service = None
        self.weibo_service = None
        self.ai_processor = None
        self.content_generator = None
        self.video_paths = {}
        self.chart_paths = {}
        self.round_gifs = {}

    def _parse_arguments(self) -> argparse.Namespace:
        """解析命令行参数"""
        parser = argparse.ArgumentParser(description="NBA 数据服务应用程序")

        parser.add_argument("--team", default="Lakers", help="指定默认球队，默认为 Lakers")
        parser.add_argument("--player", default="LeBron James", help="指定默认球员，默认为 LeBron James")
        parser.add_argument("--date", default="last", help="指定比赛日期，默认为 last 表示最近一场比赛")
        parser.add_argument("--mode", choices=[m.value for m in RunMode], default=RunMode.ALL.value,
                            help="指定运行模式，默认为 all")
        parser.add_argument("--no-weibo", action="store_true", help="不发布到微博")
        parser.add_argument("--debug", action="store_true", help="启用调试模式，输出详细日志")
        parser.add_argument("--config", help="指定配置文件")

        return parser.parse_args()

    def _set_debug_logging(self) -> None:
        """设置调试级别日志"""
        for handler in logging.root.handlers + self.logger.handlers:
            handler.setLevel(logging.DEBUG)
        self.logger.setLevel(logging.DEBUG)
        self.logger.debug("调试模式已启用")

    def _load_environment(self) -> None:
        """加载环境变量"""
        # 确保系统默认使用 UTF-8 编码
        import sys
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

        # 设置 Python 默认编码为 UTF-8
        import locale
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

        # 按优先级加载环境变量
        env_local = self.root_dir / '.env.local'
        env_default = self.root_dir / '.env'
        env_config = self.args.config and Path(self.args.config)

        if env_config and env_config.exists():
            load_dotenv(env_config)
            self.logger.info(f"从 {env_config} 加载环境变量")
        elif env_local.exists():
            load_dotenv(env_local)
            self.logger.info("从 .env.local 加载环境变量")
        elif env_default.exists():
            load_dotenv(env_default)
            self.logger.info("从 .env 加载环境变量")
        else:
            self.logger.warning("未找到环境变量文件，使用默认配置")

    def init_services(self) -> None:
        """初始化所有服务"""
        try:
            # 初始化NBA服务
            self.nba_service = self._init_nba_service()
            self._verify_nba_service_status()

            # 初始化AI处理器（需要放在WeiboContentGenerator之前）
            if self._need_ai_services():
                self.ai_processor = self._init_ai_processor()

                # 初始化内容生成器（如果AI处理器可用）
                if self.ai_processor:
                    self.content_generator = WeiboContentGenerator(
                        ai_processor=self.ai_processor,
                        logger=self.logger
                    )
                    self.logger.info("微博内容生成器初始化成功")

            # 初始化微博服务
            if self._need_weibo_services():
                self.weibo_service = self._init_weibo_service()

            # 验证微博发布所需组件是否完整
            if self._need_weibo_services() and not self.args.no_weibo:
                if not self.weibo_service:
                    self.logger.warning("微博服务未初始化，将跳过发布功能")
                if not self.content_generator:
                    self.logger.warning("内容生成器未初始化，将跳过发布功能")

        except Exception as e:
            self.logger.error(f"服务初始化失败: {e}", exc_info=True)
            raise RuntimeError(f"服务初始化失败: {e}")

    def _need_ai_services(self) -> bool:
        """判断是否需要AI服务"""
        mode = RunMode(self.args.mode)
        ai_modes = [RunMode.AI, RunMode.WEIBO, RunMode.ALL,
                    RunMode.WEIBO_TEAM, RunMode.WEIBO_PLAYER,
                    RunMode.WEIBO_CHART, RunMode.WEIBO_ROUND,
                    RunMode.WEIBO_TEAM_CHART]  # 添加 WEIBO_TEAM_CHART
        return mode in ai_modes

    def _need_weibo_services(self) -> bool:
        """判断是否需要微博服务"""
        mode = RunMode(self.args.mode)
        weibo_modes = [RunMode.WEIBO, RunMode.ALL,
                       RunMode.WEIBO_TEAM, RunMode.WEIBO_PLAYER,
                       RunMode.WEIBO_CHART, RunMode.WEIBO_ROUND,
                       RunMode.WEIBO_TEAM_CHART]  # 添加 WEIBO_TEAM_CHART
        return mode in weibo_modes and not self.args.no_weibo

    def _init_nba_service(self) -> NBAService:
        """初始化 NBA 服务"""
        self.logger.info("初始化 NBA 服务...")

        # 基础配置
        nba_config = NBAServiceConfig(
            default_team=self.args.team,
            default_player=self.args.player,
            date_str=self.args.date
        )

        # 视频配置
        video_config = VideoConfig(
            quality='hd',
            chunk_size=8192
        )

        # 视频处理配置
        video_process_config = VideoProcessConfig(
            ffmpeg_path='ffmpeg',
            max_workers=3,
            gif_fps=15,
            gif_scale="480:-1"
        )

        return NBAService(
            config=nba_config,
            video_config=video_config,
            video_process_config=video_process_config
        )

    def _verify_nba_service_status(self) -> None:
        """验证关键服务状态"""
        if not self.nba_service:
            raise RuntimeError("NBA 服务未初始化")

        critical_services = {
            'data': "数据服务",
            'videodownloader': "视频服务",
            'video_processor': "视频处理器",
            'chart': "图表服务"
        }

        for service_name, display_name in critical_services.items():
            status = self.nba_service._service_status.get(service_name)
            if status:
                if status.status == ServiceStatus.AVAILABLE:
                    self.logger.info(f"{display_name}初始化成功")
                else:
                    self.logger.error(f"{display_name}初始化失败: {status.error_message}")
                    raise RuntimeError(f"{display_name}初始化失败")

    def _init_weibo_service(self):
        """初始化微博发布服务"""
        self.logger.info("初始化微博发布服务...")
        try:
            weibo_service = WeiboPostService()  # 从环境变量获取cookie
            self.logger.info("微博发布服务初始化成功")
            return weibo_service
        except Exception as e:
            self.logger.error(f"微博发布服务初始化失败: {e}")
            return None

    def _init_ai_processor(self):
        """初始化AI处理器"""
        self.logger.info("初始化AI处理器...")
        try:
            # 创建AI配置
            ai_config = AIConfig(
                provider=AIProvider.DEEPSEEK,
                model=AIModel.DEEPSEEK_CHAT,
                enable_translation=True,
                enable_creation=True
            )

            # 初始化AI处理器
            ai_processor = AIProcessor(ai_config)
            self.logger.info("AI处理器初始化成功")
            return ai_processor
        except Exception as e:
            self.logger.error(f"AI处理器初始化失败: {e}")
            return None

    def run(self) -> int:
        """运行应用程序"""
        try:
            # 初始化服务
            self.init_services()

            # 根据模式运行特定功能
            mode = RunMode(self.args.mode)
            self.logger.info(f"以 {mode.value} 模式运行应用程序")

            # 运行指定功能
            self._execute_mode_functions(mode)

            self.logger.info("=== 应用程序运行完成 ===")
            return 0

        except Exception as e:
            self.logger.error(f"应用程序运行失败: {e}", exc_info=True)
            print(f"\n应用程序运行失败: {e}\n请查看日志获取详细信息")
            return 1

        finally:
            self.cleanup()

    def _check_required_files_for_weibo(self, mode) -> bool:
        """检查微博发布所需的文件是否存在"""
        # 初始化检查结果
        result = True

        # 查找已有的视频和图表文件
        if mode in (RunMode.WEIBO, RunMode.WEIBO_TEAM) and "team_video" not in self.video_paths:
            # 检查是否已经有球队视频
            video_dir = self.nba_service.video_service.config.output_dir
            team_video = list(video_dir.glob(f"highlight_*.mp4"))
            if team_video:
                self.video_paths["team_video"] = team_video[0]
                print(f"√ 找到球队集锦视频: {team_video[0]}")
            else:
                print("× 未找到球队集锦视频，请先运行 --mode video-team 生成视频")
                result = False

        if mode in (RunMode.WEIBO, RunMode.WEIBO_PLAYER) and "player_video" not in self.video_paths:
            # 检查是否已经有球员视频
            video_dir = self.nba_service.video_service.config.output_dir
            player_id = self.nba_service.get_player_id_by_name(self.args.player)
            player_video = list(video_dir.glob(f"player_highlight_{player_id}.mp4"))
            if player_video:
                self.video_paths["player_video"] = player_video[0]
                print(f"√ 找到球员集锦视频: {player_video[0]}")
            else:
                print("× 未找到球员集锦视频，请先运行 --mode video-player 生成视频")
                result = False

        if mode in (RunMode.WEIBO, RunMode.WEIBO_CHART) and "player_chart" not in self.chart_paths:
            # 使用正确的图表目录路径
            storage_dir = self.root_dir / "storage" / "pictures"
            player_id = self.nba_service.get_player_id_by_name(self.args.player)
            player_chart = list(storage_dir.glob(f"scoring_impact_*_{player_id}.png"))
            if player_chart:
                self.chart_paths["player_chart"] = player_chart[0]
                print(f"√ 找到球员投篮图: {player_chart[0]}")
            else:
                print("× 未找到球员投篮图，请先运行 --mode chart 生成图表")
                result = False

        # 新增对球队投篮图的检查
        if mode in (
        RunMode.WEIBO, RunMode.WEIBO_CHART, RunMode.WEIBO_TEAM_CHART) and "team_chart" not in self.chart_paths:
            storage_dir = self.root_dir / "storage" / "pictures"
            team_id = self.nba_service.get_team_id_by_name(self.args.team)
            team_chart = list(storage_dir.glob(f"team_shots_*_{team_id}.png"))
            if team_chart:
                self.chart_paths["team_chart"] = team_chart[0]
                print(f"√ 找到球队投篮图: {team_chart[0]}")
            else:
                print("× 未找到球队投篮图，请先运行 --mode chart 生成图表")
                result = False

        return result

    def _execute_mode_functions(self, mode):
        """根据模式执行相应功能"""
        # 信息查询功能
        if mode in (RunMode.INFO, RunMode.ALL):
            self._run_info_functions()

        # 图表功能
        if mode in (RunMode.CHART, RunMode.ALL):
            self._run_chart_functions()

        # 视频功能
        self._run_video_functions(mode)

        # 微博发布功能
        if not self.args.no_weibo:
            self._run_weibo_functions(mode)

        # AI分析功能
        if mode in (RunMode.AI, RunMode.ALL) and self.ai_processor:
            self._run_ai_functions()

    def _run_info_functions(self):
        """运行信息查询相关功能"""
        # 获取比赛基本信息
        get_game_info(self.nba_service, self.ai_processor, self.content_generator)

        # 获取比赛详细叙述
        get_game_narrative(self.nba_service, self.args.player, self.ai_processor)

        # 获取比赛事件时间线
        get_events_timeline(self.nba_service, self.args.team, self.args.player)

    def _run_chart_functions(self):
        """运行图表生成功能"""
        self.chart_paths = generate_shot_charts(self.nba_service, self.args.team, self.args.player)

    def _run_video_functions(self, mode):
        """运行视频处理功能"""
        if mode == RunMode.VIDEO:
            # 处理所有视频
            self.video_paths.update(process_team_video(self.nba_service, self.args.team))
            self.video_paths.update(process_player_video(self.nba_service, self.args.player))
        elif mode == RunMode.VIDEO_TEAM:
            # 只处理球队视频
            self.video_paths.update(process_team_video(self.nba_service, self.args.team))
        elif mode == RunMode.VIDEO_PLAYER:
            # 只处理球员视频
            self.video_paths.update(process_player_video(self.nba_service, self.args.player))
        elif mode == RunMode.VIDEO_ROUNDS:
            # 处理球员视频回合GIF
            self.round_gifs = process_player_round_gifs(self.nba_service, self.args.player)
        elif mode == RunMode.ALL:
            # ALL 模式下处理所有视频和GIF
            self.video_paths.update(process_team_video(self.nba_service, self.args.team))
            self.video_paths.update(process_player_video(self.nba_service, self.args.player))
            self.round_gifs = process_player_round_gifs(self.nba_service, self.args.player)

    def _run_weibo_functions(self, mode):
        """运行微博发布功能"""
        # 先检查是否存在所需文件
        if not self._check_required_files_for_weibo(mode):
            print("× 微博发布所需文件不存在，请先生成相应文件")
            return

        if mode == RunMode.WEIBO:
            # 执行所有微博发布功能
            post_all_content(self.nba_service, self.weibo_service, self.content_generator,
                             self.video_paths, self.chart_paths, self.args.player)
        elif mode == RunMode.WEIBO_TEAM:
            # 只发布球队集锦视频
            game_data = prepare_game_data(self.nba_service, self.args.team)
            if game_data and "team_video" in self.video_paths:
                post_team_video(self.weibo_service, self.content_generator,
                                self.video_paths["team_video"], game_data)
        elif mode == RunMode.WEIBO_PLAYER:
            # 只发布球员集锦视频
            player_data = prepare_player_data(self.nba_service, self.args.player)
            if player_data and "player_video" in self.video_paths:
                post_player_video(self.weibo_service, self.content_generator,
                                  self.video_paths["player_video"], player_data, self.args.player)
        elif mode == RunMode.WEIBO_CHART:
            # 只发布球员投篮图
            player_data = prepare_player_data(self.nba_service, self.args.player)
            if player_data and "player_chart" in self.chart_paths:
                post_player_chart(self.weibo_service, self.content_generator,
                                  self.chart_paths["player_chart"], player_data, self.args.player)
        elif mode == RunMode.WEIBO_TEAM_CHART:
            # 只发布球队投篮图
            game_data = prepare_game_data(self.nba_service, self.args.team)
            if game_data and "team_chart" in self.chart_paths:
                post_team_chart(self.weibo_service, self.content_generator,
                                self.chart_paths["team_chart"], game_data, self.args.team)
        elif mode == RunMode.WEIBO_ROUND:
            # 只发布球员回合解说和GIF
            player_data = prepare_player_data(self.nba_service, self.args.player)
            if player_data:
                post_player_rounds(self.weibo_service, self.content_generator,
                                   self.round_gifs, player_data, self.args.player, self.nba_service)

    def _run_ai_functions(self):
        """运行AI分析功能"""
        run_ai_analysis(self.nba_service, self.args.team, self.args.player,
                        self.ai_processor, self.content_generator)

    def cleanup(self) -> None:
        """清理资源，关闭所有服务"""
        if self.nba_service:
            try:
                self.nba_service.close()
                self.logger.info("NBA 服务已关闭")
            except Exception as e:
                self.logger.error(f"关闭 NBA 服务时发生错误: {e}")

        if self.weibo_service:
            try:
                self.weibo_service.close()
                self.logger.info("微博服务已关闭")
            except Exception as e:
                self.logger.error(f"关闭微博服务时发生错误: {e}")

        if self.ai_processor:
            try:
                if hasattr(self.ai_processor, 'close') and callable(self.ai_processor.close):
                    self.ai_processor.close()
                self.logger.info("AI处理器已关闭")
            except Exception as e:
                self.logger.error(f"关闭AI处理器时发生错误: {e}")

        self.logger.info("=== 服务结束 ===")


def main() -> int:
    """主程序入口"""
    app = NBAApplication()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())