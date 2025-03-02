"""
优化后的AI处理器模块
提供与大型语言模型交互的通用接口和服务，
"""

from enum import Enum
from typing import Dict,  Optional, List,  Callable
from dataclasses import dataclass
import os
import time
import logging


class AIProvider(Enum):
    """AI 服务提供商枚举"""
    OPENROUTER = "openrouter"
    DEEPSEEK = "deepseek"


class AIModel(Enum):
    """AI 模型枚举"""
    # OpenRouter 模型
    GPT4 = "openai/gpt-4"
    CLAUDE = "anthropic/claude-3-opus"
    GEMINI = "google/gemini-pro"
    GEMINI_FLASH = "google/gemini-2.0-flash-001"
    # Deepseek 模型
    DEEPSEEK_CHAT = "deepseek-chat"


@dataclass
class AIConfig:
    """AI 服务配置"""
    provider: AIProvider = AIProvider.OPENROUTER
    model: AIModel = AIModel.GEMINI_FLASH
    enable_translation: bool = True
    enable_creation: bool = True
    # 请求相关配置
    max_retries: int = 3
    retry_delay: int = 3  # 秒
    timeout: int = 60  # 秒
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    # 高级配置
    system_prompt: Optional[str] = None
    streaming: bool = False


class PromptTemplate:
    """提示模板类，用于格式化提示词"""

    def __init__(self, template: str, roles: Optional[Dict[str, str]] = None):
        """
        初始化提示模板

        Args:
            template: 带有占位符的模板字符串
            roles: 角色设定字典，键为角色名，值为角色设定文本
        """
        self.template = template
        self.roles = roles or {}

    def format(self, role: Optional[str] = None, **kwargs) -> str:
        """
        格式化提示模板

        Args:
            role: 角色名称，如果提供且存在于roles字典中，将添加角色设定
            **kwargs: 其他需要替换的变量

        Returns:
            格式化后的提示字符串
        """
        if role and role in self.roles:
            kwargs['role_setting'] = self.roles[role]
        elif 'role_setting' not in kwargs:
            kwargs['role_setting'] = ""

        return self.template.format(**kwargs)


class PromptManager:
    """提示管理器，管理多个提示模板"""

    def __init__(self):
        """初始化提示管理器"""
        self._templates: Dict[str, PromptTemplate] = {}
        self._init_default_templates()
        self._init_nba_templates()  # 添加NBA特定的模板

    def _init_default_templates(self):
        """初始化默认提示模板"""
        # 通用翻译模板
        self._templates["translation"] = PromptTemplate(
            template="{role_setting}\n\n请将以下{source_lang}翻译成{target_lang}，保持原文的格式和风格:\n\n{text}",
            roles={
                "translator": "你是专业的翻译，请准确流畅地进行翻译，保持原文的意思、风格和语气。注意保留原文的格式结构和专业术语。对于体育专业术语，特别是NBA相关术语，请使用对应语言中常用的表达方式。"
            }
        )

        # 通用摘要模板
        self._templates["summarize"] = PromptTemplate(
            template="{role_setting}\n\n请对以下文本进行摘要，{format_requirements}:\n\n{text}",
            roles={
                "summarizer": "你是专业的内容摘要专家，擅长提取文本的关键信息，并用简洁清晰的语言呈现。"
            }
        )

        # 通用分析模板
        self._templates["analyze"] = PromptTemplate(
            template="{role_setting}\n\n请分析以下内容:\n\n{content}",
            roles={
                "analyst": "你是专业的数据分析师，擅长从数据中发现关键洞见和模式，并提供清晰的分析结论。"
            }
        )

        # 内容创作模板
        self._templates["create"] = PromptTemplate(
            template="{role_setting}\n\n根据以下要求创作内容:\n\n{requirements}",
            roles={
                "content_creator": "你是专业的内容创作者，擅长创作高质量、引人入胜的内容。"
            }
        )

    def _init_nba_templates(self):
        """初始化NBA相关的专用模板"""
        # 比赛标题生成模板
        self._templates["game_title"] = PromptTemplate(
            template="{role_setting}\n\n请为以下NBA比赛生成一个简洁有力的标题，要求：\n1. 包含两队名称\n2. 包含比分或比赛结果\n3. 如果有突出表现的球员，可以简要提及\n4. 标题不超过20个字\n\n比赛信息：{game_info}",
            roles={
                "sports_writer": "你是一名专业的体育记者，擅长为NBA比赛创作简洁有力的标题。"
            }
        )

        # 比赛简介生成模板
        self._templates["game_summary"] = PromptTemplate(
            template="{role_setting}\n\n请为以下NBA比赛生成一段简洁的比赛总结，要求：\n1. 描述比赛结果和关键数据\n2. 提及关键球员表现\n3. 突出比赛转折点\n4. 控制在100-150字之间\n5. 语言生动，适合社交媒体发布\n\n比赛信息：{game_info}",
            roles={
                "sports_writer": "你是一名专业的体育记者，擅长为NBA比赛创作生动简洁的比赛总结。"
            }
        )

        # 球员表现分析模板
        self._templates["player_analysis"] = PromptTemplate(
            template="{role_setting}\n\n请分析以下NBA球员在本场比赛中的表现，要求：\n1. 突出关键数据统计\n2. 分析其对比赛的影响\n3. 评价表现亮点和不足\n4. 控制在100-200字之间\n5. 适合社交媒体发布\n\n球员信息：{player_info}",
            roles={
                "sports_analyst": "你是一名NBA球员分析师，擅长通过数据和比赛表现分析球员影响力。"
            }
        )

        # 微博内容生成模板
        self._templates["weibo_post"] = PromptTemplate(
            template="{role_setting}\n\n请根据以下NBA比赛信息，为微博平台创建一条引人入胜的帖子，要求：\n1. 突出比赛结果和亮点\n2. 语言生动简练\n3. 加入2-3个相关话题标签(#标签#格式)\n4. 内容长度适合微博平台(不超过140字)\n5. 适当使用表情符号增加吸引力\n\n发布类型：{post_type}\n比赛信息：{content_data}",
            roles={
                "social_media_editor": "你是一名体育社交媒体编辑，擅长创作能引起用户互动的NBA内容。"
            }
        )

    def get_prompt(self, template_name: str, role: str = "", **kwargs) -> str:
        """
        获取格式化的提示

        Args:
            template_name: 模板名称
            role: 角色名称
            **kwargs: 要替换的变量

        Returns:
            格式化后的提示字符串

        Raises:
            ValueError: 如果模板名称不存在
        """
        if template_name not in self._templates:
            raise ValueError(f"未找到模板: {template_name}")

        template = self._templates[template_name]
        return template.format(role=role, **kwargs)

    def add_template(self, name: str, template: PromptTemplate):
        """
        添加新模板

        Args:
            name: 模板名称
            template: 提示模板实例
        """
        self._templates[name] = template

    def get_all_template_names(self) -> List[str]:
        """
        获取所有模板名称

        Returns:
            模板名称列表
        """
        return list(self._templates.keys())


