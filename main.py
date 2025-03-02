"""NBA 数据服务主程序 - 优化版本

实现以下核心功能：
1. 比赛基础信息查询
2. 投篮图表生成
3. 视频处理功能
4. 发布球队集锦视频到微博
5. 发布球员集锦视频到微博
6. 发布球员投篮图到微博
7. AI分析比赛数据 (优化功能)

用法:
    python main.py [options]

选项:
    --team TEAM         指定默认球队，默认为 Lakers
    --player PLAYER     指定默认球员，默认为 LeBron James
    --date DATE         指定比赛日期，默认为 last 表示最近一场比赛
    --mode MODE         指定运行模式，可选值: info, chart, video, weibo, ai, all
                        默认为 all
    --no-weibo          不发布到微博
    --debug             启用调试模式，输出详细日志
    --config FILE       指定配置文件
"""
import json
import os
import sys
import time
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from enum import Enum
import logging
from dotenv import load_dotenv

# 导入所需的类
from utils.ai_processor import AIProcessor, AIConfig, AIProvider, AIModel
from nba.services.nba_service import NBAService, NBAServiceConfig, ServiceStatus
from nba.services.game_video_service import VideoConfig
from utils.video_converter import VideoProcessConfig
from utils.logger_handler import AppLogger
from weibo.weibo_post_service import WeiboPostService
from weibo.weibo_content_generator import WeiboContentGenerator  # 导入新的内容生成器


