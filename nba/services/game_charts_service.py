from dataclasses import dataclass, field

import numpy as np
from scipy.stats import gaussian_kde

from config.nba_config import NBAConfig
from nba.services.game_data_service import GameDataProvider
from utils.logger_handler import AppLogger
import time
from typing import Optional, Dict, Any, Tuple, Union, List
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle, Circle, Arc
from PIL import Image, ImageDraw, ImageEnhance
import requests
from io import BytesIO
from pathlib import Path


@dataclass
class ChartConfig:
    """图表服务配置"""
    dpi: int = 350  # 图表DPI
    scale_factor: float = 1.5  # 图表缩放比例
    figure_path: Optional[Path] = field(default_factory=lambda: NBAConfig.PATHS.PICTURES_DIR)  # 图表保存路径
    cache_duration: int = 24 * 60 * 60  # 缓存有效期（秒），默认24小时
    portrait_size: float = 0.015  # 减小默认头像大小
    marker_border_color: str = '#3A7711'  # 头像边框颜色
    marker_border_width: float = 0.5  # 头像边框宽度
    portrait_scale_factor: float = 2.5  # 添加全局头像尺寸放大倍数

    def __post_init__(self):
        """配置验证与初始化"""
        if self.dpi < 72 or self.dpi > 600:
            raise ValueError("DPI must be between 72 and 600")
        if self.scale_factor < 0.5 or self.scale_factor > 5.0:
            raise ValueError("Scale factor must be between 0.5 and 5.0")
        if self.portrait_scale_factor < 0.5 or self.portrait_scale_factor > 10.0:
            raise ValueError("Portrait scale factor must be between 0.5 and 10.0")

        # 简化的中文字体设置
        plt.rcParams['font.sans-serif'] = ['SimHei']  # 使用黑体
        plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题


