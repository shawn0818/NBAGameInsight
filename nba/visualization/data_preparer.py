# #nba/visualization/data_preparer.py
"""
图表数据准备器 - 为 ShotChartsRenderer 准备渲染所需的数据

此模块专注于将原始数据转换为图表渲染所需的格式，
提供一系列工具函数用于标记数据准备、图例规格创建、坐标转换等。
"""

import math
from typing import List, Dict, Any, Optional, Tuple, Union, TypedDict, cast
from scipy.spatial import cKDTree
import numpy as np
from PIL import Image

# 导入日志处理器
from utils.logger_handler import AppLogger

# 获取模块级别的日志记录器
logger = AppLogger.get_logger(__name__, app_name='nba_utils')


# ================= 类型定义 ===================

class ShotMarker(TypedDict, total=False):
    """投篮标记数据类型，用于渲染单个投篮点"""
    x: float  # X坐标 (半场坐标系)
    y: float  # Y坐标 (半场坐标系)
    marker_type: str  # 标记类型: 'default' 或 'avatar'
    size: float  # 标记大小 (对应 matplotlib scatter 的 's' 参数)
    alpha: float  # 透明度 (0-1)
    is_made: bool  # 是否命中
    color: str  # 标记颜色 (十六进制或颜色名)
    marker_symbol: str  # 标记形状 ('o', 'x', 's' 等)
    border_color: str  # 边框颜色
    border_width: float  # 边框宽度
    avatar_image: Image.Image  # 头像图像 (如果 marker_type='avatar')


class LegendItem(TypedDict, total=False):
    """图例项数据类型，描述图例中的单个条目"""
    label: str  # 显示文本
    color: str  # 颜色
    marker: str  # 标记类型
    markersize: float  # 标记大小
    edgecolor: str  # 边框颜色
    alpha: float  # 透明度
    location: str  # 图例位置 ('upper right' 等)
    bbox_to_anchor: Tuple[float, float]  # 图例锚点
    ncol: int  # 图例列数


class InfoBoxData(TypedDict, total=False):
    """信息框数据类型，用于图表底部的信息显示"""
    name: str  # 主标题 (通常是球员/球队名)
    stats: Dict[str, Any]  # 统计数据 {标签: 值}
    avatar_image: Optional[Image.Image]  # 头像图像
    creator_info: str  # 创建者信息


class ChartConfigLike(TypedDict, total=False):
    """图表配置数据类型，包含必要的配置参数"""
    marker_base_size: float  # 基础标记大小
    marker_min_size: float  # 最小标记大小
    ideal_marker_distance: float  # 理想标记间距
    marker_border_width: float  # 标记边框宽度
    default_made_shot_color: str  # 命中球默认颜色
    default_missed_shot_color: str  # 未命中球默认颜色
    default_assist_color: str  # 助攻默认颜色
    default_creator_info: str  # 默认创建者信息


# ================= 主要功能函数 ===================

def calculate_marker_sizes(
        coordinates: List[Tuple[float, float]],
        base_size: float = 50.0,
        min_size: float = 20.0,
        ideal_distance: float = 25.0
) -> List[float]:
    """
    根据局部密度计算每个投篮点的标记大小

    针对密集区域自动减小标记尺寸，避免重叠

    Args:
        coordinates: 投篮点坐标列表 [(x1,y1), (x2,y2), ...]
        base_size: 基础标记大小 ('s' 值)
        min_size: 最小标记大小 ('s' 值)
        ideal_distance: 理想的点间最小距离

    Returns:
        List[float]: 每个点对应的标记大小 ('s' 值) 列表
    """
    num_points = len(coordinates)

    # 处理特殊情况：没有点或只有一个点
    if num_points == 0:
        return []
    if num_points == 1:
        return [base_size]

    try:
        # 构建 KDTree 用于快速最近邻搜索
        coords_array = np.array(coordinates)
        tree = cKDTree(coords_array)

        # 查询每个点的最近邻
        # k=2 因为第一个最近邻是点本身
        distances, _ = tree.query(coords_array, k=2)
        nearest_distances = distances[:, 1]

        # 计算标记大小
        marker_sizes = []
        for dist in nearest_distances:
            if np.isinf(dist) or dist >= ideal_distance:
                # 孤立点使用基础大小
                size = base_size
            else:
                # 密集区域，基于距离比例缩放
                # 使用平方根关系使变化更平滑
                scale_factor = math.sqrt(max(0.1, dist / ideal_distance))
                min_scale_factor = math.sqrt(min_size / base_size)

                # 应用缩放因子，但确保不小于最小尺寸
                effective_scale = max(min_scale_factor, scale_factor)
                size = base_size * (effective_scale ** 2)

            # 确保最终尺寸不小于最小值
            marker_sizes.append(max(min_size, size))

        return marker_sizes

    except Exception as e:
        logger.error(f"计算标记大小时发生错误: {e}", exc_info=True)
        # 出错时使用默认大小
        return [base_size] * num_points


