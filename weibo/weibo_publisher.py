# weibo_publisher.py

import logging
import time
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
import requests
import random
from config.weibo_config import WeiboConfig


@dataclass
class WeiboPost:
    """微博帖子数据类"""
    text: str
    images: Optional[List[str]] = None

    def __post_init__(self):
        """验证图片路径和文本长度"""
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


class WeiboPublisher:
    """微博发布器"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = WeiboConfig
        self.session = requests.Session()
        self._setup_session()
        self.xsrf_token = self._get_token()

    def _setup_session(self):
        """配置请求会话"""
        self.session.headers.update(self.config.MOBILE_API.BASE_HEADERS)
        for cookie_name, cookie_value in self.config.MOBILE_API.WB_COOKIES.items():
            self.session.cookies.set(cookie_name, cookie_value, domain='m.weibo.cn', path='/')

    def _get_token(self) -> Optional[str]:
        """获取新的 XSRF-TOKEN"""
        try:
            response = self.session.get(
                self.config.MOBILE_API.ENDPOINTS['CONFIG'],
                headers=self.config.MOBILE_API.BASE_HEADERS,
                timeout=self.config.MOBILE_API.TIMEOUT
            )
            response.raise_for_status()

            # 从响应中获取 token
            token = response.cookies.get('XSRF-TOKEN')
            if not token:
                self.logger.error("未能获取到 XSRF-TOKEN")
                return None

            self.logger.info(f"获取到 XSRF-TOKEN: {token}")
            return token

        except Exception as e:
            self.logger.error(f"获取 XSRF-TOKEN 时出错: {e}")
            return None

    def _prepare_headers(self, api_type: str, pic_ids: List[str] = None) -> dict:
        """准备请求头"""
        if api_type == 'upload':
            headers = self.config.MOBILE_API.UPLOAD_HEADERS_TEMPLATE.copy()
            boundary = "----WebKitFormBoundaryavNDqfpHAAO9KW4Y"
            headers['content-type'] = headers['content-type'].format(boundary=boundary)
        else:  # update
            headers = self.config.MOBILE_API.UPDATE_HEADERS.copy()
            if pic_ids:
                headers['referer'] = f'https://m.weibo.cn/compose/?pids={",".join(pic_ids)}'

        if self.xsrf_token:
            headers['x-xsrf-token'] = self.xsrf_token
        return headers

    def _upload_image_mobile(self, image_path: str) -> Optional[str]:
        """通过移动端API上传图片"""
        try:
            # 生成随机的 boundary
            boundary = f"----WebKitFormBoundary{''.join([random.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(24)])}"
            headers = self._prepare_headers('upload')
            headers['content-type'] = f'multipart/form-data; boundary={boundary}'

            url = self.config.MOBILE_API.ENDPOINTS['UPLOAD']

            # 构造 multipart form-data
            data = []

            # 添加 type 字段
            data.append(f'--{boundary}')
            data.append('Content-Disposition: form-data; name="type"')
            data.append('')
            data.append('json')

            # 添加 pic 字段
            data.append(f'--{boundary}')
            filename = Path(image_path).name
            data.append(f'Content-Disposition: form-data; name="pic"; filename="{filename}"')
            data.append('Content-Type: image/jpeg')  # 或根据实际文件类型设置
            data.append('')
            with open(image_path, 'rb') as f:
                file_content = f.read()
            data.append(file_content)

            # 添加 st 字段 (XSRF token)
            data.append(f'--{boundary}')
            data.append('Content-Disposition: form-data; name="st"')
            data.append('')
            data.append(self.xsrf_token)

            # 添加 _spr 字段
            data.append(f'--{boundary}')
            data.append('Content-Disposition: form-data; name="_spr"')
            data.append('')
            data.append('screen:1280x720')

            # 结束标记
            data.append(f'--{boundary}--')

            # 将所有内容合并成一个请求体
            body = b'\r\n'.join([
                part.encode() if isinstance(part, str) else part
                for part in data
            ])

            response = self.session.post(
                url,
                headers=headers,
                data=body,
                timeout=self.config.MOBILE_API.TIMEOUT
            )
            response.raise_for_status()
            result = response.json()

            if pic_id := result.get('pic_id'):
                self.logger.info(f"图片上传成功: {image_path}，pic_id: {pic_id}")
                return pic_id

            self.logger.error(f"图片上传失败: {result}")
            return None

        except Exception as e:
            self.logger.error(f"图片上传出错: {e}")
            return None

    def publish(self, post: WeiboPost) -> bool:
        """发布微博，带重试机制"""
        self.logger.info("开始发布微博工作流")

        if not self.xsrf_token:
            self.logger.error("无有效的 XSRF-TOKEN，无法发布")
            return False

        try:
            # 1. 上传图片（如果有）
            pic_ids = []
            if post.images:
                for image_path in post.images:
                    if pic_id := self._upload_image_mobile(image_path):
                        pic_ids.append(pic_id)
                    else:
                        self.logger.error(f"图片上传失败，取消发布: {image_path}")
                        return False

            # 2. 准备发布数据和请求头
            url = self.config.MOBILE_API.ENDPOINTS['UPDATE']
            headers = self._prepare_headers('update', pic_ids)

            content = post.text if post.text else "分享图片"
            data = {
                'content': content,
                'st': self.xsrf_token,
                '_spr': 'screen:1280x720'
            }

            if pic_ids:
                data['picId'] = ','.join(pic_ids)

            self.logger.debug(f"发布微博数据: {data}")

            # 3. 发送发布请求
            for attempt in range(1, self.config.MOBILE_API.MAX_RETRIES + 1):
                try:
                    response = self.session.post(
                        url,
                        headers=headers,
                        data=data,
                        timeout=self.config.MOBILE_API.TIMEOUT
                    )
                    response.raise_for_status()
                    result = response.json()

                    if result.get('ok') == 1:
                        self.logger.info(f"发布成功，内容: '{content}', 图片数量: {len(pic_ids)}")
                        return True

                    self.logger.error(f"发布失败: {result}")
                    if attempt < self.config.MOBILE_API.MAX_RETRIES:
                        self.logger.info(f"等待 {self.config.MOBILE_API.RETRY_DELAY} 秒后重试")
                        time.sleep(self.config.MOBILE_API.RETRY_DELAY)

                except requests.exceptions.RequestException as e:
                    self.logger.error(f"发布请求出错: {e}")
                    if attempt < self.config.MOBILE_API.MAX_RETRIES:
                        self.logger.info(f"等待 {self.config.MOBILE_API.RETRY_DELAY} 秒后重试")
                        time.sleep(self.config.MOBILE_API.RETRY_DELAY)

            self.logger.error("所有发布尝试均失败")
            return False

        except Exception as e:
            self.logger.error(f"发布过程出错: {e}")
            return False