# weibo/weibo_model.py

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime



@dataclass
class WeiboPost:
    """微博发布内容模型"""
    text: str
    images: Optional[List[str]] = None
    created_at: datetime = datetime.now()

    # 将配置常量直接定义在类中
    MAX_TEXT_LENGTH = 2000
    MAX_IMAGES = 16
    ALLOWED_IMAGE_TYPES = ['.jpg', '.jpeg', '.png', '.gif']

    def __post_init__(self):
        """数据验证"""
        if self.images:
            # 验证图片数量
            if len(self.images) > self.MAX_IMAGES:
                raise ValueError(
                    f"图片数量超过限制: {len(self.images)} > {self.MAX_IMAGES}"
                )

            # 验证图片文件
            for path in self.images:
                if not Path(path).exists():
                    raise FileNotFoundError(f"图片不存在: {path}")
                if Path(path).suffix.lower() not in self.ALLOWED_IMAGE_TYPES:
                    raise ValueError(f"不支持的图片类型: {path}")

        # 验证文本长度
        if len(self.text) > self.MAX_TEXT_LENGTH:
            raise ValueError(
                f"文本长度超过限制: {len(self.text)} > {self.MAX_TEXT_LENGTH}"
            )


@dataclass
class WeiboResponse:
    """微博API响应模型"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None