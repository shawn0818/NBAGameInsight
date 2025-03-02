"""
微博内容生成器模块

负责为NBA数据生成适用于微博发布的内容，包括标题和正文。
基于Game模型的AI友好数据格式，使用AIProcessor进行内容创作。
"""

from typing import Dict, Any, Optional, List
import json
import logging


class WeiboContentGenerator:
    """微博内容生成工具类

    负责基于Game模型的AI友好数据，生成适用于微博发布的内容。
    不直接依赖NBA数据模型，仅通过AI友好的数据结构接口协作。
    """

    def __init__(self, ai_processor, logger=None):
        """初始化微博内容生成器

        Args:
            ai_processor: AI处理器实例，用于生成内容
            logger: 可选的日志记录器
        """
        self.ai_processor = ai_processor
        self.logger = logger or logging.getLogger(__name__)

    def generate_game_title(self, ai_data: Dict[str, Any]) -> str:
        """生成比赛标题"""
        try:
            if not ai_data or "error" in ai_data:
                return "NBA精彩比赛"

            # 提取基本比赛信息
            game_info = ai_data.get("game_info", {})
            home_team = game_info.get("teams", {}).get("home", {}).get("full_name", "主队")
            away_team = game_info.get("teams", {}).get("away", {}).get("full_name", "客队")

            # 获取比分
            home_score = 0
            away_score = 0
            if "game_status" in ai_data:
                home_score = ai_data["game_status"].get("score", {}).get("home", {}).get("points", 0)
                away_score = ai_data["game_status"].get("score", {}).get("away", {}).get("points", 0)

            # 确定获胜方
            winner = "主队"
            if home_score > away_score:
                winner = home_team
            else:
                winner = away_team

            # 构建提示词，明确要求中文标题
            prompt = f"""
            请为以下NBA比赛生成一个简洁有力的中文标题，要求：
            1. 必须用中文表达，包括所有球队名称
            2. 准确描述比赛结果（{winner}获胜）
            3. 比分为{away_score}-{home_score}
            4. 不超过15个中文字符
            5. 风格生动，吸引读者
            6. 不要使用英文和数字

            比赛信息：{json.dumps(game_info, ensure_ascii=False)}
            """

            title = self.ai_processor.generate(prompt)

            # 清理并检查结果
            title = title.strip().strip('"\'').strip()

            return title

        except Exception as e:
            self.logger.error(f"生成比赛标题失败: {e}")
            # 返回一个基本标题
            home_team = ai_data.get("game_info", {}).get("teams", {}).get("home", {}).get("tricode", "主队")
            away_team = ai_data.get("game_info", {}).get("teams", {}).get("away", {}).get("tricode", "客队")
            return f"{away_team} vs {home_team} 比赛集锦"

    def generate_game_summary(self, ai_data: Dict[str, Any]) -> str:
        """生成比赛摘要

        Args:
            ai_data: Game.prepare_ai_data()生成的AI友好数据

        Returns:
            str: 生成的比赛摘要
        """
        try:
            if not ai_data or "error" in ai_data:
                return ""

            # 提取核心比赛数据用于摘要生成
            summary_data = {}

            # 获取基本比赛信息
            if "game_info" in ai_data:
                summary_data["game_info"] = ai_data["game_info"]

            # 获取比赛状态和比分
            if "game_status" in ai_data:
                summary_data["game_status"] = ai_data["game_status"]

            # 获取比赛结果（如果已结束）
            if "game_result" in ai_data and ai_data["game_result"]:
                summary_data["game_result"] = ai_data["game_result"]

            # 获取球队统计数据（简化版本）
            if "team_stats" in ai_data:
                summary_data["team_stats"] = {
                    "home": {
                        "basic": ai_data["team_stats"]["home"]["basic"],
                        "shooting": ai_data["team_stats"]["home"]["shooting"]
                    },
                    "away": {
                        "basic": ai_data["team_stats"]["away"]["basic"],
                        "shooting": ai_data["team_stats"]["away"]["shooting"]
                    }
                }

            # 获取关键球员表现
            if "player_stats" in ai_data:
                top_players = []
                for team_type in ["home", "away"]:
                    if team_type in ai_data["player_stats"]:
                        players = ai_data["player_stats"][team_type]
                        if players and len(players) > 0:
                            # 按得分排序取前两名
                            sorted_players = sorted(players,
                                                    key=lambda p: p.get("basic", {}).get("points", 0),
                                                    reverse=True)[:2]
                            for player in sorted_players:
                                # 简化球员数据
                                basic = player.get("basic", {})
                                top_players.append({
                                    "name": basic.get("name", ""),
                                    "team": team_type,
                                    "points": basic.get("points", 0),
                                    "rebounds": basic.get("rebounds", 0),
                                    "assists": basic.get("assists", 0)
                                })

                summary_data["key_players"] = sorted(top_players,
                                                     key=lambda p: p.get("points", 0),
                                                     reverse=True)

            # 构建提示词
            prompt = f"""
            请为以下NBA比赛生成一段简洁的比赛总结，要求：
            1. 描述比赛结果和关键数据
            2. 提及关键球员表现
            3. 突出比赛转折点或精彩瞬间
            4. 控制在100-150字之间
            5. 语言生动，适合社交媒体发布

            比赛信息：{json.dumps(summary_data, ensure_ascii=False)}
            """

            return self.ai_processor.generate(prompt)

        except Exception as e:
            self.logger.error(f"生成比赛摘要失败: {e}")

            # 失败时返回基本信息
            try:
                home_team = ai_data.get("game_info", {}).get("teams", {}).get("home", {}).get("full_name", "主队")
                away_team = ai_data.get("game_info", {}).get("teams", {}).get("away", {}).get("full_name", "客队")
                home_score = ai_data.get("game_status", {}).get("score", {}).get("home", {}).get("points", "?")
                away_score = ai_data.get("game_status", {}).get("score", {}).get("away", {}).get("points", "?")

                return f"{away_team}对阵{home_team}的比赛，比分{away_score}-{home_score}。"
            except:
                return "NBA比赛精彩集锦。"

    def generate_player_analysis(self, ai_data: Dict[str, Any], player_name: str) -> str:
        """生成球员表现分析

        Args:
            ai_data: Game.prepare_ai_data()生成的AI友好数据（应包含player_stats）
            player_name: 球员姓名

        Returns:
            str: 球员分析文本
        """
        try:
            if not ai_data or not player_name or "error" in ai_data:
                return ""

            # 查找球员数据
            player_data = None
            team_type = None

            # 从AI友好数据中提取球员信息
            if "player_stats" in ai_data:
                for team in ["home", "away"]:
                    if team in ai_data["player_stats"]:
                        for player in ai_data["player_stats"][team]:
                            if player.get("basic", {}).get("name", "").lower() == player_name.lower():
                                player_data = player
                                team_type = team
                                break
                    if player_data:
                        break

            if not player_data:
                return f"未找到{player_name}的表现数据。"

            # 准备球员分析数据
            analysis_data = {
                "player_name": player_name,
                "team": team_type,
                "team_name": ai_data.get("game_info", {}).get("teams", {}).get(team_type, {}).get("full_name", ""),
                "opponent": "home" if team_type == "away" else "away",
                "opponent_name": ai_data.get("game_info", {}).get("teams", {}).get(
                    "home" if team_type == "away" else "away", {}).get("full_name", ""),
                "game_result": ai_data.get("game_result", {}),
                "player_stats": player_data,
                "game_info": ai_data.get("game_info", {})
            }

            # 构建提示词
            prompt = f"""
            请分析以下NBA球员在本场比赛中的表现，要求：
            1. 突出关键数据统计
            2. 分析其对比赛的影响
            3. 评价表现亮点和不足
            4. 控制在100-200字之间
            5. 适合社交媒体发布

            球员信息：{json.dumps(analysis_data, ensure_ascii=False)}
            """

            return self.ai_processor.generate(prompt)

        except Exception as e:
            self.logger.error(f"生成球员分析失败: {e}")
            return f"{player_name}在本场比赛中有出色表现。"

    def prepare_weibo_content(self,
                              ai_data: Dict[str, Any],
                              post_type: str = "game",
                              player_name: Optional[str] = None) -> Dict[str, str]:
        """准备微博发布内容

        Args:
            ai_data: Game.prepare_ai_data()生成的AI友好数据
            post_type: 发布类型，可选值: game(比赛), player(球员), chart(图表)
            player_name: 球员名称，仅当post_type为player或chart时需要

        Returns:
            Dict[str, str]: 包含title和content的字典
        """
        try:
            if not ai_data or "error" in ai_data:
                return {"title": "NBA精彩瞬间", "content": "NBA比赛精彩集锦 #NBA# #篮球#"}

            # 1. 生成标题（所有类型都需要）
            title = self.generate_game_title(ai_data)

            # 2. 根据不同类型生成内容
            if post_type == "game":
                # 比赛内容
                content = self._prepare_game_content(ai_data, title)
            elif post_type == "player" and player_name:
                # 球员内容
                content = self._prepare_player_content(ai_data, player_name, title)
            elif post_type == "chart" and player_name:
                # 投篮图表内容
                content = self._prepare_chart_content(ai_data, player_name, title)
            else:
                # 默认内容
                content = f"NBA精彩比赛 #NBA# #篮球#"

            # 3. 根据post_type修改标题
            if post_type == "player" and player_name:
                title = f"{title} - {player_name}个人集锦"
            elif post_type == "chart" and player_name:
                title = f"{title} - {player_name}投篮分布"

            return {
                "title": title.strip(),
                "content": content.strip()
            }

        except Exception as e:
            self.logger.error(f"准备微博内容失败: {e}")

            # 返回基本内容
            basic_title = "NBA比赛集锦"
            if post_type == "player" and player_name:
                basic_title = f"{player_name}个人集锦"
            elif post_type == "chart" and player_name:
                basic_title = f"{player_name}投篮分布图"

            return {
                "title": basic_title,
                "content": f"#NBA# #篮球# 精彩比赛片段"
            }

    def _prepare_game_content(self, ai_data: Dict[str, Any], title: str) -> str:
        """准备比赛集锦微博内容"""
        try:
            # 提取基本比赛信息
            game_info = ai_data.get("game_info", {})
            home_team = game_info.get("teams", {}).get("home", {}).get("full_name", "主队")
            away_team = game_info.get("teams", {}).get("away", {}).get("full_name", "客队")
            game_date = game_info.get("date", {}).get("beijing", "比赛日期")

            # 提取比分
            home_score = ai_data.get("game_status", {}).get("score", {}).get("home", {}).get("points", "?")
            away_score = ai_data.get("game_status", {}).get("score", {}).get("away", {}).get("points", "?")

            # 生成比赛摘要
            summary = self.generate_game_summary(ai_data)

            # 构建微博内容
            content = f"{game_date} NBA常规赛 {away_team}({away_score}) vs {home_team}({home_score})"

            if summary:
                content += f"\n\n{summary}"

            # 添加标签
            if "#NBA#" not in content:
                content += " #NBA# #篮球#"

            return content

        except Exception as e:
            self.logger.error(f"准备比赛内容失败: {e}")
            return f"#NBA# #篮球# 精彩比赛集锦"

    def _prepare_player_content(self, ai_data: Dict[str, Any], player_name: str, title: str) -> str:
        """准备球员集锦微博内容"""
        try:
            # 提取基本比赛信息
            game_info = ai_data.get("game_info", {})
            home_team = game_info.get("teams", {}).get("home", {}).get("full_name", "主队")
            away_team = game_info.get("teams", {}).get("away", {}).get("full_name", "客队")
            game_date = game_info.get("date", {}).get("beijing", "比赛日期")

            # 提取比分
            home_score = ai_data.get("game_status", {}).get("score", {}).get("home", {}).get("points", "?")
            away_score = ai_data.get("game_status", {}).get("score", {}).get("away", {}).get("points", "?")

            # 基础比赛信息
            content = f"{game_date} NBA常规赛 {away_team}({away_score}) vs {home_team}({home_score})"

            # 添加球员分析
            player_analysis = self.generate_player_analysis(ai_data, player_name)
            if player_analysis:
                content += f"\n\n{player_analysis}"

            # 添加标签
            if "#NBA#" not in content:
                content += " #NBA# #篮球#"

            if f"#{player_name}#" not in content:
                content += f" #{player_name}#"

            return content

        except Exception as e:
            self.logger.error(f"准备球员内容失败: {e}")
            return f"#{player_name}# #NBA# #篮球# 个人精彩表现"

    def _prepare_chart_content(self, ai_data: Dict[str, Any], player_name: str, title: str) -> str:
        """准备投篮图表微博内容"""
        try:
            # 提取基本比赛信息
            game_info = ai_data.get("game_info", {})
            home_team = game_info.get("teams", {}).get("home", {}).get("full_name", "主队")
            away_team = game_info.get("teams", {}).get("away", {}).get("full_name", "客队")
            game_date = game_info.get("date", {}).get("beijing", "比赛日期")

            # 提取比分
            home_score = ai_data.get("game_status", {}).get("score", {}).get("home", {}).get("points", "?")
            away_score = ai_data.get("game_status", {}).get("score", {}).get("away", {}).get("points", "?")

            # 基础比赛信息
            content = f"{game_date} {away_team} vs {home_team}"

            # 球员投篮信息
            content += f"\n{player_name}本场比赛投篮分布图"

            # 查找球员在这场比赛的投篮数据
            shooting_data = None
            if "player_stats" in ai_data:
                for team in ["home", "away"]:
                    if team in ai_data["player_stats"]:
                        for player in ai_data["player_stats"][team]:
                            if player.get("basic", {}).get("name", "").lower() == player_name.lower():
                                shooting = player.get("shooting", {})
                                if shooting:
                                    # 添加投篮数据说明
                                    fg = shooting.get("field_goals", {})
                                    three = shooting.get("three_pointers", {})

                                    content += f"\n投篮: {fg.get('made', 0)}/{fg.get('attempted', 0)}"
                                    if "percentage" in fg:
                                        content += f" ({fg.get('percentage', 0)}%)"

                                    content += f"\n三分: {three.get('made', 0)}/{three.get('attempted', 0)}"
                                    if "percentage" in three:
                                        content += f" ({three.get('percentage', 0)}%)"

                                    points = player.get("basic", {}).get("points", 0)
                                    content += f"\n得分: {points}分"
                                break

            # 添加标签
            if "#NBA#" not in content:
                content += " #NBA# #篮球#"

            if "#数据可视化#" not in content:
                content += " #数据可视化#"

            if f"#{player_name}#" not in content:
                content += f" #{player_name}#"

            return content

        except Exception as e:
            self.logger.error(f"准备图表内容失败: {e}")
            return f"#{player_name}# #NBA# #数据可视化# 投篮分布图"