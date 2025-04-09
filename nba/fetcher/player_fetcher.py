from typing import Dict, Optional, Any, List
from datetime import timedelta
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config import NBAConfig


class PlayerCacheEnum:
    """球员缓存类型枚举"""
    ACTIVE = "active"  # 活跃球员 - 不缓存
    HISTORICAL = "historical"  # 历史球员 - 永久缓存


class PlayerConfig:
    """球员数据配置"""
    BASE_URL: str = "https://stats.nba.com/stats"
    PLAYER_INFO_ENDPOINT: str = "commonplayerinfo"
    PLAYERS_LIST_ENDPOINT: str = "commonallplayers"
    CACHE_PATH = NBAConfig.PATHS.PLAYER_CACHE_DIR

    # 简化缓存策略: 活跃球员不缓存，历史球员永久缓存
    CACHE_DURATION: Dict[str, timedelta] = {
        PlayerCacheEnum.ACTIVE: timedelta(seconds=0),  # 活跃球员不缓存
        PlayerCacheEnum.HISTORICAL: timedelta(days=365 * 10)  # 历史球员缓存10年
    }


class PlayerFetcher(BaseNBAFetcher):
    """NBA球员数据获取器
    特点:
    1. 支持批量获取球员详细信息
    2. 简化的缓存策略: 历史球员永久缓存，活跃球员不缓存，球员列表不缓存
    3. 根据ROSTERSTATUS判断球员是否活跃
    """

    def __init__(self, custom_config: Optional[PlayerConfig] = None):
        """初始化球员数据获取器"""
        self.player_config = custom_config or PlayerConfig()

        # 配置缓存 - 默认不缓存，仅历史球员使用缓存
        cache_config = BaseCacheConfig(
            duration=timedelta(seconds=0),  # 默认不缓存
            root_path=self.player_config.CACHE_PATH,
            dynamic_duration=self.player_config.CACHE_DURATION  # 使用动态缓存时间
        )

        # 创建基础请求配置
        base_config = BaseRequestConfig(
            base_url=self.player_config.BASE_URL,
            cache_config=cache_config
        )

        # 初始化基类
        super().__init__(base_config)

        # 添加内部缓存，用于存储球员状态 (活跃/历史)
        self._player_status_cache = {}

    def _is_active_player(self, player_data: Dict[str, Any]) -> bool:
        try:
            # 从commonplayerinfo结果中提取球员状态
            if 'resultSets' not in player_data:
                self.logger.debug("球员数据缺少resultSets字段，默认为活跃球员")
                return True  # 默认为活跃

            for result_set in player_data['resultSets']:
                if result_set['name'] == 'CommonPlayerInfo' and result_set['rowSet']:
                    # 获取headers和数据行
                    headers = result_set['headers']
                    row = result_set['rowSet'][0]

                    # 找到ROSTERSTATUS的索引
                    if 'ROSTERSTATUS' in headers:
                        roster_status_idx = headers.index('ROSTERSTATUS')
                        roster_status = row[roster_status_idx]

                        # 记录状态值
                        self.logger.debug(f"检测到球员ROSTERSTATUS={roster_status}")

                        # 直接检查ROSTERSTATUS字段
                        if isinstance(roster_status, str) and roster_status.lower() == "inactive":
                            return False

                        # 也兼容数字格式的状态值
                        if roster_status == 0:
                            return False

            # 默认为活跃
            return True

        except Exception as e:
            self.logger.error(f"球员状态判断失败 | error={str(e)}", exc_info=True)
            return True  # 出错时默认为活跃

    def _get_player_status(self, player_id: int, player_data: Optional[Dict[str, Any]] = None) -> str:
        # 如果状态已缓存，直接返回
        if player_id in self._player_status_cache:
            status = self._player_status_cache[player_id]
            self.logger.debug(f"球员状态缓存命中 | player_id={player_id} | status={status}")
            return status

        # 如果提供了球员数据，则从数据中判断
        if player_data:
            is_active = self._is_active_player(player_data)
            status = PlayerCacheEnum.ACTIVE if is_active else PlayerCacheEnum.HISTORICAL

            # 缓存状态
            self._player_status_cache[player_id] = status
            self.logger.debug(f"球员状态计算完成 | player_id={player_id} | is_active={is_active} | status={status}")
            return status

        # 默认为活跃
        self.logger.debug(f"未提供球员数据，默认为活跃球员 | player_id={player_id}")
        return PlayerCacheEnum.ACTIVE

    def get_player_info(self, player_id: int, force_update: bool = False) -> Optional[Dict[str, Any]]:
        """
        获取单个球员的详细信息

        Args:
            player_id: 球员ID
            force_update: 是否强制更新缓存

        Returns:
            Dict: 球员详细信息
        """
        try:
            cache_key = f"player_info_{player_id}"

            # 尝试获取缓存数据
            cached_data = self.cache_manager.get(
                prefix=self.__class__.__name__.lower(),
                identifier=cache_key
            )

            cached_status = None
            # 如果有缓存且不强制更新，检查是否为历史球员
            if cached_data is not None and not force_update:
                cached_status = self._get_player_status(player_id, cached_data)

                # 如果是历史球员，直接使用缓存
                if cached_status == PlayerCacheEnum.HISTORICAL:
                    return cached_data

                # 否则是活跃球员，请求新数据

            # 请求参数
            params = {
                "PlayerID": player_id,
                "LeagueID": ""  # LeagueID 可以为空字符串
            }

            # 获取新数据
            data = self.fetch_data(
                endpoint=self.player_config.PLAYER_INFO_ENDPOINT,
                params=params,
                cache_key=cache_key,
                force_update=True,  # 活跃球员总是获取最新数据
                cache_status_key=cached_status
            )

            # 增加数据检查
            if data and 'resultSets' in data:
                # 判断球员状态
                current_status = self._get_player_status(player_id, data)

                # 如果是历史球员，设置长期缓存
                if current_status == PlayerCacheEnum.HISTORICAL:
                    metadata = {"player_id": player_id, "player_status": current_status}
                    self.cache_manager.set(
                        prefix=self.__class__.__name__.lower(),
                        identifier=cache_key,
                        data=data,
                        metadata=metadata
                    )

                return data

            self.logger.warning(f"获取球员ID {player_id} 的信息返回无效数据格式")
            return None

        except Exception as e:
            self.logger.error(f"获取球员ID为 {player_id} 的信息失败: {e}")
            return None

    def batch_get_players_info(self, player_ids: List[int],
                               force_update: bool = False) -> Dict[str, Dict]:
        """
        批量获取多个球员信息

        Args:
            player_ids: 球员ID列表
            force_update: 是否强制更新缓存

        Returns:
            Dict[str, Dict]: 球员信息字典，key为球员ID字符串
        """
        self.logger.info(f"开始球员数据同步任务 | player_count={len(player_ids)} | force_update={force_update}")

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

    def get_all_players_info(self, current_season_only: bool = False) -> Optional[Dict[str, Any]]:
        """
        获取所有NBA球员数据 - 始终获取最新数据，不缓存
        Args:
            current_season_only: 是否只获取当前赛季球员

        Returns:
            Dict: 所有球员数据
        """
        try:
            # 请求参数
            params = {
                "LeagueID": "00",  # 00表示NBA联盟
                "IsOnlyCurrentSeason": 1 if current_season_only else 0
            }

            # 获取新数据 - 不设置cache_key，不缓存
            self.logger.info(f"获取NBA球员名册 | current_season_only={current_season_only} | cache_policy=no_cache")
            data = self.fetch_data(
                endpoint=self.player_config.PLAYERS_LIST_ENDPOINT,
                params=params,
                cache_key=None,  # 不缓存
            )

            # 增加数据检查
            if data and 'resultSets' in data:
                return data

            self.logger.warning("获取球员名册返回无效数据格式")
            return None

        except Exception as e:
            self.logger.error(f"获取所有球员数据失败: {e}")
            return None

    def cleanup_cache(self, older_than: Optional[timedelta] = None) -> None:
        """
        清理缓存数据 - 由于仅缓存历史球员，所以只需要清理非常旧的缓存

        Args:
            older_than: 可选的时间间隔，清理该时间之前的缓存
        """
        try:
            # 默认清理超过2年的缓存
            cache_age = older_than or timedelta(days=365 * 2)

            prefix = self.__class__.__name__.lower()
            self.logger.info(f"正在清理{cache_age}之前的历史球员缓存")
            self.cache_manager.clear(prefix=prefix, age=cache_age)

            # 清空状态缓存
            self._player_status_cache = {}

        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")