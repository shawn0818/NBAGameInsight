##nba/visualization/court_drawer.py
"""
NBA球场渲染工具
用于绘制标准NBA半场图和全场图，可作为投篮热图和球员位置跟踪的基础图层
坐标系统：
- 半场图: 原点(0,0)位于篮筐中心，向右为X轴正方向，向上为Y轴负方向（底线在Y=-52.5）
- 全场图: 原点(0,0)位于球场中心，向右为X轴正方向，向上为Y轴正方向
- 比例关系: 1个坐标单位 = 0.1英尺 = 约3.04厘米
"""

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Arc
from dataclasses import dataclass
from typing import Tuple, Optional
import numpy as np


@dataclass
class CourtConfig:
    """球场绘制配置"""
    dpi: int = 350  # 图表DPI
    scale_factor: float = 1.5  # 图表缩放比例
    court_bg_color: str = '#F8F8F8'  # 球场背景色
    paint_color: str = '#FDB927'  # 禁区颜色（半场图）
    paint_alpha: float = 0.3  # 禁区透明度
    court_line_color: str = 'k'  # 球场线条颜色
    paint_color_left: str = '#552583'  # 左侧禁区颜色（全场图，例如Lakers紫色）
    paint_color_right: str = '#FDB927'  # 右侧禁区颜色（全场图，例如Lakers金色）
    center_circle_fill: str = '#C8102E'  # 中圈填充色（例如NBA红色）
    center_circle_alpha: float = 0.2  # 中圈透明度


