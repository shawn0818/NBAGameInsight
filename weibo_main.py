# weibo_main.py
import logging
import os
import time
from typing import Dict, Any, Optional

from dotenv import load_dotenv
from nba.services.nba_service import NBAService, NBAServiceConfig
from weibo.weibo_post_service import NBAWeiboService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_environment() -> tuple[bool, Optional[str], Optional[str]]:
    """加载和验证环境变量"""
    load_dotenv()

    # 验证微博 cookies
    cookies = os.getenv('WB_COOKIES')
    if not cookies:
        raise ValueError("未找到 WB_COOKIES 环境变量")
    logger.info("成功加载 cookies 配置")

    # 验证 AI 配置
    ai_api_key = os.getenv('DEEPSEEK_API_KEY')
    ai_base_url = os.getenv('DEEPSEEK_API_BASE_URL')

    if not ai_api_key:
        logger.warning("未设置 DEEPSEEK_API_KEY，AI 功能将被禁用")
        use_ai = False
    else:
        use_ai = True

    return use_ai, ai_api_key, ai_base_url


def prepare_game_content(nba_service: NBAService) -> Dict[str, Any]:
    """准备比赛内容"""
    logger.info("开始准备比赛内容...")

    # 获取完整比赛信息
    game_info = nba_service.display_game_info()
    if not game_info:
        raise ValueError("获取比赛信息失败")

    # 准备文本内容
    content = {
        "game_info": game_info,
        "text": "",
        "analysis": None,
        "videos": None
    }

    # 如果有AI服务,生成分析内容
    if hasattr(nba_service, '_ai_service') and nba_service._ai_service:
        content["analysis"] = nba_service._ai_service.generate_weibo_post(
            game_info,
            post_type="game_analysis"
        )

    # 获取视频内容
    try:
        videos = nba_service.get_game_videos(context_measure="FGM")
        if videos and "gifs" in videos:
            content["videos"] = videos
    except Exception as e:
        logger.warning(f"获取视频失败: {e}")

    logger.info("比赛内容准备完成")
    return content


def publish_content(weibo_service: NBAWeiboService, content: Dict[str, Any]) -> None:
    """发布内容"""
    logger.info("开始发布内容...")

    # 先发布纯文本分析
    response = weibo_service.publish_game_analysis(
        content=content,
        with_video=False
    )
    logger.info(f"发布比赛分析: {response.message}")

    if not response.success:
        logger.error("比赛分析发布失败")
        return

    # 如果有视频内容,等待一段时间后发布
    if content.get("videos"):
        time.sleep(60)  # 等待1分钟
        response = weibo_service.publish_game_analysis(
            content=content,
            with_video=True
        )
        logger.info(f"发布比赛视频分析: {response.message}")


def main():
    try:
        # 加载环境变量并获取配置
        use_ai, ai_api_key, ai_base_url = load_environment()

        # 配置NBA服务
        config = NBAServiceConfig(
            team="Lakers",
            player="LeBron James",
            use_ai=use_ai,
            ai_api_key=ai_api_key,
            ai_base_url=ai_base_url,
            language="zh_CN"
        )

        # 使用上下文管理器确保资源正确释放
        with NBAService(config) as nba_service:
            # 1. 准备内容
            content = prepare_game_content(nba_service)

            # 2. 初始化微博服务
            with NBAWeiboService(nba_service) as weibo_service:
                # 检查服务是否就绪
                if not weibo_service.is_ready():
                    raise ValueError("微博服务未就绪")

                # 3. 发布内容
                publish_content(weibo_service, content)

            logger.info("所有发布任务已完成")

    except ValueError as e:
        logger.error(f"配置或数据错误: {e}")
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
    finally:
        logger.info("程序执行结束")


if __name__ == "__main__":
    main()