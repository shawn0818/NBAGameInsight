from typing import Dict, Any, Optional, List
import json
import logging
import re
import time
from utils.time_handler import TimeHandler
from enum import Enum


class ContentType(Enum):
    """微博模块常量定义"""

    #微博内容类型
    TEAM_VIDEO = "team_video"
    PLAYER_VIDEO = "player_video"
    PLAYER_CHART = "player_chart"
    TEAM_CHART = "team_chart"
    ROUND_ANALYSIS = "round_analysis"
    # 常用标签
    NBA_HASHTAG = "#NBA#"
    BASKETBALL_HASHTAG = "#篮球#"


class WeiboContentGenerator:
    """
    微博内容生成工具类

    负责基于AI友好数据生成适用于微博发布的内容，不直接依赖具体的数据模型。
    """

    def __init__(self, ai_processor: Any, logger: Optional[logging.Logger] = None, debug_mode: bool = False) -> None:
        """
        初始化微博内容生成器

        Args:
            ai_processor: AI处理器实例，用于生成内容
            logger: 可选的日志记录器
            debug_mode: 是否启用调试模式
        """
        self.ai_processor = ai_processor
        self.logger = logger or logging.getLogger(__name__)
        self.debug_mode = debug_mode
        self.start_time = 0

    # === 公开的内容生成接口 ===

    def generate_content(self, content_type: str, ai_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """统一内容生成接口

        Args:
            content_type: 内容类型，如"team_video"，"player_video"等
            ai_data: AI友好数据
            **kwargs: 其他参数，如player_name等

        Returns:
            Dict: 包含内容的字典
        """
        # 根据内容类型调用相应的方法
        if content_type == "team_video":
            return self.generate_team_video_content(ai_data)

        elif content_type == "player_video":
            player_name = kwargs.get("player_name")
            if not player_name:
                raise ValueError("生成球员视频内容需要提供player_name参数")
            return self.generate_player_video_content(ai_data, player_name)

        elif content_type == "player_chart":
            player_name = kwargs.get("player_name")
            if not player_name:
                raise ValueError("生成球员投篮图内容需要提供player_name参数")
            return self.generate_player_chart_content(ai_data, player_name)

        elif content_type == "team_chart":
            team_name = kwargs.get("team_name")
            if not team_name:
                raise ValueError("生成球队投篮图内容需要提供team_name参数")
            return self.generate_team_chart_content(ai_data, team_name)

        elif content_type == "round_analysis":
            player_name = kwargs.get("player_name")
            round_ids = kwargs.get("round_ids")
            if not player_name or not round_ids:
                raise ValueError("生成回合解说内容需要提供player_name和round_ids参数")
            return self.generate_player_rounds_content(ai_data, player_name, round_ids)

        else:
            raise ValueError(f"不支持的内容类型: {content_type}")

    # === 按发布类型分类的内容生成方法 ===

    def generate_team_video_content(self, ai_data: Dict[str, Any]) -> Dict[str, str]:
        """生成球队集锦视频内容，对应post_team_video方法

        生成侧重点:
        - 标题：强调比赛整体性质、双方对阵、最终比分
        - 内容：包含比赛全局分析、团队表现、比赛关键时刻

        Returns:
            Dict包含 title, content (已包含hashtags)
        """
        if self.debug_mode:
            self._log_start("球队集锦视频")

        # 生成标题和摘要
        title = self.generate_game_title(ai_data)
        game_summary = self.generate_game_summary(ai_data)
        hashtags = f"{ContentType.NBA_HASHTAG.value} {ContentType.BASKETBALL_HASHTAG.value}"

        content = f"{game_summary}\n\n{hashtags}"

        result = {"title": title, "content": content}

        if self.debug_mode:
            self._log_result("球队集锦视频", result)

        return result

    def generate_player_video_content(self, ai_data: Dict[str, Any], player_name: str) -> Dict[str, str]:
        """生成球员集锦视频内容，对应post_player_video方法

        生成侧重点:
        - 标题：在比赛标题基础上突出球员个人表现
        - 内容：专注于球员表现亮点、技术特点、影响力分析

        Args:
            ai_data: AI友好数据
            player_name: 球员名称

        Returns:
            Dict包含 title, content (已包含hashtags)
        """
        if self.debug_mode:
            self._log_start(f"球员({player_name})集锦视频")

        # 生成标题和球员分析
        game_title = self.generate_game_title(ai_data)
        player_title = f"{game_title} - {player_name}个人集锦"
        player_analysis = self.generate_player_analysis(ai_data, player_name)
        hashtags = f"{ContentType.NBA_HASHTAG.value} {ContentType.BASKETBALL_HASHTAG.value} #{player_name}#"

        content = f"{player_analysis}\n\n{hashtags}"

        result = {"title": player_title, "content": content}

        if self.debug_mode:
            self._log_result(f"球员({player_name})集锦视频", result)

        return result

    def generate_player_chart_content(self, ai_data: Dict[str, Any], player_name: str) -> Dict[str, str]:
        """生成球员投篮图内容，对应post_player_chart方法

        生成侧重点:
        - 内容：专注于球员投篮数据分析、命中率、投篮热区分布

        Returns:
            Dict包含 title, content (已包含hashtags)
        """
        if self.debug_mode:
            self._log_start(f"球员({player_name})投篮图")

        game_title = self.generate_game_title(ai_data)
        shot_chart_title = f"{game_title} - {player_name}投篮分布"
        shot_chart_text = self.generate_shot_chart_text(ai_data, player_name)
        hashtags = f"{ContentType.NBA_HASHTAG.value} {ContentType.BASKETBALL_HASHTAG.value} #{player_name}#"

        content = f"{player_name}本场比赛投篮分布图\n\n{shot_chart_text}\n\n{hashtags}"

        result = {"title": shot_chart_title, "content": content}

        if self.debug_mode:
            self._log_result(f"球员({player_name})投篮图", result)

        return result

    def generate_team_chart_content(self, ai_data: Dict[str, Any], team_name: str) -> Dict[str, str]:
        """生成球队投篮图内容，对应post_team_chart方法

        生成侧重点:
        - 内容：专注于球队整体投篮分布、命中率热区和战术倾向

        Returns:
            Dict包含 title, content (已包含hashtags)
        """
        if self.debug_mode:
            self._log_start(f"球队({team_name})投篮图")

        game_title = self.generate_game_title(ai_data)
        team_chart_title = f"{game_title} - {team_name}球队投篮分布"
        team_shot_analysis = self.generate_team_shot_analysis(ai_data, team_name)
        hashtags = f"{ContentType.NBA_HASHTAG.value} {ContentType.BASKETBALL_HASHTAG.value} #{team_name}#"

        content = f"{team_name}球队本场比赛投篮分布图\n\n{team_shot_analysis}\n\n{hashtags}"

        result = {"title": team_chart_title, "content": content}

        if self.debug_mode:
            self._log_result(f"球队({team_name})投篮图", result)

        return result

    def generate_player_rounds_content(self, ai_data: Dict[str, Any], player_name: str, round_ids: List[int]) -> Dict[
        str, Any]:
        """生成球员回合解说内容，对应post_player_rounds方法

        生成侧重点:
        - 内容：针对每个回合的详细解说，突出球员关键表现和技术细节

        Returns:
            包含所有回合解说的字典，格式为 {"analyses": {round_id: 解说内容}}
        """
        if self.debug_mode:
            self._log_start(f"球员({player_name})回合解说")

        # 批量生成回合解说
        analyses = self._batch_generate_round_analyses(ai_data, round_ids, player_name)

        # 为缺失的回合生成简单解说
        for round_id in round_ids:
            if round_id not in analyses:
                analyses[round_id] = self._generate_simple_round_content(
                    ai_data, round_id, player_name
                )

        if self.debug_mode:
            self._log_result(f"球员({player_name})回合解说",
                             {"rounds_count": len(analyses),
                              "sample": next(iter(analyses.values())) if analyses else ""})

        # 将整数键转换为字符串键，并包装在一个字典中返回
        result = {
            "analyses": {str(round_id): content for round_id, content in analyses.items()}
        }

        return result

    # === 基础内容生成方法 ===

    def generate_game_title(self, ai_data: Dict[str, Any]) -> str:
        """
        生成比赛标题 - 直接使用单独的prompt

        Returns:
            生成的比赛标题字符串
        """
        if self.debug_mode:
            self._log_start("比赛标题")

        if not ai_data or "error" in ai_data:
            return "NBA精彩比赛"

        # 比赛标题prompt
        prompt = (
            "你是一名洛杉矶湖人队的**铁杆**球迷和体育记者，对湖人队的每场比赛都充满热情，即使是失利也依然深爱着这支球队。"
            "你擅长为NBA比赛创作简洁有力的中文标题\n"
            "请基于以下信息生成一个中文标题，要求：\n"
            "1. 必须用中文表达，包括所有球队名称（{home_team} 和 {away_team}）；\n"
            "2. 明确包含比赛最终比分并强调胜负结果（{home_score} : {away_score}）；注意胜负需要从湖人的视角看待。\n"
            "3. 标题字数控制在20字以内，简洁明了且适合社交媒体传播。\n"
            "4. 可以参考古典书名/章节风格，并适度使用Emoji来吸引注意。\n"
            "比赛信息：{game_info}"
        )

        team_info = self._get_team_info(ai_data)
        game_info = ai_data.get("game_info", {})
        scores = self._get_game_scores(ai_data)
        prompt = prompt.format(
            home_team=team_info["home_full"],
            away_team=team_info["away_full"],
            home_score=scores["home_score"],
            away_score=scores["away_score"],
            game_info=json.dumps(game_info, ensure_ascii=False)
        )
        try:
            title = self.ai_processor.generate(prompt)
            result = title.strip().strip('"\'')

            if self.debug_mode:
                self._log_result("比赛标题", {"title": result})

            return result
        except Exception as e:
            self.logger.error(f"生成比赛标题失败: {e}", exc_info=True)
            return f"{team_info['away_tricode']} vs {team_info['home_tricode']} 比赛集锦"

    def generate_game_summary(self, ai_data: Dict[str, Any]) -> str:
        """
        生成比赛摘要 - 直接使用单独的prompt

        Returns:
            生成的比赛摘要字符串
        """
        if self.debug_mode:
            self._log_start("比赛摘要")

        if not ai_data or "error" in ai_data:
            return ""

        # 比赛摘要prompt
        prompt = (
            "你是一名洛杉矶湖人队的**铁杆**球迷同时也是专业的体育记者，更是勒布朗的资深粉丝！擅长为NBA比赛创作生动简洁的比赛总结。\n"
            "请根据以下比赛信息生成一段150-200字的中文比赛摘要，要求：\n"
            "1. 详细总结比赛的关键数据（如得分、篮板、助攻等）；\n"
            "2. 仔细查看提供数据中的关于比赛回合的部分，突出比赛过程中的关键转折点和重要时刻；\n"
            "3. 提及湖人队表现突出的1-3名球员，尤其是球队在进攻、组织、防守端表现较好的球员，并结合数据进行分析；\n"
            "4. 使用生动语言，适合社交媒体发布，适当使用emoji。\n"
            "5. 所有球队和球员名称均用中文，百分数只保留小数点后两位。\n"
            "比赛信息：{summary_data}"
        )

        summary_data = {}
        for key in ["game_info", "game_status", "game_result"]:
            if key in ai_data and ai_data[key]:
                summary_data[key] = ai_data[key]
        if "team_stats" in ai_data:
            summary_data["team_stats"] = {
                "home": {
                    "basic": ai_data["team_stats"]["home"].get("basic", {}),
                    "shooting": ai_data["team_stats"]["home"].get("shooting", {})
                },
                "away": {
                    "basic": ai_data["team_stats"]["away"].get("basic", {}),
                    "shooting": ai_data["team_stats"]["away"].get("shooting", {})
                }
            }
        if "player_stats" in ai_data:
            top_players = []
            for team in ["home", "away"]:
                players = ai_data.get("player_stats", {}).get(team, [])
                if players:
                    sorted_players = sorted(
                        players,
                        key=lambda p: p.get("basic", {}).get("points", 0),
                        reverse=True
                    )[:2]
                    for player in sorted_players:
                        basic = player.get("basic", {})
                        top_players.append({
                            "name": basic.get("name", ""),
                            "team": team,
                            "points": basic.get("points", 0),
                            "rebounds": basic.get("rebounds", 0),
                            "assists": basic.get("assists", 0)
                        })
            summary_data["key_players"] = sorted(top_players, key=lambda p: p.get("points", 0), reverse=True)

        prompt = prompt.format(
            summary_data=json.dumps(summary_data, ensure_ascii=False)
        )
        try:
            result = self.ai_processor.generate(prompt).strip()

            if self.debug_mode:
                self._log_result("比赛摘要", {"summary_length": len(result),
                                              "preview": result[:100] + "..." if len(result) > 100 else result})

            return result
        except Exception as e:
            self.logger.error(f"生成比赛摘要失败: {e}", exc_info=True)
            team_info = self._get_team_info(ai_data)
            return (
                f"{team_info['away_full']}对阵{team_info['home_full']}的比赛，"
                f"比分{self._get_game_scores(ai_data)['away_score']}-"
                f"{self._get_game_scores(ai_data)['home_score']}。"
            )

    def generate_player_analysis(self, ai_data: Dict[str, Any], player_name: str) -> str:
        """
        生成球员表现分析 - 直接使用单独的prompt

        Returns:
            生成的球员分析字符串
        """
        if self.debug_mode:
            self._log_start(f"球员分析({player_name})")

        if not ai_data or not player_name or "error" in ai_data:
            return ""

        # 球员分析prompt
        prompt = (
            "你是一名NBA球员分析师，也是洛杉矶湖人队的**铁杆**球迷，更是勒布朗的资深粉丝！擅长通过数据和比赛表现分析球员影响力。\n"
            "请分析以下球员在本场比赛中的表现，要求：\n"
            "1. 仔细查看提供数据中的关于比赛回合的部分，针对球员本场比赛的表现进行深入剖析；\n"
            "2. 突出关键数据，并分析这些数据对比赛结果的影响，注意百分数只保留小数点后两位；\n"
            "3. 全面客观地评价球员的表现（此处可以适当语言犀利或者幽默，但是不能刻薄、不尊重）；\n"
            "4. 控制在100-200字之间；\n"
            "5. 适合社交媒体发布，可适度加入中式幽默，适当使用emoji；\n"
            "6. 所有专业术语用中文，球员名字也要使用中文。\n"
            "球员信息：{analysis_data}"
        )

        player_data = None
        team_type = None
        for team in ["home", "away"]:
            for player in ai_data.get("player_stats", {}).get(team, []):
                if player.get("basic", {}).get("name", "").lower() == player_name.lower():
                    player_data = player
                    team_type = team
                    break
            if player_data:
                break

        if not player_data:
            return f"未找到{player_name}的表现数据。"

        analysis_data = {
            "player_name": player_name,
            "team": team_type,
            "team_name": self._get_team_info(ai_data).get(f"{team_type}_full", ""),
            "opponent": "home" if team_type == "away" else "away",
            "opponent_name": self._get_team_info(ai_data).get("home_full" if team_type == "away" else "away_full", ""),
            "game_result": ai_data.get("game_result", {}),
            "player_stats": player_data,
            "game_info": ai_data.get("game_info", {})
        }
        prompt = prompt.format(
            analysis_data=json.dumps(analysis_data, ensure_ascii=False)
        )
        try:
            result = self.ai_processor.generate(prompt).strip()

            if self.debug_mode:
                self._log_result(f"球员分析({player_name})", {"analysis_length": len(result),
                                                              "preview": result[:100] + "..." if len(
                                                                  result) > 100 else result})

            return result
        except Exception as e:
            self.logger.error(f"生成球员分析失败: {e}", exc_info=True)
            return f"{player_name}在本场比赛中有出色表现。"

    def generate_shot_chart_text(self, ai_data: Dict[str, Any], player_name: str) -> str:
        """
        生成球员投篮图解说 - 使用单独的prompt

        Returns:
            生成的投篮图解说字符串
        """
        if self.debug_mode:
            self._log_start(f"球员投篮图解说({player_name})")

        if not ai_data or not player_name or "error" in ai_data:
            return f"{player_name}本场比赛的投篮分布图显示了他的得分热区和命中情况。"

        # 球员投篮图解说prompt
        prompt = (
            "你是一名NBA投篮分析专家，也是洛杉矶湖人队的**铁杆**球迷，更是勒布朗的资深粉丝！擅长解读球员投篮热图。\n"
            "请为以下球员的本场比赛投篮分布图提供一段80-100字的专业解说，要求：\n"
            "1. 简明分析该球员本场比赛投篮分布特点和命中率情况；\n"
            "2. 结合具体的投篮数据，突出他的投篮热区和薄弱区域；\n"
            "3. 使用专业的语言，适合微博平台传播；\n"
            "4. 所有球员名称和专业术语必须用中文表达。\n"
            "球员信息：{player_data}"
        )

        # 查找球员数据
        player_data = None
        for team in ["home", "away"]:
            for player in ai_data.get("player_stats", {}).get(team, []):
                if player.get("basic", {}).get("name", "").lower() == player_name.lower():
                    player_data = player
                    break
            if player_data:
                break

        if not player_data:
            return f"{player_name}本场比赛的投篮分布图显示了他的得分热区和命中情况。"

        # 准备数据
        shot_data = {
            "player_name": player_name,
            "player_stats": player_data,
            "game_info": ai_data.get("game_info", {}),
            "shooting_data": player_data.get("shooting", {})
        }

        # 使用专门的prompt
        prompt = prompt.format(
            player_data=json.dumps(shot_data, ensure_ascii=False)
        )

        try:
            result = self.ai_processor.generate(prompt).strip()

            if self.debug_mode:
                self._log_result(f"球员投篮图解说({player_name})", {"text_length": len(result),
                                                                    "preview": result[:100] + "..." if len(
                                                                        result) > 100 else result})

            return result
        except Exception as e:
            self.logger.error(f"生成球员投篮图解说失败: {e}", exc_info=True)
            return f"{player_name}本场比赛的投篮分布图显示了他的得分热区和命中情况。"

    def generate_team_shot_analysis(self, ai_data: Dict[str, Any], team_name: str) -> str:
        """
        生成球队投篮分析 - 使用单独的prompt

        Returns:
            生成的球队投篮分析字符串
        """
        if self.debug_mode:
            self._log_start(f"球队投篮分析({team_name})")

        if not ai_data or not team_name or "error" in ai_data:
            return f"{team_name}球队本场比赛的投篮分布展示了团队的进攻策略和热区。"

        # 球队投篮分析prompt
        prompt = (
            "你是一名NBA团队战术分析师，也是洛杉矶湖人队的**铁杆**球迷，更是勒布朗的资深粉丝！擅长解读球队整体投篮趋势。\n"
            "请为以下球队的本场比赛投篮分布图提供一段80-100字的专业解说，要求：\n"
            "1. 分析球队整体投篮趋势和特点；\n"
            "2. 提及投篮命中率和三分球表现；\n"
            "3. 探讨球队的战术特点和进攻重点；\n"
            "4. 使用专业的语言，适合微博平台传播；\n"
            "5. 所有球队名称和专业术语必须用中文表达。\n"
            "球队信息：{team_data}"
        )

        # 确定是主队还是客队
        team_info = self._get_team_info(ai_data)
        team_type = None
        if team_name.lower() in team_info["home_full"].lower() or team_name.lower() in team_info[
            "home_tricode"].lower():
            team_type = "home"
        elif team_name.lower() in team_info["away_full"].lower() or team_name.lower() in team_info[
            "away_tricode"].lower():
            team_type = "away"

        if not team_type:
            return f"{team_name}球队本场比赛的投篮分布展示了团队的进攻策略和热区。"

        # 准备数据
        team_data = {
            "team_name": team_info.get(f"{team_type}_full", team_name),
            "team_tricode": team_info.get(f"{team_type}_tricode", ""),
            "opponent": team_info.get("away_full" if team_type == "home" else "home_full", ""),
            "game_info": ai_data.get("game_info", {}),
            "team_stats": ai_data.get("team_stats", {}).get(team_type, {}),
            "game_result": ai_data.get("game_result", {})
        }

        # 使用专门的prompt
        prompt = prompt.format(
            team_data=json.dumps(team_data, ensure_ascii=False)
        )

        try:
            result = self.ai_processor.generate(prompt).strip()

            if self.debug_mode:
                self._log_result(f"球队投篮分析({team_name})", {"analysis_length": len(result),
                                                                "preview": result[:100] + "..." if len(
                                                                    result) > 100 else result})

            return result
        except Exception as e:
            self.logger.error(f"生成球队投篮分析失败: {e}", exc_info=True)
            return f"{team_name}球队本场比赛的投篮分布展示了团队的进攻策略和热区。"

    def generate_round_analysis(self, ai_data: Dict[str, Any], current_round: int) -> str:
        """
        生成回合解说分析 - 使用单独的prompt

        Returns:
            生成的回合解说字符串
        """
        if self.debug_mode:
            self._log_start(f"回合解说分析(回合{current_round})")

        rounds = ai_data.get("rounds", [])
        if not rounds:
            return "暂无回合数据。"

        # 回合解说prompt
        prompt = (
            "你是一名专业的NBA解说员，也是洛杉矶湖人队的**铁杆**球迷，更是勒布朗的资深粉丝！需要对以下回合数据进行专业解说。\n"
            "请结合上下文（共计{num_rounds}个回合）进行连贯且专业的描述，语言要求生动、富有现场感，类似于NBA直播解说。\n"
            "请着重指出当前回合（编号{current_round}）的关键转折和精彩瞬间，并联系前后三回合进行综合点评。\n"
            "语言要有趣，能吸引观众，适合在微博等社交平台发布。\n"
            "回合数据：{rounds_data}"
        )

        start = max(0, current_round - 4)
        end = min(len(rounds), current_round + 4)
        context_rounds = rounds[start:end]
        prompt = prompt.format(
            num_rounds=len(context_rounds),
            current_round=current_round,
            rounds_data=json.dumps(context_rounds, ensure_ascii=False)
        )
        try:
            result = self.ai_processor.generate(prompt).strip()

            if self.debug_mode:
                self._log_result(f"回合解说分析(回合{current_round})", {"analysis_length": len(result),
                                                                        "preview": result[:100] + "..." if len(
                                                                            result) > 100 else result})

            return result
        except Exception as e:
            self.logger.error(f"生成回合解说失败: {e}", exc_info=True)
            return "回合解说生成失败，请稍后重试。"

    # === 内部辅助方法 (标记为私有) ===

    @staticmethod
    def _get_team_info(ai_data: Dict[str, Any]) -> Dict[str, str]:
        """辅助函数：提取球队信息"""
        game_info = ai_data.get("game_info", {})
        teams = game_info.get("teams", {})
        return {
            "home_full": teams.get("home", {}).get("full_name", "主队"),
            "away_full": teams.get("away", {}).get("full_name", "客队"),
            "home_tricode": teams.get("home", {}).get("tricode", "主队"),
            "away_tricode": teams.get("away", {}).get("tricode", "客队"),
        }

    @staticmethod
    def _get_game_date(ai_data: Dict[str, Any]) -> str:
        """辅助函数：提取比赛日期"""
        return ai_data.get("game_info", {}).get("date", {}).get("beijing", "比赛日期")

    @staticmethod
    def _get_game_scores(ai_data: Dict[str, Any]) -> Dict[str, Any]:
        """辅助函数：提取比赛得分"""
        score_data = ai_data.get("game_status", {}).get("score", {})
        return {
            "home_score": score_data.get("home", {}).get("points", "?"),
            "away_score": score_data.get("away", {}).get("points", "?")
        }

    def _normalize_hashtags(self, content: str) -> str:
        """
        规范化微博话题标签格式

        处理连续话题标签，确保每个话题之间有空格，且每个话题都有完整的#包围
        """
        content = re.sub(r'#([^#\s]+)##([^#\s]+)#', r'#\1# #\2#', content)
        words = content.split()
        for i, word in enumerate(words):
            if word.startswith('#') and not word.endswith('#'):
                words[i] = word + '#'
        return ' '.join(words)

    def _format_game_time(self, period, clock):
        """格式化比赛时间和节数"""
        try:
            # 获取节次信息
            period_info = TimeHandler.get_game_time_status(int(period),
                                                           clock if clock.startswith("PT") else f"PT{clock}")
            period_name = period_info["period_name"]

            # 处理时钟显示
            if clock.startswith("PT"):
                seconds = TimeHandler.parse_duration(clock)
                minutes = seconds // 60
                seconds_remainder = seconds % 60
                formatted_clock = f"{minutes}:{seconds_remainder:02d}"
            else:
                formatted_clock = clock

            return f"{period_name} {formatted_clock}"
        except Exception as e:
            self.logger.warning(f"格式化比赛时间失败: {e}")
            return f"第{period}节 {clock}"

    def _batch_generate_round_analyses(self, ai_data, round_ids, player_name):
        """批量生成多个回合的解说内容 - 使用单独的prompt"""
        if self.debug_mode:
            self._log_start(f"批量回合解说({player_name}, {len(round_ids)}个回合)")

        try:
            # 获取所有回合数据
            all_rounds_data = []
            if "events" in ai_data and "data" in ai_data["events"]:
                all_rounds_data.extend(ai_data["events"]["data"])
            if "rounds" in ai_data:
                all_rounds_data.extend(ai_data["rounds"])

            self.logger.info(f"总回合数据: {len(all_rounds_data)}个")

            # 创建回合ID到回合数据的映射
            rounds_by_id = {}
            for round_data in all_rounds_data:
                if "action_number" in round_data:
                    action_id = int(round_data["action_number"])
                    rounds_by_id[action_id] = round_data

            # 获取与球员相关的事件ID
            player_related_ids = ai_data.get("events", {}).get("player_related_action_numbers", [])
            self.logger.info(f"找到{len(player_related_ids)}个与{player_name}相关的事件")

            # 筛选出要解说的回合数据
            filtered_rounds_data = []
            matched_ids = []

            # 记录所有要查找的回合ID
            round_ids_int = [int(rid) for rid in round_ids]
            self.logger.info(f"需要查找的回合ID: {sorted(round_ids_int)}")

            for round_id in round_ids_int:
                # 1. 首先尝试直接匹配
                if round_id in rounds_by_id:
                    filtered_rounds_data.append(rounds_by_id[round_id])
                    matched_ids.append(round_id)

            # 记录匹配情况
            self.logger.info(f"成功匹配 {len(matched_ids)}/{len(round_ids)} 个回合ID")

            # 如果没有匹配到任何回合数据，返回空结果
            if not filtered_rounds_data:
                self.logger.error("没有找到任何匹配的回合数据，无法生成解说")
                return {}

            # 批量回合解说prompt
            prompt = """
                    你是NBA中文解说员，也是洛杉矶湖人队的**铁杆**球迷，更是勒布朗的资深粉丝！
                    需要为以下{num_rounds}个回合事件用中文生成精彩的解说。

                    球员: {player_name}

                    请为以下每个回合ID生成一段专业而详细的中文解说，要求：
                    1. 每段解说长度为100-150字之间，内容必须详尽丰富
                    2. 请结合该回合前后3个回合，用富有感情和现场感的语言描述回合中的动作、球员表现和场上情况，类似于NBA直播解说。
                    3. 使用正确的篮球术语和专业词汇
                    4. 根据回合类型(投篮、助攻、防守等)强调不同的细节
                    5. 解说内容必须完全使用中文，包括术语、数字描述等全部用中文表达
                    6. 特别注意描述{player_name}的表现，展现他的技术特点和比赛影响力
                    7. 内容要生动精彩，适合微博发布

                    回合ID列表: {round_ids}

                    请结合整场比赛的背景，基于以下回合事件数据来生成解说:
                    {round_data}

                    必须以JSON格式返回结果，且只返回JSON数据，格式如下:
                    {{
                        "analyses": [
                            {{
                                "round_id": 回合ID(整数),
                                "analysis": "该回合的中文解说内容(100-150字)"
                            }},
                            ...更多回合
                        ]
                    }}
                    """

            # 构建批量请求
            prompt = prompt.format(
                num_rounds=len(filtered_rounds_data),
                player_name=player_name,
                round_ids=[rd.get('action_number') for rd in filtered_rounds_data],
                round_data=json.dumps(filtered_rounds_data, ensure_ascii=False)
            )

            # 发送批量请求
            self.logger.info("正在调用AI生成中文解说内容(JSON格式)...")
            response = self.ai_processor.generate(prompt)

            # 解析JSON响应
            analyses = {}
            try:
                # 提取JSON部分（防止AI在JSON前后添加额外文本）
                json_match = re.search(r'({[\s\S]*})', response)
                if json_match:
                    json_str = json_match.group(1)
                    json_data = json.loads(json_str)

                    # 处理JSON数据
                    if "analyses" in json_data:
                        for item in json_data["analyses"]:
                            round_id = item.get("round_id")
                            analysis = item.get("analysis")
                            if round_id is not None and analysis:
                                analyses[round_id] = analysis

                        self.logger.info(f"成功从JSON解析了{len(analyses)}个回合解说")
                    else:
                        self.logger.warning("JSON中未找到analyses字段")
                else:
                    self.logger.warning("未找到JSON格式响应")
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON解析失败: {e}")

            if self.debug_mode:
                self._log_result(f"批量回合解说({player_name})",
                                 {"requested_rounds": len(round_ids), "generated_rounds": len(analyses)})

            return analyses

        except Exception as e:
            self.logger.error(f"批量生成回合解说失败: {e}", exc_info=True)
            return {}

    def _generate_simple_round_content(self, ai_data: Dict[str, Any], round_id: int, player_name: str,
                                       round_index: int = 1, total_rounds: int = 1) -> str:
        """
        生成简单的回合解说内容，专门处理助攻回合
        """
        if self.debug_mode:
            self._log_start(f"简单回合解说(回合{round_id})")

        # 检查这是否是一个助攻回合
        is_assist_round = False
        assist_description = ""

        # 查找所有助攻投篮
        for event in ai_data.get("events", {}).get("data", []):
            if (event.get("action_type") in ["2pt", "3pt"] and
                    "assist_person_id" in event and
                    event.get("action_number") == round_id):
                is_assist_round = True
                shooter_name = event.get("player_name", "队友")
                shot_type = "三分球" if event.get("action_type") == "3pt" else "两分球"
                shot_result = "命中" if event.get("shot_result") == "Made" else "未命中"
                assist_description = f"{player_name}传出精彩助攻，{shooter_name}{shot_result}一记{shot_type}。"
                break

        # 使用格式化的时间
        formatted_time = f"第{round_index}回合/共{total_rounds}回合"

        # 根据是否是助攻回合生成不同内容
        if is_assist_round:
            content = f"{formatted_time} - {player_name}展现出色的传球视野，送出一记精准助攻！{assist_description}这样的传球展现了他作为全场组织者的能力，不仅能得分，更能帮助队友创造得分机会。"
        else:
            content = f"{formatted_time} - {player_name}在这个回合展现出色表现！无论是得分、传球还是防守，都展示了他的全面技术和领袖气质。"

        if self.debug_mode:
            self._log_result(f"简单回合解说(回合{round_id})",
                             {"content_length": len(content), "is_assist_round": is_assist_round})

        return content

    def _format_round_content(self, ai_data: Dict[str, Any], round_id: int, player_name: str,
                              analysis_text: str, round_index: int = 1, total_rounds: int = 1) -> str:
        """
        格式化回合解说内容 - 增加自动换行提高可读性
        """
        if self.debug_mode:
            self._log_start(f"格式化回合内容(回合{round_id})")

        try:
            # 查找回合事件
            round_event = None
            for event in ai_data.get("rounds", []):
                if event.get("action_number") == round_id or str(event.get("action_number")) == str(round_id):
                    round_event = event
                    break

            if not round_event:
                self.logger.warning(f"未找到回合ID为 {round_id} 的事件数据")
                return f"{player_name}本场表现回顾{round_index}/{total_rounds}\n\n精彩表现！\n\n#NBA# #湖人# #勒布朗# #詹姆斯#"

            # 提取信息
            period = round_event.get("period", "")
            clock = round_event.get("clock", "")

            # 使用格式化的时间
            formatted_time = self._format_game_time(period, clock)

            # 构建解说内容 - 新格式，添加更多换行
            content = f"{player_name}本场表现回顾{round_index}/{total_rounds} {formatted_time}\n\n"

            # 添加AI解说 - 确保不为空并添加适当换行
            if analysis_text and analysis_text.strip():
                # 清理AI解说内容
                cleaned_analysis = analysis_text.strip()
                # 移除可能在解说内容中出现的话题标签
                cleaned_analysis = re.sub(r'#[^#]+#', '', cleaned_analysis)

                # 插入自动换行来优化阅读体验
                # 1. 分割解说内容为句子
                sentences = re.split(r'([。！？!?])', cleaned_analysis)
                formatted_sentences = []

                # 2. 重新组合句子，每2-3个句子后添加换行
                current_group = ""
                sentence_count = 0

                for i in range(0, len(sentences), 2):  # 步长为2是因为分割保留了标点符号
                    if i < len(sentences):
                        current_group += sentences[i]
                        if i + 1 < len(sentences):  # 添加标点
                            current_group += sentences[i + 1]

                        sentence_count += 1
                        if sentence_count >= 2:  # 每2个句子后换行
                            formatted_sentences.append(current_group)
                            current_group = ""
                            sentence_count = 0

                # 添加最后未满2句的内容
                if current_group:
                    formatted_sentences.append(current_group)

                # 3. 将格式化后的内容组合为最终文本，用换行符连接
                content += "\n".join(formatted_sentences)
            else:
                self.logger.warning(f"回合 {round_id} 的解说文本为空，使用默认文本")
                if round_event:
                    content += self._generate_fallback_content(round_event, player_name, round_index, total_rounds)
                else:
                    content += f"{player_name}在这个回合展现出色表现！"

            # 添加固定标签（与正文间增加一个空行）
            if "#NBA#" not in content:
                content += "\n\n#NBA# #湖人# #勒布朗# #詹姆斯#"

            if self.debug_mode:
                self._log_result(f"格式化回合内容(回合{round_id})",
                                 {"content_length": len(content), "formatted_time": formatted_time})

            return content
        except Exception as e:
            self.logger.error(f"格式化回合内容失败: {e}", exc_info=True)
            # 返回一个简单的备用内容
            return f"{player_name}本场表现回顾{round_index}/{total_rounds}\n\n精彩表现！\n\n#NBA# #湖人# #勒布朗# #詹姆斯#"

    def _generate_fallback_content(self, round_data, player_name, round_index=1, total_rounds=1):
        """基于回合数据生成备选解说内容"""
        try:
            # 提取关键信息
            period = round_data.get("period", "")
            clock = round_data.get("clock", "")
            action_type = round_data.get("action_type", "")
            description = round_data.get("description", "")
            score_home = round_data.get("score_home", "")
            score_away = round_data.get("score_away", "")

            # 格式化时间
            formatted_time = self._format_game_time(period, clock)

            # 根据动作类型生成描述
            if action_type == "2pt":
                shot_type = "两分球"
            elif action_type == "3pt":
                shot_type = "三分球"
            elif action_type == "rebound":
                shot_type = "篮板球"
            elif action_type == "assist":
                shot_type = "助攻"
            elif action_type == "steal":
                shot_type = "抢断"
            elif action_type == "block":
                shot_type = "盖帽"
            else:
                shot_type = "精彩表现"

            # 基础描述文本
            content = ""

            # 添加中文描述
            if description:
                # 简单处理英文描述
                if "Jump Shot" in description:
                    chi_desc = f"{player_name}投中一记漂亮的跳投"
                elif "3PT" in description:
                    chi_desc = f"{player_name}命中一记三分球"
                elif "Layup" in description:
                    chi_desc = f"{player_name}完成一次漂亮的上篮"
                elif "Dunk" in description:
                    chi_desc = f"{player_name}完成一记精彩扣篮"
                elif "Assist" in description or "AST" in description:
                    chi_desc = f"{player_name}送出一记精准助攻"
                else:
                    chi_desc = f"{player_name}展现精彩表现"

                content += f"{chi_desc}"
            else:
                content += f"{player_name}展现了一次精彩的{shot_type}表现"

            # 添加比分信息
            if score_home and score_away:
                content += f"，当前比分 {score_away}-{score_home}"

            # 添加回合信息和时间
            content += f"（第{round_index}/{total_rounds}回合，{formatted_time}）"

            return content
        except Exception as e:
            self.logger.error(f"生成备选内容失败: {e}")
            return f"{player_name}在这个回合展现出色表现！（第{round_index}/{total_rounds}回合）"

    def _log_start(self, content_type: str) -> None:
        """记录内容生成开始"""
        self.logger.info(f"开始生成{content_type}内容")
        self.start_time = time.time()

    def _log_result(self, content_type: str, result: Dict[str, Any]) -> None:
        """记录内容生成结果"""
        elapsed = time.time() - self.start_time
        self.logger.info(f"{content_type}内容生成完成，耗时: {elapsed:.2f}秒")
        self.logger.debug(f"生成结果预览: {result}")