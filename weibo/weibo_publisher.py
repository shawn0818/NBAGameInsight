# weibo/weibo_publisher.py

import logging
import os
from pathlib import Path
from typing import List, Dict, Optional
import requests
import random
from dotenv import load_dotenv
from weibo.weibo_model import WeiboPost


class WeiboRequestConfig:
    """微博请求配置类"""
    logger = logging.getLogger(__name__)

    @classmethod
    def parse_cookies_string(cls, cookies_str: str) -> Dict[str, str]:
        """从完整的cookies字符串中提取需要的cookies"""
        if not cookies_str:
            return {}

        try:
            cookies_dict = dict(item.split("=", 1) for item in cookies_str.strip('"').split("; "))
            required_cookies = {'SUB', 'SUBP', '_T_WM', 'WEIBOCN_FROM'}
            result = {k: v for k, v in cookies_dict.items() if k in required_cookies}

            missing_cookies = required_cookies - set(result.keys())
            if missing_cookies:
                cls.logger.error(f"缺少必需的cookies: {', '.join(missing_cookies)}")
                raise ValueError(f"缺少必需的cookies: {', '.join(missing_cookies)}")

            return result

        except Exception as e:
            cls.logger.error(f"解析 cookies 失败: {e}")
            return {}

    @classmethod
    def validate_cookies(cls):
        """验证cookies配置"""
        if not cls.MOBILE_API.WB_COOKIES:
            raise ValueError("WB_COOKIES 未设置")
        required = {'SUB', 'SUBP', '_T_WM', 'WEIBOCN_FROM'}
        missing = required - set(cls.MOBILE_API.WB_COOKIES.keys())
        if missing:
            raise ValueError(f"缺少必需的 cookies: {missing}")

    class MOBILE_API:
        """移动端 API 配置"""
        # Cookies 配置
        WB_COOKIES = {}  # 初始为空，后续设置从环境变量中获取微博 cookies

        # API 端点
        ENDPOINTS = {
            'CONFIG': 'https://m.weibo.cn/api/users/show',
            'UPLOAD': 'https://m.weibo.cn/api/statuses/uploadPic',
            'UPDATE': 'https://m.weibo.cn/api/statuses/update'
        }

        # 基本请求头
        BASE_HEADERS = {
            'authority': 'm.weibo.cn',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'dnt': '1',
            'host': 'm.weibo.cn',
            'origin': 'https://m.weibo.cn',
            'referer': 'https://m.weibo.cn/compose/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'SamsungBrowser/14.2'
                        'Chrome/87.0.4280.141 Mobile Safari/537.36',
            'mweibo-pwa': '1',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'x-requested-with': 'XMLHttpRequest'
        }

        # 发布请求头
        UPDATE_HEADERS = {
            **BASE_HEADERS,
            'method': 'POST',
            'path': '/api/statuses/update',
            'scheme': 'https',
            'content-type': 'application/x-www-form-urlencoded',
        }

        # 上传图片请求头模板
        UPLOAD_HEADERS_TEMPLATE = {
            **BASE_HEADERS,
            'method': 'POST',
            'path': '/api/statuses/uploadPic',
            'scheme': 'https',
            'content-type': 'multipart/form-data; boundary={boundary}'
        }

        # 图片上传参数
        UPLOAD_PARAMS = {
            'type': 'json',
            '_spr': 'screen:1920x1080'
        }

        # 超时和重试
        TIMEOUT = 30
        MAX_RETRIES = 3
        RETRY_DELAY = 5

    class PUBLISH:
        """发布流程配置"""
        # 发布限制
        MAX_TEXT_LENGTH = 2000
        MAX_IMAGES = 16
        ALLOWED_IMAGE_TYPES = ['.jpg', '.jpeg', '.png', '.gif']

        # 重试和间隔策略
        MAX_RETRIES = 3
        RETRY_DELAY = 5  # 发布失败后的重试间隔（秒）
        MIN_PUBLISH_INTERVAL = 10  # 两次成功发布之间的最小间隔（秒）


