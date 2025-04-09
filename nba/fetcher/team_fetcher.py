import os
from typing import Dict, Optional, Any, List
from datetime import timedelta
import requests
from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config import NBAConfig


class TeamConfig:
    """球队数据配置"""
    BASE_URL: str = "https://stats.nba.com/stats"
    CACHE_PATH = NBAConfig.PATHS.TEAM_CACHE_DIR
    # 默认缓存时间（设为0表示默认不缓存）
    DEFAULT_CACHE_DURATION: timedelta = timedelta(days=180)
    # 该列表包含了 NBA 所有球队的唯一 ID
    ALL_TEAM_LIST = [
        1610612739,  # 克利夫兰骑士 (Cavaliers)
        1610612760,  # 俄克拉荷马城雷霆 (Thunder)
        1610612738,  # 波士顿凯尔特人 (Celtics)
        1610612743,  # 丹佛掘金 (Nuggets)
        1610612752,  # 纽约尼克斯 (Knicks)
        1610612747,  # 洛杉矶湖人 (Lakers)
        1610612749,  # 密尔沃基雄鹿 (Bucks)
        1610612754,  # 印第安纳步行者 (Pacers)
        1610612763,  # 孟菲斯灰熊 (Grizzlies)
        1610612744,  # 金州勇士 (Warriors)
        1610612765,  # 底特律活塞 (Pistons)
        1610612737,  # 亚特兰大老鹰 (Hawks)
        1610612750,  # 明尼苏达森林狼 (Timberwolves)
        1610612746,  # 洛杉矶快船 (Clippers)
        1610612753,  # 奥兰多魔术 (Magic)
        1610612741,  # 芝加哥公牛 (Bulls)
        1610612758,  # 萨克拉门托国王 (Kings)
        1610612742,  # 达拉斯独行侠 (Mavericks)
        1610612748,  # 迈阿密热火 (Heat)
        1610612756,  # 菲尼克斯太阳 (Suns)
        1610612761,  # 多伦多猛龙 (Raptors)
        1610612751,  # 布鲁克林篮网 (Nets)
        1610612757,  # 波特兰开拓者 (Trail Blazers)
        1610612755,  # 费城76人 (76ers)
        1610612759,  # 圣安东尼奥马刺 (Spurs)
        1610612740,  # 新奥尔良鹈鹕 (Pelicans)
        1610612766,  # 夏洛特黄蜂 (Hornets)
        1610612762,  # 犹他爵士 (Jazz)
        1610612764,  # 华盛顿奇才 (Wizards)
        1610612745  # 休斯顿火箭 (Rockets)
    ]