class ImageCache:
    """图片缓存管理器"""

    def __init__(self, cache_duration: int = 24 * 60 * 60):
        self.cache: Dict[str, Tuple[bytes, float]] = {}
        self.cache_duration = cache_duration

    def get(self, key: str) -> Optional[bytes]:
        """获取缓存的图片"""
        if key in self.cache:
            image_data, timestamp = self.cache[key]
            if time.time() - timestamp < self.cache_duration:
                return image_data
            else:
                del self.cache[key]
        return None

    def set(self, key: str, image_data: bytes):
        """设置缓存"""
        self.cache[key] = (image_data, time.time())


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
        base_width, base_height = 12, 12
        scaled_width = base_width * config.scale_factor
        scaled_height = base_height * config.scale_factor

        fig = plt.figure(figsize=(scaled_width, scaled_height), dpi=config.dpi)
        axis = fig.add_subplot(111)

        # 基础线条宽度
        base_line_width = 2 * config.scale_factor

        # 添加球场背景色
        court_bg = Rectangle(
            xy=(-250, -47.5),
            width=500,
            height=470,
            linewidth=0,
            facecolor='#F8F8F8',  # 超浅灰色背景
            fill=True
        )
        axis.add_patch(court_bg)

        # 先绘制填充的禁区（精确对齐到框线）
        paint_fill = Rectangle(
            xy=(-80, -47.5),  # 完全对齐外框
            width=160,  # 使用完整宽度
            height=190,  # 完整高度
            linewidth=0,  # 无边框
            fill=True,
            facecolor='#FDB927',  # 淡紫色
            alpha=0.3
        )
        axis.add_patch(paint_fill)

        # 然后绘制球场外框，使用更粗的线条
        outer_lines = Rectangle(xy=(-250, -47.5), width=500, height=470,
                                linewidth=base_line_width * 2, edgecolor='k', fill=False, zorder=3)
        axis.add_patch(outer_lines)

        # 绘制禁区边框
        paint = Rectangle(xy=(-80, -47.5), width=160, height=190,
                          linewidth=base_line_width * 1.5, edgecolor='k', fill=False, zorder=2)
        axis.add_patch(paint)

        # 绘制禁区内框,有些球场不画这个内框线
        # 在matplotlib中，绘图元素的层级由zorder参数控制。较大的zorder值会显示在较小值的上层
        inner_paint = Rectangle(xy=(-60, -47.5), width=120, height=190,
                                linewidth=base_line_width * 1.2, edgecolor='#808080', fill=False, zorder=1)
        axis.add_patch(inner_paint)

        # 绘制限制区（restricted area）- 4英尺半径
        restricted = Arc(xy=(0, 0), width=80, height=80,  # 40*2=80 为直径
                         theta1=0, theta2=180,
                         linewidth=base_line_width * 1.5, color='k', fill=False, zorder=2)
        axis.add_patch(restricted)

        # 绘制篮板
        backboard = Rectangle(xy=(-30, -7.5), width=60, height=1,
                              linewidth=base_line_width * 1.5, edgecolor='k', fill=False, zorder=2)
        axis.add_patch(backboard)

        # 绘制篮筐 (在篮板前方4个单位)
        basket = Circle(xy=(0, 4), radius=7.5, linewidth=base_line_width * 1.5, color='k', fill=False, zorder=2)
        axis.add_patch(basket)

        # 绘制罚球圈 - 上半部分（实线）
        free_throw_circle_top = Arc(xy=(0, 142.5), width=120, height=120,
                                    theta1=0, theta2=180,
                                    linewidth=base_line_width * 1.5, color='k', zorder=2)
        axis.add_patch(free_throw_circle_top)

        # 绘制罚球圈 - 下半部分（虚线）
        free_throw_circle_bottom = Arc(xy=(0, 142.5), width=120, height=120,
                                       theta1=180, theta2=360,
                                       linewidth=base_line_width * 1.2, linestyle='--', color='#808080', zorder=1)
        axis.add_patch(free_throw_circle_bottom)

        # 绘制三分线
        three_left = Rectangle(xy=(-220, -47.5), width=0, height=140,
                               linewidth=base_line_width * 1.5, edgecolor='k', fill=False, zorder=2)
        three_right = Rectangle(xy=(220, -47.5), width=0, height=140,
                                linewidth=base_line_width * 1.5, edgecolor='k', fill=False, zorder=2)
        axis.add_patch(three_left)
        axis.add_patch(three_right)

        # 绘制三分弧线
        three_arc = Arc(xy=(0, 0), width=477.32, height=477.32,
                        theta1=22.8, theta2=157.2,
                        linewidth=base_line_width * 1.5, color='k', zorder=2)
        axis.add_patch(three_arc)

        # 绘制中场圆圈填充
        center_circle_fill = Circle(xy=(0, 422.5), radius=60,
                                    facecolor='#552583',  # 湖人紫色
                                    alpha=0.3,  # 设置透明度让颜色变淡
                                    zorder=1)  # 确保在底层
        axis.add_patch(center_circle_fill)

        # 绘制中场圆圈
        center_outer_arc = Arc(xy=(0, 422.5), width=120, height=120,
                               theta1=180, theta2=0,
                               linewidth=base_line_width * 1.5, color='k', zorder=2)
        center_inner_arc = Arc(xy=(0, 422.5), width=40, height=40,
                               theta1=180, theta2=0,
                               linewidth=base_line_width * 1.5, color='k', zorder=2)
        axis.add_patch(center_outer_arc)
        axis.add_patch(center_inner_arc)

        # 设置坐标轴
        axis.set_xlim(-250, 250)
        axis.set_ylim(422.5, -47.5)
        axis.set_xticks([])
        axis.set_yticks([])

        return fig, axis

    # 用来缓存头像
    _image_cache = ImageCache()

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
    def _get_cached_image(url: str) -> Optional[bytes]:
        """获取缓存的图片数据"""
        return CourtRenderer._image_cache.get(url)

    @staticmethod
    def _cache_image(url: str, image_data: bytes):
        """缓存图片数据"""
        CourtRenderer._image_cache.set(url, image_data)

    @staticmethod
    def add_player_portrait(axis: plt.Axes, player_id: int,
                            position=(0.9995, 0.002),
                            size: Optional[float] = None,
                            config: Optional[ChartConfig] = None) -> None:
        """在球场图添加球员头像"""
        try:
            image_url = CourtRenderer.get_player_headshot_url(player_id)

            # 尝试从缓存获取图片
            image_data = CourtRenderer._get_cached_image(image_url)

            if image_data is None:
                # 如果缓存中没有，则下载图片
                response = requests.get(image_url)
                image_data = response.content
                CourtRenderer._cache_image(image_url, image_data)

            img = Image.open(BytesIO(image_data))

            # 使用配置中的默认大小或传入的大小，应用全局缩放因子
            portrait_size = size or (config.portrait_size if config else 0.02)
            if config:
                portrait_size *= config.portrait_scale_factor

            # 计算裁剪边界
            width, height = img.size
            if width > height:
                left = (width - height) // 2
                img = img.crop((left, 0, left + height, height))
            else:
                top = (height - width) // 2
                img = img.crop((0, top, width, top + width))

            # 创建子图，使用更小的尺寸
            portrait_ax = axis.inset_axes(
                (position[0] - portrait_size, position[1],
                 portrait_size, portrait_size),
                transform=axis.transAxes
            )
            portrait_ax.imshow(img)
            portrait_ax.axis('off')

        except Exception as e:
            print(f"添加球员头像时出错: {str(e)}")

    @staticmethod
    def add_shot_marker_with_portrait(axis: Axes, x: float, y: float,
                                      player_id: int, marker_size: float = 0.02,
                                      alpha: float = 1.0,
                                      config: Optional[ChartConfig] = None) -> None:
        """添加带有球员头像的投篮标记（增强版：抗锯齿处理）"""
        try:
            # 应用全局缩放因子
            if config:
                marker_size *= config.portrait_scale_factor

            # 使用小尺寸头像（提升加载速度）
            image_url = CourtRenderer.get_player_headshot_url(player_id, small=True)
            # 尝试从缓存获取图片
            image_data = CourtRenderer._get_cached_image(image_url)
            if image_data is None:
                response = requests.get(image_url)
                image_data = response.content
                CourtRenderer._cache_image(image_url, image_data)
            img = Image.open(BytesIO(image_data))

            # 提高初始尺寸以改善缩放质量
            size_px = int(min(img.size))
            # 将图像放大至更高分辨率以提高抗锯齿效果
            upscale_factor = 2  # 放大倍数
            large_size = size_px * upscale_factor
            img = img.resize((large_size, large_size), Image.Resampling.LANCZOS)

            # 创建高分辨率的圆形 mask
            mask_size = large_size * 2
            mask = Image.new('L', (mask_size, mask_size), 0)
            draw = ImageDraw.Draw(mask)
            # 绘制高分辨率圆形
            draw.ellipse((0, 0, mask_size - 1, mask_size - 1), fill=255)
            # 将 mask 缩放回放大后的图像大小，保持平滑边缘
            mask = mask.resize((large_size, large_size), Image.Resampling.LANCZOS)

            # 将头像贴到透明背景上
            output = Image.new('RGBA', (large_size, large_size), (0, 0, 0, 0))
            output.paste(img, mask=mask)

            # 增强图像效果（对比度和锐度）
            enhancer = ImageEnhance.Contrast(output)
            output = enhancer.enhance(1.2)  # 略微增强对比度
            enhancer = ImageEnhance.Sharpness(output)
            output = enhancer.enhance(1.3)  # 略微增强锐度

            # 缩放回目标尺寸，保持平滑的圆形边缘
            output = output.resize((size_px, size_px), Image.Resampling.LANCZOS)

            # 计算标记对应的数据坐标尺寸（假设球场宽度约500单位）
            marker_data_size = marker_size * 500
            marker_ax = axis.inset_axes(
                (x - marker_data_size / 2, y - marker_data_size / 2,
                 marker_data_size, marker_data_size),
                transform=axis.transData
            )

            # 显示头像图像（抗锯齿处理）
            marker_ax.imshow(output, alpha=alpha, interpolation='antialiased')
            # 边框样式（从配置获取，否则使用默认值）
            border_color = config.marker_border_color if config else '#3A7711'
            border_width = config.marker_border_width if config else 0.5
            # 添加圆形边框（抗锯齿）
            circle = plt.Circle((size_px / 2, size_px / 2), size_px / 2 - 0.5,
                                fill=False, color=border_color,
                                linewidth=border_width,
                                transform=marker_ax.transData,
                                antialiased=True)
            marker_ax.add_patch(circle)
            marker_ax.axis('off')

            # 强制重绘以应用抗锯齿效果
            marker_ax.figure.canvas.draw_idle()
        except Exception as e:
            print(f"添加投篮标记时出错: {str(e)}")