class WeiboPublisher:
    """微博发布器"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

        # 加载环境变量
        load_dotenv()
        cookies_str = os.getenv('WB_COOKIES')
        #self.logger.info("原始cookies字符串: %s", cookies_str)
        if not cookies_str:
            raise ValueError("未找到 WB_COOKIES 环境变量")

        # 解析 cookies
        cookies = WeiboRequestConfig.parse_cookies_string(cookies_str)
        #self.logger.info("解析后的cookies: %s", cookies)
        if not cookies:
            raise ValueError("无法解析有效的 cookies")

        # 设置并验证配置
        WeiboRequestConfig.MOBILE_API.WB_COOKIES = cookies
        WeiboRequestConfig.validate_cookies()
        self.config = WeiboRequestConfig
        #self.logger.info("最终配置中的cookies: %s", self.config.MOBILE_API.WB_COOKIES)

        self.session = requests.Session()
        self._xsrf_token = None
        self._setup_session()

    def _setup_session(self):
        """配置请求会话"""
        self.session.headers.update(self.config.MOBILE_API.BASE_HEADERS)
        self.logger.info("基础请求头: %s", self.session.headers)
        for cookie_name, cookie_value in self.config.MOBILE_API.WB_COOKIES.items():
            self.session.cookies.set(cookie_name, cookie_value, domain='m.weibo.cn', path='/')
        self.logger.info("会话中的所有cookies:")
        self._xsrf_token = self._get_token()
        if not self._xsrf_token:
            raise Exception("无法获取 XSRF-TOKEN")

    def _get_token(self) -> Optional[str]:
        """获取新的 XSRF-TOKEN"""
        try:
            self.logger.info("正在请求 XSRF-TOKEN...")
            response = self.session.get(
                self.config.MOBILE_API.ENDPOINTS['CONFIG'],
                headers=self.config.MOBILE_API.BASE_HEADERS,
                timeout=self.config.MOBILE_API.TIMEOUT
            )
            response.raise_for_status()

            token = response.cookies.get('XSRF-TOKEN')
            if not token:
                self.logger.error("未能获取到 XSRF-TOKEN")
                return None

            self.logger.info(f"获取到 XSRF-TOKEN: {token}")
            return token

        except Exception as e:
            self.logger.error(f"获取 XSRF-TOKEN 时出错: {e}")
            return None

    def _prepare_headers(self, api_type: str, pic_ids: List[str] = None, xsrf_token: str = None) -> dict:
        """准备请求头"""
        if api_type == 'upload':
            headers = self.config.MOBILE_API.UPLOAD_HEADERS_TEMPLATE.copy()
            boundary = "----WebKitFormBoundaryavNDqfpHAAO9KW4Y"
            headers['content-type'] = headers['content-type'].format(boundary=boundary)
        else:  # update
            headers = self.config.MOBILE_API.UPDATE_HEADERS.copy()
            if pic_ids:
                headers['referer'] = f'https://m.weibo.cn/compose/?pids={",".join(pic_ids)}'

        if xsrf_token:
            headers['x-xsrf-token'] = xsrf_token
        return headers

    def _upload_image_mobile(self, image_path: str, xsrf_token: str) -> Optional[str]:
        """通过移动端API上传图片"""
        try:
            boundary = f"----WebKitFormBoundary{''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=24))}"
            headers = self._prepare_headers('upload', xsrf_token=xsrf_token)
            headers['content-type'] = f'multipart/form-data; boundary={boundary}'

            url = self.config.MOBILE_API.ENDPOINTS['UPLOAD']
            self.logger.info(f"上传图片使用的 XSRF-TOKEN: {xsrf_token}")

            data = []
            data.append(f'--{boundary}')
            data.append('Content-Disposition: form-data; name="type"')
            data.append('')
            data.append('json')

            data.append(f'--{boundary}')
            filename = Path(image_path).name
            data.append(f'Content-Disposition: form-data; name="pic"; filename="{filename}"')
            data.append('Content-Type: image/jpeg')
            data.append('')
            with open(image_path, 'rb') as f:
                file_content = f.read()
            data.append(file_content)

            data.append(f'--{boundary}')
            data.append('Content-Disposition: form-data; name="st"')
            data.append('')
            data.append(xsrf_token)

            data.append(f'--{boundary}')
            data.append('Content-Disposition: form-data; name="_spr"')
            data.append('')
            data.append('screen:1280x720')

            data.append(f'--{boundary}--')

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
        """发布微博"""
        try:
            self.logger.info("开始发布微博工作流")
            self._xsrf_token = self._get_token()  # 每次发布前获取新token
            self.logger.info(f"即将发送请求的 XSRF-TOKEN: {self._xsrf_token}")


            if not self._xsrf_token:
                self.logger.error("无法获取 XSRF-TOKEN")
                return False

            pic_ids = []
            if post.images:
                self.logger.info(f"开始处理 {len(post.images)} 张图片")
                for image_path in post.images:
                    self.logger.info(f"处理图片: {image_path}")
                    path = Path(image_path)
                    self.logger.info(f"图片类型: {path.suffix}")
                    if not path.exists():
                        self.logger.error(f"图片不存在: {image_path}")
                        return False
                    if pic_id := self._upload_image_mobile(image_path, self._xsrf_token):
                        self.logger.info(f"上传成功,pic_id:{pic_id}")
                        pic_ids.append(pic_id)
                    else:
                        self.logger.error(f"图片上传失败: {image_path}")
                        return False

            url = self.config.MOBILE_API.ENDPOINTS['UPDATE']
            headers = self._prepare_headers('update', pic_ids, self._xsrf_token)
            self.logger.info(f"请求头包含的 XSRF-TOKEN: {headers.get('x-xsrf-token')}")

            content = post.text if post.text else "分享图片"
            data = {
                'content': content,
                'st': self._xsrf_token,
                '_spr': 'screen:1280x720'
            }

            if pic_ids:
                data['picId'] = ','.join(pic_ids)
                self.logger.info(f"添加图片ID到请求: {data['picId']}")

            response = self.session.post(
                url,
                headers=headers,
                data=data,
                timeout=self.config.MOBILE_API.TIMEOUT
            )
            response.raise_for_status()
            result = response.json()
            self.logger.info(f"发布响应: {result}")

            if result.get('ok') == 1:
                self.logger.info(f"发布成功,内容:'{content}',图片数量:{len(pic_ids)}")
                return True

            self.logger.error(f"发布失败: {result}")
            return False

        except Exception as e:
            self.logger.error(f"发布过程出错: {e}", exc_info=True)
            return False