class TeamFetcher(BaseNBAFetcher):
    """NBA球队数据获取器"""

    def __init__(self, custom_config: Optional[TeamConfig] = None):
        """初始化球队数据获取器"""

        self.team_config = custom_config or TeamConfig()
        # 配置缓存:
        cache_config = BaseCacheConfig(
            duration=self.team_config.DEFAULT_CACHE_DURATION,  # 使用默认缓存时间
            root_path=self.team_config.CACHE_PATH,
        )

        # 创建基础请求配置
        base_config = BaseRequestConfig(
            base_url=self.team_config.BASE_URL,
            cache_config=cache_config
        )

        # 初始化基类
        super().__init__(base_config)

    def get_team_details(self, team_id: int, force_update: bool = False) -> Optional[Dict[str, Any]]:
        """获取球队详细信息
        1. 使用基类的 fetch_data 方法
        2. 优化了缓存键生成
        3. 改进了错误处理
        """
        if not isinstance(team_id, int) or team_id <= 0:
            raise ValueError("team_id must be a positive integer")

        try:
            # 定义缓存标识和状态键
            cache_key = f"team_details_{team_id}"  # 使用teamid以区分
            cache_status_key = 'team_details'  # 触发半年缓存

            # 使用 build_url 构建URL并请求
            response = self.fetch_data(
                endpoint='teamdetails', # Use endpoint instead of url
                params={"TeamID": team_id},
                cache_key=cache_key,
                cache_status_key=cache_status_key,  # 使用状态键触发动态时长
                force_update=force_update
            )

            return response if response else None

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
            self.logger.info("开始同步所有NBA球队详细信息")
        else:
            self.logger.info(f"开始同步指定的{len(team_ids)}支球队详细信息: {team_ids[:3]}...")

        # 如果强制更新，清理旧的缓存文件，先检查文件权限再执行
        if force_update:
            progress_file = self.config.cache_config.root_path / "batch_multiple_teams_details_progress.json"
            if progress_file.exists() and progress_file.is_file() and os.access(progress_file, os.W_OK):
                progress_file.unlink()
                self.logger.info("已清除球队同步进度缓存")
            elif progress_file.exists():
                self.logger.error(f"无法清除进度文件: 权限不足或非常规文件 | path={progress_file}")

        # 获取原始结果（字符串键）
        string_key_results = self.batch_fetch(
            ids=team_ids,
            fetch_func=lambda team_id: self.get_team_details(team_id, force_update),
            task_name="multiple_teams_details",
            batch_size=5  # 球队少，可以用小批量
        )

        # 将字符串键转换为整数键以匹配返回类型声明
        return {int(k): v for k, v in string_key_results.items()}

    # 在TeamFetcher中添加获取球队Logo的方法
    def get_team_logo(self, team_id: int) -> Optional[bytes]:
        """获取球队Logo

        Args:
            team_id: 球队ID

        Returns:
            Optional[bytes]: Logo二进制数据
        """
        if not isinstance(team_id, int) or team_id <= 0:
            raise ValueError("team_id must be a positive integer")

        # 直接从URL下载
        logo_url = f"https://cdn.nba.com/logos/nba/{team_id}/primary/L/logo.svg"
        try:
            logo_data = self.http_manager.make_binary_request(logo_url)
            # 重要操作统一使用info
            self.logger.info(f"成功获取{team_id}球队Logo")
            # 详细URL信息使用debug
            self.logger.debug(f"Logo URL: {logo_url}")
            return logo_data
        except Exception as e:
            self.logger.error(f"获取球队(ID:{team_id})logo失败: {e}")
            return None

    def get_multiple_team_logos(self, team_ids: Optional[List[int]] = None) -> Dict[int, Optional[bytes]]:
        """批量获取多支球队Logo

        Args:
            team_ids: 球队ID列表

        Returns:
            Dict[int, Optional[bytes]]: 球队Logo数据字典
        """
        # 如果未提供team_ids，则使用所有球队
        if team_ids is None:
            team_ids = self.team_config.ALL_TEAM_LIST

        self.logger.info(f"批量获取球队Logo | count={len(team_ids)} | task=get_logos")

        # 使用批量获取框架，移除force_update参数
        string_key_results = self.batch_fetch(
            ids=team_ids,
            fetch_func=lambda team_id: self.get_team_logo(team_id),
            task_name="multiple_team_logos",
            batch_size=5
        )

        # 将字符串键转换为整数键
        return {int(k): v for k, v in string_key_results.items()}

    def cleanup_cache(self, older_than: Optional[timedelta] = None) -> None:
        """清理 TeamFetcher 相关的缓存数据。
        此方法会清理由 TeamFetcher 创建的，且修改时间早于指定 'older_than'
        时间点的缓存文件（主要是JSON详情文件）。
        默认情况下，会清理比球队详情缓存时间（半年）稍旧的缓存文件。
        """
        try:
            if older_than is None:
                # 使用配置中的详情缓存时间 + 1 天作为默认清理阈值
                cache_age = self.team_config.DEFAULT_CACHE_DURATION + timedelta(days=1)
                self.logger.info(f"未指定清理阈值，使用默认值：清理比球队详情缓存期更旧的缓存（实际阈值: {cache_age}）")
            else:
                cache_age = older_than
                self.logger.info(f"请求清理比 {cache_age} 更旧的 TeamFetcher 缓存数据")

            cleanup_prefix = self.__class__.__name__.lower()
            self.cache_manager.clear(
                prefix=cleanup_prefix,
                age=cache_age
            )
            self.logger.info(f"TeamFetcher 缓存清理完成 (清理 '{cleanup_prefix}' 前缀下早于 {cache_age} 的文件)")

        except Exception as e:
            self.logger.error(f"清理 TeamFetcher 缓存失败: {e}", exc_info=True)