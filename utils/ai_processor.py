from enum import Enum
from typing import Dict, Any, Optional, Protocol
from dataclasses import dataclass
import os
from abc import ABC, abstractmethod
import time

from openai import OpenAI
from google import genai
from utils.logger_handler import AppLogger


class AIProvider(Enum):
    """AI 服务提供商枚举"""
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"


class AICapability(Protocol):
    """AI 核心能力接口"""

    def translate(self, text: str) -> str:
        """翻译能力: 英译中"""
        ...

    def create_game_analysis(self, game_data: Dict[str, Any]) -> str:
        """创作能力: 专业比赛分析"""
        ...

    def create_social_content(self, game_data: Dict[str, Any]) -> str:
        """创作能力: 社交媒体风格"""
        ...


@dataclass
class AIConfig:
    """AI 服务配置"""
    provider: AIProvider
    enable_translation: bool = False  # 是否启用翻译
    enable_creation: bool = False  # 是否启用创作


class PromptTemplate:
    """Prompt 模板"""

    def __init__(self, template: str, roles: Optional[Dict[str, str]] = None):
        self.template = template
        self.roles = roles or {}

    def format(self, role: Optional[str] = None, **kwargs) -> str:
        """格式化 prompt 模板"""
        if role and role in self.roles:
            kwargs['role_setting'] = self.roles[role]
        return self.template.format(**kwargs)


class PromptManager:
    """Prompt 管理器"""

    def __init__(self):
        self._templates: Dict[str, PromptTemplate] = {}
        self._init_templates()

    def _init_templates(self):
        """初始化内置的 prompt 模板"""
        # 翻译模板
        self._templates["translation"] = PromptTemplate(
            template="{role_setting}\n\n请将以下英文翻译成中文:\n\n{text}",
            roles={
                "translator": "你是专业的 NBA 翻译，精通中英文篮球术语，请将文本翻译成地道的中文，保持专业性。",
            }
        )

        # 专业分析模板
        self._templates["professional_analysis"] = PromptTemplate(
            template="{role_setting}\n\n请分析以下比赛数据:\n\n{game_data}",
            roles={
                "analyst": """你是专业的 NBA 比赛分析师，请从以下方面分析比赛：
                1. 比赛整体走势和转折点
                2. 关键球员表现分析
                3. 双方战术特点对比
                4. 胜负关键因素分析
                5. 数据深度解读
                请用专业的视角进行深入分析。"""
            }
        )

        # 社交媒体模板
        self._templates["social_content"] = PromptTemplate(
            template="{role_setting}\n\n请基于以下比赛信息创作社交媒体内容:\n\n{game_data}",
            roles={
                "social_media": """你是 NBA 社交媒体运营专家，请创作吸引球迷的内容：
                1. 使用生动简洁的语言
                2. 突出比赛精彩瞬间
                3. 增加适当的 emoji 表情
                4. 适当使用网络用语
                5. 添加 #话题标签#
                6. 控制在 140 字以内
                要让内容既专业又有趣。"""
            }
        )

    def get_prompt(self, template_name: str) -> PromptTemplate:
        """获取指定的 prompt 模板"""
        if template_name not in self._templates:
            raise ValueError(f"未找到模板: {template_name}")
        return self._templates[template_name]

    def add_template(self, name: str, template: PromptTemplate):
        """添加新的 prompt 模板"""
        self._templates[name] = template


class AIClient(ABC):
    """AI 客户端基类

    定义了所有 AI 服务提供商需要实现的基本接口和共享功能
    """

    def __init__(self):
        self.logger = AppLogger.get_logger(__name__)

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """生成内容的抽象方法，子类必须实现"""
        pass

    def generate_with_retry(self, prompt: str, max_retries: int = 3, retry_delay: float = 1.0) -> str:
        """带重试机制的生成方法

        统一的重试逻辑，所有子类都可以复用
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                return self.generate(prompt)
            except Exception as e:
                last_error = e
                self.logger.warning(
                    f"生成失败(尝试 {attempt + 1}/{max_retries}): {str(e)}"
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        self.logger.error(f"所有重试都失败: {str(last_error)}")
        raise last_error

    def validate_response(self, response: str) -> bool:
        """验证响应是否有效

        子类可以继承并扩展这个方法来实现特定的验证逻辑
        """
        return bool(response and response.strip())


class DeepseekClient(AIClient):
    """Deepseek 客户端"""

    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("未找到 DEEPSEEK_API_KEY")
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com/v1"
        )

    def generate(self, prompt: str) -> str:
        """实现 Deepseek 的具体生成逻辑"""
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content


class GeminiClient(AIClient):
    """Gemini 客户端"""

    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("未找到 GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key)

    def generate(self, prompt: str) -> str:
        """实现 Gemini 的具体生成逻辑"""
        response = self.client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        return response.text


class AIProcessor(AICapability):
    """AI 处理器"""

    def __init__(self, config: AIConfig, prompt_manager: Optional[PromptManager] = None):
        """初始化 AI 处理器

        Args:
            config: AI 配置
            prompt_manager: Prompt管理器，如果不提供则创建默认的
        """
        self.config = config
        self.prompt_manager = prompt_manager or PromptManager()
        self.logger = AppLogger.get_logger(__name__)
        self._init_client()

    def _init_client(self):
        """初始化 AI 客户端"""
        if self.config.provider == AIProvider.DEEPSEEK:
            self.client = DeepseekClient()
        elif self.config.provider == AIProvider.GEMINI:
            self.client = GeminiClient()
        else:
            raise ValueError(f"不支持的 AI 提供商: {self.config.provider}")

    def translate(self, text: str) -> str:
        """将英文翻译成中文

        Args:
            text: 待翻译的英文文本

        Returns:
            str: 翻译后的中文文本，如果翻译失败则返回原文
        """
        if not text or not self.config.enable_translation:
            return text

        try:
            prompt_template = self.prompt_manager.get_prompt("translation")
            prompt = prompt_template.format(
                role="translator",
                text=text
            )

            return self.client.generate_with_retry(prompt)
        except Exception as e:
            self.logger.error(f"翻译失败: {str(e)}")
            return text

    def create_game_analysis(self, game_data: Dict[str, Any]) -> str:
        """创建专业比赛分析

        Args:
            game_data: 比赛相关数据

        Returns:
            str: 生成的专业分析内容
        """
        if not game_data or not self.config.enable_creation:
            return ""

        try:
            prompt_template = self.prompt_manager.get_prompt("professional_analysis")
            prompt = prompt_template.format(
                role="analyst",
                game_data=str(game_data)
            )

            return self.client.generate_with_retry(prompt)
        except Exception as e:
            self.logger.error(f"创建专业分析失败: {str(e)}")
            return ""

    def create_social_content(self, game_data: Dict[str, Any]) -> str:
        """创建社交媒体内容

        Args:
            game_data: 比赛相关数据

        Returns:
            str: 生成的社交媒体内容
        """
        if not game_data or not self.config.enable_creation:
            return ""

        try:
            prompt_template = self.prompt_manager.get_prompt("social_content")
            prompt = prompt_template.format(
                role="social_media",
                game_data=str(game_data)
            )

            return self.client.generate_with_retry(prompt)
        except Exception as e:
            self.logger.error(f"创建社交媒体内容失败: {str(e)}")
            return ""