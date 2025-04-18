"""
图表生成命令模块 - 包含所有与图表生成相关的命令

支持半场投篮图、全场投篮图、球员影响力图等类型的生成
"""
from typing import Dict, Optional, Any


from commands.base_command import NBACommand, error_handler


class ChartCommand(NBACommand):
    """半场图表生成命令 (球队+球员)"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("半场投篮图表生成")

        # Call the unified method in NBAService
        app.chart_paths = app.nba_service.generate_shot_charts(
            team=app.config.team,
            player_name=app.config.player,
            chart_type="both",  # Generate both team and player charts
            court_type="half",
            shot_outcome="made_only" # Default to made only
        )

        if app.chart_paths:
            print(f"✓ 成功生成 {len(app.chart_paths)} 个半场图表:")
            for chart_type, chart_path in app.chart_paths.items():
                print(f"  - {chart_type}: {chart_path}")
            return True
        else:
            print("× 半场图表生成失败")
            return False


class FullCourtChartCommand(NBACommand):
    """全场投篮图生成命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("全场投篮图表生成")

        # Call the unified method with court_type='full'
        full_court_paths = app.nba_service.generate_shot_charts(
            team=app.config.team,
            player_name=None,
            chart_type="team",
            court_type="full",
            shot_outcome="made_only"
        )

        if full_court_paths:
            print(f"✓ 成功生成全场图表:")
            chart_key = next(iter(full_court_paths), None)
            if chart_key:
                chart_path = full_court_paths[chart_key]
                print(f"  - 全场图: {chart_path}")
                # Store it for potential later use (e.g., Weibo)
                app.chart_paths["full_court_chart"] = chart_path
            return True
        else:
            print("× 全场图表生成失败")
            return False


class PlayerImpactChartCommand(NBACommand):
    """球员影响力图生成命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("球员得分影响力图表生成")

        if not app.config.player:
            print("× 请使用 --player 指定球员名称")
            return False

        # Call the dedicated method in NBAService
        impact_paths = app.nba_service.generate_player_scoring_impact_charts(
            player_name=app.config.player,
            team=app.config.team,
            impact_type="full_impact"
        )

        if impact_paths:
            print(f"✓ 成功生成 {len(impact_paths)} 个球员影响力图表:")
            for chart_type, chart_path in impact_paths.items():
                print(f"  - {chart_type}: {chart_path}")
                # Store for potential later use
                app.chart_paths[chart_type] = chart_path
            return True
        else:
            print("× 球员得分影响力图表生成失败")
            return False