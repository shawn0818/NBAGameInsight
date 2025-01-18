# nba/services/ai_service.py

from dataclasses import dataclass
import logging
import openai
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

        # 配置OpenAI SDK
        openai.api_key = self.config.api_key
        openai.api_base = self.config.base_url

    def translate(self, text: str, target_language: str) -> str:
        """
        翻译文本到目标语言

        Args:
            text: 要翻译的文本
            target_language: 目标语言代码，例如 "en_US" 或 "zh_CN"

        Returns:
            翻译后的文本
        """
        try:
            system_prompt = f"你是一个专业的翻译助手，擅长将文本从任何语言翻译成{target_language}。"
            user_prompt = f"请将以下文本翻译成{target_language}:\n\n{text}"

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
        生成内容总结

        Args:
            content: 需要总结的内容
            context: 额外的上下文信息
            max_length: 最大字数限制

        Returns:
            生成的总结文本
        """
        try:
            system_prompt = "你是一个专业的体育内容分析师，擅长总结和分析体育相关内容。"
            user_prompt = (
                f"请基于以下内容生成一个简短的总结：\n\n"
                f"内容：\n{content}\n"
                f"上下文：\n{context}\n"
                f"要求：\n"
                f"- 简要总结关键点\n"
                f"- 使用简洁明了的语言\n"
                f"- 篇幅控制在{max_length}字以内\n"
            )

            return self._get_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=150
            )
        except Exception as e:
            self.logger.error(f"生成总结时出错: {e}", exc_info=True)
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
            response = openai.ChatCompletion.create(
                model=self.config.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False
            )

            return response.choices[0].message['content'].strip()
        except Exception as e:
            self.logger.error(f"获取AI完成时出错: {e}", exc_info=True)
            raise