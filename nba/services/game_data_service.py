from typing import Dict, Any, Optional, List, Union
from nba.services.game_details_service import GameDetailsProvider
from database.db_service import DatabaseService
from utils.logger_handler import AppLogger


class ServiceNotAvailableError(Exception):
    """服务不可用异常"""
    pass


class GameDataService:
    """NBA游戏数据服务 - 统一数据聚合与访问接口

    该服务作为数据聚合器(Aggregator)和外观(Facade)，负责：
    1. 协调调用GameDetailsProvider和DatabaseService获取数据
    2. 统一处理数据组合和聚合逻辑
    3. 为NBAService提供一致的数据访问接口
    4. 集中处理数据获取错误和异常情况
    """

    def __init__(
            self,
            db_service: Optional[DatabaseService] = None,
            detail_service: Optional[GameDetailsProvider] = None
    ):
        """初始化GameDataService

        Args:
            db_service: 数据库服务实例
            detail_service: 比赛数据提供者实例
        """
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        # 保存依赖服务
        self._db_service = db_service
        self._detail_service = detail_service

        # 服务状态追踪
        self._service_status = {
            'db_service': {'available': self._db_service is not None},
            'detail_service': {'available': self._detail_service is not None}
        }

        self.logger.info("GameDataService初始化完成")

    @property
    def db_service(self) -> DatabaseService:
        """获取数据库服务实例，如不可用则抛出异常"""
        if not self._db_service:
            self.logger.error("数据库服务不可用")
            raise ServiceNotAvailableError("数据库服务不可用")
        return self._db_service

    @property
    def detail_service(self) -> GameDetailsProvider:
        """获取数据提供者实例，如不可用则抛出异常"""
        if not self._detail_service:
            self.logger.error("数据提供者服务不可用")
            raise ServiceNotAvailableError("数据提供者服务不可用")
        return self._detail_service

    def get_game(self, team: Optional[str] = None, date: Optional[str] = "last", force_update: bool = False) -> \
            Optional[Any]:
        """获取比赛数据

        通过调用数据库服务和数据提供者服务，获取指定球队在指定日期的比赛数据。

        Args:
            team: 球队名称
            date: 日期字符串，默认获取最近一场比赛
            force_update: 是否强制更新

        Returns:
            Optional[Any]: 比赛数据对象
        """
        try:
            # 记录请求信息
            self.logger.info(f"尝试获取球队 {team} 的比赛数据，日期参数: {date}")

            # 1. 获取球队ID
            team_id = self.get_team_id_by_name(team)
            if not team_id:
                self.logger.error(f"未找到球队: {team}")
                return None

            self.logger.info(f"获取到球队ID: {team_id}")

            # 2. 获取比赛ID
            game_id = self.db_service.get_game_id(team_id, date)
            if not game_id:
                self.logger.error(f"未找到比赛ID，球队: {team}, 日期: {date}")
                return None

            self.logger.info(f"获取到比赛ID: {game_id}")

            # 3. 使用game_id获取比赛数据
            game = self.detail_service.get_game(game_id, force_update=force_update)
            if not game:
                self.logger.error(f"未找到比赛数据，比赛ID: {game_id}")
                return None

            return game

        except ServiceNotAvailableError as e:
            self.logger.error(f"获取比赛数据失败: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"获取比赛数据失败: {str(e)}", exc_info=True)
            return None

    def get_enhanced_game(self, team: Optional[str] = None, date: Optional[str] = "last",
                          include_player_details: bool = False, force_update: bool = False) -> Dict[str, Any]:
        """获取增强的比赛数据

        获取基础比赛数据，并增加额外的上下文信息和关联数据。

        Args:
            team: 球队名称
            date: 日期字符串，默认获取最近一场比赛
            include_player_details: 是否包含详细球员信息
            force_update: 是否强制更新

        Returns:
            Dict[str, Any]: 增强的比赛数据字典
        """
        try:
            # 获取基础比赛数据
            game = self.get_game(team, date, force_update)
            if not game:
                return {"status": "error", "message": "获取比赛数据失败"}

            # 准备返回结果
            result = {
                "status": "success",
                "game": game,
                "context": {}
            }

            # 获取主客队ID
            home_team_id = game.game_data.home_team.team_id
            away_team_id = game.game_data.away_team.team_id

            # 添加球队详细信息
            try:
                result["context"]["teams"] = {
                    "home": self.db_service.team_repo.get_team_by_id(home_team_id),
                    "away": self.db_service.team_repo.get_team_by_id(away_team_id)
                }
            except Exception as e:
                self.logger.warning(f"获取球队详情失败: {e}")
                result["context"]["teams"] = {}

            # 根据需要添加球员详细信息
            if include_player_details:
                try:
                    player_ids = []
                    # 收集主队球员ID
                    for player in game.game_data.home_team.players:
                        player_ids.append(player.person_id)
                    # 收集客队球员ID
                    for player in game.game_data.away_team.players:
                        player_ids.append(player.person_id)

                    # 批量获取球员详情
                    player_details = {}
                    for player_id in player_ids:
                        player_info = self.db_service.player_repo.get_player_by_id(player_id)
                        if player_info:
                            player_details[player_id] = player_info

                    result["context"]["players"] = player_details
                except Exception as e:
                    self.logger.warning(f"获取球员详情失败: {e}")
                    result["context"]["players"] = {}

            return result

        except Exception as e:
            self.logger.error(f"获取增强比赛数据失败: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"获取增强比赛数据失败: {str(e)}"
            }

    def get_team_id_by_name(self, team_name: str) -> Optional[int]:
        """获取球队ID

        通过名称查找球队ID。

        Args:
            team_name: 球队名称

        Returns:
            Optional[int]: 球队ID，如未找到则返回None
        """
        try:
            return self.db_service.get_team_id_by_name(team_name)
        except ServiceNotAvailableError:
            self.logger.error("获取球队ID失败: 数据库服务不可用")
            return None
        except Exception as e:
            self.logger.error(f"获取球队ID失败: {str(e)}", exc_info=True)
            return None

    def get_team_name_by_id(self, team_id: int) -> Optional[str]:
        """获取球队名称

        通过ID查找球队名称。

        Args:
            team_id: 球队ID

        Returns:
            Optional[str]: 球队昵称，如未找到则返回None
        """
        try:
            # 调用数据库服务的team_repo获取球队字典
            team_info = self.db_service.team_repo.get_team_by_id(team_id)
            if team_info:
                # 返回球队昵称，如果昵称不存在则返回None
                return team_info.get('nickname')  # 或者 'full_name'
            else:
                self.logger.warning(f"未找到球队ID: {team_id} 的信息")
                return None
        except ServiceNotAvailableError:
            self.logger.error("获取球队名称失败: 数据库服务不可用")
            return None
        except Exception as e:
            self.logger.error(f"获取球队名称失败 (ID: {team_id}): {str(e)}", exc_info=True)
            return None

    def get_player_id_by_name(self, player_name: str) -> Optional[Union[int, List[Dict[str, Any]]]]:
        """获取球员ID

        通过名称查找球员ID，支持模糊匹配。

        Args:
            player_name: 球员名称

        Returns:
            Optional[Union[int, List[Dict[str, Any]]]]:
                - 整数: 唯一匹配时返回球员ID
                - 列表: 多个候选时返回候选列表
                - None: 未找到匹配
        """
        try:
            return self.db_service.get_player_id_by_name(player_name)
        except ServiceNotAvailableError:
            self.logger.error("获取球员ID失败: 数据库服务不可用")
            return None
        except Exception as e:
            self.logger.error(f"获取球员ID失败: {str(e)}", exc_info=True)
            return None

    def get_player_name_by_id(self, player_id: int) -> Optional[str]:
        """获取球员名称

        通过ID查找球员名称（默认返回全名）。

        Args:
            player_id: 球员ID

        Returns:
            Optional[str]: 球员全名，如未找到则返回None
        """
        try:
            # 调用数据库服务的 player_repo 的 get_player_name_by_id 方法
            player_name = self.db_service.player_repo.get_player_name_by_id(player_id, name_type='full')
            if player_name:
                return player_name
            else:
                self.logger.warning(f"未找到球员ID: {player_id} 的名称")
                return None
        except ServiceNotAvailableError:
            self.logger.error("获取球员名称失败: 数据库服务不可用")
            return None
        except Exception as e:
            self.logger.error(f"获取球员名称失败 (ID: {player_id}): {str(e)}", exc_info=True)
            return None

    def get_game_by_id(self, game_id: str, force_update: bool = False) -> Optional[Any]:
        """直接通过游戏ID获取比赛数据

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新

        Returns:
            Optional[Any]: 比赛数据对象
        """
        try:
            self.logger.info(f"尝试直接获取比赛ID: {game_id} 的数据")
            game = self.detail_service.get_game(game_id, force_update=force_update)

            if not game:
                self.logger.error(f"未找到比赛数据，比赛ID: {game_id}")
                return None

            return game

        except ServiceNotAvailableError as e:
            self.logger.error(f"获取比赛数据失败: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"获取比赛数据失败: {str(e)}", exc_info=True)
            return None

    def clear_cache(self) -> None:
        """清理所有服务的缓存"""
        try:
            if self._detail_service and hasattr(self._detail_service, 'clear_cache'):
                self._detail_service.clear_cache()
                self.logger.info("已清理数据提供者缓存")
        except Exception as e:
            self.logger.error(f"清理缓存失败: {str(e)}")

    def close(self) -> None:
        """关闭资源连接"""
        try:
            self.clear_cache()

            # 关闭数据提供者
            if self._detail_service and hasattr(self._detail_service, 'close'):
                self._detail_service.close()
                self.logger.info("数据提供者已关闭")

            # 不主动关闭数据库服务，因为它可能被其他服务共享使用

            self.logger.info("GameDataService资源已关闭")
        except Exception as e:
            self.logger.error(f"关闭资源时出错: {e}", exc_info=True)