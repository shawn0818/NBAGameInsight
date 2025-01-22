import logging
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Arc
import matplotlib.lines as mlines
from nba.models.game_model import Game, ShotQualifier, BaseEvent
from dataclasses import dataclass
from nba.services.game_data_service import NBAGameDataProvider
from config.nba_config import NBAConfig


@dataclass
class CourtDimensions:
    """NBA标准球场尺寸（单位：英尺）"""
    length: float = 94.0
    width: float = 50.0
    three_point_line: float = 23.75
    paint_width: float = 16.0
    paint_height: float = 19.0
    free_throw_line: float = 15.0
    hoop_radius: float = 0.75
    half_court: float = 47.0
    restricted_area: float = 4.0
    backboard_width: float = 6.0
    backboard_height: float = 3.5
    inner_paint_width: float = 12.0


class CourtRenderer:
    """NBA标准球场渲染器"""

    def __init__(self, ax: plt.Axes,
                 color: str = 'black',
                 lw: float = 2,
                 paint_color: str = "#fab624",
                 background_color: str = "#FDF5E6"):
        """
        初始化球场渲染器

        Args:
            ax: matplotlib的Axes对象
            color: 线条颜色
            lw: 线条宽度
            paint_color: 油漆区颜色
            background_color: 背景色
        """
        self.ax = ax or plt.gca()
        self.color = color
        self.lw = lw
        self.paint_color = paint_color
        self.background_color = background_color
        self.dims = CourtDimensions()
        self.court_elements = []

    def draw_court(self) -> plt.Axes:
        """绘制NBA标准球场"""
        # 绘制篮筐
        hoop = Circle((0, 0), radius=self.dims.hoop_radius,
                      linewidth=self.lw, color=self.color, fill=False)

        # 绘制篮板
        backboard = Rectangle((-self.dims.backboard_width / 2, -self.dims.hoop_radius),
                              self.dims.backboard_width, -self.dims.backboard_height / 10,
                              linewidth=self.lw, color=self.color)

        # 绘制油漆区
        outer_box = Rectangle((-self.dims.paint_width / 2, -self.dims.paint_width / 3),
                              self.dims.paint_width, self.dims.paint_height,
                              linewidth=self.lw, color=self.color,
                              fill=False, zorder=0)

        inner_box = Rectangle((-self.dims.inner_paint_width / 2, -self.dims.paint_width / 3),
                              self.dims.inner_paint_width, self.dims.paint_height,
                              linewidth=self.lw, color=self.color,
                              fill=False, zorder=0)

        # 罚球圈
        top_free_throw = Arc((0, self.dims.free_throw_line),
                             self.dims.inner_paint_width, self.dims.inner_paint_width,
                             theta1=0, theta2=180,
                             linewidth=self.lw, color=self.color,
                             fill=False, zorder=0)

        bottom_free_throw = Arc((0, self.dims.free_throw_line),
                                self.dims.inner_paint_width, self.dims.inner_paint_width,
                                theta1=180, theta2=0,
                                linewidth=self.lw, color=self.color,
                                linestyle='dashed', zorder=0)

        # 禁区
        restricted = Arc((0, 0), self.dims.restricted_area * 2, self.dims.restricted_area * 2,
                         theta1=0, theta2=180,
                         linewidth=self.lw, color=self.color, zorder=0)

        # 三分线
        corner_three_a = Rectangle((-self.dims.width / 2, -self.dims.paint_width / 3), 0, 14,
                                   linewidth=self.lw, color=self.color, zorder=0)
        corner_three_b = Rectangle((self.dims.width / 2, -self.dims.paint_width / 3), 0, 14,
                                   linewidth=self.lw, color=self.color, zorder=0)
        three_arc = Arc((0, 0), self.dims.three_point_line * 2, self.dims.three_point_line * 2,
                        theta1=22, theta2=158,
                        linewidth=self.lw, color=self.color, zorder=0)

        # 中场区域
        center_outer_arc = Arc((0, self.dims.half_court), 12, 12,
                               theta1=180, theta2=0,
                               linewidth=self.lw, color=self.color, zorder=0)
        center_inner_arc = Arc((0, self.dims.half_court), 4, 4,
                               theta1=180, theta2=0,
                               linewidth=self.lw, color=self.color, zorder=0)

        # 场地边界
        outer_lines = Rectangle((-self.dims.width / 2, -5),
                                self.dims.width, self.dims.length,
                                linewidth=self.lw, color=self.color, fill=None)

        # 背景
        outer_lines_fill = Rectangle((-self.dims.width / 2, -5),
                                     self.dims.width, self.dims.length,
                                     color=self.background_color,
                                     fill=True, zorder=-2)

        # 油漆区背景
        paint_background = Rectangle((-self.dims.paint_width / 2, -self.dims.paint_width / 3),
                                     self.dims.paint_width, self.dims.paint_height,
                                     linewidth=self.lw,
                                     color=self.paint_color,
                                     fill=True, zorder=-1)

        # 将所有元素添加到列表
        self.court_elements = [
            hoop, backboard, outer_box, inner_box,
            top_free_throw, bottom_free_throw, restricted,
            corner_three_a, corner_three_b, three_arc,
            center_outer_arc, center_inner_arc,
            outer_lines, outer_lines_fill, paint_background
        ]

        # 将所有元素添加到图表
        for element in self.court_elements:
            self.ax.add_patch(element)

        # 设置坐标轴
        self._setup_axes()

        return self.ax

    def _setup_axes(self) -> None:
        """设置坐标轴属性"""
        self.ax.set_xlim(-self.dims.width / 2, self.dims.width / 2)
        self.ax.set_ylim(-5, self.dims.length / 2)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.ax.set_aspect('equal')
        self.ax.axhline(y=0, color=self.color, linewidth=self.lw, linestyle='--')
        self.ax.axvline(x=0, color=self.color, linewidth=self.lw, linestyle='--')


