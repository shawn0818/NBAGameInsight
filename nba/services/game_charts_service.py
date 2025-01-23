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
    """
    标准NBA半场尺寸 (单位: 像素).
    根据NBA官网的SVG球场图，设置了一些标准尺寸，以便在图表中绘制球场。
    宽度和长度的比例与实际 NBA 半场球场 (50英尺 x 47英尺) 比例接近。
    """
    width: float = 540.0  #  viewBox 宽度
    length: float = 470.0 #  viewBox 高度 (半场长度方向)

    # 油漆区 (Paint Area)
    paint_outer_width: float = 160.0
    paint_inner_width: float = 120.0
    paint_height: float = 190.0

    # 三分线 (Three-Point Line)
    three_point_sideline: float = 140.0 # 底角三分线长度
    three_point_radius: float = 237.5  # 弧顶三分线半径 (近似值，SVG中为 475/2)

    # 罚球线和罚球圈 (Free Throw)
    free_throw_circle_radius: float = 60.0 # 罚球圈半径 (SVG中为 120/2)
    free_throw_line_dist: float = 150.0   # 罚球线到篮筐的距离 (近似值)

    # 禁区 (Restricted Area)
    restricted_area_radius: float = 40.0 # 禁区弧半径 (SVG中为 80/2)

    # 中圈 (Center Circle) - 半场只有一个中圈，这里定义半径仅为绘图方便
    center_circle_radius: float = 40.0 # 中圈半径 (SVG中内圈为 40/2, 外圈 120/2，这里取内圈半径)

    # 篮板和篮筐 (Backboard and Rim)
    backboard_width: float = 60.0  # 篮板宽度 (SVG中为 60)
    backboard_pad: float = 30.0    # 篮板离底线的距离 (SVG中为 -7.5 * -4 = 30，因为SVG坐标向下为正)
    rim_radius: float = 7.5       # 篮筐半径 (SVG中为 7.5)


@dataclass
class ChartStyleConfig:
    """图表样式配置类"""
    court_line_color: str = '#1d2266'  # 球场线条颜色 (深蓝色)
    court_line_width: float = 2.0      # 球场线条宽度
    made_shot_color: str = 'blue'      # 命中投篮颜色 (蓝色)
    missed_shot_color: str = 'red'     # 未命中投篮颜色 (红色)
    assisted_shot_color: str = 'green' # 助攻投篮颜色 (绿色)
    made_shot_marker: str = 'o'        # 命中投篮标记 (圆圈)
    missed_shot_marker: str = 'x'       # 未命中投篮标记 (叉号)
    assisted_shot_marker: str = '*'     # 助攻投篮标记 (星号)
    shot_marker_size: int = 100         # 投篮点标记大小
    assisted_shot_marker_size: int = 200 # 助攻投篮点标记大小
    zone_fill_alpha: float = 0.2        # 区域填充透明度
    restricted_area_color: str = '#FF0000' # 禁区颜色 (红色)
    paint_area_color: str = '#00FF00'      # 油漆区颜色 (绿色)
    mid_range_area_color: str = '#0000FF'  # 中距离区域颜色 (蓝色)
    corner_three_area_color: str = '#FFFF00' # 底角三分区域颜色 (黄色)
    above_break_three_area_color: str = '#FF00FF' # 弧顶三分区域颜色 (品红色)


