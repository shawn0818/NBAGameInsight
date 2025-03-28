# database/db_service.py
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from database.db_session import DBSession
from database.sync.sync_manager import SyncManager
from utils.logger_handler import AppLogger



class DatabaseService:
    """数据库服务统一接口

    提供数据库访问和同步操作的高级API，隐藏底层实现细节。
    作为应用程序与数据库之间的中间层，简化数据库操作。
    """

    def __init__(self, env: str = "default"):
        """初始化数据库服务

        Args:
            env: 环境名称，可以是 "default", "test", "development", "production"
        """
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')
        self.env = env

        # 获取单例实例
        self.db_session = DBSession.get_instance()
        self.sync_manager = SyncManager()

        # 初始化各个Repository
        from database.repositories.schedule_repository import ScheduleRepository
        from database.repositories.team_repository import TeamRepository
        from database.repositories.player_repository import PlayerRepository
        from database.repositories.boxscore_repository import BoxscoreRepository
        from database.repositories.playbyplay_repository import PlayByPlayRepository

        self.schedule_repo = ScheduleRepository()
        self.team_repo = TeamRepository()
        self.player_repo = PlayerRepository()
        self.boxscore_repo = BoxscoreRepository()
        self.playbyplay_repo = PlayByPlayRepository()

        # 标记初始化状态
        self._initialized = False

    def initialize(self, create_tables: bool = True) -> bool:  # 修改默认值为True
        """初始化数据库连接和服务

        Args:
            create_tables: 是否创建表结构

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 初始化数据库会话
            self.db_session.initialize(env=self.env, create_tables=create_tables)
            self._initialized = True
            self.logger.info(f"数据库服务初始化成功，环境: {self.env}")

            # 检查核心数据库是否为空，如果为空则自动同步
            if self._is_nba_database_empty():
                self.logger.info("检测到核心数据库为空，开始自动同步基础数据...")
                # 同步核心数据（球队、球员）
                sync_result = self._sync_core_data(force_update=True)
                if sync_result.get("status") == "success":
                    self.logger.info("核心数据同步成功")
                else:
                    self.logger.warning(f"核心数据同步部分失败: {sync_result}")

            return True
        except Exception as e:
            self.logger.error(f"数据库服务初始化失败: {e}", exc_info=True)
            return False

    def _is_nba_database_empty(self) -> bool:
        """检查核心数据库是否为空"""
        if not self._initialized:
            return True

        try:
            with self.db_session.session_scope('nba') as session:
                from database.models.base_models import Team
                # 检查是否有任何球队记录
                team_count = session.query(Team).count()
                return team_count == 0
        except Exception as e:
            self.logger.error(f"检查核心数据库是否为空失败: {e}", exc_info=True)
            return False

    def _sync_core_data(self, force_update: bool = False) -> Dict[str, Any]:
        """同步nba.db的所有核心数据"""
        self.logger.info("开始同步nba.db核心数据...")

        # 调用sync_all方法进行全量同步，但跳过统计数据同步
        return self.sync_manager.sync_all(force_update, skip_game_stats=True)

    def sync_all_data(self, force_update: bool = False) -> Dict[str, Any]:
        """执行全量数据同步（串行方式）

        Args:
            force_update: 是否强制更新所有数据

        Returns:
            Dict[str, Any]: 同步结果摘要
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行同步")
            return {"status": "failed", "error": "数据库服务未初始化"}

        return self.sync_manager.sync_all(force_update)
        
    def sync_all_data_parallel(self, force_update: bool = False, max_workers: int = 10, 
                              batch_size: int = 50) -> Dict[str, Any]:
        """并行执行全量数据同步
        
        使用多线程并发同步所有比赛统计数据，显著提高同步效率。
        
        Args:
            force_update: 是否强制更新所有数据
            max_workers: 最大工作线程数
            batch_size: 每批处理的比赛数量
            
        Returns:
            Dict[str, Any]: 同步结果摘要
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行并行同步")
            return {"status": "failed", "error": "数据库服务未初始化"}
            
        # 同步基础数据（球队、球员、赛程）
        self.logger.info("开始同步基础数据...")
        core_data_result = self._sync_core_data(force_update)
        
        # 然后并行同步所有比赛统计数据
        self.logger.info("开始并行同步所有比赛统计数据...")
        game_stats_result = self.sync_manager.sync_all_game_stats_parallel(
            force_update=force_update,
            max_workers=max_workers,
            batch_size=batch_size
        )
        
        # 构建结果
        result = {
            "status": "success" if core_data_result.get("status") == "success" and 
                                 game_stats_result.get("status") != "failed" else "partially_failed",
            "core_data": core_data_result,
            "game_stats": game_stats_result
        }
        
        return result

    def sync_game_stats(self, game_id: str, force_update: bool = False) -> Dict[str, Any]:
        """同步特定比赛的统计数据

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新

        Returns:
            Dict[str, Any]: 同步结果
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行同步")
            return {"status": "failed", "error": "数据库服务未初始化"}

        return self.sync_manager.sync_game_stats(game_id, force_update)
        
    def sync_remaining_data_parallel(self, force_update: bool = False, max_workers: int = 10, 
                                   batch_size: int = 50) -> Dict[str, Any]:
        """并行同步剩余未同步的比赛统计数据
        
        仅同步尚未同步的比赛数据，使用多线程提高效率。
        
        Args:
            force_update: 是否强制更新数据
            max_workers: 最大工作线程数
            batch_size: 每批处理的比赛数量
            
        Returns:
            Dict[str, Any]: 同步结果摘要
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行并行同步")
            return {"status": "failed", "error": "数据库服务未初始化"}
            
        # 并行同步剩余的比赛统计数据
        self.logger.info("开始并行同步剩余未同步的比赛统计数据...")
        result = self.sync_manager.sync_remaining_game_stats_parallel(
            force_update=force_update,
            max_workers=max_workers,
            batch_size=batch_size
        )
        
        return result

    def sync_new_season(self, season: str, force_update: bool = False) -> bool:
        """同步新赛季数据

        Args:
            season: 赛季标识，例如 "2025-26"
            force_update: 是否强制更新

        Returns:
            bool: 同步是否成功
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法同步新赛季数据")
            return False

        # 同步赛程
        schedule_result = self.sync_manager.sync_schedules(force_update=force_update)
        if schedule_result.get("status") != "success":
            self.logger.error(f"同步赛程失败: {schedule_result}")
            return False

        self.logger.info(f"新赛季 {season} 数据同步成功")
        return True

    def get_team_id_by_name(self, team_name: str) -> Optional[int]:
        """获取球队ID"""
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行查询")
            return None

        try:
            return self.team_repo.get_team_id_by_name(team_name)
        except Exception as e:
            self.logger.error(f"获取球队ID失败: {e}", exc_info=True)
            return None

    def get_player_id_by_name(self, player_name: str) -> Optional[Union[int, List[int]]]:
        """获取球员ID"""
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行查询")
            return None

        try:
            return self.player_repo.get_player_id_by_name(player_name)
        except Exception as e:
            self.logger.error(f"获取球员ID失败: {e}", exc_info=True)
            return None

    def get_game_id(self, team_id: int, date_str: str = "last") -> Optional[str]:
        """查找指定球队在特定日期的比赛ID"""
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行查询")
            return None

        try:
            # 使用ScheduleRepository的方法获取比赛ID
            if date_str.lower() == 'last':
                # 获取上一场比赛
                last_game = self.schedule_repo.get_team_last_schedule(team_id)
                if last_game:
                    game_id = last_game.get('game_id')
                    # 处理ISO格式的时间戳（带有T和时区信息）
                    if 'game_date_time_bjs' in last_game and last_game['game_date_time_bjs']:
                        try:
                            from datetime import datetime
                            import re

                            # 处理ISO格式 (2025-03-27T07:30:00+08:00)
                            time_str = last_game['game_date_time_bjs']

                            # 使用正则表达式分离日期和时间部分
                            match = re.match(r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2}).*', time_str)
                            if match:
                                date_part, time_part = match.groups()
                                # 解析日期和时间
                                dt = datetime.strptime(f"{date_part} {time_part}", '%Y-%m-%d %H:%M:%S')
                                formatted_time = dt.strftime('%Y年%m月%d日 %H:%M')
                            else:
                                # 尝试直接解析
                                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                                formatted_time = dt.strftime('%Y年%m月%d日 %H:%M')
                        except Exception as e:
                            # 如果解析失败，记录错误并使用原始值
                            self.logger.debug(f"日期解析失败: {e}, 使用原始值: {last_game['game_date_time_bjs']}")
                            formatted_time = last_game['game_date_time_bjs']

                    # 如果没有完整字段，尝试其他格式（保留原有的回退逻辑）
                    elif ('game_date_bjs' in last_game and last_game['game_date_bjs']) and \
                            ('game_time_bjs' in last_game and last_game['game_time_bjs']):
                        try:
                            date_str = last_game['game_date_bjs']
                            time_str = last_game['game_time_bjs']
                            from datetime import datetime

                            # 根据实际数据格式调整解析格式
                            dt = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M:%S')
                            formatted_time = dt.strftime('%Y年%m月%d日 %H:%M')
                        except Exception:
                            # 如果解析失败，简单拼接日期和时间
                            formatted_time = f"{last_game['game_date_bjs']} {last_game['game_time_bjs']}"

                    # 只有日期没有时间
                    elif 'game_date_bjs' in last_game and last_game['game_date_bjs']:
                        try:
                            from datetime import datetime
                            dt = datetime.strptime(last_game['game_date_bjs'], '%Y-%m-%d')
                            formatted_time = dt.strftime('%Y年%m月%d日')
                        except Exception:
                            formatted_time = last_game['game_date_bjs']

                    # 最后回退到普通日期
                    else:
                        formatted_time = last_game.get('game_date', '未知日期')

                    self.logger.info(f"找到最近已完成的比赛: ID={game_id}, 北京时间={formatted_time}")
                    return game_id
                else:
                    self.logger.warning(f"未找到球队ID={team_id}的最近比赛")
                    return None
            else:
                # 使用ScheduleRepository的get_game_id方法
                return self.schedule_repo.get_game_id(team_id, date_str)
        except Exception as e:
            self.logger.error(f"获取比赛ID失败: {e}", exc_info=True)
            return None


    def get_sync_progress(self) -> Dict[str, Any]:
        """获取同步进度统计
        
        获取当前所有比赛的同步状态统计信息
        
        Returns:
            Dict: 包含同步进度统计的字典
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法获取同步进度")
            return {"error": "数据库服务未初始化"}
            
        try:
            # 获取所有已完成比赛总数
            with self.db_session.session_scope('nba') as session:
                from database.models.base_models import Game
                total_finished_games = session.query(Game).filter(
                    Game.game_status == 3
                ).count()
                
            # 获取已同步的boxscore比赛数
            with self.db_session.session_scope('game') as session:
                from database.models.stats_models import GameStatsSyncHistory
                synced_games = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'boxscore',
                    GameStatsSyncHistory.status == 'success'
                ).distinct().count()
                
            # 计算进度
            progress_percentage = 0
            if total_finished_games > 0:
                progress_percentage = (synced_games / total_finished_games) * 100
                
            result = {
                "total_games": total_finished_games,
                "synced_games": synced_games,
                "remaining_games": total_finished_games - synced_games,
                "progress_percentage": round(progress_percentage, 2),
                "timestamp": datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"获取同步进度失败: {e}", exc_info=True)
            return {"error": str(e)}

    def close(self) -> None:
        """关闭数据库连接"""
        if self._initialized:
            try:
                self.db_session.close_all()
                self.logger.info("数据库连接已关闭")
            except Exception as e:
                self.logger.error(f"关闭数据库连接失败: {e}", exc_info=True)