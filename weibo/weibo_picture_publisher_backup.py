import logging
import random
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
import requests
from utils.logger_handler import AppLogger


@dataclass
class WeiboMobileResponse:
    """移动端微博API响应模型"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class WeiboMobileImagePublisher:
    """
    微博移动端图片发布工具类

    通过模拟移动端API发布图片微博，作为Web端API的补充方案
    """

    # 移动端API端点
    ENDPOINTS = {
        'CONFIG': 'https://m.weibo.cn/api/users/show',
        'UPLOAD': 'https://m.weibo.cn/api/statuses/uploadPic',
        'UPDATE': 'https://m.weibo.cn/api/statuses/update'
    }

    # 允许的图片类型
    ALLOWED_IMAGE_TYPES = ['.jpg', '.jpeg', '.png', '.gif']

    # 发布限制
    MAX_TEXT_LENGTH = 2000
    MAX_IMAGES = 9  # 移动端最多9张图

    # 超时和重试配置
    TIMEOUT = 30
    MAX_RETRIES = 3
    RETRY_DELAY = 5

    def __init__(self, cookie: str):
        """
        初始化移动端微博图片发布工具

        Args:
            cookie: 包含移动端所需cookies的完整cookie字符串
        """
        self.logger = AppLogger.get_logger(
            name=__name__,
            level=logging.INFO,
            app_name="weibo-mobile"
        )

        self.cookie = cookie
        self.cookies_dict = self._parse_cookies(cookie)
        self._validate_cookies()

        self.session = requests.Session()
        self._xsrf_token = None
        self._setup_session()

    def _parse_cookies(self, cookie_str: str) -> Dict[str, str]:
        """
        从完整的cookies字符串中提取需要的cookies,与web获取的cookie值是不一样的

        Args:
            cookie_str: 完整的cookie字符串

        Returns:
            Dict: 解析后的cookies字典
        """
        if not cookie_str:
            return {}

        try:
            cookies_dict = {}
            for item in cookie_str.split('; '):
                if '=' in item:
                    name, value = item.split('=', 1)
                    cookies_dict[name] = value

            # 移动端需要的cookies
            required_cookies = {'SUB', 'SUBP', '_T_WM', 'WEIBOCN_FROM'}
            result = {k: v for k, v in cookies_dict.items() if k in required_cookies}

            missing_cookies = required_cookies - set(result.keys())
            if missing_cookies:
                self.logger.warning(f"缺少部分移动端cookies: {', '.join(missing_cookies)}")

            return result

        except Exception as e:
            self.logger.error(f"解析cookies失败: {str(e)}", exc_info=True)
            return {}

    def _validate_cookies(self):
        """验证cookies配置是否有效"""
        if not self.cookies_dict:
            raise ValueError("未能解析有效的cookies")

        # 必须包含的cookies
        required = {'SUB'}
        missing = required - set(self.cookies_dict.keys())
        if missing:
            raise ValueError(f"缺少必需的cookies: {missing}")

    def _setup_session(self):
        """配置请求会话和基础请求头"""
        headers = {
            'authority': 'm.weibo.cn',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'dnt': '1',
            'host': 'm.weibo.cn',
            'origin': 'https://m.weibo.cn',
            'referer': 'https://m.weibo.cn/compose/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'SamsungBrowser/14.2 '
                          'Chrome/87.0.4280.141 Mobile Safari/537.36',
            'mweibo-pwa': '1',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'x-requested-with': 'XMLHttpRequest'
        }

        self.session.headers.update(headers)

        # 设置cookies
        for cookie_name, cookie_value in self.cookies_dict.items():
            self.session.cookies.set(cookie_name, cookie_value, domain='m.weibo.cn', path='/')

        # 获取XSRF-TOKEN
        self._xsrf_token = self._get_xsrf_token()
        if not self._xsrf_token:
            self.logger.warning("初始化时未能获取XSRF-TOKEN，将在发布时重试")

    def _get_xsrf_token(self) -> Optional[str]:
        """
        获取新的XSRF-TOKEN

        Returns:
            str: XSRF-TOKEN值，失败返回None
        """
        try:
            self.logger.debug("正在请求XSRF-TOKEN...")
            response = self.session.get(
                self.ENDPOINTS['CONFIG'],
                timeout=self.TIMEOUT
            )
            response.raise_for_status()

            # 从cookies中提取token
            token = response.cookies.get('XSRF-TOKEN')
            if token:
                self.logger.debug(f"获取到XSRF-TOKEN: {token}")
                return token

            self.logger.warning("未能从cookies中获取XSRF-TOKEN")

            # 尝试从响应中提取
            try:
                result = response.json()
                if 'st' in result.get('data', {}):
                    token = result['data']['st']
                    self.logger.debug(f"从响应数据中获取到st作为token: {token}")
                    return token
            except:
                pass

            self.logger.error("无法获取XSRF-TOKEN")
            return None

        except Exception as e:
            self.logger.error(f"获取XSRF-TOKEN失败: {str(e)}", exc_info=True)
            return None

    def _prepare_upload_headers(self, boundary: str, xsrf_token: str) -> Dict[str, str]:
        """
        准备上传图片的请求头

        Args:
            boundary: 表单边界字符串
            xsrf_token: XSRF令牌

        Returns:
            Dict: 请求头字典
        """
        headers = {
            **self.session.headers,
            'method': 'POST',
            'path': '/api/statuses/uploadPic',
            'scheme': 'https',
            'content-type': f'multipart/form-data; boundary={boundary}',
            'x-xsrf-token': xsrf_token
        }
        return headers

    def _prepare_publish_headers(self, pic_ids: List[str], xsrf_token: str) -> Dict[str, str]:
        """
        准备发布微博的请求头

        Args:
            pic_ids: 已上传图片的ID列表
            xsrf_token: XSRF令牌

        Returns:
            Dict: 请求头字典
        """
        headers = {
            **self.session.headers,
            'method': 'POST',
            'path': '/api/statuses/update',
            'scheme': 'https',
            'content-type': 'application/x-www-form-urlencoded',
            'x-xsrf-token': xsrf_token
        }

        # 如果有图片，更新referer
        if pic_ids:
            headers['referer'] = f'https://m.weibo.cn/compose/?pids={",".join(pic_ids)}'

        return headers

    def _generate_boundary(self) -> str:
        """生成随机的表单边界字符串"""
        chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        random_str = ''.join(random.choices(chars, k=24))
        return f"----WebKitFormBoundary{random_str}"

    def _upload_image(self, image_path: str, xsrf_token: str) -> Optional[str]:
        """
        上传单张图片

        Args:
            image_path: 图片文件路径
            xsrf_token: XSRF令牌

        Returns:
            str: 上传成功返回pic_id，失败返回None
        """
        try:
            # 验证文件存在
            path = Path(image_path)
            if not path.exists():
                self.logger.error(f"图片文件不存在: {image_path}")
                return None

            # 验证文件类型
            if path.suffix.lower() not in self.ALLOWED_IMAGE_TYPES:
                self.logger.error(f"不支持的图片类型: {path.suffix}")
                return None

            # 生成边界字符串
            boundary = self._generate_boundary()

            # 准备请求头
            headers = self._prepare_upload_headers(boundary, xsrf_token)

            # 构建multipart表单数据
            data = []
            data.append(f'--{boundary}')
            data.append('Content-Disposition: form-data; name="type"')
            data.append('')
            data.append('json')

            data.append(f'--{boundary}')
            filename = path.name
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

            # 转换为二进制数据
            body = b'\r\n'.join([
                part.encode() if isinstance(part, str) else part
                for part in data
            ])

            # 发送请求
            response = self.session.post(
                self.ENDPOINTS['UPLOAD'],
                headers=headers,
                data=body,
                timeout=self.TIMEOUT
            )
            response.raise_for_status()

            # 解析响应
            result = response.json()
            if not result:
                self.logger.error("上传图片响应为空")
                return None

            # 提取pic_id
            pic_id = result.get('pic_id')
            if pic_id:
                self.logger.info(f"图片上传成功: {image_path}, pic_id: {pic_id}")
                return pic_id

            self.logger.error(f"上传图片失败，未返回pic_id: {result}")
            return None

        except Exception as e:
            self.logger.error(f"上传图片过程中发生错误: {str(e)}", exc_info=True)
            return None

    def upload_images(self, image_paths: Union[str, List[str]]) -> List[str]:
        """
        上传一张或多张图片

        Args:
            image_paths: 单个图片路径或图片路径列表

        Returns:
            List[str]: 上传成功的图片ID列表
        """
        # 确保获取最新的token
        self._xsrf_token = self._get_xsrf_token()
        if not self._xsrf_token:
            self.logger.error("无法获取XSRF-TOKEN，上传图片失败")
            return []

        # 转换为列表
        if isinstance(image_paths, str):
            image_paths = [image_paths]

        # 验证图片数量
        if len(image_paths) > self.MAX_IMAGES:
            self.logger.warning(f"图片数量超过限制({self.MAX_IMAGES})，将只处理前{self.MAX_IMAGES}张")
            image_paths = image_paths[:self.MAX_IMAGES]

        # 上传图片
        pic_ids = []
        for path in image_paths:
            # 重试上传
            for attempt in range(self.MAX_RETRIES):
                pic_id = self._upload_image(path, self._xsrf_token)
                if pic_id:
                    pic_ids.append(pic_id)
                    break

                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAY * (attempt + 1)
                    self.logger.warning(f"上传图片失败，{delay}秒后重试({attempt + 1}/{self.MAX_RETRIES})...")
                    time.sleep(delay)

            # 添加随机延迟，避免频率限制
            if len(image_paths) > 1:
                time.sleep(random.uniform(1, 3))

        return pic_ids

    def publish_post(self, content: str, pic_ids: List[str]) -> WeiboMobileResponse:
        """
        发布包含图片的微博

        Args:
            content: 微博文本内容
            pic_ids: 已上传的图片ID列表

        Returns:
            WeiboMobileResponse: 发布结果响应对象
        """
        try:
            # 确保有有效的token
            if not self._xsrf_token:
                self._xsrf_token = self._get_xsrf_token()
                if not self._xsrf_token:
                    return WeiboMobileResponse(False, "无法获取XSRF-TOKEN，发布失败")

            # 准备请求头
            headers = self._prepare_publish_headers(pic_ids, self._xsrf_token)

            # 准备请求数据
            data = {
                'content': content,
                'st': self._xsrf_token,
                '_spr': 'screen:1280x720'
            }

            # 添加图片ID
            if pic_ids:
                data['picId'] = ','.join(pic_ids)

            # 发送请求
            response = self.session.post(
                self.ENDPOINTS['UPDATE'],
                headers=headers,
                data=data,
                timeout=self.TIMEOUT
            )
            response.raise_for_status()

            # 解析响应
            result = response.json()

            # 判断发布结果
            if result.get('ok') == 1:
                self.logger.info(f"微博发布成功: 文本'{content[:30]}...'，{len(pic_ids)}张图片")
                return WeiboMobileResponse(True, "发布成功", result)

            # 发布失败
            error_msg = result.get('msg', '未知错误')
            self.logger.error(f"微博发布失败: {error_msg}")
            return WeiboMobileResponse(False, error_msg, result)

        except Exception as e:
            error_message = f"发布微博过程中发生错误: {str(e)}"
            self.logger.error(error_message, exc_info=True)
            return WeiboMobileResponse(False, error_message)

    def publish_images(self, image_paths: Union[str, List[str]], content: str = "") -> Dict[str, Any]:
        """
        一站式上传图片并发布微博

        Args:
            image_paths: 单个图片路径或图片路径列表
            content: 微博文本内容

        Returns:
            Dict: 包含成功状态和消息的字典
        """
        # 验证内容长度
        if len(content) > self.MAX_TEXT_LENGTH:
            return {"success": False, "message": f"文本长度超过限制({self.MAX_TEXT_LENGTH})"}

        # 上传图片
        pic_ids = self.upload_images(image_paths)
        if not pic_ids:
            return {"success": False, "message": "所有图片上传失败"}

        # 发布微博
        for attempt in range(self.MAX_RETRIES):
            response = self.publish_post(content, pic_ids)
            if response.success:
                return {"success": True, "message": response.message, "data": response.data}

            if attempt < self.MAX_RETRIES - 1:
                delay = self.RETRY_DELAY * (attempt + 1)
                self.logger.warning(f"发布微博失败: {response.message}，{delay}秒后重试...")
                time.sleep(delay)

                # 刷新token
                self._xsrf_token = self._get_xsrf_token()

        return {"success": False, "message": f"发布微博失败，已重试{self.MAX_RETRIES}次"}

    def post_picture(self, content: str, image_paths: Union[str, List[str]]) -> Dict[str, Any]:
        """
        与WeiboPostService接口兼容的图片发布方法

        Args:
            content: 微博文本内容
            image_paths: 单个图片路径或图片路径列表

        Returns:
            Dict: 包含成功状态和消息的字典
        """
        return self.publish_images(image_paths, content)