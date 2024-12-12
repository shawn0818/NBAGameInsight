import matplotlib.pyplot as plt
import matplotlib.colors as colors
from matplotlib.patches import Circle, Rectangle, Arc
from matplotlib.offsetbox import OffsetImage
import squarify
import logging
from typing import Optional, Dict, Any, List
import numpy as np
from pathlib import Path
import pandas as pd

class NBAVisualizer:
    """NBA数据可视化基类"""
    def __init__(self, theme: str = "default"):
        self.theme = theme
        self.setup_style()
        
        # 定义通用的颜色方案
        self.team_colors = {
            "LAL": {  # 湖人队
                "primary": [84/255, 44/255, 129/255],  # 紫色
                "secondary": [250/255, 182/255, 36/255]  # 金色
            }
        }
        
    def setup_style(self):
        """设置matplotlib的基础样式"""
        plt.style.use('fivethirtyeight')
        
    @staticmethod
    def save_figure(fig, output_path: str, dpi: int = 300):
        """统一的图表保存方法"""
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_path, bbox_inches='tight', dpi=dpi)
            plt.close(fig)
            logging.info(f"Figure saved successfully to {output_path}")
        except Exception as e:
            logging.error(f"Error saving figure: {e}")

    def plot_assist_network(self, df: pd.DataFrame, title: str = "Assist Network", output_path: str = None) -> plt.Figure:
        """
        绘制助攻网络图。

        Args:
            df: 包含助攻数据的DataFrame, 至少需要包括'personId'（助攻者）和'assistPersonId'（被助攻者）列。
            title: 图表标题。
            output_path: 图表保存路径。

        Returns:
            plt.Figure: 绘制好的助攻网络图。
        """
        # 创建一个有向图
        G = nx.DiGraph()

        # 添加边（助攻关系）
        for _, row in df.iterrows():
            if row['assistPersonId'] is not None and not pd.isna(row['assistPersonId']):
                # 添加节点（如果它们不存在）
                if not G.has_node(row['personId']):
                    G.add_node(row['personId'])
                if not G.has_node(row['assistPersonId']):
                    G.add_node(row['assistPersonId'])
                # 添加边
                G.add_edge(row['assistPersonId'], row['personId'])

        # 绘制网络图
        fig, ax = plt.subplots(figsize=(12, 12))
        pos = nx.spring_layout(G)  # 使用spring_layout布局
        nx.draw(G, pos, with_labels=True, node_color='skyblue', node_size=1500, edge_color='gray', linewidths=1, font_size=15, font_weight='bold', arrowsize=20, alpha=0.7, ax=ax)

        if title:
            ax.set_title(title)

        # 保存图形
        if output_path:
            self.save_figure(fig, output_path)

        return fig

