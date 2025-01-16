"""比赛信息显示服务

集成 DeepSeek API 实现智能翻译和内容总结
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path
from openai import OpenAI
import json
from datetime import datetime

from nba.models.game_model import Game, PlayerStatistics


@dataclass
class AIConfig:
    """AI 服务配置"""
    api_key: str = "sk-e2170a0aac6545c19f21b063a5c2632b"
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    temperature: float = 1.0
    max_tokens: int = 1000
    timeout: int = 30


@dataclass
class DisplayConfig:
    """显示配置"""
    language: str = "zh_CN"
    date_format: str = "%Y-%m-%d %H:%M"
    number_format: str = ",.2f"
    show_advanced_stats: bool = True
    template_dir: Optional[Path] = None


class DisplayService:
    """比赛信息显示服务"""

    def __init__(
            self,
            display_config: Optional[DisplayConfig] = None,
            ai_config: Optional[AIConfig] = None
    ):
        """初始化显示服务"""
        self.display_config = display_config or DisplayConfig()
        self.ai_config = ai_config
        self.logger = logging.getLogger(self.__class__.__name__)

        if self.ai_config:
            self.client = OpenAI(
                api_key=self.ai_config.api_key,
                base_url=self.ai_config.base_url
            )

    def _get_completion(self, prompt: str, system_prompt: str) -> str:
        """获取 AI 补全"""
        try:
            if not self.ai_config:
                raise ValueError("AI 服务未配置")

            response = self.client.chat.completions.create(
                model=self.ai_config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.ai_config.temperature,
                max_tokens=self.ai_config.max_tokens,
                stream=False
            )

            return response.choices[0].message.content

        except Exception as e:
            self.logger.error(f"获取 AI 补全时出错: {e}")
            return ""

    def translate_content(self, content: str, target_lang: str) -> str:
        """翻译内容"""
        system_prompt = """你是一个专业的体育内容翻译专家。
        你需要准确理解体育术语和行话，保持专业性的同时确保翻译的自然流畅。"""

        prompt = f"""请将以下体育内容翻译成{target_lang}：\n\n{content}"""

        return self._get_completion(prompt, system_prompt)

    def generate_game_summary(self, game: Game) -> str:
        """生成比赛总结"""
        if not game:
            return ""

        game_info = self._format_game_info(game)

        system_prompt = """你是一个专业的NBA比赛分析师，需要基于比赛数据生成专业、生动的比赛总结。"""

        prompt = f"""请基于以下比赛数据生成一份专业的比赛总结：

比赛数据：
{json.dumps(game_info, ensure_ascii=False, indent=2)}

要求：
- 总结比赛的关键情节
- 分析双方表现
- 突出重要数据
- 使用生动专业的语言
- 篇幅控制在500字以内
"""

        return self._get_completion(prompt, system_prompt)

    def _format_game_info(self, game: Game) -> Dict[str, Any]:
        """格式化比赛信息"""
        try:
            return {
                "basic_info": {
                    "date": game.game.gameTimeLocal.isoformat(),
                    "arena": {
                        "name": game.game.arena.arenaName,
                        "city": game.game.arena.arenaCity,
                        "attendance": game.game.attendance
                    }
                },
                "teams": {
                    "home": {
                        "name": game.game.homeTeam.teamName,
                        "score": game.game.homeTeam.score,
                        "statistics": self._format_team_stats(game.game.homeTeam)
                    },
                    "away": {
                        "name": game.game.awayTeam.teamName,
                        "score": game.game.awayTeam.score,
                        "statistics": self._format_team_stats(game.game.awayTeam)
                    }
                },
                "officials": [
                    {
                        "name": official.name,
                        "position": official.assignment
                    }
                    for official in game.game.officials
                ]
            }
        except Exception as e:
            self.logger.error(f"格式化比赛信息时出错: {e}")
            return {}

    def _format_team_stats(self, team) -> Dict[str, Any]:
        """格式化球队统计数据"""
        try:
            # 确保 statistics 是 TeamStats 类型而不是 dict
            if not hasattr(team, 'statistics'):
                self.logger.error("Team object has no statistics attribute")
                return {}
            
            stats = team.statistics
            if not hasattr(stats, 'fieldGoalsMade'):
                # 如果是字典类型，使用 get 方法
                return {
                    "field_goals": f"{stats.get('fieldGoalsMade', 0)}/{stats.get('fieldGoalsAttempted', 0)}",
                    "field_goals_pct": stats.get('fieldGoalsPercentage', 0.0),
                    "three_points": f"{stats.get('threePointersMade', 0)}/{stats.get('threePointersAttempted', 0)}",
                    "three_points_pct": stats.get('threePointersPercentage', 0.0),
                    "assists": stats.get('assists', 0),
                    "rebounds": stats.get('reboundsTotal', 0),
                    "steals": stats.get('steals', 0),
                    "blocks": stats.get('blocks', 0),
                    "turnovers": stats.get('turnovers', 0)
                }
            
            # 如果是对象类型，直接访问属性
            return {
                "field_goals": f"{stats.fieldGoalsMade}/{stats.fieldGoalsAttempted}",
                "field_goals_pct": stats.fieldGoalsPercentage,
                "three_points": f"{stats.threePointersMade}/{stats.threePointersAttempted}",
                "three_points_pct": stats.threePointersPercentage,
                "assists": stats.assists,
                "rebounds": stats.reboundsTotal,
                "steals": stats.steals,
                "blocks": stats.blocks,
                "turnovers": stats.turnovers
            }
        except Exception as e:
            self.logger.error(f"格式化球队统计数据时出错: {e}")
            return {}

    def analyze_player_performance(self, player_name: str, stats: Dict[str, Any]) -> str:
        """分析球员表现"""
        system_prompt = """你是一个专业的NBA球员分析师，需要基于统计数据进行深入分析。"""

        prompt = f"""请基于以下数据分析这位球员的表现：

球员数据：
{json.dumps(stats, ensure_ascii=False, indent=2)}

要求：
- 评估整体表现
- 突出数据亮点
- 分析效率指标
- 给出专业见解
- 篇幅300字左右
"""

        return self._get_completion(prompt, system_prompt)

    def analyze_key_moments(self, plays: List[Dict[str, Any]]) -> str:
        """分析关键时刻"""
        if not plays:
            return ""

        system_prompt = """你是一个专业的NBA比赛分析师，需要分析比赛的关键时刻和转折点。"""

        prompt = f"""请分析以下比赛回放数据中的关键时刻：

比赛回放：
{json.dumps(plays, ensure_ascii=False, indent=2)}

要求：
- 识别最关键的3-5个时刻
- 分析这些时刻的影响
- 评估相关决策
- 使用专业的分析视角
- 篇幅300字左右
"""

        return self._get_completion(prompt, system_prompt)

    def format_game_report(self, game: Game) -> Dict[str, Any]:
        """生成完整比赛报告"""
        try:
            if not game:
                return {}

            # 获取比赛基本信息
            game_info = self._format_game_info(game)

            # 生成报告各部分内容
            report = {
                "basic_info": game_info["basic_info"],
                "summary": self.generate_game_summary(game)
            }

            # 如果需要翻译
            if self.display_config.language != "en":
                for key in ["summary"]:
                    if report.get(key):
                        report[key] = self.translate_content(
                            report[key],
                            self.display_config.language
                        )

            return report

        except Exception as e:
            self.logger.error(f"生成比赛报告时出错: {e}")
            return {}