import logging
from typing import Dict, Optional, Any, List, Type
from pydantic import ValidationError
from nba.models.game_model import Game, PlayByPlay, BaseEvent, CourtPosition, EventCategory, StealEvent, BlockEvent


class GameDataParser:
    """NBA比赛数据解析器"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def parse_game_data(self, data: Dict[str, Any]) -> Optional[Game]:
        """解析BoxScore数据"""
        try:
            game = Game(**data)
            return game
        except ValidationError as ve:
            self.logger.error(f"比赛数据验证错误: {ve}")
            return None
        except Exception as e:
            self.logger.error(f"解析比赛数据时出错: {e}")
            return None

    def parse_playbyplay_data(self, data: Dict[str, Any]) -> Optional[PlayByPlay]:
        """解析PlayByPlay数据"""
        try:
            playbyplay = PlayByPlay(**data)
            self.logger.info(f"成功解析 {len(playbyplay.actions_parsed)} 个比赛事件")
            return playbyplay
        except ValidationError as ve:
            self.logger.error(f"回放数据验证错误: {ve}")
            return None
        except Exception as e:
            self.logger.error(f"解析回放数据时出错: {e}")
            return None

    def parse_actions(self, actions: List[Dict[str, Any]]) -> List[BaseEvent]:
        parsed_events = []
        errors = []
        
        for action in actions:
            try:
                parsed_event = self._parse_single_action(action)
                if parsed_event:
                    parsed_events.append(parsed_event)
            except Exception as e:
                errors.append({
                    'action': action,
                    'error': str(e)
                })
                self.logger.error(f"解析事件失败: {e}")
                continue
        
        if errors:
            self._report_parsing_errors(errors)
            
        return parsed_events

    def _parse_single_action(self, action: Dict[str, Any]) -> Optional[BaseEvent]:
        """解析单个事件"""
        try:
            # 1. 处理坐标数据
            position = None
            if any(key in action for key in ['x', 'y', 'area', 'areaDetail', 'side']):
                position = CourtPosition(
                    x=action.get('x'),
                    y=action.get('y'),
                    area=action.get('area'),
                    areaDetail=action.get('areaDetail'),
                    side=action.get('side'),
                    xLegacy=action.get('xLegacy'),
                    yLegacy=action.get('yLegacy')
                )
            
            # 2. 根据事件类型选择对应的事件模型
            event_type = action.get('actionType')
            event_class = self._get_event_class(event_type)
            
            # 3. 创建事件实例
            event_data = {**action}
            if position:
                event_data['position'] = position
            
            return event_class(**event_data)
            
        except Exception as e:
            self.logger.error(f"解析事件失败: {e}, 事件: {action}")
            return None
    
    def _get_event_class(self, event_type: str) -> Type[BaseEvent]:
        """获取事件类型对应的模型类"""
        event_map = {
            EventCategory.STEAL: StealEvent,
            EventCategory.BLOCK: BlockEvent,
            # ... 其他事件类型映射
        }
        return event_map.get(event_type, BaseEvent)

    def _validate_and_clean_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """验证和清洗单个事件数据"""
        # 移除空值
        action = {k: v for k, v in action.items() if v is not None}
        
        # 标准化字段
        if 'clock' in action:
            action['clock'] = self._standardize_clock(action['clock'])
            
        return action

    def _standardize_clock(self, clock_str: str) -> str:
        """标准化时间格式"""
        # 实现时间格式标准化
        pass

    def parse_playbyplay(self, playbyplay: PlayByPlay) -> List[Dict[str, Any]]:
        """解析比赛回放数据"""
        try:
            if not playbyplay:
                return []

            parsed_plays = []
            for action in playbyplay.game['actions']:
                # 只处理得分相关的事件
                if not self._is_scoring_play(action):
                    continue

                # 解析得分事件
                play = {
                    'period': action.get('period'),
                    'time': action.get('clock', ''),
                    'description': action.get('description', ''),
                    'team': action.get('teamTricode', ''),
                    'player': action.get('playerNameI', ''),
                    'score_diff': self._calculate_score_diff(action),
                    'qualifiers': action.get('qualifiers', []),
                    'scoreHome': action.get('scoreHome'),
                    'scoreAway': action.get('scoreAway')
                }
                parsed_plays.append(play)

            # 按时间顺序排序
            return sorted(parsed_plays, key=lambda x: (x['period'], x['time'], -x.get('score_diff', 0)))

        except Exception as e:
            self.logger.error(f"解析比赛回放数据时出错: {e}")
            return []

    def _is_scoring_play(self, action: Dict[str, Any]) -> bool:
        """判断是否为得分事件"""
        if not action.get('description'):
            return False
        
        description = action['description'].upper()
        # 排除失败的投篮
        if 'MISS' in description:
            return False
        # 包含得分的事件
        return any(keyword in description for keyword in [
            'MADE', 'MAKES', 'FREE THROW', 'DUNK', 'LAYUP', 'HOOK'
        ])

    def _calculate_score_diff(self, action: Dict[str, Any]) -> int:
        """计算得分差值"""
        try:
            home_score = int(action.get('scoreHome', 0))
            away_score = int(action.get('scoreAway', 0))
            return home_score - away_score
        except (TypeError, ValueError):
            return 0

    def extract_scoring_plays(
        self, 
        plays: List[Dict[str, Any]], 
        player_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """提取得分事件"""
        try:
            if not plays:
                return []

            # 如果指定了球员ID，只返回该球员的得分事件
            if player_id:
                return [
                    play for play in plays 
                    if play.get('personId') == player_id
                ]

            return plays

        except Exception as e:
            self.logger.error(f"提取得分事件时出错: {e}")
            return []