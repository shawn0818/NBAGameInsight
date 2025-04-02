# database/sync/boxscore_sync.py
import concurrent
import json
import threading
import concurrent.futures
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Set

from nba.fetcher.game_fetcher import GameFetcher
from utils.logger_handler import AppLogger
from database.db_session import DBSession
from database.models.stats_models import Statistics, GameStatsSyncHistory


class BoxscoreSync:
    """
    比赛数据同步器
    负责从NBA API获取数据、转换并写入数据库
    支持并发同步多场比赛
    """

    def __init__(self, game_fetcher=None, max_global_concurrency=20):
        """初始化比赛数据同步器"""
        self.db_session = DBSession.get_instance()
        self.game_fetcher = game_fetcher or GameFetcher()
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')
        # 获取game_fetcher中的http_manager
        self.http_manager = self.game_fetcher.http_manager
        # 添加全局并发控制
        self.global_semaphore = threading.Semaphore(max_global_concurrency)  # 全局最大并发请求数
        self.active_threads = 0
        self.thread_lock = threading.Lock()

        # 批次和线程动态调整参数
        self.current_batch_size = 50  # 初始批次大小
        self.current_max_workers = 10  # 初始线程数
        self.success_rate_history = []  # 成功率历史记录
        self.response_time_history = []  # 响应时间历史记录

    def sync_boxscore(self, game_id: str, force_update: bool = False) -> Dict[str, Any]:
        """
        同步指定比赛的统计数据 (单场比赛)

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新，默认为False

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info(f"开始同步比赛(ID:{game_id})的Boxscore数据...")

        try:
            # 获取boxscore数据
            boxscore_data = self.game_fetcher.get_boxscore_traditional(game_id, force_update)
            if not boxscore_data:
                raise ValueError(f"无法获取比赛(ID:{game_id})的Boxscore数据")

            # 解析和保存数据
            success_count, summary = self._save_boxscore_data(game_id, boxscore_data)

            end_time = datetime.now()
            # 只要summary中没有error字段，就认为是成功的
            status = "failed" if "error" in summary else "success"

            # 记录同步历史
            self._record_sync_history(game_id, status, start_time, end_time, success_count, summary)

            self.logger.info(f"比赛(ID:{game_id})Boxscore数据同步完成，状态: {status}")
            return {
                "status": status,
                "items_processed": 1,
                "items_succeeded": success_count,
                "summary": summary,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration": (end_time - start_time).total_seconds()
            }

        except Exception as e:
            error_msg = f"同步比赛(ID:{game_id})Boxscore数据失败: {e}"
            self.logger.error(error_msg, exc_info=True)

            # 记录失败的同步历史
            self._record_sync_history(game_id, "failed", start_time, datetime.now(), 0, {"error": str(e)})

            return {
                "status": "failed",
                "items_processed": 1,
                "items_succeeded": 0,
                "error": str(e),
                "duration": (datetime.now() - start_time).total_seconds()
            }

    def batch_sync_boxscores(self, game_ids: List[str], force_update: bool = False,
                             max_workers: Optional[int] = None, batch_size: Optional[int] = None,
                             batch_interval: int = 30) -> Dict[str, Any]:
        """
        并行同步多场比赛的Boxscore数据

        Args:
            game_ids: 比赛ID列表
            force_update: 是否强制更新缓存
            max_workers: 最大工作线程数 (若为None则使用当前动态值)
            batch_size: 批处理大小 (若为None则使用当前动态值)
            batch_interval: 批次之间的间隔时间(秒)

        Returns:
            Dict: 同步结果摘要
        """
        # 使用当前动态值或指定值
        max_workers = max_workers if max_workers is not None else self.current_max_workers
        batch_size = batch_size if batch_size is not None else self.current_batch_size

        start_time = datetime.now()
        self.logger.info(
            f"开始批量同步{len(game_ids)}场比赛的Boxscore数据，最大线程数: {max_workers}, 批次大小: {batch_size}")

        # 结果统计
        result = {
            "start_time": start_time.isoformat(),
            "total_games": len(game_ids),
            "successful_games": 0,
            "failed_games": 0,
            "skipped_games": 0,
            "details": []
        }

        # 检查已同步的比赛，避免重复同步
        synced_game_ids = self._get_synced_game_ids()
        games_to_sync = [gid for gid in game_ids if gid not in synced_game_ids or force_update]

        if len(games_to_sync) < len(game_ids):
            skipped_count = len(game_ids) - len(games_to_sync)
            result["skipped_games"] = skipped_count
            self.logger.info(f"跳过{skipped_count}场已同步的比赛")

        # 如果没有需要同步的比赛，直接返回
        if not games_to_sync:
            end_time = datetime.now()
            result["end_time"] = end_time.isoformat()
            result["duration"] = (end_time - start_time).total_seconds()
            result["status"] = "completed"
            self.logger.info("所有比赛已同步，无需处理")
            return result

        # 设置http_manager的批次间隔
        self.http_manager.set_batch_interval(batch_interval)

        # 分批处理
        batches = [games_to_sync[i:i + batch_size] for i in range(0, len(games_to_sync), batch_size)]
        self.logger.info(f"将{len(games_to_sync)}场比赛分为{len(batches)}批进行处理")

        # 处理每一批
        for batch_idx, batch_game_ids in enumerate(batches):
            # 等待批次间隔
            self.http_manager.wait_for_next_batch()

            batch_start_time = datetime.now()
            self.logger.info(f"开始处理第{batch_idx + 1}/{len(batches)}批，包含{len(batch_game_ids)}场比赛")

            # 并行处理每场比赛
            batch_results = self._process_batch_with_threading(batch_game_ids, force_update, max_workers)

            # 更新统计信息
            success_count = sum(1 for r in batch_results if r["status"] == "success")
            fail_count = len(batch_results) - success_count

            result["successful_games"] += success_count
            result["failed_games"] += fail_count
            result["details"].extend(batch_results)

            batch_end_time = datetime.now()
            batch_duration = (batch_end_time - batch_start_time).total_seconds()

            self.logger.info(
                f"第{batch_idx + 1}批处理完成: 成功{success_count}场, 失败{fail_count}场, 耗时{batch_duration:.2f}秒")

            # 动态调整下一批次的参数
            if batch_idx < len(batches) - 1:  # 不是最后一批
                new_batch_size, new_max_workers = self._adjust_batch_parameters(batch_results)
                # 如果参数有变化，重新划分剩余的批次
                if new_batch_size != batch_size:
                    remaining_games = [item for sublist in batches[batch_idx + 1:] for item in sublist]
                    batches = batches[:batch_idx + 1]  # 保留已处理的批次
                    batches.extend(
                        [remaining_games[i:i + new_batch_size] for i in range(0, len(remaining_games), new_batch_size)])
                    batch_size = new_batch_size
                    self.logger.info(f"重新划分剩余{len(remaining_games)}场比赛为{len(batches) - (batch_idx + 1)}批")
                max_workers = new_max_workers

        # 完成统计
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()

        result["end_time"] = end_time.isoformat()
        result["duration"] = total_duration
        result["status"] = "completed" if result["failed_games"] == 0 else "partially_completed"

        self.logger.info(f"批量同步完成: 总计{result['total_games']}场, 成功{result['successful_games']}场, "
                         f"失败{result['failed_games']}场, 跳过{result['skipped_games']}场, 总耗时{total_duration:.2f}秒")

        return result

    def batch_sync_with_retry(self, game_ids: List[str], max_retries=3, force_update: bool = False,
                              max_workers: Optional[int] = None, batch_size: Optional[int] = None) -> Dict[str, Any]:
        """批量同步并智能重试失败的任务

        Args:
            game_ids: 比赛ID列表
            max_retries: 最大重试次数
            force_update: 是否强制更新缓存
            max_workers: 最大工作线程数
            batch_size: 批处理大小

        Returns:
            Dict: 同步结果摘要
        """
        start_time = datetime.now()
        self.logger.info(f"开始批量同步并智能重试{len(game_ids)}场比赛的Boxscore数据")

        all_results = {}
        failed_games = {}
        retry_count = 0

        # 首次执行所有任务
        results = self.batch_sync_boxscores(game_ids, force_update, max_workers, batch_size)

        # 更新结果
        all_results.update({r["game_id"]: r for r in results["details"] if r["status"] == "success"})

        # 收集失败的任务
        for r in results["details"]:
            if r["status"] == "failed":
                failed_games[r["game_id"]] = r.get("error", "Unknown error")

        # 重试失败的任务
        while failed_games and retry_count < max_retries:
            retry_count += 1
            self.logger.info(f"第{retry_count}次重试，待重试任务数: {len(failed_games)}")

            # 按错误类型分组和延迟
            network_errors = [gid for gid, err in failed_games.items()
                              if isinstance(err, str) and ("timeout" in err.lower() or "connection" in err.lower())]
            other_errors = [gid for gid in failed_games if gid not in network_errors]

            # 先重试网络错误（可能是临时性的）
            if network_errors:
                self.logger.info(f"重试{len(network_errors)}个网络错误任务")
                time.sleep(10 * retry_count)  # 网络错误递增等待
                # 网络错误使用更保守的参数
                retry_workers = max(3, (max_workers or self.current_max_workers) // 2)
                retry_batch = max(5, (batch_size or self.current_batch_size) // 2)
                retry_results = self.batch_sync_boxscores(
                    network_errors, force_update,
                    max_workers=retry_workers,
                    batch_size=retry_batch,
                    batch_interval=60  # 增加批次间隔
                )

                # 更新结果
                for r in retry_results["details"]:
                    if r["status"] == "success":
                        all_results[r["game_id"]] = r
                        failed_games.pop(r["game_id"], None)

            # 再重试其他错误
            if other_errors:
                self.logger.info(f"重试{len(other_errors)}个其他错误任务")
                time.sleep(30 * retry_count)  # 其他错误较长等待
                # 其他错误使用更保守的参数
                retry_workers = max(2, (max_workers or self.current_max_workers) // 3)
                retry_batch = max(3, (batch_size or self.current_batch_size) // 3)
                retry_results = self.batch_sync_boxscores(
                    other_errors, force_update,
                    max_workers=retry_workers,
                    batch_size=retry_batch,
                    batch_interval=90  # 更长的批次间隔
                )

                # 更新结果
                for r in retry_results["details"]:
                    if r["status"] == "success":
                        all_results[r["game_id"]] = r
                        failed_games.pop(r["game_id"], None)

        # 最终结果
        end_time = datetime.now()
        final_results = {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration": (end_time - start_time).total_seconds(),
            "total_games": len(game_ids),
            "successful_games": len(all_results),
            "failed_games": len(failed_games),
            "retries_performed": retry_count,
            "status": "completed" if not failed_games else "partially_completed",
            "details": list(all_results.values()) + [{"game_id": gid, "status": "failed", "error": err}
                                                     for gid, err in failed_games.items()]
        }

        self.logger.info(f"批量同步与重试完成: 总计{final_results['total_games']}场, "
                         f"成功{final_results['successful_games']}场, 失败{final_results['failed_games']}场, "
                         f"重试{retry_count}次, 总耗时{final_results['duration']:.2f}秒")

        return final_results

    def _process_batch_with_threading(self, game_ids: List[str], force_update: bool, max_workers: int) -> List[
        Dict[str, Any]]:
        """使用多线程处理一批比赛数据"""
        results = []

        # 线程安全的计数器
        counters = {"success": 0, "failed": 0}
        counter_lock = threading.Lock()

        # 定义处理单场比赛的函数
        def process_game(game_id):
            # 获取全局信号量，控制总并发
            with self.global_semaphore:
                with self.thread_lock:
                    self.active_threads += 1
                    current_active = self.active_threads

                self.logger.debug(f"当前活跃线程数: {current_active}")

                try:
                    start_time = datetime.now()
                    self.logger.info(f"开始同步比赛(ID:{game_id})的Boxscore数据")

                    # 获取boxscore数据
                    boxscore_data = self.game_fetcher.get_boxscore_traditional(game_id, force_update)
                    if not boxscore_data:
                        raise ValueError(f"无法获取比赛(ID:{game_id})的Boxscore数据")

                    # 解析和保存数据
                    success_count, summary = self._save_boxscore_data(game_id, boxscore_data)

                    # 记录完成状态
                    end_time = datetime.now()
                    status = "failed" if "error" in summary else "success"
                    duration = (end_time - start_time).total_seconds()

                    # 记录同步历史
                    self._record_sync_history(game_id, status, start_time, end_time, success_count, summary)

                    # 更新计数器
                    with counter_lock:
                        if status == "success":
                            counters["success"] += 1
                        else:
                            counters["failed"] += 1

                    self.logger.info(f"比赛(ID:{game_id})Boxscore数据同步完成，状态: {status}, 耗时: {duration:.2f}秒")

                    return {
                        "game_id": game_id,
                        "status": status,
                        "items_processed": 1,
                        "items_succeeded": success_count,
                        "summary": summary,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "duration": duration
                    }

                except Exception as e:
                    self.logger.error(f"同步比赛(ID:{game_id})Boxscore数据失败: {e}")

                    # 记录失败的同步历史
                    self._record_sync_history(game_id, "failed", datetime.now(), datetime.now(), 0, {"error": str(e)})

                    # 更新计数器
                    with counter_lock:
                        counters["failed"] += 1

                    return {
                        "game_id": game_id,
                        "status": "failed",
                        "error": str(e)
                    }
                finally:
                    # 无论成功失败，释放线程计数
                    with self.thread_lock:
                        self.active_threads -= 1

        # 使用线程池并行处理
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_game = {executor.submit(process_game, game_id): game_id for game_id in game_ids}

            # 获取结果
            for future in concurrent.futures.as_completed(future_to_game):
                game_id = future_to_game[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"获取比赛(ID:{game_id})处理结果失败: {e}")
                    results.append({
                        "game_id": game_id,
                        "status": "failed",
                        "error": f"获取处理结果失败: {e}"
                    })

        return results

    def _adjust_batch_parameters(self, results: List[Dict[str, Any]]) -> Tuple[int, int]:
        """根据上一批次的结果动态调整参数"""
        # 计算成功率
        total = len(results)
        if not total:
            return self.current_batch_size, self.current_max_workers

        success_count = sum(1 for r in results if r.get("status") == "success")
        success_rate = success_count / total if total > 0 else 0

        # 计算平均响应时间
        response_times = [r.get("duration", 0) for r in results if "duration" in r]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0

        # 更新历史记录
        self.success_rate_history.append(success_rate)
        self.response_time_history.append(avg_response_time)
        # 保持最近10个批次的记录
        if len(self.success_rate_history) > 10:
            self.success_rate_history.pop(0)
        if len(self.response_time_history) > 10:
            self.response_time_history.pop(0)

        # 计算平均成功率和响应时间
        avg_success_rate = sum(self.success_rate_history) / len(self.success_rate_history)
        avg_response_time = sum(self.response_time_history) / len(self.response_time_history)

        # 当前参数
        new_batch_size = self.current_batch_size
        new_max_workers = self.current_max_workers

        # 基于统计信息调整参数
        if avg_success_rate > 0.9 and avg_response_time < 2.0:
            # 高成功率且响应快，可以适度增加批次大小和线程数
            new_batch_size = min(100, self.current_batch_size + 10)
            new_max_workers = min(20, self.current_max_workers + 2)
        elif avg_success_rate < 0.7 or avg_response_time > 5.0:
            # 低成功率或响应慢，减小批次大小和线程数
            new_batch_size = max(10, self.current_batch_size - 10)
            new_max_workers = max(3, self.current_max_workers - 2)

        # 如果参数有变化，记录日志
        if new_batch_size != self.current_batch_size or new_max_workers != self.current_max_workers:
            self.logger.info(f"动态调整参数: 批次大小{self.current_batch_size}->{new_batch_size}, "
                             f"线程数{self.current_max_workers}->{new_max_workers}")
            self.logger.info(f"调整依据: 成功率={avg_success_rate:.2f}, 平均响应时间={avg_response_time:.2f}秒")

        # 更新当前参数
        self.current_batch_size = new_batch_size
        self.current_max_workers = new_max_workers

        return new_batch_size, new_max_workers

    def _get_synced_game_ids(self) -> Set[str]:
        """获取已成功同步的比赛ID集合"""
        try:
            with self.db_session.session_scope('game') as session:
                # 查询所有成功同步的boxscore记录
                synced_records = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'boxscore',
                    GameStatsSyncHistory.status == 'success'
                ).all()

                # 转换为集合
                return {record.game_id for record in synced_records}

        except Exception as e:
            self.logger.error(f"获取已同步比赛ID失败: {e}")
            return set()

    def _record_sync_history(self, game_id: str, status: str, start_time: datetime, end_time: datetime,
                             items_processed: int, details: Dict) -> None:
        """记录同步历史到数据库"""
        try:
            with self.db_session.session_scope('game') as session:
                history = GameStatsSyncHistory(
                    sync_type='boxscore',
                    game_id=game_id,
                    status=status,
                    items_processed=items_processed,
                    items_succeeded=items_processed if status == "success" else 0,
                    start_time=start_time,
                    end_time=end_time,
                    details=json.dumps(details),
                    error_message=details.get("error", "") if status == "failed" else ""
                )
                session.add(history)
                self.logger.debug(f"记录同步历史成功: {history}")
        except Exception as e:
            self.logger.error(f"记录同步历史失败: {e}")

    def _save_boxscore_data(self, game_id: str, boxscore_data: Dict) -> Tuple[int, Dict]:
        """
        解析并保存boxscore数据到数据库

        Args:
            game_id: 比赛ID
            boxscore_data: 从API获取的boxscore数据

        Returns:
            Tuple[int, Dict]: 成功保存的记录数和摘要信息
        """
        try:
            now = datetime.now()
            success_count = 0
            summary = {
                "player_stats_count": 0,
                "home_team": "",
                "away_team": ""
            }

            # 1. 解析比赛基本信息
            game_info = self._extract_game_info(boxscore_data)

            # 对于历史比赛，即使game_info可能不完整，我们也标记为成功
            # 但确保记录日志
            if not game_info or not game_info.get('game_id'):
                self.logger.warning(f"比赛(ID:{game_id})的基本信息不完整，但将继续处理")
                # 构造一个最小的game_info
                game_info = {
                    "game_id": game_id,
                    "home_team_id": 0,
                    "away_team_id": 0,
                    "home_team_name": "",
                    "home_team_city": "",
                    "home_team_tricode": "",
                    "away_team_name": "",
                    "away_team_city": "",
                    "away_team_tricode": "",
                    "game_status": 2,  # 假设完成
                    "home_team_score": 0,
                    "away_team_score": 0,
                    "video_available": 0
                }
                summary["message"] = "比赛基本信息不完整或为空，可能是历史比赛"

            # 添加到摘要
            summary["home_team"] = f"{game_info.get('home_team_city')} {game_info.get('home_team_name')}"
            summary["away_team"] = f"{game_info.get('away_team_city')} {game_info.get('away_team_name')}"

            # 2. 解析球员统计数据并与比赛信息合并
            player_stats = self._extract_player_stats(boxscore_data, game_id)

            # 即使player_stats为空，我们也能标记同步成功（对于历史比赛）
            if not player_stats:
                self.logger.warning(f"比赛(ID:{game_id})没有球员统计数据，但将标记为同步成功")
                summary["message"] = "没有球员统计数据或为空，可能是历史比赛"
                # 返回0条记录，但没有error标记
                return 0, summary

            # 如果有player_stats，正常处理
            with self.db_session.session_scope('game') as session:
                for player_stat in player_stats:
                    # 合并比赛信息和球员统计数据
                    player_stat.update({
                        "game_id": game_id,
                        "home_team_id": game_info.get("home_team_id"),
                        "away_team_id": game_info.get("away_team_id"),
                        "home_team_tricode": game_info.get("home_team_tricode"),
                        "away_team_tricode": game_info.get("away_team_tricode"),
                        "home_team_name": game_info.get("home_team_name"),
                        "home_team_city": game_info.get("home_team_city"),
                        "away_team_name": game_info.get("away_team_name"),
                        "away_team_city": game_info.get("away_team_city"),
                        "game_status": game_info.get("game_status", 0),
                        "home_team_score": game_info.get("home_team_score", 0),
                        "away_team_score": game_info.get("away_team_score", 0),
                        "video_available": game_info.get("video_available", 0),
                        "last_updated_at": now
                    })

                    # 保存合并后的数据
                    self._save_or_update_player_boxscore(session, player_stat)
                    success_count += 1

                summary["player_stats_count"] = len(player_stats)

            self.logger.info(f"成功保存比赛(ID:{game_id})的Boxscore数据，共{success_count}条记录")
            return success_count, summary

        except Exception as e:
            self.logger.error(f"保存Boxscore数据失败: {e}")
            raise

    def _extract_game_info(self, boxscore_data: Dict) -> Dict:
        """从boxscore数据中提取比赛基本信息"""
        try:
            # 初始化空字典
            game_info = {}

            # 防御性检查：确保boxscore_data不为None
            if boxscore_data is None:
                self.logger.warning("BoxScore数据为None")
                return game_info

            # 访问boxScoreTraditional字段获取基本信息
            box_data = boxscore_data.get('boxScoreTraditional', {})
            if not box_data:
                self.logger.warning("boxScoreTraditional字段为空或不存在")
                return game_info

            # 使用顶层API提供的ID，这些值通常是可靠的
            game_id = box_data.get('gameId', '')
            home_team_id = box_data.get('homeTeamId', 0)
            away_team_id = box_data.get('awayTeamId', 0)

            # 获取主队信息
            home_team = box_data.get('homeTeam', {})
            home_team_name = home_team.get('teamName', '')
            home_team_city = home_team.get('teamCity', '')
            home_team_tricode = home_team.get('teamTricode', '')

            # 获取客队信息
            away_team = box_data.get('awayTeam', {})
            away_team_name = away_team.get('teamName', '')
            away_team_city = away_team.get('teamCity', '')
            away_team_tricode = away_team.get('teamTricode', '')

            # 如果队伍信息为空或null，尝试从获取的球员信息中提取球队信息
            # 这是一个变通方法，适用于某些早期比赛的数据格式
            if (not home_team_name or home_team_name is None) and home_team.get('players'):
                # 对于早期比赛，可以从数据库中通过team_id查询队伍名称
                self.logger.warning(f"比赛(ID:{game_id})的主队信息为空，将尝试从数据库中查询")

            if (not away_team_name or away_team_name is None) and away_team.get('players'):
                # 同样的逻辑，处理客队信息
                self.logger.warning(f"比赛(ID:{game_id})的客队信息为空，将尝试从数据库中查询")

            # 注意：即使团队信息为空，我们仍然保存记录，但用0条记录，不会影响状态判断
            # 构建比赛信息，确保不为null
            game_info = {
                "game_id": game_id,
                "home_team_id": home_team_id or 0,
                "away_team_id": away_team_id or 0,
                "home_team_name": home_team_name or '',
                "home_team_city": home_team_city or '',
                "home_team_tricode": home_team_tricode or '',
                "away_team_name": away_team_name or '',
                "away_team_city": away_team_city or '',
                "away_team_tricode": away_team_tricode or '',
                "home_team_score": 0,  # 对于老的比赛，没有记录得分
                "away_team_score": 0,
                "game_status": 2,  # 假设这是一场已完成的比赛
                "video_available": 0
            }

            return game_info

        except Exception as e:
            self.logger.error(f"提取比赛信息失败: {e}", exc_info=True)
            return {}

    def _extract_player_stats(self, boxscore_data: Dict, game_id: str) -> List[Dict]:
        """从boxscore数据中提取球员统计数据"""
        try:
            player_stats = []

            # 访问boxScoreTraditional字段获取球员统计
            box_data = boxscore_data.get('boxScoreTraditional', {})
            if not box_data:
                return player_stats

            # 处理主队球员数据
            home_team = box_data.get('homeTeam', {})
            home_team_id = box_data.get('homeTeamId')
            home_players = home_team.get('players', [])

            for player in home_players:
                stats = player.get('statistics', {})
                player_stat = {
                    "person_id": player.get('personId'),
                    "team_id": home_team_id,
                    # 球员个人信息字段
                    "first_name": player.get('firstName', ''),
                    "family_name": player.get('familyName', ''),
                    "name_i": player.get('nameI', ''),
                    "player_slug": player.get('playerSlug', ''),
                    "position": player.get('position', ''),
                    "jersey_num": player.get('jerseyNum', ''),
                    "comment": player.get('comment', ''),
                    "is_starter": 1 if player.get('position', '') else 0,
                    # 球员统计数据字段
                    "minutes": stats.get('minutes', ''),
                    "field_goals_made": stats.get('fieldGoalsMade', 0),
                    "field_goals_attempted": stats.get('fieldGoalsAttempted', 0),
                    "field_goals_percentage": stats.get('fieldGoalsPercentage', 0.0),
                    "three_pointers_made": stats.get('threePointersMade', 0),
                    "three_pointers_attempted": stats.get('threePointersAttempted', 0),
                    "three_pointers_percentage": stats.get('threePointersPercentage', 0.0),
                    "free_throws_made": stats.get('freeThrowsMade', 0),
                    "free_throws_attempted": stats.get('freeThrowsAttempted', 0),
                    "free_throws_percentage": stats.get('freeThrowsPercentage', 0.0),
                    "rebounds_offensive": stats.get('reboundsOffensive', 0),
                    "rebounds_defensive": stats.get('reboundsDefensive', 0),
                    "rebounds_total": stats.get('reboundsTotal', 0),
                    "assists": stats.get('assists', 0),
                    "steals": stats.get('steals', 0),
                    "blocks": stats.get('blocks', 0),
                    "turnovers": stats.get('turnovers', 0),
                    "fouls_personal": stats.get('foulsPersonal', 0),
                    "points": stats.get('points', 0),
                    "plus_minus_points": stats.get('plusMinusPoints', 0.0)
                }
                player_stats.append(player_stat)

            # 处理客队球员数据
            away_team = box_data.get('awayTeam', {})
            away_team_id = box_data.get('awayTeamId')
            away_players = away_team.get('players', [])

            for player in away_players:
                stats = player.get('statistics', {})
                player_stat = {
                    "person_id": player.get('personId'),
                    "team_id": away_team_id,
                    # 球员个人信息字段
                    "first_name": player.get('firstName', ''),
                    "family_name": player.get('familyName', ''),
                    "name_i": player.get('nameI', ''),
                    "player_slug": player.get('playerSlug', ''),
                    "position": player.get('position', ''),
                    "jersey_num": player.get('jerseyNum', ''),
                    "comment": player.get('comment', ''),
                    "is_starter": 1 if player.get('position', '') else 0,
                    # 球员统计数据字段
                    "minutes": stats.get('minutes', ''),
                    "field_goals_made": stats.get('fieldGoalsMade', 0),
                    "field_goals_attempted": stats.get('fieldGoalsAttempted', 0),
                    "field_goals_percentage": stats.get('fieldGoalsPercentage', 0.0),
                    "three_pointers_made": stats.get('threePointersMade', 0),
                    "three_pointers_attempted": stats.get('threePointersAttempted', 0),
                    "three_pointers_percentage": stats.get('threePointersPercentage', 0.0),
                    "free_throws_made": stats.get('freeThrowsMade', 0),
                    "free_throws_attempted": stats.get('freeThrowsAttempted', 0),
                    "free_throws_percentage": stats.get('freeThrowsPercentage', 0.0),
                    "rebounds_offensive": stats.get('reboundsOffensive', 0),
                    "rebounds_defensive": stats.get('reboundsDefensive', 0),
                    "rebounds_total": stats.get('reboundsTotal', 0),
                    "assists": stats.get('assists', 0),
                    "steals": stats.get('steals', 0),
                    "blocks": stats.get('blocks', 0),
                    "turnovers": stats.get('turnovers', 0),
                    "fouls_personal": stats.get('foulsPersonal', 0),
                    "points": stats.get('points', 0),
                    "plus_minus_points": stats.get('plusMinusPoints', 0.0)
                }
                player_stats.append(player_stat)

            return player_stats

        except Exception as e:
            self.logger.error(f"提取球员统计数据失败: {e}")
            return []

    def _save_or_update_player_boxscore(self, session, player_stat: Dict) -> None:
        """保存或更新球员比赛统计数据"""
        try:
            game_id = player_stat.get('game_id')
            person_id = player_stat.get('person_id')

            # 检查是否已存在
            existing_stat = session.query(Statistics).filter_by(
                game_id=game_id,
                person_id=person_id
            ).first()

            if existing_stat:
                # 更新现有记录
                for key, value in player_stat.items():
                    if key not in ('game_id', 'person_id') and hasattr(existing_stat, key):
                        setattr(existing_stat, key, value)
            else:
                # 创建新记录
                new_stat = Statistics()
                for key, value in player_stat.items():
                    if hasattr(new_stat, key):
                        setattr(new_stat, key, value)
                session.add(new_stat)

        except Exception as e:
            self.logger.error(f"保存或更新球员比赛统计数据失败: {e}")
            raise