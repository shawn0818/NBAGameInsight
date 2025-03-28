from dataclasses import dataclass
import time
import threading
from typing import Optional, Dict, Any, Tuple, Union, List
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle, Circle, Arc
from matplotlib.lines import Line2D
from PIL import Image, ImageDraw, ImageEnhance
import requests
from io import BytesIO
from pathlib import Path
from scipy.spatial import cKDTree

from nba.models.game_model import Game
from utils.logger_handler import AppLogger
from config import NBAConfig


@dataclass
class ChartConfig:
    """图表服务配置"""
    # 基础图表设置
    dpi: int = 350  # 图表DPI
    scale_factor: float = 1.5  # 图表缩放比例
    figure_path: Optional[Path] = None  # 图表保存路径

    # 标记相关设置
    marker_base_size: float = 0.025  # 标记基础大小
    marker_min_size: float = 0.01  # 标记最小大小
    ideal_marker_distance: float = 25.0  # 理想标记间距（球场坐标单位）

    # 颜色设置
    made_shot_color: str = '#3A7711'  # 命中投篮边框颜色
    missed_shot_color: str = '#C9082A'  # 未命中投篮边框颜色
    court_bg_color: str = '#F8F8F8'  # 球场背景色
    paint_color: str = '#FDB927'  # 禁区颜色
    paint_alpha: float = 0.3  # 禁区透明度

    # 图像缓存设置
    cache_duration: int = 24 * 60 * 60  # 缓存有效期（秒），默认24小时

    # 边框设置
    marker_border_width: float = 0.5  # 头像边框宽度

    def __post_init__(self) -> None:
        """配置验证与初始化"""
        if self.dpi < 72 or self.dpi > 600:
            raise ValueError("DPI must be between 72 and 600")
        if self.scale_factor < 0.5 or self.scale_factor > 5.0:
            raise ValueError("Scale factor must be between 0.5 and 5.0")

        # 设定中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei']  # 使用黑体
        plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题


class ImageCache:
    """优化的图像缓存管理器"""

    def __init__(self, cache_duration: int = 24 * 60 * 60) -> None:
        # 原始图像缓存
        self.raw_cache: Dict[str, Tuple[bytes, float]] = {}
        # 处理后图像缓存（按大小和处理类型）
        self.processed_cache: Dict[str, Tuple[Image.Image, float]] = {}
        self.cache_duration = cache_duration

    def get_raw(self, key: str) -> Optional[bytes]:
        """获取缓存的原始图像数据"""
        if key in self.raw_cache:
            image_data, timestamp = self.raw_cache[key]
            if time.time() - timestamp < self.cache_duration:
                return image_data
            else:
                del self.raw_cache[key]
        return None

    def set_raw(self, key: str, image_data: bytes) -> None:
        """设置原始图像缓存"""
        self.raw_cache[key] = (image_data, time.time())

    def get_processed(self, key: str) -> Optional[Image.Image]:
        """获取处理后的图像"""
        if key in self.processed_cache:
            image, timestamp = self.processed_cache[key]
            if time.time() - timestamp < self.cache_duration:
                return image
            else:
                del self.processed_cache[key]
        return None

    def set_processed(self, key: str, image: Image.Image) -> None:
        """缓存处理后的图像"""
        self.processed_cache[key] = (image, time.time())


class PlayerImageManager:
    """球员图像管理器 - 处理球员头像的获取、处理和缓存"""

    # 使用单例模式共享缓存
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, cache_duration: int = 24 * 60 * 60) -> 'PlayerImageManager':
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(PlayerImageManager, cls).__new__(cls)
                cls._instance.cache = ImageCache(cache_duration)
                cls._instance.session = requests.Session()  # 重用HTTP连接
        return cls._instance

    def get_player_headshot_url(self, player_id: int, small: bool = False) -> str:
        """获取NBA官方球员头像URL"""
        if small:
            return f"https://cdn.nba.com/headshots/nba/latest/260x190/{player_id}.png"
        return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png"

    def get_player_image(self, player_id: int, size: int = 100, is_circle: bool = True) -> Image.Image:
        """获取特定大小的球员头像

        Args:
            player_id: 球员ID
            size: 目标图像大小（像素）
            is_circle: 是否返回圆形头像

        Returns:
            处理后的球员头像图像
        """
        # 构建缓存键
        cache_key = f"player_{player_id}_size_{size}_circle_{is_circle}"

        # 检查缓存中是否有处理后的图像
        processed_image = self.cache.get_processed(cache_key)
        if processed_image:
            return processed_image

        # 获取原始图像
        image_url = self.get_player_headshot_url(player_id, small=True)
        raw_data = self.cache.get_raw(image_url)

        if raw_data is None:
            try:
                response = self.session.get(image_url)
                raw_data = response.content
                self.cache.set_raw(image_url, raw_data)
            except Exception as e:
                print(f"获取球员图像失败: {e}")
                # 返回一个占位图像
                placeholder = Image.new('RGBA', (size, size), (200, 200, 200, 255))
                return placeholder

        # 处理图像
        try:
            img = Image.open(BytesIO(raw_data))
            processed = self._process_image(img, size, is_circle)
            self.cache.set_processed(cache_key, processed)
            return processed
        except Exception as e:
            print(f"处理球员图像失败: {e}")
            placeholder = Image.new('RGBA', (size, size), (200, 200, 200, 255))
            return placeholder

    def _process_image(self, img: Image.Image, target_size: int, is_circle: bool = True) -> Image.Image:
        """处理球员头像（裁剪、缩放、圆形处理）"""
        # 优化的图像处理流程
        try:
            # 1. 将图像转换为RGBA模式以支持透明度
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # 2. 裁剪为正方形（从中心裁剪）
            width, height = img.size
            crop_size = min(width, height)
            left = (width - crop_size) // 2
            top = (height - crop_size) // 2
            img = img.crop((left, top, left + crop_size, top + crop_size))

            # 3. 调整到目标大小
            img = img.resize((target_size, target_size), Image.Resampling.LANCZOS)

            # 4. 如果需要圆形处理
            if is_circle:
                # 创建一个圆形mask
                mask = Image.new('L', (target_size, target_size), 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, target_size - 1, target_size - 1), fill=255)

                # 创建新的透明背景图像
                circle_img = Image.new('RGBA', (target_size, target_size), (0, 0, 0, 0))
                # 将头像应用mask后贴到透明背景上
                circle_img.paste(img, (0, 0), mask)

                # 增强图像效果
                enhancer = ImageEnhance.Contrast(circle_img)
                circle_img = enhancer.enhance(1.2)

                return circle_img

            return img

        except Exception as e:
            print(f"图像处理错误: {e}")
            # 返回一个基本占位图
            return Image.new('RGBA', (target_size, target_size), (200, 200, 200, 255))


