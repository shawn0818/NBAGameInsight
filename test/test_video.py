import asyncio
import logging
from pathlib import Path
from datetime import datetime
import sys
import unittest



# 将项目根目录添加到 Python 路径
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from nba.parser.video_query_parser import NBAVideoProcessor
from nba.services.game_video_service import PlayerVideoService
from nba.models.video_model import ContextMeasure
from config.nba_config import NBAConfig
from nba.models.video_model import VideoRequestParams

# 配置日志输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class VideoServiceTester:
    """视频服务测试类"""
    
    def __init__(self):
        self.video_processor = NBAVideoProcessor()
        
    def print_separator(self, message: str = ""):
        """打印分隔线"""
        print("\n" + "="*50)
        if message:
            print(message)
            print("="*50)
            
    async def test_video_download(self):
        """测试视频下载功能"""
        try:
            # 测试参数
            player_name = "Stephen_Curry"  # 用于文件命名
            player_id = 201939
            team_id = 1610612744
            game_id = "0022401204"
            
            self.print_separator("开始视频下载测试")
            print(f"测试参数:")
            print(f"- 球员: {player_name}")
            print(f"- 球员ID: {player_id}")
            print(f"- 球队ID: {team_id}")
            print(f"- 比赛ID: {game_id}")
            
            # 测试不同类型的视频
            action_types = [
                ContextMeasure.FG3M,  # 三分命中
                ContextMeasure.FGM,   # 投篮命中
                ContextMeasure.AST    # 助攻
            ]
            
            for action_type in action_types:
                self.print_separator(f"获取 {action_type.value} 类型的视频")
                
                # 1. 构建查询参数
                query = VideoRequestParams(
                    game_id=game_id,
                    player_id=str(player_id),
                    team_id=str(team_id),
                    context_measure=action_type,
                    season="2023-24",
                    season_type="Regular Season"
                )
                
                # 打印构建的参数，用于调试
                params = query.build()
                print("\n请求参数:")
                print(params)
                
                # 2. 获取视频
                videos = self.video_processor.get_videos_by_query(query)
                
                if not videos:
                    print(f"未找到 {action_type.value} 类型的视频")
                    continue
                    
                print(f"找到 {len(videos)} 个视频片段")
                
                # 3. 下载视频
                print("\n开始下载视频...")
                results = {}
                for event_id, video_asset in videos.items():
                    video_url = video_asset.urls.get('hd')
                    if not video_url:
                        results[event_id] = f"未找到HD质量的视频URL"
                        continue

                    try:
                        # 生成保存路径
                        video_name = f"{player_name}_{game_id}_{event_id}"
                        temp_path = NBAConfig.PATHS.CACHE_DIR / f"{video_name}_temp.mp4"
                        output_path = NBAConfig.PATHS.VIDEO_DIR / f"{video_name}.mp4"
                        
                        # 确保输出目录存在
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # 下载视频
                        if not self.video_processor.downloader.download(video_url, temp_path):
                            results[event_id] = "视频下载失败"
                            continue
                            
                        # 移动到最终位置
                        temp_path.rename(output_path)
                        results[event_id] = output_path
                        
                    except Exception as e:
                        results[event_id] = f"处理失败: {str(e)}"
                        if temp_path.exists():
                            temp_path.unlink()
                
                # 4. 检查结果
                success_count = sum(1 for v in results.values() if isinstance(v, Path))
                print(f"\n下载完成:")
                print(f"- 成功: {success_count}")
                print(f"- 失败: {len(results) - success_count}")
                
                # 显示详细结果
                print("\n详细结果:")
                for event_id, result in results.items():
                    status = "成功" if isinstance(result, Path) else "失败"
                    detail = str(result) if isinstance(result, Path) else result
                    print(f"视频 {event_id}: {status} - {detail}")
            
            self.print_separator("测试完成")
            
        except Exception as e:
            logger.error(f"测试过程中出错: {e}", exc_info=True)
            import traceback
            traceback.print_exc()

async def main():
    """主函数"""
    # 确保必要的目录存在
    NBAConfig.PATHS.ensure_directories()
    
    # 运行测试
    tester = VideoServiceTester()
    await tester.test_video_download()

if __name__ == "__main__":
    asyncio.run(main())