# main.py
import logging
import asyncio
from pathlib import Path
from config.nba_config import NBAConfig
from nba.services.nba_service import NBAService, NBAServiceConfig

logger = logging.getLogger(__name__)

def print_game_info(game_info: dict) -> None:
    """打印比赛信息"""
    if not game_info:
        logger.warning("无比赛信息")
        return

    # 基本信息
    if "basic_info" in game_info:
        print("\n=== 比赛基本信息 ===")
        print(game_info["basic_info"])

    # 比赛状态
    if "status" in game_info:
        print("\n=== 比赛实时状态 ===")
        print(game_info["status"])

    # 统计数据
    if "statistics" in game_info:
        print("\n=== 比赛统计 ===")
        print(game_info["statistics"])

async def main_async():
    """异步主函数"""
    try:
        # 初始化服务
        async with NBAService() as nba:
            # 1. 获取比赛数据
            game_info = await nba.process_game_data()
            print_game_info(game_info)

            # 2. 处理视频数据
            if game_info:
                await nba.process_game_videos()

    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
    finally:
        logger.info("程序运行结束")

def main():
    """主函数"""
    # 确保配置初始化
    NBAConfig.initialize()
    # 运行异步主函数
    asyncio.run(main_async())

if __name__ == "__main__":
    main()