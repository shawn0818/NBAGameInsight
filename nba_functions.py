"""NBA 数据服务的业务逻辑函数

将原main.py中的业务逻辑抽取为独立函数，便于调用和维护。
包含以下主要功能：
1. 比赛信息查询
2. 图表生成
3. 视频处理
4. AI分析
"""
import json
import re
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from config.nba_config import NBAConfig


def get_game_info(nba_service, ai_processor=None, content_generator=None):
    """获取比赛基本信息"""
    print("\n=== 比赛基本信息 ===")
    try:
        game_data = nba_service.data_service.get_game(nba_service.config.default_team)
        if not game_data:
            print(f"  获取比赛信息失败: 未找到{nba_service.config.default_team}的比赛数据")
            return None

        ai_data = game_data.prepare_ai_data()
        if "error" in ai_data:
            print(f"  获取比赛信息失败: {ai_data['error']}")
            return None

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
        if ai_processor and content_generator:
            try:
                summary = content_generator.generate_game_summary(ai_data)
                if summary:
                    print("\nAI比赛摘要:")
                    print(f"  {summary}")
            except Exception as e:
                logging.warning(f"AI摘要生成失败: {e}")

        return ai_data
    except Exception as e:
        logging.error(f"获取比赛信息失败: {e}", exc_info=True)
        print("  获取比赛信息时发生错误")
        return None


def get_game_narrative(nba_service, player_name=None, ai_processor=None):
    """获取比赛详细叙述"""
    print("\n=== 比赛详细叙述 ===")
    try:
        game_data = nba_service.data_service.get_game(nba_service.config.default_team)
        if not game_data:
            print(f"  获取比赛信息失败: 未找到{nba_service.config.default_team}的比赛数据")
            return None

        ai_data = game_data.prepare_ai_data()

        if ai_processor and "team_stats" in ai_data:
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
                narrative = ai_processor.generate(prompt)

                if narrative:
                    print("\n比赛叙述:")
                    print(narrative)
                else:
                    print("  未能使用AI生成比赛叙述")

            except Exception as ai_error:
                logging.warning(f"AI叙述生成失败: {ai_error}")
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

        # 显示球员数据
        if player_name:
            print(f"\n=== {player_name} 球员详细数据 ===")
            player_id = nba_service.get_player_id_by_name(player_name)
            player_data = game_data.prepare_ai_data(player_id=player_id)

            if "player_stats" in player_data:
                player_found = False
                for team_type in ["home", "away"]:
                    for player in player_data["player_stats"].get(team_type, []):
                        if player["basic"]["name"].lower() == player_name.lower():
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
                    print(f"  未找到 {player_name} 的数据")
            else:
                print(f"  未能获取 {player_name} 的球员数据")

        return ai_data
    except Exception as e:
        logging.error(f"获取比赛叙述失败: {e}", exc_info=True)
        print("  获取比赛叙述时发生错误")
        return None


def get_events_timeline(nba_service, team=None, player_name=None):
    """获取比赛事件时间线并进行分类展示"""
    print("\n=== 比赛事件时间线 ===")
    try:
        team = team or nba_service.config.default_team
        game_data = nba_service.data_service.get_game(team)
        if not game_data:
            print(f"  获取比赛信息失败: 未找到{team}的比赛数据")
            return None

        ai_data = game_data.prepare_ai_data()
        if "events" not in ai_data or "data" not in ai_data["events"]:
            print("  未找到事件数据")
            return None

        events = ai_data["events"]["data"]
        if not events:
            print("  事件数据为空")
            return None

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
        if player_name:
            player_id = nba_service.get_player_id_by_name(player_name)
            if player_id:
                player_events = [e for e in events if e.get("player_id") == player_id]
                if player_events:
                    print(f"\n{player_name} 的事件 (共{len(player_events)}个):")

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
                    print(f"  {player_name} 的事件:")
                    for i, event in enumerate(important_events, 1):
                        period = event.get("period", "")
                        clock = event.get("clock", "")
                        action_type = event.get("action_type", "")
                        description = event.get("description", "")
                        print(f"  {i}. 第{period}节 {clock} - {action_type}: {description}")
                else:
                    print(f"  未找到 {player_name} 的事件")

        return events
    except Exception as e:
        logging.error(f"获取事件时间线失败: {e}", exc_info=True)
        print("  获取事件时间线时发生错误")
        return None


