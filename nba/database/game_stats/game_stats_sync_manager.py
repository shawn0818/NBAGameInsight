import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from utils.logger_handler import AppLogger


class GameStatsSyncManager:
    """
    比赛统计数据同步管理器
    负责协调各个数据同步器的工作
    """

    def __init__(self, db_manager, game_fetcher=None):
        """初始化同步管理器"""
        self.db_manager = db_manager
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        # 初始化各个同步器
        from nba.database.game_stats.statistics_sync import BoxscoreSync
        from nba.database.game_stats.playbyplay_sync import PlayByPlaySync

        self.boxscore_sync = BoxscoreSync(db_manager, game_fetcher=game_fetcher)
        self.playbyplay_sync = PlayByPlaySync(db_manager, game_fetcher=game_fetcher)

    def sync_game_data(self, game_id: str, force_update: bool = False) -> Dict[str, Any]:
        """
        同步指定比赛的统计数据

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新，默认为False

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now().isoformat()
        self.logger.info(f"开始同步比赛(ID:{game_id})的统计数据...")

        results = {
            "boxscore": {"status": "pending"},
            "playbyplay": {"status": "pending"}
        }

        try:
            # 1. 同步比赛统计数据
            boxscore_result = self.boxscore_sync.sync_boxscore(game_id, force_update)
            results["boxscore"] = boxscore_result

            # 2. 同步比赛回合数据
            playbyplay_result = self.playbyplay_sync.sync_playbyplay(game_id, force_update)
            results["playbyplay"] = playbyplay_result

            # 计算总体状态
            status = "success"
            if any(r.get("status") == "failed" for r in results.values()):
                status = "failed"
            elif any(r.get("status") == "partial" for r in results.values()):
                status = "partial"

            # 记录结果
            end_time = datetime.now().isoformat()
            self._record_sync_history(
                "game_data", status, game_id,
                sum(r.get("items_processed", 0) for r in results.values()),
                sum(r.get("items_succeeded", 0) for r in results.values()),
                start_time, end_time, json.dumps(results),
                None if status == "success" else "同步未完全成功"
            )

            self.logger.info(f"比赛(ID:{game_id})数据同步完成，状态: {status}")
            return {
                "status": status,
                "game_id": game_id,
                "results": results,
                "start_time": start_time,
                "end_time": end_time
            }

        except Exception as e:
            error_msg = f"同步比赛(ID:{game_id})数据失败: {e}"
            self.logger.error(error_msg, exc_info=True)

            # 记录失败历史
            end_time = datetime.now().isoformat()
            self._record_sync_history(
                "game_data", "failed", game_id, 0, 0,
                start_time, end_time, None, str(e)
            )

            return {
                "status": "failed",
                "game_id": game_id,
                "error": str(e),
                "start_time": start_time,
                "end_time": end_time
            }

    def _record_sync_history(self, sync_type, status, game_id=None, items_processed=0,
                             items_succeeded=0, start_time=None, end_time=None,
                             details=None, error_message=None):
        """记录同步历史"""
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute('''
            INSERT INTO game_stats_sync_history
            (sync_type, game_id, status, items_processed, items_succeeded, 
             start_time, end_time, details, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                sync_type, game_id, status, items_processed, items_succeeded,
                start_time, end_time,
                details if details else "",
                error_message if error_message else ""
            ))
            self.db_manager.conn.commit()
        except Exception as e:
            self.logger.error(f"记录同步历史失败: {e}")

    def batch_sync_games(self, game_ids: List[str], force_update: bool = False) -> Dict[str, Any]:
        """
        批量同步多场比赛的数据

        Args:
            game_ids: 比赛ID列表
            force_update: 是否强制更新，默认为False

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now().isoformat()
        self.logger.info(f"开始批量同步{len(game_ids)}场比赛的数据...")

        results = {}
        success_count = 0

        for game_id in game_ids:
            try:
                self.logger.info(f"开始同步比赛(ID:{game_id})数据...")
                result = self.sync_game_data(game_id, force_update)
                results[game_id] = result

                if result.get("status") == "success":
                    success_count += 1

                # 添加延迟，避免请求过于频繁
                time.sleep(0.5)

            except Exception as e:
                self.logger.error(f"同步比赛(ID:{game_id})数据失败: {e}")
                results[game_id] = {"status": "failed", "error": str(e)}

        # 记录总体结果
        end_time = datetime.now().isoformat()
        status = "success" if success_count == len(game_ids) else "partial" if success_count > 0 else "failed"

        self._record_sync_history(
            "batch_games", status, None,
            len(game_ids), success_count,
            start_time, end_time, json.dumps({"game_count": len(game_ids)}),
            None if status == "success" else f"批量同步未完全成功: {success_count}/{len(game_ids)}"
        )

        self.logger.info(f"批量同步完成，成功: {success_count}/{len(game_ids)}")
        return {
            "status": status,
            "game_count": len(game_ids),
            "success_count": success_count,
            "results": results,
            "start_time": start_time,
            "end_time": end_time
        }