# sync/playbyplay_sync.py
from datetime import datetime
from typing import Dict, List, Any, Tuple
import json
from nba.fetcher.game_fetcher import GameFetcher
from utils.logger_handler import AppLogger
from database.models.stats_models import Event, GameStatsSyncHistory
from database.db_session import DBSession


class PlayByPlaySync:
    """
    比赛回合数据同步器
    负责从NBA API获取数据、转换并写入数据库
    """

    def __init__(self, playbyplay_repository=None, game_fetcher=None):
        """初始化比赛回合数据同步器"""
        self.db_session = DBSession.get_instance()
        self.playbyplay_repository = playbyplay_repository  # 可选，用于查询
        self.game_fetcher = game_fetcher or GameFetcher()
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def sync_playbyplay(self, game_id: str, force_update: bool = False) -> Dict[str, Any]:
        """
        同步指定比赛的回合数据

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新，默认为False

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info(f"开始同步比赛(ID:{game_id})的Play-by-Play数据...")

        try:
            # 获取playbyplay数据
            playbyplay_data = self.game_fetcher.get_playbyplay(game_id, force_update)
            if not playbyplay_data:
                raise ValueError(f"无法获取比赛(ID:{game_id})的Play-by-Play数据")

            # 解析和保存数据
            success_count, summary = self._save_playbyplay_data(game_id, playbyplay_data)

            end_time = datetime.now()
            status = "success" if success_count > 0 else "failed"

            # 记录同步历史
            self._record_sync_history(game_id, status, start_time, end_time, success_count, summary)

            self.logger.info(f"比赛(ID:{game_id})Play-by-Play数据同步完成，状态: {status}")
            return {
                "status": status,
                "items_processed": 1,
                "items_succeeded": success_count,
                "summary": summary,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }

        except Exception as e:
            error_msg = f"同步比赛(ID:{game_id})Play-by-Play数据失败: {e}"
            self.logger.error(error_msg, exc_info=True)

            # 记录失败的同步历史
            self._record_sync_history(game_id, "failed", start_time, datetime.now(), 0, {"error": str(e)})

            return {
                "status": "failed",
                "items_processed": 1,
                "items_succeeded": 0,
                "error": str(e)
            }

    def _record_sync_history(self, game_id: str, status: str, start_time: datetime, end_time: datetime,
                             items_processed: int, details: Dict) -> None:
        """记录同步历史到数据库"""
        try:
            with self.db_session.session_scope('game') as session:
                sync_history = GameStatsSyncHistory(
                    sync_type='playbyplay',
                    game_id=game_id,
                    status=status,
                    items_processed=items_processed,
                    items_succeeded=items_processed if status == "success" else 0,
                    start_time=start_time,
                    end_time=end_time,
                    details=json.dumps(details),
                    error_message=details.get("error", "") if status == "failed" else ""
                )
                session.add(sync_history)
                # 事务会在session_scope结束时自动提交
        except Exception as e:
            self.logger.error(f"记录同步历史失败: {e}")

    def _save_playbyplay_data(self, game_id: str, playbyplay_data: Dict) -> Tuple[int, Dict]:
        """
        解析并保存playbyplay数据到数据库

        Args:
            game_id: 比赛ID
            playbyplay_data: 从API获取的回合数据

        Returns:
            Tuple[int, Dict]: 成功保存的记录数和摘要信息
        """
        try:
            success_count = 0
            summary = {
                "play_actions_count": 0
            }

            # 提取回合动作
            play_actions = self._extract_play_actions(playbyplay_data, game_id)
            if play_actions:
                with self.db_session.session_scope('game') as session:
                    for action in play_actions:
                        action["game_id"] = game_id
                        self._save_or_update_play_action(session, action)
                        success_count += 1

                summary["play_actions_count"] = len(play_actions)

            self.logger.info(f"成功保存比赛(ID:{game_id})的PlayByPlay数据，共{success_count}条记录")
            return success_count, summary

        except Exception as e:
            self.logger.error(f"保存PlayByPlay数据失败: {e}")
            raise

    def _extract_play_actions(self, playbyplay_data: Dict, game_id: str) -> List[Dict]:
        """从playbyplay数据中提取具体回合动作"""
        try:
            play_actions = []

            # 从新格式中获取actions数组
            game_data = playbyplay_data.get('game', {})
            actions = game_data.get('actions', [])

            if not actions:
                return play_actions

            # 遍历每个动作并提取数据
            for action in actions:
                extracted_action = {
                    "game_id": game_id,
                    "action_number": action.get('actionNumber', 0),
                    "clock": action.get('clock', ''),
                    "period": action.get('period', 0),
                    "team_id": action.get('teamId', 0),
                    "team_tricode": action.get('teamTricode', ''),
                    "person_id": action.get('personId', 0),
                    "player_name": action.get('playerName', ''),
                    "player_name_i": action.get('playerNameI', ''),
                    "x_legacy": action.get('xLegacy', 0),
                    "y_legacy": action.get('yLegacy', 0),
                    "shot_distance": action.get('shotDistance', 0),
                    "shot_result": action.get('shotResult', ''),
                    "is_field_goal": action.get('isFieldGoal', 0),
                    "score_home": action.get('scoreHome', ''),
                    "score_away": action.get('scoreAway', ''),
                    "points_total": action.get('pointsTotal', 0),
                    "location": action.get('location', ''),
                    "description": action.get('description', ''),
                    "action_type": action.get('actionType', ''),
                    "sub_type": action.get('subType', ''),
                    "video_available": action.get('videoAvailable', 0),
                    "shot_value": action.get('shotValue', 0),
                    "action_id": action.get('actionId', 0)
                }
                play_actions.append(extracted_action)

            return play_actions

        except Exception as e:
            self.logger.error(f"提取回合动作数据失败: {e}")
            return []

    def _save_or_update_play_action(self, session, play_action: Dict) -> None:
        """保存或更新回合动作数据"""
        try:
            game_id = play_action.get('game_id')
            action_number = play_action.get('action_number')

            # 检查是否已存在
            existing_event = session.query(Event).filter(
                Event.game_id == game_id,
                Event.action_number == action_number
            ).first()

            if existing_event:
                # 更新现有记录
                for key, value in play_action.items():
                    if hasattr(existing_event, key):
                        setattr(existing_event, key, value)
            else:
                # 创建新的Event对象
                new_event = Event(**play_action)
                session.add(new_event)

        except Exception as e:
            self.logger.error(f"保存或更新回合动作数据失败: {e}")
            raise