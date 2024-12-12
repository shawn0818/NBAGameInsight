import json
import asyncio
from typing import Optional, List, Dict
from dataclasses import dataclass
from datetime import datetime
import time
from playwright.async_api import async_playwright
import os
import random

@dataclass
class WeiboPost:
    text: str
    media_paths: List[str] = None
    scheduled_time: Optional[datetime] = None

class WeiboPublisher:
    def __init__(self):
        self.cookies_path = "weibo_cookies.json"
        
    async def load_cookies(self):
        """加载保存的cookies"""
        try:
            with open(self.cookies_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Cookie file not found: {self.cookies_path}")
            return None

    async def login_with_cookies(self, page):
        """使用cookies登录微博"""
        cookies = await self.load_cookies()
        if not cookies:
            return False
            
        # 设置cookies
        await page.context.add_cookies(cookies)
        
        # 访问微博首页验证登录状态
        await page.goto('https://weibo.com', wait_until='networkidle')
        
        # 检查是否登录成功
        is_logged_in = await page.locator('.gn_nav_list').is_visible()
        return is_logged_in

    async def publish_post(self, post: WeiboPost) -> bool:
        """发布微博"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)  # 设置为 True 可以隐藏浏览器
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                # 登录
                login_success = await self.login_with_cookies(page)
                if not login_success:
                    print("Login failed")
                    return False

                # 随机延时，模拟人工操作
                await asyncio.sleep(random.uniform(1, 3))
                
                # 点击发布微博按钮
                await page.click('[node-type="publish_btn"]')
                await asyncio.sleep(1)
                
                # 输入文本
                await page.fill('.Form_input_2gtXx', post.text)
                await asyncio.sleep(1)
                
                # 如果有媒体文件，上传
                if post.media_paths:
                    for media_path in post.media_paths:
                        input_file = await page.query_selector('input[type="file"]')
                        await input_file.set_input_files(media_path)
                        # 等待媒体文件上传完成
                        await page.wait_for_selector('.picture_list_1amla img')
                        await asyncio.sleep(2)
                
                # 发送微博
                await page.click('.Form_button_2Rz5h')
                await asyncio.sleep(3)  # 等待发送完成
                
                return True
                
            except Exception as e:
                print(f"Error publishing to Weibo: {e}")
                return False
                
            finally:
                await browser.close()

    async def publish_with_retry(self, post: WeiboPost, max_retries: int = 3, delay: int = 5) -> bool:
        """带重试机制的发布"""
        for attempt in range(max_retries):
            if await self.publish_post(post):
                return True
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
        return False

    def publish(self, post: WeiboPost) -> bool:
        """同步方法封装"""
        return asyncio.run(self.publish_with_retry(post))

    def create_highlight_post(self, player_name: str, action_info: Dict, gif_path: str) -> WeiboPost:
        """根据球员动作信息创建微博内容"""
        # 格式化时间
        action_time = f"第{action_info['period']}节 {action_info['clock']}"
        
        # 生成描述文本
        text = (
            f"#{player_name}# 比赛集锦\n"
            f" {action_info['description']}\n"
            f" {action_time}\n"
            f" 比分 {action_info['score']}\n"
            f"#NBA# #{player_name}集锦#"
        )
        
        return WeiboPost(text=text, media_paths=[gif_path])
