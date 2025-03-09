import os
import time
import random
import logging
import re
from typing import List, Optional, Dict, Any, Union
from pathlib import Path

from weibo.weibo_picture_publisher import WeiboImagePublisher
from weibo.weibo_video_publisher import WeiboVideoPublisher
from utils.logger_handler import AppLogger


class WeiboPostService:
    """微博发布服务，提供统一的发布接口"""

    def __init__(self, cookie: Optional[str] = None, content_generator=None):
        """初始化服务

        Args:
            cookie: 用户登录Cookie，如果不提供会尝试从环境变量获取
            content_generator: 内容生成器实例
        """
        self.logger = AppLogger.get_logger(__name__, app_name='weibo')
        self.content_generator = content_generator

        # 优先使用传入的cookie，否则尝试从环境变量获取
        self.cookie = cookie
        if not self.cookie:
            self.cookie = os.getenv("WB_COOKIES")
            if not self.cookie:
                self.logger.error("未设置WB_COOKIES环境变量且未提供cookie参数")
                raise ValueError("微博Cookie未提供且环境变量WB_COOKIES未设置")

        self.image_publisher = WeiboImagePublisher(self.cookie)
        self.video_publisher = WeiboVideoPublisher(self.cookie)

    def post_picture(self,
                     content: str,
                     image_paths: Union[str, List[str]]) -> Dict[str, Any]:
        """发布图片微博

        Args:
            content: 微博文本内容
            image_paths: 单个图片路径或图片路径列表

        Returns:
            Dict: 包含成功状态和消息的字典
        """
        try:
            self.logger.info(f"开始发布图片微博，图片数量: {len(image_paths) if isinstance(image_paths, list) else 1}")

            # 直接使用图片发布器的方法发布图片
            result = self.image_publisher.publish_images(image_paths, content)

            # 添加详细日志，记录完整的返回结果
            self.logger.debug(f"微博API返回结果: {result}")

            # WeiboImagePublisher中的publish_images方法已经处理了成功/失败的判断
            # 并返回了统一格式的结果，我们只需要信任这个结果
            if result and result.get("success") == True:
                self.logger.info(f"图片微博发布成功")
                return {"success": True, "message": result.get("message", "发布成功"), "data": result.get("data", {})}
            else:
                error_message = result.get("message", "未知错误")
                self.logger.error(f"图片微博发布失败: {error_message}")
                return {"success": False, "message": error_message, "data": result.get("data", {})}

        except Exception as e:
            error_message = f"发布图片微博失败: {str(e)}"
            self.logger.error(error_message, exc_info=True)
            return {"success": False, "message": error_message}

    def post_video(self,
                   video_path: str,
                   title: str,
                   content: str,
                   cover_path: Optional[str] = None,
                   is_original: bool = True,
                   album_id: Optional[str] = None,
                   channel_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """发布视频微博"""
        try:
            self.logger.info(f"开始发布视频微博，视频路径: {video_path}")

            # 添加视频文件检查
            if not os.path.exists(video_path):
                error_message = f"视频文件不存在: {video_path}"
                self.logger.error(error_message)
                return {"success": False, "message": error_message}

            # 上传封面（如果有）
            cover_pid = None
            if cover_path:
                self.logger.info(f"上传视频封面: {cover_path}")
                try:
                    cover_info = self.image_publisher.upload_image(cover_path)
                    if cover_info:
                        cover_pid = cover_info.get('pid')
                        self.logger.info(f"封面上传成功，PID: {cover_pid}")
                except Exception as cover_error:
                    self.logger.warning(f"封面上传失败，将使用默认封面: {str(cover_error)}")

            # 使用进度回调函数
            def progress_callback(current, total, percentage):
                self.logger.info(f"视频上传进度: {current}/{total} 块 ({percentage:.2f}%)")

            # 上传并发布视频
            self.logger.info("开始上传视频...")
            upload_result = self.video_publisher.upload_video(
                file_path=video_path,
                progress_callback=progress_callback
            )

            if not upload_result or 'media_id' not in upload_result:
                error_message = "视频上传失败，未获取到media_id"
                self.logger.error(error_message)
                return {"success": False, "message": error_message}

            media_id = upload_result.get('media_id')
            self.logger.info(f"视频上传成功，media_id: {media_id}")

            # 发布视频
            self.logger.info("开始发布视频内容...")
            publish_result = self.video_publisher.publish_video(
                media_id=media_id,
                title=title,
                content=content,
                cover_pid=cover_pid,
                is_original=is_original,
                album_id=album_id,
                channel_ids=channel_ids
            )

            # 详细记录API返回
            self.logger.debug(f"发布视频API返回: {publish_result}")

            # 简化判断逻辑
            if publish_result.get('ok') == 1 or publish_result.get('code') == 100000 or "success" in str(
                    publish_result).lower():
                self.logger.info(f"视频微博发布成功!")
                return {"success": True, "message": "视频微博发布成功", "data": publish_result}
            else:
                message = publish_result.get('msg', '发布失败')
                self.logger.error(f"视频微博发布失败: {message}")
                return {"success": False, "message": message, "data": publish_result}

        except Exception as e:
            error_message = f"发布视频微博失败: {str(e)}"
            self.logger.error(error_message, exc_info=True)
            return {"success": False, "message": error_message}

    # === 以下是从weibo_functions.py移植的高级方法 ===

    def post_team_video(self, content_generator, video_path, game_data):
        """发布球队集锦视频到微博"""
        print("\n=== 发布球队集锦视频到微博 ===")

        if not content_generator:
            content_generator = self.content_generator

        if not content_generator:
            print("内容生成器未初始化，跳过发布")
            return False

        try:
            # 增加详细的文件路径检查
            if not video_path:
                print("  × 未指定球队集锦视频文件路径")
                print("  提示: 可以先运行 '--mode video-team' 生成球队视频")
                return False

            import os.path
            if not os.path.exists(video_path):
                print(f"  × 球队集锦视频文件不存在: {video_path}")
                print("  提示: 可以先运行 '--mode video-team' 生成球队视频")
                return False

            print(f"  √ 找到球队集锦视频文件: {video_path}")

            # 使用综合内容生成
            all_content = content_generator.generate_comprehensive_content(game_data)

            # 构建发布内容
            game_title = all_content.get("title", "NBA精彩比赛")
            game_summary = all_content.get("summary", "")
            hashtags = " ".join(all_content.get("hashtags", ["#NBA#", "#篮球#"]))

            post_content = f"{game_summary}\n\n{hashtags}"

            # 显示部分发布内容以便调试
            print(f"  标题: {game_title}")
            print(f"  内容: {post_content[:50]}..." if len(post_content) > 50 else f"  内容: {post_content}")

            team_video_path = str(video_path)
            print(f"发布球队集锦视频: {team_video_path}")

            result = self.post_video(
                video_path=team_video_path,
                title=game_title,
                content=post_content,
                is_original=True
            )

            if result and result.get("success"):
                print(f"  ✓ 球队集锦视频发布成功: {result.get('message', '')}")
                logging.info(f"球队集锦视频发布成功: {result}")
                return True
            else:
                print(f"  × 球队集锦视频发布失败: {result.get('message', '未知错误')}")
                if "data" in result:
                    print(f"  详细信息: {result['data']}")
                logging.error(f"球队集锦视频发布失败: {result}")
                return False

        except Exception as e:
            logging.error(f"发布球队集锦视频失败: {e}", exc_info=True)
            print(f"  × 发布球队集锦视频失败: {e}")
            return False

    def post_player_video(self, content_generator, video_path, player_data, player_name):
        """发布球员集锦视频到微博"""
        print("\n=== 发布球员集锦视频到微博 ===")

        if not content_generator:
            content_generator = self.content_generator

        if not content_generator:
            print("内容生成器未初始化，跳过发布")
            return False

        if not player_name:
            print("  × 未指定球员，跳过发布")
            return False

        try:
            # 增加详细的文件路径检查
            if not video_path:
                print("  × 未指定球员集锦视频文件路径")
                print("  提示: 可以先运行 '--mode video-player' 生成球员视频")
                return False

            import os.path
            if not os.path.exists(video_path):
                print(f"  × 球员集锦视频文件不存在: {video_path}")
                print("  提示: 可以先运行 '--mode video-player' 生成球员视频")
                return False

            print(f"  √ 找到球员集锦视频文件: {video_path}")

            # 使用综合内容生成
            all_content = content_generator.generate_comprehensive_content(player_data, player_name=player_name)

            # 构建发布内容
            game_title = all_content.get("title", "NBA精彩比赛")
            player_title = f"{game_title} - {player_name}个人集锦"
            player_analysis = all_content.get("player_analysis", "")
            hashtags = " ".join(all_content.get("hashtags", ["#NBA#", "#篮球#", f"#{player_name}#"]))

            post_content = f"{player_analysis}\n\n{hashtags}"

            # 显示部分发布内容以便调试
            print(f"  标题: {player_title}")
            print(f"  内容: {post_content[:50]}..." if len(post_content) > 50 else f"  内容: {post_content}")

            player_video_path = str(video_path)
            print(f"发布球员集锦视频: {player_video_path}")

            result = self.post_video(
                video_path=player_video_path,
                title=player_title,
                content=post_content,
                is_original=True
            )

            if result and result.get("success"):
                print(f"  ✓ 球员集锦视频发布成功: {result.get('message', '')}")
                logging.info(f"球员集锦视频发布成功: {result}")
                return True
            else:
                print(f"  × 球员集锦视频发布失败: {result.get('message', '未知错误')}")
                if "data" in result:
                    print(f"  详细信息: {result['data']}")
                logging.error(f"球员集锦视频发布失败: {result}")
                return False

        except Exception as e:
            logging.error(f"发布球员集锦视频失败: {e}", exc_info=True)
            print(f"  × 发布球员集锦视频失败: {e}")
            return False

    def post_player_chart(self, content_generator, chart_path, player_data, player_name):
        """发布球员投篮图到微博"""
        print("\n=== 发布球员投篮图到微博 ===")

        if not content_generator:
            content_generator = self.content_generator

        if not content_generator:
            print("内容生成器未初始化，跳过发布")
            return False

        if not player_name:
            print("  × 未指定球员，跳过发布")
            return False

        try:
            # 增加详细的文件路径检查
            if not chart_path:
                print("  × 未指定投篮图文件路径")
                print("  提示: 可以先运行 '--mode chart' 生成投篮图")
                return False

            import os.path
            if not os.path.exists(chart_path):
                print(f"  × 投篮图文件不存在: {chart_path}")
                print("  提示: 可以先运行 '--mode chart' 生成投篮图")
                return False

            print(f"  √ 找到投篮图文件: {chart_path}")

            # 使用综合内容生成
            all_content = content_generator.generate_comprehensive_content(player_data, player_name=player_name)

            # 获取球员投篮图解说
            shot_chart_text = all_content.get("shot_chart_text", f"{player_name}本场比赛投篮分布图")
            hashtags = " ".join(all_content.get("hashtags", ["#NBA#", "#篮球#", f"#{player_name}#"]))

            # 构建发布内容
            post_content = f"{player_name}本场比赛投篮分布图\n\n{shot_chart_text}\n\n{hashtags}"

            # 显示部分发布内容以便调试
            print(f"  内容: {post_content[:50]}..." if len(post_content) > 50 else f"  内容: {post_content}")

            chart_path_str = str(chart_path)
            print(f"发布球员投篮图: {chart_path_str}")

            result = self.post_picture(
                content=post_content,
                image_paths=chart_path_str
            )

            if result and result.get("success"):
                print(f"  ✓ 球员投篮图发布成功: {result.get('message', '')}")
                logging.info(f"球员投篮图发布成功: {result}")
                return True
            else:
                print(f"  × 球员投篮图发布失败: {result.get('message', '未知错误')}")
                if "data" in result:
                    print(f"  详细信息: {result['data']}")
                logging.error(f"球员投篮图发布失败: {result}")
                return False

        except Exception as e:
            logging.error(f"发布球员投篮图失败: {e}", exc_info=True)
            print(f"  × 发布球员投篮图失败: {e}")
            return False

    def post_team_chart(self, content_generator, chart_path, game_data, team_name):
        """发布球队投篮图到微博"""
        print("\n=== 发布球队投篮图到微博 ===")

        if not content_generator:
            content_generator = self.content_generator

        if not content_generator:
            print("内容生成器未初始化，跳过发布")
            return False

        if not team_name:
            print("  × 未指定球队，跳过发布")
            return False

        try:
            # 增加详细的文件路径检查
            if not chart_path:
                print("  × 未指定投篮图文件路径")
                print("  提示: 可以先运行 '--mode chart' 生成投篮图")
                return False

            import os.path
            if not os.path.exists(chart_path):
                print(f"  × 投篮图文件不存在: {chart_path}")
                print("  提示: 可以先运行 '--mode chart' 生成投篮图")
                return False

            print(f"  √ 找到投篮图文件: {chart_path}")

            # 使用综合内容生成
            all_content = content_generator.generate_comprehensive_content(game_data, team_name=team_name)

            # 获取球队投篮分析
            team_shot_analysis = all_content.get("team_shot_analysis", f"{team_name}球队本场比赛投篮分布图")
            hashtags = " ".join(all_content.get("hashtags", ["#NBA#", "#篮球#", f"#{team_name}#"]))

            # 构建发布内容
            post_content = f"{team_name}球队本场比赛投篮分布图\n\n{team_shot_analysis}\n\n{hashtags}"

            # 显示部分发布内容以便调试
            print(f"  内容: {post_content[:50]}..." if len(post_content) > 50 else f"  内容: {post_content}")

            chart_path_str = str(chart_path)
            print(f"发布球队投篮图: {chart_path_str}")

            result = self.post_picture(
                content=post_content,
                image_paths=chart_path_str
            )

            if result and result.get("success"):
                print(f"  ✓ 球队投篮图发布成功: {result.get('message', '')}")
                logging.info(f"球队投篮图发布成功: {result}")
                return True
            else:
                print(f"  × 球队投篮图发布失败: {result.get('message', '未知错误')}")
                if "data" in result:
                    print(f"  详细信息: {result['data']}")
                logging.error(f"球队投篮图发布失败: {result}")
                return False

        except Exception as e:
            logging.error(f"发布球队投篮图失败: {e}", exc_info=True)
            print(f"  × 发布球队投篮图失败: {e}")
            return False

    def post_player_rounds(self, content_generator, round_gifs, player_data, player_name, nba_service):
        """发布球员回合解说和GIF到微博"""
        print("\n=== 发布球员回合解说和GIF到微博 ===")
        import random  # 导入random用于随机延迟
        import re
        from pathlib import Path

        if not content_generator:
            content_generator = self.content_generator

        if not content_generator:
            print("内容生成器未初始化，跳过发布")
            return False

        if not player_name:
            print("  × 未指定球员，跳过发布")
            return False

        try:
            # 自动查找GIF文件（如果未通过参数提供）
            if not round_gifs:
                print("参数中未提供GIF，尝试自动查找...")
                round_gifs = {}

                # 获取球员ID
                player_id = nba_service.get_player_id_by_name(player_name)
                if not player_id:
                    print(f"  × 未找到球员 {player_name} 的ID")
                    return False

                # 获取比赛数据
                game = nba_service.data_service.get_game(nba_service.config.default_team)
                if not game:
                    print(f"  × 未找到比赛数据")
                    return False

                # 构建GIF目录路径
                from config.nba_config import NBAConfig
                gif_dir = NBAConfig.PATHS.GIF_DIR / f"player_rounds_{player_id}_{game.game_data.game_id}"

                if not gif_dir.exists():
                    print(f"  × GIF目录不存在: {gif_dir}")
                    print("  提示: 请先运行 '--mode video-rounds' 生成回合GIF")
                else:
                    # 扫描目录中的GIF文件
                    gif_files = list(gif_dir.glob(f"round_*_{player_id}.gif"))

                    for gif_path in gif_files:
                        match = re.search(r'round_(\d+)_', gif_path.name)
                        if match:
                            event_id = match.group(1)
                            round_gifs[event_id] = gif_path

                    print(f"自动找到 {len(round_gifs)} 个回合GIF")

            # 最终检查，如果没有GIF，则退出
            if not round_gifs:
                print("  × 未找到回合GIF，跳过发布")
                print("  提示: 请先运行 '--mode video-rounds' 生成回合GIF")
                return False

            # 获取球员ID，用于筛选
            player_id = nba_service.get_player_id_by_name(player_name)
            if not player_id:
                print(f"  × 未找到球员 {player_name} 的ID")
                return False

            # 在调用batch_generate_round_analyses之前，确保player_data包含完整的回合数据
            if "rounds" not in player_data or not player_data.get("rounds"):
                # 检查是否有events数据
                if "events" in player_data and "data" in player_data["events"]:
                    player_data["rounds"] = player_data["events"]["data"]
                    print(f"从events数据中导入了{len(player_data['rounds'])}个回合")

            # 检查player_related_action_numbers是否存在
            if ("events" not in player_data or
                    "player_related_action_numbers" not in player_data.get("events", {})):
                print("player_data中缺少player_related_action_numbers，重新获取完整数据")
                player_data = nba_service.data_service.get_game(
                    nba_service.config.default_team).prepare_ai_data(player_id=player_id)

            # 按事件ID顺序排序 - 使用整数排序
            sorted_rounds = sorted(
                round_gifs.items(),
                key=lambda x: int(x[0]) if x[0].isdigit() else float('inf')
            )

            print(f"准备发布 {len(sorted_rounds)} 个回合GIF (按事件顺序)")

            # 获取回合ID列表
            round_ids = [int(event_id) for event_id, _ in sorted_rounds]

            # 使用综合内容生成方法
            print(f"正在为{player_name}(ID:{player_id})的相关回合生成中文解说内容...")
            all_content = content_generator.generate_comprehensive_content(
                player_data,
                player_name=player_name,
                team_name=nba_service.config.default_team,
                round_ids=round_ids
            )

            # 从综合内容中提取回合解说
            all_round_analyses = {}
            if "rounds" in all_content:
                for rid_str, analysis in all_content["rounds"].items():
                    try:
                        all_round_analyses[int(rid_str)] = analysis
                    except ValueError:
                        # 如果rid_str不是数字，忽略
                        pass

            print(f"成功生成 {len(all_round_analyses)} 个回合解说")

            # 确保所有GIF都有对应的解说内容 - 对缺失的生成简单解说
            missing_rounds = []
            for event_id, _ in sorted_rounds:
                event_id_int = int(event_id)
                if event_id_int not in all_round_analyses:
                    missing_rounds.append(event_id_int)

            if missing_rounds:
                print(f"发现 {len(missing_rounds)} 个回合没有解说内容，将生成简单解说")
                for i, event_id in enumerate(missing_rounds):
                    # 计算这个回合在所有回合中的索引位置
                    idx = [i for i, (eid, _) in enumerate(sorted_rounds, 1) if int(eid) == event_id][0]
                    all_round_analyses[event_id] = content_generator._generate_simple_round_content(
                        player_data, event_id, player_name, idx, len(sorted_rounds)
                    )
                print(f"已生成 {len(missing_rounds)} 个简单解说")

            # 定义重试函数
            def post_with_retry(gif_path, content, max_retries=3):
                for retry in range(max_retries):
                    try:
                        result = self.post_picture(
                            content=content,
                            image_paths=str(gif_path)
                        )

                        if result and result.get("success") == True:
                            return True, result

                        error_msg = result.get("message", "")
                        if "频率" in error_msg or "太快" in error_msg:
                            wait_time = 30 + retry * 15  # 30秒，45秒，60秒
                            print(f"  ! API频率限制，等待{wait_time}秒后重试...")
                            time.sleep(wait_time)
                        else:
                            return False, result

                    except Exception as e:
                        print(f"  ! 发布异常: {e}")
                        time.sleep(20)

                return False, {"message": "达到最大重试次数"}

            # 发布回合
            success_count = 0
            failure_count = 0

            for i, (event_id, gif_path) in enumerate(sorted_rounds):
                try:
                    # 获取预生成的解说
                    event_id_int = int(event_id)
                    round_content = all_round_analyses.get(event_id_int)

                    # 如果没有找到解说内容，使用备用内容
                    if not round_content:
                        print(f"  ! 回合 #{event_id} 未找到解说，正在生成简单解说...")
                        round_content = content_generator._generate_simple_round_content(
                            player_data, event_id_int, player_name, i + 1, len(sorted_rounds)
                        )

                    # 格式化内容（添加回合序号等）
                    formatted_content = content_generator._format_round_content(
                        player_data, event_id_int, player_name, round_content, i + 1, len(sorted_rounds)
                    )

                    # 检查文件是否存在
                    if not gif_path.exists():
                        print(f"  × 回合 #{event_id} 的GIF文件不存在: {gif_path}")
                        failure_count += 1
                        continue

                    print(f"发布回合 #{event_id} 解说和GIF: {gif_path.name}")
                    print(f"  内容: {formatted_content[:50]}..." if len(
                        formatted_content) > 50 else f"  内容: {formatted_content}")

                    # 直接发布到微博并处理重试
                    success, result = post_with_retry(gif_path, formatted_content)

                    # 检查结果
                    if success:
                        print(f"  ✓ 回合 #{event_id} 发布成功")
                        success_count += 1
                    else:
                        print(f"  × 回合 #{event_id} 发布失败: {result.get('message', '未知错误')}")
                        if "data" in result:
                            print(f"  详细信息: {result['data']}")
                        failure_count += 1

                    # 随机延迟20-30秒
                    if i < len(sorted_rounds) - 1:
                        delay_time = random.randint(20, 30)
                        print(f"等待 {delay_time} 秒后继续发布下一个回合...")
                        time.sleep(delay_time)

                except Exception as e:
                    print(f"  × 发布回合 #{event_id} 失败: {str(e)}")
                    failure_count += 1
                    # 发生错误后增加一些额外等待
                    print("发生错误，等待 20 秒后继续...")
                    time.sleep(20)
                    continue

            print(f"\n回合发布完成! 成功发布 {success_count}/{len(sorted_rounds)} 个回合, 失败 {failure_count} 个")
            return success_count > 0

        except Exception as e:
            logging.error(f"发布球员回合解说和GIF失败: {e}", exc_info=True)
            print(f"  × 发布球员回合解说和GIF失败: {e}")
            return False

    def post_all_content(self, nba_service, content_generator, video_paths, chart_paths, player_name=None):
        """执行所有微博发布功能"""
        print("\n=== 发布所有内容到微博 ===")

        if not content_generator:
            content_generator = self.content_generator

        if not content_generator:
            print("内容生成器未初始化，跳过发布")
            return False

        try:
            # 获取比赛和AI数据
            game_data = nba_service.data_service.get_game(nba_service.config.default_team)
            if not game_data:
                print(f"  获取比赛信息失败")
                return False

            ai_data = game_data.prepare_ai_data()
            if "error" in ai_data:
                print(f"  获取AI友好数据失败: {ai_data['error']}")
                return False

            # 发布球队集锦视频
            if "team_video" in video_paths:
                self.post_team_video(content_generator, video_paths["team_video"], ai_data)

            # 如果指定了球员，发布球员相关内容
            if player_name:
                # 准备球员数据
                player_id = nba_service.get_player_id_by_name(player_name)
                if player_id:
                    player_data = game_data.prepare_ai_data(player_id=player_id)

                    # 发布球员集锦视频
                    if "player_video" in video_paths:
                        self.post_player_video(content_generator,
                                               video_paths["player_video"], player_data, player_name)

                    # 发布球员投篮图
                    if "player_chart" in chart_paths:
                        self.post_player_chart(content_generator,
                                               chart_paths["player_chart"], player_data, player_name)

            return True

        except Exception as e:
            logging.error(f"发布内容到微博时发生错误: {e}", exc_info=True)
            print(f"  × 发布内容到微博时发生错误: {e}")
            return False

    def _check_file_exists(self, file_path, file_type="文件") -> bool:
        """检查文件是否存在，并记录日志

        Args:
            file_path: 文件路径
            file_type: 文件类型描述

        Returns:
            bool: 文件是否存在
        """
        import os.path

        if not file_path:
            self.logger.error(f"未指定{file_type}路径")
            return False

        if not os.path.exists(file_path):
            self.logger.error(f"{file_type}不存在: {file_path}")
            return False

        self.logger.info(f"找到{file_type}: {file_path}")
        return True

    def close(self):
        """清理资源"""
        if hasattr(self, 'image_publisher'):
            del self.image_publisher
        if hasattr(self, 'video_publisher'):
            del self.video_publisher

    def __enter__(self):
        """支持使用with语句"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出with语句块时自动关闭资源"""
        self.close()