def generate_shot_charts(nba_service, team=None, player_name=None):
    """生成投篮图表"""
    print("\n=== 投篮图表演示 ===")
    chart_paths = {}

    try:
        team = team or nba_service.config.default_team

        # 生成单个球员的投篮图
        if player_name:
            print(f"\n1. 生成 {player_name} 的个人投篮图")
            player_chart_path = nba_service.plot_player_scoring_impact(
                player_name=player_name
            )
            if player_chart_path:
                print(f"   ✓ 个人投篮图已生成: {player_chart_path}")
                chart_paths["player_chart"] = player_chart_path
            else:
                print("   × 个人投篮图生成失败")

        # 生成球队整体投篮图
        print(f"\n2. 生成 {team} 的球队投篮图")
        team_chart_path = nba_service.plot_team_shots(
            team=team
        )
        if team_chart_path:
            print(f"   ✓ 球队投篮图已生成: {team_chart_path}")
            chart_paths["team_chart"] = team_chart_path
        else:
            print("   × 球队投篮图生成失败")

        return chart_paths
    except Exception as e:
        logging.error(f"生成投篮图失败: {e}", exc_info=True)
        print(f"生成投篮图时发生错误: {e}")
        return chart_paths


def process_player_video(nba_service, player_name=None):
    """处理球员集锦视频"""
    print("\n=== 处理球员集锦视频 ===")
    video_paths = {}

    if not player_name:
        print("  × 未指定球员，跳过处理")
        return video_paths

    try:
        print(f"获取 {player_name} 的集锦视频")
        player_highlights = nba_service.get_player_highlights(
            player_name=player_name,
            merge=True,
            request_delay=1.0
        )

        if player_highlights:
            if isinstance(player_highlights, dict):
                if "merged" in player_highlights and isinstance(player_highlights["merged"], Path):
                    print(f"  ✓ 已生成合并视频: {player_highlights['merged']}")
                    video_paths["player_video"] = player_highlights["merged"]
                else:
                    print(f"  ✓ 获取到 {len(player_highlights)} 个视频片段")
                    for measure, paths in player_highlights.items():
                        if isinstance(paths, dict):
                            print(f"    {measure}: {len(paths)} 个片段")
        else:
            print("  × 获取球员集锦视频失败")

        return video_paths
    except Exception as e:
        logging.error(f"处理球员视频失败: {e}", exc_info=True)
        print(f"  × 处理球员视频时发生错误: {e}")
        return video_paths


def process_team_video(nba_service, team=None):
    """处理球队集锦视频"""
    print("\n=== 处理球队集锦视频 ===")
    video_paths = {}

    try:
        team = team or nba_service.config.default_team
        print(f"获取 {team} 的集锦视频")
        team_highlights = nba_service.get_team_highlights(
            team=team,
            merge=True
        )

        if team_highlights:
            if isinstance(team_highlights, dict):
                if "merged" in team_highlights and isinstance(team_highlights["merged"], Path):
                    print(f"  ✓ 已生成合并视频: {team_highlights['merged']}")
                    video_paths["team_video"] = team_highlights["merged"]
                else:
                    print(f"  ✓ 获取到 {len(team_highlights)} 个视频片段")
        else:
            print("  × 获取球队集锦视频失败")

        return video_paths
    except Exception as e:
        logging.error(f"处理球队视频失败: {e}", exc_info=True)
        print(f"  × 处理球队视频时发生错误: {e}")
        return video_paths


def process_player_round_gifs(nba_service, player_name=None):
    """基于已下载的视频处理球员回合GIF"""
    print("\n=== 处理球员回合GIF ===")
    round_gifs = {}

    if not player_name:
        print("  × 未指定球员，跳过处理")
        return round_gifs

    try:
        print(f"为 {player_name} 的集锦视频创建回合GIF")

        # 1. 获取球员ID和比赛数据，用于关联事件
        player_id = nba_service.get_player_id_by_name(player_name)
        if not player_id:
            print(f"  × 未找到球员 {player_name} 的ID")
            return round_gifs

        game = nba_service.data_service.get_game(nba_service.config.default_team)
        if not game:
            print(f"  × 未找到比赛数据")
            return round_gifs

        # 2. 查找已下载的视频文件
        video_dir = nba_service.video_service.config.output_dir
        video_files = list(video_dir.glob(f"*player{player_id}*.mp4"))

        if not video_files:
            print(f"  × 未找到球员 {player_name} 的视频文件")
            # 尝试下载视频
            print("尝试下载球员视频...")
            player_videos = process_player_video(nba_service, player_name)
            if not player_videos:
                return round_gifs
            # 重新检查视频文件
            video_files = list(video_dir.glob(f"*player{player_id}*.mp4"))
            if not video_files:
                print(f"  × 仍然未找到球员 {player_name} 的视频文件")
                return round_gifs

        print(f"找到 {len(video_files)} 个视频文件")

        # 3. 创建GIF输出目录
        gif_dir = NBAConfig.PATHS.GIF_DIR / f"player_rounds_{player_id}_{game.game_data.game_id}"
        gif_dir.mkdir(parents=True, exist_ok=True)

        # 4. 为每个视频创建对应的GIF
        gif_created = 0

        for video_path in video_files:
            try:
                # 从文件名中提取事件ID
                event_id = None
                match = re.search(r'event_(\d+)_', video_path.name)
                if match:
                    # 提取ID并去除前导零
                    event_id = match.group(1).lstrip('0')
                    # 如果全部都是零，那么至少保留一个零
                    if not event_id:
                        event_id = '0'

                print(f"处理事件 #{event_id} 的GIF: {video_path.name}")

                # 创建GIF文件名
                gif_path = gif_dir / f"round_{event_id}_{player_id}.gif"

                # 检查GIF是否已存在
                if gif_path.exists():
                    print(f"  ✓ GIF已存在: {gif_path}")
                    round_gifs[event_id] = gif_path
                    continue

                # 使用视频处理器创建GIF
                processor = nba_service.video_processor
                if not processor:
                    print("  × 视频处理器不可用，跳过GIF生成")
                    continue

                print(f"  生成GIF: {video_path.name}")
                result = processor.convert_to_gif(video_path, gif_path)

                if result:
                    round_gifs[event_id] = result
                    print(f"  ✓ GIF生成成功")
                    gif_created += 1
                else:
                    print(f"  × GIF生成失败")

            except Exception as e:
                print(f"  × 处理视频时出错: {e}")
                continue

        print(f"\n处理完成! 生成了 {gif_created} 个GIF")
        return round_gifs

    except Exception as e:
        logging.error(f"处理球员回合GIF失败: {e}", exc_info=True)
        print(f"  × 处理球员回合GIF失败: {e}")
        return round_gifs