def draw_court(config: Optional[CourtConfig] = None) -> Tuple[plt.Figure, plt.Axes]:
    """绘制NBA半场（篮筐中心为原点）

    按照NBA官方标准绘制球场，篮筐中心位于坐标原点(0,0)
    底线位于Y=-52.5（对应篮筐到底线的标准距离5.25英尺）

    Args:
        config: 图表配置对象，None则使用默认配置

    Returns:
        fig, axis: matplotlib图表对象和轴对象
    """
    if config is None:
        config = CourtConfig()

    base_width, base_height = 12, 12
    scaled_width = base_width * config.scale_factor
    scaled_height = base_height * config.scale_factor

    fig = plt.figure(figsize=(scaled_width, scaled_height), dpi=config.dpi)
    axis = fig.add_subplot(111)

    # 基础线条宽度
    base_line_width = 2 * config.scale_factor

    # 添加球场背景色
    court_bg = Rectangle(
        xy=(-250, -52.5),  # 标准底线位置：5.25英尺(52.5单位)
        width=500,
        height=470,
        linewidth=0,
        facecolor=config.court_bg_color,
        fill=True
    )
    axis.add_patch(court_bg)

    # 绘制填充的禁区
    paint_fill = Rectangle(
        xy=(-80, -52.5),  # 从底线开始
        width=160,
        height=190,
        linewidth=0,
        fill=True,
        facecolor=config.paint_color,
        alpha=config.paint_alpha
    )
    axis.add_patch(paint_fill)

    # 球场外框
    outer_lines = Rectangle(
        xy=(-250, -52.5),  # 标准底线位置
        width=500,
        height=470,
        linewidth=base_line_width * 2,
        edgecolor=config.court_line_color,
        fill=False,
        zorder=3
    )
    axis.add_patch(outer_lines)

    # 禁区边框
    paint = Rectangle(
        xy=(-80, -52.5),  # 从底线开始
        width=160,
        height=190,
        linewidth=base_line_width * 1.5,
        edgecolor=config.court_line_color,
        fill=False,
        zorder=2
    )
    axis.add_patch(paint)

    # 禁区内框
    inner_paint = Rectangle(
        xy=(-60, -52.5),  # 从底线开始
        width=120,
        height=190,
        linewidth=base_line_width * 1.2,
        edgecolor='#808080',
        fill=False,
        zorder=1
    )
    axis.add_patch(inner_paint)

    # 限制区（restricted area）
    restricted = Arc(
        xy=(0, 0),  # 篮筐中心
        width=80,
        height=80,
        theta1=0,
        theta2=180,
        linewidth=base_line_width * 1.5,
        color=config.court_line_color,
        fill=False,
        zorder=2
    )
    axis.add_patch(restricted)

    # 篮板 - 位于篮筐后方
    backboard = Rectangle(
        xy=(-30, -11.5),  # 篮板位置相对于篮筐
        width=60,
        height=1,
        linewidth=base_line_width * 1.5,
        edgecolor=config.court_line_color,
        fill=False,
        zorder=2
    )
    axis.add_patch(backboard)

    # 篮筐 - 中心位于原点(0,0)
    basket = Circle(
        xy=(0, 0),  # 篮筐中心为坐标原点
        radius=7.5,  # 视觉展示用的篮筐半径
        linewidth=base_line_width * 1.5,
        color=config.court_line_color,
        fill=False,
        zorder=2
    )
    axis.add_patch(basket)

    # 罚球圈 - 上半部分（实线）
    free_throw_circle_top = Arc(
        xy=(0, 138.5),  # 距离篮筐中心138.5单位
        width=120,
        height=120,
        theta1=0,
        theta2=180,
        linewidth=base_line_width * 1.5,
        color=config.court_line_color,
        zorder=2
    )
    axis.add_patch(free_throw_circle_top)

    # 罚球圈 - 下半部分（虚线）
    free_throw_circle_bottom = Arc(
        xy=(0, 138.5),  # 与上半部分同心
        width=120,
        height=120,
        theta1=180,
        theta2=360,
        linewidth=base_line_width * 1.2,
        linestyle='--',
        color='#808080',
        zorder=1
    )
    axis.add_patch(free_throw_circle_bottom)

    # ========== 三分线精确绘制 ==========
    # 三分线参数计算
    three_radius = 238.66  # 三分线半径 (477.32/2)
    # 计算准确的三分线端点角度
    theta1_rad = np.radians(22.8)  # 右侧端点角度(弧度)
    theta2_rad = np.radians(157.2)  # 左侧端点角度(弧度)

    # 计算三分线弧线端点坐标
    x_right = three_radius * np.cos(theta1_rad)  # 约219.84
    y_right = three_radius * np.sin(theta1_rad)  # 约92.58

    x_left = three_radius * np.cos(theta2_rad)  # 约-219.84
    y_left = three_radius * np.sin(theta2_rad)  # 约92.58

    # 绘制三分线直线部分 - 使用精确计算的端点
    three_left = Rectangle(
        xy=(x_left, -52.5),  # 从底线开始，使用精确的X坐标
        width=0,  # 宽度为0表示垂直线
        height=y_left + 52.5,  # 精确高度到弧线端点
        linewidth=base_line_width * 1.5,
        edgecolor=config.court_line_color,
        fill=False,
        zorder=2
    )
    three_right = Rectangle(
        xy=(x_right, -52.5),  # 从底线开始，使用精确的X坐标
        width=0,  # 宽度为0表示垂直线
        height=y_right + 52.5,  # 精确高度到弧线端点
        linewidth=base_line_width * 1.5,
        edgecolor=config.court_line_color,
        fill=False,
        zorder=2
    )
    axis.add_patch(three_left)
    axis.add_patch(three_right)

    # 三分弧线 - 使用原始角度，但确保使用相同的绘图参数
    three_arc = Arc(
        xy=(0, 0),  # 以篮筐中心为圆心
        width=477.32,
        height=477.32,
        theta1=22.8,
        theta2=157.2,
        linewidth=base_line_width * 1.5,
        color=config.court_line_color,
        zorder=2
    )
    axis.add_patch(three_arc)

    # 中场圆圈填充
    center_circle_fill = Circle(
        xy=(0, 418.5),  # 中场圆心位置
        radius=60,
        facecolor=config.center_circle_fill,
        alpha=config.center_circle_alpha,
        zorder=1
    )
    axis.add_patch(center_circle_fill)

    # 中场圆圈 - 外圈
    center_outer_arc = Arc(
        xy=(0, 418.5),  # 中场圆心位置
        width=120,
        height=120,
        theta1=180,
        theta2=0,
        linewidth=base_line_width * 1.5,
        color=config.court_line_color,
        zorder=2
    )
    axis.add_patch(center_outer_arc)

    # 中场圆圈 - 内圈
    center_inner_arc = Arc(
        xy=(0, 418.5),  # 与外圈同心
        width=40,
        height=40,
        theta1=180,
        theta2=0,
        linewidth=base_line_width * 1.5,
        color=config.court_line_color,
        zorder=2
    )
    axis.add_patch(center_inner_arc)

    # 设置坐标轴
    axis.set_xlim(-250, 250)
    axis.set_ylim(418.5, -52.5)  # y轴下限为精确的底线位置
    axis.set_xticks([])
    axis.set_yticks([])

    return fig, axis


