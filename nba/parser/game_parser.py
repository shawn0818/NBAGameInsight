import logging
from typing import Dict, Optional
from pydantic import ValidationError
from nba.models.game_model import Game
from nba.models.event_model import Event, PlayByPlay

class GameDataParser:
    """
    负责将原始JSON数据解析成Game模型对象
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def parse_game(self, data: Dict) -> Optional[Game]:
        """
        解析比赛数据

        Args:
            data (Dict): 从API获取的原始JSON数据

        Returns:
            Optional[Game]: 包含解析后的比赛数据，解析失败时返回None
        """
        try:
            game = Game.parse_obj(data)
            self.logger.debug(f"成功解析比赛数据，比赛ID: {game.game_id}")

            # 解析 playbyplay 数据
            playbyplay_data = data.get('playbyplay')
            if playbyplay_data:
                playbyplay = self.parse_playbyplay(playbyplay_data)
                game.playbyplay = playbyplay

            return game
        except ValidationError as ve:
            self.logger.error(f"数据验证错误: {ve}")
            return None
        except Exception as e:
            self.logger.error(f"解析比赛数据时出错: {e}")
            return None

    def parse_playbyplay(self, data: Dict) -> Optional[PlayByPlay]:
        """
        解析比赛回放数据

        Args:
            data (Dict): 从API获取的原始JSON数据

        Returns:
            Optional[GameEventCollection]: 包含解析后的回放数据，解析失败时返回None
        """
        try:
            playbyplay = GameEventCollection.parse_obj(data)
            self.logger.debug(f"成功解析回放数据，比赛ID: {playbyplay.game_id}")
            return playbyplay
        except ValidationError as ve:
            self.logger.error(f"回放数据验证错误: {ve}")
            return None
        except Exception as e:
            self.logger.error(f"解析回放数据时出错: {e}")
            return None
