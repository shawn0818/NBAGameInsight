from typing import Dict, Any, List, Union
import os,time,json,hashlib,random
import requests,base64,zlib
from utils.logger_handler import AppLogger


class WeiboImagePublisher:
    """微博图片上传发布工具类"""

    SUPPORTED_FORMATS = ('.jpg', '.jpeg', '.png', '.gif')
    APP_ID = "339644097" #应该是web端在微博内部的id
    UID = "6006177856" #微博的账户ID
    TIMEOUT = (30, 600)  # 连接超时30秒, 读取超时10分钟 ，简单设置下超时时间

    def __init__(self, cookie: str):
        """
        初始化微博图片发布器

        Args:
            cookie: 微博登录cookie
        """
        self.cookie = cookie
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.session = requests.Session()
        self._setup_session()

    def _setup_session(self):
        """设置会话默认参数"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Origin": "https://weibo.com",
            "DNT": "1",
            "Connection": "keep-alive",
            "Referer": "https://weibo.com/",
            "Cookie": self.cookie
        }
        self.session.headers.update(headers)
        self.session.timeout = self.TIMEOUT


    def _get_xsrf_token(self):
        """获取XSRF token"""
        try:
            # 1. 先访问主页获取基础 cookie
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
                "Cookie": self.cookie
            }

            session = requests.Session()
            response = session.get("https://weibo.com", headers=headers)
            response.raise_for_status()

            # 2. 再请求 log/action 接口,这是点击页面上添加图片按钮后的请求
            url = "https://weibo.com/ajax/log/action"
            headers.update({
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://weibo.com",
                "Referer": "https://weibo.com/",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin"
            })

            params = {
                "type": "pic",
                "uicode": "20000398",
                "fid": "232160",
                "act_code": "4874",
                "ext": "module:02-real",
                "luicode": "20000390",
                "t": str(int(time.time() * 1000))
            }

            response = session.get(url, params=params, headers=headers)
            response.raise_for_status()

            # 3. 从 cookie 中获取 token
            for cookie in session.cookies:
                if cookie.name == 'XSRF-TOKEN':
                    #self.logger.info(f"成功获取XSRF_Token")
                    return cookie.value

            # 4. 如果没有在 cookie 中找到，尝试获取特殊头信息
            xsrf_token = response.headers.get('XSRF-TOKEN') or \
                         response.headers.get('X-XSRF-TOKEN') or \
                         response.request.headers.get('X-XSRF-TOKEN')

            if xsrf_token:
                #self.logger.info(f"成功从请求头获取XSRF_Token")
                return xsrf_token

            raise Exception("未能获取XSRF_Token")

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
            image_params = self.process_image(file_path)

            url = "https://picupload.weibo.com/interface/upload.php"
            headers = {
                "Content-Type": "application/octet-stream",
                "Content-Length": str(image_params['file_size'])
            }

            image_params['upload_params']['request_id'] = str(int(time.time() * 1000))

            response = self.session.post(
                url,
                params=image_params['upload_params'],
                headers=headers,
                data=image_params['file_data']
            )
            response.raise_for_status()

            try:
                result = json.loads(response.text)
            except json.JSONDecodeError:
                decoded_bytes = base64.b64decode(response.text)
                result = json.loads(decoded_bytes.decode('utf-8'))

            if not result.get("ret") or not result.get("pic", {}).get("pid"):
                raise Exception(f"上传失败，错误码: {result.get('error')}")

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
        if isinstance(image_paths, str):
            image_paths = [image_paths]

        image_info_list = []
        for path in image_paths:
            info = self.upload_image(path)
            image_info_list.append(info)
            time.sleep(random.uniform(1, 3))  # 添加随机延迟

        return image_info_list

    def publish_images(self, image_paths: Union[str, List[str]], content: str = "",
                    ) -> Dict[str, Any]:
        """
        发布带图片的微博

        Args:
            image_paths: 单个图片路径或图片路径列表
            content: 微博文本内容

        Returns:
            Dict: 发布结果
        """
        url = "https://weibo.com/ajax/statuses/update"
        retry_count: int = 3  #重试次数

        for attempt in range(retry_count):
            try:
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
                    "X-XSRF-TOKEN": self._get_xsrf_token()
                }

                response = self.session.post(url, headers=headers, data=data)
                response.raise_for_status()
                result = response.json()

                if result.get("ok") == 1:
                    self.logger.info("微博发布成功")
                    return {"success": True, "message": "发布成功"}
                else:
                    raise Exception(f"微博发布失败: {result.get('msg')}")

            except Exception as e:
                if attempt == retry_count - 1:
                    error_message = f"微博发布最终失败，已重试{retry_count}次。错误信息: {str(e)}"
                    self.logger.error(error_message, exc_info=True)
                    return {"success": False, "message": error_message}
                retry_delay_seconds = random.uniform(2, 5)
                self.logger.warning(
                    f"微博发布失败 (第{attempt + 1}/{retry_count}次重试)。将在 {retry_delay_seconds:.2f} 秒后重试。错误信息: {str(e)}"
                )
                time.sleep(retry_delay_seconds)

        # 循环结束后，所有重试都失败
        return {"success": False, "message": "微博发布最终失败，超出重试次数"}