class CourtRenderer:
    """NBA球场渲染器 - 专注于绘制球场元素"""

    @staticmethod
    def draw_court(config: ChartConfig) -> Tuple[plt.Figure, plt.Axes]:
        """绘制NBA半场

        Args:
            config: 图表配置对象

        Returns:
            fig, axis: matplotlib图表对象和轴对象
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
            facecolor=config.court_bg_color,
            fill=True
        )
        axis.add_patch(court_bg)

        # 绘制填充的禁区
        paint_fill = Rectangle(
            xy=(-80, -47.5),
            width=160,
            height=190,
            linewidth=0,
            fill=True,
            facecolor=config.paint_color,
            alpha=config.paint_alpha
        )
        axis.add_patch(paint_fill)

        # 球场外框
        outer_lines = Rectangle(xy=(-250, -47.5), width=500, height=470,
                                linewidth=base_line_width * 2, edgecolor='k', fill=False, zorder=3)
        axis.add_patch(outer_lines)

        # 禁区边框
        paint = Rectangle(xy=(-80, -47.5), width=160, height=190,
                          linewidth=base_line_width * 1.5, edgecolor='k', fill=False, zorder=2)
        axis.add_patch(paint)

        # 禁区内框
        inner_paint = Rectangle(xy=(-60, -47.5), width=120, height=190,
                                linewidth=base_line_width * 1.2, edgecolor='#808080', fill=False, zorder=1)
        axis.add_patch(inner_paint)

        # 限制区（restricted area）
        restricted = Arc(xy=(0, 0), width=80, height=80,
                         theta1=0, theta2=180,
                         linewidth=base_line_width * 1.5, color='k', fill=False, zorder=2)
        axis.add_patch(restricted)

        # 篮板
        backboard = Rectangle(xy=(-30, -7.5), width=60, height=1,
                              linewidth=base_line_width * 1.5, edgecolor='k', fill=False, zorder=2)
        axis.add_patch(backboard)

        # 篮筐
        basket = Circle(xy=(0, 4), radius=7.5, linewidth=base_line_width * 1.5, color='k', fill=False, zorder=2)
        axis.add_patch(basket)

        # 罚球圈 - 上半部分（实线）
        free_throw_circle_top = Arc(xy=(0, 142.5), width=120, height=120,
                                    theta1=0, theta2=180,
                                    linewidth=base_line_width * 1.5, color='k', zorder=2)
        axis.add_patch(free_throw_circle_top)

        # 罚球圈 - 下半部分（虚线）
        free_throw_circle_bottom = Arc(xy=(0, 142.5), width=120, height=120,
                                       theta1=180, theta2=360,
                                       linewidth=base_line_width * 1.2, linestyle='--', color='#808080', zorder=1)
        axis.add_patch(free_throw_circle_bottom)

        # 三分线
        three_left = Rectangle(xy=(-220, -47.5), width=0, height=140,
                               linewidth=base_line_width * 1.5, edgecolor='k', fill=False, zorder=2)
        three_right = Rectangle(xy=(220, -47.5), width=0, height=140,
                                linewidth=base_line_width * 1.5, edgecolor='k', fill=False, zorder=2)
        axis.add_patch(three_left)
        axis.add_patch(three_right)

        # 三分弧线
        three_arc = Arc(xy=(0, 0), width=477.32, height=477.32,
                        theta1=22.8, theta2=157.2,
                        linewidth=base_line_width * 1.5, color='k', zorder=2)
        axis.add_patch(three_arc)

        # 中场圆圈填充
        center_circle_fill = Circle(xy=(0, 422.5), radius=60,
                                    facecolor='#552583',
                                    alpha=0.3,
                                    zorder=1)
        axis.add_patch(center_circle_fill)

        # 中场圆圈
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

    @staticmethod
    def add_player_portrait(axis: Axes, player_id: int,
                          position: Tuple[float, float] = (0.9995, 0.002),
                          size: float = 0.15,
                          config: Optional[ChartConfig] = None) -> None:
        """在图表中添加球员肖像（通常用于图表右下角标识）

        Args:
            axis: matplotlib轴对象
            player_id: 球员ID
            position: 肖像位置（相对坐标）
            size: 肖像大小（相对大小）
            config: 图表配置，用于获取DPI等信息
        """
        try:
            # 获取图像管理器
            image_manager = PlayerImageManager()

            # 计算图像尺寸（像素）
            fig_width, fig_height = axis.figure.get_size_inches()
            dpi = axis.figure.dpi if config is None else config.dpi
            portrait_size_px = int(size * fig_width * dpi)

            # 获取处理后的图像
            img = image_manager.get_player_image(player_id, size=portrait_size_px)

            # 创建子图
            portrait_ax = axis.inset_axes(
                (position[0] - size, position[1], size, size),
                transform=axis.transAxes
            )
            portrait_ax.imshow(img)
            portrait_ax.axis('off')

        except Exception as e:
            print(f"添加球员肖像出错: {str(e)}")


class ShotProcessor:
    """投篮数据处理器 - 处理和分析投篮数据"""

    @staticmethod
    def calculate_marker_sizes(coordinates: List[Tuple[float, float]], config: ChartConfig) -> List[float]:
        """基于局部密度计算每个投篮点标记大小

        Args:
            coordinates: 投篮点坐标列表 [(x1,y1), (x2,y2), ...]
            config: 图表配置

        Returns:
            每个点对应的标记大小列表
        """
        if len(coordinates) <= 1:
            return [config.marker_base_size] * len(coordinates)

        # 构建KD树
        tree = cKDTree(coordinates)

        # 查询每个点的最近邻点
        distances, _ = tree.query(coordinates, k=2)  # k=2因为最近的点是自己
        nearest_distances = distances[:, 1]  # 第二近的点距离

        # 计算每个点的标记大小
        marker_sizes = []
        for dist in nearest_distances:
            if dist < config.ideal_marker_distance:
                # 根据距离比例平滑缩放
                scale_factor = max(config.marker_min_size / config.marker_base_size,
                                  dist / config.ideal_marker_distance)
                size = config.marker_base_size * scale_factor
            else:
                # 孤立点保持原始大小
                size = config.marker_base_size

            marker_sizes.append(size)

        return marker_sizes

    @staticmethod
    def prepare_team_shots_data(team_shots: Dict[int, List[Dict[str, Any]]],
                               shot_outcome: str = "made_only",
                               config: Optional[ChartConfig] = None) -> List[Dict[str, Any]]:
        """处理球队投篮数据

        Args:
            team_shots: 球队投篮数据字典 {player_id: [shot_data, ...], ...}
            shot_outcome: 筛选条件，"made_only"仅命中，"all"全部
            config: 图表配置

        Returns:
            所有投篮点信息列表
        """
        if not config:
            config = ChartConfig()

        # 收集投篮数据
        all_shots_data = []
        for player_id, shots in team_shots.items():
            for shot in shots:
                shot_result = shot.get('shot_result')
                if shot_outcome == "made_only" and shot_result != "Made":
                    continue

                x = shot.get('x_legacy')
                y = shot.get('y_legacy')
                if x is not None and y is not None:
                    all_shots_data.append({
                        'player_id': player_id,
                        'x': float(x),
                        'y': float(y),
                        'is_made': shot_result == "Made"
                    })

        if len(all_shots_data) < 2:
            return all_shots_data

        # 提取坐标计算标记大小
        coordinates = [(shot['x'], shot['y']) for shot in all_shots_data]
        marker_sizes = ShotProcessor.calculate_marker_sizes(coordinates, config)

        # 合并标记大小到投篮数据
        for i, shot in enumerate(all_shots_data):
            shot['size'] = marker_sizes[i]
            # 命中的投篮设置更高的不透明度
            shot['alpha'] = 0.95 if shot['is_made'] else 0.75

        return all_shots_data

    @staticmethod
    def prepare_player_shots_data(player_shots: List[Dict[str, Any]],
                                shot_outcome: str = "made_only",
                                config: Optional[ChartConfig] = None) -> List[Dict[str, Any]]:
        """处理单个球员的投篮数据

        Args:
            player_shots: 球员投篮数据列表
            shot_outcome: 筛选条件，"made_only"仅命中，"all"全部
            config: 图表配置

        Returns:
            所有投篮点信息列表
        """
        if not config:
            config = ChartConfig()

        # 收集投篮数据
        all_shots_data = []
        for shot in player_shots:
            shot_result = shot.get('shot_result')
            if shot_outcome == "made_only" and shot_result != "Made":
                continue

            x = shot.get('x_legacy')
            y = shot.get('y_legacy')
            player_id = shot.get('player_id')
            if x is not None and y is not None and player_id is not None:
                all_shots_data.append({
                    'player_id': player_id,
                    'x': float(x),
                    'y': float(y),
                    'is_made': shot_result == "Made"
                })

        if len(all_shots_data) < 2:
            return all_shots_data

        # 提取坐标计算标记大小
        coordinates = [(shot['x'], shot['y']) for shot in all_shots_data]
        marker_sizes = ShotProcessor.calculate_marker_sizes(coordinates, config)

        # 合并标记大小到投篮数据
        for i, shot in enumerate(all_shots_data):
            shot['size'] = marker_sizes[i]
            shot['alpha'] = 0.95 if shot['is_made'] else 0.75

        return all_shots_data


class ShotRenderer:
    """投篮图渲染器 - 负责将处理后的投篮数据渲染到球场上"""

    @staticmethod
    def add_player_info_box(axis: Axes, player_id: int, player_stats: Dict[str, Any], config: ChartConfig) -> None:
        """添加球员信息框

        在球场图底部添加包含球员头像、数据统计和制作者信息的矩形框

        Args:
            axis: matplotlib轴对象
            player_id: 球员ID
            player_stats: 球员统计数据字典，包含姓名、数据等
            config: 图表配置
        """
        try:
            # 创建底部信息框区域
            fig_width, fig_height = axis.figure.get_size_inches()
            box_height = fig_height * 0.15  # 信息框高度为图表高度的15%

            # 创建信息框子图
            box_ax = axis.figure.add_axes([0.05, 0.02, 0.9, box_height / fig_height])

            # 绘制背景矩形
            box_rect = Rectangle(
                xy=(0, 0),
                width=1,
                height=1,
                facecolor='#F8F8F8',
                edgecolor='#333333',
                linewidth=2,
                alpha=0.9,
                transform=box_ax.transAxes
            )
            box_ax.add_patch(box_rect)

            # 获取图像管理器
            image_manager = PlayerImageManager()

            # 计算头像区域大小和位置
            portrait_width = 0.20  # 头像宽度为信息框宽度的20%
            portrait_size_px = int(fig_width * portrait_width * box_ax.figure.dpi)

            # 获取球员头像
            player_image = image_manager.get_player_image(
                player_id,
                size=portrait_size_px,
                is_circle=False  # 使用方形头像
            )

            # 创建头像子图
            portrait_ax = box_ax.inset_axes(
                [0.03, 0.1, portrait_width, 0.8],
                transform=box_ax.transAxes
            )
            portrait_ax.imshow(player_image)
            portrait_ax.axis('off')

            # 添加球员姓名和数据
            name = player_stats.get('name', '球员')
            box_ax.text(
                0.26, 0.75,
                name,
                fontsize=14 * config.scale_factor,
                weight='bold',
                transform=box_ax.transAxes
            )

            # 添加球员统计数据
            stats_text = ''
            if 'position' in player_stats:
                stats_text += f"位置: {player_stats['position']}   "
            if 'points' in player_stats:
                stats_text += f"得分: {player_stats['points']}   "
            if 'fg_pct' in player_stats:
                stats_text += f"命中率: {player_stats['fg_pct']:.1%}   "
            if 'three_pct' in player_stats:
                stats_text += f"三分命中率: {player_stats['three_pct']:.1%}   "

            box_ax.text(
                0.26, 0.45,
                stats_text,
                fontsize=12 * config.scale_factor,
                transform=box_ax.transAxes
            )

            # 可以添加更多统计数据行
            more_stats = ''
            if 'assists' in player_stats:
                more_stats += f"助攻: {player_stats['assists']}   "
            if 'rebounds' in player_stats:
                more_stats += f"篮板: {player_stats['rebounds']}   "
            if 'steals' in player_stats:
                more_stats += f"抢断: {player_stats['steals']}   "
            if 'blocks' in player_stats:
                more_stats += f"盖帽: {player_stats['blocks']}   "

            if more_stats:
                box_ax.text(
                    0.26, 0.25,
                    more_stats,
                    fontsize=12 * config.scale_factor,
                    transform=box_ax.transAxes
                )

            # 添加制作者信息
            box_ax.text(
                0.98, 0.05,
                'Created by 微博@勒布朗bot',
                fontsize=8 * config.scale_factor,
                color='gray',
                alpha=0.8,
                horizontalalignment='right',
                transform=box_ax.transAxes
            )

            # 去除坐标轴
            box_ax.axis('off')

        except Exception as e:
            print(f"添加球员信息框出错: {str(e)}")
            # 出错时不影响主图显示

    @staticmethod
    def add_shot_marker(axis: Axes, shot_data: Dict[str, Any], config: ChartConfig) -> None:
        """添加单个投篮标记

        Args:
            axis: matplotlib轴对象
            shot_data: 投篮点数据，包含x、y、player_id、size、alpha、is_made等
            config: 图表配置
        """
        try:
            # 获取图像管理器
            image_manager = PlayerImageManager()

            # 确定边框颜色
            border_color = config.made_shot_color if shot_data['is_made'] else config.missed_shot_color

            x, y = shot_data['x'], shot_data['y']
            marker_size = shot_data['size']
            alpha = shot_data['alpha']
            player_id = shot_data['player_id']

            # 计算图像像素尺寸
            marker_data_size = marker_size * 500  # 从相对大小转换为数据坐标系大小

            # 计算子图区域
            marker_ax = axis.inset_axes(
                (x - marker_data_size / 2, y - marker_data_size / 2,
                 marker_data_size, marker_data_size),
                transform=axis.transData
            )

            # 获取适当大小的球员头像
            fig_width_inch = axis.figure.get_size_inches()[0]
            dpi = axis.figure.dpi
            pixels_per_data_unit = (fig_width_inch * dpi) / 500  # 假设球场宽度约500单位
            image_size_px = int(marker_data_size * pixels_per_data_unit)
            image_size_px = max(20, image_size_px)  # 确保图像不会太小

            # 获取球员头像
            player_image = image_manager.get_player_image(player_id, size=image_size_px)

            # 显示头像
            marker_ax.imshow(player_image, alpha=alpha)

            # 添加边框
            border_width = config.marker_border_width
            circle = plt.Circle((image_size_px / 2, image_size_px / 2),
                                image_size_px / 2 - 0.5,
                                fill=False,
                                color=border_color,
                                linewidth=border_width,
                                transform=marker_ax.transData,
                                antialiased=True)
            marker_ax.add_patch(circle)
            marker_ax.axis('off')

        except Exception as e:
            print(f"添加投篮标记出错: {str(e)}")

    @staticmethod
    def add_legend(axis: Axes, shot_outcome: str = "made_only") -> None:
        """添加图例

        Args:
            axis: matplotlib轴对象
            shot_outcome: "made_only"仅显示命中，"all"显示所有
        """
        # 使用列表字面量初始化
        legend_elements = [
            Line2D([0], [0], marker='o', color='w', markerfacecolor='#3A7711',
                   markeredgecolor='#3A7711', markersize=10, label='投篮命中')
        ]

        # 未命中投篮图例（仅在显示全部投篮时添加）
        if shot_outcome == "all":
            legend_elements.append(
                Line2D([0], [0], marker='o', color='w', markerfacecolor='white',
                       markeredgecolor='#C9082A', markersize=10, label='投篮未命中')
            )

        axis.legend(handles=legend_elements, loc='upper right')

    @staticmethod
    def render_shots(axis: Axes, shots_data: List[Dict[str, Any]], config: ChartConfig) -> None:
        """渲染所有投篮点

        Args:
            axis: matplotlib轴对象
            shots_data: 处理后的投篮数据列表
            config: 图表配置
        """
        for shot in shots_data:
            ShotRenderer.add_shot_marker(axis, shot, config)


class GameChartsService:
    """NBA比赛数据可视化服务 - 增强版，整合业务逻辑"""

    def __init__(self, config: Optional[ChartConfig] = None) -> None:
        """初始化服务"""
        self.config = config or ChartConfig()

        # 使用 NBAConfig.PATHS.PICTURES_DIR 作为默认图表保存路径
        if not self.config.figure_path:
            self.config.figure_path = NBAConfig.PATHS.PICTURES_DIR

        # 确保图表保存路径存在
        if self.config.figure_path:
            self.config.figure_path.mkdir(parents=True, exist_ok=True)

        # 使用 NBAConfig.PATHS.PICTURES_DIR 作为默认输出目录
        self.default_output_dir = self.config.figure_path
        self.default_output_dir.mkdir(parents=True, exist_ok=True)

        # 日志系统
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

    def _save_figure(self, fig: plt.Figure, output_path: str) -> Path:
        """保存图表到文件

        Args:
            fig: matplotlib图表对象
            output_path: 输出路径

        Returns:
            Path: 保存图表的完整路径
        """
        try:
            # 如果提供了基础路径，与输出路径组合
            if self.config.figure_path:
                full_path = self.config.figure_path / output_path
            else:
                full_path = Path(output_path)

            # 确保父目录存在
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # 保存图表
            fig.savefig(
                full_path,
                bbox_inches='tight',
                dpi=self.config.dpi,
                pad_inches=0.1
            )
            plt.close(fig)
            self.logger.info(f"图表已保存至 {full_path}")
            return full_path
        except Exception as e:
            self.logger.error(f"保存图表时出错: {e}")
            raise e

    def plot_shots(self,
                   shots_data: Union[Dict[int, List[Dict[str, Any]]], List[Dict[str, Any]]],
                   title: Optional[str] = None,
                   output_path: Optional[str] = None,
                   shot_outcome: str = "made_only",
                   data_type: str = "team") -> Optional[plt.Figure]:
        """绘制投篮分布图 (通用方法，支持球队和球员)

        Args:
            shots_data: 投篮数据，可以是球队投篮数据字典或球员投篮数据列表
            title: 图表标题
            output_path: 输出路径
            shot_outcome: 投篮结果筛选，"made_only"或"all"
            data_type: 数据类型，"team"或"player"

        Returns:
            Optional[plt.Figure]: 生成的图表对象
        """
        try:
            # 验证参数
            if shot_outcome not in ["made_only", "all"]:
                self.logger.warning(f"无效的shot_outcome值: {shot_outcome}，使用默认值 'made_only'")
                shot_outcome = "made_only"

            if data_type not in ["team", "player"]:
                self.logger.warning(f"无效的data_type值: {data_type}，使用默认值 'team'")
                data_type = "team"

            # 创建球场
            fig, ax = CourtRenderer.draw_court(self.config)

            # 添加图例
            ShotRenderer.add_legend(ax, shot_outcome)

            # 处理投篮数据
            processed_shots = []
            if data_type == "team":
                team_shots = shots_data
                if not team_shots:
                    self.logger.warning("球队投篮数据为空")
                    return None

                processed_shots = ShotProcessor.prepare_team_shots_data(
                    team_shots, shot_outcome, self.config
                )

            elif data_type == "player":
                player_shots = shots_data
                if not player_shots:
                    self.logger.warning("球员投篮数据为空")
                    return None

                processed_shots = ShotProcessor.prepare_player_shots_data(
                    player_shots, shot_outcome, self.config
                )

            # 检查处理后的数据
            if len(processed_shots) < 1:
                self.logger.warning("处理后的投篮数据为空")
                return None

            # 渲染投篮点
            ShotRenderer.render_shots(ax, processed_shots, self.config)

            # 设置标题
            if title:
                if shot_outcome == "all" and "投篮分布图" in title:
                    title = title.replace("投篮分布图", "全部投篮分布图")
                ax.set_title(title, pad=20, fontsize=12 * self.config.scale_factor)

            # 保存图表
            if output_path:
                self._save_figure(fig, output_path)

            return fig

        except Exception as e:
            self.logger.error(f"绘制投篮图时出错: {str(e)}")
            return None

    def plot_player_impact(self,
                          player_shots: List[Dict[str, Any]],
                          assisted_shots: List[Dict[str, Any]],
                          player_id: int,
                          player_stats: Optional[Dict[str, Any]] = None,
                          title: Optional[str] = None,
                          output_path: Optional[str] = None,
                          impact_type: str = "full_impact") -> Optional[plt.Figure]:
        """绘制球员得分影响力图

        Args:
            player_shots: 球员自己的投篮数据
            assisted_shots: 球员助攻的投篮数据
            player_id: 球员ID
            player_stats: 球员统计数据字典，包含姓名、位置、得分等信息
            title: 图表标题
            output_path: 输出路径
            impact_type: 图表类型，"scoring_only"或"full_impact"

        Returns:
            Optional[plt.Figure]: 生成的图表对象
        """
        try:
            # 验证参数
            if impact_type not in ["scoring_only", "full_impact"]:
                self.logger.warning(f"无效的impact_type值: {impact_type}，使用默认值 'full_impact'")
                impact_type = "full_impact"

            # 创建球场
            fig, ax = CourtRenderer.draw_court(self.config)

            # 添加图例
            legend_elements = [
                Line2D([0], [0], marker='o', color='w', markerfacecolor='#3A7711',
                      markeredgecolor='#3A7711', markersize=10, label='个人得分')
            ]

            # 如果是完整影响力图，添加助攻图例
            if impact_type == "full_impact":
                legend_elements.append(
                    Line2D([0], [0], marker='o', color='w', markerfacecolor='#552583',
                          markeredgecolor='#552583', markersize=10, label='助攻队友得分')
                )

            ax.legend(handles=legend_elements, loc='upper right')

            # 处理球员自己的投篮数据
            player_processed_shots = []
            if player_shots:
                for shot in player_shots:
                    if shot.get('shot_result') == 'Made':  # 只显示命中的投篮
                        x = shot.get('x_legacy')
                        y = shot.get('y_legacy')
                        if x is not None and y is not None:
                            player_processed_shots.append({
                                'player_id': player_id,
                                'x': float(x),
                                'y': float(y),
                                'size': self.config.marker_base_size,
                                'alpha': 0.95,
                                'is_made': True,
                                'border_color': self.config.made_shot_color
                            })

            # 如果处理后的数据不为空且数量大于1，计算基于密度的标记大小
            if len(player_processed_shots) > 1:
                coordinates = [(shot['x'], shot['y']) for shot in player_processed_shots]
                marker_sizes = ShotProcessor.calculate_marker_sizes(coordinates, self.config)
                for i, shot in enumerate(player_processed_shots):
                    shot['size'] = marker_sizes[i]

            # 处理助攻数据（仅在full_impact模式下）
            assisted_processed_shots = []
            if impact_type == "full_impact" and assisted_shots:
                for shot in assisted_shots:
                    x = shot.get('x')
                    y = shot.get('y')
                    shooter_id = shot.get('shooter_id')
                    if x is not None and y is not None and shooter_id:
                        assisted_processed_shots.append({
                            'player_id': int(shooter_id),
                            'x': float(x),
                            'y': float(y),
                            'size': self.config.marker_base_size,
                            'alpha': 0.95,
                            'is_made': True,
                            'border_color': '#552583'  # 湖人紫色
                        })

            # 如果助攻数据不为空且数量大于1，计算基于密度的标记大小
            if len(assisted_processed_shots) > 1:
                coordinates = [(shot['x'], shot['y']) for shot in assisted_processed_shots]
                marker_sizes = ShotProcessor.calculate_marker_sizes(coordinates, self.config)
                for i, shot in enumerate(assisted_processed_shots):
                    shot['size'] = marker_sizes[i]

            # 渲染所有投篮点
            for shot in player_processed_shots:
                ShotRenderer.add_shot_marker(ax, shot, self.config)

            for shot in assisted_processed_shots:
                ShotRenderer.add_shot_marker(ax, shot, self.config)

            # 根据impact_type调整标题
            if title:
                if impact_type == "scoring_only" and "影响力图" in title:
                    title = title.replace("影响力图", "投篮分布图")
                ax.set_title(title, pad=20, fontsize=12 * self.config.scale_factor)

            # 添加球员信息框（如果提供了球员数据）
            if player_stats is None:
                # 如果没有提供球员数据，创建一个简单的数据对象
                player_stats = {'name': f'球员 #{player_id}'}

                # 添加一些基本统计
                if player_shots:
                    made_shots = sum(1 for shot in player_shots if shot.get('shot_result') == 'Made')
                    total_shots = len(player_shots)
                    if total_shots > 0:
                        player_stats['fg_pct'] = made_shots / total_shots
                        player_stats['points'] = made_shots * 2  # 简化计算，不区分三分

                if assisted_shots and impact_type == "full_impact":
                    player_stats['assists'] = len(assisted_shots)

            # 添加球员信息框
            ShotRenderer.add_player_info_box(ax, player_id, player_stats, self.config)

            # 保存图表
            if output_path:
                self._save_figure(fig, output_path)

            return fig

        except Exception as e:
            self.logger.error(f"绘制球员影响力图时出错: {str(e)}")
            return None

    # ==== 从NBAService下放的业务方法 ====

    def generate_player_scoring_impact_charts(self,
                                             game: Game,
                                             player_id: int,
                                             player_name: str,
                                             output_dir: Optional[Path] = None,
                                             force_reprocess: bool = False,
                                             impact_type: str = "full_impact") -> Dict[str, Path]:
        """生成球员得分影响力图

        展示球员自己的投篮和由其助攻的队友投篮，以球员头像方式显示。

        Args:
            game: 比赛对象
            player_id: 球员ID
            player_name: 球员名称
            output_dir: 输出目录，默认使用配置中的图片目录
            force_reprocess: 是否强制重新处理已存在的文件
            impact_type: 图表类型，可选 "scoring_only"(仅显示球员自己的投篮)
                        或 "full_impact"(同时显示球员投篮和助攻队友投篮)

        Returns:
            Dict[str, Path]: 图表路径字典，键包含"impact_chart"或"scoring_chart"
        """
        result = {}

        try:
            # 设置输出目录
            if not output_dir:
                output_dir = self.default_output_dir
                output_dir.mkdir(parents=True, exist_ok=True)

            # 收集输入数据
            chart_data = self._collect_player_chart_data(
                game=game,
                player_id=player_id,
                player_name=player_name,
                impact_type=impact_type
            )

            if not chart_data["success"]:
                self.logger.error(f"球员 {player_name} (ID={player_id}) 没有投篮或助攻数据")
                return result

            # 准备输出路径和文件名
            output_path = self._prepare_player_chart_output(
                player_id=player_id,
                game=game,
                output_dir=output_dir,
                impact_type=impact_type,
                force_reprocess=force_reprocess
            )

            if not output_path["success"]:
                result[output_path["key"]] = output_path["path"]  # 返回已存在的图表
                return result

            # 调用图表绘制方法
            fig = self.plot_player_impact(
                player_shots=chart_data["player_shots"],
                assisted_shots=chart_data["assisted_shots"],
                player_id=player_id,
                title=chart_data["title"],
                output_path=str(output_path["path"]),
                impact_type=impact_type
            )

            if fig:
                self.logger.info(f"球员{impact_type}图已生成: {output_path['path']}")
                result[output_path["key"]] = output_path["path"]
            else:
                self.logger.error(f"球员{impact_type}图生成失败")

            return result

        except Exception as e:
            self.logger.error(f"生成球员图表失败: {e}", exc_info=True)
            return result

    def generate_shot_charts(self,
                            game: Game,
                            team_id: Optional[int] = None,
                            player_id: Optional[int] = None,
                            team_name: Optional[str] = None,
                            player_name: Optional[str] = None,
                            chart_type: str = "both",  # "team", "player", "both"
                            output_dir: Optional[Path] = None,
                            force_reprocess: bool = False,
                            shot_outcome: str = "made_only",  # "made_only", "all"
                            impact_type: str = "full_impact") -> Dict[str, Path]:
        """生成投篮分布图

        Args:
            game: 比赛对象
            team_id: 球队ID
            player_id: 球员ID
            team_name: 球队名称
            player_name: 球员名称
            chart_type: 生成图表类型，"team"、"player"或"both"
            output_dir: 输出目录
            force_reprocess: 是否强制重新处理
            shot_outcome: 投篮结果筛选，"made_only"或"all"
            impact_type: 影响力图类型，"scoring_only"或"full_impact"

        Returns:
            Dict[str, Path]: 生成图表的路径字典
        """
        chart_paths = {}

        try:
            # 设置输出目录
            if not output_dir:
                output_dir = self.default_output_dir
                output_dir.mkdir(parents=True, exist_ok=True)

            # 1. 生成球员投篮图
            if chart_type in ["player", "both"] and player_id:
                player_chart = self._generate_player_chart(
                    player_id=player_id,
                    player_name=player_name,
                    game=game,
                    output_dir=output_dir,
                    shot_outcome=shot_outcome,
                    impact_type=impact_type,
                    force_reprocess=force_reprocess
                )
                if player_chart:
                    chart_paths["player_chart"] = player_chart

            # 2. 生成球队投篮图
            if chart_type in ["team", "both"] and team_id:
                team_chart = self._generate_team_chart(
                    team_id=team_id,
                    team_name=team_name,
                    game=game,
                    output_dir=output_dir,
                    shot_outcome=shot_outcome,
                    force_reprocess=force_reprocess
                )
                if team_chart:
                    chart_paths["team_chart"] = team_chart

            return chart_paths

        except Exception as e:
            self.logger.error(f"生成投篮图失败: {e}", exc_info=True)
            return chart_paths

    # ==== 辅助方法 ====

    def _collect_player_chart_data(self, game: Game, player_id: int, player_name: str, impact_type: str) -> Dict[str, Any]:
        """收集球员图表所需数据

        Args:
            game: 比赛对象
            player_id: 球员ID
            player_name: 球员名称
            impact_type: 图表类型

        Returns:
            Dict[str, Any]: 包含图表所需数据的字典
        """
        result = {"success": False}

        # 1. 获取球员自己的投篮数据
        player_shots = game.get_shot_data(player_id)
        if not player_shots:
            self.logger.warning(f"未找到{player_name}的投篮数据")
            player_shots = []

        # 2. 获取由球员助攻的队友投篮数据（仅在full_impact模式下需要）
        assisted_shots = []
        if impact_type == "full_impact":
            assisted_shots = game.get_assisted_shot_data(player_id)
            if not assisted_shots:
                self.logger.warning(f"未找到{player_name}的助攻投篮数据")

        # 3. 如果没有投篮数据，返回空结果
        if not player_shots:
            if impact_type == "full_impact":
                if not assisted_shots:
                    self.logger.error(f"{player_name}没有投篮或助攻数据")
                    return result
                else:  # 有助攻数据但没有投篮数据
                    self.logger.warning(f"{player_name}没有投篮数据，但有助攻数据")
                    # 继续处理，因为有助攻数据
            elif impact_type == "scoring_only":
                self.logger.error(f"{player_name}没有投篮数据")
                return result

        # 4. 准备标题
        formatted_date = game.game_data.game_time_beijing.strftime("%Y年%m月%d日")

        # 根据impact_type选择合适的标题
        if impact_type == "full_impact":
            title = f"{player_name} 得分影响力图\n{formatted_date}"
        else:  # scoring_only
            title = f"{player_name} 投篮分布图\n{formatted_date}"

        result.update({
            "success": True,
            "player_shots": player_shots,
            "assisted_shots": assisted_shots,
            "title": title
        })

        return result

    def _prepare_player_chart_output(self, player_id: int, game: Game, output_dir: Path,
                                   impact_type: str, force_reprocess: bool) -> Dict[str, Any]:
        """准备球员图表输出路径

        Args:
            player_id: 球员ID
            game: 比赛对象
            output_dir: 输出目录
            impact_type: 图表类型
            force_reprocess: 是否强制重新处理

        Returns:
            Dict[str, Any]: 包含输出路径和结果键的字典，以及是否需要重新处理的标志
        """
        # 根据impact_type选择合适的文件名
        if impact_type == "full_impact":
            output_filename = f"player_impact_{game.game_data.game_id}_{player_id}.png"
            result_key = "impact_chart"
        else:  # scoring_only
            output_filename = f"player_scoring_{game.game_data.game_id}_{player_id}.png"
            result_key = "scoring_chart"

        output_path = output_dir / output_filename

        # 检查是否已存在
        if not force_reprocess and output_path.exists():
            self.logger.info(f"检测到已存在的处理结果: {output_path}")
            return {
                "success": False,  # 不需要重新处理
                "path": output_path,
                "key": result_key
            }

        return {
            "success": True,  # 需要处理
            "path": output_path,
            "key": result_key
        }

    def _generate_player_chart(self,
                              player_id: int,
                              player_name: str,
                              game: Game,
                              output_dir: Optional[Path] = None,
                              shot_outcome: str = "made_only",
                              impact_type: str = "full_impact",
                              force_reprocess: bool = False) -> Optional[Path]:
        """生成球员投篮图的辅助方法

        Args:
            player_id: 球员ID
            player_name: 球员名称
            game: 比赛对象
            output_dir: 输出目录
            shot_outcome: 投篮结果筛选
            impact_type: 图表类型
            force_reprocess: 是否强制重新处理

        Returns:
            Optional[Path]: 生成图表的路径
        """
        self.logger.info(f"正在生成 {player_name} 的投篮图")

        # 选择生成方法：如果是full_impact则使用球员得分影响力图
        if impact_type == "full_impact":
            impact_charts = self.generate_player_scoring_impact_charts(
                game=game,
                player_id=player_id,
                player_name=player_name,
                output_dir=output_dir,
                force_reprocess=force_reprocess,
                impact_type=impact_type
            )
            if impact_charts and "impact_chart" in impact_charts:
                self.logger.info(f"球员得分影响力图已生成: {impact_charts['impact_chart']}")
                return impact_charts["impact_chart"]
            return None

        # 球员单独投篮图生成逻辑
        # 获取球员投篮数据
        shots = game.get_shot_data(player_id)
        if not shots:
            self.logger.warning(f"未找到{player_name}的投篮数据")
            return None

        # 准备输出路径和文件名
        formatted_date = game.game_data.game_time_beijing.strftime("%Y年%m月%d日")
        title_prefix = "所有" if shot_outcome == "all" else ""
        title = f"{player_name} {title_prefix}投篮分布图\n{formatted_date}"

        filename_prefix = "all_shots" if shot_outcome == "all" else "scoring"
        output_filename = f"{filename_prefix}_{game.game_data.game_id}_{player_id}.png"
        output_path = (output_dir or self.default_output_dir) / output_filename

        # 检查是否已存在
        if not force_reprocess and output_path.exists():
            self.logger.info(f"检测到已存在的处理结果: {output_path}")
            return output_path

        # 使用plot_shots方法绘制球员投篮图
        fig = self.plot_shots(
            shots_data=shots,
            title=title,
            output_path=str(output_path),
            shot_outcome=shot_outcome,
            data_type="player"
        )

        if fig:
            self.logger.info(f"球员投篮图已生成: {output_path}")
            return output_path
        else:
            self.logger.error("球员投篮图生成失败")
            return None

    def _generate_team_chart(self,
                            team_id: int,
                            team_name: str,
                            game: Game,
                            output_dir: Optional[Path] = None,
                            shot_outcome: str = "made_only",
                            force_reprocess: bool = False) -> Optional[Path]:
        """生成球队投篮图的辅助方法

        Args:
            team_id: 球队ID
            team_name: 球队名称
            game: 比赛对象
            output_dir: 输出目录
            shot_outcome: 投篮结果筛选
            force_reprocess: 是否强制重新处理

        Returns:
            Optional[Path]: 生成图表的路径
        """
        self.logger.info(f"正在生成 {team_name} 的球队投篮图")

        # 准备输出路径和文件名
        formatted_date = game.game_data.game_time_beijing.strftime("%Y年%m月%d日")
        title_prefix = "所有" if shot_outcome == "all" else ""
        title = f"{team_name} {title_prefix}球队投篮分布图\n{formatted_date}"

        filename_prefix = "all_shots" if shot_outcome == "all" else "team_shots"
        output_filename = f"{filename_prefix}_{game.game_data.game_id}_{team_id}.png"
        output_path = (output_dir or self.default_output_dir) / output_filename

        # 检查是否已存在
        if not force_reprocess and output_path.exists():
            self.logger.info(f"检测到已存在的处理结果: {output_path}")
            return output_path

        # 获取球队投篮数据
        team_shots = game.get_team_shot_data(team_id)
        if not team_shots:
            self.logger.warning(f"未找到{team_name}的投篮数据")
            return None

        # 调用图表服务绘制球队投篮图
        fig = self.plot_shots(
            shots_data=team_shots,
            title=title,
            output_path=str(output_path),
            shot_outcome=shot_outcome,
            data_type="team"
        )

        if fig:
            self.logger.info(f"球队投篮图已生成: {output_path}")
            return output_path
        else:
            self.logger.error("球队投篮图生成失败")
            return None

    def clear_cache(self) -> None:
        """清理图表服务缓存"""
        # 当前实现下没有需要特别清理的缓存
        pass

    def close(self) -> None:
        """关闭图表服务资源"""
        # 关闭所有plt图表
        plt.close('all')
        self.logger.info("图表服务资源已清理")