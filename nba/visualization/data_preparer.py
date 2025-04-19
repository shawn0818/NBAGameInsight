# #nba/visualization/data_preparer.py
"""
图表数据准备器 - 为 ShotChartsRenderer 准备渲染所需的数据。

此模块负责将原始比赛事件数据转换为可用于渲染投篮图/影响力图的结构化数据，
并提供若干工具函数（投篮标记规格、图例规格、信息框格式化、坐标转换等）。

"""


import math
from typing import List, Dict, Any, Optional, Tuple, Union, TypedDict, cast

from scipy.spatial import cKDTree  # type: ignore
import numpy as np
from PIL import Image

# 应用侧日志工具（请确保 utils.logger_handler.AppLogger 可用）
from utils.logger_handler import AppLogger

logger = AppLogger.get_logger(__name__, app_name="nba_utils")

# ===================== 类型定义 =====================


class ShotMarker(TypedDict, total=False):
    """投篮标记的渲染字段"""

    x: float  # X 坐标（半场或全场坐标系）
    y: float  # Y 坐标（半场或全场坐标系）
    marker_type: str  # 'default' | 'avatar'
    size: float  # scatter.s
    alpha: float  # 透明度 0‑1
    is_made: bool  # 是否命中
    color: str  # 填充色
    marker_symbol: str  # 'o' | 'x' ...
    border_color: str
    border_width: float
    avatar_image: Image.Image  # 头像


class LegendItem(TypedDict, total=False):
    label: str
    color: str
    marker: str
    markersize: float
    edgecolor: str
    alpha: float
    location: str
    bbox_to_anchor: Tuple[float, float]
    ncol: int


class InfoBoxData(TypedDict, total=False):
    name: str
    stats: Dict[str, Any]
    avatar_image: Optional[Image.Image]
    creator_info: str


class ChartConfigLike(TypedDict, total=False):
    marker_base_size: float
    marker_min_size: float
    ideal_marker_distance: float
    marker_border_width: float
    default_made_shot_color: str
    default_missed_shot_color: str
    default_assist_color: str
    default_creator_info: str


# ===================== 辅助函数 =====================

def calculate_marker_sizes(
    coordinates: List[Tuple[float, float]],
    base_size: float = 50.0,
    min_size: float = 20.0,
    ideal_distance: float = 25.0,
) -> List[float]:
    """根据局部密度自适应缩放标记大小"""

    n = len(coordinates)
    if n == 0:
        return []
    if n == 1:
        return [base_size]

    try:
        tree = cKDTree(np.array(coordinates))
        dists, _ = tree.query(coordinates, k=2)
        nearest = dists[:, 1]
        result: List[float] = []
        min_scale = math.sqrt(min_size / base_size)
        for dist in nearest:
            if np.isinf(dist) or dist >= ideal_distance:
                size = base_size
            else:
                scale = max(min_scale, math.sqrt(dist / ideal_distance))
                size = base_size * scale ** 2
            result.append(max(min_size, size))
        return result
    except Exception as e:  # pragma: no cover
        logger.error("计算标记大小失败: %s", e, exc_info=True)
        return [base_size] * n