def _draw_hoop_area(axis: plt.Axes, hoop_center_x: float, config: CourtConfig, base_line_width: float):
    """绘制单个篮筐及相关区域 (篮板、篮筐、限制区)"""
    lw = base_line_width * 1.5  # 线宽

    # 篮筐中心 Y 坐标固定为 0
    hoop_center_y = 0
    half_court_length = 470  # 94ft / 2 = 47ft = 470 units

    # 篮板: 距离底线4英尺(40单位)
    baseline_x = np.sign(hoop_center_x) * half_court_length  # 底线 X 坐标 (+470 or -470)
    backboard_dist_from_baseline = 40
    backboard_x = baseline_x - np.sign(baseline_x) * backboard_dist_from_baseline

    # 绘制篮板 (垂直线段)
    axis.plot([backboard_x, backboard_x], [-30, 30], color=config.court_line_color, lw=lw, zorder=2)

    # 绘制篮筐 - 中心位于 (hoop_center_x, 0)
    basket = Circle(
        xy=(hoop_center_x, hoop_center_y),
        radius=7.5,  # 视觉展示用的篮筐半径
        linewidth=lw,
        edgecolor=config.court_line_color,
        facecolor='none',  # 无填充
        fill=False,
        zorder=3
    )
    axis.add_patch(basket)

    # 限制区（restricted area）- 半径4英尺(40单位), 圆心在篮筐中心
    if hoop_center_x > 0:  # 右侧篮筐，绘制左半圆
        theta1, theta2 = 90, 270
    else:  # 左侧篮筐，绘制右半圆
        theta1, theta2 = 270, 90

    restricted = Arc(
        xy=(hoop_center_x, hoop_center_y),  # 圆心在篮筐中心
        width=80,  # 直径 8英尺 (80单位)
        height=80,
        theta1=theta1,
        theta2=theta2,
        linewidth=lw,
        color=config.court_line_color,
        fill=False,
        zorder=2
    )
    axis.add_patch(restricted)


def _draw_key_area(axis: plt.Axes, hoop_center_x: float, paint_color: str, config: CourtConfig, base_line_width: float):
    """绘制单个罚球区 (油漆区、罚球圈)"""
    lw = base_line_width * 1.5  # 线宽
    lw_dashed = base_line_width * 1.2  # 虚线线宽

    # 罚球区参数
    key_width = 160  # 16英尺
    key_length = 190  # 19英尺 (从底线到罚球线)
    ft_circle_radius = 60  # 6英尺半径
    baseline_x = np.sign(hoop_center_x) * 470  # 底线 X 坐标

    # 罚球线 X 坐标 (距离底线19英尺)
    ft_line_x = baseline_x - np.sign(hoop_center_x) * key_length
    # 罚球圈圆心
    ft_circle_center = (ft_line_x, 0)

    # 绘制填充的禁区 (油漆区)
    paint_fill = Rectangle(
        xy=(min(baseline_x, ft_line_x), -key_width / 2),  # 左下角坐标
        width=abs(baseline_x - ft_line_x),  # 长度
        height=key_width,  # 宽度
        linewidth=0,
        fill=True,
        facecolor=paint_color,
        alpha=config.paint_alpha,
        zorder=1  # 在线条下方
    )
    axis.add_patch(paint_fill)

    # 禁区边框 (矩形) - 不含罚球线
    # 两条水平线 (平行于底线)
    axis.plot([baseline_x, ft_line_x], [key_width / 2, key_width / 2],
              color=config.court_line_color, lw=lw, zorder=2)
    axis.plot([baseline_x, ft_line_x], [-key_width / 2, -key_width / 2],
              color=config.court_line_color, lw=lw, zorder=2)

    # 罚球线 (垂直于底线)
    axis.plot([ft_line_x, ft_line_x], [-key_width / 2, key_width / 2],
              color=config.court_line_color, lw=lw, zorder=2)

    # 罚球圈 - 实线部分 (远离篮筐一侧)
    if hoop_center_x > 0:  # 右侧篮筐，画左半圆
        theta1, theta2 = 90, 270
    else:  # 左侧篮筐，画右半圆
        theta1, theta2 = 270, 90

    free_throw_circle_solid = Arc(
        xy=ft_circle_center,
        width=2 * ft_circle_radius,
        height=2 * ft_circle_radius,
        theta1=theta1,
        theta2=theta2,
        linewidth=lw,
        color=config.court_line_color,
        zorder=2
    )
    axis.add_patch(free_throw_circle_solid)

    # 罚球圈 - 虚线部分 (靠近篮筐一侧)
    if hoop_center_x > 0:  # 右侧篮筐，画右半圆
        theta1, theta2 = 270, 90
    else:  # 左侧篮筐，画左半圆
        theta1, theta2 = 90, 270

    free_throw_circle_dashed = Arc(
        xy=ft_circle_center,
        width=2 * ft_circle_radius,
        height=2 * ft_circle_radius,
        theta1=theta1,
        theta2=theta2,
        linewidth=lw_dashed,
        linestyle='--',
        color='#808080',  # 灰色虚线
        zorder=1  # 在实线下方
    )
    axis.add_patch(free_throw_circle_dashed)


