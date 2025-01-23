# main.py
import logging
import os
from pathlib import Path
from config.nba_config import NBAConfig
from nba.services.nba_service import NBAService, NBAServiceConfig
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)


def print_game_info(game_info: dict) -> None:
    """打印比赛信息"""
    if not game_info:
        logger.warning("无比赛信息")
        return

    print("\n=== 比赛信息 ===")
    for key, value in game_info.items():
        print(f"\n--- {key} ---")
        if isinstance(value, dict):
            for k, v in value.items():
                print(f"{k}: {v}")
        else:
            print(value)


def print_service_status(service: NBAService) -> None:
    """打印服务状态"""
    print("\n=== 服务状态 ===")
    status_dict = service.get_service_status()
    for name, status in status_dict.items():
        print(f"{name}: {status}")


def save_content(content: str, filename: str) -> None:
    """保存内容到文件"""
    if not content:
        logger.warning(f"无内容可保存: {filename}")
        return

    output_dir = NBAConfig.PATHS.STORAGE_DIR / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    file_path = output_dir / filename
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"\n内容已保存至: {file_path}")
    except Exception as e:
        logger.error(f"保存文件失败 {filename}: {e}")


def main():
    """主函数"""
    try:
        # 从环境变量获取 AI 配置
        ai_api_key = os.getenv('NBA_AI_API_KEY')
        ai_base_url = os.getenv('NBA_AI_BASE_URL')

        if not ai_api_key:
            logger.warning("未设置 AI API 密钥，AI 功能将被禁用")

        # 配置服务
        config = NBAServiceConfig(
            team="Lakers",
            player="LeBron James",
            date_str="last",
            language="zh_CN",
            format_type="translate",  # 新增 format_type 配置
            video_quality="hd",
            to_gif=True,
            compress_video=True,
            video_max_workers=3,
            figure_path=NBAConfig.PATHS.PICTURES_DIR,
            cache_dir=NBAConfig.PATHS.CACHE_DIR,
            storage_dir=NBAConfig.PATHS.STORAGE_DIR,
            video_dir=NBAConfig.PATHS.VIDEO_DIR,
            gif_dir=NBAConfig.PATHS.GIF_DIR,
            # AI 配置
            use_ai=bool(ai_api_key),  # 只有在有 API 密钥时才启用 AI
            ai_api_key=ai_api_key,
            ai_base_url=ai_base_url
        )

        # 使用上下文管理器
        with NBAService(config) as nba:
            # 打印服务状态
            print_service_status(nba)

            # 1. 获取比赛概况
            game_info = nba.get_game_summary()
            print_game_info(game_info)

            # 2. 生成不同类型的比赛报告
            print("\n=== 生成比赛报告 ===")

            # 2.1 完整报告
            full_report = nba.format_game_content(content_type="full")
            save_content(full_report, "full_report.txt")

            # 2.2 简短总结
            brief_report = nba.format_game_content(content_type="brief")
            save_content(brief_report, "brief_report.txt")

            # 2.3 技术统计
            tech_report = nba.format_game_content(content_type="technical")
            save_content(tech_report, "technical_report.txt")

            # 3. 获取球员统计
            player_stats = nba.get_player_statistics()
            save_content(player_stats, "player_stats.txt")

            # 4. 获取比赛精彩瞬间
            highlights = nba.get_game_highlights()
            save_content(highlights, "highlights.txt")

            # 5. 获取球队数据对比
            comparison = nba.get_team_comparison()
            save_content(comparison, "team_comparison.txt")

            # 6. 获取比赛视频
            videos = nba.get_game_videos()
            if videos:
                print("\n=== 视频下载完成 ===")
                for event_id, path in videos.items():
                    print(f"视频 {event_id}: {path}")
            else:
                logger.warning("未找到视频或下载失败")

            # 7. 绘制得分影响力图
            impact_chart = nba.plot_player_scoring_impact()
            if impact_chart:
                print(f"\n得分影响力图已保存至: {impact_chart}")
            else:
                logger.warning("绘制得分影响力图失败")

    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)


if __name__ == "__main__":
    # 初始化配置
    NBAConfig.initialize()

    # 运行主程序
    main()