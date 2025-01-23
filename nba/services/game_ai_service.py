# nba/services/game_ai_service.py

from openai import OpenAI
from dataclasses import dataclass
import logging
from typing import Optional


@dataclass
class AIConfig:
    """AI配置类"""
    api_key: str
    base_url: str
    model_name: str = "deepseek-chat"


class AIService:
    """AI服务，处理所有与AI相关的功能，包括翻译和文本生成"""

    def __init__(self, config: AIConfig):
        """
        初始化AI服务

        Args:
            config: AI配置对象
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    def translate(self, text: str, target_language: str) -> str:
        """
        翻译文本到目标语言

        Args:
            text: 要翻译的文本
            target_language: 目标语言代码，例如 "en_US" 或 "zh_CN"

        Returns:
            翻译后的文本
        """
        self.logger.info(f"开始翻译文本，目标语言: {target_language}")

        try:
            system_prompt = (
                f"你是一个专业的 NBA 翻译助手，精通篮球术语和 NBA 相关内容的翻译。"
                f"请将文本准确翻译成{target_language}，保持专业性，"
                f"确保篮球术语、球员名字和球队名称的准确性。"
                f"如果遇到专业术语，应使用目标语言中约定俗成的表达方式。"
            )
            user_prompt = f"请将以下 NBA 相关内容翻译成{target_language}:\n\n{text}"

            return self._get_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=500
            )
        except Exception as e:
            self.logger.error(f"翻译时出错: {e}", exc_info=True)
            return text

    def generate_summary(self, content: str, context: str = "", max_length: int = 100) -> str:
        """
        生成 NBA 比赛内容总结

        Args:
            content: 需要总结的比赛内容
            context: 额外的比赛背景信息
            max_length: 最大字数限制
        """
        try:
            system_prompt = (
                "你是一个专业的 NBA 比赛分析师，精通中文篮球术语。"
                "请从专业角度分析比赛数据与过程，重点关注："
                "1. 比赛的关键转折点"
                "2. 双方球员的突出表现"
                "3. 战术特点和效果"
                "4. 胜负关键因素"
                "使用专业、准确的篮球术语。"
            )

            user_prompt = (
                f"请基于以下信息生成一个专业的NBA比赛分析总结：\n\n"
                f"比赛内容：\n{content}\n"
                f"比赛背景：\n{context}\n"
                f"要求：\n"
                f"- 总结控制在{max_length}字以内\n"
                f"- 重点分析比赛胜负的关键因素\n"
                f"- 点评关键球员的表现\n"
                f"- 分析战术层面的特点"
            )

            return self._get_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=250  # 增加 token 限制以获得更详细的分析
            )
        except Exception as e:
            self.logger.error(f"生成比赛总结时出错: {e}", exc_info=True)
            return "AI分析不可用。"


    def _get_completion(
            self,
            system_prompt: str,
            user_prompt: str,
            temperature: float = 0.7,
            max_tokens: int = 150
    ) -> str:
        """
        获取AI完成结果的内部方法

        Args:
            system_prompt: 系统提示
            user_prompt: 用户提示
            temperature: 温度参数，控制输出的随机性
            max_tokens: 最大标记数

        Returns:
            AI生成的文本
        """
        try:
            client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url
            )

            response = client.chat.completions.create(
                model=self.config.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False
            )

            return response.choices[0].message.content.strip()
        except Exception as e:
            self.logger.error(f"获取AI完成时出错: {e}", exc_info=True)
            raise