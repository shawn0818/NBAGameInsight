from typing import Dict, Optional, Any, List
from datetime import timedelta
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config import NBAConfig


class PlayerConfig:
    """球员数据配置"""
    BASE_URL: str = "https://stats.nba.com/stats"
    PLAYER_INFO_ENDPOINT: str = "commonplayerinfo"
    PLAYERS_LIST_ENDPOINT: str = "commonallplayers"
    CACHE_PATH = NBAConfig.PATHS.PLAYER_CACHE_DIR

    # 优化缓存策略 - 按数据类型定义不同的缓存时长
    SINGLE_PLAYER_CACHE_DURATION: timedelta = timedelta(days=1)  # 单个球员信息缓存1天
    ALL_PLAYERS_CACHE_DURATION: timedelta = timedelta(hours=12)  # 所有球员列表缓存12小时
    HISTORICAL_PLAYER_CACHE_DURATION: timedelta = timedelta(days=7)  # 历史球员数据缓存7天


class PlayerFetcher(BaseNBAFetcher):
    """NBA球员数据获取器
    特点：
    1. 支持批量获取球员详细信息
    2. 智能缓存策略
    3. 增强的错误处理
    """

    def __init__(self, custom_config: Optional[PlayerConfig] = None):
        """初始化球员数据获取器"""
        self.player_config = custom_config or PlayerConfig()

        # 配置缓存 - 增加动态缓存时长策略
        cache_config = BaseCacheConfig(
            duration=self.player_config.SINGLE_PLAYER_CACHE_DURATION,
            root_path=self.player_config.CACHE_PATH,
            dynamic_duration={
                'all_players': self.player_config.ALL_PLAYERS_CACHE_DURATION,
                'historical': self.player_config.HISTORICAL_PLAYER_CACHE_DURATION
            }
        )

        # 创建基础请求配置
        base_config = BaseRequestConfig(
            base_url=self.player_config.BASE_URL,
            cache_config=cache_config
        )

        # 初始化基类
        super().__init__(base_config)

    def get_player_info(self, player_id: int, force_update: bool = False) -> Optional[Dict[str, Any]]:
        """获取单个球员的详细信息"""
        try:
            params = {
                "PlayerID": player_id,
                "LeagueID": ""  # LeagueID 可以为空字符串
            }

            # 使用球员ID和参数哈希作为缓存key，更精确
            cache_key = f"player_info_{player_id}"

            data = self.fetch_data(
                endpoint=self.player_config.PLAYER_INFO_ENDPOINT,
                params=params,
                cache_key=cache_key,
                force_update=force_update,
                metadata={"player_id": player_id}  # 添加元数据方便追踪
            )

            # 增加数据检查
            if data and 'resultSets' in data:
                return data

            self.logger.warning(f"获取球员ID {player_id} 的信息返回无效数据格式")
            return None

        except Exception as e:
            self.logger.error(f"获取球员ID为 {player_id} 的信息失败: {e}")
            return None

    def get_all_players_info(self, force_update: bool = False,
                             current_season_only: bool = False) -> Optional[Dict[str, Any]]:
        """
        获取所有NBA球员数据

        Args:
            force_update: 是否强制更新缓存数据
            current_season_only: 是否只获取当前赛季球员
        """
        try:
            params = {
                "LeagueID": "00",  # 00表示NBA联盟
                "IsOnlyCurrentSeason": 1 if current_season_only else 0
            }

            # 根据查询类型使用不同的缓存键和缓存时长
            cache_key = "all_players_current" if current_season_only else "all_players"
            cache_status_key = 'all_players'  # 使用动态缓存时长

            data = self.fetch_data(
                endpoint=self.player_config.PLAYERS_LIST_ENDPOINT,
                params=params,
                cache_key=cache_key,
                cache_status_key=cache_status_key,
                force_update=force_update,
                metadata={"current_season_only": current_season_only}
            )

            # 增加数据检查
            if data and 'resultSets' in data:
                return data

            self.logger.warning("获取球员名册返回无效数据格式")
            return None

        except Exception as e:
            self.logger.error(f"获取所有球员数据失败: {e}")
            return None

    def batch_get_players_info(self, player_ids: List[int],
                               force_update: bool = False) -> Dict[str, Dict]:
        """
        批量获取多个球员信息

        利用BaseFetcher新增的批量获取能力，支持断点续传

        Args:
            player_ids: 球员ID列表
            force_update: 是否强制更新缓存

        Returns:
            Dict[str, Dict]: 球员信息字典，key为球员ID字符串
        """
        self.logger.info(f"开始批量获取{len(player_ids)}名球员信息")

        # 定义单个获取函数
        def fetch_single_player(player_id):
            return self.get_player_info(player_id, force_update)

        # 使用基类的批量获取实现
        results = self.batch_fetch(
            ids=player_ids,
            fetch_func=fetch_single_player,
            task_name="player_info_batch",
            batch_size=20  # 每批20个请求
        )

        return results

    def cleanup_cache(self, older_than: Optional[timedelta] = None,
                      cache_type: str = "all") -> None:
        """
        清理缓存数据

        Args:
            older_than: 可选的时间间隔，清理该时间之前的缓存
            cache_type: 缓存类型，可选 'all', 'player_info', 'players_list'
        """
        try:
            # 默认清理时间
            cache_age = older_than
            if not cache_age:
                if cache_type == 'player_info':
                    cache_age = self.player_config.SINGLE_PLAYER_CACHE_DURATION
                elif cache_type == 'players_list':
                    cache_age = self.player_config.ALL_PLAYERS_CACHE_DURATION
                else:
                    cache_age = timedelta(days=1)  # 默认清理1天前的所有缓存

            prefix = self.__class__.__name__.lower()
            if cache_type == 'player_info':
                # 只清理球员详情缓存
                self.logger.info(f"正在清理{cache_age}之前的单个球员信息缓存")
                # 模式匹配 player_info_* 的缓存
                for cache_id in ["player_info_"]:
                    self.cache_manager.clear(prefix=prefix, identifier=cache_id, age=cache_age)
            elif cache_type == 'players_list':
                # 只清理球员列表缓存
                self.logger.info(f"正在清理{cache_age}之前的球员列表缓存")
                for cache_id in ["all_players", "all_players_current"]:
                    self.cache_manager.clear(prefix=prefix, identifier=cache_id, age=cache_age)
            else:
                # 清理所有缓存
                self.logger.info(f"正在清理{cache_age}之前的所有球员相关缓存")
                self.cache_manager.clear(prefix=prefix, age=cache_age)

        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")