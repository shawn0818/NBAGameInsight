from typing import Dict, Any, Optional, List
import json
import logging
import re
from utils.time_handler import TimeHandler

# 常量定义
NBA_HASHTAG = "#NBA#"
BASKETBALL_HASHTAG = "#篮球#"

# Prompt 模板
COMPREHENSIVE_WEIBO_PROMPT = """
你是NBA官方微博的内容创作专家，擅长将复杂的比赛数据转化为引人入胜的中文社交媒体内容。
请基于以下NBA比赛数据，一次性生成所有所需的微博内容（全部内容必须是中文）：

1. 【比赛标题】(限30字)
   - 包含两队名称（中文）和最终比分
   - 突出胜负关系和关键表现
   - 适度使用emoji表情增强吸引力

2. 【比赛摘要】(150-200字)
   - 简明扼要总结比赛过程和关键转折点
   - 突出双方球队数据对比和特点
   - 提及关键球员的表现和数据

3. 【球员分析】(针对{player_name}，100-150字)
   - 深入剖析该球员在本场比赛的表现
   - 结合数据和比赛回合，分析他的优势与不足
   - 使用生动语言描述关键进球或助攻

4. 【投篮图解说】(针对{player_name}，80-100字)
   - 简明分析该球员本场比赛投篮分布特点
   - 突出命中率数据和投篮热区
   - 适合配合投篮图一起发布

5. 【球队投篮分析】(针对{team_name}，80-100字)
   - 分析球队整体投篮趋势和特点
   - 提及投篮命中率和三分球表现
   - 适合配合球队投篮分布图发布

6. 【回合解说】(每个回合100-150字)
   - 针对提供的回合ID列表，为每个回合生成专业解说
   - 解说内容生动详实，展现现场感和专业度
   - 描述回合中的技术动作和战术意图
   - 特别强调{player_name}在回合中的表现
   - 回合解说格式为：回合ID: "解说内容"

所有内容必须：
1. 完全使用中文表达，包括球队名称、球员名字和术语
2. 确保准确性，百分比数据保留两位小数
3. 风格生动活泼，适合微博平台传播
4. 适度使用emoji表情增强表现力

比赛数据: {game_data}
相关回合ID列表: {round_ids}

请以JSON格式返回所有内容：
{
  "title": "比赛标题",
  "summary": "比赛摘要",
  "player_analysis": "球员分析",
  "shot_chart_text": "投篮图解说",
  "team_shot_analysis": "球队投篮分析",
  "rounds": {
    "回合ID1": "该回合的解说内容",
    "回合ID2": "该回合的解说内容",
    ...更多回合
  },
  "hashtags": ["#话题1#", "#话题2#", "#话题3#", "#话题4#", "#话题5#"]
}
"""

# 以下保留现有的单独生成提示词，以便单独需要时使用
GAME_TITLE_PROMPT = (
    "你是一名专业的体育记者，擅长为NBA比赛创作简洁有力的中文标题。\n"
    "请基于以下信息生成一个中文标题，要求：\n"
    "1. 必须用中文表达，包括所有球队名称（{home_team} 和 {away_team}）；\n"
    "2. 明确包含比赛最终比分并强调胜负结果（{home_score} : {away_score}）；\n"
    "3. 标题字数控制在30字以内，简洁明了且适合社交媒体传播。\n"
    "4. 可以参考古典书名/章节风格，并适度使用Emoji来吸引注意。\n"
    "比赛信息：{game_info}"
)

GAME_SUMMARY_PROMPT = (
    "你是一名专业的体育记者，擅长为NBA比赛创作生动简洁的比赛总结。\n"
    "请根据以下比赛信息生成一段150-200字的中文比赛摘要，要求：\n"
    "1. 详细总结比赛的关键数据（如得分、篮板、助攻等）；\n"
    "2. 仔细查看提供数据中的关于比赛回合的部分，突出比赛过程中的关键转折点和重要时刻；\n"
    "3. 提及表现突出的球员，尤其是球队在进攻、组织、防守端表现较好的球员，并结合数据进行分析；\n"
    "4. 使用生动语言，适合社交媒体发布，适当使用emoji。\n"
    "5. 所有球队和球员名称均用中文，百分数只保留小数点后两位。\n"
    "比赛信息：{summary_data}"
)

