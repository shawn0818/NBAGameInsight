from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from matplotlib import pyplot as plt
from matplotlib.patches import Circle, Rectangle, Arc

from nba.models.game_model import Game
from nba.services.game_data_service import GameDataProvider
from config.nba_config import NBAConfig
from utils.logger_handler import AppLogger




class CourtRenderer:
    """NBA半场球场渲染器"""

    @staticmethod
    def draw_court():
        """
        Draw an NBA halfcourt with basket at the bottom
        Returns:
        - fig: matplotlib figure object
        - axis: matplotlib axis object
        """
        fig = plt.figure(figsize=(9, 9))
        axis = fig.add_subplot(111)

        # 设置球场底色
        court_shape = Rectangle(xy=(-250, -47.5), width=500, height=470,
                                linewidth=2, color='#F0F0F0', fill=True)
        court_shape.set_zorder(0)
        axis.add_patch(court_shape)

        # 绘制球场外框
        outer_lines = Rectangle(xy=(-250, -47.5), width=500, height=470,
                                linewidth=2, color='k', fill=False)
        axis.add_patch(outer_lines)

        # 绘制禁区并填充颜色
        paint = Rectangle(xy=(-80, -47.5), width=160, height=190,
                          linewidth=2, color='k', fill=True,
                          facecolor='#B0C4DE', alpha=0.3)  # 使用淡蓝色填充
        axis.add_patch(paint)

        # 绘制禁区内框
        inner_paint = Rectangle(xy=(-60, -47.5), width=120, height=190,
                                linewidth=2, color='k', fill=False)
        axis.add_patch(inner_paint)

        # 绘制篮板
        backboard = Rectangle(xy=(-30, -7.5), width=60, height=1,
                              linewidth=2, color='k', fill=False)
        axis.add_patch(backboard)

        # 绘制篮筐
        basket = Circle(xy=(0, 0), radius=7.5, linewidth=2, color='k', fill=False)
        axis.add_patch(basket)

        # 绘制限制区（restricted area）- 4英尺半径
        restricted = Arc(xy=(0, 0), width=80, height=80,  # 40*2=80 为直径
                         theta1=0, theta2=180,
                         linewidth=2, color='k', fill=False)
        axis.add_patch(restricted)

        # 绘制罚球圈 - 上半部分（实线）
        free_throw_circle_top = Arc(xy=(0, 142.5), width=120, height=120,
                                    theta1=0, theta2=180,
                                    linewidth=2, color='k')
        axis.add_patch(free_throw_circle_top)

        # 绘制罚球圈 - 下半部分（虚线）
        free_throw_circle_bottom = Arc(xy=(0, 142.5), width=120, height=120,
                                       theta1=180, theta2=360,
                                       linewidth=2, linestyle='--', color='k')
        axis.add_patch(free_throw_circle_bottom)

        # 绘制三分线
        three_left = Rectangle(xy=(-220, -47.5), width=0, height=140,
                               linewidth=2, color='k', fill=False)
        three_right = Rectangle(xy=(220, -47.5), width=0, height=140,
                                linewidth=2, color='k', fill=False)
        axis.add_patch(three_left)
        axis.add_patch(three_right)

        # 绘制三分弧线
        three_arc = Arc(xy=(0, 0), width=477.32, height=477.32,
                        theta1=22.8, theta2=157.2,
                        linewidth=2, color='k')
        axis.add_patch(three_arc)

        # 绘制中场圆圈
        center_outer_arc = Arc(xy=(0, 422.5), width=120, height=120,
                               theta1=180, theta2=0,
                               linewidth=2, color='k')
        center_inner_arc = Arc(xy=(0, 422.5), width=40, height=40,
                               theta1=180, theta2=0,
                               linewidth=2, color='k')
        axis.add_patch(center_outer_arc)
        axis.add_patch(center_inner_arc)

        # 设置坐标轴
        axis.set_xlim(-250, 250)
        axis.set_ylim(422.5, -47.5)
        axis.set_xticks([])
        axis.set_yticks([])

        return fig, axis


class GameChartsService:
    """NBA比赛数据可视化服务"""

    def __init__(self, game_data_service: GameDataProvider,
                 figure_path: Optional[Path] = None,):
        """初始化服务"""
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.figure_path = figure_path or NBAConfig.PATHS.PICTURES_DIR
        self.game_data_service = game_data_service

    def plot_player_scoring_impact(self,
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

            shots = game.get_shot_data(player_id)
            if not shots:
                self.logger.warning(f"未找到球员 {player_id} 的投篮数据")
                return None, shot_stats

            shot_stats = self._calculate_shot_stats(shots)

            # 创建图表
            fig, ax = CourtRenderer.draw_court()

            # 绘制投篮点
            for shot in shots:
                # 获取并验证坐标
                x = shot.get('xLegacy')
                y = shot.get('yLegacy')
                made = shot.get('shotResult') == 'Made'

                if x is None or y is None:
                    self.logger.warning(f"Invalid shot coordinates: x={x}, y={y}")
                    continue

                if x is not None and y is not None:

                    x = float(x)
                    y = float(y)


                    # 使用更美观的样式
                    if made:
                        ax.scatter(x, y,
                                   marker='o',
                                   edgecolors='#3A7711',  # 深绿色边框
                                   facecolors='#F0F0F0',  # 浅灰色填充
                                   s=30,  # 点的大小
                                   linewidths=2,
                                   zorder=2)
                    else:
                        ax.scatter(x, y,
                                   marker='x',
                                   color='#A82B2B',  # 暗红色
                                   s=30,
                                   zorder=2)

            if title:
                ax.set_title(title, pad=20)

            if output_path:
                self._save_figure(fig, output_path)

            return fig, shot_stats

        except Exception as e:
            self.logger.error(f"绘制投篮图时出错: {str(e)}", exc_info=True)
            return None, shot_stats

    def _calculate_shot_stats(self, shots: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算投篮统计信息"""
        stats = {
            'total': 0,
            'made': 0,
            'assisted': 0,
            'unassisted': 0,
            'fg_pct': 0.0,
            'assisted_pct': 0.0
        }

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


    def _save_figure(self, fig: plt.Figure, output_path: str, dpi: int = 300) -> None:
        """保存图表到文件"""
        try:
            output_path = self.figure_path / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_path, bbox_inches='tight', dpi=dpi, pad_inches=0.1)
            plt.close(fig)
            self.logger.info(f"图表已保存至 {output_path}")
        except Exception as e:
            self.logger.error(f"保存图表时出错: {e}")
            raise e