# ===================== 主数据准备逻辑 =====================

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
    准备投篮标记数据（兼容半场 / 全场坐标）

    - 如果 shot 字典中已经包含全场转换后的 `x / y`，优先使用；
    - 否则退回到传统半场坐标 `x_legacy / y_legacy`。
    """

    # === 0. 参数准备 ===
    if avatar_map is None:
        avatar_map = {}

    made_color   = chart_config.get('default_made_shot_color',   '#3A7711')
    missed_color = chart_config.get('default_missed_shot_color', '#C9082A')
    assist_color = chart_config.get('default_assist_color',      '#552583')

    border_width   = chart_config.get('marker_border_width',    1.0)
    base_size      = chart_config.get('marker_base_size',      50.0)
    min_size       = chart_config.get('marker_min_size',       20.0)
    ideal_distance = chart_config.get('ideal_marker_distance', 25.0)

    logger.info(f"准备投篮标记数据: {len(shots_data)} 个原始数据点, 筛选条件 '{shot_outcome}'")

    # === 1. 数据筛选 ===
    filtered_shots = []
    for shot in shots_data:
        is_made   = shot.get('shot_result') == "Made"
        # 关键：优先取全场坐标 x/y，其次取半场坐标 x_legacy/y_legacy
        x         = shot.get('x', shot.get('x_legacy'))
        y         = shot.get('y', shot.get('y_legacy'))
        player_id = shot.get('player_id')
        assist_id = shot.get('assist_person_id')

        if shot_outcome == "made_only" and not is_made:
            continue
        if x is None or y is None or player_id is None:
            logger.warning("跳过缺少必要数据的投篮记录")
            continue

        filtered_shots.append({
            'x'        : float(x),
            'y'        : float(y),
            'player_id': int(player_id),
            'is_made'  : is_made,
            'assist_id': assist_id
        })

    if not filtered_shots:
        logger.warning("筛选后没有符合条件的投篮数据")
        return []

    # === 2. 计算标记尺寸 ===
    coordinates   = [(s['x'], s['y']) for s in filtered_shots]
    marker_sizes  = calculate_marker_sizes(
        coordinates,
        base_size=base_size,
        min_size=min_size,
        ideal_distance=ideal_distance
    )
    for i, shot in enumerate(filtered_shots):
        shot['size'] = marker_sizes[i]

    # === 3. 构建最终标记 ===
    result_markers: List[ShotMarker] = []
    for shot in filtered_shots:
        pid        = shot['player_id']
        is_made    = shot['is_made']
        is_assist  = assist_player_id is not None and shot.get('assist_id') == assist_player_id

        # 头像 / 默认标记类型
        mtype = marker_type or 'default'
        if mtype == 'avatar' and pid in avatar_map:
            actual_type = 'avatar'
            avatar_img  = avatar_map[pid]
        else:
            actual_type = 'default'
            avatar_img  = None

        # 颜色选择
        if team_color:
            color = team_color
        elif is_assist and is_made:
            color = assist_color
        else:
            color = made_color if is_made else missed_color

        alpha          = 0.95 if is_made else 0.75
        marker_symbol  = 'o'  if is_made else 'x'

        marker: ShotMarker = {
            'x'            : shot['x'],
            'y'            : shot['y'],
            'is_made'      : is_made,
            'marker_type'  : actual_type,
            'size'         : shot['size'],
            'alpha'        : alpha,
            'color'        : color,
            'marker_symbol': marker_symbol,
            'border_color' : color,
            'border_width' : border_width
        }

        if actual_type == 'avatar' and avatar_img is not None:
            marker['avatar_image'] = avatar_img

        result_markers.append(marker)

    logger.info(f"成功准备 {len(result_markers)} 个投篮标记")
    return result_markers



# ===================== 图例 / 信息框 =====================

def prepare_legend_spec(
    shot_outcome: str = "made_only",
    chart_type: str = "player",  # 'player' | 'team' | 'player_impact' | 'full_court'
    team_colors: Optional[Dict[str, str]] = None,
    chart_config: Optional[ChartConfigLike] = None,
    player_name: Optional[str] = None,
) -> List[LegendItem]:
    """生成图例规格"""

    made_color = chart_config.get("default_made_shot_color", "#3A7711") if chart_config else "#3A7711"
    missed_color = chart_config.get("default_missed_shot_color", "#C9082A") if chart_config else "#C9082A"
    assist_color = chart_config.get("default_assist_color", "#552583") if chart_config else "#552583"

    legend: List[LegendItem] = []

    if chart_type == "full_court" and team_colors:
        teams = list(team_colors.items())
        ncol = len(teams) * (2 if shot_outcome == "all" else 1)
        for name, color in teams:
            legend.append({"label": f"{name} 命中", "color": color, "marker": "o", "location": "upper center", "bbox_to_anchor": (0.5, 1.05), "ncol": ncol})
            if shot_outcome == "all":
                legend.append({"label": f"{name} 未命中", "color": color, "marker": "x", "alpha": 0.5, "location": "upper center", "bbox_to_anchor": (0.5, 1.05), "ncol": ncol})
    elif chart_type == "player_impact":
        p = player_name or "球员"
        legend.extend([
            {"label": f"{p} 个人得分", "color": made_color, "marker": "o"},
            {"label": "助攻队友得分", "color": assist_color, "marker": "o"},
        ])
    else:
        legend.append({"label": "投篮命中", "color": made_color, "marker": "o"})
        if shot_outcome == "all":
            legend.append({"label": "投篮未命中", "color": missed_color, "marker": "x"})

    return legend


def prepare_info_box_data(
    player_name: str,
    stats: Dict[str, Any],
    avatar_image: Optional[Image.Image] = None,
    creator_info: Optional[str] = None,
) -> InfoBoxData:
    data: InfoBoxData = {"name": player_name, "stats": stats, "creator_info": creator_info or "图表制作者"}
    if avatar_image is not None:
        data["avatar_image"] = avatar_image
    return data


def format_player_stats(raw: Dict[str, Any], include_keys: Optional[List[str]] = None) -> Dict[str, Any]:
    default = {
        "position": "位置",
        "points": "得分",
        "assists": "助攻",
        "rebounds": "篮板",
        "fg_pct": "命中率",
        "three_pct": "三分率",
        "steals": "抢断",
        "blocks": "盖帽",
    }
    keys = include_keys or default.keys()
    res: Dict[str, Any] = {}
    for k in keys:
        if k not in raw:
            continue
        v = raw[k]
        label = default.get(k, k)
        res[label] = f"{v:.1%}" if k.endswith("_pct") and isinstance(v, (int, float)) else v
    return res


# ===================== 坐标转换 =====================

def transform_to_full_court_coordinates(
    half_court_shots: List[Dict[str, Any]],
    game_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """将以篮筐为原点的半场坐标转换成横向全场坐标。

    需求：**仅为了把两队投篮分到左右半场**；不考虑真实进攻方向。
    - 主队 → 左篮筐 (X≈‑417.5)；客队 → 右篮筐 (X≈+417.5)。
    - 保留在半场图中易于理解的几何关系：半场坐标 (x:左右、y:离篮筐距离)。
    """

    try:
        home_id = game_data.get("home_team_id")
        away_id = game_data.get("away_team_id")
        if not home_id or not away_id:
            logger.error("缺少主客队 ID，无法转换全场坐标")
            return []

        HOOP_OFFSET = 470 - 52.5  # 417.5
        LEFT_HOOP_X = -HOOP_OFFSET
        RIGHT_HOOP_X = HOOP_OFFSET

        out: List[Dict[str, Any]] = []
        for shot in half_court_shots:
            try:
                x_half = float(shot["x_legacy"])
                y_half = float(shot["y_legacy"])
                team_id = int(shot["team_id"])
            except (KeyError, TypeError, ValueError):
                logger.warning("跳过无效投篮记录: %s", shot)
                continue

            if team_id == home_id:
                full_x = LEFT_HOOP_X + y_half   # 距离左篮筐的水平方向
                full_y = x_half                 # 保留左右偏移
            elif team_id == away_id:
                full_x = RIGHT_HOOP_X - y_half  # 距离右篮筐的水平方向
                full_y = x_half
            else:
                logger.warning("未知球队 ID=%s", team_id)
                continue

            # 边界保护（理论上不应超出）
            full_x = max(-470.0, min(470.0, full_x))
            full_y = max(-250.0, min(250.0, full_y))

            new_shot = shot.copy()
            new_shot["x"] = full_x
            new_shot["y"] = full_y
            out.append(new_shot)

        logger.info("全场坐标转换完成，共 %d 点", len(out))
        return out

    except Exception as e:  # pragma: no cover
        logger.error("全场坐标转换失败: %s", e, exc_info=True)
        return []

