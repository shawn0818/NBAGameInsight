#nba/visualization/shot_charts_render.py
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union, List, cast
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
from matplotlib.lines import Line2D
from pathlib import Path
import math

# 导入通用的球场绘制工具
from nba.visualization.court_drawer import draw_court, CourtConfig, draw_full_court_horizontal
from utils.logger_handler import AppLogger
from nba.visualization.data_preparer import (
    ShotMarker, LegendItem, InfoBoxData,
    prepare_shot_markers, prepare_legend_spec, prepare_info_box_data,
    format_player_stats, transform_to_full_court_coordinates
)
from config import NBAConfig


# =============== 配置对象 ===============

@dataclass
class ChartConfig:
    """图表服务完整配置"""
    # 基础球场配置
    dpi: int = 350
    scale_factor: float = 1.5
    court_bg_color: str = '#F8F8F8'
    paint_color: str = '#FDB927'
    paint_alpha: float = 0.3
    court_line_color: str = 'k'

    # 图表特定配置
    figure_path: Optional[Path] = None

    # 标记相关设置
    marker_base_size: float = 50
    marker_min_size: float = 20
    marker_border_width: float = 1.0
    ideal_marker_distance: float = 25.0

    # 特定颜色设置
    default_made_shot_color: str = '#3A7711'
    default_missed_shot_color: str = '#C9082A'
    default_assist_color: str = '#552583'

    # 信息框默认创建者信息
    default_creator_info: str = 'Created by YourAppName'

    def get_court_config(self) -> CourtConfig:
        """获取球场配置子集"""
        return CourtConfig(
            dpi=self.dpi,
            scale_factor=self.scale_factor,
            court_bg_color=self.court_bg_color,
            paint_color=self.paint_color,
            paint_alpha=self.paint_alpha,
            court_line_color=self.court_line_color
        )


# =============== 渲染器类 ===============

