import matplotlib.pyplot as plt
import matplotlib.colors as colors
from matplotlib.patches import Circle, Rectangle, Arc
from matplotlib.offsetbox import OffsetImage
import squarify
from game_config import NBAConfig


# 将可视化进行类的封装，Visualization 类可以被扩展来包含其他类型的图表，为了使类更通用，保持方法的独立性和重用性，每个方法都应该仅接受必要的数据作为参数，并返回或保存图像。
class TreeMap:

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
        score_data = TreeMap.normalize_scores(score_data)
        color = TreeMap.map_colors(player_id, score_data)
        labels = TreeMap.create_labels(score_data)
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


class ShotChart:
    @staticmethod
    def draw_court(ax=None, color='black', lw=2, paint_color="#fab624", outer_lines=False):
        # If an axes object isn't provided to plot onto, just get current one
        if ax is None:
            ax = plt.gca()

        # Create the various parts of an NBA basketball court

        # Create the basketball hoop
        # Diameter of a hoop is 18" so it has a radius of 9", which is a value
        # 7.5 in our coordinate system
        hoop = Circle((0, 0), radius=7.5, linewidth=lw, color=color, fill=False)

        # Create backboard
        backboard = Rectangle((-30, -7.5), 60, -1, linewidth=lw, color=color)

        # The paint
        # Create the outer box 0f the paint, width=16ft, height=19ft
        outer_box = Rectangle((-80, -47.5), 160, 190, linewidth=lw, color=color,
                              fill=False, zorder=0)
        # Create the inner box of the paint, widt=12ft, height=19ft
        inner_box = Rectangle((-60, -47.5), 120, 190, linewidth=lw, color=color,
                              fill=False, zorder=0)

        # Create free throw top arc
        top_free_throw = Arc((0, 142.5), 120, 120, theta1=0, theta2=180,
                             linewidth=lw, color=color, fill=False, zorder=0)
        # Create free throw bottom arc
        bottom_free_throw = Arc((0, 142.5), 120, 120, theta1=180, theta2=0,
                                linewidth=lw, color=color, linestyle='dashed', zorder=0)
        # Restricted Zone, it is an arc with 4ft radius from center of the hoop
        restricted = Arc((0, 0), 80, 80, theta1=0, theta2=180, linewidth=lw,
                         color=color, zorder=0)

        # Three point line
        # Create the side 3pt lines, they are 14ft long before they begin to arc
        corner_three_a = Rectangle((-220, -47.5), 0, 138, linewidth=lw,
                                   color=color, zorder=0)
        corner_three_b = Rectangle((220, -47.5), 0, 138, linewidth=lw, color=color, zorder=0)
        # 3pt arc - center of arc will be the hoop, arc is 23'9" away from hoop
        # I just played around with the theta values until they lined up with the
        # threes
        three_arc = Arc((0, 0), 475, 475, theta1=22, theta2=158, linewidth=lw,
                        color=color, zorder=0)

        # Center Court
        center_outer_arc = Arc((0, 422.5), 120, 120, theta1=180, theta2=0,
                               linewidth=lw, color=color, zorder=0)
        center_inner_arc = Arc((0, 422.5), 40, 40, theta1=180, theta2=0,
                               linewidth=lw, color=color, zorder=0)

        # List of the court elements to be plotted onto the axes
        court_elements = [hoop, backboard, outer_box, inner_box, top_free_throw,
                          bottom_free_throw, restricted, corner_three_a,
                          corner_three_b, three_arc, center_outer_arc,
                          center_inner_arc]

        background_color = "#FDF5E6"
        random_line_colors = [
            "#FBB180", "#FBB180", "#FAB07F",
        ]

        # Draw the half court line, baseline and side out bound lines
        outer_lines = Rectangle((-249, -48), 498, 469, linewidth=lw,
                                color=color, fill=None)
        court_elements.append(outer_lines)
        outer_lines_fill = Rectangle((-249, -48), 498, 470, linewidth=lw,
                                     color=background_color, fill=True, zorder=-2)
        court_elements.append(outer_lines_fill)

        # 画出来油漆区
        '''
        x = -248
        while x <= 250:
            color = background_color
            bg_lw = random.randint(2, 4)
            if random.randint(0, 1) == 1:
                color = random_line_colors[random.randint(0, len(random_line_colors)-1)]
            court_elements.append(Rectangle((x, -48), bg_lw, 470, linewidth=1, color=color, fill=True, zorder=-2))
            x += bg_lw
        '''

        paint_background = Rectangle((-80, -47.5), 160, 190, linewidth=lw, color=paint_color,
                                     fill=True, zorder=-1)
        court_elements.append(paint_background)

        # Add the court elements onto the axes
        for element in court_elements:
            ax.add_patch(element)

        return ax

    @staticmethod
    def plot_raw_shotchart(action_df, title, assist_df, image_name=None):
        plt.style.use('fivethirtyeight')
        fig, ax = plt.subplots(figsize=(12, 12))

        green = '#45B056'
        red = '#B04556'
        yellowish = '#4169E1'

        made_shots = action_df.loc[action_df.shotResult == "Made"]
        missed_shots = action_df.loc[action_df.shotResult == "Missed"]

        paths = ax.scatter(
            x=made_shots.xLegacy,
            y=made_shots.yLegacy,
            marker='o',
            c=green,
            s=100,
            alpha=0.8
        )

        paths = ax.scatter(
            x=missed_shots.xLegacy,
            y=missed_shots.yLegacy,
            marker='x',
            c=red,
            s=100,
            alpha=0.8
        )

        paths = ax.scatter(
            x=assist_df.xLegacy,
            y=assist_df.yLegacy,
            marker='o',
            c=yellowish,
            s=100,
            alpha=0.8
        )

        # Legend
        ax.scatter(x=230, y=380, s=400, marker='o', c=green)
        ax.text(x=220, y=380, s="Made", color=green, fontsize=18, ha='right', va='center')
        ax.scatter(x=230, y=360, s=400, marker='x', c=red)
        ax.text(x=220, y=360, s="Missed", color=red, fontsize=18, ha='right', va='center')
        ax.scatter(x=230, y=340, s=400, marker='o', c=yellowish)
        ax.text(x=220, y=340, s="Made on LeBron AST", color=yellowish, fontsize=18, ha='right', va='center')

        # Changing court color
        # ax.set_facecolor('#FFFAFA')

        # Removing ticks
        ax.xaxis.set_ticks([])
        ax.yaxis.set_ticks([])
        ax.grid(False)

        # Title
        plt.title(title, size=20)

        # Drawing court
        ShotChart.draw_court(ax=ax, outer_lines=True, lw=3)
        ax.set_xlim(-251, 251)
        ax.set_ylim(-65, 423)

        # 本地图片路径
        img_path = 'pictures/lebron.jpg'
        # 添加球员头像
        img = plt.imread(img_path)
        # Create the OffsetImage object, also set the zoom
        offset_img = OffsetImage(img, zoom=0.9)
        # 设置图片位置
        offset_img.set_offset((55, 752))
        # 添加头像到图形中
        ax.add_artist(offset_img)

        plt.show()

        if image_name:
            fig.savefig(image_name, bbox_inches='tight')

