"""
AI分析命令 - 处理AI生成的比赛和球员分析
"""
from typing import Dict, Any, Optional

from commands.base_command import NBACommand, error_handler


class AICommand(NBACommand):
    """AI分析命令 (显示结果)"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("AI 分析结果 (显示)")

        if not app.ai_service:
            print("× AI 服务不可用，无法执行分析。")
            return False

        print("\n正在准备数据并进行AI分析...")

        # 1. 获取基础比赛数据 (用于获取 game_id)
        game = app.get_game_data()
        if not game:
            return False # Error printed in get_game_data

        game_id = game.game_data.game_id
        team_id = app.get_team_id(app.config.team) # Need team_id for context

        if not team_id:
             return False # Error printed in get_team_id

        # 2. 生成比赛整体内容
        print("\n--- 比赛分析 ---")
        game_content = app.ai_service.generate_game_content(team_id=team_id, game_id=game_id)
        if game_content.get("status") == "success":
            print(f"标题: {game_content['content'].get('title', 'N/A')}")
            print(f"摘要:\n{game_content['content'].get('summary', 'N/A')}")
        else:
            print(f"× 生成比赛分析失败: {game_content.get('message', '未知错误')}")

        # 3. 如果指定球员，生成球员分析
        if app.config.player:
            print(f"\n--- 球员 {app.config.player} 分析 ---")
            player_id = app.get_player_id(app.config.player)
            if player_id:
                player_content = app.ai_service.generate_player_content(
                    player_id=player_id,
                    game_id=game_id,
                    team_id=team_id, # Provide team context
                    include_shot_chart=False, # Don't need chart text for display here
                    include_rounds=False     # Don't need rounds text for display here
                )
                if player_content.get("status") == "success":
                    print(f"分析:\n{player_content['content'].get('player_analysis', 'N/A')}")
                else:
                    print(f"× 生成球员分析失败: {player_content.get('message', '未知错误')}")

        print("\nAI 分析显示完成。")
        return True # Even if parts failed, the command itself ran