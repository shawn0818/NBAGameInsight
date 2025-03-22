# database/db_service.py
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
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.env = env

        # 获取单例实例
        self.db_session = DBSession.get_instance()
        self.sync_manager = SyncManager()

        # 标记初始化状态
        self._initialized = False

    def initialize(self, create_tables: bool = False) -> bool:
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
            return True
        except Exception as e:
            self.logger.error(f"数据库服务初始化失败: {e}", exc_info=True)
            return False

    def sync_all_data(self, force_update: bool = False) -> Dict[str, Any]:
        """执行全量数据同步

        Args:
            force_update: 是否强制更新所有数据

        Returns:
            Dict[str, Any]: 同步结果摘要
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行同步")
            return {"status": "failed", "error": "数据库服务未初始化"}

        return self.sync_manager.sync_all(force_update)

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
        """获取球队ID

        Args:
            team_name: 球队名称

        Returns:
            Optional[int]: 球队ID，如果未找到则返回None
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行查询")
            return None

        try:
            with self.db_session.session_scope('nba') as session:
                # 在这里实现查询逻辑
                # 示例实现，具体逻辑需要根据你的数据库模型调整
                from database.models.base_models import Team
                team = session.query(Team).filter(Team.name.like(f"%{team_name}%")).first()
                if team:
                    return team.team_id
                return None
        except Exception as e:
            self.logger.error(f"获取球队ID失败: {e}", exc_info=True)
            return None

    def get_player_id_by_name(self, player_name: str) -> Optional[Union[int, List[int]]]:
        """获取球员ID

        Args:
            player_name: 球员名称

        Returns:
            Optional[Union[int, List[int]]]: 球员ID或ID列表，如果未找到则返回None
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行查询")
            return None

        try:
            with self.db_session.session_scope('nba') as session:
                # 在这里实现查询逻辑
                # 示例实现，具体逻辑需要根据你的数据库模型调整
                from database.models.base_models import Player
                players = session.query(Player).filter(Player.name.like(f"%{player_name}%")).all()
                if not players:
                    return None
                if len(players) == 1:
                    return players[0].player_id
                return [player.player_id for player in players]
        except Exception as e:
            self.logger.error(f"获取球员ID失败: {e}", exc_info=True)
            return None

    def get_game_id(self, team_id: int, date_str: str = "last") -> Optional[str]:
        """查找指定球队在特定日期的比赛ID

        Args:
            team_id: 球队ID
            date_str: 日期字符串，默认为"last"表示最近一场比赛

        Returns:
            Optional[str]: 比赛ID，如果未找到则返回None
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行查询")
            return None

        try:
            with self.db_session.session_scope('nba') as session:
                # 在这里实现查询逻辑
                # 示例实现，具体逻辑需要根据你的数据库模型调整
                from database.models.base_models import Game
                from sqlalchemy import or_, and_, desc

                if date_str.lower() == "last":
                    # 查询最近一场比赛
                    game = session.query(Game).filter(
                        or_(
                            Game.home_team_id == team_id,
                            Game.away_team_id == team_id
                        )
                    ).order_by(desc(Game.game_date)).first()
                else:
                    # 查询特定日期的比赛
                    game = session.query(Game).filter(
                        and_(
                            or_(
                                Game.home_team_id == team_id,
                                Game.away_team_id == team_id
                            ),
                            Game.game_date == date_str
                        )
                    ).first()

                if game:
                    return game.game_id
                return None
        except Exception as e:
            self.logger.error(f"获取比赛ID失败: {e}", exc_info=True)
            return None

    def get_latest_game_for_team(self, team_name: str) -> Dict[str, Any]:
        """获取指定球队的最近一场比赛信息

        Args:
            team_name: 球队名称

        Returns:
            Dict: 包含game_id和其他比赛基本信息的字典
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行查询")
            return {"error": "数据库服务未初始化"}

        try:
            # 获取球队ID
            team_id = self.get_team_id_by_name(team_name)
            if not team_id:
                return {"error": f"未找到球队: {team_name}"}

            # 查询最近一场比赛
            with self.db_session.session_scope('nba') as session:
                from database.models.base_models import Game, Team
                from sqlalchemy import or_, desc

                # 查询并加载关联数据
                game = session.query(Game).filter(
                    or_(
                        Game.home_team_id == team_id,
                        Game.away_team_id == team_id
                    )
                ).order_by(desc(Game.game_date)).first()

                if not game:
                    return {"error": f"未找到{team_name}的比赛记录"}

                # 获取对阵双方信息
                home_team = session.query(Team).filter(Team.team_id == game.home_team_id).first()
                away_team = session.query(Team).filter(Team.team_id == game.away_team_id).first()

                # 构建比赛信息
                result = {
                    "game_id": game.game_id,
                    "date": game.game_date.strftime("%Y-%m-%d") if game.game_date else "Unknown",
                    "home_team": {
                        "id": game.home_team_id,
                        "name": home_team.name if home_team else "Unknown",
                        "tricode": home_team.tricode if home_team else "???"
                    },
                    "away_team": {
                        "id": game.away_team_id,
                        "name": away_team.name if away_team else "Unknown",
                        "tricode": away_team.tricode if away_team else "???"
                    },
                    "status": game.game_status
                }

                return result

        except Exception as e:
            self.logger.error(f"获取球队最近比赛信息失败: {e}", exc_info=True)
            return {"error": str(e)}

    def get_player_games(self, player_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取指定球员的比赛记录

        Args:
            player_name: 球员名称
            limit: 返回记录数量限制

        Returns:
            List[Dict]: 比赛记录列表
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行查询")
            return [{"error": "数据库服务未初始化"}]

        try:
            # 获取球员ID
            player_id = self.get_player_id_by_name(player_name)
            if not player_id:
                return [{"error": f"未找到球员: {player_name}"}]

            # 简化处理：假设player_id是单值
            if isinstance(player_id, list):
                player_id = player_id[0]

            # 查询球员比赛记录
            with self.db_session.session_scope('nba') as session:
                from database.models.base_models import Game, PlayerGame, Team
                from sqlalchemy import desc

                # 查询球员参与的比赛
                query = session.query(Game, PlayerGame) \
                    .join(PlayerGame, Game.game_id == PlayerGame.game_id) \
                    .filter(PlayerGame.player_id == player_id) \
                    .order_by(desc(Game.game_date)) \
                    .limit(limit)

                results = []
                for game, player_game in query.all():
                    # 获取对阵双方信息
                    home_team = session.query(Team).filter(Team.team_id == game.home_team_id).first()
                    away_team = session.query(Team).filter(Team.team_id == game.away_team_id).first()

                    # 构建比赛信息
                    game_info = {
                        "game_id": game.game_id,
                        "date": game.game_date.strftime("%Y-%m-%d") if game.game_date else "Unknown",
                        "home_team": {
                            "id": game.home_team_id,
                            "name": home_team.name if home_team else "Unknown",
                            "tricode": home_team.tricode if home_team else "???"
                        },
                        "away_team": {
                            "id": game.away_team_id,
                            "name": away_team.name if away_team else "Unknown",
                            "tricode": away_team.tricode if away_team else "???"
                        },
                        "status": game.game_status,
                        "player_stats": {
                            "minutes": player_game.minutes,
                            "points": player_game.points,
                            "rebounds": player_game.rebounds,
                            "assists": player_game.assists
                        }
                    }
                    results.append(game_info)

                return results

        except Exception as e:
            self.logger.error(f"获取球员比赛记录失败: {e}", exc_info=True)
            return [{"error": str(e)}]

    def close(self) -> None:
        """关闭数据库连接"""
        if self._initialized:
            try:
                self.db_session.close_all()
                self.logger.info("数据库连接已关闭")
            except Exception as e:
                self.logger.error(f"关闭数据库连接失败: {e}", exc_info=True)

