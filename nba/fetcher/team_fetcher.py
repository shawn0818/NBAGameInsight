from typing import Dict, Optional, Any, List
from datetime import timedelta
import requests
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config import NBAConfig


class TeamConfig:
    """球队数据配置"""
    BASE_URL: str = "https://stats.nba.com/stats"
    CACHE_PATH = NBAConfig.PATHS.TEAM_CACHE_DIR
    CACHE_DURATION: timedelta = timedelta(days=7)  # 球队数据缓存7天
    ALL_TEAM_LIST = [1610612739, 1610612760, 1610612738, 1610612743, 1610612752,
                     1610612747, 1610612749, 1610612754, 1610612763, 1610612744,
                     1610612765, 1610612737, 1610612750, 1610612746, 1610612753,
                     1610612741, 1610612758, 1610612742, 1610612748, 1610612756,
                     1610612761, 1610612751, 1610612757, 1610612755, 1610612759,
                     1610612740, 1610612766, 1610612762, 1610612764, 1610612745]


class TeamFetcher(BaseNBAFetcher):
    """NBA球队数据获取器"""

    def __init__(self, custom_config: Optional[TeamConfig] = None):
        """初始化球队数据获取器"""
        self.team_config = custom_config or TeamConfig()

        # 配置缓存
        cache_config = BaseCacheConfig(
            duration=self.team_config.CACHE_DURATION,
            root_path=self.team_config.CACHE_PATH
        )

        # 创建基础请求配置
        base_config = BaseRequestConfig(
            base_url=self.team_config.BASE_URL,
            cache_config=cache_config
        )

        # 初始化基类
        super().__init__(base_config)


    @staticmethod
    def _get_cache_key(endpoint: str, team_id: int) -> str:
        """生成缓存键

        Args:
            endpoint: API端点名称
            team_id: 球队ID
        """
        return f"{endpoint.lower()}_{team_id}"

    def get_team_details(self, team_id: int, force_update: bool = False) -> Optional[Dict[str, Any]]:
        """获取球队详细信息
        1. 使用基类的 fetch_data 方法
        2. 优化了缓存键生成
        3. 改进了错误处理
        """
        if not isinstance(team_id, int) or team_id <= 0:
            raise ValueError("team_id must be a positive integer")

        try:
            cache_key = self._get_cache_key('details', team_id)
            self.logger.info(f"正在获取球队(ID:{team_id})详细信息")

            # 使用 build_url 构建URL并请求
            data = self.fetch_data(
                endpoint='teamdetails', # Use endpoint instead of url
                params={"TeamID": team_id},
                cache_key=cache_key,
                force_update=force_update
            )

            return data if data else None

        except requests.exceptions.Timeout:
            self.logger.error(f"获取球队数据超时: team_id={team_id}")
            return None
        except requests.exceptions.ConnectionError:
            self.logger.error(f"网络连接错误: team_id={team_id}")
            return None
        except ValueError as e:
            self.logger.error(f"数据格式错误: {e}")
            return None
        except Exception as e:
            self.logger.error(f"获取球队数据失败: {e}")
            return None

    def get_multiple_teams_details(self, team_ids: Optional[List[int]] = None,
                                   force_update: bool = False) -> Dict[int, Optional[Dict[str, Any]]]:
        """批量获取多支球队详细信息，支持断点续传"""
        # 如果未提供team_ids，则使用所有球队
        if team_ids is None:
            team_ids = self.team_config.ALL_TEAM_LIST

        self.logger.info(f"批量获取{len(team_ids)}支球队详细信息")

        # 如果强制更新，清理旧的缓存文件
        if force_update:
            # 清理球队相关的进度文件
            progress_file = self.config.cache_config.root_path / "batch_multiple_teams_details_progress.json"
            if progress_file.exists():
                try:
                    progress_file.unlink()
                    self.logger.info("已清除球队同步进度缓存")
                except Exception as e:
                    self.logger.error(f"清除进度文件失败: {e}")

        # 获取原始结果（字符串键）
        string_key_results = self.batch_fetch(
            ids=team_ids,
            fetch_func=lambda team_id: self.get_team_details(team_id, force_update),
            task_name="multiple_teams_details",
            batch_size=5  # 球队少，可以用小批量
        )

        # 将字符串键转换为整数键以匹配返回类型声明
        return {int(k): v for k, v in string_key_results.items()}

    def cleanup_cache(self, team_id: Optional[int] = None, older_than: Optional[timedelta] = None) -> None:
        """清理缓存数据

        修改：
        1. 使用基类的缓存清理机制
        2. 优化了缓存键处理
        """
        try:
            prefix = self.__class__.__name__.lower()
            if team_id:
                cache_key = self._get_cache_key('details', team_id)
                self.logger.info(f"正在清理球队(ID:{team_id})的缓存数据")
                self.cache_manager.clear(prefix=prefix, identifier=cache_key)
            else:
                cache_age = older_than or self.team_config.CACHE_DURATION
                self.logger.info(f"正在清理{cache_age}之前的缓存数据")
                self.cache_manager.clear(prefix=prefix, age=cache_age)
        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")