class CourtRenderer:
    """
    NBA半场球场渲染器.

    使用 matplotlib 绘制 NBA 半场球场，坐标系统原点为球场中心 (篮筐位置)，
    X轴水平方向 (宽度方向)，正方向为右侧半场，负方向为左侧半场。
    Y轴垂直方向 (长度方向)，**正方向为靠近篮筐方向 (图表上方)**，**负方向为远离篮筐方向 (图表下方)**。
    单位为 `CourtDimensions` 中定义的像素单位。

    **重要说明：** 在生成的图表中，**篮筐位于图的上方**，半场的另一端位于图的下方。
    """
    def __init__(self, ax, style_config: Optional[ChartStyleConfig] = None):
        """
        初始化 CourtRenderer.

        Args:
            ax (matplotlib.axes.Axes): matplotlib 的 Axes 对象，用于绘图.
            style_config (Optional[ChartStyleConfig]): 图表样式配置对象，默认为 None，使用默认样式.
        """
        self.ax = ax
        self.style_config = style_config or ChartStyleConfig() # 使用配置的样式或默认样式
        self.dims = CourtDimensions()


    def draw_court(self, draw_zones=True):
        """
        绘制 NBA 半场球场.

        Args:
            draw_zones (bool): 是否绘制投篮区域，默认为 True.
        Returns:
            matplotlib.axes.Axes: 绘制完成的 Axes 对象.
        """
        if draw_zones:
            self._draw_zones() # 绘制投篮区域
        self._draw_court_lines() # 绘制球场线条
        self._setup_axes()      # 设置坐标轴
        return self.ax

    def _draw_zones(self):
        """绘制投篮区域 (禁区, 油漆区, 中距离, 底角三分, 弧顶三分)."""
        zone_colors = {
            'restricted_area': {'fill': self.style_config.restricted_area_color, 'alpha': self.style_config.zone_fill_alpha},
            'paint': {'fill': self.style_config.paint_area_color, 'alpha': self.style_config.zone_fill_alpha},
            'mid_range': {'fill': self.style_config.mid_range_area_color, 'alpha': self.style_config.zone_fill_alpha},
            'corner_three': {'fill': self.style_config.corner_three_area_color, 'alpha': self.style_config.zone_fill_alpha},
            'above_break_three': {'fill': self.style_config.above_break_three_area_color, 'alpha': self.style_config.zone_fill_alpha}
        }

        # 禁区 (Restricted Area)
        self.ax.add_patch(Arc((0, 0), # 圆心在原点 (篮筐)
                              self.dims.restricted_area_radius * 2, # 宽度为直径
                              self.dims.restricted_area_radius * 2, # 高度为直径
                              theta1=0, theta2=180, # 绘制上半圆
                              fc=zone_colors['restricted_area']['fill'], # 填充颜色
                              alpha=zone_colors['restricted_area']['alpha'])) # 透明度

        # 油漆区 (Paint Area, 不含禁区)
        self.ax.add_patch(Rectangle( # 矩形
            (-self.dims.paint_outer_width / 2, 0), # 左下角坐标 (X中心偏移, Y=0 基线)
            self.dims.paint_outer_width,          # 宽度
            self.dims.paint_height,             # 高度
            fc=zone_colors['paint']['fill'],      # 填充颜色
            alpha=zone_colors['paint']['alpha'])) # 透明度


        # 中距离区域 (Mid-Range Area)
        # 使用 Path 绘制不规则四边形区域
        from matplotlib.path import Path as mplPath
        mid_range_path_data = [
            (-250, 0), # 左侧底线端点
            (-250, self.dims.three_point_sideline), # 左侧三分线底角
            (-self.dims.paint_outer_width / 2, self.dims.paint_height), # 油漆区左上角
            (self.dims.paint_outer_width / 2, self.dims.paint_height),  # 油漆区右上角
            (250, self.dims.three_point_sideline),  # 右侧三分线底角
            (250, 0), # 右侧底线端点
            (0,0) # Close path
        ]
        mid_range_path_codes = [
            mplPath.MOVETO,
            mplPath.LINETO,
            mplPath.LINETO,
            mplPath.LINETO,
            mplPath.LINETO,
            mplPath.LINETO,
            mplPath.CLOSEPOLY,
        ]
        mid_range_path = mplPath(mid_range_path_data, mid_range_path_codes)
        self.ax.add_patch(plt.matplotlib.patches.PathPatch(mid_range_path,
                              fc=zone_colors['mid_range']['fill'],
                              alpha=zone_colors['mid_range']['alpha']))


        # 底角三分区域 (Corner Three Area)
        for x_sign in [-1, 1]: # 左右两侧对称绘制
            x_base = x_sign * 250 # 底线 X 坐标 (-250 或 250)
            rect_x = x_base # 矩形左侧 X 坐标
            if x_sign > 0:
                rect_x = x_base - (x_base - self.dims.three_point_radius) # 调整右侧矩形起始 X 坐标

            self.ax.add_patch(Rectangle( # 矩形
                (rect_x, 0), # 左下角坐标
                abs(x_base) - self.dims.three_point_radius, # 宽度 (底线到三分线底角的距离)
                self.dims.three_point_sideline, # 高度 (三分线底角到边线的距离)
                fc=zone_colors['corner_three']['fill'], # 填充颜色
                alpha=zone_colors['corner_three']['alpha'] # 透明度
            ))

        # 弧顶三分区域 (Above the Break Three Area)
        self.ax.add_patch(Arc( # 弧形
            (0, 0), # 圆心在原点 (篮筐)
            self.dims.three_point_radius * 2, # 宽度为直径
            self.dims.three_point_radius * 2, # 高度为直径
            theta1=0, theta2=180, # 绘制上半圆
            fc=zone_colors['above_break_three']['fill'], # 填充颜色
            alpha=zone_colors['above_break_three']['alpha'] # 透明度
        ))

    def _draw_court_lines(self):
        """绘制球场线条 (边线, 三分线, 油漆区线, 罚球线, 篮筐, 篮板, 内部标记线)."""
        # 球场边线 (Court Boundary Lines)
        self.ax.add_patch(Rectangle( # 矩形
            (-self.dims.width / 2, 0), # 左下角坐标 (X中心偏移, Y=0 基线)
            self.dims.width,          # 宽度
            self.dims.length,         # 高度
            fill=False,               # 不填充
            color=self.style_config.court_line_color, # 线条颜色
            linewidth=self.style_config.court_line_width # 线条宽度
        ))

        # 三分线 (Three-Point Lines)
        for x_sign in [-1, 1]: # 左右两侧对称绘制
            x = x_sign * (self.dims.width / 2) # 边线 X 坐标 (-250 或 250)
            self.ax.add_line(mlines.Line2D( # 垂直线段
                [x, x], # X 坐标相同，垂直线
                [0, self.dims.three_point_sideline], # Y 坐标范围 (底线到三分线底角)
                color=self.style_config.court_line_color, # 线条颜色
                linewidth=self.style_config.court_line_width # 线条宽度
            ))
        self.ax.add_patch(Arc( # 弧形
            (0, 0), # 圆心在原点 (篮筐)
            self.dims.three_point_radius * 2, # 宽度为直径 (SVG中为 475)
            self.dims.three_point_radius * 2, # 高度为直径 (SVG中为 475)
            theta1=22, theta2=158, # 弧形角度范围 (根据SVG代码调整)
            color=self.style_config.court_line_color, # 线条颜色
            linewidth=self.style_config.court_line_width # 线条宽度
        ))

        # 油漆区线 (Paint Area Lines)
        for width in [self.dims.paint_outer_width, self.dims.paint_inner_width]: # 绘制外油漆区和内油漆区
            self.ax.add_patch(Rectangle( # 矩形
                (-width / 2, 0), # 左下角坐标 (X中心偏移, Y=0 基线)
                width,             # 宽度
                self.dims.paint_height, # 高度
                color=self.style_config.court_line_color, # 线条颜色
                fill=False,          # 不填充
                linewidth=self.style_config.court_line_width # 线条宽度
            ))

        # 罚球圈 (Free Throw Circle)
        self.ax.add_patch(Arc( # 上半圆弧
            (0, self.dims.free_throw_line_dist), # 圆心坐标 (X=0 中心线, Y轴偏移)
            self.dims.free_throw_circle_radius * 2, # 宽度为直径 (SVG中为 120)
            self.dims.free_throw_circle_radius * 2, # 高度为直径 (SVG中为 120)
            theta1=0, theta2=180, # 绘制上半圆
            color=self.style_config.court_line_color, # 线条颜色
            linewidth=self.style_config.court_line_width # 线条宽度
        ))
        self.ax.add_patch(Arc( # 下半圆虚线弧
            (0, self.dims.free_throw_line_dist), # 圆心坐标 (同上)
            self.dims.free_throw_circle_radius * 2, # 宽度为直径 (同上)
            self.dims.free_throw_circle_radius * 2, # 高度为直径 (同上)
            theta1=180, theta2=360, # 绘制下半圆
            linestyle='--',          # 虚线
            color=self.style_config.court_line_color, # 线条颜色
            linewidth=self.style_config.court_line_width # 线条宽度
        ))

        # 篮筐 (Rim)
        self.ax.add_patch(Circle( # 圆形
            (0, 0), # 圆心在原点 (篮筐)
            self.dims.rim_radius, # 半径 (SVG中为 7.5)
            color=self.style_config.court_line_color, # 线条颜色
            fill=False,          # 不填充
            linewidth=self.style_config.court_line_width # 线条宽度
        ))
        # 篮板 (Backboard)
        self.ax.add_line(mlines.Line2D( # 水平线段
            [-self.dims.backboard_width / 2, self.dims.backboard_width / 2], # X 坐标范围 (篮板左右端点)
            [self.dims.backboard_pad, self.dims.backboard_pad], # Y 坐标相同 (篮板 Y 坐标)
            color=self.style_config.court_line_color, # 线条颜色
            linewidth=self.style_config.court_line_width # 线条宽度
        ))

        # 内部标记线 (Inner Markings)
        # 罚球线两侧的短横线，以及油漆区顶端附近的横线
        for y_offset in [69.8, 79.9, 109.9, 140]: # 不同的 Y 轴偏移量
            for x_offset in [-170, 340]: # 不同的 X 轴偏移量 (相对于中心线)
                self.ax.add_line(mlines.Line2D( # 水平短线段
                    [x_offset - 10, x_offset], # X 坐标范围 (短线段左右端点)
                    [y_offset, y_offset],      # Y 坐标相同 (水平线)
                    color=self.style_config.court_line_color, # 线条颜色
                    linewidth=self.style_config.court_line_width # 线条宽度
                ))

    def _setup_axes(self):
        """设置坐标轴范围和样式."""
        self.ax.set_xlim(-self.dims.width / 2 - 20, self.dims.width / 2 + 20) # X 轴范围，左右两侧留出一些空白
        # 修改 Y 轴范围和反转 Y 轴
        self.ax.set_ylim(self.dims.length + 20, -20)  # Y 轴范围反转，上限设为 length+20, 下限设为 -20
        self.ax.invert_yaxis() # 反转 Y 轴方向，正方向向下
        self.ax.set_aspect('equal') # 设置纵横比为 1:1
        self.ax.axis('off')         # 关闭坐标轴显示