class GameChartsService:
    """NBA比赛数据可视化服务"""

    def __init__(self, game_data_service: NBAGameDataProvider, figure_path: Optional[Path] = None):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.figure_path = figure_path or NBAConfig.PATHS.PICTURES_DIR
        self.game_data_service = game_data_service
        self._setup_style()

    def _setup_style(self) -> None:
        """设置matplotlib的基础样式"""
        try:
            plt.style.use('fivethirtyeight')
            plt.rcParams['font.family'] = ['Microsoft YaHei', 'SimHei', 'sans-serif']
        except Exception as e:
            self.logger.warning(f"设置样式失败，使用默认样式: {str(e)}")

    def plot_player_shots(self,
                          game: Game,
                          player_id: Optional[int] = None,
                          title: Optional[str] = None,
                          output_path: Optional[str] = None,
                          show_stats: bool = True) -> Tuple[Optional[plt.Figure], Dict[str, Any]]:
        """绘制球员投篮图"""

        shot_stats = {'total': 0, 'made': 0, 'assisted': 0, 'unassisted': 0}

        try:
            if not isinstance(game, Game):
                self.logger.error("传入的不是有效的Game对象")
                return None, shot_stats

            # 获取投篮数据
            shots = game.get_shot_data(player_id)

            if not shots:
                self.logger.warning(f"未找到球员 {player_id} 的投篮数据")
                return None, shot_stats

            # 计算统计信息
            shot_stats = self._calculate_shot_stats(shots)

            # 创建图表
            fig, ax = plt.subplots(figsize=(12, 11))

            try:
                court_renderer = CourtRenderer(ax)
                court_renderer.draw_court()
            except Exception as e:
                self.logger.error(f"绘制球场失败: {str(e)}")
                plt.close(fig)
                return None, shot_stats

            # 绘制投篮点
            self._plot_shots(ax, shots)

            # 添加图例和统计信息
            if show_stats:
                try:
                    self._add_shot_stats_text(ax, shot_stats)
                except Exception as e:
                    self.logger.warning(f"添加统计信息失败: {str(e)}")

            try:
                self._add_shot_legend(ax)
            except Exception as e:
                self.logger.warning(f"添加图例失败: {str(e)}")

            if title:
                ax.set_title(title)

            # 保存图表
            if output_path:
                try:
                    self._save_figure(fig, output_path)
                except Exception as e:
                    self.logger.error(f"保存图表失败: {str(e)}")

            return fig, shot_stats

        except Exception as e:
            self.logger.error(f"绘制投篮图时出错: {str(e)}", exc_info=True)
            return None, shot_stats

    def plot_player_assists(self,
                            game: Game,
                            passer_id: int,
                            title: Optional[str] = None,
                            output_path: Optional[str] = None,
                            show_stats: bool = True) -> Tuple[Optional[plt.Figure], Dict[str, Any]]:
        """绘制球员助攻位置图"""

        assist_stats = {
            'total_assists': 0,
            'twos_assisted': 0,
            'threes_assisted': 0,
            'points_created': 0,
            'assisted_players': set()
        }

        try:
            if not isinstance(game, Game):
                self.logger.error("传入的不是有效的Game对象")
                return None, assist_stats

            # 获取所有助攻位置数据
            assisted_shots = game.get_assisted_shot_data(passer_id)

            if not assisted_shots:
                self.logger.warning(f"未找到球员 {passer_id} 的助攻数据")
                return None, assist_stats

            # 创建图表
            fig, ax = plt.subplots(figsize=(12, 11))
            court_renderer = CourtRenderer(ax)
            court_renderer.draw_court()

            # 计算统计信息并绘制位置点
            self._plot_assisted_shots(ax, assisted_shots, assist_stats)

            if show_stats:
                self._add_assist_stats_text(ax, assist_stats)

            if title:
                ax.set_title(title)

            if output_path:
                self._save_figure(fig, output_path)

            return fig, assist_stats

        except Exception as e:
            self.logger.error(f"绘制助攻位置图时出错: {str(e)}", exc_info=True)
            return None, assist_stats

    def plot_player_scoring_impact(self,
                                   game: Game,
                                   player_id: int,
                                   title: Optional[str] = None,
                                   output_path: Optional[str] = None,
                                   show_stats: bool = True) -> Tuple[Optional[plt.Figure], Dict[str, Any]]:
        """绘制球员得分影响力图(包含个人投篮和助攻位置)"""

        stats = {
            'shots': {'total': 0, 'made': 0, 'points': 0},
            'assists': {'total': 0, 'points_created': 0, 'assisted_players': set()}
        }

        try:
            if not isinstance(game, Game):
                self.logger.error("传入的不是有效的Game对象")
                return None, stats

            # 获取投篮和助攻数据
            shots = game.get_shot_data(player_id)
            assisted_shots = game.get_assisted_shot_data(player_id)

            if not shots and not assisted_shots:
                self.logger.warning(f"未找到球员 {player_id} 的相关数据")
                return None, stats

            # 创建图表
            fig, ax = plt.subplots(figsize=(12, 11))
            court_renderer = CourtRenderer(ax)
            court_renderer.draw_court()

            # 绘制个人投篮
            for shot in shots:
                x = shot.get('xLegacy')
                y = shot.get('yLegacy')
                if x is None or y is None:
                    continue

                made = shot.get('shotResult') == 'Made'
                stats['shots']['total'] += 1

                if made:
                    stats['shots']['made'] += 1
                    stats['shots']['points'] += 3 if shot.get('actionType') == '3pt' else 2
                    marker = 'o'
                    color = 'blue'
                    size = 100
                else:
                    marker = 'x'
                    color = 'red'
                    size = 100

                ax.scatter(x, y, c=color, marker=marker, s=size)

            # 绘制助攻位置
            for shot in assisted_shots:
                x = shot.get('x')
                y = shot.get('y')
                if x is None or y is None:
                    continue

                stats['assists']['total'] += 1
                stats['assists']['assisted_players'].add(shot['shooter_name'])

                points = 3 if shot['shot_type'] == '3pt' else 2
                stats['assists']['points_created'] += points

                # 使用星号标记助攻位置,颜色区分二分和三分
                color = 'purple' if shot['shot_type'] == '3pt' else 'green'
                ax.scatter(x, y, c=color, marker='*', s=200)

                # 添加被助攻球员标注
                ax.annotate(shot['shooter_name'],
                            (x, y),
                            xytext=(5, 5),
                            textcoords='offset points',
                            fontsize=8)

            # 添加图例
            # 修改图例的添加方式
            legend_elements = [
                mlines.Line2D([], [], marker='o', color='w', markerfacecolor='blue',
                              markersize=10, label='个人命中'),
                mlines.Line2D([], [], marker='x', color='w', markerfacecolor='red',
                              markersize=10, label='个人未命中'),
                mlines.Line2D([], [], marker='*', color='w', markerfacecolor='green',
                              markersize=15, label='助攻二分球'),
                mlines.Line2D([], [], marker='*', color='w', markerfacecolor='purple',
                              markersize=15, label='助攻三分球')
            ]

            # 正确的图例添加方式
            ax.legend(handles=legend_elements, loc='upper right')

            if show_stats:
                # 计算总得分影响力
                total_impact = stats['shots']['points'] + stats['assists']['points_created']
                stats_text = (
                    f"个人得分表现:\n"
                    f"  投篮: {stats['shots']['made']}/{stats['shots']['total']} "
                    f"({stats['shots']['made'] / stats['shots']['total'] * 100:.1f}%)\n"
                    f"  得分: {stats['shots']['points']}\n\n"
                    f"组织进攻表现:\n"
                    f"  助攻数: {stats['assists']['total']}\n"
                    f"  创造得分: {stats['assists']['points_created']}\n"
                    f"  助攻队友数: {len(stats['assists']['assisted_players'])}\n\n"
                    f"总得分影响力: {total_impact}"
                )
                ax.text(0.05, 0.95, stats_text,
                        transform=ax.transAxes,
                        bbox=dict(facecolor='white', alpha=0.8),
                        fontsize=10,
                        verticalalignment='top')

            if title:
                ax.set_title(title)

            if output_path:
                self._save_figure(fig, output_path)

            return fig, stats

        except Exception as e:
            self.logger.error(f"绘制得分影响力图时出错: {str(e)}", exc_info=True)
            return None, stats

    def _calculate_shot_stats(self, shots: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算投篮统计信息"""
        stats = {'total': 0, 'made': 0, 'assisted': 0, 'unassisted': 0}

        for shot in shots:
            stats['total'] += 1
            if shot.get('shotResult') == 'Made':
                stats['made'] += 1
                if shot.get('assisted'):
                    stats['assisted'] += 1
                else:
                    stats['unassisted'] += 1

        if stats['total'] > 0:
            stats['fg_pct'] = stats['made'] / stats['total'] * 100
            if stats['made'] > 0:
                stats['assisted_pct'] = stats['assisted'] / stats['made'] * 100

        return stats

    def _plot_shots(self, ax: plt.Axes, shots: List[Dict[str, Any]]) -> None:
        """绘制投篮点"""
        for shot in shots:
            x = shot.get('xLegacy')
            y = shot.get('yLegacy')
            if x is None or y is None:
                continue

            made = shot.get('shotResult') == 'Made'
            assisted = shot.get('assisted', False)

            # 根据投篮结果和是否被助攻选择不同的标记样式
            if made:
                if assisted:
                    marker = '*'
                    color = 'green'
                    size = 200
                else:
                    marker = 'o'
                    color = 'blue'
                    size = 100
            else:
                marker = 'x'
                color = 'red'
                size = 100

            ax.scatter(x, y, c=color, marker=marker, s=size)

    def _plot_assisted_shots(self, ax: plt.Axes,
                             shots: List[Dict[str, Any]],
                             stats: Dict[str, Any]) -> None:
        """绘制助攻位置点"""
        for shot in shots:
            x = shot.get('x')
            y = shot.get('y')
            if x is None or y is None:
                continue

            # 更新统计信息
            stats['total_assists'] += 1
            stats['assisted_players'].add(shot['shooter_name'])
            if shot['shot_type'] == '3pt':
                stats['threes_assisted'] += 1
                stats['points_created'] += 3
                color = 'red'
            else:
                stats['twos_assisted'] += 1
                stats['points_created'] += 2
                color = 'blue'

            # 绘制位置点
            ax.scatter(x, y, c=color, marker='*', s=100)

            # 添加投篮者姓名标注
            ax.annotate(shot['shooter_name'],
                        (x, y),
                        xytext=(5, 5),
                        textcoords='offset points',
                        fontsize=8)

    def _add_shot_stats_text(self, ax: plt.Axes, stats: Dict[str, Any]) -> None:
        """添加投篮统计信息文本"""
        stats_text = (
            f"总投篮: {stats['total']}\n"
            f"命中: {stats['made']} ({stats.get('fg_pct', 0):.1f}%)\n"
            f"助攻命中: {stats['assisted']}\n"
            f"无助攻命中: {stats['unassisted']}"
        )
        ax.text(0.05, 0.95, stats_text,
                transform=ax.transAxes,
                bbox=dict(facecolor='white', alpha=0.8),
                fontsize=10,
                verticalalignment='top')

    def _add_assist_stats_text(self, ax: plt.Axes, stats: Dict[str, Any]) -> None:
        """添加助攻统计信息文本"""
        stats_text = (
            f"总助攻数: {stats['total_assists']}\n"
            f"助攻二分球: {stats['twos_assisted']}\n"
            f"助攻三分球: {stats['threes_assisted']}\n"
            f"创造得分: {stats['points_created']}\n"
            f"助攻队友数: {len(stats['assisted_players'])}"
        )
        ax.text(0.05, 0.95, stats_text,
                transform=ax.transAxes,
                bbox=dict(facecolor='white', alpha=0.8),
                fontsize=10,
                verticalalignment='top')

    def _add_shot_legend(self, ax: plt.Axes) -> None:
        """添加投篮图例"""
        ax.legend([
            plt.Line2D([0], [0], marker='*', color='w', markerfacecolor='green',
                       markersize=15, label='助攻命中'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='blue',
                       markersize=10, label='个人命中'),
            plt.Line2D([0], [0], marker='x', color='w', markerfacecolor='red',
                       markersize=10, label='未命中')
        ], loc='upper right')

    def _save_figure(self, fig: plt.Figure, output_path: str, dpi: int = 300) -> None:
        """保存图表到文件"""
        try:
            output_path = self.figure_path / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_path, bbox_inches='tight', dpi=dpi)
            plt.close(fig)
            self.logger.info(f"图表已保存至 {output_path}")
        except Exception as e:
            self.logger.error(f"保存图表时出错: {e}")