def _draw_three_point_line(axis: plt.Axes, hoop_center_x: float, config: CourtConfig, base_line_width: float):
    """绘制单侧的三分线"""
    lw = base_line_width * 1.5  # 线宽

    # 三分线参数
    three_radius = 237.5  # NBA三分线半径 23英尺9英寸 = 23.75英尺 = 237.5单位
    corner_three_y = 220  # 角落三分线距离球场中心线的距离 (边线250 - 边线到底角三分线距离30 = 220)
    baseline_x = np.sign(hoop_center_x) * 470  # 底线 X 坐标

    # 计算弧线与直线连接点的 X 坐标
    # (x - hoop_center_x)^2 + y^2 = three_radius^2
    # y = +/- corner_three_y
    delta_x_sq = three_radius**2 - corner_three_y**2
    if delta_x_sq < 0:  # 半径小于角落距离，不太可能发生
        print("警告：三分线半径小于底角距离，无法绘制弧线。")
        return
    delta_x = np.sqrt(delta_x_sq)  # ≈ 89.477

    # 连接点的 X 坐标
    arc_end_x = hoop_center_x - np.sign(hoop_center_x) * delta_x

    # 绘制两条直线部分 (从底线到连接点)
    axis.plot([baseline_x, arc_end_x], [corner_three_y, corner_three_y],
              color=config.court_line_color, lw=lw, zorder=2)
    axis.plot([baseline_x, arc_end_x], [-corner_three_y, -corner_three_y],
              color=config.court_line_color, lw=lw, zorder=2)

    # 计算弧线角度
    # angle = atan2(y, x - hoop_center_x)
    if hoop_center_x > 0:  # 右侧篮筐
        theta_start = np.degrees(np.arctan2(-corner_three_y, -delta_x))  # 对应下连接点
        theta_end = np.degrees(np.arctan2(corner_three_y, -delta_x))     # 对应上连接点
        theta1 = theta_end
        theta2 = theta_start + 360 if theta_start < theta_end else theta_start  # 确保 theta2 > theta1
    else:  # 左侧篮筐
        theta_start = np.degrees(np.arctan2(-corner_three_y, delta_x))  # 对应下连接点
        theta_end = np.degrees(np.arctan2(corner_three_y, delta_x))     # 对应上连接点
        theta1 = theta_start
        theta2 = theta_end

    # 绘制三分弧线
    three_arc = Arc(
        xy=(hoop_center_x, 0),  # 以篮筐中心为圆心
        width=2 * three_radius,
        height=2 * three_radius,
        theta1=theta1,
        theta2=theta2,
        linewidth=lw,
        color=config.court_line_color,
        zorder=2
    )
    axis.add_patch(three_arc)