class GameChartsService:
    """NBA比赛数据可视化服务"""

    def __init__(self, game_data_service: NBAGameDataProvider,
                 figure_path: Optional[Path] = None,
                 style_config: Optional[ChartStyleConfig] = None):
        """
        初始化 GameChartsService.

        Args:
            game_data_service (NBAGameDataProvider): NBA 比赛数据提供服务.
            figure_path (Optional[Path]): 图表保存路径，默认为 NBAConfig.PATHS.PICTURES_DIR.
            style_config (Optional[ChartStyleConfig]): 图表样式配置对象，默认为 None，使用默认样式.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.figure_path = figure_path or NBAConfig.PATHS.PICTURES_DIR
        self.game_data_service = game_data_service
        self.style_config = style_config or ChartStyleConfig() # 使用配置的样式或默认样式
        self._setup_style()

    def _setup_style(self) -> None:
        """设置matplotlib的基础样式 (例如字体)."""
        try:
            plt.style.use('fivethirtyeight') # 使用 fivethirtyeight 样式
            plt.rcParams['font.family'] = ['Microsoft YaHei', 'SimHei', 'sans-serif'] # 设置中文字体
        except Exception as e:
            self.logger.warning(f"设置样式失败，使用默认样式: {str(e)}")

    def plot_player_shots(self,
                          game: Game,
                          player_id: Optional[int] = None,
                          title: Optional[str] = None,
                          output_path: Optional[str] = None,
                          show_stats: bool = True) -> Tuple[Optional[plt.Figure], Dict[str, Any]]:
        """
        绘制球员投篮图.

        Args:
            game (Game): 比赛数据 Game 对象.
            player_id (Optional[int]): 球员 ID，如果为 None，则绘制所有球员投篮.
            title (Optional[str]): 图表标题，默认为 None.
            output_path (Optional[str]): 图表保存路径 (文件名)，默认为 None (不保存).
            show_stats (bool): 是否在图表中显示统计信息，默认为 True.

        Returns:
            Tuple[Optional[plt.Figure], Dict[str, Any]]: 包含 Figure 对象和投篮统计信息的字典.
                                                        如果绘制失败，Figure 对象为 None.
        """

        shot_stats = {'total': 0, 'made': 0, 'assisted': 0, 'unassisted': 0} # 初始化投篮统计信息

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
            fig, ax = plt.subplots(figsize=(12, 11)) # 创建 Figure 和 Axes 对象

            try:
                court_renderer = CourtRenderer(ax, style_config=self.style_config) # 创建 CourtRenderer, 传入样式配置
                court_renderer.draw_court() # 绘制球场
            except Exception as e:
                self.logger.error(f"绘制球场失败: {str(e)}")
                plt.close(fig) # 关闭 Figure
                return None, shot_stats

            # 绘制投篮点
            self._plot_shots(ax, shots) # 调用 _plot_shots 绘制投篮点

            # 添加图例和统计信息
            if show_stats:
                try:
                    self._add_shot_stats_text(ax, shot_stats) # 添加投篮统计信息文本
                except Exception as e:
                    self.logger.warning(f"添加统计信息失败: {str(e)}")

            try:
                self._add_shot_legend(ax) # 添加图例
            except Exception as e:
                self.logger.warning(f"添加图例失败: {str(e)}")

            if title:
                ax.set_title(title) # 设置图表标题

            # 保存图表
            if output_path:
                try:
                    self._save_figure(fig, output_path) # 保存图表到文件
                except Exception as e:
                    self.logger.error(f"保存图表失败: {str(e)}")

            return fig, shot_stats # 返回 Figure 对象和投篮统计信息

        except Exception as e:
            self.logger.error(f"绘制投篮图时出错: {str(e)}", exc_info=True)
            return None, shot_stats

    def plot_player_assists(self,
                            game: Game,
                            passer_id: int,
                            title: Optional[str] = None,
                            output_path: Optional[str] = None,
                            show_stats: bool = True) -> Tuple[Optional[plt.Figure], Dict[str, Any]]:
        """
        绘制球员助攻位置图.

        Args:
            game (Game): 比赛数据 Game 对象.
            passer_id (int): 助攻球员 ID.
            title (Optional[str]): 图表标题，默认为 None.
            output_path (Optional[str]): 图表保存路径 (文件名)，默认为 None (不保存).
            show_stats (bool): 是否在图表中显示统计信息，默认为 True.

        Returns:
            Tuple[Optional[plt.Figure], Dict[str, Any]]: 包含 Figure 对象和助攻统计信息的字典.
                                                        如果绘制失败，Figure 对象为 None.
        """
        assist_stats = { # 初始化助攻统计信息
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
            fig, ax = plt.subplots(figsize=(12, 11)) # 创建 Figure 和 Axes
            court_renderer = CourtRenderer(ax, style_config=self.style_config) # 创建 CourtRenderer, 传入样式配置
            court_renderer.draw_court() # 绘制球场

            # 计算统计信息并绘制位置点
            self._plot_assisted_shots(ax, assisted_shots, assist_stats) # 绘制助攻位置点

            if show_stats:
                self._add_assist_stats_text(ax, assist_stats) # 添加助攻统计信息文本

            if title:
                ax.set_title(title) # 设置图表标题

            if output_path:
                self._save_figure(fig, output_path) # 保存图表

            return fig, assist_stats # 返回 Figure 对象和助攻统计信息

        except Exception as e:
            self.logger.error(f"绘制助攻位置图时出错: {str(e)}", exc_info=True)
            return None, assist_stats

    def plot_player_scoring_impact(self,
                                   game: Game,
                                   player_id: int,
                                   title: Optional[str] = None,
                                   output_path: Optional[str] = None,
                                   show_stats: bool = True) -> Tuple[Optional[plt.Figure], Dict[str, Any]]:
        """
        绘制球员得分影响力图 (包含个人投篮和助攻位置).

        Args:
            game (Game): 比赛数据 Game 对象.
            player_id (int): 球员 ID.
            title (Optional[str]): 图表标题，默认为 None.
            output_path (Optional[str]): 图表保存路径 (文件名)，默认为 None (不保存).
            show_stats (bool): 是否在图表中显示统计信息，默认为 True.

        Returns:
            Tuple[Optional[plt.Figure], Dict[str, Any]]: 包含 Figure 对象和得分影响力统计信息的字典.
                                                        如果绘制失败，Figure 对象为 None.
        """
        stats = { # 初始化得分影响力统计信息
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
            fig, ax = plt.subplots(figsize=(12, 11)) # 创建 Figure 和 Axes
            court_renderer = CourtRenderer(ax, style_config=self.style_config) # 创建 CourtRenderer, 传入样式配置
            court_renderer.draw_court() # 绘制球场

            # 绘制个人投篮
            for shot in shots:
                x = shot.get('xLegacy') # 获取投篮 X 坐标 (Legacy 坐标系)
                y = shot.get('yLegacy') # 获取投篮 Y 坐标 (Legacy 坐标系)
                if x is None or y is None:
                    continue

                made = shot.get('shotResult') == 'Made' # 判断是否命中
                stats['shots']['total'] += 1 # 增加总投篮次数

                if made: # 如果命中
                    stats['shots']['made'] += 1 # 增加命中次数
                    stats['shots']['points'] += 3 if shot.get('actionType') == '3pt' else 2 # 增加得分 (2分或3分)
                    marker = self.style_config.made_shot_marker # 使用命中标记
                    color = self.style_config.made_shot_color   # 使用命中颜色
                    size = self.style_config.shot_marker_size    # 使用标记大小
                else: # 如果未命中
                    marker = self.style_config.missed_shot_marker # 使用未命中标记
                    color = self.style_config.missed_shot_color  # 使用未命中颜色
                    size = self.style_config.shot_marker_size   # 使用标记大小

                ax.scatter(x, y, c=color, marker=marker, s=size) # 绘制个人投篮点

            # 绘制助攻位置
            for shot in assisted_shots:
                x = shot.get('x') # 获取助攻投篮 X 坐标
                y = shot.get('y') # 获取助攻投篮 Y 坐标
                if x is None or y is None:
                    continue

                stats['assists']['total'] += 1 # 增加总助攻次数
                stats['assists']['assisted_players'].add(shot['shooter_name']) # 记录被助攻球员姓名

                points = 3 if shot['shot_type'] == '3pt' else 2 # 判断助攻的是2分球还是3分球
                stats['assists']['points_created'] += points # 增加创造得分

                # 使用星号标记助攻位置,颜色区分二分和三分
                color = self.style_config.assisted_shot_color # 使用助攻颜色
                marker = self.style_config.assisted_shot_marker # 使用助攻标记
                size = self.style_config.assisted_shot_marker_size # 使用助攻标记大小
                ax.scatter(x, y, c=color, marker=marker, s=size) # 绘制助攻位置点

                # 添加被助攻球员标注
                ax.annotate(shot['shooter_name'], # 标注文本为被助攻球员姓名
                            (x, y),              # 标注位置为助攻点坐标
                            xytext=(5, 5),       # 文本偏移量
                            textcoords='offset points', # 文本偏移坐标系
                            fontsize=8)          # 字体大小

            # 添加图例
            legend_elements = [ # 创建图例元素列表
                mlines.Line2D([], [], marker=self.style_config.made_shot_marker, color='w', markerfacecolor=self.style_config.made_shot_color,
                              markersize=10, label='个人命中'), # 个人命中图例
                mlines.Line2D([], [], marker=self.style_config.missed_shot_marker, color='w', markerfacecolor=self.style_config.missed_shot_color,
                              markersize=10, label='个人未命中'), # 个人未命中图例
                mlines.Line2D([], [], marker=self.style_config.assisted_shot_marker, color='w', markerfacecolor=self.style_config.assisted_shot_color,
                              markersize=15, label='助攻得分') # 助攻得分图例
            ]

            ax.legend(handles=legend_elements, loc='upper right') # 添加图例到图表右上角

            if show_stats: # 如果需要显示统计信息
                # 计算总得分影响力
                total_impact = stats['shots']['points'] + stats['assists']['points_created'] # 总得分影响力 = 个人得分 + 助攻创造得分
                stats_text = ( # 统计信息文本
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
                ax.text(0.05, 0.95, stats_text, # 在图表左上角添加统计信息文本
                        transform=ax.transAxes, # 文本坐标系为 Axes 坐标系
                        bbox=dict(facecolor='white', alpha=0.8), # 文本框样式
                        fontsize=10,           # 字体大小
                        verticalalignment='top') # 垂直对齐方式

            if title:
                ax.set_title(title) # 设置图表标题

            if output_path:
                self._save_figure(fig, output_path) # 保存图表

            return fig, stats # 返回 Figure 对象和得分影响力统计信息

        except Exception as e:
            self.logger.error(f"绘制得分影响力图时出错: {str(e)}", exc_info=True)
            return None, stats

    def _calculate_shot_stats(self, shots: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算投篮统计信息."""
        stats = {'total': 0, 'made': 0, 'assisted': 0, 'unassisted': 0} # 初始化统计信息

        for shot in shots: # 遍历投篮数据
            stats['total'] += 1 # 增加总投篮次数
            if shot.get('shotResult') == 'Made': # 如果命中
                stats['made'] += 1 # 增加命中次数
                if shot.get('assisted'): # 如果是助攻
                    stats['assisted'] += 1 # 增加助攻命中次数
                else: # 如果不是助攻
                    stats['unassisted'] += 1 # 增加无助攻命中次数

        if stats['total'] > 0: # 如果有投篮数据
            stats['fg_pct'] = stats['made'] / stats['total'] * 100 # 计算投篮命中率
            if stats['made'] > 0: # 如果有命中投篮
                stats['assisted_pct'] = stats['assisted'] / stats['made'] * 100 # 计算助攻命中占比

        return stats # 返回统计信息字典

    def _plot_shots(self, ax: plt.Axes, shots: List[Dict[str, Any]]) -> None:
        """绘制投篮点."""
        for shot in shots: # 遍历投篮数据
            x = shot.get('xLegacy') # 获取投篮 X 坐标 (Legacy 坐标系)
            y = shot.get('yLegacy') # 获取投篮 Y 坐标 (Legacy 坐标系)
            if x is None or y is None:
                continue

            made = shot.get('shotResult') == 'Made' # 判断是否命中
            assisted = shot.get('assisted', False) # 判断是否助攻

            # 根据投篮结果和是否被助攻选择不同的标记样式
            if made: # 如果命中
                if assisted: # 如果是助攻
                    marker = self.style_config.assisted_shot_marker # 使用助攻标记
                    color = self.style_config.assisted_shot_color   # 使用助攻颜色
                    size = self.style_config.assisted_shot_marker_size # 使用助攻标记大小
                else: # 如果不是助攻
                    marker = self.style_config.made_shot_marker     # 使用命中标记
                    color = self.style_config.made_shot_color       # 使用命中颜色
                    size = self.style_config.shot_marker_size        # 使用标记大小
            else: # 如果未命中
                marker = self.style_config.missed_shot_marker   # 使用未命中标记
                color = self.style_config.missed_shot_color     # 使用未命中颜色
                size = self.style_config.shot_marker_size      # 使用标记大小

            ax.scatter(x, y, c=color, marker=marker, s=size) # 绘制投篮点

    def _plot_assisted_shots(self, ax: plt.Axes,
                             shots: List[Dict[str, Any]],
                             stats: Dict[str, Any]) -> None:
        """绘制助攻位置点."""
        for shot in shots: # 遍历助攻投篮数据
            x = shot.get('x') # 获取助攻投篮 X 坐标
            y = shot.get('y') # 获取助攻投篮 Y 坐标
            if x is None or y is None:
                continue

            # 更新统计信息
            stats['total_assists'] += 1 # 增加总助攻数
            stats['assisted_players'].add(shot['shooter_name']) # 记录被助攻球员姓名
            if shot['shot_type'] == '3pt': # 如果是三分球
                stats['threes_assisted'] += 1 # 增加助攻三分球数
                stats['points_created'] += 3 # 增加创造得分 (3分)
                color = self.style_config.assisted_shot_color # 使用助攻颜色 (这里颜色可以根据需求调整)
            else: # 如果是二分球
                stats['twos_assisted'] += 1 # 增加助攻二分球数
                stats['points_created'] += 2 # 增加创造得分 (2分)
                color = self.style_config.assisted_shot_color # 使用助攻颜色 (这里颜色可以根据需求调整)

            # 绘制位置点
            ax.scatter(x, y, c=color, marker=self.style_config.assisted_shot_marker, s=self.style_config.assisted_shot_marker_size) # 绘制助攻位置点

            # 添加投篮者姓名标注
            ax.annotate(shot['shooter_name'], # 标注文本为被助攻球员姓名
                        (x, y),              # 标注位置为助攻点坐标
                        xytext=(5, 5),       # 文本偏移量
                        textcoords='offset points', # 文本偏移坐标系
                        fontsize=8)          # 字体大小

    def _add_shot_stats_text(self, ax: plt.Axes, stats: Dict[str, Any]) -> None:
        """添加投篮统计信息文本到图表."""
        stats_text = ( # 统计信息文本
            f"总投篮: {stats['total']}\n"
            f"命中: {stats['made']} ({stats.get('fg_pct', 0):.1f}%)\n"
            f"助攻命中: {stats['assisted']}\n"
            f"无助攻命中: {stats['unassisted']}"
        )
        ax.text(0.05, 0.95, stats_text, # 在图表左上角添加文本
                transform=ax.transAxes, # 文本坐标系为 Axes 坐标系
                bbox=dict(facecolor='white', alpha=0.8), # 文本框样式
                fontsize=10,           # 字体大小
                verticalalignment='top') # 垂直对齐方式

    def _add_assist_stats_text(self, ax: plt.Axes, stats: Dict[str, Any]) -> None:
        """添加助攻统计信息文本到图表."""
        stats_text = ( # 助攻统计信息文本
            f"总助攻数: {stats['total_assists']}\n"
            f"助攻二分球: {stats['twos_assisted']}\n"
            f"助攻三分球: {stats['threes_assisted']}\n"
            f"创造得分: {stats['points_created']}\n"
            f"助攻队友数: {len(stats['assisted_players'])}"
        )
        ax.text(0.05, 0.95, stats_text, # 在图表左上角添加文本
                transform=ax.transAxes, # 文本坐标系为 Axes 坐标系
                bbox=dict(facecolor='white', alpha=0.8), # 文本框样式
                fontsize=10,           # 字体大小
                verticalalignment='top') # 垂直对齐方式

    def _add_shot_legend(self, ax: plt.Axes) -> None:
        """添加投篮图例到图表."""
        legend_elements = [ # 图例元素列表
            plt.Line2D([0], [0], marker=self.style_config.assisted_shot_marker, color='w', markerfacecolor=self.style_config.assisted_shot_color,
                       markersize=15, label='助攻命中'), # 助攻命中图例
            plt.Line2D([0], [0], marker=self.style_config.made_shot_marker, color='w', markerfacecolor=self.style_config.made_shot_color,
                       markersize=10, label='个人命中'), # 个人命中图例
            plt.Line2D([0], [0], marker=self.style_config.missed_shot_marker, color='w', markerfacecolor=self.style_config.missed_shot_color,
                       markersize=10, label='未命中') # 未命中图例
        ]
        ax.legend(handles=legend_elements, loc='upper right') # 添加图例到图表右上角

    def _save_figure(self, fig: plt.Figure, output_path: str, dpi: int = 300) -> None:
        """保存图表到文件."""
        try:
            output_path = self.figure_path / output_path # 拼接完整输出路径
            output_path.parent.mkdir(parents=True, exist_ok=True) # 创建父目录，如果不存在
            fig.savefig(output_path, bbox_inches='tight', dpi=dpi) # 保存图表，去除空白边距，设置 DPI
            plt.close(fig) # 关闭 Figure 对象，释放内存
            self.logger.info(f"图表已保存至 {output_path}") # 记录日志
        except Exception as e:
            self.logger.error(f"保存图表时出错: {e}") # 记录错误日志