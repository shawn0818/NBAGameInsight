import matplotlib.pyplot as plt
import matplotlib.colors as colors
import squarify
from game_config import NBAConfig


# 将可视化进行类的封装，Visualization 类可以被扩展来包含其他类型的图表，为了使类更通用，保持方法的独立性和重用性，每个方法都应该仅接受必要的数据作为参数，并返回或保存图像。
class GameDataVisualization:

    @staticmethod
    def normalize_scores(score_df):
        """这个函数负责矩形面积的大小"""
        score_df.loc[:, 'Score_Normalized'] = score_df['statistics_points'] / score_df['statistics_points'].sum()
        return score_df

    @staticmethod
    def map_colors(player_id, score_df):
        """这个函数负责影射矩形的颜色以及颜色设置"""
        custom_blue = [84 / 255, 44 / 255, 129 / 255]  # 湖人紫色
        custom_yellow = [250 / 255, 182 / 255, 36 / 255]  # 湖人金色
        min_percentage = score_df['statistics_fieldGoalsPercentage'].min()
        max_percentage = score_df['statistics_fieldGoalsPercentage'].max()
        norm = colors.Normalize(min_percentage, max_percentage)

        color_mapped = []
        for _, row in score_df.iterrows():
            if row['personId'] == int(player_id):
                color_mapped.append(custom_yellow)  # 对于特定 teamId，使用固定的黄色
            else:
                # 根据命中率调整蓝色的亮度
                adjusted_intensity = norm(row['statistics_fieldGoalsPercentage'])
                min_lightness = 0.6
                lightness = min_lightness + (1 - min_lightness) * adjusted_intensity
                adjusted_color = [custom_blue[0] * lightness,
                                  custom_blue[1] * lightness,
                                  custom_blue[2] * lightness, 1]
                color_mapped.append(adjusted_color)

        return color_mapped

    @staticmethod
    def create_labels(score_df):
        """负责标签的制定"""
        return [
            "{}\nPoints: {}\nShooting %: {:.1f}".format(
                row['name'], row['statistics_points'], row['statistics_fieldGoalsPercentage'] * 100
            ) for index, row in score_df.iterrows()
        ]

    @staticmethod
    def display_player_scores(team_id, player_id, player_data_parsed, output_path=NBAConfig.TREE_OUT_PATH):
        # Filter the DataFrame for the specified team and positive points.
        score_data = player_data_parsed[
            (player_data_parsed["teamId"] == int(team_id)) &
            (player_data_parsed["statistics_points"] > 0)
            ].sort_values(by="statistics_points", ascending=False)
        # Normalize scores and map colors.
        score_data = GameDataVisualization.normalize_scores(score_data)
        color = GameDataVisualization.map_colors(player_id, score_data)
        labels = GameDataVisualization.create_labels(score_data)
        # Plot the treemap.
        fig, ax = plt.subplots(1, figsize=(12, 6))
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)  # 调整边框
        squarify.plot(
            sizes=score_data['Score_Normalized'],
            label=labels,
            color=color,
            alpha=0.8,
            ax=ax,
            linewidth=2,
            edgecolor='white'
        )
        # Set the title and remove axes.
        plt.title('Player Score Distribution Treemap')
        plt.axis('off')
        # Save the figure.
        plt.savefig(output_path)
        plt.close()