PLAYER_ANALYSIS_PROMPT = (
    "你是一名NBA球员分析师，擅长通过数据和比赛表现分析球员影响力。\n"
    "请分析以下球员在本场比赛中的表现，要求：\n"
    "1. 仔细查看提供数据中的关于比赛回合的部分，针对球员本场比赛的表现进行深入剖析；\n"
    "2. 突出关键数据，并分析这些数据对比赛结果的影响，注意百分数只保留小数点后两位；\n"
    "3. 客观指出球员的亮点与不足（此处可以适当语言犀利或者幽默，但是不能刻薄、不尊重）；\n"
    "4. 控制在100-200字之间；\n"
    "5. 适合社交媒体发布，可适度加入中式幽默，适当使用emoji；\n"
    "6. 所有专业术语用中文，球员名字也要使用中文。\n"
    "球员信息：{analysis_data}"
)

ROUND_ANALYSIS_PROMPT = (
    "你是一名专业的NBA解说员，需要对以下回合数据进行专业解说。\n"
    "请结合上下文（共计{num_rounds}个回合）进行连贯且专业的描述，语言要求生动、富有现场感，类似于NBA直播解说。\n"
    "请着重指出当前回合（编号{current_round}）的关键转折和精彩瞬间，并联系前后三回合进行综合点评。\n"
    "语言要有趣，能吸引观众，适合在微博等社交平台发布。\n"
    "回合数据：{rounds_data}"
)


# 辅助函数：提取球队信息
def get_team_info(ai_data: Dict[str, Any]) -> Dict[str, str]:
    game_info = ai_data.get("game_info", {})
    teams = game_info.get("teams", {})
    return {
        "home_full": teams.get("home", {}).get("full_name", "主队"),
        "away_full": teams.get("away", {}).get("full_name", "客队"),
        "home_tricode": teams.get("home", {}).get("tricode", "主队"),
        "away_tricode": teams.get("away", {}).get("tricode", "客队"),
    }


# 辅助函数：提取比赛日期
def get_game_date(ai_data: Dict[str, Any]) -> str:
    return ai_data.get("game_info", {}).get("date", {}).get("beijing", "比赛日期")


# 辅助函数：提取比赛得分
def get_game_scores(ai_data: Dict[str, Any]) -> Dict[str, Any]:
    score_data = ai_data.get("game_status", {}).get("score", {})
    return {
        "home_score": score_data.get("home", {}).get("points", "?"),
        "away_score": score_data.get("away", {}).get("points", "?")
    }


