# weibo/weibo_model.py

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime
from config.weibo_config import WeiboConfig

@dataclass
class WeiboPost:
    text: str
    images: Optional[List[str]] = None
    created_at: datetime = datetime.now()

    def __post_init__(self):
        if self.images:
            if len(self.images) > WeiboConfig.PUBLISH.MAX_IMAGES:
                raise ValueError(f"图片数量超过限制: {len(self.images)} > {WeiboConfig.PUBLISH.MAX_IMAGES}")
            for path in self.images:
                if not Path(path).exists():
                    raise FileNotFoundError(f"图片不存在: {path}")
                if Path(path).suffix.lower() not in WeiboConfig.PUBLISH.ALLOWED_IMAGE_TYPES:
                    raise ValueError(f"不支持的图片类型: {path}")

        if len(self.text) > WeiboConfig.PUBLISH.MAX_TEXT_LENGTH:
            raise ValueError(f"文本长度超过限制: {len(self.text)} > {WeiboConfig.PUBLISH.MAX_TEXT_LENGTH}")

@dataclass
class WeiboResponse:
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None