def draw_full_court_horizontal(config: Optional[CourtConfig] = None) -> Tuple[plt.Figure, plt.Axes]:
    """绘制NBA全场（横向，球场中心为原点）

    按照NBA官方标准绘制球场，球场中心位于坐标原点(0,0)
    X轴为长度方向，Y轴为宽度方向。

    Args:
        config: 图表配置对象，None则使用默认配置

    Returns:
        fig, axis: matplotlib图表对象和轴对象
    """
    if config is None:
        config = CourtConfig()

    # 画布基础尺寸，调整比例适应横向
    base_width, base_height = 18, 12  # 横向更宽
    scaled_width = base_width * config.scale_factor
    scaled_height = base_height * config.scale_factor

    fig = plt.figure(figsize=(scaled_width, scaled_height), dpi=config.dpi)
    axis = fig.add_subplot(111)

    # 基础线条宽度
    base_line_width = 1.5 * config.scale_factor  # 稍微调细一点

    # 球场尺寸 (单位: 0.1英尺)
    court_length = 940
    court_width = 500
    half_court_length = court_length / 2
    half_court_width = court_width / 2
    hoop_dist_from_baseline = 52.5
    hoop_center_x_right = half_court_length - hoop_dist_from_baseline  # 右侧篮筐X坐标
    hoop_center_x_left = -half_court_length + hoop_dist_from_baseline  # 左侧篮筐X坐标

    # 1. 添加球场背景色
    court_bg = Rectangle(
        xy=(-half_court_length, -half_court_width),
        width=court_length,
        height=court_width,
        linewidth=0,
        facecolor=config.court_bg_color,
        fill=True,
        zorder=0  # 最底层
    )
    axis.add_patch(court_bg)

    # 2. 球场外框 (边线和底线)
    outer_lines = Rectangle(
        xy=(-half_court_length, -half_court_width),  # 左下角
        width=court_length,
        height=court_width,
        linewidth=base_line_width * 2,  # 外框线加粗
        edgecolor=config.court_line_color,
        fill=False,
        zorder=3  # 在填充和部分线条之上
    )
    axis.add_patch(outer_lines)

    # 3. 中线
    axis.plot([0, 0], [-half_court_width, half_court_width],
              color=config.court_line_color, lw=base_line_width*1.5, zorder=2)

    # 4. 中圈
    center_circle_radius = 60  # 半径6英尺
    # 中圈填充
    center_circle_fill = Circle(
        xy=(0, 0),
        radius=center_circle_radius,
        facecolor=config.center_circle_fill,
        alpha=config.center_circle_alpha,
        zorder=1
    )
    axis.add_patch(center_circle_fill)
    # 中圈线条
    center_circle_line = Circle(
        xy=(0, 0),
        radius=center_circle_radius,
        linewidth=base_line_width*1.5,
        edgecolor=config.court_line_color,
        fill=False,
        zorder=2
    )
    axis.add_patch(center_circle_line)

    # 5. 绘制两侧半场对称元素
    # 左侧
    _draw_hoop_area(axis, hoop_center_x_left, config, base_line_width)
    _draw_key_area(axis, hoop_center_x_left, config.paint_color_left, config, base_line_width)
    _draw_three_point_line(axis, hoop_center_x_left, config, base_line_width)

    # 右侧
    _draw_hoop_area(axis, hoop_center_x_right, config, base_line_width)
    _draw_key_area(axis, hoop_center_x_right, config.paint_color_right, config, base_line_width)
    _draw_three_point_line(axis, hoop_center_x_right, config, base_line_width)

    # 6. 设置坐标轴范围和样式
    margin = 30  # 边距
    axis.set_xlim(-half_court_length - margin, half_court_length + margin)
    axis.set_ylim(-half_court_width - margin, half_court_width + margin)

    # 隐藏坐标轴刻度和标签
    axis.set_xticks([])
    axis.set_yticks([])

    # 保持横纵轴比例一致，使圆形看起来是圆的
    axis.set_aspect('equal', adjustable='box')

    # 移除坐标轴周围的空白
    plt.tight_layout(pad=0)

    return fig, axis

'''
if __name__ == "__main__":
    """示例用法"""
    # 创建自定义配置 (可选)
    my_config = CourtConfig(
        dpi=300,
        scale_factor=1.2,
        court_bg_color='#EFEFEF',
        paint_color='yellow',
        paint_alpha=0.3,
        paint_color_left='blue',
        paint_color_right='red',
        center_circle_fill='orange'
    )

    # 创建标准NBA半场图
    print("正在绘制半场图...")
    fig_half, axis_half = draw_court()
    # 保存图片
    fig_half.savefig("nba_court_half.png", dpi=300, bbox_inches='tight')
    print("半场图已保存为 nba_court_half.png")

    # 创建标准NBA全场图
    print("\n正在绘制全场图...")
    fig_full, axis_full = draw_full_court_horizontal()
    # 保存图片
    fig_full.savefig("nba_court_full.png", dpi=300, bbox_inches='tight', pad_inches=0.1)
    print("全场图已保存为 nba_court_full.png")

    # 创建自定义样式的NBA全场图
    print("\n正在绘制自定义样式的全场图...")
    fig_custom, axis_custom = draw_full_court_horizontal(config=my_config)
    # 保存图片
    fig_custom.savefig("nba_court_full_custom.png", dpi=300, bbox_inches='tight', pad_inches=0.1)
    print("自定义全场图已保存为 nba_court_full_custom.png")

    # 显示图片
    plt.show()
'''