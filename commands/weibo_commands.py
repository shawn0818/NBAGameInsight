"""
微博发布命令模块 - 处理微博内容发布相关功能

实现将图表、视频和AI生成内容发布到微博平台
"""
from typing import Dict, Any, Optional, Union, List
from pathlib import Path

from commands.base_command import NBACommand, error_handler


class WeiboCommand(NBACommand):
    """微博发布命令基类"""

    def _check_required_files(self, app, mode) -> bool:
        """检查微博发布所需的文件"""
        return app.check_required_files_for_weibo(mode)

    def _generate_weibo_content(self, app, content_type: str, **kwargs) -> Optional[str]:
        """Helper to generate content using AIService"""
        if not app.ai_service:
            app.logger.warning("AI 服务不可用，无法生成微博内容，将使用默认文本。")
            return None

        game_id = kwargs.get("game_id")
        team_id = kwargs.get("team_id")
        player_id = kwargs.get("player_id")
        player_name = kwargs.get("player_name")
        team_name = kwargs.get("team_name")
        round_ids = kwargs.get("round_ids")

        try:
            # 准备数据上下文
            prepared_data = app.get_prepared_data(game_id=game_id, team_id=team_id, player_id=player_id)
            if not prepared_data or "error" in prepared_data:
                app.logger.error(f"准备微博内容数据失败: {prepared_data.get('error', '未知错误')}")
                return None

            # 添加特定生成器需要的额外参数
            gen_kwargs = {}
            if content_type == "round_analysis":
                gen_kwargs["round_ids"] = round_ids
                gen_kwargs["player_name"] = player_name

            # 生成内容
            result = app.ai_service.generate_content_for_weibo(
                content_type=content_type,
                data=prepared_data,
                **gen_kwargs
            )

            if result.get("status") == "success":
                # 处理批量回合分析的特殊情况
                content = result.get("content")
                if content_type == "batch_round_analyses" and isinstance(content, dict):
                    # 基本格式化，用于显示/发布
                    formatted_content = f"{player_name} 精彩回合解析:\n\n" + "\n\n".join(
                        f"回合 {rid}: {analysis}" for rid, analysis in content.items()
                    )
                    return formatted_content + f"\n\n#NBA# #篮球# #{player_name}# #{team_name}#"
                elif isinstance(content, str):
                    # 添加默认标签（如果尚未存在）
                    final_content = content
                    tags_to_add = ["#NBA#", "#篮球#"]
                    if team_name: tags_to_add.append(f"#{team_name}#")
                    if player_name: tags_to_add.append(f"#{player_name}#")

                    if not all(tag in final_content for tag in ["#NBA#", "#篮球#"]):
                        final_content += "\n\n" + " ".join(tags_to_add)
                    return final_content
                else:
                    app.logger.warning(f"AI 生成的内容格式未知: {type(content)}")
                    return None
            else:
                app.logger.error(f"使用 AI 生成内容 '{content_type}' 失败: {result.get('message', '未知错误')}")
                return None

        except Exception as e:
            app.logger.error(f"生成微博内容 '{content_type}' 时发生异常: {e}", exc_info=True)
            return None

    def _post_to_weibo(self, app, post_type: str,
                       media_path: Union[str, Path, List[Union[str, Path]], None],
                       content: str,
                       title: Optional[str] = None) -> bool:
        """Helper to post content to Weibo"""
        if not app.weibo_service:
            print("× 微博服务不可用，跳过发布。")
            return False

        print(f"  准备发布 {post_type} 到微博...")
        print(f"  内容预览:\n{content[:150]}{'...' if len(content) > 150 else ''}")
        if media_path:
            print(f"  媒体文件: {media_path}")

        try:
            # 确定内容类型
            if post_type in ["球队视频", "球员视频"]:
                service_content_type = "video"
            elif post_type in ["球员投篮图", "球队投篮图", "影响力图", "全场图"]:
                service_content_type = "picture"
            elif post_type == "球员回合GIF":
                service_content_type = "gif"
            elif post_type == "球队赛后评级":
                service_content_type = "text"
                media_path = None
            else:
                print(f"× 未知的发布类型: {post_type}")
                return False

            result = app.weibo_service.post_content(
                content_type=service_content_type,
                media_path=media_path,
                content=content,
                title=title
            )

            if result and result.get("success"):
                print(f"✓ {post_type} 发布成功!")
                return True
            else:
                print(f"× {post_type} 发布失败: {result.get('message', '未知错误')}")
                # 记录详细错误信息
                if result and "data" in result:
                    app.logger.error(f"微博API失败详情 ({post_type}): {result['data']}")
                return False
        except Exception as e:
            app.logger.error(f"发布 {post_type} 到微博时发生异常: {e}", exc_info=True)
            print(f"× 发布 {post_type} 到微博时发生异常: {e}")
            return False


