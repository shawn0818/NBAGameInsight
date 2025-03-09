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

# 导入业务逻辑函数和服务
from nba.services.nba_service import NBAService, NBAServiceConfig, ServiceStatus
from nba.services.game_video_service import VideoConfig
from utils.video_converter import VideoProcessConfig
from utils.logger_handler import AppLogger
from utils.ai_processor import AIProcessor, AIConfig, AIProvider, AIModel
from weibo.weibo_post_service import WeiboPostService
from weibo.weibo_content_generator import WeiboContentGenerator


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

            # 初始化微博服务，并传入内容生成器
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
                    RunMode.WEIBO_TEAM_CHART]
        return mode in ai_modes

    def _need_weibo_services(self) -> bool:
        """判断是否需要微博服务"""
        mode = RunMode(self.args.mode)
        weibo_modes = [RunMode.WEIBO, RunMode.ALL,
                       RunMode.WEIBO_TEAM, RunMode.WEIBO_PLAYER,
                       RunMode.WEIBO_CHART, RunMode.WEIBO_ROUND,
                       RunMode.WEIBO_TEAM_CHART]
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
        video_config = VideoConfig()

        # 视频处理配置
        video_process_config = VideoProcessConfig()

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
            # 初始化时传入内容生成器
            weibo_service = WeiboPostService(content_generator=self.content_generator)
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
            ai_config = AIConfig()

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

        # 获取基础信息
        team_id = self.nba_service.get_team_id_by_name(self.args.team)
        player_id = self.nba_service.get_player_id_by_name(self.args.player)
        game = self.nba_service.data_service.get_game(self.args.team)
        game_id = game.game_data.game_id if game else None

        if not game_id:
            print("× 未找到比赛数据")
            return False

        # 查找已有的视频和图表文件
        if mode in (RunMode.WEIBO, RunMode.WEIBO_TEAM) and "team_video" not in self.video_paths:
            # 检查是否已经有球队视频
            team_video_dir = NBAConfig.PATHS.VIDEO_DIR / "team_videos" / f"team_{team_id}_{game_id}"
            if team_video_dir.exists():
                team_video = list(team_video_dir.glob(f"team_{team_id}_{game_id}.mp4"))
                if team_video:
                    self.video_paths["team_video"] = team_video[0]
                    print(f"√ 找到球队集锦视频: {team_video[0]}")
                else:
                    print("× 未找到球队集锦视频，请先运行 --mode video-team 生成视频")
                    result = False
            else:
                print("× 未找到球队视频目录，请先运行 --mode video-team 生成视频")
                result = False

        if mode in (RunMode.WEIBO, RunMode.WEIBO_PLAYER) and "player_video" not in self.video_paths:
            # 检查是否已经有球员视频
            player_video_dir = NBAConfig.PATHS.VIDEO_DIR / "player_videos" / f"player_{player_id}_{game_id}"
            if player_video_dir.exists():
                player_video = list(player_video_dir.glob(f"player_{player_id}_{game_id}.mp4"))
                if player_video:
                    self.video_paths["player_video"] = player_video[0]
                    print(f"√ 找到球员集锦视频: {player_video[0]}")
                else:
                    print("× 未找到球员集锦视频，请先运行 --mode video-player 生成视频")
                    result = False
            else:
                print("× 未找到球员视频目录，请先运行 --mode video-player 生成视频")
                result = False

        if mode in (RunMode.WEIBO, RunMode.WEIBO_CHART) and "player_chart" not in self.chart_paths:
            # 使用正确的图表目录路径
            storage_dir = NBAConfig.PATHS.PICTURES_DIR
            player_chart = list(storage_dir.glob(f"scoring_impact_{game_id}_{player_id}.png"))
            if player_chart:
                self.chart_paths["player_chart"] = player_chart[0]
                print(f"√ 找到球员投篮图: {player_chart[0]}")
            else:
                print("× 未找到球员投篮图，请先运行 --mode chart 生成图表")
                result = False

        # 检查球队投篮图
        if mode in (RunMode.WEIBO, RunMode.WEIBO_TEAM_CHART) and "team_chart" not in self.chart_paths:
            storage_dir = NBAConfig.PATHS.PICTURES_DIR
            team_chart = list(storage_dir.glob(f"team_shots_{game_id}_{team_id}.png"))
            if team_chart:
                self.chart_paths["team_chart"] = team_chart[0]
                print(f"√ 找到球队投篮图: {team_chart[0]}")
            else:
                print("× 未找到球队投篮图，请先运行 --mode chart 生成图表")
                result = False

        # 检查球员回合GIF
        if mode in (RunMode.WEIBO, RunMode.WEIBO_ROUND) and not self.round_gifs:
            # 检查是否已经有球员回合GIF
            gif_dir = NBAConfig.PATHS.GIF_DIR / f"player_{player_id}_{game_id}_rounds"
            if gif_dir.exists():
                gifs = list(gif_dir.glob(f"round_*_{player_id}.gif"))
                if gifs:
                    # 将找到的GIF添加到round_gifs字典中
                    for gif in gifs:
                        match = re.search(r'round_(\d+)_', gif.name)
                        if match:
                            event_id = match.group(1)
                            self.round_gifs[event_id] = gif
                    print(f"√ 找到 {len(self.round_gifs)} 个球员回合GIF")
                else:
                    print("× 未找到球员回合GIF，请先运行 --mode video-rounds 生成GIF")
                    result = False
            else:
                print("× 未找到球员回合GIF目录，请先运行 --mode video-rounds 生成GIF")
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
        print("\n=== 比赛基本信息 ===")

        # 获取比赛数据
        game_data = self.nba_service.data_service.get_game(self.nba_service.config.default_team)
        if not game_data:
            print(f"  获取比赛信息失败")
            return

        ai_data = game_data.prepare_ai_data()
        if "error" in ai_data:
            print(f"  获取AI友好数据失败: {ai_data['error']}")
            return

        # 显示比赛基本信息
        if "game_info" in ai_data:
            info = ai_data["game_info"]
            print("\n比赛信息:")
            print(f"  比赛ID: {info.get('game_id', 'N/A')}")
            print(
                f"  对阵: {info.get('teams', {}).get('away', {}).get('full_name', 'N/A')} vs {info.get('teams', {}).get('home', {}).get('full_name', 'N/A')}")
            print(f"  日期: {info.get('date', {}).get('beijing', 'N/A')}")
            print(f"  时间: {info.get('date', {}).get('time_beijing', 'N/A')}")
            print(f"  场馆: {info.get('arena', {}).get('full_location', 'N/A')}")

        # 显示比赛状态信息
        if "game_status" in ai_data:
            status = ai_data["game_status"]
            print("\n比赛状态:")
            print(f"  当前状态: {status.get('status', 'N/A')}")
            print(f"  当前节数: {status.get('period', {}).get('name', 'N/A')}")
            print(f"  剩余时间: {status.get('time_remaining', 'N/A')}")
            print(
                f"  比分: {status.get('score', {}).get('away', {}).get('team', 'N/A')} {status.get('score', {}).get('away', {}).get('points', 0)} - {status.get('score', {}).get('home', {}).get('team', 'N/A')} {status.get('score', {}).get('home', {}).get('points', 0)}")

        # 如果比赛已结束，显示比赛结果
        if "game_result" in ai_data and ai_data["game_result"]:
            result = ai_data["game_result"]
            print("\n比赛结果:")
            print(f"  最终比分: {result.get('final_score', 'N/A')}")
            print(
                f"  获胜方: {result.get('winner', {}).get('team_name', 'N/A')} ({result.get('winner', {}).get('score', 0)}分)")
            print(
                f"  失利方: {result.get('loser', {}).get('team_name', 'N/A')} ({result.get('loser', {}).get('score', 0)}分)")
            print(f"  分差: {result.get('score_difference', 0)}分")
            print(f"  观众数: {result.get('attendance', {}).get('count', 'N/A')}")
            print(f"  比赛时长: {result.get('duration', 'N/A')}分钟")

        # 使用内容生成器生成摘要
        if self.content_generator:
            try:
                summary = self.content_generator.generate_game_summary(ai_data)
                if summary:
                    print("\nAI比赛摘要:")
                    print(f"  {summary}")
            except Exception as e:
                logging.warning(f"AI摘要生成失败: {e}")

        # 获取球员数据
        if self.args.player:
            print(f"\n=== {self.args.player} 球员详细数据 ===")
            player_id = self.nba_service.get_player_id_by_name(self.args.player)
            if player_id:
                player_data = game_data.prepare_ai_data(player_id=player_id)

                if "player_stats" in player_data:
                    player_found = False
                    for team_type in ["home", "away"]:
                        for player in player_data["player_stats"].get(team_type, []):
                            if player["basic"]["name"].lower() == self.args.player.lower():
                                player_found = True
                                basic = player["basic"]
                                print(f"\n{basic['name']} 基本数据:")
                                print(
                                    f"  位置: {basic.get('position', 'N/A')} | 球衣号: {basic.get('jersey_num', 'N/A')}")
                                print(
                                    f"  上场时间: {basic.get('minutes', 'N/A')} | 首发/替补: {basic.get('starter', 'N/A')}")
                                print(
                                    f"  得分: {basic.get('points', 0)} | 篮板: {basic.get('rebounds', 0)} | 助攻: {basic.get('assists', 0)}")
                                print(f"  +/-: {basic.get('plus_minus', 0)}")

                                shooting = player.get("shooting", {})
                                print("\n投篮数据:")
                                fg = shooting.get("field_goals", {})
                                print(
                                    f"  投篮: {fg.get('made', 0)}/{fg.get('attempted', 0)} ({fg.get('percentage', 0)}%)")
                                three = shooting.get("three_pointers", {})
                                print(
                                    f"  三分: {three.get('made', 0)}/{three.get('attempted', 0)} ({three.get('percentage', 0)}%)")
                                ft = shooting.get("free_throws", {})
                                print(
                                    f"  罚球: {ft.get('made', 0)}/{ft.get('attempted', 0)} ({ft.get('percentage', 0)}%)")

                                other = player.get("other_stats", {})
                                print("\n其他数据:")
                                print(f"  抢断: {other.get('steals', 0)} | 盖帽: {other.get('blocks', 0)}")
                                print(
                                    f"  失误: {other.get('turnovers', 0)} | 个人犯规: {other.get('fouls', {}).get('personal', 0)}")
                                break
                    if not player_found:
                        print(f"  未找到 {self.args.player} 的数据")
                else:
                    print(f"  未能获取 {self.args.player} 的球员数据")
            else:
                print(f"  未找到球员 {self.args.player}")

        # 显示事件时间线
        events = self.nba_service.get_events_timeline(self.args.team, self.args.player)
        if events:
            print("\n=== 比赛事件时间线 ===")
            print(f"\n共获取到 {len(events)} 个事件")

            # 按事件类型分类
            events_by_type = {}
            for event in events:
                event_type = event.get("action_type", "unknown")
                if event_type not in events_by_type:
                    events_by_type[event_type] = []
                events_by_type[event_type].append(event)

            # 统计事件类型
            print("\n事件类型统计:")
            for event_type, event_list in sorted(events_by_type.items(), key=lambda x: len(x[1]), reverse=True):
                print(f"  {event_type}: {len(event_list)}个")

            # 显示重要得分事件
            if "2pt" in events_by_type or "3pt" in events_by_type:
                print("\n重要得分事件:")
                scoring_events = []
                if "2pt" in events_by_type:
                    scoring_events.extend(events_by_type["2pt"])
                if "3pt" in events_by_type:
                    scoring_events.extend(events_by_type["3pt"])

                made_shots = [e for e in scoring_events if e.get("shot_result") == "Made"]
                important_shots = sorted(made_shots, key=lambda x: (x.get("period", 0), x.get("clock", "")))[:10]

                for i, event in enumerate(important_shots, 1):
                    period = event.get("period", "")
                    clock = event.get("clock", "")
                    action_type = event.get("action_type", "")
                    player_name = event.get("player_name", "未知球员")
                    shot_distance = event.get("shot_distance", "")
                    score_home = event.get("score_home", "")
                    score_away = event.get("score_away", "")
                    score = f"{score_away} - {score_home}" if score_away and score_home else "未知"

                    description = f"{player_name} {shot_distance}英尺 "
                    if action_type == "3pt":
                        description += "三分球"
                    else:
                        description += "两分球"

                    if "assist_person_id" in event and event["assist_person_id"]:
                        assist_name = event.get("assist_player_name_initial", "")
                        if assist_name:
                            description += f" (由 {assist_name} 助攻)"

                    print(f"{i}. 第{period}节 {clock} - {description}, 比分: {score}")

    def _run_chart_functions(self):
        """运行图表生成功能"""
        print("\n=== 投篮图表演示 ===")

        self.chart_paths = self.nba_service.generate_shot_charts(
            team=self.args.team,
            player_name=self.args.player
        )

    def _run_video_functions(self, mode):
        """运行视频处理功能"""
        if mode == RunMode.VIDEO or mode == RunMode.VIDEO_TEAM or mode == RunMode.ALL:
            # 处理球队视频
            print("\n=== 处理球队集锦视频 ===")
            team_videos = self.nba_service.get_team_highlights(team=self.args.team, merge=True)
            if team_videos:
                if "merged" in team_videos:
                    self.video_paths["team_video"] = team_videos["merged"]
                    print(f"✓ 已生成球队合并视频: {team_videos['merged']}")
                else:
                    print(f"✓ 获取到 {len(team_videos)} 个球队视频片段")
            else:
                print("× 获取球队集锦视频失败")

        if mode == RunMode.VIDEO or mode == RunMode.VIDEO_PLAYER or mode == RunMode.ALL:
            # 处理球员视频
            print("\n=== 处理球员集锦视频 ===")
            player_videos = self.nba_service.get_player_highlights(
                player_name=self.args.player,
                merge=True
            )
            if player_videos:
                if "video_merged" in player_videos:
                    self.video_paths["player_video"] = player_videos["video_merged"]
                    print(f"✓ 已生成球员合并视频: {player_videos['video_merged']}")
                else:
                    print(f"✓ 获取到 {len(player_videos.get('videos', {}))} 个分类视频")
            else:
                print("× 获取球员集锦视频失败")

        if mode == RunMode.VIDEO_ROUNDS or mode == RunMode.ALL:
            # 处理球员回合GIF
            print("\n=== 处理球员回合GIF ===")
            self.round_gifs = self.nba_service.create_player_round_gifs(
                player_name=self.args.player
            )

    def _run_weibo_functions(self, mode):
        """运行微博发布功能 - 使用WeiboPostService的方法"""
        # 先检查是否存在所需文件
        if not self._check_required_files_for_weibo(mode):
            print("× 微博发布所需文件不存在，请先生成相应文件")
            return

        # 获取基础数据
        game_data = self.nba_service.data_service.get_game(self.nba_service.config.default_team)
        if not game_data:
            print(f"  获取比赛信息失败")
            return

        game_ai_data = game_data.prepare_ai_data()
        if "error" in game_ai_data:
            print(f"  获取AI友好数据失败: {game_ai_data['error']}")
            return

        # 准备球员数据(如果需要)
        player_data = None
        if self.args.player:
            player_id = self.nba_service.get_player_id_by_name(self.args.player)
            if player_id:
                player_data = game_data.prepare_ai_data(player_id=player_id)

        if mode == RunMode.WEIBO:
            # 执行所有微博发布功能
            # 发布球队集锦视频
            if "team_video" in self.video_paths:
                self.weibo_service.post_team_video(
                    self.content_generator,
                    self.video_paths["team_video"],
                    game_ai_data
                )

            # 发布球员相关内容
            if player_data and self.args.player:
                # 发布球员集锦视频
                if "player_video" in self.video_paths:
                    self.weibo_service.post_player_video(
                        self.content_generator,
                        self.video_paths["player_video"],
                        player_data,
                        self.args.player
                    )

                # 发布球员投篮图
                if "player_chart" in self.chart_paths:
                    self.weibo_service.post_player_chart(
                        self.content_generator,
                        self.chart_paths["player_chart"],
                        player_data,
                        self.args.player
                    )

        elif mode == RunMode.WEIBO_TEAM:
            # 只发布球队集锦视频
            if "team_video" in self.video_paths:
                self.weibo_service.post_team_video(
                    self.content_generator,
                    self.video_paths["team_video"],
                    game_ai_data
                )

        elif mode == RunMode.WEIBO_PLAYER:
            # 只发布球员集锦视频
            if player_data and "player_video" in self.video_paths:
                self.weibo_service.post_player_video(
                    self.content_generator,
                    self.video_paths["player_video"],
                    player_data,
                    self.args.player
                )

        elif mode == RunMode.WEIBO_CHART:
            # 只发布球员投篮图
            if player_data and "player_chart" in self.chart_paths:
                self.weibo_service.post_player_chart(
                    self.content_generator,
                    self.chart_paths["player_chart"],
                    player_data,
                    self.args.player
                )

        elif mode == RunMode.WEIBO_TEAM_CHART:
            # 只发布球队投篮图
            if "team_chart" in self.chart_paths:
                self.weibo_service.post_team_chart(
                    self.content_generator,
                    self.chart_paths["team_chart"],
                    game_ai_data,
                    self.args.team
                )

        elif mode == RunMode.WEIBO_ROUND:
            # 只发布球员回合解说和GIF
            if player_data:
                self.weibo_service.post_player_rounds(
                    self.content_generator,
                    self.round_gifs,
                    player_data,
                    self.args.player,
                    self.nba_service
                )

    def _run_ai_functions(self):
        """运行AI分析功能"""
        print("\n=== AI分析结果 ===")

        if not self.ai_processor or not self.content_generator:
            print("  × AI处理器或内容生成器未初始化，跳过分析")
            return

        try:
            print("\n正在获取结构化数据并进行AI分析，这可能需要一些时间...")

            # 获取比赛数据
            game_data = self.nba_service.data_service.get_game(self.args.team)
            if not game_data:
                print(f"  获取比赛信息失败: 未找到{self.args.team}的比赛数据")
                return

            # 准备AI友好数据
            player_id = None
            if self.args.player:
                player_id = self.nba_service.get_player_id_by_name(self.args.player)

            ai_data = game_data.prepare_ai_data(player_id=player_id)

            if "error" in ai_data:
                print(f"  × 获取数据失败: {ai_data['error']}")
                return

            # 使用内容生成器进行分析
            title = self.content_generator.generate_game_title(ai_data)
            summary = self.content_generator.generate_game_summary(ai_data)

            if self.args.player:
                player_analysis = self.content_generator.generate_player_analysis(
                    ai_data, self.args.player
                )

                # 显示分析结果
                print("\n比赛标题:")
                print(f"  {title}")

                print("\n比赛摘要:")
                print(summary)

                print(f"\n{self.args.player}表现分析:")
                print(player_analysis)
            else:
                # 显示分析结果
                print("\n比赛标题:")
                print(f"  {title}")

                print("\n比赛摘要:")
                print(summary)

            print("\nAI分析完成!")

        except Exception as e:
            self.logger.error(f"AI分析功能执行失败: {e}", exc_info=True)
            print(f"  × AI分析失败: {e}")

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