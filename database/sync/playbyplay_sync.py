# database/sync/playbyplay_sync.py
import random
from datetime import datetime
from typing import Dict, List, Any, Tuple, Set, Optional
import json
import concurrent.futures
import threading
import time
from requests.exceptions import ReadTimeout, ProxyError
from nba.fetcher.game_fetcher import GameFetcher
from utils.logger_handler import AppLogger
from database.models.stats_models import Event, GameStatsSyncHistory
from database.db_session import DBSession
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import and_, exists

class PlayByPlaySync:
    """
    优化的比赛回合数据同步器
    """

    def __init__(self, playbyplay_repository=None, game_fetcher=None, max_global_concurrency=5):
        """初始化比赛回合数据同步器 - 默认降低并发度"""
        self.db_session = DBSession.get_instance()
        self.playbyplay_repository = playbyplay_repository
        self.game_fetcher = game_fetcher or GameFetcher()
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')

        # 获取game_fetcher中的http_manager引用或创建新的
        self.http_manager = self.game_fetcher.http_manager

        # 添加全局并发控制 - 默认降低并发
        self.global_semaphore = threading.Semaphore(max_global_concurrency)
        self.active_threads = 0
        self.thread_lock = threading.Lock()

        # 批次和线程动态调整参数
        self.current_batch_size = 20  # 初始批次大小 - 降低到20
        self.current_max_workers = 4  # 初始线程数 - 降低到4
        self.success_rate_history = []
        self.response_time_history = []

        # 添加全局的处理计数器
        self.processed_count = 0
        self.processed_lock = threading.Lock()

    def sync_playbyplay(self, game_id: str, force_update: bool = False) -> Dict[str, Any]:
        start_time = datetime.now()
        self.logger.info(f"开始同步比赛(ID:{game_id})的Play-by-Play数据...")
        try:
            # 获取playbyplay数据
            playbyplay_data = self.game_fetcher.get_playbyplay(game_id, force_update)

            # 区分API请求失败和无数据情况
            if playbyplay_data is None:
                # playbyplay_data为None表示API请求失败（超时、连接错误等）
                error_msg = f"API请求失败，无法获取比赛(ID:{game_id})的Play-by-Play数据"
                self.logger.error(error_msg)
                self._record_sync_history(game_id, "failed", start_time, datetime.now(), 0, {"error": error_msg})
                return {
                    "status": "failed",
                    "items_processed": 1,
                    "items_succeeded": 0,
                    "error": error_msg,
                    "start_time": start_time.isoformat(),
                    "end_time": datetime.now().isoformat(),
                    "duration": (datetime.now() - start_time).total_seconds()
                }

            # 检查是否存在有效的回合数据
            if ('game' in playbyplay_data and
                    'actions' in playbyplay_data.get('game', {}) and
                    playbyplay_data['game']['actions']):  # 检查actions数组是否非空
                # 数据存在且有回合数据
                success_count, summary = self._save_playbyplay_data(game_id, playbyplay_data)

                # 记录同步成功
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                self.logger.info(f"比赛(ID:{game_id})的Play-by-Play数据同步成功，耗时: {duration:.2f}秒")
                self._record_sync_history(game_id, "success", start_time, end_time, success_count, summary)
                return {
                    "game_id": game_id,
                    "status": "success",
                    "items_processed": 1,
                    "items_succeeded": success_count,
                    "summary": summary,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "duration": duration
                }
            else:
                # 请求成功但无回合数据（早期比赛）
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                summary = {"message": "没有可用的Play-by-Play数据，可能是早期比赛"}
                self._record_sync_history(game_id, "success", start_time, end_time, 0, summary)
                self.logger.info(
                    f"比赛(ID:{game_id})没有可用的Play-by-Play数据，已记录为同步成功，耗时: {duration:.2f}秒")
                return {
                    "game_id": game_id,
                    "status": "success",
                    "items_processed": 0,
                    "items_succeeded": 0,
                    "summary": summary,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "duration": duration,
                    "no_data": True
                }

        except (ReadTimeout, ProxyError) as e:
            # 请求异常（例如超时或代理问题）
            error_msg = f"请求失败: {e}"
            self.logger.error(f"同步比赛(ID:{game_id})Play-by-Play数据失败: {error_msg}", exc_info=True)
            self._record_sync_history(game_id, "failed", start_time, datetime.now(), 0, {"error": error_msg})
            return {
                "game_id": game_id,
                "status": "failed",
                "items_processed": 0,
                "items_succeeded": 0,
                "error": error_msg,
                "duration": (datetime.now() - start_time).total_seconds()
            }

        except Exception as e:
            # 捕获其他异常
            error_msg = f"同步比赛(ID:{game_id})Play-by-Play数据发生异常: {e}"
            self.logger.error(error_msg, exc_info=True)
            self._record_sync_history(game_id, "failed", start_time, datetime.now(), 0, {"error": error_msg})
            return {
                "game_id": game_id,
                "status": "failed",
                "items_processed": 0,
                "items_succeeded": 0,
                "error": error_msg,
                "duration": (datetime.now() - start_time).total_seconds()
            }

    def batch_sync_playbyplay(self, game_ids: List[str], force_update: bool = False, max_workers: int = 6,
                              batch_size: int = 20, batch_interval: int = 60) -> Dict[str, Any]:
        """
        批量同步多场比赛的Play-by-Play数据，保持传入顺序处理批次

        Args:
            game_ids: 比赛ID列表，将按照此顺序分批处理
            force_update: 是否强制更新
            max_workers: 最大工作线程数
            batch_size: 每批次处理的比赛数量
            batch_interval: 批次间隔时间(秒)

        Returns:
            Dict: 同步结果
        """
        start_time = datetime.now()
        self.logger.info(
            f"开始批量同步{len(game_ids)}场比赛的Play-by-Play数据，最大线程数: {max_workers}, 批次大小: {batch_size}")

        # 记录处理结果
        result = {
            "start_time": start_time.isoformat(),
            "total_games": len(game_ids),
            "processed_games": 0,
            "successful_games": 0,
            "failed_games": 0,
            "no_data_games": 0,
            "details": []
        }

        if not game_ids:
            self.logger.info("没有需要同步的比赛")
            result["status"] = "completed"
            result["end_time"] = datetime.now().isoformat()
            result["duration"] = (datetime.now() - start_time).total_seconds()
            return result

        # 检查已同步的比赛，避免重复处理
        if not force_update:
            already_synced = []
            with self.db_session.session_scope('game') as session:
                for game_id in game_ids:
                    synced = session.query(exists().where(
                        and_(
                            GameStatsSyncHistory.game_id == game_id,
                            GameStatsSyncHistory.sync_type == 'playbyplay',
                            GameStatsSyncHistory.status == 'success'
                        )
                    )).scalar()
                    if synced:
                        already_synced.append(game_id)

            if already_synced:
                self.logger.info(f"跳过{len(already_synced)}场已同步的比赛")
                # 从待处理列表中移除已同步的比赛
                game_ids = [gid for gid in game_ids if gid not in already_synced]
                result["skipped_games"] = len(already_synced)

        if not game_ids:
            self.logger.info("所有比赛已同步，无需处理")
            result["status"] = "completed"
            result["end_time"] = datetime.now().isoformat()
            result["duration"] = (datetime.now() - start_time).total_seconds()
            return result


        # 将比赛分批处理，保持原始排序顺序
        batches = [game_ids[i:i + batch_size] for i in range(0, len(game_ids), batch_size)]
        self.logger.info(f"将{len(game_ids)}场比赛分为{len(batches)}批进行处理")

        # 记录前几个批次的ID以确认顺序正确
        for i, batch in enumerate(batches[:3]):  # 只记录前3批
            if batch:
                self.logger.info(f"批次{i + 1}的前5个比赛ID: {batch[:min(5, len(batch))]}")

        # 设置http_manager的批次间隔
        self.http_manager.set_batch_interval(batch_interval, adaptive=True)

        # 逐批处理 - 批次间严格按顺序，批次内并行
        for batch_idx, batch_game_ids in enumerate(batches):
            # 批次开始时间
            batch_start_time = datetime.now()
            self.logger.info(f"开始处理第{batch_idx + 1}/{len(batches)}批，包含{len(batch_game_ids)}场比赛")

            # 处理当前批次 - 批次内可以并行
            batch_results = []

            # 使用线程池并行处理批次内的比赛
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 创建future到game_id的映射，以便后续按原始顺序收集结果
                future_to_game_id = {
                    executor.submit(self.sync_playbyplay, game_id, force_update): game_id
                    for game_id in batch_game_ids
                }

                # 按照Future完成的顺序处理结果
                for future in as_completed(future_to_game_id):
                    game_id = future_to_game_id[future]
                    try:
                        result_data = future.result()
                        batch_results.append(result_data)
                    except Exception as e:
                        self.logger.error(f"处理比赛(ID:{game_id})时发生错误: {e}", exc_info=True)
                        batch_results.append({
                            "game_id": game_id,
                            "status": "failed",
                            "error": str(e)
                        })

            # 重要：对批次结果按原始game_ids顺序重新排序
            sorted_batch_results = []
            for game_id in batch_game_ids:
                for res in batch_results:
                    if res.get("game_id") == game_id:
                        sorted_batch_results.append(res)
                        break

            # 更新结果统计
            result["processed_games"] += len(sorted_batch_results)
            result["successful_games"] += sum(1 for r in sorted_batch_results if r.get("status") == "success")
            result["failed_games"] += sum(1 for r in sorted_batch_results if r.get("status") == "failed")
            result["no_data_games"] += sum(1 for r in sorted_batch_results if r.get("no_data", False))
            result["details"].extend(sorted_batch_results)

            # 批次处理完成，等待下一批次
            if batch_idx < len(batches) - 1:  # 不是最后一批
                self.http_manager.wait_for_next_batch()


        # 完成统计
        end_time = datetime.now()
        result["status"] = "completed"
        result["end_time"] = end_time.isoformat()
        result["duration"] = (end_time - start_time).total_seconds()

        self.logger.info(f"批量同步完成: 总计{result['total_games']}场, 处理{result['processed_games']}场, "
                         f"成功{result['successful_games']}场, 失败{result['failed_games']}场, "
                         f"无数据{result['no_data_games']}场, 总耗时{result['duration']}秒")

        return result

    def batch_sync_with_retry(self, game_ids: List[str], max_retries=3, force_update: bool = False,
                              max_workers: Optional[int] = None, batch_size: Optional[int] = None) -> Dict[str, Any]:
        """批量同步并智能重试失败的任务"""
        start_time = datetime.now()
        self.logger.info(f"开始批量同步并智能重试{len(game_ids)}场比赛的Play-by-Play数据")

        all_results = {}
        failed_games = {}
        retry_count = 0

        # 首次执行所有任务
        results = self.batch_sync_playbyplay(game_ids, force_update, max_workers, batch_size)

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
                retry_results = self.batch_sync_playbyplay(
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
                retry_results = self.batch_sync_playbyplay(
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
            "no_data_games": sum(1 for r in all_results.values() if r.get("no_data", False)),
            "status": "completed" if not failed_games else "partially_completed",
            "details": list(all_results.values()) + [{"game_id": gid, "status": "failed", "error": err}
                                                     for gid, err in failed_games.items()]
        }

        self.logger.info(f"批量同步与重试完成: 总计{final_results['total_games']}场, "
                         f"成功{final_results['successful_games']}场, 失败{final_results['failed_games']}场, "
                         f"无数据{final_results['no_data_games']}场, 重试{retry_count}次, "
                         f"总耗时{final_results['duration']:.2f}秒")

        return final_results

    def _process_batch_with_threading(self, game_ids: List[str], force_update: bool, max_workers: int) -> List[
        Dict[str, Any]]:
        """使用多线程处理一批比赛数据 - 增强版"""
        results = []

        # 线程安全的计数器
        counters = {"success": 0, "failed": 0, "no_data": 0}
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
                    self.logger.info(f"开始同步比赛(ID:{game_id})的Play-by-Play数据")

                    # 获取playbyplay数据
                    playbyplay_data = self.game_fetcher.get_playbyplay(game_id, force_update)

                    # 更新全局处理计数
                    with self.processed_lock:
                        self.processed_count += 1

                        # 随机添加小暂停，避免请求过于均匀
                        if random.random() < 0.1:  # 10%概率
                            pause = random.uniform(1.0, 3.0)
                            time.sleep(pause)

                    # 处理无数据情况
                    if (not playbyplay_data or
                            'game' not in playbyplay_data or
                            'actions' not in playbyplay_data.get('game', {}) or
                            not playbyplay_data['game']['actions']):
                        summary = {"message": "没有可用的Play-by-Play数据，可能是早期比赛"}

                        self._record_sync_history(game_id, "success", start_time, datetime.now(), 0, summary)

                        with counter_lock:
                            counters["no_data"] += 1

                        self.logger.info(f"比赛(ID:{game_id})没有可用的Play-by-Play数据，已记录为同步成功")
                        return {
                            "game_id": game_id,
                            "status": "success",
                            "items_processed": 0,
                            "items_succeeded": 0,
                            "summary": summary,
                            "start_time": start_time.isoformat(),
                            "end_time": datetime.now().isoformat(),
                            "duration": (datetime.now() - start_time).total_seconds(),
                            "no_data": True
                        }

                    # 解析和保存数据
                    success_count, summary = self._save_playbyplay_data(game_id, playbyplay_data)

                    # 记录完成状态
                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()
                    status = "success" if success_count > 0 else "failed"

                    # 记录同步历史
                    self._record_sync_history(game_id, status, start_time, end_time, success_count, summary)

                    # 更新计数器
                    with counter_lock:
                        if status == "success":
                            counters["success"] += 1
                        else:
                            counters["failed"] += 1

                    self.logger.info(
                        f"比赛(ID:{game_id})Play-by-Play数据同步完成，状态: {status}, 耗时: {duration:.2f}秒")

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
                    error_msg = f"同步比赛(ID:{game_id})Play-by-Play数据失败: {e}"
                    self.logger.error(error_msg)

                    # 记录失败的同步历史
                    self._record_sync_history(game_id, "failed", datetime.now(), datetime.now(), 0, {"error": str(e)})

                    # 更新计数器
                    with counter_lock:
                        counters["failed"] += 1

                    return {
                        "game_id": game_id,
                        "status": "failed",
                        "error": str(e),
                        "duration": (datetime.now() - start_time).total_seconds()
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

    def _adjust_batch_parameters(self, results: List[Dict[str, Any]], batch_idx: int) -> Tuple[int, int]:
        """根据上一批次的结果动态调整参数 - 增强版"""
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
        avg_success_rate = sum(self.success_rate_history) / len(
            self.success_rate_history) if self.success_rate_history else 0
        avg_response_time = sum(self.response_time_history) / len(
            self.response_time_history) if self.response_time_history else 0

        # 当前参数
        new_batch_size = self.current_batch_size
        new_max_workers = self.current_max_workers

        # 错误类型分析
        error_counts = {"timeout": 0, "rate_limit": 0, "connection": 0, "server": 0, "other": 0}
        for r in results:
            if r.get("status") == "failed" and "error" in r:
                error = r["error"].lower()
                if "timeout" in error:
                    error_counts["timeout"] += 1
                elif "429" in error or "rate" in error or "limit" in error:
                    error_counts["rate_limit"] += 1
                elif "connection" in error:
                    error_counts["connection"] += 1
                elif "500" in error or "502" in error or "503" in error or "504" in error:
                    error_counts["server"] += 1
                else:
                    error_counts["other"] += 1

        # 基于批次索引的调整策略
        batch_factor = 1.0
        if batch_idx >= 15:
            # 危险区域 - 批次索引达到15以上时，更保守
            batch_factor = 0.4
            self.logger.warning(f"批次索引({batch_idx})达到高风险区域，应用保守因子: {batch_factor}")
        elif batch_idx >= 10:
            # 警告区域
            batch_factor = 0.6
            self.logger.info(f"批次索引({batch_idx})达到警告区域，应用谨慎因子: {batch_factor}")

        # 基于错误的调整策略
        if error_counts["rate_limit"] > 0 or error_counts["timeout"] > total * 0.2:
            # 速率限制或大量超时
            new_batch_size = max(5, int(self.current_batch_size * 0.5))
            new_max_workers = max(2, int(self.current_max_workers * 0.5))
            self.logger.warning(f"检测到速率限制或大量超时，显著减小参数")
        elif error_counts["server"] > 0 or error_counts["connection"] > 0:
            # 服务器错误或连接问题
            new_batch_size = max(10, int(self.current_batch_size * 0.7))
            new_max_workers = max(2, int(self.current_max_workers * 0.7))
            self.logger.warning(f"检测到服务器错误或连接问题，减小参数")
        elif avg_success_rate < 0.7 or avg_response_time > 5.0:
            # 低成功率或响应慢
            new_batch_size = max(10, int(self.current_batch_size * 0.8))
            new_max_workers = max(2, self.current_max_workers - 1)
            self.logger.info(f"低成功率或响应慢，适度减小参数")
        elif avg_success_rate > 0.95 and avg_response_time < 1.5 and batch_idx < 10:
            # 只有在批次索引较小时才考虑增加参数
            new_batch_size = min(50, int(self.current_batch_size * 1.1))
            new_max_workers = min(8, self.current_max_workers + 1)
            self.logger.info(f"高成功率且响应快，小幅增加参数")

        # 应用批次因子
        new_batch_size = max(5, int(new_batch_size * batch_factor))
        new_max_workers = max(2, int(new_max_workers * batch_factor))

        # 如果参数有变化，记录日志
        if new_batch_size != self.current_batch_size or new_max_workers != self.current_max_workers:
            self.logger.info(f"动态调整参数: 批次大小{self.current_batch_size}->{new_batch_size}, "
                             f"线程数{self.current_max_workers}->{new_max_workers}")
            self.logger.info(f"调整依据: 成功率={avg_success_rate:.2f}, 平均响应时间={avg_response_time:.2f}秒, "
                             f"批次索引={batch_idx}, 错误分布={error_counts}")

        return new_batch_size, new_max_workers

    def _get_synced_game_ids(self) -> Set[str]:
        """获取已成功同步的比赛ID集合"""
        try:
            with self.db_session.session_scope('game') as session:
                # 查询所有成功同步的playbyplay记录
                synced_records = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'playbyplay',
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
        """
        try:
            success_count = 0
            summary = {
                "play_actions_count": 0
            }

            # 提取回合动作
            play_actions = self._extract_play_actions(playbyplay_data, game_id)

            # 即使没有回合动作数据，也应该视为成功同步
            # 因为某些比赛可能就是没有回合数据
            if play_actions:
                with self.db_session.session_scope('game') as session:
                    for action in play_actions:
                        action["game_id"] = game_id
                        self._save_or_update_play_action(session, action)
                        success_count += 1

                summary["play_actions_count"] = len(play_actions)
            else:
                # 没有回合动作数据，但仍然是成功的同步
                summary["message"] = "没有回合动作数据，但同步成功"

            self.logger.info(f"成功保存比赛(ID:{game_id})的PlayByPlay数据，共{success_count}条记录")
            # 即使记录数为0，同步也应该视为成功
            return success_count, summary

        except Exception as e:
            self.logger.error(f"保存PlayByPlay数据失败: {e}")
            raise

    def _extract_play_actions(self, playbyplay_data: Dict, game_id: str) -> List[Dict]:
        """从playbyplay数据中提取具体回合动作"""
        try:
            play_actions = []

            # 从正确的嵌套结构中获取actions数组
            actions = playbyplay_data.get('game', {}).get('actions', [])

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