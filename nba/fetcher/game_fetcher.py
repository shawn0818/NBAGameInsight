from dataclasses import dataclass
from typing import Dict, Optional, Any, Tuple, List, Callable
from datetime import timedelta
from enum import Enum
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config import NBAConfig


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
    # 不同API的基础URL
    BASE_URL: str = "https://stats.nba.com/stats"
    CDN_URL: str = "https://cdn.nba.com/static/json/liveData"
    CACHE_PATH = NBAConfig.PATHS.GAME_CACHE_DIR
    # 根据比赛状态配置不同的缓存时间
    CACHE_DURATION: Dict[GameStatusEnum, timedelta] = {
        GameStatusEnum.NOT_STARTED: timedelta(seconds=0),  # 未开始比赛不缓存
        GameStatusEnum.IN_PROGRESS: timedelta(seconds=0),  # 进行中比赛不缓存
        GameStatusEnum.FINISHED: timedelta(days=365 * 10)  # 已结束比赛缓存10年
    }


@dataclass
class GameDataResponse:
    """比赛数据响应类"""
    boxscore: Dict[str, Any]  # 比赛统计数据
    playbyplay: Dict[str, Any]  # 比赛回放数据

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
            duration=timedelta(seconds=0),  # 默认不缓存
            root_path=game_config.CACHE_PATH,
            dynamic_duration=game_config.CACHE_DURATION  # 使用动态缓存时间
        )

        # 创建基础请求配置
        base_config = BaseRequestConfig(
            base_url=game_config.BASE_URL,  # 注意这是统计API的基础URL
            cache_config=cache_config
        )

        # 初始化基类
        super().__init__(base_config)
        self.game_config = game_config

    # ============== CDN API 请求方法（使用完整URL） ==============

    def _get_data_with_status(
            self,
            game_id: str,
            data_type: str,
            force_update: bool = False,
            game_status: Optional[GameStatusEnum] = None
    ) -> Tuple[Optional[Dict[str, Any]], GameStatusEnum]:
        """获取CDN数据并返回比赛状态

        Args:
            game_id: 比赛ID
            data_type: 数据类型 (boxscore或playbyplay)
            force_update: 是否强制更新缓存
            game_status: 已知的比赛状态

        Returns:
            Tuple: (数据, 比赛状态)
        """
        try:
            # 构建完整URL (使用CDN URL)
            url = f"{self.game_config.CDN_URL}/{data_type}/{data_type}_{game_id}.json"
            cache_key = f"{data_type}_{game_id}"

            # 先尝试获取缓存数据
            cached_data = self.cache_manager.get(
                prefix=self.__class__.__name__.lower(),
                identifier=cache_key
            )

            cached_status = None

            if cached_data is not None:
                # 从缓存数据中获取比赛状态
                cached_status = self._get_game_status(cached_data)
                # 添加缓存状态日志
                self.logger.debug(
                    f"比赛状态缓存信息 | game_id={game_id} | data_type={data_type} | "
                    f"cached_status={cached_status.name}"
                )
                # 如果比赛已结束且不强制更新，直接使用缓存
                if cached_status == GameStatusEnum.FINISHED and not force_update:
                    self.logger.debug(
                        f"使用已结束比赛缓存 | game_id={game_id} | data_type={data_type}"
                    )
                    return cached_data, cached_status

            # 获取数据，传递正确的状态作为cache_status_key
            effective_status = game_status or cached_status

            data = self.fetch_data(
                url=url,  # 使用完整URL
                cache_key=cache_key,
                force_update=force_update,
                cache_status_key=effective_status,
                # 添加元数据，记录当前状态
                metadata={"game_status": effective_status.value} if effective_status else None
            )

            # 确定最终状态
            if data is not None:
                final_status = self._get_game_status(data)

                # 如果是已完成的比赛，确保更新缓存并存储状态
                if final_status == GameStatusEnum.FINISHED:
                    self.cache_manager.set(
                        prefix=self.__class__.__name__.lower(),
                        identifier=cache_key,
                        data=data,
                        metadata={"game_status": final_status.value}
                    )
            else:
                final_status = effective_status or GameStatusEnum.NOT_STARTED

            return data, final_status

        except Exception as e:
            self.logger.error(
                f"获取比赛数据失败 | game_id={game_id} | data_type={data_type} | error='{e}' | "
                f"url={self.game_config.CDN_URL}/{data_type}/{data_type}_{game_id}.json}}",
                exc_info=True
            )
            return None, GameStatusEnum.NOT_STARTED

    def _get_game_status(self, data: Dict[str, Any]) -> GameStatusEnum:
        """从数据中获取比赛状态

        Args:
            data: 比赛数据

        Returns:
            GameStatusEnum: 比赛状态
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        try:
            status = data.get('game', {}).get('gameStatus', 1)
            result = GameStatusEnum.from_api_status(status)
            self.logger.debug(f"解析比赛状态 | raw_status={status} | enum_status={result.name}")
            return result
        except Exception as e:
            self.logger.error(f"解析比赛状态失败 | error={str(e)}", exc_info=True)
            return GameStatusEnum.NOT_STARTED

    # ============== Stats API 请求方法（使用端点） ==============

    def _get_endpoint_data(
            self,
            game_id: str,
            endpoint: str,
            params: Dict[str, Any],
            cache_key_prefix: str,
            description: str,
            force_update: bool = False,
            game_status: Optional[GameStatusEnum] = None
    ) -> Optional[Dict[str, Any]]:
        """通用方法获取NBA比赛的API端点数据

        Args:
            game_id: 比赛ID
            endpoint: API端点
            params: 请求参数
            cache_key_prefix: 缓存键前缀
            description: 数据描述(用于日志)
            force_update: 是否强制更新缓存
            game_status: 已知的比赛状态

        Returns:
            Dict: 获取的数据
        """
        try:
            # 完整缓存键
            cache_key = f"{cache_key_prefix}_{game_id}"

            # 先检查缓存
            cached_data = self.cache_manager.get(
                prefix=self.__class__.__name__.lower(),
                identifier=cache_key
            )

            # 如果有缓存元数据，从中获取比赛状态
            cached_status = game_status

            # 记录缓存状态日志
            if cached_data:
                status_name = cached_status.name if cached_status else "UNKNOWN"
                self.logger.debug(
                    f"端点数据缓存状态 | game_id={game_id} | endpoint={endpoint} | "
                    f"status={status_name} | force_update={force_update}"
                )
            # 如果比赛已结束且不强制更新，直接使用缓存
            if cached_data and cached_status == GameStatusEnum.FINISHED and not force_update:
                self.logger.debug(
                    f"使用已完成比赛缓存 | game_id={game_id} | endpoint={endpoint}"
                )
                return cached_data

            # 如果比赛未开始或进行中，强制更新
            if cached_status in [GameStatusEnum.NOT_STARTED, GameStatusEnum.IN_PROGRESS]:
                force_update = True

            # 使用fetch_data方法获取数据（通过endpoint）
            data = self.fetch_data(
                endpoint=endpoint,
                params=params,
                cache_key=cache_key,
                force_update=force_update,
                cache_status_key=cached_status,
                metadata={"game_status": cached_status.value} if cached_status else None
            )

            if not data:
                self.logger.error(
                    f"API返回无效数据 | game_id={game_id} | endpoint={endpoint} | description={description}"
                )
                return None

            # 如果比赛已结束，确保更新缓存
            if game_status == GameStatusEnum.FINISHED and data:
                self.cache_manager.set(
                    prefix=self.__class__.__name__.lower(),
                    identifier=cache_key,
                    data=data,
                    metadata={"game_status": game_status.value}
                )

            return data

        except Exception as e:
            self.logger.error(
                f"获取数据异常 | game_id={game_id} | endpoint={endpoint} | "
                f"description={description} | params={params} | error='{e}'",
                exc_info=True
            )
            return None

    # ============== 批量请求方法 ==============

    def _batch_get_data(
            self,
            game_ids: List[str],
            get_function: Callable[[str, bool, Optional[GameStatusEnum]], Optional[Dict[str, Any]]],
            task_name: str,
            description: str,
            force_update: bool = False,
            game_statuses: Optional[Dict[str, GameStatusEnum]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """通用批量获取方法

        Args:
            game_ids: 比赛ID列表
            get_function: 单个数据获取函数
            task_name: 批处理任务名称
            description: 数据描述(用于日志)
            force_update: 是否强制更新缓存
            game_statuses: 比赛ID到状态的映射

        Returns:
            Dict: 批量获取结果
        """
        self.logger.info(
            f"开始批量获取比赛数据 | count={len(game_ids)} | data_type={description} | "
            f"force_update={force_update} | task={task_name}"
        )

        # 如果没有提供状态映射，则创建空映射
        statuses = game_statuses or {}

        # 定义单个获取函数
        def fetch_single(game_id):
            status = statuses.get(game_id)
            return get_function(game_id, force_update, status)

        # 使用基类的批量获取方法
        results = self.batch_fetch(
            ids=game_ids,
            fetch_func=fetch_single,
            task_name=task_name
        )

        return results

    # ============== 公开API方法 ==============

    def get_game_data(self, game_id: str, force_update: bool = False) -> Optional[GameDataResponse]:
        """获取完整的比赛数据

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新缓存

        Returns:
            GameDataResponse: 完整的比赛数据响应
        """
        try:
            # 1. 获取boxscore数据和状态
            # 始终获取最新的boxscore数据以确定比赛状态
            boxscore_data, game_status = self._get_data_with_status(
                game_id,
                'boxscore',
                force_update=True  # 明确强制更新boxscore
            )

            if not boxscore_data or 'game' not in boxscore_data:
                self.logger.error(f"无效boxscore数据 | game_id={game_id} | has_data={boxscore_data is not None}")
                return None

            # 2. 获取playbyplay数据
            # 如果比赛已结束，使用相同的force_update参数
            # 如果比赛未开始或进行中，始终获取最新数据
            playbyplay_force_update = force_update
            if game_status != GameStatusEnum.FINISHED:
                playbyplay_force_update = True

            playbyplay_data, _ = self._get_data_with_status(
                game_id,
                'playbyplay',
                playbyplay_force_update,
                game_status
            )

            if not playbyplay_data or 'game' not in playbyplay_data:
                self.logger.error(
                    f"无效playbyplay数据 | game_id={game_id} | status={game_status.name} | "
                    f"has_data={playbyplay_data is not None}"
                )
                playbyplay_data = {'game': {}}

            # 3. 构建响应
            return GameDataResponse(
                boxscore=boxscore_data['game'],
                playbyplay=playbyplay_data['game'],
            )

        except Exception as e:
            self.logger.error(
                f"获取综合比赛数据失败 | game_id={game_id} | force_update={force_update} | error='{e}'",
                exc_info=True
            )

            return None

    # ============== Stats API 公开方法 ==============

    def get_boxscore_summary(
            self,
            game_id: str,
            force_update: bool = False,
            game_status: Optional[GameStatusEnum] = None
    ) -> Optional[Dict[str, Any]]:
        """获取NBA比赛的摘要信息

        该方法获取比赛的总体摘要信息，包括比赛基本信息、球队信息、比赛记录、
        场馆信息、裁判信息、比赛进程、比分等综合性数据。

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新缓存
            game_status: 已知的比赛状态

        Returns:
            Dict: 比赛摘要数据
        """
        return self._get_endpoint_data(
            game_id=game_id,
            endpoint="boxscoresummaryv2",
            params={"GameID": game_id},
            cache_key_prefix="boxscore_summary_v2",
            description="比赛摘要信息",
            force_update=force_update,
            game_status=game_status
        )

    def get_boxscore_traditional(
            self,
            game_id: str,
            force_update: bool = False,
            game_status: Optional[GameStatusEnum] = None
    ) -> Optional[Dict[str, Any]]:
        """获取比赛的传统盒子分数统计

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新缓存
            game_status: 已知的比赛状态

        Returns:
            Dict: 传统盒子分数统计数据
        """
        return self._get_endpoint_data(
            game_id=game_id,
            endpoint="boxscoretraditionalv3",
            params={
                "GameID": game_id,
                "EndPeriod": 0,
                "EndRange": 28800,
                "StartPeriod": 0,
                "StartRange": 0
            },
            cache_key_prefix="boxscore_traditional",
            description="传统盒子分数统计",
            force_update=force_update,
            game_status=game_status
        )

    def get_playbyplay(
            self,
            game_id: str,
            force_update: bool = False,
            game_status: Optional[GameStatusEnum] = None
    ) -> Optional[Dict[str, Any]]:
        """获取比赛的详细回放数据(V3版本)

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新缓存
            game_status: 已知的比赛状态

        Returns:
            Dict: 比赛回放数据
        """
        return self._get_endpoint_data(
            game_id=game_id,
            endpoint="playbyplayv3",
            params={
                "GameID": game_id,
                "StartPeriod": 0,
                "EndPeriod": 0
            },
            cache_key_prefix="playbyplay_v3",
            description="比赛回放数据(V3)",
            force_update=force_update,
            game_status=game_status
        )

    def get_boxscore_misc(
            self,
            game_id: str,
            force_update: bool = False,
            game_status: Optional[GameStatusEnum] = None
    ) -> Optional[Dict[str, Any]]:
        """获取NBA比赛的Box Score杂项统计信息

        该方法获取比赛中的各种非传统统计数据，包括得分来源(失误、二次进攻、快攻、油漆区)
        以及犯规和盖帽等详细信息。为主队和客队的每位球员提供全面的杂项统计数据。

        Args:
            game_id: 比赛ID
            force_update: 是否强制更新缓存
            game_status: 已知的比赛状态

        Returns:
            Dict: Box Score杂项统计数据
        """
        return self._get_endpoint_data(
            game_id=game_id,
            endpoint="boxscoremiscv3",
            params={
                "GameID": game_id,
                "EndPeriod": 0,
                "EndRange": 28800,
                "StartPeriod": 0,
                "StartRange": 0
            },
            cache_key_prefix="boxscore_misc_v3",
            description="Box Score杂项统计信息",
            force_update=force_update,
            game_status=game_status
        )

    # ============== 批量获取方法 ==============

    def batch_get_boxscore_traditional(
            self,
            game_ids: List[str],
            force_update: bool = False,
            game_statuses: Optional[Dict[str, GameStatusEnum]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """批量获取多场比赛的传统盒子分数统计

        Args:
            game_ids: 比赛ID列表
            force_update: 是否强制更新缓存
            game_statuses: 比赛ID到状态的映射

        Returns:
            Dict: 以比赛ID为键，统计数据为值的字典
        """
        return self._batch_get_data(
            game_ids=game_ids,
            get_function=self.get_boxscore_traditional,
            task_name="boxscore_traditional_batch",
            description="传统盒子分数统计",
            force_update=force_update,
            game_statuses=game_statuses
        )

    def batch_get_playbyplay(
            self,
            game_ids: List[str],
            force_update: bool = False,
            game_statuses: Optional[Dict[str, GameStatusEnum]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """批量获取多场比赛的详细回放数据(V3版本)

        Args:
            game_ids: 比赛ID列表
            force_update: 是否强制更新缓存
            game_statuses: 比赛ID到状态的映射

        Returns:
            Dict: 以比赛ID为键，回放数据为值的字典
        """
        return self._batch_get_data(
            game_ids=game_ids,
            get_function=self.get_playbyplay,
            task_name="playbyplay_v3_batch",
            description="详细回放数据(V3)",
            force_update=force_update,
            game_statuses=game_statuses
        )

    def batch_get_boxscore_misc(
            self,
            game_ids: List[str],
            force_update: bool = False,
            game_statuses: Optional[Dict[str, GameStatusEnum]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """批量获取多场比赛的Box Score杂项统计信息

        Args:
            game_ids: 比赛ID列表
            force_update: 是否强制更新缓存
            game_statuses: 比赛ID到状态的映射

        Returns:
            Dict: 以比赛ID为键，杂项统计数据为值的字典
        """
        return self._batch_get_data(
            game_ids=game_ids,
            get_function=self.get_boxscore_misc,
            task_name="boxscore_misc_v3_batch",
            description="Box Score杂项统计信息",
            force_update=force_update,
            game_statuses=game_statuses
        )

    # ============== 缓存管理方法 ==============

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
                data_types = ['boxscore', 'playbyplay', 'boxscore_summary_v2',
                              'boxscore_traditional', 'boxscore_misc_v3', 'playbyplay_v3']

                if data_type is not None:
                    data_types = [dt for dt in data_types if data_type in dt]

                for dt in data_types:
                    cache_key = f"{dt}_{game_id}"
                    self.cache_manager.clear(prefix=prefix, identifier=cache_key)
                    self.logger.info(f"缓存清理完成 | game_id={game_id} | data_type={dt}")
            else:
                self.cache_manager.clear(prefix=prefix, age=older_than)
                age_info = f"older_than={older_than}" if older_than else "all_time"
                self.logger.info(f"全局缓存清理完成 | prefix={prefix} | {age_info}")

        except Exception as e:
            game_info = f"game_id={game_id}" if game_id else "all_games"
            type_info = f"data_type={data_type}" if data_type else "all_types"
            self.logger.error(
                f"缓存清理失败 | {game_info} | {type_info} | error='{e}'",
                exc_info=True
            )