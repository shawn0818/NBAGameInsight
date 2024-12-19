import logging
from typing import Dict, Optional, Any, Tuple
from datetime import datetime
from pydantic import ValidationError
from nba.models.game_model import Game
from nba.models.event_model import PlayByPlay, Event, EventType

class GameDataParser:
    """NBA比赛数据解析器 - 负责将原始JSON数据解析成规范的数据模型对象"""

    def __init__(self):
        """初始化解析器"""
        self.logger = logging.getLogger(self.__class__.__name__)

    def parse_game(self, data: Dict[str, Any]) -> Optional[Game]:
        """
        解析比赛数据为Game模型对象

        Args:
            data: 从API获取的原始JSON数据

        Returns:
            Optional[Game]: 解析后的比赛数据，解析失败时返回None
        """
        try:
            # 预处理数据
            if not self._validate_raw_game_data(data):
                return None

            # 处理时间格式
            if 'game' in data:
                self._preprocess_datetime_fields(data['game'])
                
            # 使用Pydantic模型解析数据
            game = Game.model_validate(data)
            
            # 验证解析后的数据
            if not self._validate_parsed_game(game):
                return None
                
            self.logger.info(f"Successfully parsed game data for game {game.game.gameId}")
            return game
            
        except ValidationError as ve:
            self.logger.error(f"Game data validation error: {str(ve)}")
            return None
        except Exception as e:
            self.logger.error(f"Error parsing game data: {str(e)}")
            return None

    def parse_playbyplay(self, data: Dict[str, Any]) -> Optional[PlayByPlay]:
        """
        解析比赛回放数据为PlayByPlay模型对象

        Args:
            data: 从API获取的原始JSON数据

        Returns:
            Optional[PlayByPlay]: 解析后的回放数据，解析失败时返回None
        """
        try:
            # 验证原始数据结构
            if not self._validate_raw_playbyplay_data(data):
                return None

            # 预处理时间格式
            self._preprocess_playbyplay_data(data)
            
            # 解析为PlayByPlay模型
            playbyplay = PlayByPlay.model_validate(data)
            
            # 验证并丰富事件信息
            enriched_actions = []
            for action in playbyplay.actions:
                if enriched_action := self._enrich_event(action):
                    enriched_actions.append(enriched_action)
            
            # 记录解析信息
            action_count = len(enriched_actions)
            self.logger.info(f"Successfully parsed {action_count} play-by-play events")
            
            return playbyplay
            
        except ValidationError as ve:
            self.logger.error(f"PlayByPlay data validation error: {str(ve)}")
            return None
        except Exception as e:
            self.logger.error(f"Error parsing PlayByPlay data: {str(e)}")
            return None

    def _validate_raw_game_data(self, data: Dict[str, Any]) -> bool:
        """验证原始比赛数据的基本结构"""
        if not isinstance(data, dict):
            self.logger.error("Input data must be a dictionary")
            return False
            
        if 'meta' not in data or 'game' not in data:
            self.logger.error("Missing required top-level keys: 'meta' and 'game'")
            return False
            
        required_game_fields = {
            'gameId', 'gameTimeLocal', 'gameStatus', 
            'homeTeam', 'awayTeam'
        }
        
        if not all(field in data['game'] for field in required_game_fields):
            self.logger.error(f"Missing required game fields: {required_game_fields}")
            return False
            
        return True

    def _validate_raw_playbyplay_data(self, data: Dict[str, Any]) -> bool:
        """验证原始回放数据的基本结构"""
        if not isinstance(data, dict):
            self.logger.error("Input data must be a dictionary")
            return False
            
        if 'meta' not in data or 'game' not in data:
            self.logger.error("Missing required top-level keys in PlayByPlay data")
            return False
            
        if 'gameId' not in data['game'] or 'actions' not in data['game']:
            self.logger.error("Missing required game fields in PlayByPlay data")
            return False
            
        if not isinstance(data['game']['actions'], list):
            self.logger.error("Actions must be a list")
            return False
            
        return True

    def _preprocess_datetime_fields(self, game_data: Dict[str, Any]) -> None:
        """处理比赛数据中的日期时间字段"""
        datetime_fields = [
            'gameTimeLocal', 'gameTimeUTC', 'gameTimeHome', 
            'gameTimeAway', 'gameEt'
        ]
        
        for field in datetime_fields:
            if field in game_data and isinstance(game_data[field], str):
                if game_data[field].endswith('Z'):
                    game_data[field] = game_data[field].replace('Z', '+00:00')

    def _preprocess_playbyplay_data(self, data: Dict[str, Any]) -> None:
        """预处理回放数据"""
        if 'game' not in data or 'actions' not in data['game']:
            return
            
        for action in data['game']['actions']:
            # 处理时间字段
            if 'timeActual' in action and isinstance(action['timeActual'], str):
                if action['timeActual'].endswith('Z'):
                    action['timeActual'] = action['timeActual'].replace('Z', '+00:00')
                    
            if 'edited' in action and isinstance(action['edited'], str):
                if action['edited'].endswith('Z'):
                    action['edited'] = action['edited'].replace('Z', '+00:00')

    def _enrich_event(self, event: Event) -> Optional[Event]:
        """丰富事件信息，添加额外的验证和处理逻辑"""
        try:
            # 验证事件类型
            if event.actionType:
                try:
                    event_type = EventType(event.actionType)
                    
                    # 验证子类型是否有效
                    if event.subType and event_type:
                        valid_subtypes = EventType.get_valid_subtypes(event_type)
                        if valid_subtypes and event.subType not in valid_subtypes:
                            self.logger.warning(f"Invalid subtype {event.subType} for event type {event_type}")
                            
                except ValueError:
                    self.logger.warning(f"Unknown event type: {event.actionType}")

            # 处理坐标信息
            if event.x is not None and event.y is not None:
                # 可以添加坐标验证或转换逻辑
                pass
                
            # 处理得分信息
            if event.scoreHome is not None and event.scoreAway is not None:
                try:
                    event.scoreHome = int(event.scoreHome)
                    event.scoreAway = int(event.scoreAway)
                except ValueError:
                    self.logger.warning("Invalid score format")

            return event
            
        except Exception as e:
            self.logger.error(f"Error enriching event: {str(e)}")
            return None

    def _validate_parsed_game(self, game: Game) -> bool:
        """验证解析后的Game对象"""
        try:
            # 基本比赛信息验证
            if not game.game.gameId:
                self.logger.error("Missing gameId")
                return False
                
            # 球队信息验证
            for team_type in ['homeTeam', 'awayTeam']:
                team = getattr(game.game, team_type)
                if not team.teamId or not team.teamName:
                    self.logger.error(f"Missing {team_type} information")
                    return False
                    
            # 比分验证
            if game.game.gameStatus in [2, 3]:  # 进行中或结束
                if not isinstance(game.game.homeTeam.score, int) or \
                   not isinstance(game.game.awayTeam.score, int):
                    self.logger.error("Invalid score data")
                    return False
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating game: {str(e)}")
            return False