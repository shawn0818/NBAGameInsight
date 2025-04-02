from typing import Dict, Any, Optional, List
import json
import logging
import re
import time
from utils.time_handler import TimeHandler
from enum import Enum
from nba.models.game_model import Game
from nba.services.game_data_adapter import GameDataAdapter



class ContentType(Enum):
    """微博模块常量定义"""

    # 微博内容类型
    TEAM_VIDEO = "team_video"
    PLAYER_VIDEO = "player_video"
    PLAYER_CHART = "player_chart"
    TEAM_CHART = "team_chart"
    ROUND_ANALYSIS = "round_analysis"
    # 新增内容类型
    TEAM_RATING = "team_rating"
    # 常用标签
    NBA_HASHTAG = "#NBA#"
    BASKETBALL_HASHTAG = "#篮球#"


class WeiboContentGenerator:
    """
    微博内容生成工具类

    负责基于AI友好数据生成适用于微博发布的内容，不直接依赖具体的数据模型。
    使用GameDataAdapter处理数据转换，根据ID而非名称进行操作。
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
        self.adapter = GameDataAdapter()  # 实例化数据适配器

    # === 公开的内容生成接口 ===

    def generate_content(self, content_type: str, game_data: Game, **kwargs) -> Dict[str, Any]:
        """统一内容生成接口

        Args:
            content_type: 内容类型，如"team_video"，"player_video"等
            game_data: 比赛数据 (应始终为 Game 对象)
            **kwargs: 其他参数，如player_id, team_id等

        Returns:
            Dict: 包含内容的字典
        """

        if not isinstance(game_data, Game):
            self.logger.error(f"generate_content 预期接收 Game 对象，但收到了 {type(game_data)}")
            # 可以根据需要决定是抛出异常还是返回错误字典
            raise TypeError(f"generate_content 预期接收 Game 对象，但收到了 {type(game_data)}")

        # 根据内容类型调用相应的方法，直接传递原始 game_data(Game 对象)
        if content_type == ContentType.TEAM_VIDEO.value:
            team_id = kwargs.get("team_id")
            if not team_id:
                raise ValueError("生成球队视频内容需要提供team_id参数")
            return self.generate_team_video_content(game_data, team_id)

        elif content_type == ContentType.PLAYER_VIDEO.value:
            player_id = kwargs.get("player_id")
            if not player_id:
                raise ValueError("生成球员视频内容需要提供player_id参数")
            return self.generate_player_video_content(game_data, player_id)

        elif content_type == ContentType.PLAYER_CHART.value:
            player_id = kwargs.get("player_id")
            if not player_id:
                raise ValueError("生成球员投篮图内容需要提供player_id参数")
            return self.generate_player_chart_content(game_data, player_id)

        elif content_type == ContentType.TEAM_CHART.value:
            team_id = kwargs.get("team_id")
            if not team_id:
                raise ValueError("生成球队投篮图内容需要提供team_id参数")
            return self.generate_team_chart_content(game_data, team_id)

        elif content_type == ContentType.ROUND_ANALYSIS.value:
            player_id = kwargs.get("player_id")
            round_ids = kwargs.get("round_ids")
            if not player_id or not round_ids:
                raise ValueError("生成回合解说内容需要提供player_id和round_ids参数")
            return self.generate_player_rounds_content(game_data, player_id, round_ids)

        elif content_type == ContentType.TEAM_RATING.value:
            team_id = kwargs.get("team_id")
            if not team_id:
                raise ValueError("生成球队评级内容需要提供team_id参数")
            return self.generate_team_performance_rating(game_data, team_id)

        else:
            raise ValueError(f"不支持的内容类型: {content_type}")

    # === 按发布类型分类的内容生成方法 ===

    def generate_team_video_content(self, game_data: Any, team_id: int) -> Dict[str, str]:
        """生成球队集锦视频内容，对应post_team_video方法

        生成侧重点:
        - 标题：强调比赛整体性质、双方对阵、最终比分
        - 内容：包含比赛全局分析、团队表现、比赛关键时刻

        Args:
            game_data: 比赛数据 (Game对象)
            team_id: 球队ID

        Returns:
            Dict包含 title, content (已包含hashtags)
        """
        if self.debug_mode:
            self._log_start("球队集锦视频")

        try:
            # 使用适配器获取适配后的数据
            adapted_data = self.adapter.adapt_for_team_content(game_data, team_id)

            if "error" in adapted_data:
                self.logger.error(f"获取球队数据失败: {adapted_data['error']}")
                return {"title": "NBA精彩比赛", "content": ""}

            # 生成标题和摘要
            title = self.generate_game_title(adapted_data)
            game_summary = self.generate_game_summary(adapted_data)
            hashtags = f"{ContentType.NBA_HASHTAG.value} {ContentType.BASKETBALL_HASHTAG.value}"

            content = f"{game_summary}\n\n{hashtags}"

            result = {"title": title, "content": content}

            if self.debug_mode:
                self._log_result("球队集锦视频", result)

            return result

        except Exception as e:
            self.logger.error(f"生成球队集锦视频内容失败: {e}", exc_info=True)
            return {"title": "NBA精彩比赛", "content": ""}

    def generate_player_video_content(self, game_data: Any, player_id: int) -> Dict[str, str]:
        """生成球员集锦视频内容，对应post_player_video方法

        生成侧重点:
        - 标题：在比赛标题基础上突出球员个人表现
        - 内容：专注于球员表现亮点、技术特点、影响力分析

        Args:
            game_data: 比赛数据 (Game对象)
            player_id: 球员ID

        Returns:
            Dict包含 title, content (已包含hashtags)
        """
        if self.debug_mode:
            self._log_start(f"球员({player_id})集锦视频")

        try:
            # 使用适配器获取适配后的数据
            adapted_data = self.adapter.adapt_for_player_content(game_data, player_id)

            if "error" in adapted_data:
                self.logger.error(f"获取球员数据失败: {adapted_data['error']}")
                return {"title": "NBA球员集锦", "content": ""}

            # 获取球员名称
            player_name = adapted_data["player_info"]["basic"]["name"]

            # 首先获取团队数据，用于生成比赛标题
            team_id = adapted_data["team_info"]["team_id"]
            team_data = self.adapter.adapt_for_team_content(game_data, team_id)

            # 生成标题和球员分析
            game_title = self.generate_game_title(team_data)
            player_title = f"{game_title} - {player_name}个人集锦"
            player_analysis = self.generate_player_analysis(adapted_data)
            hashtags = f"{ContentType.NBA_HASHTAG.value} {ContentType.BASKETBALL_HASHTAG.value} #{player_name}#"

            content = f"{player_analysis}\n\n{hashtags}"

            result = {"title": player_title, "content": content}

            if self.debug_mode:
                self._log_result(f"球员({player_name})集锦视频", result)

            return result

        except Exception as e:
            self.logger.error(f"生成球员集锦视频内容失败: {e}", exc_info=True)
            return {"title": "NBA球员集锦", "content": ""}

    def generate_player_chart_content(self, game_data: Any, player_id: int) -> Dict[str, str]:
        """生成球员投篮图内容，对应post_player_chart方法

        生成侧重点:
        - 内容：专注于球员投篮数据分析、命中率、投篮热区分布

        Args:
            game_data: 比赛数据 (Game对象)
            player_id: 球员ID

        Returns:
            Dict包含 title, content (已包含hashtags)
        """
        if self.debug_mode:
            self._log_start(f"球员({player_id})投篮图")

        try:
            # 使用适配器获取适配后的数据
            adapted_data = self.adapter.adapt_for_shot_chart(game_data, player_id, is_team=False)

            if "error" in adapted_data:
                self.logger.error(f"获取球员投篮数据失败: {adapted_data['error']}")
                return {"title": "NBA球员投篮分析", "content": ""}

            # 获取球员名称
            player_name = adapted_data["player_info"]["basic"]["name"]

            # 生成标题和投篮图文本
            game_title = self.generate_game_title(adapted_data) # <--- 修改：直接传递 adapted_data
            shot_chart_title = f"{game_title} - {player_name}投篮分布"
            shot_chart_text = self.generate_shot_chart_text(adapted_data)
            hashtags = f"{ContentType.NBA_HASHTAG.value} {ContentType.BASKETBALL_HASHTAG.value} #{player_name}#"

            content = f"{player_name}本场比赛投篮分布图\n\n{shot_chart_text}\n\n{hashtags}"

            result = {"title": shot_chart_title, "content": content}

            if self.debug_mode:
                self._log_result(f"球员({player_name})投篮图", result)

            return result

        except Exception as e:
            self.logger.error(f"生成球员投篮图内容失败: {e}", exc_info=True)
            player_name = "球员"  # 无法获取球员名称时的默认值
            return {"title": f"{player_name}投篮分析",
                    "content": f"{player_name}本场比赛的投篮分布图显示了他的得分热区和命中情况。"}

    def generate_team_chart_content(self, game_data: Any, team_id: int) -> Dict[str, str]:
        """生成球队投篮图内容，对应post_team_chart方法

        生成侧重点:
        - 内容：专注于球队整体投篮分布、命中率热区和战术倾向

        Args:
            game_data: 比赛数据 (Game对象)
            team_id: 球队ID

        Returns:
            Dict包含 title, content (已包含hashtags)
        """
        if self.debug_mode:
            self._log_start(f"球队({team_id})投篮图")

        try:
            # 使用适配器获取适配后的数据
            adapted_data = self.adapter.adapt_for_shot_chart(game_data, team_id, is_team=True)

            if "error" in adapted_data:
                self.logger.error(f"获取球队投篮数据失败: {adapted_data['error']}")
                return {"title": "NBA球队投篮分析", "content": ""}

            # 获取球队名称
            team_name = adapted_data["team_info"]["team_name"]

            # 获取团队数据，用于生成比赛标题
            team_data = self.adapter.adapt_for_team_content(game_data, team_id)

            # 生成标题和球队投篮分析
            game_title = self.generate_game_title(team_data)
            team_chart_title = f"{game_title} - {team_name}球队投篮分布"
            team_shot_analysis = self.generate_team_shot_analysis(adapted_data)
            hashtags = f"{ContentType.NBA_HASHTAG.value} {ContentType.BASKETBALL_HASHTAG.value} #{team_name}#"

            content = f"{team_name}球队本场比赛投篮分布图\n\n{team_shot_analysis}\n\n{hashtags}"

            result = {"title": team_chart_title, "content": content}

            if self.debug_mode:
                self._log_result(f"球队({team_name})投篮图", result)

            return result

        except Exception as e:
            self.logger.error(f"生成球队投篮图内容失败: {e}", exc_info=True)
            team_name = "球队"  # 无法获取球队名称时的默认值
            return {"title": f"{team_name}投篮分析",
                    "content": f"{team_name}球队本场比赛的投篮分布展示了团队的进攻策略和热区。"}

    def generate_player_rounds_content(self, game_data: Any, player_id: int, round_ids: List[int]) -> Dict[str, Any]:
        """生成球员回合解说内容，对应post_player_rounds方法

        生成侧重点:
        - 内容：针对每个回合的详细解说，突出球员关键表现和技术细节

        Args:
            game_data: 比赛数据 (Game对象)
            player_id: 球员ID
            round_ids: 回合ID列表

        Returns:
            包含所有回合解说的字典，格式为 {"analyses": {round_id: 解说内容}}
        """
        if self.debug_mode:
            self._log_start(f"球员({player_id})回合解说")

        try:
            # 使用适配器获取适配后的数据
            adapted_data = self.adapter.adapt_for_round_analysis(game_data, player_id, round_ids)

            if "error" in adapted_data:
                self.logger.error(f"获取回合数据失败: {adapted_data['error']}")
                return {"analyses": {}}

            # 获取球员名称
            player_name = adapted_data["player_info"]["basic"]["name"]

            # 批量生成回合解说
            analyses = self._batch_generate_round_analyses(adapted_data, round_ids, player_name)

            # 为缺失的回合生成简单解说
            for round_id in round_ids:
                if str(round_id) not in analyses:
                    analyses[str(round_id)] = self._generate_simple_round_content(
                        adapted_data, round_id, player_name
                    )

            if self.debug_mode:
                self._log_result(f"球员({player_name})回合解说",
                                 {"rounds_count": len(analyses),
                                  "sample": next(iter(analyses.values())) if analyses else ""})

            # 返回包装后的结果
            result = {
                "analyses": analyses
            }

            return result

        except Exception as e:
            self.logger.error(f"生成球员回合解说内容失败: {e}", exc_info=True)
            return {"analyses": {}}

    def generate_team_performance_rating(self, game_data: Any, team_id: int) -> Dict[str, str]:
        """生成球队赛后评级报告

        分析要点:
        - 球队整体表现评级 (1-5星)
        - 关键球员表现评级 (每人1-5星)
        - 对上场时间超过10分钟的球员进行详细分析
        - 团队数据和趋势分析

        Args:
            game_data: 比赛数据 (Game对象)
            team_id: 球队ID

        Returns:
            Dict包含 title, content (已包含hashtags)
        """
        if self.debug_mode:
            self._log_start("球队赛后评级")

        try:
            # 使用适配器获取适配后的数据
            adapted_data = self.adapter.adapt_for_team_content(game_data, team_id)

            if "error" in adapted_data:
                self.logger.error(f"获取球队评级数据失败: {adapted_data['error']}")
                return {"title": "球队赛后评级", "content": ""}

            # 使用提示词生成球队评级内容
            prompt = (
                "你是一名NBA球队分析师，也是洛杉矶湖人队的**铁杆**球迷，更是勒布朗的资深粉丝！擅长对球队和球员表现进行专业评级。\n"
                "请对以下球队本场比赛的表现进行评级分析，要求：\n"
                "1. 总体评价球队表现(1-5星)，并分析得失分原因；\n"
                "2. 对首发五人和表现突出的替补球员的表现进行评级(1-5星)；\n"
                "3. 重点分析上场时间超过10分钟的球员表现；\n"
                "4. 分析团队数据趋势和战术执行情况；\n"
                "5. 内容应包含对比赛整体走势和关键节点的分析；\n"
                "6. 整体内容控制在250-350字之间；\n"
                "7. 适合社交媒体发布，可适度使用星级emoji(⭐)表示评分；\n"
                "8. 所有专业术语用中文，球员名字也要使用中文。\n"
                "评级数据：{rating_data}"
            )

            # 提取评级需要的数据
            team_info = adapted_data["team_info"]
            team_stats = adapted_data.get("team_stats", {})
            opponent_info = adapted_data.get("opponent_info", {})
            game_info = adapted_data.get("game_info", {})

            # 从game_data中获取球员列表并筛选
            player_list = []

            # 假设可以从game_data中获取到球员列表
            # 这里需要获取球员数据，可以通过遍历球队的players列表实现
            # 简单起见，我们使用top_players
            top_players = adapted_data.get("top_players", [])

            # 筛选出上场时间超过10分钟的球员
            key_players = []
            for player in top_players:
                # 解析上场时间
                minutes_value = player.get("minutes")  # 获取原始值
                minutes_played = 0  # 初始化分钟数
                try:
                    if isinstance(minutes_value, str) and ":" in minutes_value:
                        # 尝试解析 "MM:SS" 格式
                        parts = minutes_value.split(":")
                        if len(parts) >= 1:
                            minutes_played = int(parts[0])
                    elif isinstance(minutes_value, (int, float)):
                        # 假设数字是总分钟数 (例如 25.5)
                        # 如果是总秒数，需要除以 60: minutes_played = int(minutes_value / 60)
                        minutes_played = int(minutes_value)  # 只取整数部分比较
                    elif minutes_value is None or minutes_value == "0:00":
                        minutes_played = 0
                    else:
                        # 记录未知的格式，但可能仍需处理或跳过
                        self.logger.warning(
                            f"未知的上场时间格式: {minutes_value} (类型: {type(minutes_value)}) 球员ID: {player.get('id')}")
                        # 根据需要决定如何处理未知格式，这里暂时跳过
                        # continue # 或者可以设置为0分钟

                    # 根据计算出的分钟数判断是否添加到关键球员列表
                    if minutes_played >= 10:
                        key_players.append(player)

                except (ValueError, TypeError, AttributeError) as e:
                    # 捕获解析过程中可能发生的其他错误
                    self.logger.error(f"解析球员 {player.get('id')} 的上场时间 {minutes_value} 时出错: {e}",
                                      exc_info=False)

            # 准备评级数据
            rating_data = {
                "team_name": team_info["team_name"],
                "team_tricode": team_info.get("team_tricode", ""),
                "opponent_name": opponent_info.get("team_name", "对手"),
                "opponent_tricode": opponent_info.get("team_tricode", ""),
                "score": team_info.get("score", 0),
                "opponent_score": opponent_info.get("score", 0),
                "is_home": team_info.get("is_home", True),
                "game_result": adapted_data.get("game_result", {}),
                "team_stats": team_stats,
                "key_players": key_players,
                "game_info": game_info
            }

            # 格式化提示词
            prompt = prompt.format(
                rating_data=json.dumps(rating_data, ensure_ascii=False)
            )

            # 生成评级内容
            content = self.ai_processor.generate(prompt).strip()

            # 生成标题
            home_team = game_info.get("teams", {}).get("home", {}).get("short_name", "主队")
            away_team = game_info.get("teams", {}).get("away", {}).get("short_name", "客队")

            # 确保标题中球队顺序正确（访客vs主场）
            if team_info.get("is_home", True):
                title = f"{away_team}vs{team_info['team_name']}赛后评级"
            else:
                title = f"{team_info['team_name']}vs{home_team}赛后评级"

            # 添加标签
            hashtags = f"{ContentType.NBA_HASHTAG.value} {ContentType.BASKETBALL_HASHTAG.value} #{team_info['team_name']}#"

            # 组合完整内容
            full_content = f"{content}\n\n{hashtags}"

            result = {"title": title, "content": full_content}

            if self.debug_mode:
                self._log_result("球队赛后评级", {"title": result["title"], "content_length": len(result["content"])})

            return result

        except Exception as e:
            self.logger.error(f"生成球队赛后评级失败: {e}", exc_info=True)
            team_name = "球队"
            if "team_info" in adapted_data and "team_name" in adapted_data["team_info"]:
                team_name = adapted_data["team_info"]["team_name"]
            return {"title": f"{team_name}赛后评级", "content": f"{team_name}本场比赛表现分析。"}

    # === 基础内容生成方法 ===

    def generate_game_title(self, adapted_data: Dict[str, Any]) -> str:
        """
        生成比赛标题 - 直接使用单独的prompt

        Args:
            adapted_data: 适配器提供的数据

        Returns:
            生成的比赛标题字符串
        """
        if self.debug_mode:
            self._log_start("比赛标题")

        if not adapted_data or "error" in adapted_data:
            return "NBA精彩比赛"

        try:
            # 提取所需信息 - 增加数据检查避免KeyError
            game_info = adapted_data.get("game_info", {})
            basic_info = game_info.get("basic", {})
            teams_info = basic_info.get("teams", {})

            # 安全获取球队信息
            home_team = teams_info.get("home", {}).get("full_name", "主队")
            away_team = teams_info.get("away", {}).get("full_name", "客队")

            # 安全获取比分信息
            status = game_info.get("status", {})
            score = status.get("score", {})
            home_score = score.get("home", {}).get("points", 0)
            away_score = score.get("away", {}).get("points", 0)

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

            rivalry_info = adapted_data.get("rivalry_info", {"available": False})

            prompt = prompt.format(
                home_team=home_team,
                away_team=away_team,
                home_score=home_score,
                away_score=away_score,
                game_info=json.dumps({
                    "game_info": game_info,
                    "rivalry_info": rivalry_info
                }, ensure_ascii=False)
            )

            title = self.ai_processor.generate(prompt)
            result = title.strip().strip('"\'')

            if self.debug_mode:
                self._log_result("比赛标题", {"title": result})

            return result

        except Exception as e:
            self.logger.error(f"生成比赛标题失败: {e}", exc_info=True)
            # 使用更安全的方式获取数据
            game_info = adapted_data.get("game_info", {})
            status = game_info.get("status", {})
            score = status.get("score", {})

            # 获取主客队tricode和比分（使用更安全的方式）
            home_team_info = score.get("home", {})
            away_team_info = score.get("away", {})

            home_team = home_team_info.get("team", "主队") if isinstance(home_team_info, dict) else "主队"
            away_team = away_team_info.get("team", "客队") if isinstance(away_team_info, dict) else "客队"
            home_score = home_team_info.get("points", "?") if isinstance(home_team_info, dict) else "?"
            away_score = away_team_info.get("points", "?") if isinstance(away_team_info, dict) else "?"

            return f"{away_team} vs {home_team} {away_score}-{home_score} 比赛集锦"

    def generate_game_summary(self, adapted_data: Dict[str, Any]) -> str:
        """
        生成比赛摘要 - 直接使用单独的prompt

        Args:
            adapted_data: 适配器提供的数据

        Returns:
            生成的比赛摘要字符串
        """
        if self.debug_mode:
            self._log_start("比赛摘要")

        if not adapted_data or "error" in adapted_data:
            return ""

        try:
            # 比赛摘要prompt
            prompt = (
                "你是一名洛杉矶湖人队的**铁杆**球迷同时也是专业的体育记者，更是勒布朗的资深粉丝！擅长为NBA比赛创作生动简洁的比赛总结。\n"
                "请根据以下比赛信息生成一段150-200字的中文比赛摘要，要求：\n"
                "1. 详细总结比赛的关键数据（如得分、篮板、助攻等）；\n"
                "2. 突出比赛过程中的关键转折点和重要时刻；\n"
                "3. 提及湖人队表现突出的1-3名球员，尤其是球队在进攻、组织、防守端表现较好的球员，并结合数据进行分析；\n"
                #"4. 注意：只在数据中明确包含rivalry_info字段且available为true时，才提及两队对抗历史；否则不要提及；\n"
                "5. 使用生动语言，适合社交媒体发布，适当使用emoji。\n"
                "6. 所有球队和球员名称均用中文，百分数只保留小数点后两位。\n"
                "比赛信息：{summary_data}"
            )

            # 提取摘要所需数据
            summary_data = {
                "game_info": adapted_data["game_info"],
                "team_stats": {
                    "home": adapted_data.get("team_stats", {}) if adapted_data.get("team_info", {}).get("is_home",
                                                                                                        False) else {},
                    "away": {} if adapted_data.get("team_info", {}).get("is_home", False) else adapted_data.get(
                        "team_stats", {})
                },
                "top_players": adapted_data.get("top_players", []),
                "game_result": adapted_data.get("game_result", {}),
                "rivalry_info": adapted_data.get("rivalry_info", {"available": False})
            }

            prompt = prompt.format(
                summary_data=json.dumps(summary_data, ensure_ascii=False)
            )

            result = self.ai_processor.generate(prompt).strip()

            if self.debug_mode:
                self._log_result("比赛摘要", {"summary_length": len(result),
                                              "preview": result[:100] + "..." if len(result) > 100 else result})

            return result

        except Exception as e:
            self.logger.error(f"生成比赛摘要失败: {e}", exc_info=True)
            home_team = adapted_data.get("game_info", {}).get("teams", {}).get("home", {}).get("full_name", "主队")
            away_team = adapted_data.get("game_info", {}).get("teams", {}).get("away", {}).get("full_name", "客队")
            home_score = adapted_data.get("game_info", {}).get("status", {}).get("score", {}).get("home", "?")
            away_score = adapted_data.get("game_info", {}).get("status", {}).get("score", {}).get("away", "?")

            return f"{away_team}对阵{home_team}的比赛，比分{away_score}-{home_score}。"

    def generate_player_analysis(self, adapted_data: Dict[str, Any]) -> str:
        """
        生成球员表现分析 - 直接使用单独的prompt

        考虑球员可能因伤或其他原因不参赛的情况，提供相应分析。

        Args:
            adapted_data: 适配器提供的数据

        Returns:
            生成的球员分析字符串
        """
        if self.debug_mode:
            self._log_start(f"球员分析")

        if not adapted_data or "error" in adapted_data:
            return ""

        try:
            # 首先获取球员信息和各种状态数据
            player_info = adapted_data.get("player_info", {})
            team_info = adapted_data.get("team_info", {})
            opponent_info = adapted_data.get("opponent_info", {})
            game_info = adapted_data.get("game_info", {})
            game_result = adapted_data.get("game_result", {})

            # 处理球员名称 (从各种可能的位置获取)
            player_name = "未知球员"
            if "name" in player_info:
                player_name = player_info["name"]
            elif "basic" in player_info and "name" in player_info["basic"]:
                player_name = player_info["basic"]["name"]

            # 检查球员是否参与了比赛 - 注意检查多种可能的路径
            is_injured = False
            injury_status = {}
            injury_reason = ""

            # 检查是否直接标记为伤病球员
            if adapted_data.get("is_injured_player", False):
                is_injured = True
                injury_status = player_info.get("injury_status", {})
                injury_reason = injury_status.get("reason", "伤病")

            # 检查status信息
            elif "status" in player_info:
                status = player_info["status"]
                if not status.get("is_active", True):
                    is_injured = True
                    injury_status = status.get("injury", {})
                    injury_reason = injury_status.get("reason", "伤病")

            # 检查basic中的played字段
            elif "basic" in player_info and "played" in player_info["basic"] and not player_info["basic"]["played"]:
                is_injured = True
                # 尝试从injury_description字段获取原因
                injury_description = adapted_data.get("injury_description", "")
                if injury_description:
                    injury_reason = injury_description

            # 检查首发名单和伤病名单
            elif "injuries" in adapted_data:
                injuries = adapted_data.get("injuries", {})
                for team_type in ["home", "away"]:
                    for injured_player in injuries.get(team_type, []):
                        if injured_player.get("name") == player_name:
                            is_injured = True
                            injury_reason = injured_player.get("reason", "伤病")
                            injury_status = {
                                "reason": injury_reason,
                                "description": injured_player.get("description", ""),
                                "detailed": injured_player.get("detailed", "")
                            }
                            break

            # 根据球员是否参赛生成不同的分析提示词
            if is_injured:
                # 伤病球员分析prompt
                prompt = (
                    "你是一名NBA球员分析师，也是洛杉矶湖人队的**铁杆**球迷，更是勒布朗的资深粉丝！擅长通过数据和比赛表现分析球员影响力。\n"
                    "这位球员因{injury_reason}未参与本场比赛，请你：\n"
                    "1. 以洛杉矶湖人队铁杆球迷的身份，对比赛结果进行简短点评；\n"
                    "2. 简要分析此球员缺阵对球队的影响；\n"
                    "3. 表达对他康复和尽快回归的期望；\n"
                    "4. 语言风格幽默活泼，充满热情和感情；\n"
                    "5. 控制在100-200字之间；\n"
                    "6. 适合社交媒体发布，适当使用emoji；\n"
                    "7. 所有专业术语用中文，球员名字也要使用中文。\n"
                    "球员信息：{analysis_data}"
                )
            else:
                # 常规球员分析prompt
                prompt = (
                    "你是一名NBA球员分析师，也是洛杉矶湖人队的**铁杆**球迷，更是勒布朗的资深粉丝！擅长通过数据和比赛表现分析球员影响力。\n"
                    "请分析以下球员在本场比赛中的表现，要求：\n"
                    "1. 针对球员本场比赛的表现进行深入剖析；\n"
                    "2. 突出关键数据，并分析这些数据对比赛结果的影响，注意百分数只保留小数点后两位；\n"
                    "3. 全面客观地评价球员的表现（此处可以适当语言犀利或者幽默，但是不能刻薄、不尊重）；\n"
                    "4. 控制在100-200字之间；\n"
                    "5. 适合社交媒体发布，可适度加入中式幽默，适当使用emoji；\n"
                    "6. 所有专业术语用中文，球员名字也要使用中文。\n"
                    "球员信息：{analysis_data}"
                )

            # 安全获取球队名称
            team_name = team_info.get("team_name", "未知球队")
            opponent_name = opponent_info.get("opponent_name", opponent_info.get("team_name", "对手"))

            # 准备分析数据
            analysis_data = {
                "player_name": player_name,
                "team_name": team_name,
                "opponent_name": opponent_name,
                "game_result": game_result,
                "game_info": game_info,
                "is_injured": is_injured,
                "injury_status": injury_status,
                "injury_reason": injury_reason
            }

            # 如果球员有上场，则添加球员数据
            if not is_injured:
                analysis_data["player_stats"] = player_info.get("basic", {})
                # 添加更多详细数据
                if "shooting" in player_info:
                    analysis_data["shooting"] = player_info["shooting"]
                if "other_stats" in player_info:
                    analysis_data["other_stats"] = player_info["other_stats"]

            # 格式化提示词并生成内容
            formatted_prompt = prompt.format(
                injury_reason=injury_reason,
                analysis_data=json.dumps(analysis_data, ensure_ascii=False)
            )

            result = self.ai_processor.generate(formatted_prompt).strip()

            if self.debug_mode:
                self._log_result(f"球员分析", {
                    "is_injured": is_injured,
                    "injury_reason": injury_reason if is_injured else "N/A",
                    "analysis_length": len(result),
                    "preview": result[:100] + "..." if len(result) > 100 else result
                })

            return result

        except Exception as e:
            self.logger.error(f"生成球员分析失败: {e}", exc_info=True)
            # 尝试安全获取球员名称
            player_name = "球员"
            try:
                player_info = adapted_data.get("player_info", {})
                if "name" in player_info:
                    player_name = player_info["name"]
                elif "basic" in player_info and "name" in player_info["basic"]:
                    player_name = player_info["basic"]["name"]
            except:
                pass

            # 检查是否是伤病状态
            try:
                is_injured = adapted_data.get("is_injured_player", False)
                if is_injured:
                    injury_details = adapted_data.get("injury_description", "")
                    return f"很遗憾，{player_name}因伤缺席了本场比赛。{injury_details}希望他早日康复，重返赛场！💪"
            except:
                pass

            return f"{player_name}在本场比赛中表现值得关注。"

    def generate_shot_chart_text(self, adapted_data: Dict[str, Any]) -> str:
        """
        生成球员投篮图解说 - 使用单独的prompt

        Args:
            adapted_data: 适配器提供的数据

        Returns:
            生成的投篮图解说字符串
        """
        if self.debug_mode:
            self._log_start(f"球员投篮图解说")

        if not adapted_data or "error" in adapted_data:
            player_name = adapted_data.get("player_info", {}).get("name", "球员")
            return f"{player_name}本场比赛的投篮分布图显示了他的得分热区和命中情况。"

        try:
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

            # 提取投篮数据分析所需数据
            player_info = adapted_data["player_info"]
            shot_data = adapted_data["shot_data"]
            shooting_stats = adapted_data.get("shooting_stats", {})

            player_data = {
                "player_name": player_info["name"],
                "shot_data": shot_data,
                "shooting_stats": shooting_stats
            }

            prompt = prompt.format(
                player_data=json.dumps(player_data, ensure_ascii=False)
            )

            result = self.ai_processor.generate(prompt).strip()

            if self.debug_mode:
                self._log_result(f"球员投篮图解说", {"text_length": len(result),
                                                     "preview": result[:100] + "..." if len(result) > 100 else result})

            return result

        except Exception as e:
            self.logger.error(f"生成球员投篮图解说失败: {e}", exc_info=True)
            player_name = adapted_data.get("player_info", {}).get("name", "球员")
            return f"{player_name}本场比赛的投篮分布图显示了他的得分热区和命中情况。"

    def generate_team_shot_analysis(self, adapted_data: Dict[str, Any]) -> str:
        """
        生成球队投篮分析 - 使用单独的prompt

        Args:
            adapted_data: 适配器提供的数据

        Returns:
            生成的球队投篮分析字符串
        """
        if self.debug_mode:
            self._log_start(f"球队投篮分析")

        if not adapted_data or "error" in adapted_data:
            team_name = adapted_data.get("team_info", {}).get("team_name", "球队")
            return f"{team_name}球队本场比赛的投篮分布展示了团队的进攻策略和热区。"

        try:
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

            # 提取球队投篮分析所需数据
            team_info = adapted_data["team_info"]
            opponent_info = adapted_data.get("opponent_info", {})
            shot_data = adapted_data["shot_data"]
            shooting_stats = adapted_data.get("shooting_stats", {})
            game_info = adapted_data["game_info"]

            team_data = {
                "team_name": team_info["team_name"],
                "team_tricode": team_info["team_tricode"],
                "opponent": opponent_info.get("team_name", "对手"),
                "shot_data": shot_data,
                "shooting_stats": shooting_stats,
                "game_info": game_info
            }

            prompt = prompt.format(
                team_data=json.dumps(team_data, ensure_ascii=False)
            )

            result = self.ai_processor.generate(prompt).strip()

            if self.debug_mode:
                self._log_result(f"球队投篮分析", {"analysis_length": len(result),
                                                   "preview": result[:100] + "..." if len(result) > 100 else result})

            return result

        except Exception as e:
            self.logger.error(f"生成球队投篮分析失败: {e}", exc_info=True)
            team_name = adapted_data.get("team_info", {}).get("team_name", "球队")
            return f"{team_name}球队本场比赛的投篮分布展示了团队的进攻策略和热区。"

    def generate_round_analysis(self, adapted_data: Dict[str, Any], current_round: int) -> str:
        """
        生成回合解说分析 - 使用单独的prompt

        Args:
            adapted_data: 适配器提供的数据
            current_round: 当前回合ID

        Returns:
            生成的回合解说字符串
        """
        if self.debug_mode:
            self._log_start(f"回合解说分析(回合{current_round})")

        rounds = adapted_data.get("rounds", [])
        if not rounds:
            return "暂无回合数据。"

        try:
            # 回合解说prompt
            prompt = """
                你是一名专业的NBA解说员，也是洛杉矶湖人队的**铁杆**球迷，更是勒布朗的资深粉丝！需要对以下回合数据进行专业解说。\n
                请结合上下文（共计{num_rounds}个回合）进行连贯且专业的描述，语言要求生动、富有现场感，类似于NBA直播解说。\n
                请着重指出当前回合（编号{current_round}）的关键转折和精彩瞬间，并联系前后三回合进行综合点评。\n
                语言要有趣，能吸引观众，适合在微博等社交平台发布。\n
                回合数据：{rounds_data}
                """

            # 查找当前回合及其上下文
            current_round_data = None
            context_rounds = []

            for round_data in rounds:
                if round_data["action_number"] == current_round:
                    current_round_data = round_data
                    break

            if current_round_data:
                # 添加相邻回合作为上下文
                if "context" in current_round_data:
                    context_rounds = current_round_data["context"]
                else:
                    # 找出前后三个回合
                    current_index = rounds.index(current_round_data)
                    start = max(0, current_index - 3)
                    end = min(len(rounds), current_index + 4)
                    context_rounds = rounds[start:end]
            else:
                return "未找到指定回合数据。"

            # 准备回合数据
            rounds_data = {
                "current_round": current_round_data,
                "context_rounds": context_rounds,
                "player_name": adapted_data["player_info"]["name"]
            }

            prompt = prompt.format(
                num_rounds=len(context_rounds) + 1,  # +1 因为还有当前回合
                current_round=current_round,
                rounds_data=json.dumps(rounds_data, ensure_ascii=False)
            )

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

    def _batch_generate_round_analyses(self, adapted_data: Dict[str, Any], round_ids: List[int], player_name: str) -> \
    Dict[str, str]:
        """批量生成多个回合的解说内容 - 使用单独的prompt"""
        if self.debug_mode:
            self._log_start(f"批量回合解说({player_name}, {len(round_ids)}个回合)")

        try:
            # 提取回合数据
            all_rounds = adapted_data.get("rounds", [])
            if not all_rounds:
                self.logger.warning(f"未找到回合数据")
                return {}

            # 筛选需要解说的回合
            filtered_rounds = []
            matched_ids = []

            for round_id in round_ids:
                for round_data in all_rounds:
                    if round_data["action_number"] == round_id:
                        # 创建回合数据的简化副本，移除可能导致循环引用的字段
                        simplified_round = {
                            "action_number": round_data.get("action_number"),
                            "action_type": round_data.get("action_type"),
                            "player_name": round_data.get("player_name"),
                            "description": round_data.get("description", ""),
                            "period": round_data.get("period"),
                            "clock": round_data.get("clock"),
                            "score_home": round_data.get("score_home"),
                            "score_away": round_data.get("score_away"),
                            "shot_result": round_data.get("shot_result", ""),
                            "shot_distance": round_data.get("shot_distance", ""),
                            "assist_person_id": round_data.get("assist_person_id"),
                            "assist_player_name_initial": round_data.get("assist_player_name_initial")
                            # 注意：特意不包含context字段
                        }
                        filtered_rounds.append(simplified_round)
                        matched_ids.append(round_id)
                        break

            # 记录匹配情况
            self.logger.info(f"成功匹配 {len(matched_ids)}/{len(round_ids)} 个回合ID")

            # 如果没有匹配到任何回合数据，返回空结果
            if not filtered_rounds:
                self.logger.error("没有找到任何匹配的回合数据，无法生成解说")
                return {}

            # 批量回合解说prompt
            prompt = """
                你是NBA中文解说员，也是洛杉矶湖人队的**铁杆**球迷，更是勒布朗的资深粉丝！
                需要为以下{num_rounds}个回合事件用中文生成精彩的解说。

                球员: {player_name}

                请为以下每个回合ID生成一段专业而详细的中文解说，要求：
                1. 每段解说长度为100-150字之间，内容必须详尽丰富
                2. 请结合该回合前后的比赛情况，用富有感情和现场感的语言描述回合中的动作、球员表现和场上情况，类似于NBA直播解说。
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
                num_rounds=len(filtered_rounds),
                player_name=player_name,
                round_ids=[rd.get('action_number') for rd in filtered_rounds],
                round_data=json.dumps(filtered_rounds, ensure_ascii=False)  # 这里使用简化后的数据
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
                    self.logger.info(f"提取的JSON字符串: {json_str[:100]}...")
                    json_data = json.loads(json_str)

                    # 处理JSON数据
                    if "analyses" in json_data:
                        for item in json_data["analyses"]:
                            round_id = item.get("round_id")
                            analysis = item.get("analysis")
                            if round_id is not None and analysis:
                                analyses[str(round_id)] = analysis

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

    def _generate_simple_round_content(self, adapted_data: Dict[str, Any], round_id: int, player_name: str,
                                       round_index: int = 1, total_rounds: int = 1) -> str:
        """
        生成简单的回合解说内容，专门处理助攻回合
        """
        if self.debug_mode:
            self._log_start(f"简单回合解说(回合{round_id})")

        try:
            # 查找当前回合数据
            current_round = None
            for round_data in adapted_data.get("rounds", []):
                if round_data["action_number"] == round_id:
                    current_round = round_data
                    break

            # 检查这是否是一个助攻回合
            is_assist_round = False
            assist_description = ""

            if current_round and current_round["action_type"] in ["2pt", "3pt"] and "assist_person_id" in current_round:
                is_assist_round = True
                shooter_name = current_round.get("player_name", "队友")
                shot_type = "三分球" if current_round["action_type"] == "3pt" else "两分球"
                shot_result = "命中" if current_round.get("shot_result") == "Made" else "未命中"
                assist_description = f"{player_name}传出精彩助攻，{shooter_name}{shot_result}一记{shot_type}。"

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

        except Exception as e:
            self.logger.error(f"生成简单回合解说失败: {e}", exc_info=True)
            return f"{player_name}在本场比赛中展现了精彩表现。"

    def _format_round_content(self, adapted_data: Dict[str, Any], round_id: int, player_name: str,
                              analysis_text: str, round_index: int = 1, total_rounds: int = 1) -> str:
        """
        格式化回合解说内容 - 增加自动换行提高可读性
        """
        if self.debug_mode:
            self._log_start(f"格式化回合内容(回合{round_id})")

        try:
            # 查找回合事件
            round_event = None
            for event in adapted_data.get("rounds", []):
                if event["action_number"] == round_id:
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