class ChartRenderer:
    """图表渲染器 - 处理纯渲染逻辑"""

    def __init__(self, config: ChartConfig):
        """初始化渲染器"""
        self.config = config
        self.logger = AppLogger.get_logger(f"{__name__}.Renderer", app_name='nba')

    def render_default_marker(self, ax: plt.Axes, marker_data: ShotMarker) -> None:
        """
        渲染默认标记 (圆圈, 叉号等)
        """
        x = marker_data['x']
        y = marker_data['y']
        size_mpl = marker_data.get('size', self.config.marker_base_size)
        color = marker_data.get('color', '#000000')
        alpha = marker_data.get('alpha', 0.8)
        is_made = marker_data.get('is_made', True)
        marker_symbol = marker_data.get('marker_symbol', 'o' if is_made else 'x')
        border_color = marker_data.get('border_color', 'none')
        border_width = marker_data.get('border_width', 0)

        ax.scatter(x, y, s=size_mpl, c=color, alpha=alpha, marker=marker_symbol,
                   edgecolors=border_color,
                   linewidths=border_width,
                   zorder=5)

    def render_avatar_marker(self, ax: plt.Axes, marker_data: ShotMarker) -> None:
        """
        渲染头像标记
        """
        x = marker_data['x']
        y = marker_data['y']
        avatar_image = marker_data.get('avatar_image')
        marker_data_diameter = marker_data.get('size', 30)
        alpha = marker_data.get('alpha', 0.95)
        border_color = marker_data.get('border_color', self.config.default_made_shot_color)
        border_width = marker_data.get('border_width', self.config.marker_border_width)

        if not avatar_image:
            self.logger.warning(f"头像标记缺少 'avatar_image' 数据，跳过渲染 at ({x},{y})")
            return

        # 计算位置和大小
        left = x - marker_data_diameter / 2
        bottom = y - marker_data_diameter / 2
        width = marker_data_diameter
        height = marker_data_diameter

        try:
            # 创建子图区域用于显示头像
            marker_ax = ax.inset_axes(
                (left, bottom, width, height),
                transform=ax.transData,
                zorder=10
            )

            # 显示头像
            marker_ax.imshow(avatar_image, alpha=alpha)
            marker_ax.axis('off')

            # 添加圆形边框
            border_circle = Circle((x, y), marker_data_diameter / 2,
                                   fill=False, edgecolor=border_color,
                                   linewidth=border_width,
                                   transform=ax.transData,
                                   zorder=11)
            ax.add_patch(border_circle)

        except Exception as e:
            self.logger.error(f"渲染头像标记时出错 at ({x},{y}): {e}", exc_info=True)

    def add_custom_legend(self, ax: plt.Axes, legend_spec: List[LegendItem]) -> None:
        """
        添加自定义图例
        """
        legend_elements = []
        legend_kwargs = {}
        legend_location = 'upper right'
        bbox_to_anchor = None
        ncol = 1

        for item in legend_spec:
            # 提取基本图例属性
            label = item.get('label', '')
            color = item.get('color', '#000000')
            marker = item.get('marker', 'o')
            markersize = item.get('markersize', 8)
            edgecolor = item.get('edgecolor', color)
            alpha = item.get('alpha', 1.0)

            # 图例定位相关属性
            if 'location' in item:
                legend_location = item['location']
            if 'bbox_to_anchor' in item:
                bbox_to_anchor = item['bbox_to_anchor']
            if 'ncol' in item:
                ncol = item['ncol']

            legend_elements.append(
                Line2D([0], [0], marker=marker, color='w',
                       label=label,
                       markerfacecolor=color,
                       markersize=markersize,
                       markeredgecolor=edgecolor,
                       alpha=alpha,
                       linestyle='None')
            )

        if legend_elements:
            legend_kwargs = {'loc': legend_location, 'fontsize': 8 * self.config.scale_factor}
            if bbox_to_anchor is not None:
                legend_kwargs['bbox_to_anchor'] = bbox_to_anchor
            if ncol > 1:
                legend_kwargs['ncol'] = ncol

            ax.legend(handles=legend_elements, **legend_kwargs)

    def add_info_box(self, fig: plt.Figure, ax: plt.Axes, info_data: InfoBoxData) -> None:
        """
        添加信息框
        """
        try:
            name = info_data.get('name', '图表信息')
            stats = info_data.get('stats', {})
            avatar_image = info_data.get('avatar_image')
            creator_info = info_data.get('creator_info', self.config.default_creator_info)

            # 计算信息框位置和大小
            main_ax_pos = ax.get_position()
            box_height_ratio = 0.12
            bottom_margin_ratio = 0.02
            box_bottom = bottom_margin_ratio
            box_left = main_ax_pos.x0
            box_width = main_ax_pos.width

            # 创建信息框子图
            box_ax = fig.add_axes([box_left, box_bottom, box_width, box_height_ratio])

            # 绘制背景和边框
            box_rect = Rectangle(
                xy=(0, 0), width=1, height=1,
                facecolor='#F0F0F0',
                edgecolor='#AAAAAA',
                linewidth=1,
                transform=box_ax.transAxes
            )
            box_ax.add_patch(box_rect)
            box_ax.axis('off')

            # 添加头像
            has_avatar = avatar_image is not None
            text_start_x = 0.05
            if has_avatar:
                avatar_width_ratio = 0.18
                avatar_height_ratio = 0.8
                avatar_left = 0.03
                avatar_bottom = (1 - avatar_height_ratio) / 2

                # 创建头像子图
                avatar_ax = box_ax.inset_axes(
                    [avatar_left, avatar_bottom, avatar_width_ratio, avatar_height_ratio],
                    transform=box_ax.transAxes
                )
                avatar_ax.imshow(avatar_image)
                avatar_ax.axis('off')
                text_start_x = avatar_left + avatar_width_ratio + 0.03

            # 添加球员名称
            box_ax.text(
                text_start_x, 0.75, name,
                fontsize=11 * self.config.scale_factor, weight='bold',
                transform=box_ax.transAxes, verticalalignment='top'
            )

            # 格式化统计数据(最多分两行显示)
            stats_items = list(stats.items())
            line1_stats = ""
            line2_stats = ""
            max_items_line1 = min(4, math.ceil(len(stats_items) / 2))

            for i, (key, value) in enumerate(stats_items):
                stat_str = f"{key}: {value}  "
                if i < max_items_line1:
                    line1_stats += stat_str
                else:
                    line2_stats += stat_str

            if line1_stats:
                box_ax.text(
                    text_start_x, 0.50, line1_stats.rstrip(),
                    fontsize=9 * self.config.scale_factor,
                    transform=box_ax.transAxes, verticalalignment='top'
                )
            if line2_stats:
                box_ax.text(
                    text_start_x, 0.25, line2_stats.rstrip(),
                    fontsize=9 * self.config.scale_factor,
                    transform=box_ax.transAxes, verticalalignment='top'
                )

            # 添加创建者信息
            box_ax.text(
                0.98, 0.05, creator_info,
                fontsize=7 * self.config.scale_factor, color='gray',
                horizontalalignment='right',
                transform=box_ax.transAxes, verticalalignment='bottom'
            )

            # 调整主轴位置
            main_ax_pos = ax.get_position()
            new_bottom = box_height_ratio + bottom_margin_ratio * 2
            new_height = main_ax_pos.height - (new_bottom - main_ax_pos.y0)
            ax.set_position([main_ax_pos.x0, new_bottom, main_ax_pos.width, new_height])

        except Exception as e:
            self.logger.error(f"添加信息框时出错: {str(e)}", exc_info=True)