class GameChartsService:
    """NBA比赛数据可视化服务"""

    def __init__(self, game_data_service: GameDataProvider,
                 config: Optional[ChartConfig] = None):
        """初始化服务"""
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.game_data_service = game_data_service
        self.config = config or ChartConfig()

    def plot_player_scoring_impact(self,
                                   shots: List[Dict[str, Any]],
                                   player_id: Optional[int] = None,
                                   title: Optional[str] = None,
                                   output_path: Optional[Union[str, Path]] = None) -> Tuple[
        Optional[plt.Figure], Dict[str, Any]]:
        """绘制球员投篮图

        Args:
            shots: 投篮数据列表
            player_id: 球员ID（用于显示头像）
            title: 图表标题
            output_path: 输出路径
        """
        shot_stats = {'total': 0, 'made': 0, 'assisted': 0, 'unassisted': 0}

        try:
            if not shots:
                self.logger.warning("未提供投篮数据")
                return None, shot_stats

            # 创建图表
            fig, ax = CourtRenderer.draw_court(self.config)

            # 计算合适的标记大小 - 与球场成比例
            # 球场宽度为500单位，调整为更合适的视觉大小
            marker_size = 100 * self.config.scale_factor  # 显著增大标记尺寸

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
                                   s=marker_size,  # 增大点的大小
                                   linewidths=2 * self.config.scale_factor,
                                   zorder=2)
                    else:
                        ax.scatter(x, y,
                                   marker='x',
                                   color='#A82B2B',  # 暗红色
                                   s=marker_size,  # 增大点的大小
                                   linewidths=2 * self.config.scale_factor,
                                   zorder=2)

            # 添加标题
            if title:
                ax.set_title(title, pad=20, fontsize=12 * self.config.scale_factor)

            # 添加制作者水印信息
            ax.text(-240, 400, 'Created by 微博@勒布朗bot',
                    verticalalignment='top',
                    horizontalalignment='left',
                    fontsize=10 * self.config.scale_factor,
                    color='gray',
                    alpha=0.5)

            # 添加球员头像 - 使用现有方法但传入更大的尺寸参数
            if player_id:
                # 中圈半径约为60单位，将头像尺寸调整为与中圈相当
                portrait_size = 0.15  # 显著增大头像尺寸，约为原来的7.5倍
                portrait_position = (0.85, 0.03)  # 右下角，留出一些边距

                # 使用现有方法但传入自定义尺寸和位置
                CourtRenderer.add_player_portrait(
                    ax,
                    player_id,
                    position=portrait_position,
                    size=portrait_size,
                    config=self.config
                )

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
                dpi=self.config.dpi,  # 从 self.config.dpi 获取 dpi
                pad_inches=0.1
            )
            plt.close(fig)
            self.logger.info(f"图表已保存至 {output_path}")
        except Exception as e:
            self.logger.error(f"保存图表时出错: {e}")
            raise e

    def plot_team_shots(self, game, team_id: int,
                        title: Optional[str] = None,
                        output_path: Optional[str] = None) -> Optional[plt.Figure]:
        """绘制球队所有球员的投篮分布图（区域自适应头像大小）"""
        try:
            fig, ax = CourtRenderer.draw_court(self.config)
            team_shots = game.get_team_shot_data(team_id)
            if not team_shots:
                return None

            # 收集所有命中投篮的坐标和对应球员
            all_made_shots_data = []
            for player_id, shots in team_shots.items():
                for shot in shots:
                    if shot.get('shot_result') == 'Made':
                        x = shot.get('x_legacy')
                        y = shot.get('y_legacy')
                        if x is not None and y is not None:
                            x, y = float(x), float(y)
                            all_made_shots_data.append((player_id, x, y))

            if len(all_made_shots_data) < 5:
                self.logger.warning("投篮点太少，无法生成热度图")
                return None

            # 准备用于密度计算的投篮坐标
            shot_points = np.array([(x, y) for _, x, y in all_made_shots_data]).T

            # 计算全局投篮点核密度估计 (KDE)
            global_kde = gaussian_kde(shot_points, bw_method='silverman')
            shot_densities = global_kde(shot_points)
            max_density = np.max(shot_densities)
            min_density = np.min(shot_densities)

            # 预处理：为已知的高密度区域定义特殊系数
            def get_region_modifier(x, y):
                """返回基于区域的头像大小修正系数"""
                # 禁区内 - 显著减小头像
                if -80 <= x <= 80 and -47.5 <= y <= 142.5:
                    if y < 0:  # 篮筐附近
                        return 0.4  # 篮下区域头像更小
                    return 0.5  # 禁区其他区域

                # 左底角三分
                if x < -200 and y < 100:
                    return 0.6

                # 右底角三分
                if x > 200 and y < 100:
                    return 0.6

                # 弧顶三分区
                if -120 <= x <= 120 and 200 <= y <= 270:
                    return 0.7

                # 中距离区域 - 适中头像
                if 100 <= y <= 180:
                    return 0.8

                # 其他区域 - 标准头像
                return 1.0

            # 准备最终的投篮信息列表
            shots_info = []
            for i, (player_id, x, y) in enumerate(all_made_shots_data):
                # 计算该点的密度因子(0~1范围)
                normalized_density = (shot_densities[i] - min_density) / (
                            max_density - min_density) if max_density > min_density else 0.5

                # 结合区域修正和密度因子
                region_modifier = get_region_modifier(x, y)

                # 密度越高，尺寸越小(使用非线性映射)
                density_factor = 1.0 - min(0.75, normalized_density ** 2)

                # 组合两种因子
                combined_factor = region_modifier * density_factor

                # 计算最终尺寸
                # 基础尺寸
                base_size = 0.015
                # 限制最小和最大尺寸
                final_size = base_size * max(0.3, min(1.2, combined_factor))

                # 保存结果
                shots_info.append({
                    'player_id': player_id,
                    'x': x, 'y': y,
                    'size': final_size,
                    'alpha': max(0.8, 1.0 - normalized_density * 0.2)  # 略微调整透明度
                })

            # 绘制所有头像
            for shot in shots_info:
                CourtRenderer.add_shot_marker_with_portrait(
                    ax, shot['x'], shot['y'],
                    shot['player_id'],
                    marker_size=shot['size'],
                    alpha=shot['alpha'],
                    config=self.config
                )

            if title:
                ax.set_title(title, pad=20, fontsize=12 * self.config.scale_factor)
            if output_path:
                self._save_figure(fig, output_path)
            return fig
        except Exception as e:
            self.logger.error(f"绘制球队投篮图时出错: {str(e)}", exc_info=True)
            return None