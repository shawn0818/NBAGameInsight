# utils/ai_processor.py

from dataclasses import dataclass
from typing import Optional, Dict, List, Any
from functools import lru_cache
import json
import time
from enum import Enum
from openai import OpenAI, APITimeoutError, APIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from utils.logger_handler import AppLogger

class PromptRole(Enum):
    NBA_ANALYST = "nba_analyst"
    NBA_SOCIAL_ANALYST = "nba_social_analyst"
    ZH_TRANSLATOR = "zh_translator"


class PromptTask(Enum):
    SUMMARY = "summary"
    TRANSLATION = "translation"
    WEIBO = "weibo"
    HIGHLIGHT = "highlight"


@dataclass
class AIConfig:
    providers: Dict[str, Dict[str, Any]]
    default_provider: str = "deepseek"
    max_retries: int = 3
    retry_delay: int = 1
    cache_size: int = 100
    timeout: int = 60

    def __post_init__(self):
        """后初始化验证和设置"""
        if self.default_provider not in self.providers:
            raise ValueError(f"默认 AI 提供商 '{self.default_provider}' 未在配置中定义")
        default_config = self.providers[self.default_provider]
        if 'model_name' not in default_config:
            default_config['model_name'] = "default-model"


class AIProcessor:
    PROMPTS = {
        "zh_translator": {
            "translation": """你是一位专业的 NBA 数据翻译员，精通中英文篮球术语。请将以下英文 NBA 数据或描述翻译成流畅、准确的中文，务必保持术语的专业性和一致性。"""
        },
        "nba_analyst": {
            "summary": """你是专业的 NBA 比赛分析师，精通中文篮球术语。
               请分析以下内容的关键点：
               1. 比赛转折点
               2. 球员表现
               3. 战术特点
               4. 胜负关键因素""",
        },
        "nba_social_analyst": {
            "weibo": """你是资深的NBA比赛分析师，同时也是NBA社交媒体运营编辑，需要制作吸引球迷的微博内容：
               1. 结合专业的比赛分析
               2. 使用简洁生动的语言
               3. 添加适当的emoji
               4. 突出比赛亮点
               5. 加入#话题标签#
               6. 控制在140字以内""",
            "highlight": """你是NBA集锦解说员，同时也是资深NBA分析师，需要为比赛精彩瞬间创作生动描述：
               1. 结合专业的比赛分析
               2. 描述动作特点
               3. 点明比赛形势
               4. 突出球员表现
               5. 使用专业术语"""
        }
    }

    PROVIDER_FACTORIES = {
        "deepseek": lambda config: OpenAI(
            api_key=config['api_key'],
            base_url=config['base_url'],
            timeout=config.get('timeout', 60.0),
            max_retries=config.get('max_retries', 3)
        ),
        "openai": lambda config: None,
        "gemini": lambda config: None,
    }

    def __init__(self, config: AIConfig, provider_name: Optional[str] = None):
        self.config = config
        self.logger = AppLogger.get_logger(__name__,app_name="ai")
        self.provider_name = provider_name or config.default_provider
        if self.provider_name not in config.providers:
            raise ValueError(f"指定的 AI 提供商 '{self.provider_name}' 未在配置中定义")

        provider_config = config.providers[self.provider_name]

        factory = self.PROVIDER_FACTORIES.get(self.provider_name.lower())
        if not factory:
            raise ValueError(f"不支持的 AI 提供商: '{self.provider_name}'")

        client = factory(provider_config)
        if client is None and self.provider_name.lower() != "deepseek":
            self.logger.warning(f"AI Provider '{self.provider_name}' is a placeholder and not fully implemented.")
            self.client = self.PROVIDER_FACTORIES["deepseek"](config.providers["deepseek"])
            self.provider_name = "deepseek"
        else:
            self.client = client

        self._request_count = 0
        self._last_request_time = 0

    def translate(self, text: str, target_language: str) -> str:
        """翻译文本到目标语言"""
        try:
            if not text:
                return text

            system_prompt = self.PROMPTS["zh_translator"]["translation"]
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

            system_prompt = self.PROMPTS["nba_social_analyst"]["weibo"]
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

            system_prompt = self.PROMPTS["nba_social_analyst"]["highlight"]
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
            if self.provider_name.lower() == "deepseek":
                response = self.client.chat.completions.create(
                    model=self.config.providers[self.provider_name]['model_name'],
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                    timeout=self.config.timeout
                )
                result_chunks = []
                for chunk in response:
                    if chunk.choices[0].delta.content:
                        result_chunks.append(chunk.choices[0].delta.content)

                final_result = "".join(result_chunks).strip()
                self.logger.debug(f"收到AI响应: {final_result[:200]}...")
                return final_result

            elif self.provider_name.lower() in ["openai", "gemini"]:
                self.logger.warning(f"AI Provider '{self.provider_name}' is a placeholder, returning '生成失败'.")
                return "生成失败"
            else:
                raise ValueError(f"Unknown AI Provider: '{self.provider_name}'")


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