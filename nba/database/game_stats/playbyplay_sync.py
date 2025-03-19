import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from nba.fetcher.game_fetcher import GameFetcher
from utils.logger_handler import AppLogger


class PlayByPlaySync:
    """
    比赛回合数据同步器
    负责从NBA API获取数据、转换并写入数据库
    """

    def __init__(self, db_manager, playbyplay_repository=None, game_fetcher=None):
        """初始化比赛回合数据同步器"""
        self.db_manager = db_manager
        self.playbyplay_repository = playbyplay_repository  # 可选，用于查询
        self.game_fetcher = game_fetcher or GameFetcher()
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')

    def sync_playbyplay(self, game_id: str, force_update: bool = False) -> Dict[str, Any]:
        """
        同步指定比赛的回合数据

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新，默认为False

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now().isoformat()
        self.logger.info(f"开始同步比赛(ID:{game_id})的Play-by-Play数据...")

        try:
            # 获取playbyplay数据
            playbyplay_data = self.game_fetcher.get_playbyplay(game_id, force_update)
            if not playbyplay_data:
                raise ValueError(f"无法获取比赛(ID:{game_id})的Play-by-Play数据")

            # 解析和保存数据
            success_count, summary = self._save_playbyplay_data(game_id, playbyplay_data)

            end_time = datetime.now().isoformat()
            status = "success" if success_count > 0 else "failed"

            # 记录同步历史
            self._record_sync_history(game_id, status, start_time, end_time, success_count, summary)

            self.logger.info(f"比赛(ID:{game_id})Play-by-Play数据同步完成，状态: {status}")
            return {
                "status": status,
                "items_processed": 1,
                "items_succeeded": success_count,
                "summary": summary,
                "start_time": start_time,
                "end_time": end_time
            }

        except Exception as e:
            error_msg = f"同步比赛(ID:{game_id})Play-by-Play数据失败: {e}"
            self.logger.error(error_msg, exc_info=True)

            # 记录失败的同步历史
            self._record_sync_history(game_id, "failed", start_time, datetime.now().isoformat(), 0, {"error": str(e)})

            return {
                "status": "failed",
                "items_processed": 1,
                "items_succeeded": 0,
                "error": str(e)
            }

    def _record_sync_history(self, game_id: str, status: str, start_time: str, end_time: str,
                             items_processed: int, details: Dict) -> None:
        """记录同步历史到数据库"""
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute('''
                INSERT INTO game_stats_sync_history 
                (sync_type, game_id, status, items_processed, items_succeeded, 
                start_time, end_time, details, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                'playbyplay',
                game_id,
                status,
                items_processed,
                items_processed if status == "success" else 0,
                start_time,
                end_time,
                json.dumps(details),
                details.get("error", "") if status == "failed" else ""
            ))
            self.db_manager.conn.commit()
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
            cursor = self.db_manager.conn.cursor()
            now = datetime.now().isoformat()
            success_count = 0
            summary = {
                "play_actions_count": 0
            }

            # 提取并保存回合动作
            play_actions = self._extract_play_actions(playbyplay_data, game_id)
            if play_actions:
                for action in play_actions:
                    action["game_id"] = game_id
                    action["last_updated_at"] = now
                    self._save_or_update_play_action(cursor, action)
                    success_count += 1

                summary["play_actions_count"] = len(play_actions)

            self.db_manager.conn.commit()
            self.logger.info(f"成功保存比赛(ID:{game_id})的PlayByPlay数据，共{success_count}条记录")
            return success_count, summary

        except Exception as e:
            self.db_manager.conn.rollback()
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

    def _save_or_update_play_action(self, cursor, play_action: Dict) -> None:
        """保存或更新回合动作数据"""
        try:
            game_id = play_action.get('game_id')
            action_number = play_action.get('action_number')

            # 检查是否已存在
            cursor.execute("SELECT game_id FROM events WHERE game_id = ? AND action_number = ?",
                           (game_id, action_number))
            exists = cursor.fetchone()

            if exists:
                # 更新现有记录
                placeholders = ", ".join([f"{k} = ?" for k in play_action.keys()
                                          if k not in ('game_id', 'action_number')])
                values = [v for k, v in play_action.items() if k not in ('game_id', 'action_number')]
                values.append(game_id)  # WHERE条件的值
                values.append(action_number)  # WHERE条件的值

                cursor.execute(
                    f"UPDATE events SET {placeholders} WHERE game_id = ? AND action_number = ?", values)
            else:
                # 插入新记录
                placeholders = ", ".join(["?"] * len(play_action))
                columns = ", ".join(play_action.keys())
                values = list(play_action.values())

                cursor.execute(f"INSERT INTO events ({columns}) VALUES ({placeholders})", values)

        except Exception as e:
            self.logger.error(f"保存或更新回合动作数据失败: {e}")
            raise