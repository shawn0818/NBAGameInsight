from dataclasses import dataclass, field

from config.nba_config import NBAConfig
from nba.models.game_model import Game
from nba.services.game_data_service import GameDataProvider
from utils.logger_handler import AppLogger

from typing import Optional, Dict, Any, Tuple, Union
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle, Circle, Arc
from PIL import Image, ImageDraw
import requests
from io import BytesIO
from pathlib import Path

@dataclass
class ChartConfig:
    """图表服务配置"""
    dpi: int = 300  # 图表DPI
    scale_factor: float = 2.0  # 图表缩放比例
    figure_path: Optional[Path] = field(default_factory=lambda: NBAConfig.PATHS.PICTURES_DIR)   # 图表保存路径


    def __post_init__(self):
        """配置验证与初始化"""
        if self.dpi < 72 or self.dpi > 600:
            raise ValueError("DPI must be between 72 and 600")
        if self.scale_factor < 0.5 or self.scale_factor > 5.0:
            raise ValueError("Scale factor must be between 0.5 and 5.0")



class CourtRenderer:
    """NBA半场球场渲染器"""

    @staticmethod
    def draw_court(config: ChartConfig):
        """
        Draw an NBA halfcourt with basket at the bottom
        Args:
            - config: 图表配置对象
        Returns:
            - fig: matplotlib figure object
            - axis: matplotlib axis object
        """
        base_width, base_height = 9, 9
        scaled_width = base_width * config.scale_factor
        scaled_height = base_height * config.scale_factor

        fig = plt.figure(figsize=(scaled_width, scaled_height), dpi=config.dpi)
        axis = fig.add_subplot(111)

        line_width = 2 * config.scale_factor

        # 设置球场底色
        court_shape = Rectangle(xy=(-250, -47.5), width=500, height=470,
                                linewidth=line_width, edgecolor='#F0F0F0', fill=True)
        court_shape.set_zorder(0)
        axis.add_patch(court_shape)

        # 绘制球场外框
        outer_lines = Rectangle(xy=(-250, -47.5), width=500, height=470,
                                linewidth=line_width, edgecolor='k', fill=False)
        axis.add_patch(outer_lines)

        # 绘制禁区并填充颜色
        paint = Rectangle(xy=(-80, -47.5), width=160, height=190,
                          linewidth=line_width, edgecolor='k', fill=True,
                          facecolor='#B0C4DE', alpha=0.3)  # 使用淡蓝色填充
        axis.add_patch(paint)

        # 绘制禁区内框
        inner_paint = Rectangle(xy=(-60, -47.5), width=120, height=190,
                                linewidth=line_width, edgecolor='k', fill=False)
        axis.add_patch(inner_paint)

        # 绘制篮板
        backboard = Rectangle(xy=(-30, -7.5), width=60, height=1,
                              linewidth=line_width, edgecolor='k', fill=False)
        axis.add_patch(backboard)

        # 绘制篮筐
        basket = Circle(xy=(0, 0), radius=7.5, linewidth=line_width, color='k', fill=False)
        axis.add_patch(basket)

        # 绘制限制区（restricted area）- 4英尺半径
        restricted = Arc(xy=(0, 0), width=80, height=80,  # 40*2=80 为直径
                         theta1=0, theta2=180,
                         linewidth=line_width, color='k', fill=False)
        axis.add_patch(restricted)

        # 绘制罚球圈 - 上半部分（实线）
        free_throw_circle_top = Arc(xy=(0, 142.5), width=120, height=120,
                                    theta1=0, theta2=180,
                                    linewidth=line_width, color='k')
        axis.add_patch(free_throw_circle_top)

        # 绘制罚球圈 - 下半部分（虚线）
        free_throw_circle_bottom = Arc(xy=(0, 142.5), width=120, height=120,
                                       theta1=180, theta2=360,
                                       linewidth=line_width, linestyle='--', color='k')
        axis.add_patch(free_throw_circle_bottom)

        # 绘制三分线
        three_left = Rectangle(xy=(-220, -47.5), width=0, height=140,
                               linewidth=line_width, edgecolor='k', fill=False)
        three_right = Rectangle(xy=(220, -47.5), width=0, height=140,
                                linewidth=line_width, edgecolor='k', fill=False)
        axis.add_patch(three_left)
        axis.add_patch(three_right)

        # 绘制三分弧线
        three_arc = Arc(xy=(0, 0), width=477.32, height=477.32,
                        theta1=22.8, theta2=157.2,
                        linewidth=line_width, color='k')
        axis.add_patch(three_arc)

        # 绘制中场圆圈
        center_outer_arc = Arc(xy=(0, 422.5), width=120, height=120,
                               theta1=180, theta2=0,
                               linewidth=line_width, color='k')
        center_inner_arc = Arc(xy=(0, 422.5), width=40, height=40,
                               theta1=180, theta2=0,
                               linewidth=line_width, color='k')
        axis.add_patch(center_outer_arc)
        axis.add_patch(center_inner_arc)

        # 设置坐标轴
        axis.set_xlim(-250, 250)
        axis.set_ylim(422.5, -47.5)
        axis.set_xticks([])
        axis.set_yticks([])

        return fig, axis

    @staticmethod
    def get_player_headshot_url(player_id: int, small: bool = False) -> str:
        """获取NBA官方球员头像URL

        Args:
            player_id: 球员ID
            small: 是否使用小尺寸图片（用于投篮点标记）
        """
        if small:
            return f"https://cdn.nba.com/headshots/nba/latest/260x190/{player_id}.png"
        return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png"

    @staticmethod
    def add_player_portrait(axis: Axes, player_id: int, position=(0.9995, 0.002), size=0.2) -> None:
        """在球场图右下角添加球员头像，贴合框线内侧

        Args:
            axis: matplotlib坐标轴对象
            player_id: 球员ID
            position: 头像位置，默认为(0.9995, 0.002)表示紧贴框线内侧
            size: 头像大小，相对于图像大小的比例
        """
        try:
            image_url = CourtRenderer.get_player_headshot_url(player_id)
            response = requests.get(image_url)
            img = Image.open(BytesIO(response.content))

            # 计算裁剪边界，确保完整显示
            width, height = img.size
            if width > height:
                left = (width - height) // 2
                img = img.crop((left, 0, left + height, height))
            else:
                top = (height - width) // 2
                img = img.crop((0, top, width, top + width))

            # 创建子图，紧贴框线内侧
            portrait_ax = axis.inset_axes(
                (position[0] - size, position[1], size, size),
                transform=axis.transAxes
            )
            portrait_ax.imshow(img)
            portrait_ax.axis('off')

        except Exception as e:
            print(f"添加球员头像时出错: {str(e)}")


