# weibo/weibo_publisher.py

import logging
import os
from pathlib import Path
from typing import List, Optional
import requests
import random
from dotenv import load_dotenv
from config.weibo_config import WeiboConfig, parse_cookies_string
from weibo.weibo_model import WeiboPost


class WeiboPublisher:
   """微博发布器"""

   def __init__(self):
       self.logger = logging.getLogger(self.__class__.__name__)

       # 加载环境变量
       load_dotenv()
       cookies_str = os.getenv('WB_COOKIES')
       self.logger.info("原始cookies字符串: %s", cookies_str)  # 新增：输出原始cookie字符串
       if not cookies_str:
           raise ValueError("未找到 WB_COOKIES 环境变量")

       # 解析 cookies
       cookies = parse_cookies_string(cookies_str)
       self.logger.info("解析后的cookies: %s", cookies)  # 新增：输出解析后的cookies
       if not cookies:
           raise ValueError("无法解析有效的 cookies")

       # 设置并验证是否正确配置cookies
       WeiboConfig.MOBILE_API.WB_COOKIES = cookies
       WeiboConfig.validate_cookies()  # 新增：验证配置
       self.config = WeiboConfig
       self.logger.info("最终配置中的cookies: %s", self.config.MOBILE_API.WB_COOKIES)  # 新增：输出配置中的cookies

       self.session = requests.Session()
       self._xsrf_token = None
       self._setup_session()

   def _setup_session(self):
       """配置请求会话"""
       self.session.headers.update(self.config.MOBILE_API.BASE_HEADERS)
       self.logger.info("基础请求头: %s", self.session.headers)  # 新增：输出基础请求头
       for cookie_name, cookie_value in self.config.MOBILE_API.WB_COOKIES.items():
           self.session.cookies.set(cookie_name, cookie_value, domain='m.weibo.cn', path='/')
           # 新增：输出设置后的所有cookies
       self.logger.info("会话中的所有cookies:")
       self._xsrf_token = self._get_token()
       if not self._xsrf_token:
           raise Exception("无法获取 XSRF-TOKEN")

   def _get_token(self) -> Optional[str]:
       """获取新的 XSRF-TOKEN"""
       try:
           # 新增：记录请求详情
           self.logger.info("正在请求 XSRF-TOKEN...")
           self.logger.info("请求URL: %s", self.config.MOBILE_API.ENDPOINTS['CONFIG'])
           self.logger.info("请求头: %s", self.session.headers)

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
           boundary = f"----WebKitFormBoundary{''.join([random.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(24)])}"
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
           # 新增：记录发布前的认证状态
           self.logger.info("当前会话中的cookies:")

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

           # 新增：详细记录请求信息
           self.logger.info("发布请求详情:")
           self.logger.info("URL: %s", url)
           self.logger.info("Headers: %s", headers)
           self.logger.info("Cookies: %s", dict(self.session.cookies))

           content = post.text if post.text else "分享图片"
           data = {
               'content': content,
               'st': self._xsrf_token,
               '_spr': 'screen:1280x720'
           }

           if pic_ids:
               data['picId'] = ','.join(pic_ids)
               self.logger.info(f"添加图片ID到请求: {data['picId']}")

           self.logger.info(f"发送发布请求: {url}")
           self.logger.debug(f"请求头: {headers}")
           self.logger.debug(f"请求数据: {data}")

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