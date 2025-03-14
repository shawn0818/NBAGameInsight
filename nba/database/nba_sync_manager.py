import time
import json
import random
from datetime import datetime
from typing import Dict,  Optional, Any, Callable

from nba.database.player_repository import PlayerRepository
from nba.database.team_repository import TeamRepository
from nba.database.schedule_repository import ScheduleRepository
from nba.database.player_sync import PlayerSync
from nba.database.team_sync import TeamSync
from nba.database.schedule_sync import ScheduleSync
from utils.logger_handler import AppLogger


class NBASyncManager:
    """
    NBA数据同步管理器
    根据NBA赛季周期特点，优化数据同步策略
    """

    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 2  # 指数退避基数（秒）

    def __init__(self, db_manager, config=None):
        """初始化同步管理器"""
        self.db_manager = db_manager
        self.config = config or {}
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')

        # 初始化仓库(只用于查询)
        self.team_repository = TeamRepository(db_manager)
        self.player_repository = PlayerRepository(db_manager)
        self.schedule_repository = ScheduleRepository(db_manager)

        # 初始化同步器(负责数据获取和写入)
        # 注意：传递db_manager用于写入、team_repository用于查询
        self.team_sync = TeamSync(db_manager, self.team_repository)

        # 获取 league_fetcher 用于其他同步器
        league_fetcher = self.team_sync.league_fetcher


        # 初始化球员和赛程同步器
        self.player_sync = PlayerSync(db_manager, self.player_repository, league_fetcher)
        self.schedule_sync = ScheduleSync(db_manager, schedule_repository=self.schedule_repository)

        # 更新历史记录表
        self._init_sync_history_table()
        self._init_sync_progress_table()  # 新增进度跟踪表

    def _init_sync_history_table(self):
        """初始化同步历史记录表"""
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type TEXT NOT NULL,
                season TEXT,
                status TEXT NOT NULL,
                items_processed INTEGER,
                items_succeeded INTEGER,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                details TEXT,
                error_message TEXT
            )
            ''')
            self.db_manager.conn.commit()
            self.logger.info("同步历史记录表初始化完成")
        except Exception as e:
            self.logger.error(f"初始化同步历史记录表失败: {e}")

    def _init_sync_progress_table(self):
        """初始化同步进度跟踪表"""
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS sync_progress (
                sync_type TEXT PRIMARY KEY,
                last_synced TEXT,
                last_updated TIMESTAMP,
                state TEXT
            )
            ''')
            self.db_manager.conn.commit()
            self.logger.info("同步进度跟踪表初始化完成")
        except Exception as e:
            self.logger.error(f"初始化同步进度跟踪表失败: {e}")

    def _record_sync_history(self, sync_type, status, season=None, items_processed=0,
                             items_succeeded=0, start_time=None, end_time=None,
                             details=None, error_message=None):
        """记录同步历史"""
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute('''
            INSERT INTO sync_history
            (sync_type, season, status, items_processed, items_succeeded, 
             start_time, end_time, details, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                sync_type, season, status, items_processed, items_succeeded,
                start_time, end_time,
                details if details else "",
                error_message if error_message else ""
            ))
            self.db_manager.conn.commit()
        except Exception as e:
            self.logger.error(f"记录同步历史失败: {e}")

    def _update_sync_progress(self, sync_type, last_synced=None, state=None):
        """更新同步进度"""
        try:
            cursor = self.db_manager.conn.cursor()
            now = datetime.now().isoformat()

            # 检查是否已存在该类型的记录
            cursor.execute("SELECT sync_type FROM sync_progress WHERE sync_type = ?", (sync_type,))
            exists = cursor.fetchone()

            if exists:
                # 更新现有记录
                if state is not None:
                    state_json = json.dumps(state)
                    cursor.execute('''
                    UPDATE sync_progress 
                    SET last_synced = ?, last_updated = ?, state = ?
                    WHERE sync_type = ?
                    ''', (last_synced, now, state_json, sync_type))
                else:
                    cursor.execute('''
                    UPDATE sync_progress 
                    SET last_synced = ?, last_updated = ?
                    WHERE sync_type = ?
                    ''', (last_synced, now, sync_type))
            else:
                # 插入新记录
                state_json = json.dumps(state) if state is not None else None
                cursor.execute('''
                INSERT INTO sync_progress 
                (sync_type, last_synced, last_updated, state)
                VALUES (?, ?, ?, ?)
                ''', (sync_type, last_synced, now, state_json))

            self.db_manager.conn.commit()
            self.logger.debug(f"更新同步进度: {sync_type}, last_synced: {last_synced}")
        except Exception as e:
            self.logger.error(f"更新同步进度失败: {e}")

    def _get_sync_progress(self, sync_type):
        """获取同步进度"""
        try:
            cursor = self.db_manager.conn.cursor()
            cursor.execute('''
            SELECT last_synced, state FROM sync_progress
            WHERE sync_type = ?
            ''', (sync_type,))

            result = cursor.fetchone()
            if result:
                last_synced = result[0]
                state = json.loads(result[1]) if result[1] else None
                return {
                    'last_synced': last_synced,
                    'state': state
                }
            return None
        except Exception as e:
            self.logger.error(f"获取同步进度失败: {e}")
            return None

    def _with_retry(self, func, *args, max_retries=None, **kwargs):
        """
        使用指数退避重试机制执行操作

        Args:
            func: 要执行的函数
            max_retries: 最大重试次数，默认使用类常量
            *args, **kwargs: 传递给func的参数

        Returns:
            返回func的执行结果或在多次失败后抛出最后一个异常
        """
        if max_retries is None:
            max_retries = self.MAX_RETRIES

        last_error = None
        for attempt in range(max_retries + 1):  # +1 表示初始尝试加上重试次数
            try:
                if attempt > 0:
                    # 计算指数退避延迟
                    delay = self.RETRY_DELAY_BASE ** attempt + random.uniform(0, 1)
                    self.logger.info(f"尝试第 {attempt} 次重试，等待 {delay:.2f} 秒...")
                    time.sleep(delay)

                return func(*args, **kwargs)

            except Exception as e:
                last_error = e
                error_type = type(e).__name__
                self.logger.warning(f"操作失败 (尝试 {attempt + 1}/{max_retries + 1}): {error_type}: {e}")

                # 对于某些不应该重试的错误类型，直接抛出
                if any(err_type in error_type for err_type in ["PermissionError", "KeyboardInterrupt"]):
                    raise

        # 如果执行到这里，说明所有重试都失败了
        self.logger.error(f"在 {max_retries + 1} 次尝试后操作仍然失败: {last_error}")
        raise last_error

    def _execute_sync_operation(self,
                                sync_type: str,
                                operation_func: Callable,
                                season: Optional[str] = None,
                                force_update: bool = False,
                                record_progress: bool = True,
                                **kwargs) -> Dict[str, Any]:
        """
        通用同步操作执行器，处理开始/结束时间、异常处理和历史记录

        Args:
            sync_type: 同步类型
            operation_func: 执行具体同步操作的函数
            season: 赛季标识
            force_update: 是否强制更新
            record_progress: 是否记录进度
            **kwargs: 传递给operation_func的其他参数

        Returns:
            Dict: 包含同步结果的字典
        """
        start_time = datetime.now().isoformat()
        self.logger.info(f"开始 {sync_type} 同步..." + (f" 赛季: {season}" if season else ""))

        try:
            # 使用重试机制执行同步操作
            result = self._with_retry(
                operation_func,
                force_update=force_update,
                **kwargs
            )

            # 确定操作状态
            if isinstance(result, dict):
                status = result.get("status", "unknown")
                items_processed = result.get("total", result.get("count", 0))
                items_succeeded = result.get("count", 0)
            elif isinstance(result, bool):
                status = "success" if result else "failed"
                items_processed = 0
                items_succeeded = 0
            elif isinstance(result, int):
                status = "success" if result > 0 else "failed"
                items_processed = result
                items_succeeded = result
            else:
                status = "unknown"
                items_processed = 0
                items_succeeded = 0

            # 记录同步历史
            end_time = datetime.now().isoformat()
            details = json.dumps(result) if isinstance(result, dict) else None

            self._record_sync_history(
                sync_type, status, season,
                items_processed, items_succeeded,
                start_time, end_time, details,
                None if status == "success" else f"{sync_type} 同步未完全成功"
            )

            # 如果需要，更新同步进度
            if record_progress:
                progress_data = {
                    'items_processed': items_processed,
                    'items_succeeded': items_succeeded,
                    'last_sync_time': end_time
                }
                self._update_sync_progress(sync_type, season, progress_data)

            self.logger.info(f"{sync_type} 同步完成，状态: {status}" +
                             (f", 处理: {items_processed}, 成功: {items_succeeded}" if items_processed > 0 else ""))

            return {
                "status": status,
                "season": season,
                "start_time": start_time,
                "end_time": end_time,
                "items_processed": items_processed,
                "items_succeeded": items_succeeded,
                "result": result
            }

        except Exception as e:
            error_msg = f"{sync_type} 同步失败: {e}"
            self.logger.error(error_msg, exc_info=True)

            # 记录失败历史
            end_time = datetime.now().isoformat()
            self._record_sync_history(
                sync_type, "failed", season, 0, 0,
                start_time, end_time, None, str(e)
            )

            return {
                "status": "failed",
                "error": str(e),
                "season": season,
                "start_time": start_time,
                "end_time": end_time
            }

    def initial_data_sync(self, force_update=False):
        """
        首次运行时执行全量数据同步
        包括所有球队、球员和历史赛程数据
        """
        start_time = datetime.now().isoformat()
        self.logger.info("开始初始化全量数据同步...")

        results = {
            "teams": {"status": "pending", "count": 0},
            "players": {"status": "pending", "count": 0},
            "schedule": {"status": "pending", "count": 0, "seasons": {}}
        }

        try:
            # 1. 先同步球队数据
            self.logger.info("开始同步球队数据...")
            team_result = self.sync_teams(force_update)
            results["teams"] = team_result.get("result", team_result)

            time.sleep(2)  # 短暂延迟，API请求间隔

            # 2. 再同步球员数据
            self.logger.info("开始同步球员数据...")
            player_result = self.sync_players(force_update)
            results["players"] = player_result.get("result", player_result)

            time.sleep(2)  # 短暂延迟，API请求间隔

            # 3. 同步所有历史赛季赛程
            self.logger.info("开始同步历史赛程数据...")
            schedule_result = self.sync_all_seasons(force_update=force_update)
            results["schedule"] = schedule_result.get("result", schedule_result)

            # 计算总体状态
            status = "success"
            if any(r.get("status") == "failed" for r in results.values()):
                status = "failed"
            elif any(r.get("status") == "partial" for r in results.values()):
                status = "partial"

            # 记录结果
            end_time = datetime.now().isoformat()

            self._record_sync_history(
                "initial_sync", status, None,
                sum(r.get("items_processed", r.get("count", 0)) for r in results.values()),
                sum(r.get("items_succeeded", r.get("count", 0)) for r in results.values()),
                start_time, end_time, json.dumps(results),
                None if status == "success" else "初始化同步未完全成功"
            )

            self.logger.info(f"初始化全量数据同步完成，状态: {status}")
            return {
                "status": status,
                "results": results,
                "start_time": start_time,
                "end_time": end_time
            }

        except Exception as e:
            error_msg = f"初始化全量数据同步失败: {e}"
            self.logger.error(error_msg)
            end_time = datetime.now().isoformat()

            self._record_sync_history(
                "initial_sync", "failed", None, 0, 0,
                start_time, end_time, json.dumps(results), str(e)
            )

            return {
                "status": "failed",
                "error": str(e),
                "results": results
            }

    def new_season_sync(self, season=None):
        """
        新赛季开始时的同步操作
        更新球队和球员数据

        Args:
            season: 赛季标识，如"2024-25"，默认使用当前赛季
        """
        season = season or self.schedule_sync.schedule_fetcher.schedule_config.CURRENT_SEASON
        start_time = datetime.now().isoformat()
        self.logger.info(f"开始新赛季 {season} 同步...")

        results = {
            "teams": {"status": "pending", "count": 0},
            "players": {"status": "pending", "count": 0},
            "schedule": {"status": "pending", "count": 0}
        }

        try:
            # 1. 更新球队数据（相对稳定，但可能有变更）
            self.logger.info("更新球队数据...")
            team_result = self.sync_teams(force_update=True)  # 强制更新以确保数据为最新
            results["teams"] = team_result.get("result", team_result)

            time.sleep(2)  # 防止API限流

            # 2. 更新球员数据（新秀加入，球员转会等）
            self.logger.info("更新球员数据...")
            player_result = self.sync_players(force_update=True)  # 强制更新以包含新球员
            results["players"] = player_result.get("result", player_result)

            # 3. 同步新赛季赛程
            self.logger.info(f"同步 {season} 赛季赛程...")
            schedule_result = self.sync_current_season(force_update=True)
            results["schedule"] = schedule_result.get("result", schedule_result)

            # 计算总体状态
            status = "success"
            if any(r.get("status") == "failed" for r in results.values()):
                status = "failed"
            elif any(r.get("status") == "partial" for r in results.values()):
                status = "partial"

            # 记录结果
            end_time = datetime.now().isoformat()

            self._record_sync_history(
                "new_season", status, season,
                sum(r.get("items_processed", r.get("count", 0)) for r in results.values()),
                sum(r.get("items_succeeded", r.get("count", 0)) for r in results.values()),
                start_time, end_time, json.dumps(results),
                None if status == "success" else "新赛季同步未完全成功"
            )

            # 更新同步进度
            self._update_sync_progress("current_season", season)

            self.logger.info(f"新赛季 {season} 同步完成，状态: {status}")
            return {
                "status": status,
                "season": season,
                "results": results
            }

        except Exception as e:
            error_msg = f"新赛季 {season} 同步失败: {e}"
            self.logger.error(error_msg)
            end_time = datetime.now().isoformat()

            self._record_sync_history(
                "new_season", "failed", season, 0, 0,
                start_time, end_time, json.dumps(results), str(e)
            )

            return {
                "status": "failed",
                "error": str(e),
                "season": season,
                "results": results
            }

    def update_current_schedule(self, force_update=True):
        """
        更新当前赛季赛程
        用于常规维护，频率可以是每天或每周

        Args:
            force_update: 是否强制更新，默认为True
        """
        # 直接使用内部实现方法，避免循环调用
        current_season = self.schedule_sync.schedule_fetcher.schedule_config.CURRENT_SEASON
        return self._execute_sync_operation(
            "current_season",
            self._sync_current_season_internal,
            season=current_season,
            force_update=force_update
        )

    def sync_teams(self, force_update=False):
        """同步球队数据"""
        return self._execute_sync_operation(
            "team",
            self._sync_teams_internal,
            force_update=force_update
        )

    def _sync_teams_internal(self, force_update=False):
        """内部同步球队数据实现"""
        try:
            # 同步球队详细信息
            result = self.team_sync.sync_team_details(force_update)

            # 同步球队Logo
            logo_result = self.team_sync.sync_team_logos()

            status = "success" if result else "failed"
            team_count = len(self.team_repository.get_all_teams())

            return {
                "status": status,
                "count": team_count,
                "logos_synced": logo_result
            }

        except Exception as e:
            self.logger.error(f"同步球队数据失败: {e}")
            raise

    def sync_players(self, force_update=False):
        """同步球员数据"""
        return self._execute_sync_operation(
            "player",
            self._sync_players_internal,
            force_update=force_update
        )

    def _sync_players_internal(self, force_update=False):
        """内部同步球员数据实现"""
        try:
            result = self.player_sync.sync_players(force_update)

            status = "success" if result else "failed"
            player_count = len(self.player_repository.get_all_players()) if hasattr(self.player_repository,
                                                                                    "get_all_players") else 0

            return {
                "status": status,
                "count": player_count
            }

        except Exception as e:
            self.logger.error(f"同步球员数据失败: {e}")
            raise

    def sync_all_seasons(self, start_from_season=None, force_update=False):
        """
        同步所有赛季的赛程数据，支持断点续传

        Args:
            start_from_season: 从哪个赛季开始同步，None表示从上次中断点或最早赛季开始
            force_update: 是否强制更新

        Returns:
            Dict: 同步结果
        """
        # 如果没有指定起始赛季，尝试从上次同步点继续
        if start_from_season is None:
            progress = self._get_sync_progress("all_seasons")
            if progress and not force_update:
                start_from_season = progress.get('last_synced')
                self.logger.info(f"从上次同步点继续: {start_from_season}")

        return self._execute_sync_operation(
            "all_seasons",
            self._sync_all_seasons_internal,
            start_from_season=start_from_season,
            force_update=force_update,
            record_progress=True
        )

    def _sync_all_seasons_internal(self, start_from_season=None, force_update=False):
        """内部同步所有赛季实现，支持断点续传"""
        try:
            # 获取所有赛季
            all_seasons = self.schedule_sync.schedule_fetcher.get_all_seasons()
            if not all_seasons:
                raise Exception("无法获取赛季列表")

            # 如果指定了起始赛季，则只同步该赛季及之后的
            if start_from_season:
                try:
                    start_idx = all_seasons.index(start_from_season)
                    seasons_to_sync = all_seasons[start_idx:]
                except ValueError:
                    self.logger.warning(f"找不到指定的起始赛季: {start_from_season}，将从头开始同步")
                    seasons_to_sync = all_seasons
            else:
                seasons_to_sync = all_seasons

            total_seasons = len(seasons_to_sync)
            self.logger.info(f"准备同步 {total_seasons} 个赛季")

            season_results = {}
            for i, season in enumerate(seasons_to_sync):
                self.logger.info(f"正在同步赛季 {season} 的数据... ({i + 1}/{total_seasons})")

                # 更新当前处理的赛季，以便中断后可以从这里继续
                self._update_sync_progress("all_seasons", season)

                # 检查数据库中该赛季的数据量
                existing_count = 0
                if self.schedule_repository:
                    existing_count = self.schedule_repository.get_schedules_count_by_season(season)

                if existing_count > 0 and not force_update:
                    self.logger.info(f"赛季 {season} 已有 {existing_count} 场比赛数据，跳过同步")
                    season_results[season] = existing_count
                    continue

                # 同步单个赛季，最后一个赛季不应用延迟
                apply_delay = (i < total_seasons - 1)
                try:
                    result = self._with_retry(
                        self.schedule_sync.sync_season,
                        season, force_update, apply_delay
                    )
                    season_results[season] = result
                except Exception as e:
                    self.logger.error(f"同步赛季 {season} 失败: {e}")
                    season_results[season] = 0

                # 随机延迟，防止API限流
                if apply_delay:
                    delay = random.uniform(1.0, 3.0)
                    self.logger.debug(f"赛季间延迟 {delay:.2f} 秒")
                    time.sleep(delay)

            total_games = sum(season_results.values())
            status = "success" if total_games > 0 else "failed"

            return {
                "status": status,
                "count": total_games,
                "seasons": season_results,
                "total_seasons": len(season_results)
            }

        except Exception as e:
            self.logger.error(f"同步所有赛季赛程数据失败: {e}")
            raise

    def sync_current_season(self, force_update=True):
        """
        同步当前赛季的赛程数据
        """
        current_season = self.schedule_sync.schedule_fetcher.schedule_config.CURRENT_SEASON
        return self._execute_sync_operation(
            "current_season",
            self._sync_current_season_internal,
            season=current_season,
            force_update=force_update
        )

    def _sync_current_season_internal(self, force_update=True):
        """内部同步当前赛季实现"""
        try:
            current_season = self.schedule_sync.schedule_fetcher.schedule_config.CURRENT_SEASON

            # 同步当前赛季
            success_count = self.schedule_sync.sync_current_season(force_update)
            status = "success" if success_count > 0 else "failed"

            return {
                "status": status,
                "count": success_count,
                "season": current_season
            }

        except Exception as e:
            self.logger.error(f"同步当前赛季赛程数据失败: {e}")
            raise

    def is_first_run(self):
        """
        检查是否是首次运行
        通过检查同步历史记录和数据库内容来判断
        """
        try:
            # 检查是否有同步历史
            cursor = self.db_manager.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sync_history")
            history_count = cursor.fetchone()[0]

            if history_count > 0:
                return False

            # 检查是否有球队数据
            teams_count = len(self.team_repository.get_all_teams())
            if teams_count > 0:
                return False

            # 如果没有历史记录和球队数据，则认为是首次运行
            return True

        except Exception as e:
            self.logger.error(f"检查首次运行状态失败: {e}")
            # 保守起见，返回False
            return False

    def get_last_sync_status(self, sync_type=None):
        """获取最近一次同步状态"""
        try:
            cursor = self.db_manager.conn.cursor()

            if sync_type:
                cursor.execute("""
                SELECT * FROM sync_history 
                WHERE sync_type = ? 
                ORDER BY id DESC LIMIT 1
                """, (sync_type,))
            else:
                cursor.execute("""
                SELECT * FROM sync_history 
                ORDER BY id DESC LIMIT 1
                """)

            result = cursor.fetchone()
            return dict(result) if result else None

        except Exception as e:
            self.logger.error(f"获取同步状态失败: {e}")
            return None

    def get_sync_progress(self, sync_type=None):
        """
        获取同步进度信息

        Args:
            sync_type: 同步类型，None表示获取所有类型的进度

        Returns:
            Dict或List[Dict]: 同步进度信息
        """
        try:
            cursor = self.db_manager.conn.cursor()

            if sync_type:
                cursor.execute("""
                SELECT sync_type, last_synced, last_updated, state
                FROM sync_progress 
                WHERE sync_type = ?
                """, (sync_type,))

                result = cursor.fetchone()
                if result:
                    return {
                        'sync_type': result[0],
                        'last_synced': result[1],
                        'last_updated': result[2],
                        'state': json.loads(result[3]) if result[3] else None
                    }
                return None
            else:
                cursor.execute("""
                SELECT sync_type, last_synced, last_updated, state
                FROM sync_progress
                ORDER BY last_updated DESC
                """)

                results = []
                for row in cursor.fetchall():
                    results.append({
                        'sync_type': row[0],
                        'last_synced': row[1],
                        'last_updated': row[2],
                        'state': json.loads(row[3]) if row[3] else None
                    })
                return results

        except Exception as e:
            self.logger.error(f"获取同步进度失败: {e}")
            return None

    def reset_sync_progress(self, sync_type=None):
        """
        重置同步进度

        Args:
            sync_type: 要重置的同步类型，None表示重置所有

        Returns:
            bool: 是否成功
        """
        try:
            cursor = self.db_manager.conn.cursor()

            if sync_type:
                cursor.execute("DELETE FROM sync_progress WHERE sync_type = ?", (sync_type,))
                self.logger.info(f"已重置同步进度: {sync_type}")
            else:
                cursor.execute("DELETE FROM sync_progress")
                self.logger.info("已重置所有同步进度")

            self.db_manager.conn.commit()
            return True

        except Exception as e:
            self.logger.error(f"重置同步进度失败: {e}")
            self.db_manager.conn.rollback()
            return False

    def check_data_integrity(self):
        """
        检查数据完整性

        Returns:
            Dict: 数据完整性检查结果
        """
        issues = []

        try:
            cursor = self.db_manager.conn.cursor()

            # 检查球员-球队关系
            cursor.execute("""
            SELECT COUNT(*) as count FROM player
            WHERE team_id IS NOT NULL AND team_id NOT IN (SELECT team_id FROM team)
            """)
            invalid_player_teams = cursor.fetchone()[0]
            if invalid_player_teams > 0:
                issues.append({
                    'type': 'invalid_player_team_relation',
                    'count': invalid_player_teams,
                    'description': f"{invalid_player_teams}名球员关联了不存在的球队ID"
                })

            # 检查赛程-球队关系
            cursor.execute("""
            SELECT COUNT(*) as count FROM schedule
            WHERE home_team_id NOT IN (SELECT team_id FROM team)
            OR away_team_id NOT IN (SELECT team_id FROM team)
            """)
            invalid_schedule_teams = cursor.fetchone()[0]
            if invalid_schedule_teams > 0:
                issues.append({
                    'type': 'invalid_schedule_team_relation',
                    'count': invalid_schedule_teams,
                    'description': f"{invalid_schedule_teams}场比赛关联了不存在的球队ID"
                })

            # 检查是否有空的必要字段
            cursor.execute("""
            SELECT COUNT(*) as count FROM team
            WHERE nickname IS NULL OR abbreviation IS NULL
            """)
            invalid_teams = cursor.fetchone()[0]
            if invalid_teams > 0:
                issues.append({
                    'type': 'invalid_team_data',
                    'count': invalid_teams,
                    'description': f"{invalid_teams}支球队缺少必要信息"
                })

            cursor.execute("""
            SELECT COUNT(*) as count FROM player
            WHERE display_first_last IS NULL
            """)
            invalid_players = cursor.fetchone()[0]
            if invalid_players > 0:
                issues.append({
                    'type': 'invalid_player_data',
                    'count': invalid_players,
                    'description': f"{invalid_players}名球员缺少必要信息"
                })

            return {
                'has_issues': len(issues) > 0,
                'issue_count': len(issues),
                'issues': issues
            }

        except Exception as e:
            self.logger.error(f"数据完整性检查失败: {e}")
            return {
                'has_issues': True,
                'issue_count': 1,
                'issues': [
                    {
                        'type': 'check_failed',
                        'description': f"检查过程出错: {e}"
                    }
                ]
            }