def run_ai_analysis(nba_service, team=None, player_name=None, ai_processor=None, content_generator=None):
    """运行AI分析功能"""
    print("\n=== AI分析结果 ===")

    if not ai_processor:
        print("  × AI处理器未初始化，跳过分析")
        return None

    try:
        print("\n正在获取结构化数据并进行AI分析，这可能需要一些时间...")

        # 获取比赛数据
        team = team or nba_service.config.default_team
        game_data = nba_service.data_service.get_game(team)
        if not game_data:
            print(f"  获取比赛信息失败: 未找到{team}的比赛数据")
            return None

        # 使用Game模型的prepare_ai_data方法获取结构化数据
        player_id = None
        if player_name:
            player_id = nba_service.get_player_id_by_name(player_name)

        ai_formatted_data = game_data.prepare_ai_data(player_id=player_id)

        if "error" in ai_formatted_data:
            print(f"  × 获取数据失败: {ai_formatted_data['error']}")
            return None

        # 获取事件时间线并按重要性排序
        events = ai_formatted_data["events"]["data"] if "events" in ai_formatted_data else []

        # 使用内容生成器进行分析
        if content_generator:
            title = content_generator.generate_game_title(ai_formatted_data)
            summary = content_generator.generate_game_summary(ai_formatted_data)

            if player_name:
                player_analysis = content_generator.generate_player_analysis(
                    ai_formatted_data, player_name
                )

                # 显示分析结果
                print("\n比赛标题:")
                print(f"  {title}")

                print("\n比赛摘要:")
                print(summary)

                print(f"\n{player_name}表现分析:")
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
            ai_results = ai_processor.generate(prompt)

            if ai_results:
                print("\n比赛分析:")
                print(ai_results)
            else:
                print("  × AI分析未能产生任何结果")

        print("\nAI分析完成!")
        return ai_formatted_data

    except Exception as e:
        logging.error(f"AI分析功能执行失败: {e}", exc_info=True)
        print(f"  × AI分析失败: {e}")
        return None


def prepare_game_data(nba_service, team=None):
    """准备比赛数据，返回AI友好格式的数据"""
    team = team or nba_service.config.default_team
    game = nba_service.data_service.get_game(team)
    if not game:
        print(f"  获取比赛信息失败: 未找到{team}的比赛数据")
        return None

    # 获取AI友好格式数据
    ai_data = game.prepare_ai_data()
    if "error" in ai_data:
        print(f"  获取AI友好数据失败: {ai_data['error']}")
        return None

    return ai_data


def prepare_player_data(nba_service, player_name, game_data=None):
    """准备球员数据，返回包含球员数据的AI友好格式"""
    if not player_name:
        print(f"  未指定球员")
        return None

    # 如果没有传入game_data，则获取数据
    if not game_data:
        game_data = prepare_game_data(nba_service)
        if not game_data:
            return None

    player_id = nba_service.get_player_id_by_name(player_name)
    if not player_id:
        print(f"  未找到球员 {player_name} 的ID")
        return None

    player_ai_data = nba_service.data_service.get_game(nba_service.config.default_team).prepare_ai_data(
        player_id=player_id)
    return player_ai_data