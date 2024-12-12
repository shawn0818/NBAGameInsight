import pandas as pd
from typing import Dict, Optional
import logging
from datetime import datetime
from utils.time_helper import TimeConverter

class GameDataParser:
    """NBA比赛数据解析器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_game_basic_info(self, boxscore_data: Dict) -> Optional[Dict]:
        """
        获取比赛基本信息
        
        Args:
            boxscore_data (Dict): 比赛数据
            
        Returns:
            Optional[Dict]: 比赛基本信息
        """
        try:
            game = boxscore_data.get('game', {})
            if not game:
                return None

            # 比赛场地信息
            arena_info = {
                'arena': game.get('arena'),
                'arenaCity': game.get('arenaCity'),
                'arenaState': game.get('arenaState'),
                'arenaCountry': game.get('arenaCountry'),
                'capacity': game.get('arenaCapacity')
            }
            
            # 比赛时间信息
            game_time_utc = game.get('gameTimeUTC')
            game_time_info = {
                'gameTimeUTC': game_time_utc,
                'gameTimeLocal': TimeConverter.to_beijing_time(
                    datetime.strptime(game_time_utc, '%Y-%m-%dT%H:%M:%SZ')
                ) if game_time_utc else None,
                'dayNumber': game.get('dayNumber'),  # 赛季第几天
                'seasonYear': game.get('seasonYear'),
                'seasonType': game.get('seasonType')  # 常规赛/季后赛
            }
            
            # 转播信息
            broadcast_info = {
                'broadcasters': game.get('broadcasters', []),
                'nationalBroadcast': game.get('nationalBroadcast', False)
            }
            
            # 主队信息
            home_team = game.get('homeTeam', {})
            home_team_info = {
                'teamId': home_team.get('teamId'),
                'teamName': home_team.get('teamName'),
                'teamCity': home_team.get('teamCity'),
                'teamTricode': home_team.get('teamTricode'),
                'teamSlug': home_team.get('teamSlug'),
                'wins': home_team.get('wins'),
                'losses': home_team.get('losses'),
                'score': home_team.get('score'),
                'seed': home_team.get('seed')
            }
            
            # 客队信息
            away_team = game.get('awayTeam', {})
            away_team_info = {
                'teamId': away_team.get('teamId'),
                'teamName': away_team.get('teamName'),
                'teamCity': away_team.get('teamCity'),
                'teamTricode': away_team.get('teamTricode'),
                'teamSlug': away_team.get('teamSlug'),
                'wins': away_team.get('wins'),
                'losses': away_team.get('losses'),
                'score': away_team.get('score'),
                'seed': away_team.get('seed')
            }
            
            return {
                'gameId': game.get('gameId'),
                'arena': arena_info,
                'gameTime': game_time_info,
                'broadcast': broadcast_info,
                'homeTeam': home_team_info,
                'awayTeam': away_team_info
            }
            
        except Exception as e:
            self.logger.error(f"Error parsing game basic info: {e}")
            return None

    def get_game_live_status(self, boxscore_data: Dict) -> Dict:
        """
        获取比赛实时状态
        
        Args:
            boxscore_data (Dict): 比赛数据
            
        Returns:
            Dict: 比赛实时状态
        """
        game = boxscore_data.get('game', {})
        
        # 比赛阶段信息
        period_info = {
            'period': game.get('period'),
            'periodType': game.get('periodType'),  # REGULAR/OVERTIME
            'gameClock': game.get('gameClock'),
            'gameClockDisplay': game.get('gameClockDisplay'),
            'isHalftime': game.get('isHalftime', False),
            'isEndOfPeriod': game.get('isEndOfPeriod', False)
        }
        
        # 比赛状态信息
        game_status = {
            'gameStatus': game.get('gameStatus'),
            'gameStatusText': game.get('gameStatusText'),
            'regulationPeriods': game.get('regulationPeriods', 4),
            'hasGameStarted': game.get('hasGameStarted', False),
            'isGameActivated': game.get('isGameActivated', False),
            'gameDuration': game.get('gameDuration')
        }
        
        # 主队实时信息
        home_team = game.get('homeTeam', {})
        home_status = {
            'score': home_team.get('score'),
            'timeoutsRemaining': home_team.get('timeoutsRemaining'),
            'foulsToGive': home_team.get('foulsToGive'),
            'inBonus': home_team.get('inBonus', False),
            'pointsInPaint': home_team.get('pointsInPaint'),
            'biggestLead': home_team.get('biggestLead'),
            'fastBreakPoints': home_team.get('fastBreakPoints'),
            'secondChancePoints': home_team.get('secondChancePoints')
        }
        
        # 客队实时信息
        away_team = game.get('awayTeam', {})
        away_status = {
            'score': away_team.get('score'),
            'timeoutsRemaining': away_team.get('timeoutsRemaining'),
            'foulsToGive': away_team.get('foulsToGive'),
            'inBonus': away_team.get('inBonus', False),
            'pointsInPaint': away_team.get('pointsInPaint'),
            'biggestLead': away_team.get('biggestLead'),
            'fastBreakPoints': away_team.get('fastBreakPoints'),
            'secondChancePoints': away_team.get('secondChancePoints')
        }
        
        return {
            'period': period_info,
            'gameStatus': game_status,
            'homeTeam': home_status,
            'awayTeam': away_status,
            'leadChanges': game.get('leadChanges'),
            'timesTied': game.get('timesTied')
        }



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
                # 转换时间到北京时间
                utc_time = play.get('timeActual')
                beijing_time = TimeConverter.to_beijing_time(utc_time) if utc_time else None
                
                play_dict = {
                    # 基本信息
                    'actionNumber': play.get('actionNumber'),
                    'period': play.get('period'),
                    'clock': play.get('clock'),
                    'timeActual': utc_time,  # 保留原始UTC时间
                    'timeBeijing': beijing_time,  # 添加北京时间
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
            self.logger.error(f"Error parsing play by play data: {str(e)}")
            return pd.DataFrame()