class WeiboTeamCommand(WeiboCommand):
    """微博发布球队视频命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("微博发布球队集锦视频")

        # 检查所需文件
        if not self._check_required_files(app, app.config.mode):
            return False

        # 获取基础数据
        game = app.get_game_data()
        if not game: return False
        team_id = app.get_team_id(app.config.team)
        if not team_id: return False

        # 生成微博内容
        content = self._generate_weibo_content(
            app,
            "game_summary",
            game_id=game.game_data.game_id,
            team_id=team_id,
            team_name=app.config.team
        )
        content = content or f"{app.config.team} 比赛集锦\n\n#NBA# #篮球# #{app.config.team}#"  # 默认内容
        title = f"{app.config.team} 比赛集锦"

        # 发布到微博
        return self._post_to_weibo(app, "球队视频", app.video_paths.get("team_video"), content, title)


class WeiboPlayerCommand(WeiboCommand):
    """微博发布球员视频命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("微博发布球员集锦视频")

        # 检查所需文件
        if not self._check_required_files(app, app.config.mode): return False
        if not app.config.player:
            print("× 未指定球员")
            return False

        # 获取基础数据
        game = app.get_game_data()
        if not game: return False
        player_id = app.get_player_id(app.config.player)
        if not player_id: return False
        team_id = app.get_team_id(app.config.team)
        if not team_id: return False

        # 生成微博内容
        content = self._generate_weibo_content(
            app,
            "player_analysis",
            game_id=game.game_data.game_id,
            player_id=player_id,
            player_name=app.config.player,
            team_id=team_id,
            team_name=app.config.team
        )
        content = content or f"{app.config.player} 精彩表现\n\n#NBA# #篮球# #{app.config.player}#"  # 默认内容
        title = f"{app.config.player} 精彩表现"

        # 发布到微博
        return self._post_to_weibo(app, "球员视频", app.video_paths.get("player_video"), content, title)


class WeiboChartCommand(WeiboCommand):
    """微博发布球员投篮图命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("微博发布球员投篮图")

        # 检查所需文件
        if not self._check_required_files(app, app.config.mode): return False
        if not app.config.player:
            print("× 未指定球员")
            return False

        # 获取基础数据
        game = app.get_game_data()
        if not game: return False
        player_id = app.get_player_id(app.config.player)
        if not player_id: return False
        team_id = app.get_team_id(app.config.team)
        if not team_id: return False

        # 生成微博内容
        content = self._generate_weibo_content(
            app,
            "shot_chart_text",
            game_id=game.game_data.game_id,
            player_id=player_id,
            player_name=app.config.player,
            team_id=team_id,
            team_name=app.config.team
        )
        content = content or f"{app.config.player} 本场投篮点分布\n\n#NBA# #篮球# #{app.config.player}#"  # 默认内容

        # 发布到微博
        return self._post_to_weibo(app, "球员投篮图", app.chart_paths.get("player_chart"), content)


class WeiboTeamChartCommand(WeiboCommand):
    """微博发布球队投篮图命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("微博发布球队投篮图")

        # 检查所需文件
        if not self._check_required_files(app, app.config.mode): return False

        # 获取基础数据
        game = app.get_game_data()
        if not game: return False
        team_id = app.get_team_id(app.config.team)
        if not team_id: return False

        # 生成微博内容
        content = self._generate_weibo_content(
            app,
            "team_shot_analysis",
            game_id=game.game_data.game_id,
            team_id=team_id,
            team_name=app.config.team
        )
        content = content or f"{app.config.team} 本场投篮点分布\n\n#NBA# #篮球# #{app.config.team}#"  # 默认内容

        # 发布到微博
        return self._post_to_weibo(app, "球队投篮图", app.chart_paths.get("team_chart"), content)


class WeiboRoundCommand(WeiboCommand):
    """微博发布球员回合解说和GIF命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("微博发布球员回合解说和GIF")

        # 检查所需文件
        if not self._check_required_files(app, app.config.mode): return False
        if not app.config.player:
            print("× 未指定球员")
            return False

        # 获取基础数据
        game = app.get_game_data()
        if not game: return False
        player_id = app.get_player_id(app.config.player)
        if not player_id: return False
        team_id = app.get_team_id(app.config.team)
        if not team_id: return False

        # 提取回合ID
        round_ids = []
        if app.round_gifs:
            round_ids = [int(rid) for rid in app.round_gifs.keys() if rid.isdigit()]

        if not round_ids:
            print("× 未找到可用的球员回合 GIF 或回合 ID")
            return False

        # 选择要发布的GIF
        first_gif_event_id = str(min(round_ids))
        first_gif_event_id = next(iter(app.round_gifs.keys()), None)
        media_path = app.round_gifs.get(first_gif_event_id)

        if not media_path:
            print(f"× 未找到事件 ID '{first_gif_event_id}' 对应的 GIF 文件")
            return False

        # 生成回合分析内容
        content = self._generate_weibo_content(
            app,
            "batch_round_analyses",
            game_id=game.game_data.game_id,
            player_id=player_id,
            player_name=app.config.player,
            team_id=team_id,
            team_name=app.config.team,
            round_ids=round_ids[:5]  # 限制分析前5个回合
        )
        content = content or f"{app.config.player} 精彩回合集锦\n\n#NBA# #篮球# #{app.config.player}#"  # 默认内容

        # 发布到微博
        return self._post_to_weibo(app, "球员回合GIF", media_path, content)


class WeiboTeamRatingCommand(WeiboCommand):
    """微博发布球队赛后评级命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("微博发布球队赛后评级")

        # 获取基础数据
        game = app.get_game_data()
        if not game: return False
        team_id = app.get_team_id(app.config.team)
        if not team_id: return False

        # 检查比赛是否结束
        game_status = getattr(game.game_data, "game_status", 0)
        if game_status != 3:
            print("× 比赛尚未结束，无法发布赛后评级。")
            return False

        # 生成内容
        content = self._generate_weibo_content(
            app,
            "game_summary",
            game_id=game.game_data.game_id,
            team_id=team_id,
            team_name=app.config.team
        )
        content = content or f"{app.config.team} 赛后总结。\n\n#NBA# #篮球# #{app.config.team}#"  # 默认内容

        # 获取标题
        title_content = self._generate_weibo_content(
            app,
            "game_title",
            game_id=game.game_data.game_id,
            team_id=team_id,
            team_name=app.config.team
        )
        title = title_content or f"{app.config.team} 赛后评级"
        final_content = f"{title}\n\n{content}"

        # 发布到微博 (纯文本)
        return self._post_to_weibo(app, "球队赛后评级", None, final_content)