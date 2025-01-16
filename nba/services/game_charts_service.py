import matplotlib.pyplot as plt
import matplotlib.colors as colors
from matplotlib.patches import Circle, Rectangle, Arc
from matplotlib.offsetbox import OffsetImage, AnnotationBbox  # 添加 AnnotationBbox 导入
import squarify
import logging
from typing import Optional, Dict, Any, List, Tuple
import numpy as np
from pathlib import Path
import pandas as pd
import seaborn as sns
import networkx as nx
from utils.time_handler import TimeParser, BasketballGameTime


class NBAVisualizer:
    """NBA数据可视化基类

    提供了基础的图表绘制功能，包括：
    1. 统一的样式设置
    2. 通用的颜色方案
    3. 图表保存功能
    4. 错误处理机制
    """

    def __init__(self, theme: str = "default"):
        """初始化可视化器

        Args:
            theme: 主题名称，默认为 "default"
        """
        self.theme = theme
        self.setup_style()
        self.logger = logging.getLogger(self.__class__.__name__)  # 初始化日志记录器

        # 定义通用的颜色方案
        self.team_colors = {
            "LAL": {  # 湖人队
                "primary": [84 / 255, 44 / 255, 129 / 255],  # 紫色
                "secondary": [250 / 255, 182 / 255, 36 / 255]  # 金色
            },
            # ... 其他球队颜色配置
        }

    def setup_style(self):
        """设置matplotlib的基础样式"""
        plt.style.use('fivethirtyeight')
        plt.rcParams['font.family'] = ['Microsoft YaHei', 'SimHei', 'sans-serif']

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


class GameFlowVisualizer(NBAVisualizer):
    """比赛流程可视化类

    专门用于可视化比赛进程相关的数据，包括：
    1. 比分流程图
    2. 球员得分分布
    3. 球队表现对比
    """

    def plot_score_flow(self,
                        plays: List[Dict[str, Any]],
                        home_team: str,
                        away_team: str,
                        title: Optional[str] = None,
                        output_path: Optional[str] = None) -> plt.Figure:
        """绘制比分流程图"""
        fig, ax = plt.subplots(figsize=(15, 8))

        # 准备数据
        times = []
        score_diffs = []
        current_diff = 0

        for play in sorted(plays, key=lambda x: (x['period'], x['time'])):
            if 'MISS' in play['description']:
                continue

            # 计算得分
            points = 3 if '3PT' in play['description'] else (1 if 'Free Throw' in play['description'] else 2)
            if play['team'] == home_team:
                current_diff += points
            else:
                current_diff -= points

            # 添加数据点
            period = play['period']
            time = self._convert_time_to_minutes(play['time'], period)
            times.append(time)
            score_diffs.append(current_diff)

        # 绘制曲线
        ax.plot(times, score_diffs, linewidth=2, label=f"{home_team} vs {away_team}")
        ax.fill_between(times, score_diffs, 0, alpha=0.1)

        # 添加零线和四节分隔线
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.2)
        for i in range(1, 4):
            ax.axvline(x=i * 12, color='gray', linestyle='--', alpha=0.2)

        # 设置标签
        ax.set_xlabel('比赛时间（分钟）')
        ax.set_ylabel('分差（主队领先）')
        if title:
            ax.set_title(title)
        ax.legend()

        # 保存图形
        if output_path:
            self.save_figure(fig, output_path)

        return fig

    def _convert_time_to_minutes(self, time_str: str, period: int) -> float:
        """将比赛时间转换为总分钟数

        使用 TimeParser 处理 ISO8601 格式的时间

        Args:
            time_str: ISO8601格式的时间字符串 (如 "PT11M15S")
            period: 比赛节数

        Returns:
            float: 转换后的总分钟数
        """
        try:
            # 使用 TimeParser 解析时间
            seconds = TimeParser.parse_iso8601_duration(time_str)
            minutes = seconds / 60

            # 转换为比赛总分钟数
            return (period - 1) * 12 + (12 - minutes)

        except Exception as e:
            self.logger.error(f"时间格式转换错误: {time_str}, {str(e)}")
            return 0.0


