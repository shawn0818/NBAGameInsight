import logging
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import ValidationError

from nba.models.game_model import (
    Game, GameData, GameStatusEnum, Arena, Official, PeriodScore,
    Player, TeamStats, BaseEvent, PlayByPlay,
    PeriodEvent, JumpBallEvent, TwoPointEvent, ThreePointEvent,
    FreeThrowEvent, ReboundEvent, StealEvent, BlockEvent, FoulEvent,
    AssistEvent, TurnoverEvent, SubstitutionEvent, TimeoutEvent, ViolationEvent,
    ShotEvent, GameEvent
)
from utils.time_handler import TimeParser, NBATimeHandler, BasketballGameTime


class GameDataParser:
    """NBA比赛数据解析器"""

    EVENT_TYPE_MAP = {
        "period": PeriodEvent,
        "jumpball": JumpBallEvent,
        "2pt": TwoPointEvent,
        "3pt": ThreePointEvent,
        "freethrow": FreeThrowEvent,
        "rebound": ReboundEvent,
        "steal": StealEvent,
        "block": BlockEvent,
        "foul": FoulEvent,
        "assist": AssistEvent,
        "turnover": TurnoverEvent,
        "violation": ViolationEvent,
        "timeout": TimeoutEvent,
        "substitution": SubstitutionEvent,
        "game": GameEvent
    }

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def _parse_datetime(self, datetime_str: str) -> datetime:
        """
        解析ISO格式的时间字符串

        Args:
            datetime_str: ISO格式的时间字符串

        Returns:
            datetime: 解析后的datetime对象

        Raises:
            ValueError: 时间格式无效时抛出
        """
        try:
            return TimeParser.parse_iso8601_datetime(datetime_str)
        except Exception as e:
            raise ValueError(f"Invalid datetime format: {datetime_str}") from e


    def _parse_game_clock(self, clock_str: str) -> float:
        """
        解析比赛时钟时间为秒数

        Args:
            clock_str: 时钟时间字符串（格式：PT{minutes}M{seconds}S）

        Returns:
            float: 转换后的秒数

        Raises:
            ValueError: 时钟格式无效时抛出
        """
        try:
            return TimeParser.parse_iso8601_duration(clock_str)
        except Exception as e:
            raise ValueError(f"Error parsing game clock: {clock_str}") from e

    def parse_game_data(self, data: Dict[str, Any]) -> Optional[Game]:
        """解析完整比赛数据"""
        try:
            if not isinstance(data, dict):
                raise ValueError("Invalid game data format")

            # 处理比赛基本信息
            game_data = self._process_game_data(data)
            self.logger.debug("成功处理比赛基本信息")

            # 创建Game实例
            game = Game(
                meta=data.get('meta', {}),
                game=game_data,
                playByPlay=None  # 初始化为None，后续处理
            )

            # 解析回放数据（如果存在）
            if 'playByPlay' in data:
                self.logger.debug("开始解析回放数据")
                play_by_play = self._parse_playbyplay(data['playByPlay'])
                if play_by_play:
                    self.logger.debug(f"成功解析回放数据，共 {len(play_by_play.actions)} 个事件")
                    game.playByPlay = play_by_play
                else:
                    self.logger.warning("回放数据解析失败")

            return game

        except Exception as e:
            self.logger.error(f"解析比赛数据时出错: {e}")
            return None

    def _process_game_data(self, game_data: Dict[str, Any]) -> GameData:
        """
        处理比赛基础信息

        Args:
            game_data: 比赛基础数据字典

        Returns:
            GameData: 处理后的比赛数据对象
        """
        try:
            # 处理嵌套的数据结构
            if 'meta' in game_data and 'game' in game_data:
                data = game_data['game']
            else:
                data = game_data

            # 处理比赛状态
            if 'gameStatus' in data:
                status_value = data['gameStatus']
                if isinstance(status_value, int):
                    data['gameStatus'] = GameStatusEnum(status_value)
                else:
                    data['gameStatus'] = GameStatusEnum.NOT_STARTED
            else:
                data['gameStatus'] = GameStatusEnum.NOT_STARTED

            # 从data中提取并删除team数据，避免重复
            home_team_data = data.pop('homeTeam', {})
            away_team_data = data.pop('awayTeam', {})

            # 处理球队数据
            home_team = self._process_team_stats(home_team_data)
            away_team = self._process_team_stats(away_team_data)

            # 日期时间处理
            for time_field in ['gameTimeLocal', 'gameTimeUTC', 'gameTimeHome', 'gameTimeAway', 'gameEt']:
                if time_field in data and isinstance(data[time_field], str):
                    data[time_field] = self._parse_datetime(data[time_field])

            # 处理场馆信息
            if 'arena' in data:
                data['arena'] = Arena(**data['arena'])
            else:
                data['arena'] = Arena()

            # 处理裁判信息
            if 'officials' in data and isinstance(data['officials'], list):
                data['officials'] = [Official(**official) for official in data['officials']]

            # 创建 GameData 实例
            return GameData(
                **data,
                homeTeam=home_team,
                awayTeam=away_team
            )

        except Exception as e:
            self.logger.error(f"处理比赛数据时出错: {str(e)}", exc_info=True)
            # 返回最小可用的游戏数据
            return GameData(
                homeTeam=self._process_team_stats({}),
                awayTeam=self._process_team_stats({})
            )

    def _process_team_stats(self, team_data: Dict[str, Any]) -> TeamStats:
        """处理球队统计数据"""
        try:
            if not team_data:
                return TeamStats(
                    teamId=0,
                    teamName="Unknown",
                    teamCity="Unknown",
                    teamTricode="UNK",
                    score=0,
                    inBonus="0",
                    timeoutsRemaining=0
                )

            # 处理每节比分
            if 'periods' in team_data:
                processed_periods = []
                for period_data in team_data['periods']:
                    try:
                        period_score = PeriodScore(
                            period=period_data['period'],
                            periodType=period_data['periodType'],
                            score=period_data['score']
                        )
                        processed_periods.append(period_score)
                    except Exception as e:
                        self.logger.error(f"处理节次数据时出错: {str(e)}")
                        continue
                team_data['periods'] = processed_periods

            # 处理球员数据
            if 'players' in team_data:
                processed_players = []
                for player in team_data['players']:
                    try:
                        # 基础数据确认
                        if 'statistics' not in player:
                            player['statistics'] = {}

                        # 处理球员状态相关字段
                        self._process_player_status(player)

                        processed_players.append(Player(**player))
                    except Exception as e:
                        self.logger.error(f"处理球员数据时出错: {str(e)}")
                        continue

                team_data['players'] = processed_players

            return TeamStats(**team_data)

        except Exception as e:
            self.logger.error(f"处理球队统计数据时出错: {str(e)}")
            raise

    def _process_player_status(self, player: Dict[str, Any]) -> None:
        """处理球员状态相关字段"""
        # 检查并设置状态字段
        if 'status' not in player:
            player['status'] = 'INACTIVE' if player.get('notPlayingReason') else 'ACTIVE'

        # 检查并设置场上状态
        if 'oncourt' not in player:
            is_active = player['status'] == 'ACTIVE'
            no_injury = not player.get('notPlayingReason')
            player['oncourt'] = '1' if is_active and no_injury else '0'

        # 检查并设置参赛状态
        if 'played' not in player:
            minutes = player.get('statistics', {}).get('minutes', 'PT00M00.00S')
            player['played'] = '1' if minutes != 'PT00M00.00S' else '0'

        # 确保描述字段存在
        if 'notPlayingReason' not in player:
            player['notPlayingReason'] = None
        if 'notPlayingDescription' not in player:
            player['notPlayingDescription'] = None

    def _process_event(self, event_data: Dict[str, Any]) -> Optional[BaseEvent]:
        """处理单个事件数据"""
        try:
            if 'actionType' not in event_data:
                return None

            event_type = event_data['actionType']

            # 处理团队失误事件
            if event_type == 'turnover' and event_data.get('qualifiers', []) == ['team']:
                # 为团队失误添加必要字段
                event_data.update({
                    'playerName': 'TEAM',
                    'playerNameI': 'TEAM',
                    'turnoverTotal': 1
                })
                return TurnoverEvent(**event_data)

            # 处理团队篮板事件（包括deadball情况）
            elif event_type == 'rebound' and 'team' in event_data.get('qualifiers', []):
                # 为团队篮板添加必要字段
                event_data.update({
                    'playerName': 'TEAM',
                    'playerNameI': 'TEAM',
                    'reboundTotal': 1,
                    'reboundDefensiveTotal': 1 if event_data['subType'] == 'defensive' else 0,
                    'reboundOffensiveTotal': 1 if event_data['subType'] == 'offensive' else 0
                })
                return ReboundEvent(**event_data)

            # ... 其他现有的事件处理代码保持不变 ...

            # 处理换人事件
            elif event_type == 'substitution':
                # 根据 subType 设置进出场球员信息
                if event_data['subType'] == 'out':
                    event_data.update({
                        'incomingPlayerName': event_data['playerName'],
                        'incomingPlayerNameI': event_data['playerNameI'],
                        'incomingPersonId': event_data['personId'],
                        'outgoingPlayerName': event_data['playerName'],
                        'outgoingPlayerNameI': event_data['playerNameI'],
                        'outgoingPersonId': event_data['personId']
                    })
                else:  # subType == 'in'
                    event_data.update({
                        'incomingPlayerName': event_data['playerName'],
                        'incomingPlayerNameI': event_data['playerNameI'],
                        'incomingPersonId': event_data['personId'],
                        'outgoingPlayerName': event_data['playerName'],
                        'outgoingPlayerNameI': event_data['playerNameI'],
                        'outgoingPersonId': event_data['personId']
                    })
                return SubstitutionEvent(**event_data)

            # 处理投篮事件
            elif event_type in ['2pt', '3pt']:
                if 'shotResult' not in event_data:
                    event_data['shotResult'] = (
                        'Made' if 'pointsTotal' in event_data else 'Missed'
                    )
                return ShotEvent(**event_data)

            # 处理抢断事件
            elif event_type == 'steal':
                if 'subType' not in event_data:
                    event_data['subType'] = ""
                return StealEvent(**event_data)

            # 处理失误事件
            elif event_type == 'turnover':
                if 'stealPlayerName' in event_data:
                    event_data['stealPersonId'] = event_data.get('stealPersonId')
                if 'turnoverTotal' not in event_data:
                    event_data['turnoverTotal'] = 1
                return TurnoverEvent(**event_data)

            # 处理篮板事件
            elif event_type == 'rebound':
                if 'shotActionNumber' not in event_data:
                    event_data['shotActionNumber'] = None
                return ReboundEvent(**event_data)

            # 其他事件类型
            event_class = self.EVENT_TYPE_MAP.get(event_type)
            if not event_class:
                self.logger.warning(f"未知事件类型: {event_type}")
                return BaseEvent(**event_data)

            return event_class(**event_data)

        except ValidationError as ve:
            self.logger.error(f"事件数据验证错误: {ve.errors()}")
            return None
        except Exception as e:
            self.logger.error(f"处理事件时出错: {str(e)}")
            return None


    def _parse_playbyplay(self, data: Dict[str, Any]) -> Optional[PlayByPlay]:
        """解析比赛回放数据"""
        try:
            # 添加更详细的日志
            self.logger.debug(f"开始解析回放数据: {data.keys() if data else None}")

            if not data:
                self.logger.warning("回放数据为空")
                return None

            if 'game' not in data:
                self.logger.warning("回放数据中缺少 'game' 字段")
                return None

            # 检查actions的位置
            actions_data = None
            if 'actions' in data:
                actions_data = data['actions']
                self.logger.debug("从根级别找到actions")
            elif 'actions' in data.get('game', {}):
                actions_data = data['game']['actions']
                self.logger.debug("从game字段中找到actions")

            if not actions_data:
                self.logger.warning("未找到有效的actions数据")
                return None

            actions = []
            for action_data in actions_data:
                try:
                    event = self._process_event(action_data)
                    if event:
                        actions.append(event)
                except Exception as e:
                    self.logger.error(f"处理事件时出错: {e}, 事件数据: {action_data}")
                    continue

            self.logger.info(f"成功解析 {len(actions)} 个事件")

            # 创建PlayByPlay对象
            play_by_play = PlayByPlay(
                game=data.get('game', {}),
                meta=data.get('meta'),
                actions=actions
            )

            self.logger.debug(f"成功创建PlayByPlay对象，包含 {len(play_by_play.actions)} 个事件")
            return play_by_play

        except Exception as e:
            self.logger.error(f"解析回放数据时出错: {e}")
            return None

