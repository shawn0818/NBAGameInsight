"""
game_display_service.py
比赛数据显示服务，负责格式化和展示比赛相关的各类信息
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import logging
from functools import lru_cache
import hashlib
from datetime import datetime

from nba.services.ai_service import AIService
from nba.services.game_data_service import NBAGameDataProvider


@dataclass
class DisplayConfig:
    """显示配置类"""
    language: str = "zh_CN"
    show_advanced_stats: bool = True
    cache_size: int = 128


class DisplayService:
    """比赛数据显示服务"""

    def __init__(
            self,
            game_data_service: NBAGameDataProvider,
            display_config: DisplayConfig,
            ai_service: Optional[AIService] = None
    ):
        """初始化显示服务

        Args:
            game_data_service: 数据服务实例
            display_config: 显示配置
            ai_service: AI服务实例(可选)
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.game_data_service = game_data_service
        self.display_config = display_config
        self.ai_service = ai_service
        self._translation_cache = {}

    def _safe_get(self, data: Dict[str, Any], keys: List[str], default: Any = "N/A") -> Any:
        """安全获取嵌套字典数据

        Args:
            data: 源数据字典
            keys: 键的路径列表
            default: 默认值

        Returns:
            找到的值或默认值
        """
        try:
            result = data
            for key in keys:
                if not isinstance(result, dict):
                    return default
                result = result.get(key, default)
            return result if result is not None else default
        except Exception:
            return default

    def _validate_data(self, data: Dict[str, Any], required_fields: List[str]) -> bool:
        """验证数据完整性

        Args:
            data: 待验证的数据字典
            required_fields: 必需的字段列表

        Returns:
            数据是否有效
        """
        return all(self._safe_get(data, field.split('.')) != "N/A"
                   for field in required_fields)

    @lru_cache(maxsize=128)
    def _get_translation(self, text: str, target_language: str) -> str:
        """获取或缓存翻译结果

        Args:
            text: 待翻译文本
            target_language: 目标语言

        Returns:
            翻译后的文本
        """
        if not self.ai_service:
            return text

        cache_key = hashlib.md5(f"{text}:{target_language}".encode()).hexdigest()
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]

        translated = self.ai_service.translate(text=text, target_language=target_language)
        self._translation_cache[cache_key] = translated
        return translated

    def format_game_basic_info(self, game_data: Dict[str, Any]) -> Optional[str]:
        """格式化比赛基本信息

        Args:
            game_data: 比赛数据字典

        Returns:
            格式化的基本信息文本
        """
        required_fields = ['gameId', 'homeTeam.teamName', 'awayTeam.teamName']
        if not self._validate_data(game_data, required_fields):
            self.logger.error("无效的比赛基础数据")
            return None

        try:
            # 格式化比赛时间
            game_time = self._safe_get(game_data, ['gameTimeLocal'])
            try:
                formatted_time = datetime.strptime(game_time, "%Y-%m-%dT%H:%M:%S%z").strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                formatted_time = str(game_time)

            info_items = [
                f"比赛编号: {self._safe_get(game_data, ['gameId'])}",
                f"比赛时间: {formatted_time}",
                f"比赛地点: {self._safe_get(game_data, ['arena', 'arenaName'])}, "
                f"{self._safe_get(game_data, ['arena', 'arenaCity'])}",
                f"主队: {self._safe_get(game_data, ['homeTeam', 'teamName'])}",
                f"客队: {self._safe_get(game_data, ['awayTeam', 'teamName'])}",
                f"比赛状态: {self._safe_get(game_data, ['gameStatusText'])}",
                f"观众人数: {self._safe_get(game_data, ['attendance'])}"
            ]

            return self._get_translation(
                "\n".join(info_items),
                self.display_config.language
            )
        except Exception as e:
            self.logger.error(f"格式化比赛信息时出错: {str(e)}")
            return None

    def format_game_live_status(self, game_stats: Dict[str, Any]) -> Optional[str]:
        """格式化比赛实时状态

        Args:
            game_stats: 比赛统计数据字典

        Returns:
            格式化的比赛状态文本
        """
        required_fields = ['homeTeam.score', 'awayTeam.score']
        if not self._validate_data(game_stats, required_fields):
            return None

        try:
            home_team = self._safe_get(game_stats, ['homeTeam'], {})
            away_team = self._safe_get(game_stats, ['awayTeam'], {})

            status_items = [
                f"比赛状态: {self._safe_get(game_stats, ['gameStatusText'])}",
                f"当前比分: {self._safe_get(home_team, ['score'])} - "
                f"{self._safe_get(away_team, ['score'])}",
                "",
                f"主队 {self._safe_get(home_team, ['teamName'])}:",
                f"本节得分: {self._safe_get(home_team, ['periods', -1, 'score'], 0)}",
                f"犯规次数: {self._safe_get(home_team, ['fouls'], 0)}",
                "",
                f"客队 {self._safe_get(away_team, ['teamName'])}:",
                f"本节得分: {self._safe_get(away_team, ['periods', -1, 'score'], 0)}",
                f"犯规次数: {self._safe_get(away_team, ['fouls'], 0)}"
            ]

            return self._get_translation(
                "\n".join(status_items),
                self.display_config.language
            )
        except Exception as e:
            self.logger.error(f"格式化比赛状态时出错: {str(e)}")
            return None

    def format_player_stats(self, player_stats: Dict[str, Any]) -> Optional[str]:
        """格式化球员统计数据

        Args:
            player_stats: 球员统计数据字典

        Returns:
            格式化的球员统计文本
        """
        required_fields = ['name', 'statistics']
        if not self._validate_data(player_stats, required_fields):
            return None

        try:
            stats = self._safe_get(player_stats, ['statistics'], {})

            basic_items = [
                f"球员: {self._safe_get(player_stats, ['name'])}",
                f"上场时间: {self._safe_get(stats, ['minutes'])}",
                f"得分: {self._safe_get(stats, ['points'], 0)}",
                f"篮板: {self._safe_get(stats, ['reboundsTotal'], 0)}",
                f"助攻: {self._safe_get(stats, ['assists'], 0)}",
                f"抢断: {self._safe_get(stats, ['steals'], 0)}",
                f"盖帽: {self._safe_get(stats, ['blocks'], 0)}",
                f"失误: {self._safe_get(stats, ['turnovers'], 0)}"
            ]

            shooting_items = [
                f"投篮: {self._safe_get(stats, ['fieldGoalsMade'], 0)}/"
                f"{self._safe_get(stats, ['fieldGoalsAttempted'], 0)}",
                f"三分: {self._safe_get(stats, ['threePointersMade'], 0)}/"
                f"{self._safe_get(stats, ['threePointersAttempted'], 0)}"
            ]

            if self.display_config.show_advanced_stats:
                advanced_items = [
                    "",
                    "进阶数据:",
                    f"投篮命中率: {self._safe_get(stats, ['fieldGoalsPercentage'], 0):.1f}%",
                    f"三分命中率: {self._safe_get(stats, ['threePointersPercentage'], 0):.1f}%"
                ]
            else:
                advanced_items = []

            all_items = basic_items + shooting_items + advanced_items
            return self._get_translation(
                "\n".join(all_items),
                self.display_config.language
            )
        except Exception as e:
            self.logger.error(f"格式化球员统计时出错: {str(e)}")
            return None

    def process_event(self, event_data: Dict[str, Any]) -> Optional[str]:
        """处理比赛事件

        Args:
            event_data: 事件数据字典

        Returns:
            处理后的事件描述
        """
        try:
            event_time = (
                f"{self._safe_get(event_data, ['period'])}节 "
                f"{self._safe_get(event_data, ['clock'])}"
            )
            description = self._safe_get(event_data, ['description'])

            event_text = f"[{event_time}] {description}"
            return self._get_translation(
                event_text,
                self.display_config.language
            )
        except Exception as e:
            self.logger.error(f"处理比赛事件时出错: {str(e)}")
            return None

    def clear_cache(self) -> None:
        """清理缓存数据"""
        try:
            self._translation_cache.clear()
            self._get_translation.cache_clear()
            self.logger.info("显示服务缓存已清理")
        except Exception as e:
            self.logger.warning(f"清理缓存时出错: {str(e)}")