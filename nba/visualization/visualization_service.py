#nba/visualization/visualization_service.py
from nba.visualization.shot_charts_renderer import ShotChartsRenderer


class VisualizationService:
    """NBA数据可视化服务 - 统一协调各类图表生成"""

    def __init__(self):
        """初始化可视化服务，各渲染器使用自己的默认配置"""
        # 直接实例化各渲染器，无需传递配置
        self.shot_charts_renderer = ShotChartsRenderer()
        # 未来可能的其他渲染器
        # self.stats_renderer = StatsRenderer()
        # ...

    # 统一的图表生成入口
    def generate_visualization(self, vis_type, **params):
        """根据类型生成不同的可视化"""
        if vis_type == "shot_chart":
            return self.shot_charts_renderer.generate_shot_charts(**params)
        elif vis_type == "impact_chart":
            return self.shot_charts_renderer.generate_player_scoring_impact_charts(**params)
        elif vis_type == "full_court":
            return self.shot_charts_renderer.generate_full_court_shot_chart(**params)
        # 未来可添加更多类型...
        else:
            raise ValueError(f"不支持的可视化类型: {vis_type}")

    # 便捷方法 - 直接调用特定图表功能
    def generate_shot_charts(self, **params):
        return self.shot_charts_renderer.generate_shot_charts(**params)

    def generate_impact_charts(self, **params):
        return self.shot_charts_renderer.generate_player_scoring_impact_charts(**params)

    # 资源管理方法
    def clear_cache(self):
        """清理所有可视化服务的缓存"""
        self.shot_charts_renderer.clear_cache()
        # 清理其他服务的缓存...

    def close(self):
        """关闭所有可视化服务"""
        self.shot_charts_renderer.close()
        # 关闭其他服务...