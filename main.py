import sys
import locale
import codecs
import logging
import pandas as pd
from datetime import datetime
import time
from typing import Dict

from nba.fetcher.schedule import ScheduleFetcher
from nba.fetcher.game import GameFetcher
from nba.parser.schedule_parser import ScheduleParser
from config.nba_config import NBAConfig
from utils.http_handler import HTTPRequestManager, DataPoller
from utils.time_helper import TimeConverter

def setup_chinese_env():
    """设置中文环境"""
    # 设置默认编码
    if sys.platform.startswith('win'):
        # Windows系统
        system_encoding = locale.getpreferredencoding()
        if system_encoding.upper() != 'UTF-8':
            locale.setlocale(locale.LC_ALL, 'Chinese')
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)
    else:
        # 类Unix系统
        locale.setlocale(locale.LC_ALL, 'zh_CN.UTF-8')

def setup_logging():
    """配置日志系统"""
    # 创建一个处理器，写入文件
    file_handler = logging.FileHandler('nba_game.log', encoding='utf-8')
    
    # 创建一个处理器，输出到控制台
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # 设置日志格式
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 获取根日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # 清除现有的处理器
    logger.handlers.clear()
    
    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

class GameDataParser:
    """NBA比赛数据解析器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_play_by_play_data(self, pbp_data: Dict) -> pd.DataFrame:
        """
        获取比赛回合数据，并进行分析，添加更多用于球员表现分析的列。

        Args:
            pbp_data (Dict): 原始回合数据

        Returns:
            pd.DataFrame: 包含所有回合数据和分析指标的DataFrame
        """
        try:
            plays = pbp_data.get('game', {}).get('actions', [])
            if not plays:
                self.logger.warning("No plays found in the data")
                return pd.DataFrame()

            # 转换为DataFrame格式
            play_list = []
            for play in plays:
                play_dict = {
                    # 基本信息
                    'actionNumber': play.get('actionNumber'),
                    'period': play.get('period'),
                    'clock': play.get('clock'),
                    'timeActual': play.get('timeActual'),
                    'periodType': play.get('periodType'),

                    # 事件信息
                    'actionType': play.get('actionType'),
                    'subType': play.get('subType'),
                    'qualifiers': play.get('qualifiers'),
                    'description': play.get('description'),

                    # 球员和球队信息
                    'personId': play.get('personId'),
                    'teamId': play.get('teamId'),
                    'teamTricode': play.get('teamTricode'),

                    # 比分信息
                    'scoreHome': int(play.get('scoreHome', '0')),
                    'scoreAway': int(play.get('scoreAway', '0')),

                    # 额外信息
                    'isFieldGoal': play.get('isFieldGoal'),
                    'shotDistance': play.get('shotDistance'),
                    'shotResult': play.get('shotResult'),
                    'possession': play.get('possession'),
                    'x': play.get('x'),
                    'y': play.get('y'),
                    'area': play.get('area'),
                    'areaDetail': play.get('areaDetail'),
                    'side': play.get('side')
                }
                
                # 查找助攻者信息
                if play_dict['actionType'] in ['2pt', '3pt'] and play_dict['shotResult'] == 'Made':
                    description = str(play_dict['description']).lower()
                    if 'assist' in description:
                        start_index = description.find('(') + 1
                        end_index = description.find('ast)')
                        if start_index > 0 and end_index > 0 and end_index > start_index:
                            assist_info = description[start_index:end_index].strip()
                            parts = assist_info.split()
                            if len(parts) >= 2:
                                first_initial = parts[0][0]
                                last_initial = parts[-1][0]

                                # 在两队球员中查找助攻者
                                for team_type in ['homeTeam', 'awayTeam']:
                                    for player in pbp_data.get('game', {}).get(team_type, {}).get('players', []):
                                        if (player.get('firstName', '')[0].lower() == first_initial.lower() and 
                                            player.get('familyName', '')[0].lower() == last_initial.lower()):
                                            play_dict['assistPersonId'] = player.get('personId')
                                            break
                                    if 'assistPersonId' in play_dict:
                                        break
                
                play_list.append(play_dict)

            # 创建DataFrame并添加额外的分析列
            df = pd.DataFrame(play_list)
            
            if not df.empty:
                # 基本事件类型标记
                df['is_three_pointer'] = df['actionType'] == '3pt'
                df['is_two_pointer'] = df['actionType'] == '2pt'
                df['is_dunk'] = df['subType'] == 'DUNK'
                df['is_layup'] = df['subType'] == 'Layup'
                df['is_block'] = df['actionType'] == 'block'
                df['is_steal'] = df['actionType'] == 'steal'
                df['is_turnover'] = df['actionType'] == 'turnover'
                df['is_foul'] = df['actionType'] == 'foul'
                df['is_freethrow'] = df['actionType'] == 'freethrow'
                
                # 计算得分变化
                df['scoreDiff'] = df['scoreHome'] - df['scoreAway']
                
                # 标记是否为该节第一个回合
                if 'actionNumber' in df.columns:
                    df['is_first_action_of_period'] = df.groupby('period')['actionNumber'].transform('first') == df['actionNumber']
                
                self.logger.info(f"Successfully parsed {len(df)} plays")

            return df

        except Exception as e:
            self.logger.error(f"Error parsing play by play data: {str(e)}", exc_info=True)
            return pd.DataFrame()

def main():
    # 设置中文环境
    setup_chinese_env()
    
    # 设置日志
    logger = setup_logging()
    
    try:
        # 获取赛程数据
        schedule_fetcher = ScheduleFetcher()
        schedule_data = schedule_fetcher.get_schedule(force_update=False)
        
        if not schedule_data:
            logger.error("获取赛程数据失败")
            return
            
        # 解析赛程数据
        schedule_df = ScheduleParser.parse_raw_schedule(schedule_data)
        
        if schedule_df.empty:
            logger.error("解析赛程数据失败")
            return
            
        # 湖人队ID
        team_id = 1610612747
        
        # 获取最近一场比赛的ID
        last_game_id = ScheduleParser.get_last_game_id(schedule_df, team_id)
        if last_game_id:
            logger.info(f"\n最近比赛ID: {last_game_id}")
            
            game_fetcher = GameFetcher()
            playbyplay_data = game_fetcher.get_playbyplay(last_game_id)
            
            if playbyplay_data:
                game_parser = GameDataParser()
                plays_df = game_parser.get_play_by_play_data(playbyplay_data)
                
                if not plays_df.empty:
                    # 查看DataFrame的基本信息
                    logger.info("\nDataFrame信息:")
                    logger.info(f"数据形状: {plays_df.shape}")
                    logger.info("\n列名:")
                    logger.info(plays_df.columns.tolist())
                    
                    # 查看数据类型
                    logger.info("\n数据类型:")
                    for col, dtype in plays_df.dtypes.items():
                        logger.info(f"{col}: {dtype}")
                    
                    # 查看前几行数据
                    logger.info("\n前5行数据示例:")
                    logger.info(plays_df.head().to_string())
                    
                    # 保存原始数据到CSV便于查看
                    plays_df.to_csv('game_plays_full.csv', encoding='utf-8', index=False)
                    logger.info("\n完整数据已保存到 game_plays_full.csv")
                    
                    # 输出回合描述
                    logger.info("\n比赛回合数据:")
                    for _, play in plays_df.iterrows():
                        period = play['period']
                        clock = play['clock']
                        description = play['description']
                        logger.info(f"第{period}节 {clock}: {description}")
                else:
                    logger.error("解析回合数据失败")
            else:
                logger.error("获取回合数据失败")
        else:
            logger.info("\n没有找到过去的比赛")
               
    except Exception as e:
        logger.error(f"主函数执行错误: {e}", exc_info=True)

if __name__ == "__main__":
    import pandas as pd
    main()