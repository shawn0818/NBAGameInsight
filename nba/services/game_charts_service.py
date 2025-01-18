import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Arc
import matplotlib.lines as mlines
from nba.models.game_model import Game, ShotQualifier
from dataclasses import dataclass
from nba.services.game_data_service import NBAGameDataProvider


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
        self.figure_path = figure_path or Path("figures")
        self.game_data_service = game_data_service
        self.setup_style()

    def setup_style(self) -> None:
        """设置matplotlib的基础样式"""
        plt.style.use('fivethirtyeight')
        plt.rcParams['font.family'] = ['Microsoft YaHei', 'SimHei', 'sans-serif']

    def plot_player_shots(self,
                          game: Game,
                          player_id: Optional[int] = None,
                          title: Optional[str] = None,
                          output_path: Optional[str] = None,
                          show_stats: bool = True) -> Optional[plt.Figure]:
        """
        绘制球员投篮图
        """
        try:
            if not game:
                self.logger.error("未提供比赛数据")
                return None

            shots = self.game_data_service.get_filtered_events(game=game, player_id=player_id, event_type="2pt")
            shots.extend(self.game_data_service.get_filtered_events(game=game, player_id=player_id, event_type="3pt"))

            if not shots:
               self.logger.error(f"未找到球员 {player_id} 的投篮数据")
               return None

            fig, ax = plt.subplots(figsize=(12, 11))
            court_renderer = CourtRenderer(ax)
            court_renderer.draw_court()

            shot_stats = self._calculate_shot_stats(shots)

            # 绘制投篮点
            for shot in shots:
                coords = shot.get('coordinates', {})
                x = coords.get('x')
                y = coords.get('y')

                if x is None or y is None:
                   continue

                marker_style = self._get_marker_style(shot)
                ax.scatter(x, y, **marker_style)

                self._add_shot_qualifier_annotation(ax, shot, x, y)

            self._add_legend(ax)

            if show_stats:
               self._add_stats_text(ax, shot_stats)

            if title:
               ax.set_title(title)

            if output_path:
               self._save_figure(fig, output_path)

            return fig

        except Exception as e:
            self.logger.error(f"绘制投篮图时出错: {str(e)}", exc_info=True)
            return None

    def _calculate_shot_stats(self, shots: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算投篮统计信息"""
        total_shots = len(shots)
        made_shots = sum(1 for shot in shots
                         if shot.get('shot_info', {}).get('result') == 'Made')
        assisted_shots = sum(1 for shot in shots
                             if shot.get('shot_info', {}).get('assist'))

        return {
            'total': total_shots,
            'made': made_shots,
            'assisted': assisted_shots,
            'pct': made_shots / total_shots if total_shots > 0 else 0,
            'assisted_pct': assisted_shots / made_shots if made_shots > 0 else 0
        }

    def _get_marker_style(self, shot: Dict[str, Any]) -> Dict[str, Any]:
        """获取投篮点的标记样式"""
        is_made = shot.get('shot_info', {}).get('result') == 'Made'
        has_assist = shot.get('shot_info', {}).get('assist') is not None

        if is_made:
            if has_assist:
                return {'marker': '*', 'c': 'green', 's': 200}
            return {'marker': 'o', 'c': 'blue', 's': 100}
        return {'marker': 'x', 'c': 'red', 's': 100}

    def _add_shot_qualifier_annotation(self, ax: plt.Axes, shot: Dict[str, Any],
                                       x: float, y: float) -> None:
        """添加投篮限定词注释"""
        if shot.get('shot_info', {}).get('result') == 'Made':
            qualifiers = shot.get('shot_info', {}).get('qualifiers', [])
            if qualifiers:
                for qualifier in qualifiers:
                    if qualifier in ShotQualifier.__members__:
                        ax.annotate(
                            ShotQualifier(qualifier).value,
                            (x, y),
                            xytext=(5, 5),
                            textcoords='offset points',
                            fontsize=8,
                            alpha=0.7
                        )

    def _add_legend(self, ax: plt.Axes) -> None:
        """添加图例"""
        ax.legend([
            plt.Line2D([0], [0], marker='*', color='w', markerfacecolor='green',
                       markersize=15, label='助攻命中'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='blue',
                       markersize=10, label='个人命中'),
            plt.Line2D([0], [0], marker='x', color='w', markerfacecolor='red',
                       markersize=10, label='未命中')
        ], loc='upper right')

    def _add_stats_text(self, ax: plt.Axes, stats: Dict[str, Any]) -> None:
        """添加统计信息文本"""
        stats_text = (
            f"总投篮: {stats['total']}\n"
            f"命中: {stats['made']} ({stats['pct']:.1%})\n"
            f"助攻命中: {stats['assisted']} ({stats['assisted_pct']:.1%})"
        )
        ax.text(0.05, 0.95, stats_text,
                transform=ax.transAxes,
                bbox=dict(facecolor='white', alpha=0.8),
                fontsize=10,
                verticalalignment='top')

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