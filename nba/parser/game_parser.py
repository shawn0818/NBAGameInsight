import logging
from typing import Dict, Optional, Any
from pydantic import ValidationError
from nba.models.game_model import Game
from nba.models.event_model import PlayByPlay, Event, EventType

class GameDataParser:
    """NBA比赛数据解析器"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def parse_game(self, data: Dict[str, Any]) -> Optional[Game]:
        """解析比赛数据"""
        try:
            # 验证和预处理数据
            if not self._validate_data(data, self._get_game_required_fields()):
                return None

            # 处理时间格式
            if 'game' in data:
                data['game'] = self._process_datetime_fields(data['game'])
                
            # 解析为Game对象
            game = Game.model_validate(data)
            
            # 验证解析后的数据
            if not self._post_validate_game(game):
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
        """解析比赛回放数据"""
        try:
            # 验证和预处理数据
            if not self._validate_data(data, self._get_playbyplay_required_fields()):
                return None

            # 处理时间格式
            data = self._process_playbyplay_data(data)
            
            # 解析为PlayByPlay对象
            playbyplay = PlayByPlay.model_validate(data)
            
            # 丰富事件信息
            enriched_actions = []
            for action in playbyplay.actions:
                if enriched_action := self._enrich_event(action):
                    enriched_actions.append(enriched_action)
            
            self.logger.info(f"Successfully parsed {len(enriched_actions)} play-by-play events")
            return playbyplay
            
        except ValidationError as ve:
            self.logger.error(f"PlayByPlay data validation error: {str(ve)}")
            return None
        except Exception as e:
            self.logger.error(f"Error parsing PlayByPlay data: {str(e)}")
            return None

    def _validate_data(self, data: Dict[str, Any], required_fields: Dict[str, set]) -> bool:
        """通用数据验证"""
        if not isinstance(data, dict):
            self.logger.error("Input data must be a dictionary")
            return False

        # 检查顶层字段
        for top_field, sub_fields in required_fields.items():
            if top_field not in data:
                self.logger.error(f"Missing required top-level key: {top_field}")
                return False
                
            # 检查子字段
            if sub_fields and not all(field in data[top_field] for field in sub_fields):
                self.logger.error(f"Missing required fields in {top_field}: {sub_fields}")
                return False
                
        return True

    @staticmethod
    def _get_game_required_fields() -> Dict[str, set]:
        """获取比赛数据必需字段"""
        return {
            'meta': set(),
            'game': {'gameId', 'gameTimeLocal', 'gameStatus', 'homeTeam', 'awayTeam'}
        }

    @staticmethod
    def _get_playbyplay_required_fields() -> Dict[str, set]:
        """获取回放数据必需字段"""
        return {
            'meta': set(),
            'game': {'gameId', 'actions'}
        }

    def _process_datetime_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理日期时间字段"""
        datetime_fields = [
            'gameTimeLocal', 'gameTimeUTC', 'gameTimeHome', 
            'gameTimeAway', 'gameEt'
        ]
        
        data = data.copy()
        for field in datetime_fields:
            if field in data and isinstance(data[field], str):
                data[field] = data[field].rstrip('Z') + '+00:00'
                
        return data

    def _process_playbyplay_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理回放数据的时间字段"""
        if 'game' not in data or 'actions' not in data['game']:
            return data
            
        data = data.copy()
        data['game'] = data['game'].copy()
        data['game']['actions'] = [
            self._process_action_time(action.copy()) 
            for action in data['game']['actions']
        ]
        return data

    def _process_action_time(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """处理单个动作的时间字段"""
        time_fields = ['timeActual', 'edited']
        for field in time_fields:
            if field in action and isinstance(action[field], str):
                action[field] = action[field].rstrip('Z') + '+00:00'
        return action

    def _enrich_event(self, event: Event) -> Optional[Event]:
        """丰富事件信息"""
        try:
            event = self._validate_event_type(event)
            event = self._process_coordinates(event)
            event = self._process_scores(event)
            return event
            
        except Exception as e:
            self.logger.error(f"Error enriching event: {str(e)}")
            return None

    def _validate_event_type(self, event: Event) -> Event:
        """验证事件类型"""
        if event.actionType:
            try:
                event_type = EventType(event.actionType)
                if event.subType and event_type:
                    valid_subtypes = EventType.get_valid_subtypes(event_type)
                    if valid_subtypes and event.subType not in valid_subtypes:
                        self.logger.warning(
                            f"Invalid subtype {event.subType} for event type {event_type}"
                        )
            except ValueError:
                self.logger.warning(f"Unknown event type: {event.actionType}")
        return event

    def _process_coordinates(self, event: Event) -> Event:
        """处理坐标信息"""
        if event.x is not None and event.y is not None:
            # 可以添加坐标验证或转换逻辑
            pass
        return event

    def _process_scores(self, event: Event) -> Event:
        """处理得分信息"""
        if event.scoreHome is not None and event.scoreAway is not None:
            try:
                event.scoreHome = int(event.scoreHome)
                event.scoreAway = int(event.scoreAway)
            except ValueError:
                self.logger.warning("Invalid score format")
        return event

    def _post_validate_game(self, game: Game) -> bool:
        """验证解析后的Game对象"""
        try:
            if not game.game.gameId:
                self.logger.error("Missing gameId")
                return False

            # 验证球队信息
            for team_type in ['homeTeam', 'awayTeam']:
                team = getattr(game.game, team_type)
                if not team.teamId or not team.teamName:
                    self.logger.error(f"Missing {team_type} information")
                    return False

            # 验证比分
            if game.game.gameStatus in [2, 3]:  # 进行中或结束
                if not isinstance(game.game.homeTeam.score, int) or \
                   not isinstance(game.game.awayTeam.score, int):
                    self.logger.error("Invalid score data")
                    return False

            return True
            
        except Exception as e:
            self.logger.error(f"Error validating game: {str(e)}")
            return False