class PlayerPerformanceVisualizer(NBAVisualizer):
    """球员表现可视化类"""

    def plot_shot_distribution(self,
                               shot_data: pd.DataFrame,
                               player_name: str,
                               title: Optional[str] = None,
                               output_path: Optional[str] = None) -> plt.Figure:
        """绘制投篮分布图"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 8))

        # 1. 投篮位置分布饼图
        shot_zones = shot_data['zone'].value_counts()
        ax1.pie(shot_zones, labels=shot_zones.index, autopct='%1.1f%%')
        ax1.set_title('投篮位置分布')

        # 2. 命中率条形图
        zone_percentages = shot_data.groupby('zone')['made'].mean()
        zone_percentages.plot(kind='bar', ax=ax2)
        ax2.set_title('各区域命中率')
        ax2.set_ylabel('命中率')

        if title:
            fig.suptitle(title)

        if output_path:
            self.save_figure(fig, output_path)

        return fig

    def plot_performance_timeline(self,
                                  plays: List[Dict[str, Any]],
                                  player_name: str,
                                  title: Optional[str] = None,
                                  output_path: Optional[str] = None) -> plt.Figure:
        """绘制球员表现时间线"""
        fig, ax = plt.subplots(figsize=(15, 8))

        # 准备数据
        events = []
        times = []
        colors = []

        for play in plays:
            if player_name in play['description']:
                time = self._convert_time_to_minutes(play['time'], play['period'])
                times.append(time)
                events.append(play['description'])

                # 根据事件类型设置颜色
                if 'MISS' in play['description']:
                    colors.append('red')
                elif any(x in play['description'] for x in ['3PT', '2PT', 'Free Throw']):
                    colors.append('green')
                else:
                    colors.append('blue')

        # 绘制时间线
        ax.scatter(times, [0] * len(times), c=colors, s=100)

        # 添加事件标签
        for i, (time, event) in enumerate(zip(times, events)):
            ax.annotate(event, (time, 0), xytext=(0, 10 if i % 2 == 0 else -10),
                        textcoords='offset points', ha='center', rotation=45)

        # 设置图表样式
        ax.set_yticks([])
        ax.set_xlabel('比赛时间（分钟）')
        if title:
            ax.set_title(title)

        if output_path:
            self.save_figure(fig, output_path)

        return fig

    def _convert_time_to_minutes(self, time_str: str, period: int) -> float:
        """将比赛时间转换为总分钟数

        使用 TimeParser 处理 ISO8601 格式的时间

        Args:
            time_str: ISO8601格式的时间字符串 (如 "PT11M15S")
            period: 比赛节数

        Returns:
            float: 转换后的总分钟数
        """
        try:
            # 使用 TimeParser 解析时间
            seconds = TimeParser.parse_iso8601_duration(time_str)
            minutes = seconds / 60

            # 转换为比赛总分钟数
            return (period - 1) * 12 + (12 - minutes)

        except Exception as e:
            self.logger.error(f"时间格式转换错误: {time_str}, {str(e)}")
            return 0.0


class TeamPerformanceVisualizer(NBAVisualizer):
    """球队表现可视化类"""

    def plot_team_comparison(self,
                             home_stats: Dict[str, Any],
                             away_stats: Dict[str, Any],
                             home_team: str,
                             away_team: str,
                             title: Optional[str] = None,
                             output_path: Optional[str] = None) -> plt.Figure:
        """绘制球队数据对比图"""
        fig, ax = plt.subplots(figsize=(12, 8))

        # 准备数据
        metrics = [
            'fieldGoalsPercentage', 'threePointersPercentage',
            'freeThrowsPercentage', 'reboundsTotal',
            'assists', 'steals', 'blocks', 'turnovers'
        ]

        x = np.arange(len(metrics))
        width = 0.35

        # 绘制条形图
        home_data = [home_stats.get(m, 0) for m in metrics]
        away_data = [away_stats.get(m, 0) for m in metrics]

        ax.bar(x - width / 2, home_data, width, label=home_team)
        ax.bar(x + width / 2, away_data, width, label=away_team)

        # 设置图表样式
        ax.set_xticks(x)
        ax.set_xticklabels(metrics, rotation=45)
        ax.legend()

        if title:
            ax.set_title(title)

        if output_path:
            self.save_figure(fig, output_path)

        return fig

    def plot_scoring_runs(self,
                          plays: List[Dict[str, Any]],
                          title: Optional[str] = None,
                          output_path: Optional[str] = None) -> plt.Figure:
        """绘制得分高潮图"""
        fig, ax = plt.subplots(figsize=(15, 8))

        # 实现得分高潮的可视化
        # ...（具体实现）

        return fig


class InteractionVisualizer(NBAVisualizer):
    """球员互动可视化类"""

    def plot_assist_network(self,
                          plays: List[Dict[str, Any]],
                          team_name: str,
                          title: Optional[str] = None,
                          output_path: Optional[str] = None) -> plt.Figure:
        """绘制助攻网络图"""
        fig, ax = plt.subplots(figsize=(12, 12))
        
        # 创建有向图
        G = nx.DiGraph()
        
        # 统计助攻数据
        assist_counts = {}
        for play in plays:
            if play.get('action_type') == 'assist' and play.get('team') == team_name:
                assister = play.get('player_name')
                scorer = play.get('scoring_player', {}).get('name')
                if assister and scorer:
                    key = (assister, scorer)
                    assist_counts[key] = assist_counts.get(key, 0) + 1
        
        # 添加边和节点
        for (assister, scorer), weight in assist_counts.items():
            G.add_edge(assister, scorer, weight=weight)
        
        # 设置布局
        pos = nx.spring_layout(G)
        
        # 绘制网络
        nx.draw_networkx_nodes(G, pos, node_color='lightblue',
                             node_size=1000, alpha=0.7, ax=ax)
        nx.draw_networkx_edges(G, pos, edge_color='gray',
                             width=[G[u][v]['weight'] for u, v in G.edges()],
                             alpha=0.5, ax=ax)
        nx.draw_networkx_labels(G, pos, ax=ax)
        
        if title:
            ax.set_title(title)
        
        if output_path:
            self.save_figure(fig, output_path)
        
        return fig


class LineupAnalysisVisualizer(NBAVisualizer):
    """阵容分析可视化类"""

    def plot_lineup_performance(self,
                                lineup_data: pd.DataFrame,
                                title: Optional[str] = None,
                                output_path: Optional[str] = None) -> plt.Figure:
        """绘制阵容表现分析图"""
        fig, ax = plt.subplots(figsize=(12, 8))

        # 实现阵容分析的可视化
        # ...（具体实现）

        return fig


class ShotChartVisualizer(NBAVisualizer):
    """投篮图可视化类

    用于生成详细的投篮图表，支持：
    1. 标准NBA球场绘制
    2. 投篮点位显示
    3. 命中率热图
    4. 球员头像和信息展示
    """

    def __init__(self, theme: str = "default"):
        super().__init__(theme)
        # NBA标准球场尺寸（单位：英尺）
        self.court_dimensions = {
            "court_length": 94,  # 球场长度
            "court_width": 50,  # 球场宽度
            "three_point_radius": 23.75,  # 三分线弧度半径(2013-14赛季后)
            "three_point_side_radius": 22,  # 三分线底角半径
            "three_point_side_y": 14,  # 三分线直线部分的纵向距离
            "paint_width": 16,  # 油漆区宽度
            "paint_height": 19,  # 油漆区高度
            "free_throw_line_distance": 15,  # 罚球线距离
            "restricted_area_radius": 4,  # 禁区半径
            "hoop_diameter": 1.5,  # 篮筐直径
            "backboard_width": 6,  # 篮板宽度
            "backboard_to_baseline": 4  # 篮板到底线距离
        }

        # 坐标系转换因子（将英尺转换为图表坐标）
        self.scale = 10

        self.court_colors = {
            "background": "#FDF5E6",
            "paint": "#fab624",
            "lines": "black",
            "made": "#00ff00",  # 命中-绿色
            "missed": "#ff0000",  # 未命中-红色
            "threept": "#0000ff",  # 三分线-蓝色
            "restricted": "#ff69b4"  # 限制区-粉色
        }

        # 添加水印和标签的样式
        self.watermark_style = {
            "fontsize": 10,
            "color": "#666666",
            "alpha": 0.5
        }

        # 添加球员信息样式
        self.player_info_style = {
            "fontsize": 16,
            "fontweight": "bold",
            "color": "#333333"
        }

    def draw_court(self, ax: plt.Axes, color: str = 'black', lw: int = 2) -> plt.Axes:
        """绘制标准NBA球场"""
        # 转换尺寸到图表坐标
        d = self.court_dimensions
        s = self.scale

        # 篮筐
        hoop = Circle((0, 0), radius=d['hoop_diameter'] / 2 * s,
                      linewidth=lw, color=color, fill=False)

        # 篮板
        backboard = Rectangle(
            (-d['backboard_width'] / 2 * s, -d['backboard_to_baseline'] * s),
            d['backboard_width'] * s,
            lw / self.scale,
            linewidth=lw,
            color=color
        )

        # 油漆区
        paint = Rectangle(
            (-d['paint_width'] / 2 * s, 0),
            d['paint_width'] * s,
            d['paint_height'] * s,
            linewidth=lw,
            color=color,
            fill=False,
            zorder=0
        )

        # 罚球圈
        free_throw_circle = Arc(
            (0, d['free_throw_line_distance'] * s),
            d['paint_width'] * s,
            d['paint_width'] * s,
            theta1=0,
            theta2=180,
            linewidth=lw,
            color=color,
            fill=False
        )

        # 限制区
        restricted = Arc(
            (0, 0),
            d['restricted_area_radius'] * 2 * s,
            d['restricted_area_radius'] * 2 * s,
            theta1=0,
            theta2=180,
            linewidth=lw,
            color=self.court_colors["restricted"]
        )

        # 三分线
        three_point_side_length = d['three_point_side_y'] * s
        three_point_side_left = Rectangle(
            (-d['court_width'] / 2 * s, 0),
            0,
            three_point_side_length,
            linewidth=lw,
            color=self.court_colors["threept"]
        )
        three_point_side_right = Rectangle(
            (d['court_width'] / 2 * s, 0),
            0,
            three_point_side_length,
            linewidth=lw,
            color=self.court_colors["threept"]
        )
        three_point_arc = Arc(
            (0, 0),
            d['three_point_radius'] * 2 * s,
            d['three_point_radius'] * 2 * s,
            theta1=22,
            theta2=158,
            linewidth=lw,
            color=self.court_colors["threept"]
        )

        court_elements = [
            hoop, backboard, paint, free_throw_circle, restricted,
            three_point_side_left, three_point_side_right, three_point_arc
        ]

        # 绘制油漆区背景
        paint_background = Rectangle(
            (-d['paint_width'] / 2 * s, 0),
            d['paint_width'] * s,
            d['paint_height'] * s,
            facecolor=self.court_colors["paint"],
            alpha=0.3,
            zorder=-1
        )
        court_elements.append(paint_background)

        # 添加所有元素到图形中
        for element in court_elements:
            ax.add_patch(element)

        # 设置坐标轴范围
        ax.set_xlim(
            -d['court_width'] / 2 * s - 5,
            d['court_width'] / 2 * s + 5
        )
        ax.set_ylim(
            -5,
            d['three_point_radius'] * s + 5
        )

        return ax

    def add_player_headshot(self,
                            ax: plt.Axes,
                            player_id: int,
                            position: Tuple[float, float] = (0.02, 0.85),
                            zoom: float = 0.15) -> None:
        """
        添加球员头像

        Args:
            ax: matplotlib轴对象
            player_id: NBA官方球员ID
            position: 头像在图中的位置(左下角坐标，范围0-1)
            zoom: 头像缩放比例
        """
        try:
            # 构建NBA官方头像URL
            headshot_url = f"https://ak-static.cms.nba.com/wp-content/uploads/headshots/nba/latest/260x190/{player_id}.png"

            # 下载并读取图片
            import requests
            from PIL import Image
            from io import BytesIO

            response = requests.get(headshot_url)
            img = Image.open(BytesIO(response.content))

            # 创建OffsetImage对象
            imagebox = OffsetImage(img, zoom=zoom)
            imagebox.image.axes = ax

            # 创建AnnotationBbox对象
            ab = AnnotationBbox(imagebox,
                                position,
                                xycoords='axes fraction',  # 修改坐标系为轴的分数坐标
                                frameon=False,
                                box_alignment=(0, 0))

            # 添加到图表
            ax.add_artist(ab)

        except Exception as e:
            self.logger.warning(f"Failed to add player headshot: {e}")

    def add_watermark(self,
                      ax: plt.Axes,
                      text: str,
                      position: Tuple[float, float] = (0.98, 0.02)) -> None:
        """
        添加水印信息

        Args:
            ax: matplotlib轴对象
            text: 水印文本
            position: 水印位置(右下角坐标，范围0-1)
        """
        ax.text(position[0], position[1],
                text,
                transform=ax.transAxes,
                ha='right',
                va='bottom',
                **self.watermark_style)

    def plot_shot_chart(self,
                        shot_data: pd.DataFrame,
                        player_id: Optional[int] = None,
                        player_name: Optional[str] = None,
                        team_name: Optional[str] = None,
                        title: str = "Shot Chart",
                        output_path: Optional[str] = None,
                        show_misses: bool = True,
                        show_makes: bool = True,
                        annotate: bool = False,
                        add_player_photo: bool = True,
                        creator_info: Optional[str] = None) -> plt.Figure:
        """
        绘制投篮热图。

        Args:
            shot_data: 包含投篮数据的DataFrame
            player_id: NBA官方球员ID
            player_name: 球员名称
            team_name: 球队名称
            title: 图表标题
            output_path: 图表保存路径
            show_misses: 是否显示未命中的投篮
            show_makes: 是否显示命中的投篮
            annotate: 是否添加投篮注释
            add_player_photo: 是否添加球员照片
            creator_info: 制作者信息
        """
        # 创建图形
        fig = plt.figure(figsize=(12, 11))
        ax = fig.add_subplot(1, 1, 1)

        # 绘制球场
        self.draw_court(ax)

        # 处理投篮数据
        makes = misses = 0
        for _, shot in shot_data.iterrows():
            x, y = shot['xLegacy'], shot['yLegacy']
            made = shot['shotResult'] != "Missed"

            if made:
                makes += 1
            else:
                misses += 1

            # 根据命中情况选择标记样式
            if made and show_makes:
                marker = 'o'
                color = self.court_colors["made"]
                alpha = 0.8
            elif not made and show_misses:
                marker = 'x'
                color = self.court_colors["missed"]
                alpha = 0.6
            else:
                continue

            # 绘制投篮点
            ax.scatter(x, y, c=[color], marker=marker, s=100, alpha=alpha)  # color需要是数组

            # 添加注释
            if annotate:
                ax.annotate(shot['description'],
                            (x, y),
                            xytext=(5, 5),
                            textcoords='offset points',
                            fontsize=8,
                            alpha=0.7)

        # 添加球员头像
        if add_player_photo and player_id:
            self.add_player_headshot(ax, player_id)

        # 添加球员信息
        if player_name:
            total_shots = makes + misses
            fg_pct = makes / total_shots if total_shots > 0 else 0
            player_info = (f"{player_name}\n"
                           f"FG: {makes}/{total_shots} ({fg_pct:.1%})")
            ax.text(0.02, 0.98, player_info,
                    transform=ax.transAxes,
                    va='top',
                    **self.player_info_style)

        # 添加制作者信息水印
        if creator_info:
            self.add_watermark(ax, creator_info)

        # 设置图表样式
        ax.set_xlim(-self.court_dimensions['court_width'] / 2 * self.scale,
                    self.court_dimensions['court_width'] / 2 * self.scale)
        ax.set_ylim(-self.court_dimensions['restricted_area_radius'] * self.scale,
                    self.court_dimensions['three_point_radius'] * self.scale + 5)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_facecolor(self.court_colors["background"])

        # 添加图例
        legend_elements = []
        if show_makes:
            legend_elements.append(plt.Line2D([0], [0], marker='o', color='w',
                                              markerfacecolor=self.court_colors["made"],
                                              label=f'命中 ({makes})', markersize=10))
        if show_misses:
            legend_elements.append(plt.Line2D([0], [0], marker='x', color='w',
                                              markerfacecolor=self.court_colors["missed"],
                                              label=f'未命中 ({misses})', markersize=10))
        ax.legend(handles=legend_elements, loc='upper right')

        if title:
            ax.set_title(title, pad=20, fontsize=16, fontweight='bold')

        # 保存图形
        if output_path:
            self.save_figure(fig, output_path)

        return fig

    def plot_shot_zones(self,
                        shot_data: pd.DataFrame,
                        title: Optional[str] = None,
                        output_path: Optional[str] = None) -> plt.Figure:
        """
        绘制投篮区域分布图

        Args:
            shot_data: 包含投篮数据的DataFrame
            title: 图表标题
            output_path: 输出路径
        """
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))

        # 1. 左图：球场投篮热图
        self.draw_court(ax1)

        # 创建热图数据
        x = shot_data['xLegacy'].values
        y = shot_data['yLegacy'].values
        heatmap, xedges, yedges = np.histogram2d(x, y, bins=50)

        # 使用插值来平滑热图
        extent = [xedges[0], xedges[-1], yedges[0], yedges[-1]]
        ax1.imshow(heatmap.T, extent=extent, origin='lower',
                   cmap='hot', alpha=0.6)

        # 2. 右图：各区域命中率
        # 确保 shot_data 包含 'zone' 和 'made' 列
        if 'zone' in shot_data.columns and 'made' in shot_data.columns:
            zones = shot_data.groupby('zone').agg({
                'shotResult': ['count', lambda x: (x != 'Missed').sum()]
            })
            zones.columns = ['总数', '命中数']
            zones['命中率'] = zones['命中数'] / zones['总数']

            zones['命中率'].plot(kind='bar', ax=ax2)
            ax2.set_title('各区域命中率')
            ax2.set_ylabel('命中率')
            ax2.set_xlabel('投篮区域')
        else:
            self.logger.warning("shot_data缺少 'zone' 或 'made' 列，无法绘制各区域命中率图")
            ax2.text(0.5, 0.5, "数据缺失", horizontalalignment='center', verticalalignment='center')
            ax2.axis('off')

        if title:
            fig.suptitle(title)

        if output_path:
            self.save_figure(fig, output_path)

        return fig
