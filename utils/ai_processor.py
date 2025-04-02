import logging
from enum import Enum
from typing import  Optional,  Callable
from dataclasses import dataclass
import os
import time
from utils.logger_handler import AppLogger
from openai import OpenAI


class AIProvider(Enum):
    """AI 服务提供商枚举"""
    OPENROUTER = "openrouter"
    DEEPSEEK = "deepseek"


class AIModel(Enum):
    """AI 模型枚举"""
    # OpenRouter 模型
    GPT4 = "openai/gpt-4"
    CLAUDE = "anthropic/claude-3.7-sonnet"
    GEMINI = "google/gemini-2.5-pro-exp-03-25:free"
    GEMINI_FLASH = "google/gemini-2.0-flash-001"
    # Deepseek 模型
    DEEPSEEK_CHAT = "deepseek-chat"
    DEEPSEEK_R1 = 'deepseek-reasoner'


@dataclass
class AIConfig:
    """AI 服务配置"""
    provider: AIProvider = AIProvider.DEEPSEEK
    model: AIModel = AIModel.DEEPSEEK_R1
    enable_translation: bool = True
    enable_creation: bool = True
    # 请求相关配置
    max_retries: int = 3
    retry_delay: int = 3  # 秒
    timeout: int = 100  # 秒
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    # 高级配置
    system_prompt: Optional[str] = None
    streaming: bool = False


class AIProcessor:
    """
    AI处理器: 提供与AI模型交互的通用接口，专注于NBA数据处理、翻译、摘要等功能。
    相比原版本，移除了PromptManager、PromptTemplate等，改为在各方法里直接写Prompt。
    """

    def __init__(self, config: Optional[AIConfig] = None, logger: Optional[logging.Logger] = None):
        """
        初始化AI处理器

        Args:
            config: AI配置，如果不提供则使用默认配置
            logger: 日志记录器，如果不提供则创建默认的
        """
        self.config = config or AIConfig()
        self.logger = logger or AppLogger.get_logger(__name__,app_name='AIProcessor')
        self.client = None
        self._init_client()


    def _init_client(self):
        """
        初始化AI服务客户端

        Raises:
            ValueError: 如果提供商的API密钥未找到
            ImportError: 如果缺少必要的包
            RuntimeError: 如果初始化客户端失败
        """
        try:
            if self.config.provider == AIProvider.OPENROUTER:
                self._init_openrouter_client()
            elif self.config.provider == AIProvider.DEEPSEEK:
                self._init_deepseek_client()
            else:
                raise ValueError(f"不支持的AI提供商: {self.config.provider}")
        except ImportError as e:
            self.logger.error(f"初始化客户端失败，缺少必要的包: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"初始化客户端失败: {str(e)}")
            raise RuntimeError(f"初始化AI客户端失败: {str(e)}")

    def _init_openrouter_client(self):
        """初始化OpenRouter客户端"""
        try:
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError("未找到OPENROUTER_API_KEY环境变量")

            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
                default_headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "HTTP-Referer": os.getenv("OPENROUTER_REFERER"),
                    "X-Title": os.getenv("OPENROUTER_TITLE")
                }
            )
            self.logger.info("OpenRouter客户端初始化成功")
        except ImportError:
            raise ImportError("请安装openai包: pip install openai>=1.0.0")

    def _init_deepseek_client(self):
        """初始化Deepseek客户端"""
        try:
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise ValueError("未找到DEEPSEEK_API_KEY环境变量")

            self.client = OpenAI(
                base_url="https://api.deepseek.com/v1",
                api_key=api_key
            )
            self.logger.info("Deepseek客户端初始化成功")
        except ImportError:
            raise ImportError("请安装openai包: pip install openai>=1.0.0")

    def generate(self, prompt: str, system_prompt: Optional[str] = None,
                 callback: Optional[Callable[[str], None]] = None) -> str:
        """
        生成文本（封装大模型调用，支持重试、流式回调等）

        Args:
            prompt: 用户提示
            system_prompt: 系统提示，覆盖默认配置
            callback: 流式输出的回调函数，仅当streaming=True时有效

        Returns:
            生成的文本

        Raises:
            RuntimeError: 如果生成过程中发生错误
        """
        last_error = None
        system_message = system_prompt or self.config.system_prompt

        for attempt in range(self.config.max_retries):
            try:
                return self._generate_with_openai_interface(prompt, system_message, callback)
            except Exception as e:
                self.logger.warning(f"生成失败(尝试 {attempt + 1}/{self.config.max_retries}): {str(e)}")
                last_error = e

                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay)

        # 所有尝试都失败
        self.logger.error(f"所有重试尝试都失败: {str(last_error)}")
        raise RuntimeError(f"文本生成失败: {str(last_error)}")

    def _generate_with_openai_interface(self, prompt: str, system_prompt: Optional[str] = None,
                                        callback: Optional[Callable[[str], None]] = None) -> str:
        """使用OpenAI兼容接口生成文本"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        if self.config.streaming and callback:
            collected_chunks = []
            for chunk in self.client.chat.completions.create(
                    model=self.config.model.value,
                    messages=messages,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    stream=True,
                    timeout=self.config.timeout
            ):
                content = chunk.choices[0].delta.get("content", "")
                if content:
                    callback(content)
                    collected_chunks.append(content)
            return "".join(collected_chunks)
        else:
            response = self.client.chat.completions.create(
                model=self.config.model.value,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout=self.config.timeout
            )
            return response.choices[0].message.content

    def translate(self, text: str, source_lang: str = "英文", target_lang: str = "中文") -> str:
        """
        翻译文本，针对NBA内容和体育专业术语优化

        Args:
            text: 要翻译的文本
            source_lang: 源语言
            target_lang: 目标语言

        Returns:
            翻译后的文本

        Raises:
            RuntimeError: 如果翻译失败
        """
        if not text or not text.strip() or not self.config.enable_translation:
            return text

        try:
            if len(text) > 4000:
                # 如果文本过大，分块处理
                return self._translate_large_text(text, source_lang, target_lang)

            # 直接在方法里写死 prompt（或从外部文件读取）
            prompt = (
                "你是一名专业的翻译，请准确流畅地进行翻译，"
                "保持原文的意思、风格和语气。对于体育专业术语，特别是NBA相关术语，"
                "请使用对应语言中常用的表达方式。\n\n"
                f"请将以下{text}从{source_lang}翻译成{target_lang}：\n\n"
                f"{text.strip()}\n"
            )
            return self.generate(prompt)
        except Exception as e:
            self.logger.error(f"翻译失败: {str(e)}")
            raise RuntimeError(f"翻译失败: {str(e)}")

    def _translate_large_text(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        分块处理大型文本的翻译
        """
        chunk_size = 3000
        paragraphs = text.split('\n')
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                chunks.append(current_chunk)
                current_chunk = para + '\n'
            else:
                current_chunk += para + '\n'

        if current_chunk:
            chunks.append(current_chunk)

        translated_chunks = []
        for i, chunk in enumerate(chunks):
            self.logger.info(f"正在翻译第 {i + 1}/{len(chunks)} 个块")
            try:
                translated = self.translate(chunk, source_lang, target_lang)
                translated_chunks.append(translated)
                if i < len(chunks) - 1:
                    time.sleep(1)
            except Exception as e:
                self.logger.error(f"翻译第 {i + 1} 个块时出错: {str(e)}")
                translated_chunks.append(chunk)

        return ''.join(translated_chunks)

