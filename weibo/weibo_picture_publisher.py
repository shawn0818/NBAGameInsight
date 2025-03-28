from typing import Dict, Any, List, Union
import os, time, json, hashlib, random
import requests, base64, zlib
from utils.logger_handler import AppLogger


class WeiboImagePublisher:
    """微博图片上传发布工具类"""

    SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.png', '.gif')
    APP_ID = "339644097"  # 应该是web端在微博内部的id
    UID = "6006177856"  # 微博的账户ID
    TIMEOUT = (180, 600)  # 连接超时30秒, 读取超时10分钟 ，简单设置下超时时间

    def __init__(self, cookie: str):
        """初始化上传器
        Args:
            cookie: 用户cookie
        """
        self.logger = AppLogger.get_logger(__name__, app_name='weibo')
        self.cookie = cookie
        self.xsrf_token = ""  # 初始为空，将通过API自动获取

        # 创建并初始化会话对象
        self.session = requests.Session()

        # 设置会话的cookies
        if self.cookie:
            for cookie_str in self.cookie.split(';'):
                if '=' in cookie_str:
                    name, value = cookie_str.strip().split('=', 1)
                    self.session.cookies.set(name, value)

        # 设置会话的基本headers
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Origin": "https://weibo.com",
            "DNT": "1",
            "Connection": "keep-alive",
            "Referer": "https://weibo.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache"
        })

    def _get_xsrf_token(self):
        """获取XSRF token"""
        try:
            # 请求 log/action 接口，这是点击页面上添加图片按钮后的请求
            url = "https://weibo.com/ajax/log/action"
            headers = {
                "Referer": "https://weibo.com",
                "Content-Type": "application/json;charset=utf-8",
                "Sec-Fetch-Site": "same-origin"
            }

            params = {
                "type": "pic",
                "uicode": "20000398",
                "fid": "232160",
                "act_code": "4874",
                "ext": "module:02-real",
                "luicode": "20000390",
                "t": str(int(time.time() * 1000))
            }

            # 使用会话发送请求
            response = self.session.get(url, params=params, headers=headers, timeout=self.TIMEOUT)
            response.raise_for_status()

            # 从会话的cookies中提取新的XSRF令牌
            if 'XSRF-TOKEN' in self.session.cookies:
                self.xsrf_token = self.session.cookies['XSRF-TOKEN']
                self.session.headers.update({"X-XSRF-TOKEN": self.xsrf_token})
                self.logger.info(f"成功获取XSRF令牌: {self.xsrf_token}")
                return self.xsrf_token

        except Exception as e:
            self.logger.error(f"获取XSRF_Token失败: {str(e)}", exc_info=True)
            raise

    def process_image(self, file_path: str) -> Dict[str, Any]:
        """
        处理图片文件，返回所需的所有参数

        Args:
            file_path: 图片文件路径

        Returns:
            Dict: 包含处理后的图片参数的字典

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 不支持的文件格式
        """
        self.logger.debug(f"开始处理图片文件: {file_path}")
        # 检查文件是否存在
        if not os.path.exists(file_path):
            self.logger.error(f"文件不存在: {file_path}")
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 检查文件格式
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in self.SUPPORTED_FORMATS:
            self.logger.error(f"不支持的图片格式: {file_ext}")
            raise ValueError(f"不支持的图片格式: {file_ext}。支持的格式: {', '.join(self.SUPPORTED_FORMATS)}")

        # 读取文件数据
        with open(file_path, 'rb') as f:
            file_data = f.read()

        # 基础文件信息
        file_size = len(file_data)
        file_md5 = hashlib.md5(file_data).hexdigest()
        cs = zlib.crc32(file_data) & 0xFFFFFFFF

        # 确定文件类型
        content_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif'
        }

        # 组装上传参数
        upload_params = {
            "file_source": "1",
            "cs": str(cs),
            "ent": "miniblog",
            "appid": self.APP_ID,
            "uid": self.UID,
            "raw_md5": file_md5,
            "ori": "1",
            "mpos": "1",
            "nick": "0",
            "pri": "0",
            "file_size": str(file_size)
        }

        # 返回处理结果
        return {
            'file_data': file_data,
            'file_size': file_size,
            'content_type': content_type_map[file_ext],
            'upload_params': upload_params
        }

    def upload_image(self, file_path: str) -> Dict[str, str]:
        """
        上传单张图片

        Args:
            file_path: 图片文件路径

        Returns:
            Dict: 包含pid和类型的字典
        """
        try:
            # 处理图片
            image_params = self.process_image(file_path)

            # 设置上传URL和特定的请求头
            url = "https://picupload.weibo.com/interface/upload.php"
            headers = {
                "Content-Type": "application/octet-stream",
                "Content-Length": str(image_params['file_size'])
            }

            # 添加请求ID参数
            upload_params = image_params['upload_params']
            upload_params['request_id'] = str(int(time.time() * 1000))

            self.logger.debug(f"上传图片请求参数: {upload_params}")

            # 发送上传请求
            response = self.session.post(
                url,
                params=upload_params,
                headers=headers,
                data=image_params['file_data'],
                timeout=self.TIMEOUT
            )
            response.raise_for_status()

            # 处理响应
            try:
                result = json.loads(response.text)
            except json.JSONDecodeError:
                # 有些响应可能是Base64编码的
                try:
                    decoded_bytes = base64.b64decode(response.text)
                    result = json.loads(decoded_bytes.decode('utf-8'))
                except Exception as e:
                    self.logger.error(f"解析响应失败: {str(e)}")
                    self.logger.debug(f"原始响应: {response.text[:200]}...")  # 只记录前200个字符避免日志过大
                    raise ValueError(f"无法解析上传响应: {str(e)}")

            self.logger.debug(f"上传图片响应: {result}")

            if not result.get("ret") or not result.get("pic", {}).get("pid"):
                raise Exception(f"上传失败，错误码: {result.get('error', '未知错误')}")

            return {
                'pid': result["pic"]["pid"],
                'type': image_params['content_type']
            }

        except Exception as e:
            self.logger.error(f"上传图片失败: {str(e)}", exc_info=True)
            raise

    def upload_images(self, image_paths: Union[str, List[str]]) -> List[Dict[str, str]]:
        """
        上传一张或多张图片

        Args:
            image_paths: 单个图片路径或图片路径列表

        Returns:
            List[Dict]: 图片信息列表
        """

        # 转换单个路径为列表
        if isinstance(image_paths, str):
            image_paths = [image_paths]

        self.logger.info(f"开始上传 {len(image_paths)} 张图片")

        image_info_list = []
        for i, path in enumerate(image_paths):
            try:
                self.logger.info(f"上传第 {i + 1}/{len(image_paths)} 张图片: {path}")
                info = self.upload_image(path)
                image_info_list.append(info)
                self.logger.info(f"图片上传成功: {info}")

                # 添加随机延迟，避免频繁请求
                if i < len(image_paths) - 1:  # 如果不是最后一张图片
                    delay = random.uniform(5, 15)
                    self.logger.debug(f"等待 {delay:.2f} 秒后上传下一张图片")
                    time.sleep(delay)

            except Exception as e:
                self.logger.error(f"上传图片 {path} 失败: {str(e)}", exc_info=True)
                # 可以选择继续上传其他图片，或者在这里直接抛出异常中断整个上传过程
                raise  # 如果希望一张图片失败就中断整个上传，保留此行

        return image_info_list

    def publish_images(self, image_paths: Union[str, List[str]], content: str = "") -> Dict[str, Any]:
        """
        发布带图片的微博

        Args:
            image_paths: 单个图片路径或图片路径列表
            content: 微博文本内容

        Returns:
            Dict: 发布结果
        """
        url = "https://weibo.com/ajax/statuses/update"
        retry_count = 3

        for attempt in range(retry_count):
            try:
                # 先获取最新的XSRF令牌，用于发布微博
                self.xsrf_token = self._get_xsrf_token()
                # 确保请求头中包含最新的XSRF令牌
                self.session.headers.update({"X-XSRF-TOKEN": self.xsrf_token})

                # 上传图片
                image_info_list = self.upload_images(image_paths)
                pic_id = [{"type": info["type"], "pid": info["pid"]} for info in image_info_list]

                data = {
                    "content": content,
                    "visible": "0",
                    "pic_id": json.dumps(pic_id)
                }

                headers = {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest",
                    "X-XSRF-TOKEN": self.xsrf_token  # 确保这里明确设置XSRF令牌
                }

                self.logger.info(f"开始发布微博，内容: {content[:30]}{'...' if len(content) > 30 else ''}")
                self.logger.debug(f"发布请求数据: {data}")

                response = self.session.post(url, headers=headers, data=data, timeout=self.TIMEOUT)
                response.raise_for_status()

                result = response.json()
                self.logger.debug(f"发布响应: {result}")

                if result.get("ok") == 1:
                    self.logger.info("微博发布成功")
                    return {"success": True, "message": "发布成功", "data": result}
                else:
                    error_msg = result.get("msg", "未知错误")
                    self.logger.warning(f"微博发布返回错误: {error_msg}")
                    raise Exception(f"微博发布失败: {error_msg}")

            except Exception as e:
                if attempt == retry_count - 1:
                    error_message = f"微博发布最终失败，已重试{retry_count}次。错误信息: {str(e)}"
                    self.logger.error(error_message, exc_info=True)
                    return {"success": False, "message": error_message}

                retry_delay_seconds = random.uniform(2, 5)
                self.logger.warning(
                    f"微博发布失败 (第{attempt + 1}/{retry_count}次尝试)。将在 {retry_delay_seconds:.2f} 秒后重试。错误信息: {str(e)}"
                )
                time.sleep(retry_delay_seconds)

        # 循环结束后，所有重试都失败
        return {"success": False, "message": "微博发布最终失败，超出重试次数"}


###=====以下是移动网页版API发布，可以作为备用====
'''
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
        self.logger = AppLogger.get_logger(__name__, app_name='weibo')

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
'''