class ShotChartVisualizer(NBAVisualizer):
    """投篮图可视化类"""
    
    def __init__(self, theme: str = "default"):
        super().__init__(theme)
        self.court_colors = {
            "background": "#FDF5E6",
            "paint": "#fab624",
            "lines": "black"
        }
        
    def draw_court(self, ax: plt.Axes, color: str = 'black', lw: int = 2) -> plt.Axes:
        """绘制球场"""
        # 篮筐
        hoop = Circle((0, 0), radius=7.5, linewidth=lw, color=color, fill=False)
        
        # 篮板
        backboard = Rectangle((-30, -7.5), 60, -1, linewidth=lw, color=color)
        
        # 油漆区
        outer_box = Rectangle((-80, -47.5), 160, 190, linewidth=lw, 
                            color=color, fill=False, zorder=0)
        inner_box = Rectangle((-60, -47.5), 120, 190, linewidth=lw,
                            color=color, fill=False, zorder=0)
        
        # 罚球线和罚球圈
        top_free_throw = Arc((0, 142.5), 120, 120, theta1=0, theta2=180,
                            linewidth=lw, color=color, fill=False)
        bottom_free_throw = Arc((0, 142.5), 120, 120, theta1=180, theta2=0,
                              linewidth=lw, color=color, linestyle='dashed')
        
        # 限制区
        restricted = Arc((0, 0), 80, 80, theta1=0, theta2=180, linewidth=lw,
                        color=color)
        
        # 三分线
        corner_three_a = Rectangle((-220, -47.5), 0, 138, linewidth=lw,
                                 color=color)
        corner_three_b = Rectangle((220, -47.5), 0, 138, linewidth=lw,
                                 color=color)
        three_arc = Arc((0, 0), 475, 475, theta1=22, theta2=158, linewidth=lw,
                       color=color)
        
        # 中场
        center_outer_arc = Arc((0, 422.5), 120, 120, theta1=180, theta2=0,
                             linewidth=lw, color=color)
        
        court_elements = [
            hoop, backboard, outer_box, inner_box, top_free_throw,
            bottom_free_throw, restricted, corner_three_a, corner_three_b,
            three_arc, center_outer_arc
        ]
        
        # 绘制油漆区背景
        paint_background = Rectangle(
            (-80, -47.5), 160, 190,
            linewidth=lw,
            color=self.court_colors["paint"],
            fill=True,
            zorder=-1
        )
        court_elements.append(paint_background)
        
        # 添加所有元素到图形中
        for element in court_elements:
            ax.add_patch(element)
            
        return ax

    def plot_shot_chart(self, df: pd.DataFrame, title: str = "Shot Chart", output_path: str = None):
        """
        绘制投篮热图。

        Args:
            df: 包含投篮数据的DataFrame。
            title: 图表标题。
            output_path: 图表保存路径。
        """
        # 创建一个新的图形和坐标轴
        fig, ax = plt.subplots(figsize=(12, 11))

        # 绘制球场
        self.draw_court(ax, color="black")

        # 筛选出投篮数据
        shots = df[df['actionType'].isin(['2pt', '3pt'])]

        # 根据投篮结果分配颜色
        colors = ['red' if result == 'Missed' else 'green' for result in shots['shotResult']]

        # 绘制投篮点
        ax.scatter(shots['xLegacy'], shots['yLegacy'], c=colors, alpha=0.7, edgecolors='k')

        # 设置图形标题和坐标轴范围
        ax.set_title(title)
        ax.set_xlim(-250, 250)
        ax.set_ylim(-50, 422.5)  # 调整y轴范围以适应整个半场

        # 隐藏坐标轴刻度
        ax.set_xticks([])
        ax.set_yticks([])

        # 保存图形
        if output_path:
            self.save_figure(fig, output_path)

        return fig

class TreeMapVisualizer(NBAVisualizer):
    """树图可视化类"""

    def __init__(self, theme: str = "default"):
        super().__init__(theme)

    def normalize_scores(self, data: pd.DataFrame) -> pd.DataFrame:
        """标准化得分数据"""
        df = data.copy()
        df['Score_Normalized'] = df['statistics_points'] / df['statistics_points'].sum()
        return df

    def map_colors(self, data: pd.DataFrame, player_id: str, team_id: str = "LAL", color_by: str = "Score_Normalized") -> List:
        """
        映射颜色方案

        Args:
            data: 数据DataFrame
            player_id: 要突出显示的球员ID
            team_id: 球队ID
            color_by: 用于映射颜色的列名，默认为 "Score_Normalized"
        """
        team_colors = self.team_colors.get(team_id, {"primary": [0.2, 0.2, 0.2], "secondary": [0.8, 0.8, 0.8]})
        
        # 根据指定的列 (默认为标准化得分) 生成颜色映射
        min_val = data[color_by].min()
        max_val = data[color_by].max()
        norm = colors.Normalize(min_val, max_val)

        color_mapped = []
        for _, row in data.iterrows():
            if row['personId'] == int(player_id):
                color_mapped.append(team_colors["secondary"])
            else:
                intensity = norm(row[color_by])
                min_lightness = 0.6
                lightness = min_lightness + (1 - min_lightness) * intensity
                adjusted_color = [
                    team_colors["primary"][0] * lightness,
                    team_colors["primary"][1] * lightness,
                    team_colors["primary"][2] * lightness,
                    1
                ]
                color_mapped.append(adjusted_color)

        return color_mapped

    def create_labels(self, data: pd.DataFrame, label_fields: List[str] = None) -> List[str]:
        """
        创建标签

        Args:
            data: 数据DataFrame
            label_fields: 要包含在标签中的字段列表，默认为 None
        """
        if label_fields is None:
            label_fields = ['name', 'statistics_points', 'statistics_fieldGoalsPercentage']

        labels = []
        for _, row in data.iterrows():
            label_parts = []
            for field in label_fields:
                if field == 'statistics_fieldGoalsPercentage':
                    label_parts.append(f"FG%: {row[field]*100:.1f}")
                elif 'statistics' in field:
                    label_parts.append(f"{field.split('_')[1]}: {row[field]}")
                else:
                    label_parts.append(f"{field}: {row[field]}")
            labels.append("\n".join(label_parts))
        return labels

    def plot(self,
             data: pd.DataFrame,
             player_id: str,
             team_id: str = "LAL",
             title: Optional[str] = None,
             output_path: Optional[str] = None,
             color_by: str = "Score_Normalized",
             label_fields: Optional[List[str]] = None) -> plt.Figure:
        """
        绘制树图

        Args:
            data: 球员数据DataFrame
            player_id: 高亮显示的球员ID
            team_id: 球队ID
            title: 图表标题
            output_path: 输出路径
            color_by: 用于映射颜色的列名，默认为 "Score_Normalized"
            label_fields: 标签中要显示的字段列表
        """
        try:
            # 数据预处理
            filtered_data = data[data['statistics_points'] > 0].copy()
            filtered_data = self.normalize_scores(filtered_data)

            # 创建图形
            fig, ax = plt.subplots(1, figsize=(12, 6))
            fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

            # 准备绘图数据
            colors = self.map_colors(filtered_data, player_id, team_id, color_by)
            labels = self.create_labels(filtered_data, label_fields)

            # 绘制树图
            squarify.plot(
                sizes=filtered_data['Score_Normalized'],
                label=labels,
                color=colors,
                alpha=0.8,
                ax=ax,
                linewidth=2,
                edgecolor='white'
            )

            if title:
                plt.title(title)

            plt.axis('off')

            if output_path:
                self.save_figure(fig, output_path)

            return fig

        except Exception as e:
            logging.error(f"Error plotting treemap: {e}")
            raise