class WeiboContentGenerator:
    """
    微博内容生成工具类

    负责基于AI友好数据生成适用于微博发布的内容，不直接依赖具体的数据模型。
    """

    def __init__(self, ai_processor: Any, logger: Optional[logging.Logger] = None) -> None:
        """
        初始化微博内容生成器

        Args:
            ai_processor: AI处理器实例，用于生成内容
            logger: 可选的日志记录器
        """
        self.ai_processor = ai_processor
        self.logger = logger or logging.getLogger(__name__)

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

    def format_game_time(self, period, clock):
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

    def generate_comprehensive_content(self, ai_data: Dict[str, Any], player_name: str = None,
                                       team_name: str = None, round_ids: List[int] = None) -> Dict[str, Any]:
        """一次性生成所有微博内容类型，包括回合解说

        Args:
            ai_data: 完整的比赛AI友好数据
            player_name: 需要分析的球员名称
            team_name: 需要分析的球队名称
            round_ids: 需要解说的回合ID列表

        Returns:
            包含所有内容类型的字典
        """
        player_name = player_name or ""
        team_name = team_name or ""
        round_ids = round_ids or []

        # 使用综合prompt
        prompt = COMPREHENSIVE_WEIBO_PROMPT.format(
            player_name=player_name,
            team_name=team_name,
            game_data=json.dumps(ai_data, ensure_ascii=False),
            round_ids=json.dumps(round_ids)
        )

        try:
            self.logger.info(f"正在生成综合微博内容 (球员:{player_name}, 球队:{team_name}, 回合数:{len(round_ids)})...")
            response = self.ai_processor.generate(prompt)

            # 提取JSON部分
            json_match = re.search(r'({[\s\S]*})', response)
            if json_match:
                content_json = json.loads(json_match.group(1))
                self.logger.info(f"成功生成全部微博内容，包含{len(content_json.get('rounds', {}))}个回合解说")
                return content_json
            else:
                self.logger.error("无法解析AI返回的JSON内容")
                return {"error": "内容解析失败"}

        except Exception as e:
            self.logger.error(f"生成综合内容失败: {e}", exc_info=True)
            # 返回基本的备用内容
            return {
                "title": f"{team_name}vs{player_name}精彩表现",
                "summary": "本场比赛精彩纷呈，双方展开激烈对抗。",
                "player_analysis": f"{player_name}在本场比赛中有出色发挥。",
                "shot_chart_text": f"{player_name}本场比赛投篮分布图显示了他的得分区域。",
                "team_shot_analysis": f"{team_name}球队整体投篮效率良好。",
                "rounds": {str(rid): f"{player_name}在这个回合展现出色表现！" for rid in round_ids},
                "hashtags": ["#NBA#", "#篮球#", "#比赛集锦#"]
            }

    def generate_game_title(self, ai_data: Dict[str, Any]) -> str:
        """
        生成比赛标题

        Returns:
            生成的比赛标题字符串
        """
        # 尝试使用综合内容生成
        try:
            comprehensive_content = self.generate_comprehensive_content(ai_data)
            if "title" in comprehensive_content and comprehensive_content["title"]:
                return comprehensive_content["title"]
        except Exception as e:
            self.logger.warning(f"使用综合生成标题失败，将使用单独生成: {e}")

        # 如果综合生成失败，退回到单独生成
        if not ai_data or "error" in ai_data:
            return "NBA精彩比赛"

        team_info = get_team_info(ai_data)
        game_info = ai_data.get("game_info", {})
        scores = get_game_scores(ai_data)
        prompt = GAME_TITLE_PROMPT.format(
            home_team=team_info["home_full"],
            away_team=team_info["away_full"],
            home_score=scores["home_score"],
            away_score=scores["away_score"],
            game_info=json.dumps(game_info, ensure_ascii=False)
        )
        try:
            title = self.ai_processor.generate(prompt)
            return title.strip().strip('"\'')
        except Exception as e:
            self.logger.error(f"生成比赛标题失败: {e}", exc_info=True)
            return f"{team_info['away_tricode']} vs {team_info['home_tricode']} 比赛集锦"

    def generate_game_summary(self, ai_data: Dict[str, Any]) -> str:
        """
        生成比赛摘要

        Returns:
            生成的比赛摘要字符串
        """
        # 尝试使用综合内容生成
        try:
            comprehensive_content = self.generate_comprehensive_content(ai_data)
            if "summary" in comprehensive_content and comprehensive_content["summary"]:
                return comprehensive_content["summary"]
        except Exception as e:
            self.logger.warning(f"使用综合生成摘要失败，将使用单独生成: {e}")

        # 如果综合生成失败，退回到单独生成
        if not ai_data or "error" in ai_data:
            return ""

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

        prompt = GAME_SUMMARY_PROMPT.format(
            summary_data=json.dumps(summary_data, ensure_ascii=False)
        )
        try:
            return self.ai_processor.generate(prompt).strip()
        except Exception as e:
            self.logger.error(f"生成比赛摘要失败: {e}", exc_info=True)
            team_info = get_team_info(ai_data)
            return (
                f"{team_info['away_full']}对阵{team_info['home_full']}的比赛，"
                f"比分{get_game_scores(ai_data)['away_score']}-"
                f"{get_game_scores(ai_data)['home_score']}。"
            )

    def generate_player_analysis(self, ai_data: Dict[str, Any], player_name: str) -> str:
        """
        生成球员表现分析

        Returns:
            生成的球员分析字符串
        """
        # 尝试使用综合内容生成
        try:
            comprehensive_content = self.generate_comprehensive_content(ai_data, player_name=player_name)
            if "player_analysis" in comprehensive_content and comprehensive_content["player_analysis"]:
                return comprehensive_content["player_analysis"]
        except Exception as e:
            self.logger.warning(f"使用综合生成球员分析失败，将使用单独生成: {e}")

        # 如果综合生成失败，退回到单独生成
        if not ai_data or not player_name or "error" in ai_data:
            return ""

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
            "team_name": get_team_info(ai_data).get(f"{team_type}_full", ""),
            "opponent": "home" if team_type == "away" else "away",
            "opponent_name": get_team_info(ai_data).get("home_full" if team_type == "away" else "away_full", ""),
            "game_result": ai_data.get("game_result", {}),
            "player_stats": player_data,
            "game_info": ai_data.get("game_info", {})
        }
        prompt = PLAYER_ANALYSIS_PROMPT.format(
            analysis_data=json.dumps(analysis_data, ensure_ascii=False)
        )
        try:
            return self.ai_processor.generate(prompt).strip()
        except Exception as e:
            self.logger.error(f"生成球员分析失败: {e}", exc_info=True)
            return f"{player_name}在本场比赛中有出色表现。"

    def generate_shot_chart_text(self, ai_data: Dict[str, Any], player_name: str) -> str:
        """
        生成球员投篮图解说

        Returns:
            生成的投篮图解说字符串
        """
        # 从综合内容中获取
        try:
            comprehensive_content = self.generate_comprehensive_content(ai_data, player_name=player_name)
            if "shot_chart_text" in comprehensive_content and comprehensive_content["shot_chart_text"]:
                return comprehensive_content["shot_chart_text"]
        except Exception as e:
            self.logger.warning(f"获取球员投篮图解说失败: {e}")
            return f"{player_name}本场比赛的投篮分布图显示了他的得分热区和命中情况。"

    def generate_team_shot_analysis(self, ai_data: Dict[str, Any], team_name: str) -> str:
        """
        生成球队投篮分析

        Returns:
            生成的球队投篮分析字符串
        """
        # 从综合内容中获取
        try:
            comprehensive_content = self.generate_comprehensive_content(ai_data, team_name=team_name)
            if "team_shot_analysis" in comprehensive_content and comprehensive_content["team_shot_analysis"]:
                return comprehensive_content["team_shot_analysis"]
        except Exception as e:
            self.logger.warning(f"获取球队投篮分析失败: {e}")
            return f"{team_name}球队本场比赛的投篮分布展示了团队的进攻策略和热区。"

    def generate_round_analysis(self, ai_data: Dict[str, Any], current_round: int) -> str:
        """
        生成回合解说分析

        Returns:
            生成的回合解说字符串
        """
        rounds = ai_data.get("rounds", [])
        if not rounds:
            return "暂无回合数据。"

        start = max(0, current_round - 4)
        end = min(len(rounds), current_round + 4)
        context_rounds = rounds[start:end]
        prompt = ROUND_ANALYSIS_PROMPT.format(
            num_rounds=len(context_rounds),
            current_round=current_round,
            rounds_data=json.dumps(context_rounds, ensure_ascii=False)
        )
        try:
            return self.ai_processor.generate(prompt).strip()
        except Exception as e:
            self.logger.error(f"生成回合解说失败: {e}", exc_info=True)
            return "回合解说生成失败，请稍后重试。"

    def batch_generate_round_analyses(self, ai_data, round_ids, player_name, player_id=None):
        """批量生成多个回合的解说内容"""
        try:
            # 使用综合内容生成
            comprehensive_content = self.generate_comprehensive_content(
                ai_data,
                player_name=player_name,
                round_ids=round_ids
            )

            # 从综合内容中提取回合解说
            if "rounds" in comprehensive_content and comprehensive_content["rounds"]:
                round_analyses = comprehensive_content["rounds"]
                # 将string类型的键转换为整数类型
                return {int(k): v for k, v in round_analyses.items()}

            # 如果回合解说为空，则回退到旧方法
            self.logger.warning("从综合内容中未获取到回合解说，将使用旧方法")

            # 以下是原有的实现，作为备选
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

            # 构建批量分析请求，要求返回JSON格式
            batch_prompt = f"""
    你是NBA中文解说员，需要为以下{len(filtered_rounds_data)}个回合事件用中文生成精彩的解说。

    球员: {player_name}

    请为以下每个回合ID生成一段专业而详细的中文解说，要求：
    1. 每段解说长度为100-150字之间，内容必须详尽丰富
    2. 用富有感情和现场感的语言描述回合中的动作、球员表现和场上情况
    3. 使用正确的篮球术语和专业词汇
    4. 根据回合类型(投篮、助攻、防守等)强调不同的细节
    5. 解说内容必须完全使用中文，包括术语、数字描述等全部用中文表达
    6. 特别注意描述{player_name}的表现，展现他的技术特点和比赛影响力
    7. 内容要生动精彩，适合微博发布

    回合ID列表: {[rd.get('action_number') for rd in filtered_rounds_data]}

    请结合整场比赛的背景，基于以下回合事件数据来生成解说:
    {json.dumps(filtered_rounds_data, ensure_ascii=False)}

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

            # 发送批量请求
            self.logger.info("正在调用AI生成中文解说内容(JSON格式)...")
            response = self.ai_processor.generate(batch_prompt)

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

            return analyses

        except Exception as e:
            self.logger.error(f"批量生成回合解说失败: {e}", exc_info=True)
            return {}

    def _generate_simple_round_content(self, ai_data: Dict[str, Any], round_id: int, player_name: str,
                                       round_index: int = 1, total_rounds: int = 1) -> str:
        """
        生成简单的回合解说内容，专门处理助攻回合
        """
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
        formatted_time = f"第{round_index}回合"

        # 根据是否是助攻回合生成不同内容
        if is_assist_round:
            content = f"{player_name}展现出色的传球视野，送出一记精准助攻！{assist_description}这样的传球展现了他作为全场组织者的能力，不仅能得分，更能帮助队友创造得分机会。"
        else:
            content = f"{player_name}在这个回合展现出色表现！无论是得分、传球还是防守，都展示了他的全面技术和领袖气质。"

        return content

    def _format_round_content(self, ai_data: Dict[str, Any], round_id: int, player_name: str,
                              analysis_text: str, round_index: int = 1, total_rounds: int = 1) -> str:
        """
        格式化回合解说内容 - 增加自动换行提高可读性
        """
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
            formatted_time = self.format_game_time(period, clock)

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
                    content += self.generate_fallback_content(round_event, player_name, round_index, total_rounds)
                else:
                    content += f"{player_name}在这个回合展现出色表现！"

            # 添加固定标签（与正文间增加一个空行）
            if "#NBA#" not in content:
                content += "\n\n#NBA# #湖人# #勒布朗# #詹姆斯#"

            return content
        except Exception as e:
            self.logger.error(f"格式化回合内容失败: {e}", exc_info=True)
            # 返回一个简单的备用内容
            return f"{player_name}本场表现回顾{round_index}/{total_rounds}\n\n精彩表现！\n\n#NBA# #湖人# #勒布朗# #詹姆斯#"

    def generate_fallback_content(self, round_data, player_name, round_index=1, total_rounds=1):
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
            formatted_time = self.format_game_time(period, clock)

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

            return content
        except Exception as e:
            self.logger.error(f"生成备选内容失败: {e}")
            return f"{player_name}在这个回合展现出色表现！"

    def prepare_weibo_content(self, ai_data: Dict[str, Any], post_type: str = "game",
                              player_name: Optional[str] = None, round_number: Optional[int] = None) -> Dict[str, str]:
        """
        准备微博发布内容，使用新的综合内容生成方法

        Args:
            ai_data: AI友好数据
            post_type: 发布类型，可选值: game(比赛), player(球员), chart(图表), team_chart(球队图表), round(回合解说)
            player_name: 球员名称，仅当post_type为player或chart或round时需要
            round_number: 回合号，仅当post_type为round时需要

        Returns:
            包含 title 和 content 的字典
        """
        if not ai_data or "error" in ai_data:
            return {"title": "NBA精彩瞬间", "content": f"NBA比赛精彩集锦 {NBA_HASHTAG} {BASKETBALL_HASHTAG}"}

        # 先尝试获取所有内容，团队名称根据需要确定
        team_name = None
        if post_type == "team_chart":
            team_name = player_name  # 在team_chart模式下，player_name实际上是team_name

        # 如果是回合解说，则需要传入回合ID列表
        round_ids = None
        if post_type == "round" and round_number is not None:
            round_ids = [round_number] if isinstance(round_number, int) else round_number

        # 获取综合内容
        comprehensive_content = self.generate_comprehensive_content(
            ai_data,
            player_name=player_name if post_type != "team_chart" else None,
            team_name=team_name,
            round_ids=round_ids
        )

        # 默认标题
        title = comprehensive_content.get("title", "NBA精彩比赛")

        # 根据不同类型组织内容
        if post_type == "game":
            summary = comprehensive_content.get("summary", "")
            hashtags = " ".join(comprehensive_content.get("hashtags", ["#NBA#", "#篮球#"]))
            content = f"{summary}\n\n{hashtags}"
        elif post_type == "player" and player_name:
            player_analysis = comprehensive_content.get("player_analysis", "")
            hashtags = " ".join(comprehensive_content.get("hashtags", ["#NBA#", "#篮球#", f"#{player_name}#"]))
            content = f"{player_analysis}\n\n{hashtags}"
            title = f"{title} - {player_name}个人集锦"
        elif post_type == "chart" and player_name:
            shot_chart_text = comprehensive_content.get("shot_chart_text", f"{player_name}本场比赛投篮分布图")
            hashtags = " ".join(comprehensive_content.get("hashtags", ["#NBA#", "#篮球#", f"#{player_name}#"]))
            content = f"{player_name}本场比赛投篮分布图\n\n{shot_chart_text}\n\n{hashtags}"
            title = f"{title} - {player_name}投篮分布"
        elif post_type == "team_chart" and team_name:
            team_shot_analysis = comprehensive_content.get("team_shot_analysis", f"{team_name}球队本场比赛投篮分布图")
            hashtags = " ".join(comprehensive_content.get("hashtags", ["#NBA#", "#篮球#", f"#{team_name}#"]))
            content = f"{team_name}球队本场比赛投篮分布图\n\n{team_shot_analysis}\n\n{hashtags}"
            title = f"{title} - {team_name}球队投篮分布"
        elif post_type == "round" and round_number is not None and player_name:
            # 对于回合解说，我们只需要返回JSON内容，因为实际发布时会用_format_round_content格式化
            round_id = round_number[0] if isinstance(round_number, list) else round_number
            round_content = None

            # 从综合内容中获取此回合的解说
            if "rounds" in comprehensive_content:
                round_content = comprehensive_content["rounds"].get(str(round_id))

            if not round_content:
                # 如果没有找到解说，生成简单解说
                round_content = self._generate_simple_round_content(ai_data, round_id, player_name)

            content = round_content
            title = f"{title} - {player_name}回合#{round_id}解说"
        else:
            content = f"NBA精彩比赛 {NBA_HASHTAG} {BASKETBALL_HASHTAG}"

        return {"title": title.strip(), "content": content.strip()}