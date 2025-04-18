"""
数据同步命令模块 - 处理数据库同步和更新相关操作
"""
from typing import Dict, Any

from commands.base_command import NBACommand, error_handler


class BaseSyncCommand(NBACommand):
    """同步命令基类"""
    pass


class SyncCommand(BaseSyncCommand):
    """增量并行同步比赛统计数据命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("增量并行同步比赛统计数据 (gamedb)")
        if not app.nba_service or not app.nba_service.db_service:
            print("× 数据库服务不可用，无法执行同步。")
            return False

        print("开始使用多线程并行同步未同步过的比赛统计数据...")
        print("这将优先处理最新的比赛。")
        if app.config.force_update:
            print("注意：已启用 --force-update，将强制重新同步所有找到的比赛，即使它们之前已同步。")

        max_workers = app.config.max_workers
        batch_size = app.config.batch_size
        print(f"最大线程数: {max_workers}, 批次大小: {batch_size}")

        result = app.nba_service.db_service.sync_remaining_data_parallel(
            force_update=app.config.force_update,
            max_workers=max_workers,
            batch_size=batch_size,
            reverse_order=True
        )

        # 处理结果
        if result.get("status") in ["success", "partially_failed", "completed"]:
            # 显示详细结果
            total_games = result.get("total_games", 0)
            synced_games = result.get("synced_games", 0)
            failed_games = result.get("failed_games", 0)
            skipped_games = result.get("skipped_games", 0)
            duration = result.get("duration", 0)

            print(f"\n同步结果摘要:")
            print(f"  总计游戏: {total_games}")
            print(f"  成功同步: {synced_games}")
            print(f"  同步失败: {failed_games}")
            print(f"  已跳过(已同步): {skipped_games}")
            print(f"\n总耗时: {duration:.2f}秒")

            return result.get("status") != "failed"
        else:
            error = result.get("error", "未知错误")
            print(f"× 增量并行同步失败: {error}")
            return False


class NewSeasonCommand(BaseSyncCommand):
    """新赛季核心数据同步命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("新赛季核心数据同步 (nba.db)")
        if not app.nba_service or not app.nba_service.db_service:
            print("× 数据库服务不可用，无法执行同步。")
            return False

        print("开始同步新赛季核心数据：强制更新球队、球员，并同步当前赛季赛程...")
        if not app.config.force_update:
            print("提示: 未使用 --force-update，将只更新不存在或需要更新的数据。建议新赛季使用 --force-update。")

        result = app.nba_service.db_service.sync_new_season_core_data(
            force_update=app.config.force_update
        )

        # 处理结果
        if result.get("status") in ["success", "partially_failed"]:
            # 显示详细结果
            details = result.get("details", {})

            print("\n同步结果摘要:")

            # 球队同步结果
            teams_result = details.get("teams", {})
            print(f"  球队同步: {teams_result.get('status', '未知')}")
            if "updated_teams" in teams_result:
                print(f"    更新球队数: {teams_result.get('updated_teams', 0)}")

            # 球员同步结果
            players_result = details.get("players", {})
            print(f"  球员同步: {players_result.get('status', '未知')}")
            if "updated_players" in players_result:
                print(f"    更新球员数: {players_result.get('updated_players', 0)}")

            # 赛程同步结果
            schedules_result = details.get("schedules", {})
            print(f"  赛程同步: {schedules_result.get('status', '未知')}")
            if "updated_games" in schedules_result:
                print(f"    更新赛程数: {schedules_result.get('updated_games', 0)}")

            print(f"\n总耗时: {result.get('duration', 0):.2f}秒")

            return result.get("status") == "success"
        else:
            error = result.get("error", "未知错误")
            print(f"× 新赛季核心数据同步失败: {error}")
            return False


class SyncPlayerDetailsCommand(BaseSyncCommand):
    """同步球员详细信息命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("同步球员详细信息")
        if not app.nba_service or not app.nba_service.db_service:
            print("× 数据库服务不可用，无法执行同步。")
            return False

        print("开始同步球员详细信息...")
        only_active = not app.config.force_update
        if not only_active:
            print("注意：已启用 --force-update，将同步所有球员的详细信息...")
        else:
            print("默认只同步可能活跃球员的详细信息...")

        result = app.nba_service.db_service.sync_player_details(
            force_update=app.config.force_update,
            only_active=only_active
        )

        # 处理结果
        if result.get("status") in ["success", "partially_completed"]:
            # 显示详细结果
            total_players = result.get("total_players", 0)
            synced_players = result.get("synced_players", 0)
            failed_players = result.get("failed_players", 0)
            skipped_players = result.get("skipped_players", 0)
            duration = result.get("duration", 0)

            print(f"\n同步结果摘要:")
            print(f"  总计球员: {total_players}")
            print(f"  成功同步: {synced_players}")
            print(f"  同步失败: {failed_players}")
            print(f"  已跳过(不活跃或已同步): {skipped_players}")
            print(f"\n总耗时: {duration:.2f}秒")

            return result.get("status") == "success"
        else:
            error = result.get("error", "未知错误")
            print(f"× 同步球员详细信息失败: {error}")
            return False