# 定义运行模式
class RunMode(Enum):
    """应用程序运行模式"""
    INFO = "info"  # 只显示比赛信息
    CHART = "chart"  # 只生成图表
    VIDEO = "video"  # 只处理视频
    WEIBO = "weibo"  # 只发布到微博
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
        self.content_generator = None  # 新增内容生成器
        self.video_paths = {}
        self.chart_paths = {}

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
            if self.args.mode in (RunMode.AI.value, RunMode.WEIBO.value, RunMode.ALL.value):
                self.ai_processor = self._init_ai_processor()

                # 初始化内容生成器（如果AI处理器可用）
                if self.ai_processor:
                    self.content_generator = WeiboContentGenerator(
                        ai_processor=self.ai_processor,
                        logger=self.logger
                    )
                    self.logger.info("微博内容生成器初始化成功")

            # 初始化微博服务
            if not self.args.no_weibo and (
                    self.args.mode == RunMode.WEIBO.value or self.args.mode == RunMode.ALL.value):
                self.weibo_service = self._init_weibo_service()

            # 验证微博发布所需组件是否完整
            if self.args.mode in (RunMode.WEIBO.value, RunMode.ALL.value) and not self.args.no_weibo:
                if not self.weibo_service:
                    self.logger.warning("微博服务未初始化，将跳过发布功能")
                if not self.content_generator:
                    self.logger.warning("内容生成器未初始化，将跳过发布功能")

        except Exception as e:
            self.logger.error(f"服务初始化失败: {e}", exc_info=True)
            raise RuntimeError(f"服务初始化失败: {e}")

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

    def _init_weibo_service(self) -> Optional[WeiboPostService]:
        """初始化微博发布服务"""
        self.logger.info("初始化微博发布服务...")
        try:
            weibo_service = WeiboPostService()  # 从环境变量获取cookie
            self.logger.info("微博发布服务初始化成功")
            return weibo_service
        except Exception as e:
            self.logger.error(f"微博发布服务初始化失败: {e}")
            return None

    def _init_ai_processor(self) -> Optional[AIProcessor]:
        """初始化AI处理器"""
        self.logger.info("初始化AI处理器...")
        try:
            # 创建AI配置
            ai_config = AIConfig(
                provider=AIProvider.OPENROUTER,
                model=AIModel.GEMINI_FLASH,
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

            if mode in (RunMode.INFO, RunMode.ALL):
                self.run_game_info()
                self.run_game_narrative()
                self.run_events_timeline()

            if mode in (RunMode.CHART, RunMode.ALL):
                self.run_shot_charts()

            if mode in (RunMode.VIDEO, RunMode.ALL):
                self.run_video_features()

            if mode in (RunMode.WEIBO, RunMode.ALL) and not self.args.no_weibo:
                self.run_weibo_post()

            if mode in (RunMode.AI, RunMode.ALL) and self.ai_processor:
                self.run_ai_analysis()

            self.logger.info("=== 应用程序运行完成 ===")
            return 0

        except Exception as e:
            self.logger.error(f"应用程序运行失败: {e}", exc_info=True)
            print(f"\n应用程序运行失败: {e}\n请查看日志获取详细信息")
            return 1

        finally:
            self.cleanup()

    def run_game_info(self) -> None:
        """运行比赛信息查询功能"""
        print("\n=== 比赛基本信息 ===")
        try:
            game_data = self.nba_service.data_service.get_game(self.args.team)
            if not game_data:
                print(f"  获取比赛信息失败: 未找到{self.args.team}的比赛数据")
                return

            ai_data = game_data.prepare_ai_data()
            if "error" in ai_data:
                print(f"  获取比赛信息失败: {ai_data['error']}")
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

            # 使用AI处理器生成摘要
            if self.ai_processor and self.content_generator:
                try:
                    summary = self.content_generator.generate_game_summary(ai_data)
                    if summary:
                        print("\nAI比赛摘要:")
                        print(f"  {summary}")
                except Exception as e:
                    self.logger.warning(f"AI摘要生成失败: {e}")

        except Exception as e:
            self.logger.error(f"获取比赛信息失败: {e}", exc_info=True)
            print("  获取比赛信息时发生错误")

    def run_game_narrative(self) -> None:
        """获取比赛详细叙述"""
        # 这个方法保持不变，使用AI处理器而非内容生成器
        print("\n=== 比赛详细叙述 ===")
        try:
            game_data = self.nba_service.data_service.get_game(self.args.team)
            if not game_data:
                print(f"  获取比赛信息失败: 未找到{self.args.team}的比赛数据")
                return

            ai_data = game_data.prepare_ai_data()

            if self.ai_processor and "team_stats" in ai_data:
                try:
                    home_stats = ai_data["team_stats"]["home"]
                    away_stats = ai_data["team_stats"]["away"]
                    home_name = home_stats["basic"]["team_name"]
                    away_name = away_stats["basic"]["team_name"]

                    narrative_data = {
                        "home_team": home_name,
                        "away_team": away_name,
                        "home_score": home_stats["basic"]["points"],
                        "away_score": away_stats["basic"]["points"],
                        "home_fg": f"{home_stats['shooting']['field_goals']['made']}/{home_stats['shooting']['field_goals']['attempted']} ({home_stats['shooting']['field_goals']['percentage']}%)",
                        "away_fg": f"{away_stats['shooting']['field_goals']['made']}/{away_stats['shooting']['field_goals']['attempted']} ({away_stats['shooting']['field_goals']['percentage']}%)",
                        "home_rebounds": home_stats["rebounds"]["total"],
                        "away_rebounds": away_stats["rebounds"]["total"],
                        "home_assists": home_stats["offense"]["assists"],
                        "away_assists": away_stats["offense"]["assists"]
                    }

                    prompt = f"""
                    生成一个简洁的比赛叙述，描述以下两队表现和比赛走势:
                    {json.dumps(narrative_data, ensure_ascii=False)}
                    """
                    narrative = self.ai_processor.generate(prompt)

                    if narrative:
                        print("\n比赛叙述:")
                        print(narrative)
                    else:
                        print("  未能使用AI生成比赛叙述")

                except Exception as ai_error:
                    self.logger.warning(f"AI叙述生成失败: {ai_error}")
                    if "game_status" in ai_data:
                        status = ai_data["game_status"]
                        print(
                            f"\n当前比分: {status['score']['away']['team']} {status['score']['away']['points']} - {status['score']['home']['team']} {status['score']['home']['points']}")
                        print(f"比赛状态: {status['status']}")
            else:
                if "game_status" in ai_data:
                    status = ai_data["game_status"]
                    print(
                        f"\n当前比分: {status['score']['away']['team']} {status['score']['away']['points']} - {status['score']['home']['team']} {status['score']['home']['points']}")
                    print(f"比赛状态: {status['status']}")

            # 显示球员数据部分保持不变
            if self.args.player:
                print(f"\n=== {self.args.player} 球员详细数据 ===")
                player_id = self.nba_service.get_player_id_by_name(self.args.player)
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
                        if player_found:
                            break

                    if not player_found:
                        print(f"  未找到 {self.args.player} 的数据")
                else:
                    print(f"  未能获取 {self.args.player} 的球员数据")
        except Exception as e:
            self.logger.error(f"获取比赛叙述失败: {e}", exc_info=True)
            print("  获取比赛叙述时发生错误")

    def run_events_timeline(self) -> None:
        """获取比赛事件时间线并进行分类展示"""
        # 事件时间线的代码保持不变
        print("\n=== 比赛事件时间线 ===")
        try:
            game_data = self.nba_service.data_service.get_game(self.args.team)
            if not game_data:
                print(f"  获取比赛信息失败: 未找到{self.args.team}的比赛数据")
                return

            ai_data = game_data.prepare_ai_data()
            if "events" not in ai_data or "data" not in ai_data["events"]:
                print("  未找到事件数据")
                return

            events = ai_data["events"]["data"]
            if not events:
                print("  事件数据为空")
                return

            print(f"\n共获取到 {len(events)} 个事件:")

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

            # 球员事件
            if self.args.player:
                player_id = self.nba_service.get_player_id_by_name(self.args.player)
                if player_id:
                    player_events = [e for e in events if e.get("player_id") == player_id]
                    if player_events:
                        print(f"\n{self.args.player} 的事件 (共{len(player_events)}个):")

                        player_events_by_type = {}
                        for event in player_events:
                            event_type = event.get("action_type", "unknown")
                            if event_type not in player_events_by_type:
                                player_events_by_type[event_type] = []
                            player_events_by_type[event_type].append(event)

                        print(f"  事件类型分布: ", end="")
                        type_counts = [f"{k}({len(v)})" for k, v in player_events_by_type.items()]
                        print(", ".join(type_counts))

                        player_events.sort(key=lambda x: (x.get("period", 0), x.get("clock", "")))
                        important_events = player_events[:5]
                        print(f"  {self.args.player} 的事件:")
                        for i, event in enumerate(important_events, 1):
                            period = event.get("period", "")
                            clock = event.get("clock", "")
                            action_type = event.get("action_type", "")
                            description = event.get("description", "")
                            print(f"  {i}. 第{period}节 {clock} - {action_type}: {description}")
                    else:
                        print(f"  未找到 {self.args.player} 的事件")
        except Exception as e:
            self.logger.error(f"获取事件时间线失败: {e}", exc_info=True)
            print("  获取事件时间线时发生错误")

    def run_shot_charts(self) -> None:
        """运行投篮图生成功能"""
        print("\n=== 投篮图表演示 ===")

        try:
            # 生成单个球员的投篮图
            player_name = self.args.player
            print(f"\n1. 生成 {player_name} 的个人投篮图")
            player_chart_path = self.nba_service.plot_player_scoring_impact(
                player_name=player_name
            )
            if player_chart_path:
                print(f"   ✓ 个人投篮图已生成: {player_chart_path}")
                self.chart_paths["player_chart"] = player_chart_path
            else:
                print("   × 个人投篮图生成失败")

            # 生成球队整体投篮图
            team_name = self.args.team
            print(f"\n2. 生成 {team_name} 的球队投篮图")
            team_chart_path = self.nba_service.plot_team_shots(
                team=team_name
            )
            if team_chart_path:
                print(f"   ✓ 球队投篮图已生成: {team_chart_path}")
                self.chart_paths["team_chart"] = team_chart_path
            else:
                print("   × 球队投篮图生成失败")

        except Exception as e:
            self.logger.error(f"生成投篮图失败: {e}", exc_info=True)
            print(f"生成投篮图时发生错误: {e}")

    def run_video_features(self) -> None:
        """运行视频功能，包含请求间隔"""
        print("\n=== 视频功能 ===")

        # 设置请求间隔时间（秒）
        request_delay = 2.0

        try:
            # 获取球员集锦
            player_name = self.args.player
            print(f"\n1. 获取 {player_name} 的集锦视频")
            player_highlights = self.nba_service.get_player_highlights(
                player_name=player_name,
                merge=True,
                request_delay=1.0
            )

            if player_highlights:
                if isinstance(player_highlights, dict):
                    if "merged" in player_highlights and isinstance(player_highlights["merged"], Path):
                        print(f"  ✓ 已生成合并视频: {player_highlights['merged']}")
                        self.video_paths["player_video"] = player_highlights["merged"]
                    else:
                        print(f"  ✓ 获取到 {len(player_highlights)} 个视频片段")
                        for measure, paths in player_highlights.items():
                            if isinstance(paths, dict):
                                print(f"    {measure}: {len(paths)} 个片段")
            else:
                print("  × 获取球员集锦视频失败")

            # 等待一段时间再进行下一个请求
            print(f"\n等待 {request_delay} 秒后继续...")
            time.sleep(request_delay)

            # 获取球队集锦
            team_name = self.args.team
            print(f"\n2. 获取 {team_name} 的集锦视频")
            team_highlights = self.nba_service.get_team_highlights(
                team=team_name,
                merge=True
            )

            if team_highlights:
                if isinstance(team_highlights, dict):
                    if "merged" in team_highlights and isinstance(team_highlights["merged"], Path):
                        print(f"  ✓ 已生成合并视频: {team_highlights['merged']}")
                        self.video_paths["team_video"] = team_highlights["merged"]
                    else:
                        print(f"  ✓ 获取到 {len(team_highlights)} 个视频片段")
            else:
                print("  × 获取球队集锦视频失败")

        except Exception as e:
            self.logger.error(f"运行视频功能失败: {e}", exc_info=True)
            print(f"运行视频功能时发生错误: {e}")

    def run_ai_analysis(self) -> None:
        """运行AI分析功能"""
        print("\n=== AI分析结果 ===")

        if not self.ai_processor:
            print("  × AI处理器未初始化，跳过分析")
            return

        try:
            print("\n正在获取结构化数据并进行AI分析，这可能需要一些时间...")

            # 获取比赛数据
            game_data = self.nba_service.data_service.get_game(self.args.team)
            if not game_data:
                print(f"  获取比赛信息失败: 未找到{self.args.team}的比赛数据")
                return

            # 使用Game模型的prepare_ai_data方法获取结构化数据
            player_id = None
            if self.args.player:
                player_id = self.nba_service.get_player_id_by_name(self.args.player)

            ai_formatted_data = game_data.prepare_ai_data(player_id=player_id)

            if "error" in ai_formatted_data:
                print(f"  × 获取数据失败: {ai_formatted_data['error']}")
                return

            # 获取事件时间线并按重要性排序
            events = ai_formatted_data["events"]["data"] if "events" in ai_formatted_data else []

            # 使用内容生成器进行分析
            if self.content_generator:
                title = self.content_generator.generate_game_title(ai_formatted_data)
                summary = self.content_generator.generate_game_summary(ai_formatted_data)

                if self.args.player:
                    player_analysis = self.content_generator.generate_player_analysis(
                        ai_formatted_data, self.args.player
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
            else:
                prompt = f"""
                分析这场NBA比赛的关键数据，包括比赛走势、关键球员表现和胜负因素:
                {json.dumps(ai_formatted_data, ensure_ascii=False)}
                """
                ai_results = self.ai_processor.generate(prompt)

                if ai_results:
                    print("\n比赛分析:")
                    print(ai_results)
                else:
                    print("  × AI分析未能产生任何结果")

            print("\nAI分析完成!")

        except Exception as e:
            self.logger.error(f"AI分析功能执行失败: {e}", exc_info=True)
            print(f"  × AI分析失败: {e}")

    def _calculate_event_importance(self, event: Dict[str, Any]) -> int:
        """计算事件重要性(0-5)"""
        importance = 0

        # 事件类型重要性
        action_type = event.get("action_type", "").lower()
        high_importance_types = {"2pt", "3pt", "dunk", "block", "steal"}
        medium_importance_types = {"rebound", "assist", "foul"}

        if action_type in high_importance_types:
            importance += 3
        elif action_type in medium_importance_types:
            importance += 2

        # 关键时刻加分
        period = event.get("period", 0)
        clock = event.get("clock", "")
        if period >= 4 and ":" in clock:
            minutes = int(clock.split(":")[0])
            if minutes <= 2:
                importance += 1

        # 比分接近加分
        score_home = event.get("score_home")
        score_away = event.get("score_away")
        if score_home and score_away:
            try:
                score_diff = abs(int(score_home) - int(score_away))
                if score_diff <= 5:
                    importance += 1
            except (ValueError, TypeError):
                pass

        return min(importance, 5)

    def run_weibo_post(self) -> None:
        """发布内容到微博"""
        if not self.weibo_service or not self.content_generator:
            print("微博服务或内容生成器未初始化，跳过发布")
            return

        print("\n=== 发布内容到微博 ===")

        try:
            # 1. 获取比赛数据
            game = self.nba_service.data_service.get_game(self.args.team)
            if not game:
                print(f"  获取比赛信息失败: 未找到{self.args.team}的比赛数据")
                return

            # 2. 使用Game模型的prepare_ai_data获取结构化数据
            ai_data = game.prepare_ai_data()
            if "error" in ai_data:
                print(f"  获取AI友好数据失败: {ai_data['error']}")
                return

            # 3. 发布球队集锦视频
            self._post_team_video(ai_data)

            # 4. 发布球员集锦视频
            if self.args.player:
                # 准备包含球员数据的AI友好格式
                player_id = self.nba_service.get_player_id_by_name(self.args.player)
                player_ai_data = game.prepare_ai_data(player_id=player_id)

                # 发布球员视频和图表
                self._post_player_video(player_ai_data)
                self._post_player_chart(player_ai_data)

        except Exception as e:
            self.logger.error(f"发布内容到微博时发生错误: {e}", exc_info=True)
            print(f"  × 发布内容到微博时发生错误: {e}")

    def _post_team_video(self, ai_data: Dict[str, Any]) -> None:
        """发布球队集锦视频到微博

        Args:
            ai_data: Game.prepare_ai_data()生成的AI友好数据
        """
        if "team_video" not in self.video_paths or not self.video_paths["team_video"].exists():
            print("  × 球队集锦视频不存在，跳过发布")
            return

        # 使用WeiboContentGenerator生成内容
        game_post = self.content_generator.prepare_weibo_content(ai_data, "game")

        team_video_path = str(self.video_paths["team_video"])
        print(f"\n1. 发布球队集锦视频: {team_video_path}")

        result = self.weibo_service.post_video(
            video_path=team_video_path,
            title=game_post["title"],
            content=game_post["content"],
            is_original=True
        )

        if result and result.get("success"):
            print(f"  ✓ 球队集锦视频发布成功: {result.get('message', '')}")
            self.logger.info(f"球队集锦视频发布成功: {result}")
        else:
            print(f"  × 球队集锦视频发布失败: {result.get('message', '未知错误')}")
            self.logger.error(f"球队集锦视频发布失败: {result}")

    def _post_player_video(self, player_ai_data: Dict[str, Any]) -> None:
        """发布球员集锦视频到微博

        Args:
            player_ai_data: 包含球员数据的AI友好格式
        """
        if "player_video" not in self.video_paths or not self.video_paths["player_video"].exists():
            print("  × 球员集锦视频不存在，跳过发布")
            return

        # 使用WeiboContentGenerator生成内容
        player_post = self.content_generator.prepare_weibo_content(
            player_ai_data, "player", self.args.player
        )

        player_video_path = str(self.video_paths["player_video"])
        print(f"\n2. 发布球员集锦视频: {player_video_path}")

        result = self.weibo_service.post_video(
            video_path=player_video_path,
            title=player_post["title"],
            content=player_post["content"],
            is_original=True
        )

        if result and result.get("success"):
            print(f"  ✓ 球员集锦视频发布成功: {result.get('message', '')}")
            self.logger.info(f"球员集锦视频发布成功: {result}")
        else:
            print(f"  × 球员集锦视频发布失败: {result.get('message', '未知错误')}")
            self.logger.error(f"球员集锦视频发布失败: {result}")

    def _post_player_chart(self, player_ai_data: Dict[str, Any]) -> None:
        """发布球员投篮图到微博

        Args:
            player_ai_data: 包含球员数据的AI友好格式
        """
        if "player_chart" not in self.chart_paths or not self.chart_paths["player_chart"].exists():
            print("  × 球员投篮图不存在，跳过发布")
            return

        # 使用WeiboContentGenerator生成内容
        chart_post = self.content_generator.prepare_weibo_content(
            player_ai_data, "chart", self.args.player
        )

        chart_path = str(self.chart_paths["player_chart"])
        print(f"\n3. 发布球员投篮图: {chart_path}")

        result = self.weibo_service.post_picture(
            content=chart_post["content"],
            image_paths=chart_path
        )

        if result and result.get("success"):
            print(f"  ✓ 球员投篮图发布成功: {result.get('message', '')}")
            self.logger.info(f"球员投篮图发布成功: {result}")
        else:
            print(f"  × 球员投篮图发布失败: {result.get('message', '未知错误')}")
            self.logger.error(f"球员投篮图发布失败: {result}")

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