def prepare_shot_markers(
        shots_data: List[Dict[str, Any]],
        chart_config: ChartConfigLike,
        avatar_map: Optional[Dict[int, Image.Image]] = None,
        shot_outcome: str = "made_only",
        marker_type: Optional[str] = None,
        team_color: Optional[str] = None,
        assist_player_id: Optional[int] = None
) -> List[ShotMarker]:
    """
    准备投篮标记数据

    从原始投篮数据转换为 ShotChartsRenderer 所需的标记格式

    Args:
        shots_data: 原始投篮数据列表
        chart_config: 图表配置，包含默认样式参数
        avatar_map: 球员ID到头像图像的映射
        shot_outcome: 筛选条件，"made_only" 或 "all"
        marker_type: 可选，强制标记类型 'default' 或 'avatar'
        team_color: 可选，指定团队颜色 (覆盖默认颜色)
        assist_player_id: 可选，助攻球员ID (用于球员影响力图)

    Returns:
        List[ShotMarker]: 格式化的标记数据列表
    """
    # 参数验证和默认值
    if avatar_map is None:
        avatar_map = {}

    # 从配置中获取样式参数
    made_color = chart_config.get('default_made_shot_color', '#3A7711')
    missed_color = chart_config.get('default_missed_shot_color', '#C9082A')
    assist_color = chart_config.get('default_assist_color', '#552583')
    border_width = chart_config.get('marker_border_width', 1.0)
    base_size = chart_config.get('marker_base_size', 50.0)
    min_size = chart_config.get('marker_min_size', 20.0)
    ideal_distance = chart_config.get('ideal_marker_distance', 25.0)

    logger.info(f"准备投篮标记数据: {len(shots_data)} 个原始数据点, 筛选条件 '{shot_outcome}'")

    # 1. 筛选并提取基础数据
    filtered_shots = []
    for shot in shots_data:
        # 获取基本属性
        is_made = shot.get('shot_result') == "Made"
        x = shot.get('x_legacy')
        y = shot.get('y_legacy')
        player_id = shot.get('player_id')
        assist_id = shot.get('assist_person_id')

        # 应用筛选条件
        if shot_outcome == "made_only" and not is_made:
            continue

        # 检查必要数据
        if x is None or y is None or player_id is None:
            logger.warning(f"跳过缺少必要数据的投篮记录")
            continue

        # 添加到筛选后列表
        filtered_shots.append({
            'x': float(x),
            'y': float(y),
            'player_id': int(player_id),
            'is_made': is_made,
            'assist_id': assist_id
        })

    # 如果没有符合条件的投篮，返回空列表
    if not filtered_shots:
        logger.warning("筛选后没有符合条件的投篮数据")
        return []

    # 2. 计算基于密度的标记大小
    coordinates = [(shot['x'], shot['y']) for shot in filtered_shots]
    marker_sizes = calculate_marker_sizes(
        coordinates,
        base_size=base_size,
        min_size=min_size,
        ideal_distance=ideal_distance
    )

    # 将大小添加回数据
    for i, shot in enumerate(filtered_shots):
        shot['size'] = marker_sizes[i]

    # 3. 构建最终标记列表
    result_markers: List[ShotMarker] = []

    for shot in filtered_shots:
        player_id = shot['player_id']
        is_made = shot['is_made']
        is_assisted = assist_player_id is not None and shot.get('assist_id') == assist_player_id

        # 确定标记类型
        final_marker_type = marker_type or 'default'
        if final_marker_type == 'avatar' and player_id in avatar_map:
            actual_marker_type = 'avatar'
            avatar_image = avatar_map[player_id]
        else:
            actual_marker_type = 'default'
            avatar_image = None

        # 确定颜色方案
        if team_color:
            color = team_color
        elif is_assisted and is_made:
            color = assist_color
        else:
            color = made_color if is_made else missed_color

        # 设置透明度和形状
        alpha = 0.95 if is_made else 0.75
        marker_symbol = 'o' if is_made else 'x'

        # 创建标记数据
        marker: ShotMarker = {
            'x': shot['x'],
            'y': shot['y'],
            'is_made': is_made,
            'marker_type': actual_marker_type,
            'size': shot['size'],
            'alpha': alpha,
            'color': color,
            'marker_symbol': marker_symbol,
            'border_color': color,
            'border_width': border_width
        }

        # 如果使用头像标记，添加头像
        if actual_marker_type == 'avatar' and avatar_image is not None:
            marker['avatar_image'] = avatar_image

        result_markers.append(marker)

    logger.info(f"成功准备 {len(result_markers)} 个投篮标记")
    return result_markers