class RadarChartVisualizer(NBAVisualizer):
    """雷达图可视化类，用于展示球员各项数据"""

    def __init__(self, theme: str = "default"):
        super().__init__(theme)

    def plot(self,
             stats: Dict[str, float],
             max_values: Dict[str, float],
             title: Optional[str] = None,
             output_path: Optional[str] = None,
             labels: Optional[List[str]] = None) -> plt.Figure:
        """
        绘制雷达图

        Args:
            stats: 球员数据字典，如 {'points': 25, 'rebounds': 10, ...}
            max_values: 各项数据的最大值参考
            title: 图表标题
            output_path: 输出路径
            labels: 自定义标签
        """
        # 数据归一化
        values = np.array([stats[cat] / max_values[cat] for cat in stats.keys()])

        # 设置雷达图的角度
        categories = list(stats.keys())
        num_vars = len(categories)
        angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
        
        # 闭合多边形
        values = np.concatenate((values, [values[0]]))
        angles += angles[:1]

        # 创建图形
        fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))

        # 绘制雷达图
        ax.plot(angles, values, linewidth=2, linestyle='solid')
        ax.fill(angles, values, alpha=0.25)

        # 设置刻度和标签
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels if labels else categories)

        # 设置y轴范围
        ax.set_ylim(0, 1)

        if title:
            plt.title(title, size=20, y=1.1)

        if output_path:
            self.save_figure(fig, output_path)

        return fig

class HeatMapVisualizer(NBAVisualizer):
    """热图可视化类，用于展示投篮热点图"""

    def __init__(self, theme: str = "default"):
        super().__init__(theme)
        self.shot_chart_viz = ShotChartVisualizer(theme)

    def plot(self,
             shot_data: pd.DataFrame,
             title: Optional[str] = None,
             output_path: Optional[str] = None) -> plt.Figure:
        """
        绘制投篮热图

        Args:
            shot_data: 包含投篮位置数据的DataFrame，应包含'xLegacy'和'yLegacy'列。
            title: 图表标题
            output_path: 输出路径
        """
        fig, ax = plt.subplots(figsize=(12, 11))

        # 绘制球场背景
        self.shot_chart_viz.draw_court(ax, color="black")

        # 创建热图
        heatmap, xedges, yedges = np.histogram2d(shot_data['xLegacy'], shot_data['yLegacy'], bins=50, range=[[-250, 250], [-50, 420]])
        extent = [xedges[0], xedges[-1], yedges[0], yedges[-1]]

        # 使用imshow绘制热图
        img = ax.imshow(heatmap.T, extent=extent, origin='lower', cmap='hot', alpha=0.8)

        # 设置标题
        if title:
            ax.set_title(title)

        # 移除坐标轴标签和刻度
        ax.set_xticks([])
        ax.set_yticks([])

        # 设置坐标轴范围
        ax.set_xlim([-250, 250])
        ax.set_ylim([-50, 422.5])

        # 添加颜色条
        cbar = fig.colorbar(img, ax=ax)
        cbar.set_label('Density')

        # 保存图形
        if output_path:
            self.save_figure(fig, output_path)

        return fig