class AIProcessor:
    """AI处理器
    提供与AI模型交互的通用接口，专注于NBA数据处理和生成微博内容。
    """

    def __init__(self, config: Optional[AIConfig] = None, prompt_manager: Optional[PromptManager] = None,
                 logger: Optional[logging.Logger] = None):
        """
        初始化AI处理器

        Args:
            config: AI配置，如果不提供则使用默认配置
            prompt_manager: 提示管理器，如果不提供则创建默认的
            logger: 日志记录器，如果不提供则创建默认的
        """
        self.config = config or AIConfig()
        self.prompt_manager = prompt_manager or PromptManager()
        self.logger = logger or self._setup_default_logger()
        self.client = None
        self._init_client()

    def _setup_default_logger(self) -> logging.Logger:
        """
        设置默认日志记录器

        Returns:
            配置好的日志记录器
        """
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

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
            from openai import OpenAI

            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError("未找到OPENROUTER_API_KEY环境变量")

            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
                default_headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "localhost"),
                    "X-Title": os.getenv("OPENROUTER_TITLE", "AI Processor")
                }
            )
            self.logger.info("OpenRouter客户端初始化成功")
        except ImportError:
            raise ImportError("请安装openai包: pip install openai>=1.0.0")

    def _init_deepseek_client(self):
        """初始化Deepseek客户端"""
        try:
            from openai import OpenAI

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
        生成文本

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
                content = chunk.choices[0].delta.content
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
            # 检查文本大小，如果过大则分块处理
            if len(text) > 4000:
                return self._translate_large_text(text, source_lang, target_lang)

            prompt = self.prompt_manager.get_prompt(
                "translation",
                role="translator",
                source_lang=source_lang,
                target_lang=target_lang,
                text=text.strip()
            )
            return self.generate(prompt)
        except Exception as e:
            self.logger.error(f"翻译失败: {str(e)}")
            raise RuntimeError(f"翻译失败: {str(e)}")

    def _translate_large_text(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        分块处理大型文本的翻译

        Args:
            text: 要翻译的大型文本
            source_lang: 源语言
            target_lang: 目标语言

        Returns:
            翻译后的完整文本
        """
        # 设置合理的块大小
        chunk_size = 3000
        chunks = []

        # 按段落分割文本（保持段落完整性）
        paragraphs = text.split('\n')
        current_chunk = ""

        for para in paragraphs:
            # 如果加上这个段落会超过块大小，先处理当前块
            if len(current_chunk) + len(para) > chunk_size and current_chunk:
                chunks.append(current_chunk)
                current_chunk = para + '\n'
            else:
                current_chunk += para + '\n'

        # 添加最后一个块
        if current_chunk:
            chunks.append(current_chunk)

        # 翻译每个块
        translated_chunks = []
        for i, chunk in enumerate(chunks):
            self.logger.info(f"正在翻译第 {i + 1}/{len(chunks)} 个块")
            try:
                translated = self.translate(chunk, source_lang, target_lang)
                translated_chunks.append(translated)
                # 避免频繁请求，添加短暂延迟
                if i < len(chunks) - 1:
                    time.sleep(1)
            except Exception as e:
                self.logger.error(f"翻译第 {i + 1} 个块时出错: {str(e)}")
                # 出错时使用原文
                translated_chunks.append(chunk)

        # 合并翻译结果
        return ''.join(translated_chunks)

    def summarize(self, text: str, max_length: Optional[int] = None, format_type: str = "文本") -> str:
        """
        摘要文本

        Args:
            text: 要摘要的文本
            max_length: 最大摘要长度
            format_type: 摘要格式类型，如"文本"、"要点"等

        Returns:
            摘要文本

        Raises:
            RuntimeError: 如果摘要失败
        """
        if not text or not text.strip():
            return ""

        try:
            format_requirements = f"生成{format_type}格式的摘要"
            if max_length:
                format_requirements += f"，长度不超过{max_length}字"

            prompt = self.prompt_manager.get_prompt(
                "summarize",
                role="summarizer",
                format_requirements=format_requirements,
                text=text.strip()
            )
            return self.generate(prompt)
        except Exception as e:
            self.logger.error(f"生成摘要失败: {str(e)}")
            raise RuntimeError(f"生成摘要失败: {str(e)}")
