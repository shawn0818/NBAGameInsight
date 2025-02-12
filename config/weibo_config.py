# weibo_config.py
import logging
from pathlib import Path
from typing import  Dict
from utils.logger_handler import AppLogger

logger =  AppLogger.get_logger(__name__, app_name='weibo')

def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent

def parse_cookies_string(cookies_str: str) -> Dict[str, str]:
    """从完整的cookies字符串中提取需要的cookies"""
    if not cookies_str:
        return {}

    try:
        # 解析所有cookies
        cookies_dict = dict(item.split("=", 1) for item in cookies_str.strip('"').split("; "))

        # 只保留必需的cookies
        required_cookies = {'SUB', 'SUBP', '_T_WM', 'WEIBOCN_FROM'}
        result = {k: v for k, v in cookies_dict.items() if k in required_cookies}

        # 验证是否获取到所有必需的cookies
        missing_cookies = required_cookies - set(result.keys())
        if missing_cookies:
            raise ValueError(f"缺少必需的cookies: {', '.join(missing_cookies)}")

        return result

    except Exception as e:
        logger.error(f"解析 cookies 失败: {e}")
        return {}


class WeiboConfig:
    """微博配置类"""

    @classmethod
    def validate_cookies(cls):
        """验证cookies配置"""
        if not cls.MOBILE_API.WB_COOKIES:
            raise ValueError("WB_COOKIES 未设置")
        required =  {'SUB', 'SUBP', '_T_WM',  'WEIBOCN_FROM'}
        missing = required - set(cls.MOBILE_API.WB_COOKIES.keys())
        if missing:
            raise ValueError(f"缺少必需的 cookies: {missing}")

    class MOBILE_API:
        """移动端 API 配置"""

        # Cookies 配置
        WB_COOKIES = {} # 初始为空，后续设置从环境变量中获取微博 cookies

        # API 端点
        ENDPOINTS = {
            'CONFIG': 'https://m.weibo.cn//api/users/show',
            'UPLOAD': 'https://m.weibo.cn/api/statuses/uploadPic',
            'UPDATE': 'https://m.weibo.cn/api/statuses/update'
        }

        # 基本请求头,发起第一次请求，获取X-XSRF-TOKEN
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
  

