# utils/ai_processor.py

from dataclasses import dataclass
from typing import Optional, Dict, List, Any
from functools import lru_cache
import logging
import json
import time
from enum import Enum
from openai import OpenAI, APITimeoutError, APIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class PromptRole(Enum):
    NBA_ANALYST = "nba_analyst"
    SOCIAL_EDITOR = "social_editor"


class PromptTask(Enum):
    SUMMARY = "summary"
    TRANSLATION = "translation"
    WEIBO = "weibo"
    HIGHLIGHT = "highlight"


@dataclass
class AIConfig:
    api_key: str
    base_url: str
    model_name: str = "deepseek-chat"
    max_retries: int = 3
    retry_delay: int = 1
    cache_size: int = 100
    timeout: int = 60  # 增加默认超时时间


class AIProcessor:
    PROMPTS = {
        "nba_analyst": {
            "summary": """你是专业的 NBA 比赛分析师，精通中文篮球术语。
               请分析以下内容的关键点：
               1. 比赛转折点
               2. 球员表现 
               3. 战术特点
               4. 胜负关键因素""",
            "translation": """你是专业的 NBA 翻译，精通篮球术语。
               请准确翻译以下内容，保持专业性和术语准确性。"""
        },
        "social_editor": {
            "weibo": """你是NBA社交媒体运营编辑，需要制作吸引球迷的微博内容：
               1. 使用简洁生动的语言
               2. 添加适当的emoji
               3. 突出比赛亮点
               4. 加入#话题标签#
               5. 控制在140字以内""",
            "highlight": """你是NBA集锦解说员，需要为比赛精彩瞬间创作生动描述：
               1. 描述动作特点
               2. 点明比赛形势
               3. 突出球员表现
               4. 使用专业术语"""
        }
    }

    def __init__(self, config: AIConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=60.0,  # 增加全局超时时间
            max_retries=3  # 设置重试次数
        )
        self._request_count = 0
        self._last_request_time = 0

    def translate(self, text: str, target_language: str) -> str:
        """翻译文本到目标语言"""
        try:
            if not text:
                return text

            system_prompt = self.PROMPTS["nba_analyst"]["translation"]
            user_prompt = f"请翻译成{target_language}:\n\n{text}"

            self.logger.debug(f"开始翻译文本: {text[:100]}...")
            result = self._get_completion(system_prompt, user_prompt, temperature=0.3)

            if result == "生成失败":
                return text

            return result
        except Exception as e:
            self.logger.error(f"翻译失败: {str(e)}")
            return text

    def generate_summary(self, content: str, context: str = "", max_length: int = 100) -> str:
        """生成内容摘要"""
        try:
            if not content:
                return "生成失败"

            # 预处理输入数据
            if isinstance(content, (dict, list)):
                content = json.dumps(content, ensure_ascii=False, indent=2)

            system_prompt = self.PROMPTS["nba_analyst"]["summary"]
            user_prompt = f"请总结(限{max_length}字):\n\n{content}\n背景:{context}"

            self.logger.debug(f"开始生成摘要, 内容长度: {len(content)}")
            return self._get_completion(system_prompt, user_prompt, max_tokens=max_length)
        except Exception as e:
            self.logger.error(f"生成摘要失败: {str(e)}")
            return "生成失败"

    def generate_weibo_post(self, content: str, post_type: str = "game_summary") -> str:
        """生成微博内容"""
        try:
            if not content:
                return "生成失败"

            if isinstance(content, (dict, list)):
                content = json.dumps(content, ensure_ascii=False, indent=2)

            system_prompt = self.PROMPTS["social_editor"]["weibo"]
            user_prompt = f"请生成微博:\n\n{content}"

            self.logger.debug(f"开始生成微博, 类型: {post_type}")
            return self._get_completion(system_prompt, user_prompt, max_tokens=140)
        except Exception as e:
            self.logger.error(f"生成微博内容失败: {str(e)}")
            return "生成失败"

    def generate_shots_summary(self, shots: List[str]) -> str:
        """生成投篮集锦总结"""
        try:
            if not shots:
                return "生成失败"

            system_prompt = self.PROMPTS["social_editor"]["highlight"]
            user_prompt = f"请总结这些投篮集锦(限140字):\n\n" + "\n".join(shots)

            self.logger.debug(f"开始生成投篮总结, 数量: {len(shots)}")
            return self._get_completion(system_prompt, user_prompt, max_tokens=140)
        except Exception as e:
            self.logger.error(f"生成投篮总结失败: {str(e)}")
            return "生成失败"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=5),
        retry=retry_if_exception_type((APITimeoutError, APIError))
    )
    @lru_cache(maxsize=100)
    def _get_completion(
            self,
            system_prompt: str,
            user_prompt: str,
            temperature: float = 0.7,
            max_tokens: int = 150,
    ) -> str:
        """获取AI完成结果"""
        try:
            # 限流控制
            current_time = time.time()
            if current_time - self._last_request_time < 1:
                time.sleep(1 - (current_time - self._last_request_time))

            self._last_request_time = time.time()
            self._request_count += 1

            # 构建请求
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            self.logger.debug(f"发送AI请求: {json.dumps(messages, ensure_ascii=False)[:200]}...")

            # 使用流式响应
            response = self.client.chat.completions.create(
                model=self.config.model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,  # 启用流式响应
                timeout=60.0  # 设置单次请求超时时间
            )

            # 收集流式响应内容
            result_chunks = []
            for chunk in response:
                if chunk.choices[0].delta.content:
                    result_chunks.append(chunk.choices[0].delta.content)

            final_result = "".join(result_chunks).strip()
            self.logger.debug(f"收到AI响应: {final_result[:200]}...")

            return final_result

        except Exception as e:
            self.logger.error(f"AI请求失败: {str(e)}", exc_info=True)
            raise

    def clear_cache(self):
        """清理缓存"""
        self._get_completion.cache_clear()
        self._request_count = 0
        self._last_request_time = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.clear_cache()