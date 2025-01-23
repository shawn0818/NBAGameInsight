# weibo_config.py
import os
from pathlib import Path
import requests
from typing import List
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def parse_cookies_string(cookies_str: str) -> dict:
    """解析cookies字符串为字典"""
    if not cookies_str:
        return {}
    return dict(item.split("=", 1) for item in cookies_str.strip('"').split("; "))


def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent


class WeiboConfig:
    """微博配置类"""

    class MOBILE_API:
        """移动端 API 配置"""
        # API 端点
        ENDPOINTS = {
            'CONFIG': 'https://m.weibo.cn/api/config',
            'UPLOAD': 'https://m.weibo.cn/api/statuses/uploadPic',
            'UPDATE': 'https://m.weibo.cn/api/statuses/update'
        }

        # 基本请求头
        BASE_HEADERS = {
            'authority': 'm.weibo.cn',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'dnt': '1',
            'origin': 'https://m.weibo.cn',
            'referer': 'https://m.weibo.cn/compose/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/131.0.0.0 Safari/537.36'
        }

        # 发布请求头
        UPDATE_HEADERS = {
            **BASE_HEADERS,
            'method': 'POST',
            'path': '/api/statuses/update',
            'scheme': 'https',
            'content-type': 'application/x-www-form-urlencoded',
            'mweibo-pwa': '1',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'x-requested-with': 'XMLHttpRequest'
        }

        # 上传图片请求头模板
        UPLOAD_HEADERS_TEMPLATE = {
            **BASE_HEADERS,
            'mweibo-pwa': '1',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'x-requested-with': 'XMLHttpRequest',
            'content-type': 'multipart/form-data; boundary={boundary}'
        }

        # Cookies 配置
        WB_COOKIES = parse_cookies_string(os.getenv('WB_COOKIES', '')) # 从环境变量中获取微博 cookies

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
        MAX_TEXT_LENGTH = 140
        MAX_IMAGES = 9
        ALLOWED_IMAGE_TYPES = ['.jpg', '.jpeg', '.png', '.gif']

        # 重试和间隔策略
        MAX_RETRIES = 3
        RETRY_DELAY = 5  # 发布失败后的重试间隔（秒）
        MIN_PUBLISH_INTERVAL = 10  # 两次成功发布之间的最小间隔（秒）
  