# =============== 图表管理器 ===============

class ChartManager:
    """图表管理器 - 处理文件保存和资源管理"""

    def __init__(self, config: ChartConfig):
        """初始化图表管理器"""
        self.config = config
        self.default_output_dir = config.figure_path or NBAConfig.PATHS.PICTURES_DIR
        self.default_output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = AppLogger.get_logger(f"{__name__}.Manager", app_name='nba')

    def save_figure(self, fig: plt.Figure, output_path: Union[str, Path]) -> Path:
        """保存图表到文件"""
        try:
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
            self.logger.info(f"图表已保存至 {full_path}")
            return full_path
        except Exception as e:
            self.logger.error(f"保存图表时出错: {e}", exc_info=True)
            raise
        finally:
            # 释放资源
            if fig is not None and plt.fignum_exists(fig.number):
                plt.close(fig)

    def clear_resources(self) -> None:
        """清理图表资源"""
        # 关闭所有matplotlib图形
        plt.close('all')
        self.logger.info("已清理所有图表资源")


# =============== 主服务类 ===============

class ShotChartsRenderer:
    """
    NBA比赛数据可视化服务 - 增强版
    专注于根据预处理的数据渲染图表，不包含数据获取或处理逻辑。
    """

    def __init__(self, config: Optional[ChartConfig] = None) -> None:
        """初始化服务"""
        self.config = config or ChartConfig()
        self.renderer = ChartRenderer(self.config)
        self.manager = ChartManager(self.config)
        self.logger = AppLogger.get_logger(__name__, app_name='nba')
        self.default_output_dir = self.config.figure_path or NBAConfig.PATHS.PICTURES_DIR
        self.default_output_dir.mkdir(parents=True, exist_ok=True)

    def render_shot_chart(
            self,
            shot_markers: List[ShotMarker],
            output_path: Union[str, Path],
            chart_title: Optional[str] = None,
            legend_spec: Optional[List[LegendItem]] = None,
            info_box_data: Optional[InfoBoxData] = None,
            court_config_override: Optional[CourtConfig] = None
    ) -> Optional[Path]:
        """
        渲染一个包含投篮标记的NBA半场图。

        此方法是纯粹的渲染器，接收所有绘图所需的、已处理好的数据。

        Args:
            shot_markers: 投篮标记列表，每个标记必须包含x/y坐标
            output_path: 输出路径
            chart_title: 图表标题
            legend_spec: 图例规格
            info_box_data: 信息框数据
            court_config_override: 球场配置覆盖

        Returns:
            Optional[Path]: 保存的图表路径
        """
        fig = None
        try:
            # 1. 验证输入数据
            if not shot_markers:
                self.logger.warning("shot_markers 列表为空，图表将不包含投篮点")

            # 2. 确定球场配置
            court_config = court_config_override or self.config.get_court_config()

            # 3. 绘制基础球场
            fig, ax = draw_court(court_config)

            # 4. 渲染投篮标记
            for marker_data in shot_markers:
                # 确保必要数据存在
                if 'x' not in marker_data or 'y' not in marker_data:
                    self.logger.warning(f"标记数据缺少坐标，已跳过")
                    continue

                marker_type = marker_data.get('marker_type', 'default')
                if marker_type == 'avatar':
                    self.renderer.render_avatar_marker(ax, marker_data)
                else:  # 'default'
                    self.renderer.render_default_marker(ax, marker_data)

            # 5. 添加图例
            if legend_spec:
                self.renderer.add_custom_legend(ax, legend_spec)

            # 6. 添加标题
            if chart_title:
                ax.set_title(chart_title, pad=20, fontsize=12 * self.config.scale_factor)

            # 7. 添加信息框
            if info_box_data:
                self.renderer.add_info_box(fig, ax, info_box_data)

            # 8. 保存图表
            return self.manager.save_figure(fig, output_path)

        except Exception as e:
            self.logger.error(f"渲染半场投篮图时出错: {e}", exc_info=True)
            if fig is not None and plt.fignum_exists(fig.number):
                plt.close(fig)
            return None

    def render_full_court_shot_chart(
            self,
            shot_markers: List[ShotMarker],
            output_path: Union[str, Path],
            chart_title: Optional[str] = None,
            legend_spec: Optional[List[LegendItem]] = None,
            court_config_override: Optional[CourtConfig] = None
    ) -> Optional[Path]:
        """
        渲染一个包含投篮标记的NBA全场图 (横向)。

        Args:
            shot_markers: 投篮标记列表，每个标记必须包含x/y坐标
            output_path: 输出路径
            chart_title: 图表标题
            legend_spec: 图例规格
            court_config_override: 球场配置覆盖

        Returns:
            Optional[Path]: 保存的图表路径
        """
        fig = None
        try:
            # 1. 验证输入数据
            if not shot_markers:
                self.logger.warning("shot_markers 列表为空，图表将不包含投篮点")

            # 2. 确定球场配置
            if court_config_override:
                court_config = court_config_override
            else:
                # 使用默认配置，但调整scale_factor
                court_config = self.config.get_court_config()
                court_config.scale_factor *= 0.8  # 全场图稍微缩小

            # 3. 绘制基础球场 (全场横向)
            fig, ax = draw_full_court_horizontal(court_config)

            # 4. 渲染投篮标记
            for marker_data in shot_markers:
                if 'x' not in marker_data or 'y' not in marker_data:
                    self.logger.warning(f"标记数据缺少坐标，已跳过")
                    continue

                # 全场图通常只用默认标记
                marker_type = marker_data.get('marker_type', 'default')
                if marker_type == 'default':
                    self.renderer.render_default_marker(ax, marker_data)
                else:
                    # 对于全场图，我们也支持头像标记，但可能需要调整大小
                    # 复制一份数据以调整大小
                    adjusted_marker = dict(marker_data)
                    # 如果提供了size，缩小一点以适应全场视图
                    if 'size' in adjusted_marker:
                        adjusted_marker['size'] = adjusted_marker['size'] * 0.8

                    if marker_type == 'avatar':
                        self.renderer.render_avatar_marker(ax, cast(ShotMarker, adjusted_marker))
                    else:
                        self.renderer.render_default_marker(ax, cast(ShotMarker, adjusted_marker))

            # 5. 添加图例
            if legend_spec:
                # 调整图例位置以适应全场图
                adjusted_legend_spec = []
                has_location_specified = any('location' in item for item in legend_spec)

                if not has_location_specified:
                    # 添加默认的全场图图例位置
                    for item in legend_spec:
                        new_item = dict(item)
                        new_item['location'] = 'upper center'
                        new_item['bbox_to_anchor'] = (0.5, 1.05)
                        new_item['ncol'] = min(4, len(legend_spec))
                        adjusted_legend_spec.append(cast(LegendItem, new_item))
                else:
                    adjusted_legend_spec = legend_spec

                self.renderer.add_custom_legend(ax, adjusted_legend_spec)

            # 6. 添加标题
            if chart_title:
                ax.set_title(chart_title, pad=15, fontsize=10 * court_config.scale_factor)

            # 7. 保存图表
            return self.manager.save_figure(fig, output_path)

        except Exception as e:
            self.logger.error(f"渲染全场投篮图时出错: {e}", exc_info=True)
            if fig is not None and plt.fignum_exists(fig.number):
                plt.close(fig)
            return None

    def validate_shot_markers(self, markers: List[Dict[str, Any]]) -> List[ShotMarker]:
        """
        验证和转换投篮标记数据

        Args:
            markers: 原始标记数据列表

        Returns:
            List[ShotMarker]: 验证后的标记数据
        """
        valid_markers = []

        for i, marker in enumerate(markers):
            # 检查必要字段
            if 'x' not in marker or 'y' not in marker:
                self.logger.warning(f"标记 #{i} 缺少必要的坐标数据，已跳过")
                continue

            try:
                # 确保坐标是浮点数
                x = float(marker['x'])
                y = float(marker['y'])

                # 创建新的验证过的标记
                valid_marker: ShotMarker = {
                    'x': x,
                    'y': y
                }

                # 复制其他有效字段
                for key in ['marker_type', 'color', 'size', 'alpha', 'is_made',
                            'marker_symbol', 'border_color', 'border_width', 'avatar_image']:
                    if key in marker:
                        valid_marker[key] = marker[key]

                valid_markers.append(valid_marker)
            except (ValueError, TypeError) as e:
                self.logger.warning(f"标记 #{i} 坐标转换失败: {e}")
                continue

        return valid_markers

    # 下面是基于我们讨论实现的新方法，直接使用Game模型数据

    def generate_shot_charts(
            self,
            game: Any,  # Game模型对象
            team_id: Optional[int] = None,
            player_id: Optional[int] = None,
            team_name: Optional[str] = None,
            player_name: Optional[str] = None,
            chart_type: str = "both",  # "team", "player", "both"
            output_dir: Optional[Path] = None,
            force_reprocess: bool = False,
            shot_outcome: str = "made_only"  # "made_only", "all"
    ) -> Dict[str, Path]:
        """
        生成半场投篮分布图

        Args:
            game: 比赛数据对象
            team_id: 球队ID
            player_id: 球员ID
            team_name: 球队名称（用于显示）
            player_name: 球员名称（用于显示）
            chart_type: 图表类型，可选 "team", "player", "both"
            output_dir: 输出目录
            force_reprocess: 是否强制重新处理
            shot_outcome: 投篮结果筛选，可选 "made_only", "all"

        Returns:
            Dict[str, Path]: 图表路径字典
        """
        result_paths = {}
        output_dir = output_dir or self.default_output_dir

        try:
            # 生成团队投篮图
            if chart_type in ["team", "both"] and team_id:
                team_chart_path = self._generate_team_shot_chart(
                    game=game,
                    team_id=team_id,
                    team_name=team_name or f"Team {team_id}",
                    output_dir=output_dir,
                    force_reprocess=force_reprocess,
                    shot_outcome=shot_outcome
                )
                if team_chart_path:
                    result_paths["team_chart"] = team_chart_path

            # 生成球员投篮图
            if chart_type in ["player", "both"] and player_id:
                player_chart_path = self._generate_player_shot_chart(
                    game=game,
                    player_id=player_id,
                    player_name=player_name or f"Player {player_id}",
                    output_dir=output_dir,
                    force_reprocess=force_reprocess,
                    shot_outcome=shot_outcome
                )
                if player_chart_path:
                    result_paths["player_chart"] = player_chart_path

            return result_paths
        except Exception as e:
            self.logger.error(f"生成投篮图表失败: {e}", exc_info=True)
            return {}

    def _generate_team_shot_chart(
            self,
            game: Any,  # Game模型对象
            team_id: int,
            team_name: str,
            output_dir: Optional[Path] = None,
            force_reprocess: bool = False,
            shot_outcome: str = "made_only"
    ) -> Optional[Path]:
        """
        生成球队投篮图

        Args:
            game: 比赛数据对象
            team_id: 球队ID
            team_name: 球队名称
            output_dir: 输出目录
            force_reprocess: 是否强制重新处理
            shot_outcome: 投篮结果筛选

        Returns:
            Optional[Path]: 保存的图表路径
        """
        try:
            # 1. 确定输出路径
            output_dir = output_dir or self.default_output_dir
            output_filename = f"{team_name}_shot_chart.png"
            output_path = output_dir / output_filename

            # 检查文件是否已存在且不需要重新处理
            if output_path.exists() and not force_reprocess:
                self.logger.info(f"文件 {output_path} 已存在，跳过处理")
                return output_path

            # 2. 直接从Game模型获取球队投篮数据
            team_shots_dict = game.get_team_shot_data(team_id)

            # 将字典转换为列表格式
            all_team_shots = []
            for player_shots in team_shots_dict.values():
                all_team_shots.extend(player_shots)

            if not all_team_shots:
                self.logger.warning(f"球队 {team_id} 没有投篮数据")
                return None

            # 3. 使用chart_data_preparer准备标记数据
            shot_markers = prepare_shot_markers(
                all_team_shots,
                self.config.__dict__,
                shot_outcome=shot_outcome
            )

            # 4. 准备图例
            legend_spec = prepare_legend_spec(
                shot_outcome=shot_outcome,
                chart_type="team"
            )

            # 5. 设置标题
            opponent_name = ""
            if hasattr(game.game_data, 'home_team') and hasattr(game.game_data, 'away_team'):
                home_team = game.game_data.home_team
                away_team = game.game_data.away_team

                if home_team.team_id == team_id:
                    opponent_name = away_team.team_name
                else:
                    opponent_name = home_team.team_name

            chart_title = f"{team_name} 投篮分布" + (f" vs {opponent_name}" if opponent_name else "")

            # 6. 调用渲染器生成图表
            return self.render_shot_chart(
                shot_markers=shot_markers,
                output_path=output_path,
                chart_title=chart_title,
                legend_spec=legend_spec
            )

        except Exception as e:
            self.logger.error(f"生成球队投篮图失败: {e}", exc_info=True)
            return None

    def _generate_player_shot_chart(
            self,
            game: Any,  # Game模型对象
            player_id: int,
            player_name: str,
            output_dir: Optional[Path] = None,
            force_reprocess: bool = False,
            shot_outcome: str = "made_only"
    ) -> Optional[Path]:
        """
        生成球员投篮图

        Args:
            game: 比赛数据对象
            player_id: 球员ID
            player_name: 球员名称
            output_dir: 输出目录
            force_reprocess: 是否强制重新处理
            shot_outcome: 投篮结果筛选

        Returns:
            Optional[Path]: 保存的图表路径
        """
        try:
            # 1. 确定输出路径
            output_dir = output_dir or self.default_output_dir
            output_filename = f"{player_name}_shot_chart.png"
            output_path = output_dir / output_filename

            # 检查文件是否已存在且不需要重新处理
            if output_path.exists() and not force_reprocess:
                self.logger.info(f"文件 {output_path} 已存在，跳过处理")
                return output_path

            # 2. 直接从Game模型获取球员投篮数据
            player_shots = game.get_shot_data(player_id)

            if not player_shots:
                self.logger.warning(f"球员 {player_id} 没有投篮数据")
                return None

            # 3. 使用chart_data_preparer准备标记数据
            shot_markers = prepare_shot_markers(
                player_shots,
                self.config.__dict__,
                shot_outcome=shot_outcome
            )

            # 4. 准备图例
            legend_spec = prepare_legend_spec(
                shot_outcome=shot_outcome,
                chart_type="player"
            )

            # 5. 尝试获取球员详细信息，准备信息框
            player_info = None
            team_name = ""

            # 查找球员信息
            for team_type in ["home_team", "away_team"]:
                if hasattr(game.game_data, team_type):
                    team = getattr(game.game_data, team_type)
                    if hasattr(team, "players"):
                        for player in team.players:
                            if player.person_id == player_id:
                                player_info = player
                                team_name = team.team_name
                                break
                if player_info:
                    break

            # 准备信息框数据
            info_box_data = None
            if player_info:
                # 获取统计数据
                stats = {}
                if hasattr(player_info, "statistics"):
                    stats = format_player_stats(player_info.statistics.__dict__)

                # 获取位置信息
                position = getattr(player_info, "position", "")
                if position and "position" not in stats:
                    stats["位置"] = position

                # 创建信息框数据
                info_box_data = prepare_info_box_data(
                    player_name=f"{player_name} ({team_name})" if team_name else player_name,
                    stats=stats,
                    creator_info=self.config.default_creator_info
                )

            # 6. 设置标题
            opponent_name = ""
            if hasattr(game.game_data, 'home_team') and hasattr(game.game_data, 'away_team'):
                home_team = game.game_data.home_team
                away_team = game.game_data.away_team

                if team_name == home_team.team_name:
                    opponent_name = away_team.team_name
                elif team_name == away_team.team_name:
                    opponent_name = home_team.team_name

            chart_title = f"{player_name} 投篮分布" + (f" vs {opponent_name}" if opponent_name else "")

            # 7. 调用渲染器生成图表
            return self.render_shot_chart(
                shot_markers=shot_markers,
                output_path=output_path,
                chart_title=chart_title,
                legend_spec=legend_spec,
                info_box_data=info_box_data
            )

        except Exception as e:
            self.logger.error(f"生成球员投篮图失败: {e}", exc_info=True)
            return None

    def generate_player_scoring_impact_charts(
            self,
            game: Any,  # Game模型对象
            player_id: int,
            player_name: str,
            output_dir: Optional[Path] = None,
            force_reprocess: bool = False,
            impact_type: str = "full_impact"  # "scoring_only", "full_impact"
    ) -> Dict[str, Path]:
        """
        生成球员得分影响力图

        Args:
            game: 比赛数据对象
            player_id: 球员ID
            player_name: 球员名称
            output_dir: 输出目录
            force_reprocess: 是否强制重新处理
            impact_type: 影响力类型，可选 "scoring_only"(仅显示投篮), "full_impact"(显示投篮和助攻)

        Returns:
            Dict[str, Path]: 图表路径字典
        """
        result_paths = {}
        output_dir = output_dir or self.default_output_dir

        try:
            # 1. 生成球员个人得分图
            scoring_chart_path = self._generate_player_shot_chart(
                game=game,
                player_id=player_id,
                player_name=player_name,
                output_dir=output_dir,
                force_reprocess=force_reprocess,
                shot_outcome="made_only"  # 只显示命中的投篮
            )

            if scoring_chart_path:
                result_paths["scoring_chart"] = scoring_chart_path

            # 2. 如果需要完整影响力图，添加助攻数据
            if impact_type == "full_impact":
                # 获取球员助攻导致的队友得分位置
                assisted_shots = game.get_assisted_shot_data(player_id)

                if assisted_shots:
                    # 生成完整影响力图
                    impact_chart_path = self._generate_player_impact_chart(
                        game=game,
                        player_id=player_id,
                        player_name=player_name,
                        assisted_shots=assisted_shots,
                        output_dir=output_dir,
                        force_reprocess=force_reprocess
                    )

                    if impact_chart_path:
                        result_paths["impact_chart"] = impact_chart_path

            return result_paths

        except Exception as e:
            self.logger.error(f"生成球员得分影响力图失败: {e}", exc_info=True)
            return {}

    def _generate_player_impact_chart(
            self,
            game: Any,  # Game模型对象
            player_id: int,
            player_name: str,
            assisted_shots: List[Dict[str, Any]],
            output_dir: Optional[Path] = None,
            force_reprocess: bool = False
    ) -> Optional[Path]:
        """
        生成球员得分影响力图 (包含个人得分和助攻队友得分)

        Args:
            game: 比赛数据对象
            player_id: 球员ID
            player_name: 球员名称
            assisted_shots: 助攻导致的队友得分数据
            output_dir: 输出目录
            force_reprocess: 是否强制重新处理

        Returns:
            Optional[Path]: 保存的图表路径
        """
        try:
            # 1. 确定输出路径
            output_dir = output_dir or self.default_output_dir
            output_filename = f"{player_name}_impact_chart.png"
            output_path = output_dir / output_filename

            # 检查文件是否已存在且不需要重新处理
            if output_path.exists() and not force_reprocess:
                self.logger.info(f"文件 {output_path} 已存在，跳过处理")
                return output_path

            # 2. 获取球员个人得分数据(仅命中的投篮)
            scoring_shots = []
            player_shots = game.get_shot_data(player_id)
            for shot in player_shots:
                if shot.get('shot_result') == "Made":
                    scoring_shots.append(shot)

            # 3. 准备标记数据 - 个人得分
            scoring_markers = prepare_shot_markers(
                scoring_shots,
                self.config.__dict__,
                shot_outcome="made_only",
                marker_type="default"
            )

            # 4. 准备标记数据 - 助攻队友得分
            assist_markers = prepare_shot_markers(
                assisted_shots,
                self.config.__dict__,
                shot_outcome="made_only",
                marker_type="default",
                team_color=self.config.default_assist_color
            )

            # 合并所有标记
            all_markers = scoring_markers + assist_markers

            # 5. 准备图例
            legend_spec = prepare_legend_spec(
                shot_outcome="made_only",
                chart_type="player_impact",
                player_name=player_name
            )

            # 6. 获取球员信息，准备信息框
            player_info = None
            team_name = ""

            # 查找球员信息
            for team_type in ["home_team", "away_team"]:
                if hasattr(game.game_data, team_type):
                    team = getattr(game.game_data, team_type)
                    if hasattr(team, "players"):
                        for player in team.players:
                            if player.person_id == player_id:
                                player_info = player
                                team_name = team.team_name
                                break
                if player_info:
                    break

            # 准备信息框数据
            info_box_data = None
            if player_info:
                # 获取统计数据
                stats = {}
                if hasattr(player_info, "statistics"):
                    stats = format_player_stats(player_info.statistics.__dict__)

                # 添加影响力统计数据
                stats["个人得分"] = len(scoring_markers)
                stats["助攻得分"] = len(assist_markers)
                stats["总得分影响"] = len(scoring_markers) + len(assist_markers)

                # 创建信息框数据
                info_box_data = prepare_info_box_data(
                    player_name=f"{player_name} ({team_name}) 得分影响力" if team_name else f"{player_name} 得分影响力",
                    stats=stats,
                    creator_info=self.config.default_creator_info
                )
            # 7. 设置标题
            opponent_name = ""
            if hasattr(game.game_data, 'home_team') and hasattr(game.game_data, 'away_team'):
                home_team = game.game_data.home_team
            away_team = game.game_data.away_team

            if team_name == home_team.team_name:
                opponent_name = away_team.team_name
            elif team_name == away_team.team_name:
                opponent_name = home_team.team_name

            chart_title = f"{player_name} 得分影响力" + (f" vs {opponent_name}" if opponent_name else "")

            # 8. 调用渲染器生成图表
            return self.render_shot_chart(
                shot_markers=all_markers,
                output_path=output_path,
                chart_title=chart_title,
                legend_spec=legend_spec,
                info_box_data=info_box_data
            )

        except Exception as e:
            self.logger.error(f"生成球员得分影响力图失败: {e}", exc_info=True)
            return None

    def generate_full_court_shot_chart(
            self,
            game: Any,  # Game模型对象
            output_path: Union[str, Path],
            shot_outcome: str = "made_only",
            force_reprocess: bool = False
    ) -> Optional[Path]:
        """
        渲染全场投篮图

        使用双方球队的所有投篮数据生成全场投篮分布图

        Args:
            game: 比赛数据对象
            output_path: 输出路径
            shot_outcome: 投篮结果筛选，可选 "made_only"(仅命中), "all"(全部)
            force_reprocess: 是否强制重新处理

        Returns:
            Optional[Path]: 保存的图表路径
        """
        try:
            # 检查文件是否已存在且不需要重新处理
            output_path = Path(output_path)
            if output_path.exists() and not force_reprocess:
                self.logger.info(f"文件 {output_path} 已存在，跳过处理")
                return output_path

            # 1. 获取主客队ID和颜色
            home_team_id = game.game_data.home_team.team_id
            home_team_name = game.game_data.home_team.team_name
            away_team_id = game.game_data.away_team.team_id
            away_team_name = game.game_data.away_team.team_name

            # 使用球队配色（这里使用示例颜色，实际可从外部配置获取）
            team_colors = {
                str(home_team_id): "#FDB927",  # 默认主队颜色
                str(away_team_id): "#552583"  # 默认客队颜色
            }

            # 2. 获取两队投篮数据并合并
            home_shots_dict = game.get_team_shot_data(home_team_id)
            away_shots_dict = game.get_team_shot_data(away_team_id)

            # 将字典转换为列表格式
            home_shots = []
            for player_shots in home_shots_dict.values():
                for shot in player_shots:
                    shot['team_type'] = 'home'  # 标记队伍类型
                    shot['team_id'] = home_team_id  # 确保有team_id字段
                    home_shots.append(shot)

            away_shots = []
            for player_shots in away_shots_dict.values():
                for shot in player_shots:
                    shot['team_type'] = 'away'  # 标记队伍类型
                    shot['team_id'] = away_team_id  # 确保有team_id字段
                    away_shots.append(shot)

            # 3. 转换为全场坐标系
            game_data = {
                'home_team_id': home_team_id,
                'away_team_id': away_team_id
            }

            home_full_court_shots = transform_to_full_court_coordinates(home_shots, game_data)
            away_full_court_shots = transform_to_full_court_coordinates(away_shots, game_data)

            # 4. 准备标记数据
            home_markers = prepare_shot_markers(
                home_full_court_shots,
                self.config.__dict__,
                shot_outcome=shot_outcome,
                team_color=team_colors[str(home_team_id)]
            )

            away_markers = prepare_shot_markers(
                away_full_court_shots,
                self.config.__dict__,
                shot_outcome=shot_outcome,
                team_color=team_colors[str(away_team_id)]
            )

            all_markers = home_markers + away_markers

            if not all_markers:
                self.logger.warning("没有符合条件的投篮数据，无法生成全场图")
                return None

            # 5. 准备图例
            legend_spec = prepare_legend_spec(
                shot_outcome=shot_outcome,
                chart_type="full_court",
                team_colors={
                    home_team_name: team_colors[str(home_team_id)],
                    away_team_name: team_colors[str(away_team_id)]
                }
            )

            # 6. 设置标题
            chart_title = f"{home_team_name} vs {away_team_name} 全场投篮分布图"

            # 7. 调用渲染器生成全场图
            return self.render_full_court_shot_chart(
                shot_markers=all_markers,
                output_path=output_path,
                chart_title=chart_title,
                legend_spec=legend_spec
            )

        except Exception as e:
            self.logger.error(f"生成全场投篮图失败: {e}", exc_info=True)
            return None

    def clear_cache(self) -> None:
        """清理图表服务缓存"""
        self.manager.clear_resources()

    def close(self) -> None:
        """关闭图表服务资源"""
        self.clear_cache()
        self.logger.info("图表服务已清理")