def prepare_legend_spec(
        shot_outcome: str = "made_only",
        chart_type: str = "player",
        team_colors: Optional[Dict[str, str]] = None,
        chart_config: Optional[ChartConfigLike] = None,
        player_name: Optional[str] = None
) -> List[LegendItem]:
    """
    准备图例规格

    根据图表类型和其他参数生成适当的图例规格

    Args:
        shot_outcome: 投篮结果筛选 "made_only" 或 "all"
        chart_type: 图表类型 "player", "team", "player_impact" 或 "full_court"
        team_colors: 球队颜色映射 {team_name: color}
        chart_config: 图表配置，提供默认样式
        player_name: 球员名称，用于影响力图

    Returns:
        List[LegendItem]: 图例规格列表
    """
    # 获取默认颜色
    made_color = '#3A7711'  # 默认命中颜色
    missed_color = '#C9082A'  # 默认未命中颜色
    assist_color = '#552583'  # 默认助攻颜色

    if chart_config:
        made_color = chart_config.get('default_made_shot_color', made_color)
        missed_color = chart_config.get('default_missed_shot_color', missed_color)
        assist_color = chart_config.get('default_assist_color', assist_color)

    legend_spec: List[LegendItem] = []

    # 根据图表类型生成不同图例
    if chart_type == "full_court" and team_colors:
        # 全场图 - 显示两队颜色
        teams = list(team_colors.items())
        ncol = len(teams) * (2 if shot_outcome == "all" else 1)

        for team_name, color in teams:
            # 添加命中图例
            legend_spec.append({
                'label': f"{team_name} 命中",
                'color': color,
                'marker': 'o',
                'location': 'upper center',
                'bbox_to_anchor': (0.5, 1.05),
                'ncol': ncol
            })

            # 如果显示全部投篮，添加未命中图例
            if shot_outcome == "all":
                legend_spec.append({
                    'label': f"{team_name} 未命中",
                    'color': color,
                    'marker': 'x',
                    'alpha': 0.5,
                    'location': 'upper center',
                    'bbox_to_anchor': (0.5, 1.05),
                    'ncol': ncol
                })

    elif chart_type == "player_impact":
        # 球员影响力图 - 显示个人得分和助攻
        player_display = player_name or '球员'

        # 个人得分图例
        legend_spec.append({
            'label': f"{player_display}个人得分",
            'color': made_color,
            'marker': 'o'
        })

        # 助攻图例
        legend_spec.append({
            'label': "助攻队友得分",
            'color': assist_color,
            'marker': 'o'
        })

    else:
        # 默认图例 - 适用于普通球员/球队图
        # 命中图例
        legend_spec.append({
            'label': "投篮命中",
            'color': made_color,
            'marker': 'o'
        })

        # 如果显示全部投篮，添加未命中图例
        if shot_outcome == "all":
            legend_spec.append({
                'label': "投篮未命中",
                'color': missed_color,
                'marker': 'x'
            })

    logger.debug(f"为 '{chart_type}' 图表创建了 {len(legend_spec)} 个图例项")
    return legend_spec