class GameChartsService:
    """NBA比赛数据可视化服务"""

    def __init__(self, game_data_service: GameDataProvider,
                 config: Optional[ChartConfig] = None):
        """初始化服务"""
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.game_data_service = game_data_service
        self.config = config or ChartConfig()

    def plot_player_scoring_impact(self,
                                   game: Game,
                                   player_id: Optional[int] = None,
                                   title: Optional[str] = None,
                                   output_path: Optional[Union[str, Path]] = None ,
                                  ) -> Tuple[Optional[plt.Figure], Dict[str, Any]]:
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



            # 创建图表
            fig, ax = CourtRenderer.draw_court(self.config)

            # 绘制投篮点
            for shot in shots:
                x = shot.get('x_legacy')
                y = shot.get('y_legacy')
                made = shot.get('shot_result') == 'Made'

                if x is None or y is None:
                    self.logger.warning(f"Invalid shot coordinates: x={x}, y={y}")
                    continue

                if x is not None and y is not None:
                    x = float(x)
                    y = float(y)

                    if made:
                        ax.scatter(x, y,
                                   marker='o',
                                   edgecolors='#3A7711',  # 深绿色边框
                                   facecolors='#F0F0F0',  # 浅灰色填充
                                   s=30 * self.config.scale_factor,  # 点的大小随比例放大
                                   linewidths=2 * self.config.scale_factor,
                                   zorder=2)
                    else:
                        ax.scatter(x, y,
                                   marker='x',
                                   color='#A82B2B',  # 暗红色
                                   s=30 * self.config.scale_factor,
                                   linewidths=2 * self.config.scale_factor,
                                   zorder=2)

            if title:
                ax.set_title(title, pad=20, fontsize=12 * self.config.scale_factor)

            # 添加球员头像
            if player_id:
                CourtRenderer.add_player_portrait(ax, player_id)

            if output_path:
                self._save_figure(fig, output_path)

            return fig, shot_stats

        except Exception as e:
            self.logger.error(f"绘制投篮图时出错: {str(e)}", exc_info=True)
            return None, shot_stats

    def _save_figure(self, fig: plt.Figure, output_path: str) -> None:
        """保存图表到文件

        Args:
            fig: matplotlib图表对象
            output_path: 输出路径
        """
        try:
            output_path = self.config.figure_path / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(
                output_path,
                bbox_inches='tight',
                dpi=self.config.dpi, #  从 self.config.dpi 获取 dpi
                pad_inches=0.1
            )
            plt.close(fig)
            self.logger.info(f"图表已保存至 {output_path}")
        except Exception as e:
            self.logger.error(f"保存图表时出错: {e}")
            raise e

    def plot_team_shots(self,
                        game: Game,
                        team_id: int,
                        title: Optional[str] = None,
                        output_path: Optional[str] = None,
                        ) -> Optional[plt.Figure]:
        """绘制球队所有球员的投篮图"""
        try:
            self.logger.info(f"开始绘制球队 {team_id} 的投篮图")

            fig, ax = CourtRenderer.draw_court(self.config)

            team_shots = game.get_team_shot_data(team_id)
            self.logger.info(f"获取到 {len(team_shots)} 个球员的投篮数据")

            base_marker_size = 0.02 * self.config.scale_factor

            for player_id, shots in team_shots.items():
                self.logger.info(f"处理球员 {player_id} 的投篮数据，共 {len(shots)} 个投篮点")
                for shot in shots:
                    x = shot.get('x_legacy')
                    y = shot.get('y_legacy')
                    made = shot.get('shot_result') == 'Made'

                    # 只处理投进的球
                    if x is not None and y is not None and made:
                        self.logger.info(f"绘制投篮点: x={x}, y={y}, made={made}")
                        self._add_shot_marker_with_portrait(
                            ax, x, y, player_id,
                            marker_size=base_marker_size,
                            alpha=1.0  # 投进的球都用完全不透明
                        )

            if title:
                ax.set_title(title, pad=20, fontsize=12 * self.config.scale_factor)

            if output_path:
                plt.savefig(output_path, dpi=self.config.dpi, bbox_inches='tight')
                plt.close(fig)
                self.logger.info(f"图表已保存到: {output_path}")

            return fig

        except Exception as e:
            self.logger.error(f"绘制团队投篮图时出错: {str(e)}", exc_info=True)
            return None

    def _add_shot_marker_with_portrait(self, axis: Axes, x: float, y: float,
                                       player_id: int, marker_size: float = 0.02,
                                       alpha: float = 1.0) -> None:
        """添加带有球员头像的投篮标记"""
        try:
            # 使用小尺寸头像
            image_url = CourtRenderer.get_player_headshot_url(player_id, small=True)
            response = requests.get(image_url)
            img = Image.open(BytesIO(response.content))

            size_px = int(min(img.size))
            img = img.resize((size_px, size_px), Image.Resampling.LANCZOS)

            # 创建高分辨率的圆形mask
            mask_size = size_px * 4  # 增加mask的分辨率
            mask = Image.new('L', (mask_size, mask_size), 0)
            draw = ImageDraw.Draw(mask)

            # 使用更高分辨率的圆形
            draw.ellipse((0, 0, mask_size - 1, mask_size - 1), fill=255)

            # 将mask缩放回原始大小，这样可以得到更平滑的圆形
            mask = mask.resize((size_px, size_px), Image.Resampling.LANCZOS)

            output = Image.new('RGBA', (size_px, size_px), (0, 0, 0, 0))
            output.paste(img, mask=mask)

            # 计算标记大小（从数据坐标）
            marker_data_size = marker_size * 500  # 使用球场宽度(500)作为参考

            marker_ax = axis.inset_axes(
                (x - marker_data_size / 2, y - marker_data_size / 2,
                 marker_data_size, marker_data_size),
                transform=axis.transData
            )
            marker_ax.imshow(output, alpha=alpha)

            # 添加细绿色圆形边框，使用更小的linewidth
            circle = plt.Circle((size_px / 2, size_px / 2), size_px / 2 - 0.5,  # 稍微减小半径以确保边框完全可见
                                fill=False,
                                color='#3A7711',  # 使用深绿色
                                linewidth=0.5,  # 更细的线条
                                transform=marker_ax.transData,
                                antialiased=True)  # 开启抗锯齿
            marker_ax.add_patch(circle)

            marker_ax.axis('off')

        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"添加投篮标记时出错: {str(e)}")
            else:
                print(f"添加投篮标记时出错: {str(e)}")