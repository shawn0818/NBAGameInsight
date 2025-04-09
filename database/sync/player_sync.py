# database/sync/player_sync.py
from datetime import datetime
from typing import Dict, List, Optional, Any
import threading
import time
from nba.fetcher.player_fetcher import PlayerFetcher, PlayerCacheEnum
from utils.logger_handler import AppLogger
from database.models.base_models import Player
from database.db_session import DBSession


class PlayerSync:
    """
    球员数据同步器
    负责从NBA API获取数据、转换并写入数据库
    优化版：充分利用http_handler和base_fetcher中的功能
    """

    def __init__(self, player_repository=None, player_fetcher=None, max_global_concurrency=10):
        """初始化球员数据同步器"""
        self.db_session = DBSession.get_instance()
        self.player_repository = player_repository  # 可选，用于查询
        self.player_fetcher = player_fetcher or PlayerFetcher()
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')

        # 全局并发控制
        self.global_semaphore = threading.Semaphore(max_global_concurrency)
        self.thread_lock = threading.Lock()

        # 确保player_fetcher的http_manager已正确配置
        if hasattr(self.player_fetcher, 'http_manager'):
            self.http_manager = self.player_fetcher.http_manager
            # 设置默认批处理参数
            self.http_manager.set_batch_interval(30, adaptive=True)
        else:
            self.http_manager = None
            self.logger.warning("PlayerFetcher没有提供HTTP管理器，将使用基本请求控制")

    # 同步球员的花名册，包括NBA历史上所有球员
    def sync_players(self, force_update: bool = False) -> bool:
        """
        同步球员数据

        Args:
            force_update: 是否强制更新所有数据

        Returns:
            bool: 同步是否成功
        """
        try:
            # 如果不强制更新，检查是否有数据
            if not force_update and self.player_repository:
                players = self.player_repository.get_all_players()
                if players:
                    self.logger.info(f"数据库中已有{len(players)}名球员数据，跳过同步")
                    return True

            # 获取球员名册数据
            players_data = self.player_fetcher.get_all_players_info()
            if not players_data:
                self.logger.error("获取球员名册数据失败")
                return False

            # 解析球员数据
            parsed_players = self._parse_players_data(players_data)
            if not parsed_players:
                self.logger.error("解析球员数据失败")
                return False

            # 导入数据到数据库
            success_count = self._import_players(parsed_players)
            self.logger.info(f"成功同步{success_count}名球员数据")

            return success_count > 0

        except Exception as e:
            self.logger.error(f"同步球员数据失败: {e}")
            return False

    def _import_players(self, players_data: List[Dict]) -> int:
        """
        将球员数据写入数据库

        Args:
            players_data: 球员数据列表

        Returns:
            int: 成功写入的记录数
        """
        success_count = 0
        new_count = 0
        update_count = 0

        try:
            with self.db_session.session_scope('nba') as session:
                for player_data in players_data:
                    try:
                        person_id = player_data.get('person_id')
                        if not person_id:
                            continue

                        # 检查是否已存在该球员
                        existing_player = session.query(Player).filter(Player.person_id == person_id).first()

                        if existing_player:
                            # 更新现有记录
                            is_changed = False
                            for key, value in player_data.items():
                                if hasattr(existing_player, key):
                                    current_value = getattr(existing_player, key)
                                    if current_value != value:
                                        setattr(existing_player, key, value)
                                        is_changed = True

                            # 如果有修改，更新时间戳
                            if is_changed:
                                if hasattr(existing_player, 'last_updated_at'):
                                    existing_player.last_updated_at = datetime.now()
                                update_count += 1
                                self.logger.debug(
                                    f"更新球员记录: {player_data.get('display_first_last')} (ID: {person_id})")
                        else:
                            # 创建新记录
                            new_player = Player(**player_data)
                            if hasattr(new_player, 'created_at'):
                                new_player.created_at = datetime.now()
                            if hasattr(new_player, 'last_updated_at'):
                                new_player.last_updated_at = datetime.now()
                            session.add(new_player)
                            new_count += 1
                            self.logger.debug(
                                f"新增球员记录: {player_data.get('display_first_last')} (ID: {person_id})")

                        success_count += 1

                    except Exception as e:
                        self.logger.error(f"处理球员记录失败: {e}")
                        # 继续处理下一条记录

                # 提交事务（会在session_scope结束时自动提交）
                self.logger.info(
                    f"成功保存{success_count}/{len(players_data)}名球员数据, 新增: {new_count}, 更新: {update_count}")

        except Exception as e:
            # 异常会在session_scope中被捕获并回滚
            self.logger.error(f"批量保存球员数据失败: {e}")

        return success_count

    def _parse_players_data(self, players_data: Dict) -> List[Dict]:
        """
        解析球员名册数据

        Args:
            players_data: 原始球员数据

        Returns:
            List[Dict]: 解析后的球员数据列表
        """
        parsed_players = []

        try:
            if 'resultSets' not in players_data or not players_data['resultSets']:
                self.logger.error("球员数据格式不正确")
                return []

            players_set = players_data['resultSets'][0]

            # 检查是否有头部和数据
            if 'headers' not in players_set or 'rowSet' not in players_set:
                self.logger.error("球员数据缺少headers或rowSet")
                return []

            # 建立列名到索引的映射
            headers = {name: idx for idx, name in enumerate(players_set['headers'])}

            # 检查必要的字段是否存在
            required_fields = ['PERSON_ID']
            for field in required_fields:
                if field not in headers:
                    self.logger.error(f"球员数据缺少必要字段: {field}")
                    return []

            for player in players_set['rowSet']:
                # 检查数据行是否有足够的元素
                if len(player) <= headers['PERSON_ID']:
                    self.logger.warning(f"球员数据行长度不足: {player}")
                    continue

                # 检查 PERSON_ID 是否为空
                person_id = player[headers['PERSON_ID']]
                if not person_id:
                    self.logger.warning(f"球员ID为空: {player}")
                    continue

                # 安全地获取其他字段
                player_data = {
                    'person_id': person_id,
                    'display_last_comma_first': self._safe_get_value(player, headers, 'DISPLAY_LAST_COMMA_FIRST'),
                    'display_first_last': self._safe_get_value(player, headers, 'DISPLAY_FIRST_LAST'),
                    'player_slug': self._safe_get_value(player, headers, 'PLAYER_SLUG'),
                    'games_played_flag': self._safe_get_value(player, headers, 'GAMES_PLAYED_FLAG'),
                    'otherleague_experience_ch': self._safe_get_value(player, headers, 'OTHERLEAGUE_EXPERIENCE_CH'),
                }

                parsed_players.append(player_data)

            return parsed_players

        except Exception as e:
            self.logger.error(f"解析球员数据失败: {e}")
            return []

    def _safe_get_value(self, row, headers, field_name, default_value=''):
        """安全地从数据行中获取值"""
        if field_name in headers and len(row) > headers[field_name]:
            value = row[headers[field_name]]
            return value if value is not None else default_value
        return default_value

    # 根据球员的花名册，批量同步球员的详细信息 - 优化版本
    def sync_player_details(self, player_ids: Optional[List[int]] = None,
                            force_update: bool = False,
                            only_active: bool = True,
                            max_workers: Optional[int] = None,
                            batch_size: Optional[int] = None,
                            batch_interval: int = 30) -> Dict[str, Any]:
        """
        批量同步球员详细信息 - 利用base_fetcher的批量处理功能

        从commonplayerinfo API获取球员详细数据，包括准确的roster_status、
        身高体重、位置等信息，并更新到球员表中。

        Args:
            player_ids: 指定的球员ID列表，不指定则同步所有符合条件的球员
            force_update: 是否强制更新（对于历史球员，设置为True将跳过缓存获取最新数据）
            only_active: 是否只同步活跃球员
            max_workers: 最大工作线程数
            batch_size: 批处理大小
            batch_interval: 批次之间的间隔时间(秒)

        Returns:
            Dict: 同步结果统计
        """
        start_time = datetime.now()
        self.logger.info(f"开始批量同步球员详细信息，最大线程数: {max_workers}, 批次大小: {batch_size}")

        result = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "total": 0,
            "processed": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "details": []
        }

        try:
            # 1. 获取需要同步的球员ID列表
            sync_player_ids = self._get_player_ids_to_sync(player_ids, only_active)
            if not sync_player_ids:
                self.logger.warning("未找到需要同步的球员ID")
                result["status"] = "failed"
                result["error"] = "未找到需要同步的球员ID"
                return result

            result["total"] = len(sync_player_ids)
            self.logger.info(f"找到{len(sync_player_ids)}名球员需要同步详细信息")

            # 2. 配置HTTP管理器的批处理参数
            if self.http_manager:
                self.http_manager.set_batch_interval(batch_interval, adaptive=True)
                if batch_size:
                    # 告知HTTP管理器预期的批次大小，有助于速率控制
                    self.logger.info(f"设置HTTP管理器批次大小提示: {batch_size}")
                # 重置批次计数器，开始新的同步任务
                self.http_manager.reset_batch_count()

            # 3. 分批处理球员数据 - 使用自定义批处理来保持"分批请求处理"逻辑
            batches = [sync_player_ids[i:i + (batch_size or 50)] for i in
                       range(0, len(sync_player_ids), (batch_size or 50))]
            self.logger.info(f"将{len(sync_player_ids)}名球员分为{len(batches)}批进行处理")

            # 创建处理函数，将被传递给batch_fetch
            def batch_processor(batch_ids: List[int]) -> List[Dict[str, Any]]:
                """处理单个批次的球员数据，返回处理结果"""
                self.logger.info(f"开始处理一批包含{len(batch_ids)}名球员的数据")

                # 利用PlayerFetcher的批量获取功能获取数据
                batch_data = {}
                for player_id in batch_ids:
                    player_info = self.player_fetcher.get_player_info(player_id, force_update)
                    if player_info:
                        batch_data[player_id] = player_info

                # 处理获取到的数据（更新到数据库）
                batch_results = self._process_batch_data(batch_ids, batch_data, only_active)

                # 如果HTTP管理器存在，等待下一批处理
                if self.http_manager and len(batches) > 1:
                    self.http_manager.wait_for_next_batch()

                return batch_results

            # 4. 逐批处理数据
            for batch_idx, batch_player_ids in enumerate(batches):
                self.logger.info(f"开始处理第{batch_idx + 1}/{len(batches)}批，包含{len(batch_player_ids)}名球员")

                # 处理当前批次
                batch_results = batch_processor(batch_player_ids)

                # 更新结果统计
                batch_processed = len(batch_results)
                batch_success = sum(1 for r in batch_results if r.get("status") == "success")
                batch_failed = sum(1 for r in batch_results if r.get("status") == "failed")
                batch_skipped = sum(1 for r in batch_results if r.get("status") == "skipped")

                result["processed"] += batch_processed
                result["success"] += batch_success
                result["failed"] += batch_failed
                result["skipped"] += batch_skipped
                result["details"].extend(batch_results)

                self.logger.info(
                    f"第{batch_idx + 1}批处理完成: 成功{batch_success}名, 失败{batch_failed}名, "
                    f"跳过{batch_skipped}名")

        except Exception as e:
            self.logger.error(f"同步球员详细信息失败: {e}")
            result["status"] = "failed"
            result["error"] = str(e)

        # 计算耗时
        end_time = datetime.now()
        result["end_time"] = end_time.isoformat()
        result["duration"] = (end_time - start_time).total_seconds()

        self.logger.info(f"球员详细信息同步完成: 总计{result['total']}名球员, "
                         f"处理{result['processed']}名, 成功{result['success']}名, "
                         f"失败{result['failed']}名, 跳过{result['skipped']}名, "
                         f"耗时{result['duration']}秒")

        return result

    def _get_player_ids_to_sync(self, specified_ids: Optional[List[int]], only_active: bool) -> List[int]:
        """获取需要同步的球员ID列表"""
        if specified_ids:
            return specified_ids

        sync_player_ids = []
        with self.db_session.session_scope('nba') as session:
            # 查询条件
            query = session.query(Player.person_id)

            if only_active:
                # 优先使用is_active字段（最准确）
                try:
                    query = query.filter(Player.is_active == True)
                    count = query.count()
                    if count > 0:
                        self.logger.info(f"使用is_active字段找到{count}名活跃球员")
                    else:
                        # 如果没有找到活跃球员，回退到使用to_year字段
                        current_year = str(datetime.now().year)
                        query = session.query(Player.person_id).filter(Player.to_year >= current_year)
                        self.logger.info(f"is_active字段查询无结果，回退到使用to_year字段")
                except Exception as e:
                    # 如果is_active字段不存在或查询出错，回退到使用to_year字段
                    current_year = str(datetime.now().year)
                    query = session.query(Player.person_id).filter(Player.to_year >= current_year)
                    self.logger.info(f"is_active字段查询失败: {e}，回退到使用to_year字段")

            sync_player_ids = [p[0] for p in query.all()]

        return sync_player_ids

    def _process_batch_data(self, batch_ids: List[int], batch_data: Dict[int, Dict],
                            only_active: bool) -> List[Dict[str, Any]]:
        """处理一批获取到的球员数据，更新到数据库"""
        results = []

        # 批量处理数据库操作（在单个会话中）
        with self.db_session.session_scope('nba') as session:
            # 批量获取当前批次所有球员记录
            existing_players = session.query(Player).filter(Player.person_id.in_(batch_ids)).all()
            existing_players_map = {player.person_id: player for player in existing_players}

            # 处理每个球员ID
            for player_id in batch_ids:
                try:
                    player_data = batch_data.get(player_id)

                    # 如果没有获取到数据
                    if not player_data:
                        results.append({
                            "player_id": player_id,
                            "status": "failed",
                            "error": "获取数据失败"
                        })
                        continue

                    # 检查是否为活跃球员（如果只处理活跃球员）
                    if only_active:
                        player_status = self.player_fetcher._get_player_status(player_id, player_data)
                        if player_status == PlayerCacheEnum.HISTORICAL:
                            results.append({
                                "player_id": player_id,
                                "status": "skipped",
                                "reason": "历史球员"
                            })
                            continue

                    # 解析球员详细信息
                    player_detail = self._parse_player_detail(player_data)
                    if not player_detail:
                        results.append({
                            "player_id": player_id,
                            "status": "failed",
                            "error": "解析数据失败"
                        })
                        continue

                    # 获取现有球员对象
                    player_in_db = existing_players_map.get(player_id)

                    # 更新到数据库
                    success = self._update_player_detail_to_db(session, player_id, player_detail, player_in_db)

                    if success:
                        results.append({
                            "player_id": player_id,
                            "status": "success",
                            "name": player_detail.get("display_first_last",
                                                      "") or f"{player_detail.get('first_name', '')} {player_detail.get('last_name', '')}",
                            "roster_status": player_detail.get("roster_status", ""),
                            "is_active": player_detail.get("is_active", False)
                        })
                    else:
                        results.append({
                            "player_id": player_id,
                            "status": "failed",
                            "error": "更新数据库失败"
                        })

                except Exception as e:
                    self.logger.error(f"处理球员(ID:{player_id})详细信息失败: {e}")
                    results.append({
                        "player_id": player_id,
                        "status": "failed",
                        "error": str(e)
                    })

        return results

    def batch_sync_player_details_with_retry(self, player_ids: Optional[List[int]] = None,
                                             max_retries: int = 3,
                                             force_update: bool = False,
                                             only_active: bool = True,
                                             max_workers: Optional[int] = None,
                                             batch_size: Optional[int] = None) -> Dict[str, Any]:
        """批量同步球员详细信息并智能重试失败的任务 - 优化版本

        利用HTTP管理器的重试策略，避免重复实现。

        Args:
            player_ids: 指定的球员ID列表，不指定则同步所有符合条件的球员
            max_retries: 最大重试次数
            force_update: 是否强制更新
            only_active: 是否只同步活跃球员
            max_workers: 最大工作线程数
            batch_size: 批处理大小

        Returns:
            Dict: 同步结果统计
        """
        start_time = datetime.now()
        self.logger.info(f"开始批量同步并智能重试球员详细信息")

        all_results = {}
        skipped_results = {}
        failed_players = {}
        retry_count = 0
        original_config = None

        # 如果HTTP管理器存在，配置重试策略
        if self.http_manager and hasattr(self.http_manager, 'retry_strategy'):
            # 为此任务临时设置更激进的重试策略
            from utils.http_handler import RetryConfig
            original_config = self.http_manager.retry_strategy.config
            retry_config = RetryConfig(
                max_retries=max_retries,
                base_delay=5.0,
                max_delay=60.0,
                backoff_factor=1.5,
                jitter_factor=0.2
            )
            self.http_manager.set_retry_config(retry_config)
            self.logger.info("已配置HTTP管理器的重试策略")

        try:
            # 首次执行所有任务
            sync_results = self.sync_player_details(
                player_ids=player_ids,
                force_update=force_update,
                only_active=only_active,
                max_workers=max_workers,
                batch_size=batch_size
            )

            # 更新结果
            all_results.update({r["player_id"]: r for r in sync_results["details"] if r["status"] == "success"})
            skipped_results.update({r["player_id"]: r for r in sync_results["details"] if r["status"] == "skipped"})

            # 收集失败的任务
            for r in sync_results["details"]:
                if r["status"] == "failed":
                    failed_players[r["player_id"]] = r.get("error", "Unknown error")

            # 重试失败的任务，使用更小的批次和更长的间隔
            while failed_players and retry_count < max_retries:
                retry_count += 1
                failed_ids = list(failed_players.keys())
                self.logger.info(f"第{retry_count}次重试，待重试任务数: {len(failed_ids)}")

                # 网络错误和其他错误分组
                network_errors = [pid for pid, err in failed_players.items()
                                  if isinstance(err, str) and ("timeout" in err.lower() or
                                                               "connection" in err.lower() or
                                                               "network" in err.lower())]
                other_errors = [pid for pid in failed_players if int(pid) not in network_errors]

                retry_batch_size = max(5, (batch_size or 50) // 2)  # 减小批次大小
                retry_interval = 60 * retry_count  # 递增批次间隔

                # 先处理网络错误
                if network_errors:
                    self.logger.info(f"重试{len(network_errors)}个网络错误任务")
                    time.sleep(10 * retry_count)  # 网络错误递增等待

                    network_retry_results = self.sync_player_details(
                        player_ids=[int(pid) for pid in network_errors],
                        force_update=force_update,
                        only_active=only_active,
                        batch_size=retry_batch_size,
                        batch_interval=retry_interval
                    )

                    # 直接更新重试结果（内联_update_retry_results逻辑）
                    for r in network_retry_results["details"]:
                        pid = r["player_id"]
                        if r["status"] == "success":
                            all_results[pid] = r
                            failed_players.pop(str(pid), None)
                        elif r["status"] == "skipped":
                            skipped_results[pid] = r
                            failed_players.pop(str(pid), None)

                # 再处理其他错误
                if other_errors:
                    self.logger.info(f"重试{len(other_errors)}个其他错误任务")
                    time.sleep(30 * retry_count)  # 其他错误较长等待

                    other_retry_results = self.sync_player_details(
                        player_ids=[int(pid) for pid in other_errors],
                        force_update=force_update,
                        only_active=only_active,
                        batch_size=max(1, retry_batch_size // 2),  # 更小批次
                        batch_interval=retry_interval * 2  # 更长间隔
                    )

                    # 直接更新重试结果（内联_update_retry_results逻辑）
                    for r in other_retry_results["details"]:
                        pid = r["player_id"]
                        if r["status"] == "success":
                            all_results[pid] = r
                            failed_players.pop(str(pid), None)
                        elif r["status"] == "skipped":
                            skipped_results[pid] = r
                            failed_players.pop(str(pid), None)

        except Exception as e:
            self.logger.error(f"批量同步球员详细信息失败: {e}")
        finally:
            # 恢复原始重试策略
            if self.http_manager and hasattr(self.http_manager, 'retry_strategy') and original_config is not None:
                self.http_manager.retry_strategy.config = original_config
                self.logger.info("已恢复HTTP管理器的原始重试策略")

        # 最终结果
        end_time = datetime.now()
        final_results = {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration": (end_time - start_time).total_seconds(),
            "total": sync_results["total"],
            "successful": len(all_results),
            "failed": len(failed_players),
            "skipped": len(skipped_results),
            "retries_performed": retry_count,
            "status": "completed" if not failed_players else "partially_completed",
            "details": list(all_results.values()) + list(skipped_results.values()) + [
                {"player_id": pid, "status": "failed", "error": err}
                for pid, err in failed_players.items()
            ]
        }

        self.logger.info(f"批量同步与重试完成: 总计{final_results['total']}名球员, "
                         f"成功{final_results['successful']}名, 失败{final_results['failed']}名, "
                         f"跳过{final_results['skipped']}名, 重试{retry_count}次, "
                         f"总耗时{final_results['duration']:.2f}秒")

        return final_results

    def _parse_player_detail(self, detail_data: Dict) -> Dict:
        """
        解析球员详细信息
        从commonplayerinfo API返回的数据中提取所需字段
        """
        if not detail_data or 'resultSets' not in detail_data:
            return {}

        try:
            # 获取CommonPlayerInfo结果集
            player_info = None
            for result_set in detail_data['resultSets']:
                if result_set['name'] == 'CommonPlayerInfo':
                    player_info = result_set
                    break

            if not player_info or not player_info.get('rowSet') or not player_info['rowSet'][0]:
                return {}

            # 获取表头和数据行
            headers = player_info['headers']
            row = player_info['rowSet'][0]

            # 构建字段映射
            data = {}
            for i, header in enumerate(headers):
                if i < len(row):
                    data[header] = row[i]

            # 使用fetcher的方法判断球员是否活跃
            is_active = self.player_fetcher._is_active_player(detail_data)

            # 获取原始的roster_status值
            roster_status = data.get('ROSTERSTATUS')

            # 提取需要的字段
            player_detail = {
                # 基本信息
                'first_name': data.get('FIRST_NAME'),
                'last_name': data.get('LAST_NAME'),

                # 个人信息
                'birthdate': data.get('BIRTHDATE'),
                'school': data.get('SCHOOL'),
                'country': data.get('COUNTRY'),
                'last_affiliation': data.get('LAST_AFFILIATION'),
                'height': data.get('HEIGHT'),
                'weight': data.get('WEIGHT'),
                'season_exp': data.get('SEASON_EXP'),
                'position': data.get('POSITION'),
                'jersey': data.get('JERSEY'),

                # 职业信息 - 从commonplayerinfo获取的准确值
                'roster_status': roster_status,  # 保持原始值，不转换为数字
                'from_year': data.get('FROM_YEAR'),
                'to_year': data.get('TO_YEAR'),
                'draft_year': data.get('DRAFT_YEAR'),
                'draft_round': data.get('DRAFT_ROUND'),
                'draft_number': data.get('DRAFT_NUMBER'),
                'greatest_75_flag': data.get('GREATEST_75_FLAG'),

                # 球队相关信息
                'team_id': data.get('TEAM_ID'),
                'team_name': data.get('TEAM_NAME'),
                'team_city': data.get('TEAM_CITY'),
                'team_abbreviation': data.get('TEAM_ABBREVIATION'),
                'team_code': data.get('TEAM_CODE'),
                'playercode': data.get('PLAYERCODE'),

                # 其他信息
                'dleague_flag': data.get('DLEAGUE_FLAG'),
                'nba_flag': data.get('NBA_FLAG'),
                'games_played_flag': data.get('GAMES_PLAYED_FLAG'),

                # 是否活跃 - 使用fetcher的判断结果
                'is_active': is_active,
                'last_synced': datetime.now()
            }

            return player_detail

        except Exception as e:
            self.logger.error(f"解析球员详细信息失败: {e}")
            return {}

    def _update_player_detail_to_db(self, session, player_id: int, player_detail: Dict, player=None) -> bool:
        """
        更新球员详细信息到数据库

        使用commonplayerinfo API获取的数据更新球员记录

        Args:
            session: 数据库会话
            player_id: 球员ID
            player_detail: 球员详细信息
            player: 已查询的球员对象(可选)，如果为None则自动查询

        Returns:
            bool: 是否更新成功
        """
        try:
            # 如果没有传入 player 对象，尝试在当前会话中查询
            if player is None:
                player = session.query(Player).filter(Player.person_id == player_id).first()

            if player:
                # 更新球员记录
                is_changed = False
                for key, value in player_detail.items():
                    if hasattr(player, key) and value is not None:
                        # 只有在值不同时才更新
                        current_value = getattr(player, key)
                        if current_value != value:
                            setattr(player, key, value)
                            is_changed = True

                # 如果有字段被修改，更新 last_updated_at 字段
                if is_changed and hasattr(player, 'last_updated_at'):
                    player.last_updated_at = datetime.now()

                self.logger.info(
                    f"更新球员 {player_detail.get('first_name')} {player_detail.get('last_name')} (ID: {player_id}) 的详细信息, "
                    f"roster_status: {player_detail.get('roster_status')}, "
                    f"is_active: {player_detail.get('is_active')}, "
                    f"{'有字段变更' if is_changed else '无字段变更'}")
                return True
            else:
                self.logger.warning(f"未找到ID为 {player_id} 的球员记录")
                return False

        except Exception as e:
            self.logger.error(f"更新球员ID {player_id} 详细信息到数据库失败: {e}")
            return False