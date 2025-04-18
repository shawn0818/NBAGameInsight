#weibo/weibo_video_publisher.py
import json
import os
import time
import math
import hashlib
import requests
from typing import Dict, Any, Optional, List, Callable
from utils.logger_handler import AppLogger

class WeiboVideoPublisher:
    """微博视频上传工具类"""

    def __init__(self, cookie: str):
        """初始化上传器
        Args:
            cookie: 用户cookie
        """
        self.logger = AppLogger.get_logger(__name__, app_name='weibo')
        self.cookie = cookie
        self.xsrf_token = ""  # 初始为空，将通过API自动获取
        self.base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "X-XSRF-TOKEN": "",  # 初始为空，会在get_upload_urls中更新
            "Origin": "https://weibo.com",
            "DNT": "1",
            "Connection": "keep-alive",
            "Referer": "https://weibo.com/",
            "Cookie": cookie,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache"
        }


    def generate_boundary(self) -> str:
        """生成随机的boundary字符串"""
        timestamp = str(int(time.time() * 1000))
        return f"2067456weiboPro{timestamp}"

    def calculate_file_md5(self, file_path: str, chunk_size: int = 8192) -> str:
        """计算文件的MD5值
        Args:
            file_path: 文件路径
            chunk_size: 读取文件的块大小
        Returns:
            str: 文件的MD5哈希值
        """
        md5_hash = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b''):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    def calculate_chunk_md5(self, chunk_data: bytes) -> str:
        """计算数据块的MD5值
        Args:
            chunk_data: 字节数据
        Returns:
            str: 数据的MD5哈希值
        """
        return hashlib.md5(chunk_data).hexdigest()

    def get_upload_urls(self) -> Dict[str, Any]:
        """获取上传相关的URL配置，同时更新XSRF token"""
        # 创建会话对象处理cookies
        session = requests.Session()

        # 设置session的cookies
        if self.cookie:
            for cookie_str in self.cookie.split(';'):
                if '=' in cookie_str:
                    name, value = cookie_str.strip().split('=', 1)
                    session.cookies.set(name, value)

        url = "https://weibo.com/ajax/multimedia/dispatch"
        headers = {
            **self.base_headers,
            "Referer": "https://weibo.com/upload/channel",
            "Content-Type": "application/json;charset=utf-8",
            "Sec-Fetch-Site": "same-origin"
        }

        # 设置正确的请求参数
        data = {
            "source": 339644097,
            "types": "video",
            "version": 4,
            "auth_accept": "video",
            "size": 1048576,
            "timeout": 180000
        }

        # 使用session发送请求
        response = session.post(url, headers=headers, json=data)
        response.raise_for_status()

        # 从session的cookies中提取新的XSRF令牌，保存供发布视频时使用
        for cookie in session.cookies:
            if cookie.name == 'XSRF-TOKEN':
                self.xsrf_token = cookie.value
                # 更新基础请求头中的XSRF令牌
                self.base_headers["X-XSRF-TOKEN"] = self.xsrf_token
                self.logger.info(f"成功获取XSRF令牌: {self.xsrf_token}，将用于后续发布视频")
                break

        try:
            data = response.json()
            if "data" not in data or "video" not in data["data"]:
                raise ValueError(f"响应格式不正确: {data}")

            # 如果此时还没有获取到XSRF令牌，记录警告
            if not self.xsrf_token:
                print("警告：未能获取XSRF令牌，可能会影响后续视频发布")

            return data["data"]["video"]
        except ValueError as e:
            print(f"JSON解析错误: {str(e)}")
            raise

    def init_upload(self, file_path: str) -> Dict[str, Any]:
        """初始化上传请求，获取upload_id、media_id、strategy等关键参数
        Args:
            file_path: 视频文件路径
        Returns:
            Dict[str, Any]: 包含以下关键信息：
                - upload_id: 上传ID
                - media_id: 媒体ID
                - strategy: 上传策略，包含:
                    - upload_protocol: 上传协议
                    - chunk_retry: 重试次数
                    - chunk_delay: 延迟时间
                    - chunk_timeout: 超时时间
                    - chunk_read_timeout: 读取超时
                    - chunk_slow_speed: 慢速阈值
                    - threads: 线程数
                    - url_tag: URL标签
                    - chunk_size: 分块大小
                - auth: 认证信息
        """
        url = "https://fileplatform-cn1.api.weibo.com/2/fileplatform/init.json"

        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)

        params = {
            "source": "339644097",
            "size": str(file_size),
            "name": file_name,
            "type": "video",
            "client": "web",
        }

        boundary = self.generate_boundary()
        headers = {
            **self.base_headers,
            "Content-Type": f"multipart/mixed; boundary={boundary}",
        }

        data = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="biz_file"\r\n'
            "\r\n"
            '{"mediaprops":"{\\\"screenshot\\\":1}"}\r\n'
            f"--{boundary}--"
        )

        response = requests.post(
            url,
            params=params,
            headers=headers,
            data=data.encode('utf-8')
        )

        result = response.json()
        return result

    def upload_chunk(self, file_path: str, upload_info: Dict[str, Any], chunk_index: int, chunk_size: int,
                     total_chunks: int) -> bool:
        """上传单个分块
        Args:
            file_path: 视频文件路径
            upload_info: 初始化上传后返回的信息
            chunk_index: 当前分块索引
            chunk_size: 分块大小
            total_chunks: 总分块数
        Returns:
            bool: 上传是否成功
        """
        upload_url = "https://up-cn1.video.weibocdn.com/2/fileplatform/upload.json"

        with open(file_path, 'rb') as f:
            f.seek(chunk_index * chunk_size)
            chunk_data = f.read(chunk_size)

        # 计算当前块的MD5
        chunk_md5 = self.calculate_chunk_md5(chunk_data)

        # 使用初始化返回的strategy中的配置
        strategy = upload_info["strategy"]

        params = {
            "source": "339644097",
            "upload_id": upload_info["upload_id"],
            "media_id": upload_info["media_id"],
            "upload_protocol": strategy["upload_protocol"],
            "type": "video",
            "client": "web",
            "index": str(chunk_index),
            "size": str(len(chunk_data)),
            "start_loc": str(chunk_index * chunk_size),
            "count": str(total_chunks),  # 使用总块数
            "check": chunk_md5
        }

        headers = {
            **self.base_headers,
            "Content-Type": "application/octet-stream",
            "X-Up-Auth": upload_info["auth"]
        }

        response = requests.post(
            upload_url,
            params=params,
            headers=headers,
            data=chunk_data
        )

        result = response.json()
        self.logger.info(f"分块 {chunk_index + 1}/{total_chunks} 上传结果: {result}")
        return result["result"]

    def check_upload(self, upload_info: Dict[str, Any], file_size: int, chunk_count: int) -> Dict[str, Any]:
        """检查上传是否完成
        Args:
            upload_info: 初始化上传后返回的信息
            file_size: 文件总大小
            chunk_count: 总分块数
        Returns:
            Dict[str, Any]: 上传完成状态信息
        """
        url = "https://fileplatform-cn1.api.weibo.com/2/fileplatform/check.json"

        # 添加所有必需的参数
        params = {
            "source": "339644097",
            "upload_id": upload_info["upload_id"],
            "media_id": upload_info["media_id"],
            "upload_protocol": upload_info["strategy"]["upload_protocol"],  # 从strategy中获取
            "count": str(chunk_count),  # 总分块数
            "action": "finish",  # 完成动作
            "size": str(file_size),  # 文件总大小
            "client": "web",
            "status": ""  # 状态参数
        }

        headers = {
            **self.base_headers,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Up-Auth": upload_info["auth"]
        }

        response = requests.post(url, headers=headers, params=params)
        return response.json()

    def upload_video(self, file_path: str,
                     progress_callback: Optional[Callable[[int, int, float], None]] = None) -> Dict[str, Any]:
        """完整的视频上传流程

        Args:
            file_path: 视频文件路径
            progress_callback: 进度回调函数，接收参数(current_chunk, total_chunks, percentage)

        Returns:
            Dict[str, Any]: 上传完成状态信息
        """
        # 1. 获取上传URL配置
        #urls = self.get_upload_urls()

        # 2. 初始化上传
        init_result = self.init_upload(file_path)

        # 3. 默认使用8MB的分块大小
        chunk_size = 8 * 1024 * 1024

        # 计算分块信息
        file_size = os.path.getsize(file_path)
        chunk_count = math.ceil(file_size / chunk_size)

        # 上传所有分块
        strategy = init_result["strategy"]
        for i in range(chunk_count):
            retry_count = 0
            max_retries = strategy.get("chunk_retry", 3)

            while retry_count < max_retries:
                try:
                    success = self.upload_chunk(
                        file_path,
                        init_result,
                        i,
                        chunk_size,
                        chunk_count
                    )
                    if success:
                        # 更新上传进度并调用回调函数
                        current = i + 1
                        percentage = (current / chunk_count) * 100
                        self.logger.info(f"上传进度: {percentage:.2f}%")

                        # 如果提供了回调函数，则调用它
                        if progress_callback:
                            progress_callback(current, chunk_count, percentage)
                        break
                    retry_count += 1
                except Exception as e:
                    self.logger.info(f"分块 {i} 上传失败: {str(e)}")
                    retry_count += 1
                    if retry_count < max_retries:
                        delay = strategy.get("chunk_delay", 3000) / 1000
                        self.logger.info(f"正在重试... ({retry_count}/{max_retries}), 等待{delay}秒")
                        time.sleep(delay)

            if retry_count >= max_retries:
                raise Exception(f"分块 {i} 在重试 {max_retries} 次后仍然上传失败")

        # 4. 检查上传完成状态
        max_check_retries = 3
        check_retry_count = 0
        while check_retry_count < max_check_retries:
            try:
                check_result = self.check_upload(init_result, file_size, chunk_count)
                if "error" in check_result:
                    self.logger.error(f"检查上传状态失败: {check_result}")
                    check_retry_count += 1
                    time.sleep(2)
                    continue
                return check_result
            except Exception as e:
                self.logger.error(f"检查上传状态出错: {str(e)}")
                check_retry_count += 1
                if check_retry_count < max_check_retries:
                    time.sleep(2)
                    continue
                raise

        raise Exception(f"检查上传状态失败，已重试{max_check_retries}次")

    def publish_video(self,
                      media_id: str,
                      title: str,
                      content: str,
                      cover_pid: Optional[str] = None,
                      is_original: bool = True,
                      album_id: Optional[str] = None,
                      channel_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """发布视频
        Args:
            media_id: 视频ID
            title: 视频标题
            content: 微博正文内容
            cover_pid: 封面图片ID (可选，不指定则使用默认第一张)
            is_original: 是否为原创内容
            album_id: 合集ID (可选)
            channel_ids: 频道ID列表 (可选)
        """
        url = "https://weibo.com/ajax/statuses/update"

        media_params = {
            "titles": [{
                "title": title,
                "default": "true"
            }],
            "type": "video",
            "media_id": media_id,
            "resource": {
                "video_down": 0
            },
            "free_duration": {
                "start": 0,
                "end": 30
            },
            "homemade": {
                "channel_ids": channel_ids or [4450180980998176],
                "type": 0 if is_original else 2  # 0是原创，1是转载，2是二创
            },
            "approval_reprint": "1"
        }

        # 如果指定了封面
        if cover_pid:
            media_params["covers"] = [{
                "pid": cover_pid,
                "width": 1280,
                "height": 720
            }]

        # 如果指定了合集
        if album_id:
            media_params["playlist"] = {
                "playlist_video": True,
                "album_ids": album_id
            }

        data = {
            "content": content,
            "visible": 0,
            "media": json.dumps(media_params)
        }

        headers = {
            **self.base_headers,
            "Content-Type": "application/x-www-form-urlencoded"
        }

        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()
