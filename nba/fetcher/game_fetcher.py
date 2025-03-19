from dataclasses import dataclass
from typing import Dict, Optional, Any, Tuple, List
from datetime import timedelta
from enum import Enum
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config import  NBAConfig


class GameStatusEnum(Enum):
    """比赛状态枚举"""
    NOT_STARTED = 1
    IN_PROGRESS = 2
    FINISHED = 3

    @classmethod
    def from_api_status(cls, status: Optional[int]) -> 'GameStatusEnum':
        """从API状态码转换为枚举值"""
        try:
            return cls(status)
        except (ValueError, TypeError):
            return cls.NOT_STARTED


class GameConfig:
    """比赛数据配置"""
    # 将BASE_URL修改为stats API的基础URL
    BASE_URL: str = "https://stats.nba.com/stats"
    CDN_URL: str = "https://cdn.nba.com/static/json/liveData"
    CACHE_PATH = NBAConfig.PATHS.GAME_CACHE_DIR
    # 根据比赛状态配置不同的缓存时间
    CACHE_DURATION: Dict[GameStatusEnum, timedelta] = {
        GameStatusEnum.NOT_STARTED: timedelta(minutes=1),
        GameStatusEnum.IN_PROGRESS: timedelta(seconds=0),
        GameStatusEnum.FINISHED: timedelta(days=1)
    }

@dataclass
class GameDataResponse:
    """比赛数据响应类"""
    boxscore: Dict[str, Any]  # 比赛统计数据
    playbyplay: Dict[str, Any]  # 比赛回放数据
    boxscore_summary: Optional[Dict[str, Any]] = None  # 添加比赛摘要数据，包含对抗历史信息

    @property
    def status(self) -> GameStatusEnum:
        """从boxscore中获取比赛状态"""
        return GameStatusEnum.from_api_status(
            self.boxscore.get('gameStatus', 1)
        )


