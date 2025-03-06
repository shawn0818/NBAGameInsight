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

    if not weibo_service or not content_generator:
        print("微博服务或内容生成器未初始化，跳过发布")
        return False

    if not player_name:
        print("  × 未指定球员，跳过发布")
        return False

    try:
        if not round_gifs:
            print("  × 未找到回合GIF，跳过发布")
            player_id = nba_service.get_player_id_by_name(player_name)
            if player_id:
                # 检查GIF目录
                video_dir = nba_service.video_service.config.output_dir
                gif_dir = video_dir / f"player_rounds_{player_id}"
                if gif_dir.exists():
                    gif_files = list(gif_dir.glob(f"round_*_{player_id}.gif"))
                    if gif_files:
                        print(f"找到 {len(gif_files)} 个回合GIF文件")
                        round_gifs = {}
                        # 从文件名中提取事件ID并创建字典
                        for gif_path in gif_files:
                            match = re.search(r'round_(\d+)_', gif_path.name)
                            if match:
                                event_id = match.group(1)
                                round_gifs[event_id] = gif_path
                    else:
                        print("  提示: 请先生成回合GIF")
                        return False
                else:
                    print("  提示: 请先生成回合GIF")
                    return False
            else:
                print("  提示: 请先生成回合GIF")
                return False

        if not round_gifs:
            print("  × 仍然未找到回合GIF，跳过发布")
            return False

        # 从player_data获取球员事件用于解说
        if "rounds" not in player_data:
            # 获取球员事件
            game = nba_service.data_service.get_game(nba_service.config.default_team)
            if not game:
                print(f"  × 未找到比赛数据")
                return False

            player_id = nba_service.get_player_id_by_name(player_name)
            events = game.filter_events(player_id=player_id)
            # 添加到player_data中供解说使用
            player_data["rounds"] = [e.model_dump() if hasattr(e, 'model_dump') else e.dict() for e in events
                                     if hasattr(e, 'dict') or hasattr(e, 'model_dump')]

        # 按事件ID顺序排序
        sorted_rounds = sorted(
            round_gifs.items(),
            key=lambda x: int(x[0]) if x[0].isdigit() else float('inf')
        )

        print(f"准备发布 {len(sorted_rounds)} 个回合GIF (按事件顺序)")

        # 一次性生成所有回合解说
        print("正在一次性为所有回合生成解说内容...")
        round_ids = [int(event_id) for event_id, _ in sorted_rounds]
        all_round_analyses = content_generator.batch_generate_round_analyses(
            player_data, round_ids, player_name
        )

        print(f"成功生成 {len(all_round_analyses)} 个回合解说")

        # 发布回合，添加重试逻辑
        success_count = 0
        failure_count = 0

        # 定义重试函数
        def post_with_retry(gif_path, content, max_retries=3, initial_delay=60):
            retry_count = 0
            current_delay = initial_delay

            while retry_count < max_retries:
                try:
                    result = weibo_service.post_picture(
                        content=content,
                        image_paths=str(gif_path)
                    )

                    if result and result.get("success"):
                        return result, True

                    error_msg = result.get("message", "")
                    if "频率" in error_msg or "太快" in error_msg:
                        # 是API频率限制，需要等待
                        print(f"检测到API频率限制，等待 {current_delay} 秒后重试 ({retry_count + 1}/{max_retries})...")
                        time.sleep(current_delay)
                        # 指数退避，下次等待更长时间
                        current_delay *= 2
                        retry_count += 1
                    else:
                        # 其他错误，不重试
                        return result, False
                except Exception as e:
                    print(f"发布失败: {e}")
                    time.sleep(current_delay)
                    current_delay *= 2
                    retry_count += 1

            return {"success": False, "message": f"达到最大重试次数 ({max_retries})"}, False

        for i, (event_id, gif_path) in enumerate(sorted_rounds):
            try:
                # 获取预生成的解说
                round_content = all_round_analyses.get(int(event_id))
                if not round_content:
                    print(f"  × 回合 #{event_id} 未生成解说，跳过发布")
                    continue

                # 检查文件是否存在
                if not gif_path.exists():
                    print(f"  × 回合 #{event_id} 的GIF文件不存在: {gif_path}")
                    continue

                # 安全措施：对第一个以外的每个回合增加发布延迟
                if i > 0:
                    delay_time = 30  # 减少到30秒
                    print(f"等待 {delay_time} 秒后继续发布下一个回合，避免微博API限制...")
                    time.sleep(delay_time)

                print(f"发布回合 #{event_id} 解说和GIF: {gif_path.name}")
                print(f"  内容: {round_content[:50]}..." if len(round_content) > 50 else f"  内容: {round_content}")

                # 发布到微博，带重试机制
                result, success = post_with_retry(gif_path, round_content)

                # 检查结果
                if success:
                    print(f"  ✓ 回合 #{event_id} 发布成功")
                    success_count += 1
                else:
                    print(f"  × 回合 #{event_id} 发布失败: {result.get('message', '未知错误')}")
                    if "data" in result:
                        print(f"  详细信息: {result['data']}")
                    failure_count += 1

            except Exception as e:
                print(f"  × 发布回合 #{event_id} 失败: {str(e)}")
                failure_count += 1
                # 发生错误后增加一些额外等待
                print("发生错误，等待 30 秒后继续...")
                time.sleep(30)
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