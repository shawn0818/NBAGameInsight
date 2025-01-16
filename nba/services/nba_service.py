"""NBA统一服务模块

整合所有子服务功能，提供统一的接口
"""

from typing import Optional, Dict, Any, List, Union, Tuple
from pathlib import Path
import logging
from datetime import datetime

from nba.services.game_data_service import NBAGameDataProvider, ServiceConfig
from nba.services.game_video_service import GameVideoService
from nba.services.game_display_service import DisplayService, DisplayConfig, AIConfig
from nba.services.game_charts_service import (
    NBAVisualizer,
    GameFlowVisualizer,
    PlayerPerformanceVisualizer,
    TeamPerformanceVisualizer,
    InteractionVisualizer,
    ShotChartVisualizer
)
from nba.models.game_model import Game, PlayerStatistics, TeamStats
from nba.models.video_model import VideoAsset, ContextMeasure

logger = logging.getLogger(__name__)


class NBAService:
    """NBA统一服务接口，整合所有子服务功能"""

    def __init__(
            self,
            default_team: Optional[str] = None,
            default_player: Optional[str] = None,
            date_str: Optional[str] = None,
            display_language: str = "zh_CN",
            enable_ai: bool = True
    ):
        """初始化NBA服务

        Args:
            default_team: 默认的球队名称，如果不指定则使用ServiceConfig中的默认值
            default_player: 默认的球员名称，如果不指定则使用ServiceConfig中的默认值
            date_str: 默认的日期字符串，如果不指定则使用ServiceConfig中的默认值
            display_language: 显示语言，默认中文
            enable_ai: 是否启用AI分析功能
        """
        self.logger = logger.getChild(self.__class__.__name__)

        # 配置服务 - 只传入非None的值
        service_config_params = {}
        if default_team is not None:
            service_config_params['default_team'] = default_team
        if default_player is not None:
            service_config_params['default_player'] = default_player
        if date_str is not None:
            service_config_params['date_str'] = date_str

        service_config = ServiceConfig(**service_config_params)

        display_config = DisplayConfig(
            language=display_language,
            show_advanced_stats=True
        )

        ai_config = AIConfig() if enable_ai else None

        # 初始化子服务
        self._data_provider = NBAGameDataProvider(config=service_config)
        self._video_service = GameVideoService()
        self._display_service = DisplayService(
            display_config=display_config,
            ai_config=ai_config
        )

        # 可视化服务
        self._shot_visualizer = ShotChartVisualizer()
        self._player_visualizer = PlayerPerformanceVisualizer()
        self._team_visualizer = TeamPerformanceVisualizer()
        self._interaction_visualizer = InteractionVisualizer()
        self._flow_visualizer = GameFlowVisualizer()

    def get_game(self, team: Optional[str] = None,
                 date: Optional[str] = None) -> Optional[Game]:
        """获取比赛数据"""
        return self._data_provider.get_game(team, date)

    def display_game_info(
            self,
            team: Optional[str] = None,
            date: Optional[str] = None,
            include_ai_analysis: bool = False
    ) -> Dict[str, Any]:
        """显示比赛信息，支持AI分析

        Args:
            team: 球队名称
            date: 比赛日期
            include_ai_analysis: 是否包含AI分析报告

        Returns:
            Dict包含比赛信息和可选的AI分析
        """
        try:
            game = self.get_game(team, date)
            if not game:
                self.logger.error("未找到比赛数据")
                return {}

            basic_info = self.get_game_basic_info(game)
            stats = self.get_game_stats(game)

            result = {
                "basic_info": basic_info,
                "statistics": stats
            }

            if include_ai_analysis:
                ai_analysis = self._display_service.format_game_report(game)
                result["ai_analysis"] = ai_analysis

            return result

        except Exception as e:
            self.logger.error(f"生成比赛信息时出错: {e}")
            return {}

    def download_game_highlights(
            self,
            team: Optional[str] = None,
            player: Optional[str] = None,
            date: Optional[str] = None,
            action_type: str = "FGM",
            to_gif: bool = False,
            quality: str = "hd",
            compress: bool = False,
            output_dir: Optional[Path] = None
    ) -> Dict[str, Path]:
        """下载比赛精彩片段"""
        try:
            game = self.get_game(team, date)
            if not game:
                self.logger.error("未找到比赛数据")
                return {}

            videos = self.get_game_videos(
                game_id=game.game.gameId,
                player=player,
                team=team,
                action_type=action_type
            )

            if not videos:
                self.logger.error("未找到视频数据")
                return {}

            self.logger.info(f"找到 {len(videos)} 个视频")

            return self._video_service.batch_download(
                videos=videos,
                output_dir=output_dir,
                quality=quality,
                to_gif=to_gif,
                compress=compress
            )

        except Exception as e:
            self.logger.error(f"下载视频时出错: {str(e)}", exc_info=True)
            return {}

    def create_shot_chart(
            self,
            player: Optional[str] = None,
            team: Optional[str] = None,
            date: Optional[str] = None,
            output_path: Optional[str] = None,
            show_misses: bool = True,
            show_makes: bool = True,
            annotate: bool = False,
            add_player_photo: bool = True,
            creator_info: Optional[str] = None

    ) -> None:
        """生成投篮图表"""
        try:
            game = self.get_game(team, date)
            if not game:
                self.logger.error("未找到比赛数据")
                return

            player_id = self._data_provider._get_player_id(player) if player else None
            shot_data = game.get_shot_data(player_id=player_id)

            # 将 shot_data 列表转换为 DataFrame
            import pandas as pd
            shot_df = pd.DataFrame(shot_data)

            self._shot_visualizer.plot_shot_chart(
                shot_data=shot_df,  # 传递 DataFrame
                player_id=player_id,
                player_name=player,
                team_name=team,
                output_path=output_path,
                show_misses=show_misses,
                show_makes=show_makes,
                annotate=annotate,
                add_player_photo=add_player_photo
            )
        except Exception as e:
            self.logger.error(f"生成投篮图表时出错: {e}")

    def create_player_performance_chart(
            self,
            player: Optional[str] = None,
            team: Optional[str] = None,
            date: Optional[str] = None,
            output_path: Optional[str] = None
    ) -> None:
        """生成球员表现分析图表"""
        try:
            game = self.get_game(team, date)
            if not game:
                self.logger.error("未找到比赛数据")
                return

            player_id = self._data_provider._get_player_id(player) if player else None
            player_name = player or self._data_provider.config.default_player

            if hasattr(game, 'playByPlay') and game.playByPlay:
                plays = game.playByPlay.actions
                self._player_visualizer.plot_performance_timeline(
                    plays=plays,
                    player_name=player_name,
                    output_path=output_path
                )
            else:
                self.logger.error("未找到比赛回放数据")

        except Exception as e:
            self.logger.error(f"生成球员表现图表时出错: {e}")

    def create_team_comparison(
            self,
            team: Optional[str] = None,
            date: Optional[str] = None,
            output_path: Optional[str] = None
    ) -> None:
        """生成球队对比图表"""
        try:
            game = self.get_game(team, date)
            if not game:
                self.logger.error("未找到比赛数据")
                return

            self._team_visualizer.plot_team_comparison(
                home_stats=game.game.homeTeam.statistics,
                away_stats=game.game.awayTeam.statistics,
                home_team=game.game.homeTeam.teamName,
                away_team=game.game.awayTeam.teamName,
                output_path=output_path
            )
        except Exception as e:
            self.logger.error(f"生成球队对比图表时出错: {e}")

    def create_assist_network(
            self,
            team: Optional[str] = None,
            date: Optional[str] = None,
            output_path: Optional[str] = None
    ) -> None:
        """生成助攻网络图"""
        try:
            game = self.get_game(team, date)
            if not game:
                self.logger.error("未找到比赛数据")
                return

            if not game.playByPlay or not game.playByPlay.actions:
                self.logger.error("未找到有效的比赛回放数据")
                return

            plays = self._data_provider.get_play_by_play(game)
            if not plays:
                self.logger.error("处理回放数据失败")
                return

            team_name = team or self._data_provider.config.default_team
            self._interaction_visualizer.plot_assist_network(
                plays=plays,
                team_name=team_name,
                output_path=output_path
            )

        except Exception as e:
            self.logger.error(f"生成助攻网络图时出错: {e}")

    def create_game_flow(
            self,
            team: Optional[str] = None,
            date: Optional[str] = None,
            output_path: Optional[str] = None
    ) -> None:
        """生成比赛流程图"""
        try:
            game = self.get_game(team, date)
            if not game:
                self.logger.error("未找到比赛数据")
                return

            if hasattr(game, 'playByPlay') and game.playByPlay:
                plays = game.playByPlay.actions
                self._flow_visualizer.plot_score_flow(
                    plays=plays,
                    home_team=game.game.homeTeam.teamName,
                    away_team=game.game.awayTeam.teamName,
                    output_path=output_path
                )
            else:
                self.logger.error("未找到比赛回放数据")

        except Exception as e:
            self.logger.error(f"生成比赛流程图时出错: {e}")

    def analyze_game_moments(
            self,
            team: Optional[str] = None,
            date: Optional[str] = None
    ) -> str:
        """分析比赛关键时刻"""
        try:
            game = self.get_game(team, date)
            if not game:
                return "未找到比赛数据"

            plays = []
            if hasattr(game, 'playByPlay') and game.playByPlay and game.playByPlay.actions:
                for action in game.playByPlay.actions:
                    play = {
                        "period": action.period,
                        "clock": action.clock,
                        "action_type": action.actionType.value if action.actionType else None,
                        "description": action.description,
                        "team": action.teamTricode,
                        "score": {
                            "home": action.scoreHome,
                            "away": action.scoreAway
                        } if action.scoreHome is not None else None
                    }
                    plays.append(play)

            return self._display_service.analyze_key_moments(plays)

        except Exception as e:
            self.logger.error(f"分析比赛关键时刻时出错: {e}")
            return "分析比赛关键时刻时出错"

    def refresh_data(self) -> None:
        """刷新所有数据"""
        try:
            self._data_provider.refresh_all_data()
            self.logger.info("数据刷新完成")
        except Exception as e:
            self.logger.error(f"刷新数据时出错: {e}")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出，清理资源"""
        if hasattr(self, '_data_provider'):
            try:
                self._data_provider.clear_cache()
            except Exception as e:
                self.logger.error(f"清理资源时出错: {e}")

    def display_player_stats(
            self,
            player: Optional[str] = None,
            date: Optional[str] = None,
            include_analysis: bool = False
    ) -> Dict[str, Any]:
        """显示球员数据，支持AI分析"""
        try:
            game = self.get_game(None, date)  # 先获取比赛数据
            if not game:
                self.logger.error("未找到比赛数据")
                return {}

            # 查找球员统计数据
            player_name = player or self._data_provider.config.default_player
            player_stats = None

            # 在主队和客队中查找球员
            for team_player in game.game.homeTeam.players + game.game.awayTeam.players:
                if team_player.name.lower() == player_name.lower():
                    player_stats = team_player.statistics
                    break

            if not player_stats:
                self.logger.error(f"未找到球员统计数据: {player_name}")
                return {}

            # 格式化球员统计数据
            stats = {
                "points": player_stats.points,
                "rebounds": player_stats.reboundsTotal,
                "assists": player_stats.assists,
                "steals": player_stats.steals,
                "blocks": player_stats.blocks,
                "turnovers": player_stats.turnovers,
                "minutes": player_stats.seconds_played / 60,
                "shooting": {
                    "fg": f"{player_stats.fieldGoalsMade}/{player_stats.fieldGoalsAttempted}",
                    "fg_pct": player_stats.fieldGoalsPercentage,
                    "three": f"{player_stats.threePointersMade}/{player_stats.threePointersAttempted}",
                    "three_pct": player_stats.threePointersPercentage,
                    "ft": f"{player_stats.freeThrowsMade}/{player_stats.freeThrowsAttempted}",
                    "ft_pct": player_stats.freeThrowsPercentage
                }
            }

            result = {"statistics": stats}

            if include_analysis:
                result["analysis"] = self._display_service.analyze_player_performance(
                    player_name,
                    stats
                )

            return result

        except Exception as e:
            self.logger.error(f"显示球员统计数据时出错: {e}")
            return {}

    def display_team_stats(
            self,
            team: Optional[str] = None,
            date: Optional[str] = None
    ) -> Dict[str, Any]:
        """显示球队统计数据"""
        try:
            game = self.get_game(team, date)
            if not game:
                self.logger.error("未找到比赛数据")
                return {}

            return {
                "home_team": {
                    "name": game.game.homeTeam.teamName,
                    "statistics": {
                        "field_goals": f"{game.game.homeTeam.statistics.get('fieldGoalsMade', 0)}/{game.game.homeTeam.statistics.get('fieldGoalsAttempted', 0)}",
                        "field_goals_pct": game.game.homeTeam.statistics.get('fieldGoalsPercentage', 0.0),
                        "three_points": f"{game.game.homeTeam.statistics.get('threePointersMade', 0)}/{game.game.homeTeam.statistics.get('threePointersAttempted', 0)}",
                        "three_points_pct": game.game.homeTeam.statistics.get('threePointersPercentage', 0.0),
                        "assists": game.game.homeTeam.statistics.get('assists', 0),
                        "rebounds": game.game.homeTeam.statistics.get('reboundsTotal', 0),
                        "steals": game.game.homeTeam.statistics.get('steals', 0),
                        "blocks": game.game.homeTeam.statistics.get('blocks', 0),
                        "turnovers": game.game.homeTeam.statistics.get('turnovers', 0)
                    }
                },
                "away_team": {
                    "name": game.game.awayTeam.teamName,
                    "statistics": {
                        "field_goals": f"{game.game.awayTeam.statistics.get('fieldGoalsMade', 0)}/{game.game.awayTeam.statistics.get('fieldGoalsAttempted', 0)}",
                        "field_goals_pct": game.game.awayTeam.statistics.get('fieldGoalsPercentage', 0.0),
                        "three_points": f"{game.game.awayTeam.statistics.get('threePointersMade', 0)}/{game.game.awayTeam.statistics.get('threePointersAttempted', 0)}",
                        "three_points_pct": game.game.awayTeam.statistics.get('threePointersPercentage', 0.0),
                        "assists": game.game.awayTeam.statistics.get('assists', 0),
                        "rebounds": game.game.awayTeam.statistics.get('reboundsTotal', 0),
                        "steals": game.game.awayTeam.statistics.get('steals', 0),
                        "blocks": game.game.awayTeam.statistics.get('blocks', 0),
                        "turnovers": game.game.awayTeam.statistics.get('turnovers', 0)
                    }
                }
            }

        except Exception as e:
            self.logger.error(f"显示球队统计数据时出错: {e}")
            return {}

    def get_game_videos(
            self,
            game_id: Optional[str] = None,
            player: Optional[str] = None,
            team: Optional[str] = None,
            action_type: str = "FGM"
    ) -> Dict[str, VideoAsset]:
        """获取比赛视频"""
        try:
            if not game_id:
                game = self.get_game(team)
                if not game:
                    self.logger.error("未找到比赛数据")
                    return {}
                game_id = game.game.gameId

            context_measure = getattr(ContextMeasure, action_type, ContextMeasure.FGM)
            player_id = self._data_provider._get_player_id(player) if player else None
            team_id = self._data_provider._get_team_id(team) if team else None

            return self._video_service.get_game_videos(
                game_id=game_id,
                context_measure=context_measure,
                player_id=player_id,
                team_id=team_id
            )
        except Exception as e:
            self.logger.error(f"获取比赛视频时出错: {e}")
            return {}

    def get_game_basic_info(self, game: Game) -> Dict[str, Any]:
        """获取比赛基本信息"""
        try:
            return {
                "game_time": game.game.gameTimeLocal,
                "arena": {
                    "name": game.game.arena.arenaName,
                    "city": game.game.arena.arenaCity,
                    "attendance": game.game.attendance
                },
                "officials": [
                    {
                        "name": official.name,
                        "position": official.assignment
                    }
                    for official in game.game.officials
                ],
                "status": game.game.gameStatusText
            }
        except Exception as e:
            self.logger.error(f"获取比赛基本信息时出错: {e}")
            return {}

    def get_game_stats(self, game: Game) -> Dict[str, Any]:
        """获取比赛统计数据"""
        try:
            return {
                "score": {
                    "home": game.game.homeTeam.score,
                    "away": game.game.awayTeam.score
                },
                "home_team": {
                    "name": game.game.homeTeam.teamName,
                    "stats": self._get_team_stats(game.game.homeTeam),
                    "players": [
                        {
                            "name": p.name,
                            "stats": self._get_player_stats(p.statistics)
                        }
                        for p in game.game.homeTeam.players
                    ]
                },
                "away_team": {
                    "name": game.game.awayTeam.teamName,
                    "stats": self._get_team_stats(game.game.awayTeam),
                    "players": [
                        {
                            "name": p.name,
                            "stats": self._get_player_stats(p.statistics)
                        }
                        for p in game.game.awayTeam.players
                    ]
                }
            }
        except Exception as e:
            self.logger.error(f"获取比赛统计数据时出错: {e}")
            return {}

    def get_play_by_play(self, game: Game) -> List[Dict[str, Any]]:
        """获取比赛回合数据，处理成适合AI分析的格式"""
        try:
            if not game.playByPlay or not game.playByPlay.actions:
                return []

            plays = []
            for action in game.playByPlay.actions:
                play = {
                    "period": action.period,
                    "clock": action.clock,
                    "action_type": action.actionType.value if action.actionType else None,
                    "description": action.description,
                    "team": action.teamTricode,
                    "score": {
                        "home": action.scoreHome,
                        "away": action.scoreAway
                    } if action.scoreHome is not None else None
                }
                plays.append(play)

            return plays
        except Exception as e:
            self.logger.error(f"获取比赛回合数据时出错: {e}")
            return []

    def _get_player_stats(self, stats: PlayerStatistics) -> Dict[str, Any]:
        """格式化球员统计数据"""
        try:
            return {
                "points": stats.points,
                "rebounds": stats.reboundsTotal,
                "assists": stats.assists,
                "steals": stats.steals,
                "blocks": stats.blocks,
                "turnovers": stats.turnovers,
                "minutes": stats.seconds_played / 60,
                "shooting": {
                    "fg": f"{stats.fieldGoalsMade}/{stats.fieldGoalsAttempted}",
                    "fg_pct": stats.fieldGoalsPercentage,
                    "three": f"{stats.threePointersMade}/{stats.threePointersAttempted}",
                    "three_pct": stats.threePointersPercentage,
                    "ft": f"{stats.freeThrowsMade}/{stats.freeThrowsAttempted}",
                    "ft_pct": stats.freeThrowsPercentage
                }
            }
        except Exception as e:
            self.logger.error(f"格式化球员统计数据时出错: {e}")
            return {}

    def _get_team_stats(self, team: TeamStats) -> Dict[str, Any]:
        """格式化球队统计数据"""
        try:
            stats = team.statistics
            if not isinstance(stats, dict):
                stats = {}

            return {
                "field_goals": f"{stats.get('fieldGoalsMade', 0)}/{stats.get('fieldGoalsAttempted', 0)}",
                "field_goals_pct": stats.get('fieldGoalsPercentage', 0.0),
                "three_points": f"{stats.get('threePointersMade', 0)}/{stats.get('threePointersAttempted', 0)}",
                "three_points_pct": stats.get('threePointersPercentage', 0.0),
                "rebounds": stats.get('reboundsTotal', 0),
                "assists": stats.get('assists', 0),
                "steals": stats.get('steals', 0),
                "blocks": stats.get('blocks', 0),
                "turnovers": stats.get('turnovers', 0)
            }
        except Exception as e:
            self.logger.error(f"格式化球队统计数据时出错: {e}")
            return {}
