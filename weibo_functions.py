"""微博发布相关的业务逻辑函数

处理各种微博内容的生成和发布功能。
主要功能：
1. 发布球队集锦视频
2. 发布球员集锦视频
3. 发布球员投篮图
4. 发布球员回合解说和GIF
"""
import re
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from config.nba_config import  NBAConfig


def post_team_video(weibo_service, content_generator, video_path, game_data):
    """发布球队集锦视频到微博"""
    print("\n=== 发布球队集锦视频到微博 ===")

    if not weibo_service or not content_generator:
        print("微博服务或内容生成器未初始化，跳过发布")
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

        # 使用WeiboContentGenerator生成内容
        game_post = content_generator.prepare_weibo_content(game_data, "game")

        # 显示部分发布内容以便调试
        print(f"  标题: {game_post['title']}")
        print(f"  内容: {game_post['content'][:50]}..." if len(
            game_post['content']) > 50 else f"  内容: {game_post['content']}")

        team_video_path = str(video_path)
        print(f"发布球队集锦视频: {team_video_path}")

        result = weibo_service.post_video(
            video_path=team_video_path,
            title=game_post["title"],
            content=game_post["content"],
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


def post_player_video(weibo_service, content_generator, video_path, player_data, player_name):
    """发布球员集锦视频到微博"""
    print("\n=== 发布球员集锦视频到微博 ===")

    if not weibo_service or not content_generator:
        print("微博服务或内容生成器未初始化，跳过发布")
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

        # 使用WeiboContentGenerator生成内容
        player_post = content_generator.prepare_weibo_content(
            player_data, "player", player_name
        )

        # 显示部分发布内容以便调试
        print(f"  标题: {player_post['title']}")
        print(f"  内容: {player_post['content'][:50]}..." if len(
            player_post['content']) > 50 else f"  内容: {player_post['content']}")

        player_video_path = str(video_path)
        print(f"发布球员集锦视频: {player_video_path}")

        result = weibo_service.post_video(
            video_path=player_video_path,
            title=player_post["title"],
            content=player_post["content"],
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


def post_player_chart(weibo_service, content_generator, chart_path, player_data, player_name):
    """发布球员投篮图到微博"""
    print("\n=== 发布球员投篮图到微博 ===")

    if not weibo_service or not content_generator:
        print("微博服务或内容生成器未初始化，跳过发布")
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

        # 使用WeiboContentGenerator生成内容
        chart_post = content_generator.prepare_weibo_content(
            player_data, "chart", player_name
        )

        # 显示部分发布内容以便调试
        print(f"  内容: {chart_post['content'][:50]}..." if len(
            chart_post['content']) > 50 else f"  内容: {chart_post['content']}")

        chart_path_str = str(chart_path)
        print(f"发布球员投篮图: {chart_path_str}")

        result = weibo_service.post_picture(
            content=chart_post["content"],
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


def post_team_chart(weibo_service, content_generator, chart_path, game_data, team_name):
    """发布球队投篮图到微博"""
    print("\n=== 发布球队投篮图到微博 ===")

    if not weibo_service or not content_generator:
        print("微博服务或内容生成器未初始化，跳过发布")
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

        # 使用WeiboContentGenerator生成内容
        # 使用与player_chart类似的方式，但为球队准备内容
        team_post = content_generator.prepare_weibo_content(
            game_data, "team_chart", team_name
        )

        # 显示部分发布内容以便调试
        print(f"  内容: {team_post['content'][:50]}..." if len(
            team_post['content']) > 50 else f"  内容: {team_post['content']}")

        chart_path_str = str(chart_path)
        print(f"发布球队投篮图: {chart_path_str}")

        result = weibo_service.post_picture(
            content=team_post["content"],
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


def post_player_rounds(weibo_service, content_generator, round_gifs, player_data, player_name, nba_service):
    """发布球员回合解说和GIF到微博"""
    print("\n=== 发布球员回合解说和GIF到微博 ===")
    import random  # 导入random用于随机延迟
    import re
    from pathlib import Path

    if not weibo_service or not content_generator:
        print("微博服务或内容生成器未初始化，跳过发布")
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

        # 一次性生成所有回合解说
        print(f"正在为{player_name}(ID:{player_id})的相关回合生成中文解说内容...")
        round_ids = [event_id for event_id, _ in sorted_rounds]

        # 传入player_id参数进行筛选
        all_round_analyses = content_generator.batch_generate_round_analyses(
            player_data, round_ids, player_name, player_id
        )

        print(f"成功生成 {len(all_round_analyses)} 个回合解说")

        # 确保所有GIF都有对应的解说内容
        # 如果某些回合没有解说内容，生成简单解说
        missing_rounds = []
        for event_id, _ in sorted_rounds:
            if int(event_id) not in all_round_analyses:
                missing_rounds.append(int(event_id))

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
                    result = weibo_service.post_picture(
                        content=content,
                        image_paths=str(gif_path)
                    )

                    if result and result.get("success"):
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


def post_all_content(nba_service, weibo_service, content_generator, video_paths, chart_paths, player_name=None):
    """执行所有微博发布功能"""
    print("\n=== 发布所有内容到微博 ===")

    if not weibo_service or not content_generator:
        print("微博服务或内容生成器未初始化，跳过发布")
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
            post_team_video(weibo_service, content_generator, video_paths["team_video"], ai_data)

        # 如果指定了球员，发布球员相关内容
        if player_name:
            # 准备球员数据
            player_id = nba_service.get_player_id_by_name(player_name)
            if player_id:
                player_data = game_data.prepare_ai_data(player_id=player_id)

                # 发布球员集锦视频
                if "player_video" in video_paths:
                    post_player_video(weibo_service, content_generator,
                                      video_paths["player_video"], player_data, player_name)

                # 发布球员投篮图
                if "player_chart" in chart_paths:
                    post_player_chart(weibo_service, content_generator,
                                      chart_paths["player_chart"], player_data, player_name)

        return True

    except Exception as e:
        logging.error(f"发布内容到微博时发生错误: {e}", exc_info=True)
        print(f"  × 发布内容到微博时发生错误: {e}")
        return False