class GameFetcher(BaseNBAFetcher):
    """NBA比赛数据获取器"""

    def __init__(self, custom_config: Optional[GameConfig] = None):
        """初始化

        Args:
            custom_config: 自定义配置，如果为None则使用默认配置
        """
        game_config = custom_config or GameConfig()

        # 配置缓存
        cache_config = BaseCacheConfig(
            duration=timedelta(days=1),  # 默认缓存时间
            root_path=game_config.CACHE_PATH,
            dynamic_duration=game_config.CACHE_DURATION  # 使用动态缓存时间
        )

        # 创建基础请求配置
        base_config = BaseRequestConfig(
            base_url=game_config.BASE_URL,
            cache_config=cache_config
        )

        # 初始化基类
        super().__init__(base_config)
        self.game_config = game_config

    def get_game_data(self, game_id: str, force_update: bool = False) -> Optional[GameDataResponse]:
        """获取完整的比赛数据"""
        try:
            # 1. 获取boxscore数据和状态
            boxscore_data, game_status = self._get_data_with_status(
                game_id,
                'boxscore',
                force_update
            )

            if not boxscore_data or 'game' not in boxscore_data:
                self.logger.error("无法获取boxscore数据")
                return None

            # 2. 获取playbyplay数据 (不再区分比赛状态)
            playbyplay_data, _ = self._get_data_with_status(
                game_id,
                'playbyplay',
                force_update,
                game_status
            )

            if not playbyplay_data or 'game' not in playbyplay_data:
                self.logger.error("无法获取playbyplay数据 (即使比赛未开始，也尝试获取)")
                playbyplay_data = {'game': {}}
            elif game_status == GameStatusEnum.NOT_STARTED:
                self.logger.info("比赛未开始，但已尝试获取playbyplay数据")

            # 3. 获取boxscore_summary数据
            boxscore_summary_data = self.get_boxscore_summary(game_id, force_update)

            # 4. 构建响应
            return GameDataResponse(
                boxscore=boxscore_data['game'],
                playbyplay=playbyplay_data['game'],
                boxscore_summary=boxscore_summary_data  # 添加摘要数据
            )

        except Exception as e:
            self.logger.error(f"获取比赛数据失败: {e}")
            return None

    def _get_data_with_status(
            self,
            game_id: str,
            data_type: str,
            force_update: bool = True,
            game_status: Optional[GameStatusEnum] = None
    ) -> Tuple[Optional[Dict[str, Any]], GameStatusEnum]:
        """获取数据并返回比赛状态"""
        try:
            # 构建完整URL (使用CDN URL)
            url = f"{self.game_config.CDN_URL}/{data_type}/{data_type}_{game_id}.json"
            cache_key = f"{data_type}_{game_id}"

            # 获取数据
            data = self.fetch_data(
                url=url,  # 使用完整URL
                cache_key=cache_key,
                force_update=force_update,
                cache_status_key=game_status
            )

            # 如果没有传入状态，从数据中获取
            if game_status is None and data is not None:
                game_status = self._get_game_status(data)
            elif game_status is None:
                game_status = GameStatusEnum.NOT_STARTED

            return data, game_status

        except Exception as e:
            self.logger.error(f"获取{data_type}数据失败: {e}")
            return None, GameStatusEnum.NOT_STARTED

    def _get_game_status(self, data: Dict[str, Any]) -> GameStatusEnum:
        """从数据中获取比赛状态"""
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        try:
            status = data.get('game', {}).get('gameStatus', 1)
            return GameStatusEnum.from_api_status(status)
        except Exception as e:
            self.logger.error(f"获取比赛状态失败: {e}")
            return GameStatusEnum.NOT_STARTED

    def get_boxscore_summary(self, game_id: str, force_update: bool = False) -> Optional[Dict[str, Any]]:
        """获取NBA比赛的摘要信息

        该方法获取比赛的总体摘要信息，包括比赛基本信息、球队信息、比赛记录、
        场馆信息、裁判信息、比赛进程、比分等综合性数据。

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新缓存

        Returns:
            Dict: 比赛摘要数据
        """
        try:
            # 使用endpoint和params
            endpoint = "boxscoresummaryv2"
            params = {
                "GameID": game_id
            }

            cache_key = f"boxscore_summary_v2_{game_id}"

            # 使用fetch_data方法获取数据
            data = self.fetch_data(
                endpoint=endpoint,
                params=params,
                cache_key=cache_key,
                force_update=force_update
            )

            if not data:
                self.logger.error(f"无法获取比赛{game_id}的摘要信息")
                return None

            return data
        except Exception as e:
            self.logger.error(f"获取比赛摘要信息失败: {e}")
            return None


    def get_boxscore_traditional(self, game_id: str, force_update: bool = False) -> Optional[Dict[str, Any]]:
        """获取比赛的传统盒子分数统计

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新缓存

        Returns:
            Dict: 传统盒子分数统计数据
        """
        try:
            # 使用endpoint和params，而不是完整URL
            endpoint = "boxscoretraditionalv3"
            params = {
                "GameID": game_id,
                "EndPeriod": 0,
                "EndRange": 28800,
                "StartPeriod": 0,
                "StartRange": 0
            }

            cache_key = f"boxscore_traditional_{game_id}"

            # 使用fetch_data方法获取数据
            data = self.fetch_data(
                endpoint=endpoint,
                params=params,
                cache_key=cache_key,
                force_update=force_update
            )

            if not data:
                self.logger.error(f"无法获取比赛{game_id}的传统盒子分数统计")
                return None

            return data
        except Exception as e:
            self.logger.error(f"获取传统盒子分数统计失败: {e}")
            return None

    def get_playbyplay(self, game_id: str, force_update: bool = False) -> Optional[Dict[str, Any]]:
        """获取比赛的详细回放数据(V3版本)

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新缓存

        Returns:
            Dict: 比赛回放数据
        """
        try:
            # 使用endpoint和params，而不是完整URL
            endpoint = "playbyplayv3"
            params = {
                "GameID": game_id,
                "StartPeriod": 0,
                "EndPeriod": 0
            }

            cache_key = f"playbyplay_v3_{game_id}"

            # 使用fetch_data方法获取数据
            data = self.fetch_data(
                endpoint=endpoint,
                params=params,
                cache_key=cache_key,
                force_update=force_update
            )

            if not data:
                self.logger.error(f"无法获取比赛{game_id}的回放数据(V3)")
                return None

            return data
        except Exception as e:
            self.logger.error(f"获取回放数据(V3)失败: {e}")
            return None

    def batch_get_boxscore_traditional(self, game_ids: List[str], force_update: bool = False) -> Dict[
        str, Dict[str, Any]]:
        """批量获取多场比赛的传统盒子分数统计

        Args:
            game_ids: 比赛ID列表
            force_update: 是否强制更新缓存

        Returns:
            Dict: 以比赛ID为键，统计数据为值的字典
        """
        self.logger.info(f"批量获取{len(game_ids)}场比赛的传统盒子分数统计")

        # 定义单个获取函数
        def fetch_single(game_id):
            return self.get_boxscore_traditional(game_id, force_update)

        # 使用基类的批量获取方法
        results = self.batch_fetch(
            ids=game_ids,
            fetch_func=fetch_single,
            task_name="boxscore_traditional_batch"
        )

        return results

    def batch_get_playbyplay(self, game_ids: List[str], force_update: bool = False) -> Dict[str, Dict[str, Any]]:
        """批量获取多场比赛的详细回放数据(V3版本)

        Args:
            game_ids: 比赛ID列表
            force_update: 是否强制更新缓存

        Returns:
            Dict: 以比赛ID为键，回放数据为值的字典
        """
        self.logger.info(f"批量获取{len(game_ids)}场比赛的详细回放数据(V3)")

        # 定义单个获取函数
        def fetch_single(game_id):
            return self.get_playbyplay(game_id, force_update)

        # 使用基类的批量获取方法
        results = self.batch_fetch(
            ids=game_ids,
            fetch_func=fetch_single,
            task_name="playbyplay_v3_batch"
        )

        return results

    def get_boxscore_misc(self, game_id: str, force_update: bool = False) -> Optional[Dict[str, Any]]:
        """获取NBA比赛的Box Score杂项统计信息

        该方法获取比赛中的各种非传统统计数据，包括得分来源(失误、二次进攻、快攻、油漆区)
        以及犯规和盖帽等详细信息。为主队和客队的每位球员提供全面的杂项统计数据。

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新缓存

        Returns:
            Dict: Box Score杂项统计数据
        """
        try:
            # 使用endpoint和params
            endpoint = "boxscoremiscv3"
            params = {
                "GameID": game_id,
                "EndPeriod": 0,
                "EndRange": 28800,
                "StartPeriod": 0,
                "StartRange": 0
            }

            cache_key = f"boxscore_misc_v3_{game_id}"

            # 使用fetch_data方法获取数据
            data = self.fetch_data(
                endpoint=endpoint,
                params=params,
                cache_key=cache_key,
                force_update=force_update
            )

            if not data:
                self.logger.error(f"无法获取比赛{game_id}的Box Score杂项统计信息")
                return None

            return data
        except Exception as e:
            self.logger.error(f"获取Box Score杂项统计信息失败: {e}")
            return None

    def batch_get_boxscore_misc(self, game_ids: List[str], force_update: bool = False) -> Dict[str, Dict[str, Any]]:
        """批量获取多场比赛的Box Score杂项统计信息

        Args:
            game_ids: 比赛ID列表
            force_update: 是否强制更新缓存

        Returns:
            Dict: 以比赛ID为键，杂项统计数据为值的字典
        """
        self.logger.info(f"批量获取{len(game_ids)}场比赛的Box Score杂项统计信息")

        # 定义单个获取函数
        def fetch_single(game_id):
            return self.get_boxscore_misc(game_id, force_update)

        # 使用基类的批量获取方法
        results = self.batch_fetch(
            ids=game_ids,
            fetch_func=fetch_single,
            task_name="boxscore_misc_v3_batch"
        )

        return results

    def clear_cache(
            self,
            game_id: Optional[str] = None,
            older_than: Optional[timedelta] = None,
            data_type: Optional[str] = None
    ) -> None:
        """清理缓存

        Args:
            game_id: 指定清理某场比赛的缓存
            older_than: 清理指定时间之前的缓存
            data_type: 指定清理的数据类型(boxscore或playbyplay)
        """
        try:
            prefix = self.__class__.__name__.lower()

            if game_id:
                data_types = ['boxscore', 'playbyplay'] if data_type is None else [data_type]
                for dt in data_types:
                    cache_key = f"{dt}_{game_id}"
                    self.cache_manager.clear(prefix=prefix, identifier=cache_key)
            else:
                self.cache_manager.clear(prefix=prefix, age=older_than)

        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")