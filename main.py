import logging
import sys
from pathlib import Path
from nba.services.nba_service import NBAService, NBAServiceConfig
from config.nba_config import NBAConfig

# 创建全局logger
logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """配置日志系统"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # 确保日志目录存在
    log_dir = NBAConfig.PATHS.LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    # 配置根日志记录器
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                log_dir / 'video_service.log',
                encoding='utf-8'
            )
        ]
    )


def ensure_directories() -> None:
    """确保所有必要的目录都存在"""
    directories = [
        NBAConfig.PATHS.CACHE_DIR,
        NBAConfig.PATHS.VIDEO_DIR,
        NBAConfig.PATHS.GIF_DIR,
        NBAConfig.PATHS.STORAGE_DIR
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"确保目录存在: {directory}")


def main() -> None:
    """主函数"""
    try:
        # 设置日志
        setup_logging()

        # 确保目录存在
        ensure_directories()

        # 创建配置 - 精简后只保留必要配置
        config = NBAServiceConfig(
            # 基础配置
            team="Lakers",
            player="LeBron James",
            date_str="last",

            # 视频配置
            video_format='gif',  # 'mp4' 或 'gif'
            video_quality='hd',  # 'sd' 或 'hd'

            # 缓存配置
            cache_size=128,
            auto_refresh=False,
            use_pydantic_v2=True
        )

        # 使用上下文管理器创建服务实例
        with NBAService(config) as nba:
            # 获取不同类型的视频
            video_types = ["FGM", "BLK", "STL", "AST"]
            for video_type in video_types:
                logger.info(f"\n开始获取 {video_type} 类型的视频...")
                try:
                    videos = nba.get_game_videos(context_measure=video_type)
                    if videos:
                        logger.info(f"=== {video_type} 视频处理完成 ===")
                        for event_id, path in videos.items():
                            logger.info(f"- Event {event_id}: {path}")
                    else:
                        logger.warning(f"未找到 {video_type} 类型的视频或处理失败")
                except Exception as e:
                    logger.error(f"{video_type} 视频处理出错: {e}")
                    continue

    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
    finally:
        logging.shutdown()


if __name__ == "__main__":
    main()