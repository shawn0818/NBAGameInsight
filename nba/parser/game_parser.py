from typing import Optional, Dict, Any, Union
from datetime import datetime
import re
from pydantic import ValidationError
from nba.fetcher.game_fetcher import GameDataResponse
from nba.models.game_model import (
    Game, GameData, GameStatusEnum, Arena, Official, PeriodScore,
    PlayerInGame, TeamInGame, BaseEvent, PlayByPlay,
    PeriodEvent, JumpBallEvent, TwoPointEvent, ThreePointEvent,
    FreeThrowEvent, ReboundEvent, StealEvent, BlockEvent, FoulEvent,
    AssistEvent, TurnoverEvent, SubstitutionEvent, TimeoutEvent, ViolationEvent,
    ShotEvent, GameEvent, TeamStatistics, PlayerStatistics, EjectionEvent,
    TeamRivalryInfo  # 添加对新模型的引用
)
from utils.logger_handler import AppLogger


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
        "ejection": EjectionEvent,
        "game": GameEvent
    }

    def __init__(self):
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def parse_game_data(self, data: Union[Dict[str, Any], GameDataResponse]) -> Optional[Game]:
        """解析完整比赛数据

        Args:
            data: 可以是原始的字典数据，也可以是 GameDataResponse 对象

        Returns:
            Optional[Game]: 解析后的 Game 对象，解析失败则返回 None
        """
        try:
            # 1. 处理 GameDataResponse 类型
            if isinstance(data, GameDataResponse):
                processed_data = {
                    'meta': {},  # 元数据，可以为空字典
                    'game': data.boxscore,  # boxscore 作为 game 数据
                }

                # 1.1 处理对抗历史信息
                if data.boxscore_summary:
                    self._parse_rivalry_info(data.boxscore_summary, processed_data['game'])
            else:
                # 2. 处理字典类型数据
                if not isinstance(data, dict):
                    self.logger.error(f"数据类型错误: {type(data)}")
                    raise ValueError("Invalid game data output_format")

                processed_data = data

                # 3. 处理缓存数据
                if 'timestamp' in processed_data and 'data' in processed_data:
                    processed_data = processed_data['data']

            # 4. 处理比赛基本信息
            game_data = self._process_game_data(processed_data)

            # 5. 创建 Game 实例（保证符合 model 要求）
            game = Game(
                meta=processed_data.get('meta', {}),
                gameData=game_data,
                playByPlay=None  # 初始设置为 None
            )

            # 6. 处理回放数据
            if isinstance(data, GameDataResponse):
                # 如果是 GameDataResponse，直接使用 playbyplay 属性
                if data.playbyplay:
                    play_by_play = self._parse_playbyplay({'game': data.playbyplay})
                    if play_by_play:
                        game.play_by_play = play_by_play
                        self.logger.debug("成功解析回放数据")
            else:
                # 如果是字典类型，检查 playByPlay 字段
                if 'playByPlay' in processed_data:
                    play_by_play = self._parse_playbyplay(processed_data)
                    if play_by_play:
                        game.playByPlay = play_by_play
                        self.logger.debug("成功解析回放数据")

            return game

        except Exception as e:
            self.logger.error(f"解析比赛数据时出错: {str(e)}", exc_info=True)
            return None

    def _parse_date_safely(self, date_str, default_value=None):
        """安全解析多种格式的日期字符串

        Args:
            date_str: 日期字符串
            default_value: 解析失败时的默认值

        Returns:
            datetime: 解析后的日期时间对象
        """
        if not date_str:
            return default_value or datetime.now()

        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except ValueError as e:
            self.logger.debug(f"日期不是ISO格式: {e}")
            try:
                return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
            except ValueError as e:
                self.logger.warning(f"无法解析日期 '{date_str}': {e}，使用默认值")
                return default_value or datetime.now()

    def _convert_field_name(self, field_name, prefix_to_remove=None):
        """转换字段名称，从snake_case到camelCase

        Args:
            field_name: 输入的字段名
            prefix_to_remove: 需要移除的前缀

        Returns:
            str: 转换后的字段名
        """
        if prefix_to_remove and field_name.startswith(prefix_to_remove):
            field_name = field_name.replace(prefix_to_remove, "")

        # 转换为驼峰命名
        parts = field_name.split('_')
        camel_case = parts[0]
        for part in parts[1:]:
            if part:
                camel_case += part[0].upper() + part[1:]

        return camel_case

    def _parse_rivalry_info(self, boxscore_summary: Dict[str, Any], game_data: Dict[str, Any]) -> None:
        """解析球队对抗历史信息并添加到game_data中"""
        try:
            self.logger.debug("开始解析球队对抗历史信息")

            # 初始化所需字段的字典
            rivalry_data = {}

            # 遍历所有结果集
            for result_set in boxscore_summary.get("resultSets", []):
                result_name = result_set.get("name")

                if not result_set.get("rowSet") or len(result_set["rowSet"]) == 0:
                    continue

                headers = result_set.get("headers", [])
                row = result_set["rowSet"][0]

                # 处理LastMeeting数据
                if result_name == "LastMeeting":
                    self._parse_last_meeting(headers, row, rivalry_data)
                # 处理SeasonSeries数据
                elif result_name == "SeasonSeries":
                    self._parse_season_series(headers, row, rivalry_data)

            # 确保所有必需字段都存在
            self._ensure_required_rivalry_fields(rivalry_data)

            # 确保lastGameId是字符串类型
            if "lastGameId" in rivalry_data and not isinstance(rivalry_data["lastGameId"], str):
                rivalry_data["lastGameId"] = str(rivalry_data["lastGameId"])

            game_data["rivalryInfo"] = rivalry_data
            self.logger.debug(f"成功解析球队对抗历史信息，字段数量: {len(rivalry_data)}")

        except Exception as e:
            self.logger.error(f"解析球队对抗历史信息时出错: {str(e)}", exc_info=True)
            game_data["rivalryInfo"] = None

    def _parse_last_meeting(self, headers, row, rivalry_data):
        """解析LastMeeting数据

        Args:
            headers: 字段头
            row: 数据行
            rivalry_data: 存储结果的字典
        """
        for i, header in enumerate(headers):
            field_name = self._convert_to_snake_case(header)
            value = row[i]

            # 特殊处理lastGameId，确保是字符串类型
            if field_name == "last_game_id":
                rivalry_data["lastGameId"] = str(value) if value else ""
            # 日期字段特殊处理
            elif field_name == "last_game_date_est":
                rivalry_data["lastGameDateEst"] = self._parse_date_safely(value)
            # ID和分数字段特殊处理，确保是整数
            elif field_name in ["last_game_home_team_id", "last_game_visitor_team_id",
                                "last_game_home_team_points", "last_game_visitor_team_points"]:
                try:
                    key = field_name.replace("last_game_", "lastGame").replace("_", "")
                    # 首字母小写
                    key = key[0].lower() + key[1:]
                    rivalry_data[key] = int(value) if value is not None else 0
                except (ValueError, TypeError) as e:
                    self.logger.debug(f"无法将 '{value}' 转换为整数: {e}")
                    key = field_name.replace("last_game_", "lastGame").replace("_", "")
                    key = key[0].lower() + key[1:]
                    rivalry_data[key] = 0
            # 确保队伍简写字段正确处理
            elif header == "LAST_GAME_VISITOR_TEAM_CITY1":
                rivalry_data["lastGameVisitorTeamAbbreviation"] = value if value else ""
            # 普通文本字段
            elif field_name in ["last_game_home_team_city", "last_game_home_team_name",
                                "last_game_home_team_abbreviation", "last_game_visitor_team_city",
                                "last_game_visitor_team_name"]:
                key = field_name.replace("last_game_", "lastGame").replace("_", "")
                key = key[0].lower() + key[1:]
                rivalry_data[key] = value if value else ""

    def _parse_season_series(self, headers, row, rivalry_data):
        """解析SeasonSeries数据

        Args:
            headers: 字段头
            row: 数据行
            rivalry_data: 存储结果的字典
        """
        for i, header in enumerate(headers):
            if header == "GAME_ID":
                rivalry_data["gameId"] = str(row[i]) if row[i] else ""
            elif header == "HOME_TEAM_ID":
                try:
                    rivalry_data["homeTeamId"] = int(row[i]) if row[i] else 0
                except (ValueError, TypeError) as e:
                    self.logger.debug(f"无法将 '{row[i]}' 转换为整数: {e}")
                    rivalry_data["homeTeamId"] = 0
            elif header == "VISITOR_TEAM_ID":
                try:
                    rivalry_data["visitorTeamId"] = int(row[i]) if row[i] else 0
                except (ValueError, TypeError) as e:
                    self.logger.debug(f"无法将 '{row[i]}' 转换为整数: {e}")
                    rivalry_data["visitorTeamId"] = 0
            elif header == "GAME_DATE_EST":
                rivalry_data["gameDateEst"] = self._parse_date_safely(row[i])
            elif header == "HOME_TEAM_WINS":
                try:
                    rivalry_data["homeTeamWins"] = int(row[i]) if row[i] else 0
                except (ValueError, TypeError) as e:
                    self.logger.debug(f"无法将 '{row[i]}' 转换为整数: {e}")
                    rivalry_data["homeTeamWins"] = 0
            elif header == "HOME_TEAM_LOSSES":
                try:
                    rivalry_data["homeTeamLosses"] = int(row[i]) if row[i] else 0
                except (ValueError, TypeError) as e:
                    self.logger.debug(f"无法将 '{row[i]}' 转换为整数: {e}")
                    rivalry_data["homeTeamLosses"] = 0
            elif header == "SERIES_LEADER":
                rivalry_data["seriesLeader"] = row[i] if row[i] else ""

    def _ensure_required_rivalry_fields(self, rivalry_data):
        """确保所有必需字段都存在

        Args:
            rivalry_data: 需要检查和补充的数据字典
        """
        required_fields = [
            "gameId", "homeTeamId", "visitorTeamId", "gameDateEst",
            "homeTeamWins", "homeTeamLosses", "lastGameId", "lastGameDateEst",
            "lastGameHomeTeamId", "lastGameHomeTeamCity", "lastGameHomeTeamName",
            "lastGameHomeTeamAbbreviation", "lastGameHomeTeamPoints",
            "lastGameVisitorTeamId", "lastGameVisitorTeamCity", "lastGameVisitorTeamName",
            "lastGameVisitorTeamAbbreviation", "lastGameVisitorTeamPoints"
        ]

        for field in required_fields:
            if field not in rivalry_data:
                if "Id" in field or "Points" in field or "Wins" in field or "Losses" in field:
                    rivalry_data[field] = 0
                elif "Date" in field:
                    rivalry_data[field] = datetime.now()
                elif field == "gameId" or field == "lastGameId":
                    rivalry_data[field] = ""  # 确保ID字段是字符串
                else:
                    rivalry_data[field] = ""

    def _convert_to_snake_case(self, text: str) -> str:
        """将驼峰命名转换为蛇形命名"""
        return re.sub(r'(?<!^)(?=[A-Z])', '_', text).lower()

    def _parse_datetime(self, date_str: str) -> datetime:
        """解析日期时间字符串为datetime对象"""
        return self._parse_date_safely(date_str)

    def _process_game_data(self, game_data: Dict[str, Any]) -> GameData:
        try:
            # 处理嵌套的数据结构
            if 'meta' in game_data and 'game' in game_data:
                data = game_data['game']
            else:
                data = game_data

            # 确保关键字段存在且有效
            if 'period' not in data or not isinstance(data['period'], int) or data['period'] < 1:
                data['period'] = 1

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

            # 处理场馆信息
            if 'arena' in data:
                data['arena'] = Arena(**data['arena'])
            else:
                data['arena'] = Arena()

            # 处理裁判信息
            if 'officials' in data and isinstance(data['officials'], list):
                data['officials'] = [Official(**official) for official in data['officials']]

            # 处理球队对抗历史信息
            if 'rivalryInfo' in data:
                try:
                    # 转换为TeamRivalryInfo实例
                    rivalry_data = data.pop('rivalryInfo')  # 先移除原始数据
                    if rivalry_data:  # 确保数据不为None
                        # 确保lastGameId是字符串类型
                        if 'lastGameId' in rivalry_data and not isinstance(rivalry_data['lastGameId'], str):
                            rivalry_data['lastGameId'] = str(rivalry_data['lastGameId'])

                        data['rivalryInfo'] = TeamRivalryInfo(**rivalry_data)
                        self.logger.debug("成功创建TeamRivalryInfo实例")
                except ValidationError as ve:
                    self.logger.error(f"TeamRivalryInfo验证错误: {ve}")
                    data['rivalryInfo'] = None
                except Exception as e:
                    self.logger.error(f"处理球队对抗历史信息时出错: {str(e)}", exc_info=True)
                    data['rivalryInfo'] = None

            # 创建 GameData 实例
            return GameData(
                **data,
                homeTeam=home_team,
                awayTeam=away_team
            )

        except Exception as e:
            self.logger.error(f"处理比赛数据时出错: {str(e)}", exc_info=True)
            return GameData(
                homeTeam=self._process_team_stats({}),
                awayTeam=self._process_team_stats({}),
                statistics=None,  # 保证数据结构正确
                rivalryInfo=None  # 处理数据出错的情况下,保证数据结构正确
            )

    def _process_team_stats(self, team_data: Dict[str, Any]) -> TeamInGame:
        """处理球队统计数据"""
        try:
            # 处理每节比分
            if 'periods' in team_data:
                team_data['periods'] = [
                    PeriodScore(**period_data)
                    for period_data in team_data['periods']
                ]

            # 处理球员数据
            if 'players' in team_data:
                processed_players = []
                for player in team_data['players']:
                    player['team_name'] = team_data.get('teamName')
                    processed_player = self._process_player_stats(player)
                    if processed_player:
                        processed_players.append(processed_player)
                team_data['players'] = processed_players

            # 处理团队统计
            if 'statistics' in team_data:
                team_data['statistics'] = TeamStatistics(**team_data['statistics'])

            return TeamInGame(**team_data)

        except Exception as e:
            self.logger.error(f"处理球队数据时出错: {str(e)}", exc_info=True)
            raise  # 让上层处理错误

    def _process_player_stats(self, player_data: Dict[str, Any]) -> Optional[PlayerInGame]:
        """处理球员统计数据"""
        try:
            if not player_data or not isinstance(player_data, dict):
                self.logger.warning("无效的球员数据")
                return None

            # 1. 处理基础统计数据
            if 'statistics' not in player_data:
                player_data['statistics'] = {}

            # 2. 处理状态字段
            self._process_player_status(player_data)

            # 3. 处理统计数据
            player_data['statistics'] = PlayerStatistics(**player_data['statistics'])

            return PlayerInGame(**player_data)

        except Exception as e:
            self.logger.error(f"处理球员数据时出错: {str(e)}", exc_info=True)
            return None

    def _process_team_event(self, event_type, event_data):
        """处理团队事件

        Args:
            event_type: 事件类型
            event_data: 事件数据

        Returns:
            BaseEvent: 事件对象
        """
        # 共同处理团队事件的基本字段
        event_data.update({
            'playerName': 'TEAM',
            'playerNameI': 'TEAM'
        })

        # 针对不同事件类型的特殊处理
        if event_type == 'foul':
            return FoulEvent(**event_data)
        elif event_type == 'turnover':
            event_data['turnoverTotal'] = 1
            return TurnoverEvent(**event_data)
        elif event_type == 'rebound':
            event_data.update({
                'reboundTotal': 1,
                'reboundDefensiveTotal': 1 if event_data['subType'] == 'defensive' else 0,
                'reboundOffensiveTotal': 1 if event_data['subType'] == 'offensive' else 0
            })
            return ReboundEvent(**event_data)
        elif event_type == 'violation':
            return ViolationEvent(**event_data)

        # 默认返回基本事件
        return BaseEvent(**event_data)

    def _process_event(self, event_data: Dict[str, Any]) -> Optional[BaseEvent]:
        """处理单个事件数据"""
        try:
            if 'actionType' not in event_data:
                return None

            event_type = event_data['actionType']

            # 处理团队相关事件
            if self._is_team_event(event_type, event_data):
                return self._process_team_event(event_type, event_data)

            # 处理投篮事件
            if event_type in ['2pt', '3pt']:
                if 'shotResult' not in event_data:
                    event_data['shotResult'] = 'Made' if 'pointsTotal' in event_data else 'Missed'
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

            # 处理换人事件
            elif event_type == 'substitution':
                return self._process_substitution_event(event_data)

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
            self.logger.error(f"处理事件时出错: {str(e)}", exc_info=True)
            return None

    def _is_team_event(self, event_type, event_data):
        """判断是否为团队事件

        Args:
            event_type: 事件类型
            event_data: 事件数据

        Returns:
            bool: 是否为团队事件
        """
        # 团队技术犯规
        if (event_type == 'foul' and
                event_data.get('subType') == 'technical' and
                'TEAM' in event_data.get('description', '').upper()):
            return True

        # 团队失误事件
        if event_type == 'turnover' and event_data.get('qualifiers', []) == ['team']:
            return True

        # 团队篮板事件
        if event_type == 'rebound' and 'team' in event_data.get('qualifiers', []):
            return True

        # 团队违例事件
        if event_type == 'violation' and 'team' in event_data.get('qualifiers', []):
            return True

        return False

    def _process_substitution_event(self, event_data):
        """处理换人事件

        Args:
            event_data: 换人事件数据

        Returns:
            SubstitutionEvent: 换人事件对象
        """
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

    def _parse_playbyplay(self, data: Dict[str, Any]) -> Optional[PlayByPlay]:
        """解析比赛回放数据"""
        try:
            # 添加更详细的日志
            self.logger.debug(f"开始解析回放数据: {data.keys() if data else None}")

            if not data:
                self.logger.warning("回放数据为空")
                return None

            # 1. 处理缓存数据结构
            if 'timestamp' in data and 'data' in data:
                data = data['data']

            # 2. 检查数据结构
            if not isinstance(data, dict):
                self.logger.warning("无效的数据格式")
                return None

            # 3. 定位 actions 数据
            game_data = data.get('game', {})
            actions_data = game_data.get('actions', [])

            if not actions_data and not game_data.get('gameStatus') == GameStatusEnum.NOT_STARTED:
                self.logger.warning("未找到有效的actions数据")
                return None

            # 4. 处理事件
            actions = []
            for action_data in actions_data:
                try:
                    event = self._process_event(action_data)
                    if event:
                        actions.append(event)
                except Exception as e:
                    self.logger.error(f"处理事件时出错: {e}, 事件数据: {action_data}", exc_info=True)
                    continue

            self.logger.info(f"成功解析 {len(actions)} 个事件")

            # 5. 创建回放对象
            play_by_play = PlayByPlay(
                game=game_data,
                meta=data.get('meta', {}),
                actions=actions
            )

            return play_by_play

        except Exception as e:
            self.logger.error(f"解析回放数据时出错: {e}", exc_info=True)
            return None

    def _get_event_class(self, event_type: str) -> Optional[type]:
        """
        根据事件类型获取对应的事件类

        Args:
            event_type: 事件类型字符串

        Returns:
            type: 事件类，如果找不到对应类型则返回None
        """
        return self.EVENT_TYPE_MAP.get(event_type)

    def _validate_event_data(self, event_data: Dict[str, Any], event_class: type) -> Dict[str, Any]:
        """
        验证并处理事件数据

        Args:
            event_data: 事件数据字典
            event_class: 事件类

        Returns:
            Dict[str, Any]: 处理后的事件数据

        Raises:
            ValidationError: 数据验证失败时抛出
        """
        try:
            # 创建事件类实例进行验证
            event = event_class(**event_data)
            return event.model_dump()
        except Exception as e:
            raise ValidationError(f"Event validation failed: {str(e)}")

    def is_valid_game_data(self, data: Dict[str, Any]) -> bool:
        """
        验证比赛数据是否有效

        Args:
            data: 待验证的比赛数据

        Returns:
            bool: 数据是否有效
        """
        try:
            if not isinstance(data, dict):
                return False

            required_fields = {'game', 'meta'}
            if not all(field in data for field in required_fields):
                return False

            # 检查game对象
            game_data = data['game']
            if not isinstance(game_data, dict):
                return False

            required_game_fields = {'gameId', 'gameStatus', 'homeTeam', 'awayTeam'}
            if not all(field in game_data for field in required_game_fields):
                return False

            return True

        except Exception as e:
            self.logger.error(f"验证比赛数据时出错: {e}", exc_info=True)
            return False