def prepare_info_box_data(
        player_name: str,
        stats: Dict[str, Any],
        avatar_image: Optional[Image.Image] = None,
        creator_info: Optional[str] = None
) -> InfoBoxData:
    """
    准备球员信息框数据

    准备显示在图表底部的球员信息框内容

    Args:
        player_name: 球员名称
        stats: 统计数据字典，已格式化好的 {标签: 值}
        avatar_image: 球员头像图像
        creator_info: 创建者信息

    Returns:
        InfoBoxData: 信息框数据
    """
    # 创建基本数据结构
    info_box: InfoBoxData = {
        'name': player_name,
        'stats': stats,
        'creator_info': creator_info or '图表制作者'
    }

    # 如果提供了头像，添加到数据中
    if avatar_image is not None:
        info_box['avatar_image'] = avatar_image

    logger.debug(f"为 {player_name} 准备了信息框数据，包含 {len(stats)} 个统计项")
    return info_box


def format_player_stats(
        raw_stats: Dict[str, Any],
        include_keys: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    格式化球员统计数据

    从原始统计数据提取并格式化信息框所需的数据

    Args:
        raw_stats: 原始统计数据
        include_keys: 可选，要包含的特定键列表

    Returns:
        Dict[str, Any]: 格式化后的统计数据 {标签: 值}
    """
    # 默认显示的统计项及其转换后的中文标签
    default_keys = {
        'position': '位置',
        'points': '得分',
        'assists': '助攻',
        'rebounds': '篮板',
        'fg_pct': '命中率',
        'three_pct': '三分率',
        'steals': '抢断',
        'blocks': '盖帽'
    }

    # 如果未指定要包含的键，使用默认键
    keys_to_use = include_keys or default_keys.keys()

    # 格式化结果
    formatted = {}

    for key in keys_to_use:
        if key not in raw_stats:
            continue

        value = raw_stats[key]
        label = default_keys.get(key, key)  # 获取中文标签，如果没有则使用原键名

        # 特殊处理百分比
        if key.endswith('_pct') and isinstance(value, (int, float)):
            formatted[label] = f"{value:.1%}"
        else:
            formatted[label] = value

    return formatted


def transform_to_full_court_coordinates(
        half_court_shots: List[Dict[str, Any]],
        game_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    将半场投篮数据转换为全场坐标系

    用于全场投篮图的数据准备

    Args:
        half_court_shots: 半场坐标系下的投篮数据列表
        game_data: 包含主客队ID的比赛数据

    Returns:
        List[Dict[str, Any]]: 转换后的全场坐标系投篮数据
    """
    try:
        # 提取主客队ID
        home_id = game_data.get('home_team_id')
        away_id = game_data.get('away_team_id')

        if not home_id or not away_id:
            logger.error("无法获取主客队ID，坐标转换失败")
            return []

        # 篮筐到中心的距离
        hoop_dist = 417.5  # 篮筐到中线的距离

        # 转换后的结果
        full_court_shots = []

        for shot in half_court_shots:
            # 提取必要数据
            x_half = shot.get('x_legacy') or shot.get('x')
            y_half = shot.get('y_legacy') or shot.get('y')
            team_id = shot.get('team_id')

            if x_half is None or y_half is None or team_id is None:
                logger.warning("投篮数据缺少必要字段，跳过转换")
                continue

            try:
                x_half = float(x_half)
                y_half = float(y_half)
                team_id = int(team_id)
            except (ValueError, TypeError):
                logger.warning(f"投篮坐标转换类型错误: x={x_half}, y={y_half}, team={team_id}")
                continue

            # 转换坐标
            # Y轴: 半场X对应全场Y (边线方向)
            full_y = x_half

            # X轴: 取决于球队进攻方向
            if team_id == home_id:
                # 主队进攻右侧
                full_x = hoop_dist - y_half
            elif team_id == away_id:
                # 客队进攻左侧
                full_x = -hoop_dist + y_half
            else:
                logger.warning(f"球队ID {team_id} 不匹配主客队ID")
                continue

            # 复制原始数据并更新坐标
            full_court_shot = shot.copy()
            full_court_shot['x'] = full_x
            full_court_shot['y'] = full_y

            full_court_shots.append(full_court_shot)

        logger.info(f"成功将 {len(full_court_shots)}/{len(half_court_shots)} 个投篮点转换到全场坐标系")
        return full_court_shots

    except Exception as e:
        logger.error(f"全场坐标转换时发生错误: {e}", exc_info=True)
        return []