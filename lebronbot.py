import requests
from datetime import datetime,timedelta
from pytz import timezone
import pandas as pd
import numpy as np
import os
import json
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import squarify 
import subprocess
import time 
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

class NBAConfig:
    """创建一个类负责解决硬编码的部分，比如路径、文件地址等"""
    #url 集合
    SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"
    liveData_URL = "https://cdn.nba.com/static/json/liveData"
    VideoData_URL = 'https://stats.nba.com/stats/videoeventsasset'
    #文件路径集合
    TREE_OUT_PATH = "C:\\Users\\tong\\Desktop\\presend\\tree.png"
    VIDEO_TO_PICTURE_PATH = "C:\\Users\\tong\\Desktop\\presend"
    JSON_FILE_PATH = r"C:\Users\tong\lebron_bot\nba_schedule.json"
    HEADERS = {
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "DNT": "1",
        "Origin": "https://www.nba.com",
        "Pragma": "no-cache",
        "Referer": "https://www.nba.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"  
    }

#可以创建一个日程表的类，默认参数为日期和球队
class NBASchedule:
    def __init__(self):
        self.json_file_path = NBAConfig.JSON_FILE_PATH
        self.schedule_url = NBAConfig.SCHEDULE_URL
        self.schedule_headers = NBAConfig.HEADERS
                  
    def get_nba_schedule(self):      
        if os.path.exists(self.json_file_path):
            with open(self.json_file_path, "r") as file:
                schedule_data = json.load(file)
            return schedule_data 
        else:
            return self.fetch_schedule_data()      
              
    def fetch_schedule_data(self):
        try:
            response = requests.get(url=self.schedule_url, headers=self.schedule_headers)
            response.raise_for_status()
            schedule_data = response.json()
            with open(self.json_file_path, "w") as file:
                json.dump(schedule_data, file)
            return schedule_data
        except requests.RequestException as e:
            print(f"Error fetching NBA static schedule: {e}")
            return {}
        
    @staticmethod
    def parse_input_date(date_str)-> datetime.date:
        #输入的时间是按照北京时间日期来输入
        if not date_str:
            return None       
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                # 解析日期字符串
                dt = datetime.strptime(date_str, fmt)
                # 将得到的日期减去一天，以调整为北京时间的前一天
                adjusted_dt = dt - timedelta(days=1)               
                adjusted_dt = adjusted_dt.date()
                return adjusted_dt
            except ValueError:
                continue
        raise ValueError(f"Date format for {date_str} is not supported.")

    def filter_team_schedule(self,team_id=None,game_date=None) ->  pd.DataFrame:      
        #获取所有的日程
        all_team_schedule = self.get_nba_schedule()
        all_team_schedule_df = pd.json_normalize(all_team_schedule,record_path=["leagueSchedule","gameDates","games"],errors="ignore",sep='_')
        #all_team_schedule_df = all_team_schedule_df.copy()   
        #将 gameDateUTC 列转换为日期类型
        all_team_schedule_df['gameDateUTC'] = pd.to_datetime(all_team_schedule_df['gameDateUTC']).dt.date
        #将 gameTimeUTC 列转换为日期时间类型    
        all_team_schedule_df['gameDateTimeUTC'] = pd.to_datetime(all_team_schedule_df['gameDateTimeUTC'])  
                    
        #创建筛选条件              
        if team_id:
            team_filter = ((all_team_schedule_df['homeTeam_teamId'] == int(team_id)) | (all_team_schedule_df['awayTeam_teamId'] == int(team_id)))           
            team_schedule_df = all_team_schedule_df[team_filter]
            team_schedule_df = team_schedule_df.copy()
            #判断主场客场，生成新的列  
            team_schedule_df['home_or_away'] =np.where(team_schedule_df['homeTeam_teamId'] == int(team_id), 'home', 'away')           

            if game_date:
                #处理输入的日期文本
                game_date = self.parse_input_date(game_date) 
                given_date_filter = team_schedule_df['gameDateUTC'] == game_date
                # 检查结果的类型
                team_date_schedule_df = team_schedule_df[given_date_filter] 
                team_date_schedule_df.reset_index(drop=True, inplace=True)
                return team_date_schedule_df
            
            else:
                               
                auto_from_now_filter = team_schedule_df['gameDateTimeUTC'] >= datetime.now(timezone('UTC'))
                team_date_schedule_df = team_schedule_df[auto_from_now_filter] 
                team_date_schedule_df.reset_index(drop=True, inplace=True)
                return team_date_schedule_df
            
        else:
            all_team_schedule_df = all_team_schedule_df['gameDateTimeUTC'] >= datetime.now(timezone('UTC'))
            all_team_schedule_df.reset_index(drop=True, inplace=True)
            return all_team_schedule_df
   
#如果查询到比赛的话，这里使用 TeamScheduleDataParser 来解析比赛的信息
#这部分最重要的功能是获取到 game_id，还有比赛时间场馆等静态信息。后续还可以添加功能功能，比如近几场比赛信息等。
class TeamScheduleDataParser:  
    @staticmethod    
    def get_schedule_as_dict(team_schedule_data):
        team_schedule_dict = team_schedule_data.to_dict(orient='records')[0]
        return team_schedule_dict 
    
    def get_game_id(self, team_schedule_data):
        schedule_dict = self.get_schedule_as_dict(team_schedule_data)  
        return schedule_dict['gameId']

#使用 GameDataFetcher 获得某一场比赛 game_id 的动态信息，比如实时比分，实时 playbyplay 等。
class GameDataFetcher:
    def __init__(self, game_id):
        self.game_id = game_id
        self.headers = NBAConfig.HEADERS
       
    @contextmanager
    def session_manager(self):
        session = requests.Session()
        session.headers.update(self.headers)
        try:
            yield session
        finally:
            session.close()

    def fetch_data(self, endpoint):
        url = f"{NBAConfig.liveData_URL}/{endpoint}_{self.game_id}.json"
        with self.session_manager() as session:
            try:
                response = session.get(url)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                print(f"Error fetching NBA gamedata : {e}")
                return None
          
    ### 获取 playbypaly 的 json 数据
    def fetch_game_playbyplay(self):
        endpoint = "playbyplay/playbyplay"
        return self.fetch_data(endpoint)
    ### 获取 boxscore 的 json 数据
    def fetch_game_boxscore(self):
        endpoint = "boxscore/boxscore"
        return self.fetch_data(endpoint)
      
#获取比赛本身实时统计数据之后进行数据解析
class GameDataParser:
    #获取关于比赛本身的一些信息，比如比赛进行状态，比赛时间地点场馆，本场执法裁判等
    @staticmethod
    def parse_game_data(boxscore_data):      
        game_boxsocre_df = pd.json_normalize(boxscore_data,errors="ignore",sep='_')
        game_start_position = game_boxsocre_df.columns.get_loc('game_gameId')
        game_end_position = game_boxsocre_df.columns.get_loc('game_officials')
        game_info_df = game_boxsocre_df.iloc[:, game_start_position:game_end_position+1] 
        game_info_df.columns = game_info_df.columns.str.split('_').str[-1]            
        #需要添加关于球队的列的信息
        team_columns_df = game_boxsocre_df.loc[:, ['game_homeTeam_teamId', 'game_homeTeam_teamName','game_homeTeam_score','game_awayTeam_teamId', 'game_awayTeam_teamName','game_awayTeam_score']]
        #简化下列名
        team_columns_df.columns = team_columns_df.columns.str.extract(r'game_(.*?)_(.*)').agg('_'.join, axis=1)       
        game_meta_df = pd.concat([game_info_df, team_columns_df], axis=1)  
        return game_meta_df
                     
    #解析关于球队的数据，比如球队整体的数据统计 
    @staticmethod      
    def parse_team_data(boxscore_data):
        game_boxsocre_df = pd.json_normalize(boxscore_data,errors="ignore",sep='_')
        home_start_position = game_boxsocre_df.columns.get_loc('game_homeTeam_teamId')
        home_end_position = game_boxsocre_df.columns.get_loc('game_homeTeam_statistics_twoPointersPercentage')
        home_team_df = game_boxsocre_df.iloc[:, home_start_position:home_end_position+1] 
        away_start_position = game_boxsocre_df.columns.get_loc('game_awayTeam_teamId')
        away_end_position = game_boxsocre_df.columns.get_loc('game_awayTeam_statistics_twoPointersPercentage')
        away_team_df = game_boxsocre_df.iloc[:, away_start_position:away_end_position+1]  
        #修改列名一致，方便进行下一步拼接
        home_team_df.columns = home_team_df.columns.str.split('_').str[-1]
        away_team_df.columns = away_team_df.columns.str.split('_').str[-1]      
        # 进行上下拼接
        team_df = pd.concat([home_team_df, away_team_df], ignore_index=True)
        # 在原始数据框上就地去掉不用的列
        team_df.drop(["periods","players"], axis=1, inplace=True)       
        return team_df
    
    #解析球员的实时数据统计 
    @staticmethod     
    def parse_player_data(boxscore_data):  
        #解析出球员数据        
        home_player_df = pd.json_normalize(boxscore_data,record_path= ["game","homeTeam","players"],meta=[["game","homeTeam","teamId"],["game","homeTeam","teamName"]],errors="ignore",sep='_')
        away_player_df = pd.json_normalize(boxscore_data,record_path= ["game","awayTeam","players"],meta=[["game","awayTeam","teamId"],["game","awayTeam","teamName"]],errors="ignore",sep='_')      
        #使 meta 部分添加的列名保持一致
        home_player_df =home_player_df.rename(columns={'game_homeTeam_teamId': 'teamId', 'game_homeTeam_teamName': 'teamName'})
        away_player_df =away_player_df.rename(columns={'game_awayTeam_teamId': 'teamId', 'game_awayTeam_teamName': 'teamName'})
        # 进行上下拼接
        player_df = pd.concat([home_player_df, away_player_df], ignore_index=True)
        return player_df
    
    #解析本场比赛的所有回合，从回合中可以得到更详细的数据，比如投篮地点，投篮方式等等。  
    @staticmethod               
    def parse_playbyplay_data(actions_data):       
        if actions_data:           
            actions_df = pd.json_normalize(actions_data, record_path=['game', 'actions'],meta=[["game","gameId"]],errors="ignore",sep='_')           
            return actions_df
    
#将视频下载进行类的封装
class GameVideoDownload:
    """获取 playbyplay 回合的视频下载链接""" 
    @staticmethod
    def get_video_url(game_id,action_number):    
        try:
            url = NBAConfig.VideoData_URL
            headers = NBAConfig.HEADERS
            params = {'GameID': str(game_id),'GameEventID': str(action_number)}
            #参数很多，contextMeasure 参数的值 "FGM","REB"， 'PlayerID'等参数
            # actionType 的值如果是 block 类型会出现返回空值的的现象
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()  # 抛出异常如果 HTTP 状态码不是 200
            response_data = response.json() # Parse response as JSON
            video_data = response_data["resultSets"]['Meta']['videoUrls']
            if not video_data:  # 检查列表是否为空
            # 可以选择记录日志或返回一个默认值
                print(f"No video available for action number: {action_number}")
                return None
            video_url = video_data[0]["lurl"]
            return video_url 
        except requests.RequestException as e:
            print(f"Error fetching video for action number {action_number}: {e}")
            return None
  
    @staticmethod
    def from_videourl_to_gif(video_info_list):
        output_folder = NBAConfig.VIDEO_TO_PICTURE_PATH
        for idx, (video_url, name_info) in enumerate(video_info_list, start=1):
            # 构建文件名
            safe_name = re.sub(r'\W+', '_', name_info)  # 将非字母数字字符替换为下划线
            output_path = f"{output_folder}/{idx}_{safe_name}.gif"
            download_command = f'ffmpeg -i "{video_url}" -vf "fps=10,scale=960:-1:flags=lanczos" -c:v gif "{output_path}"'
            subprocess.run(download_command, shell=True)
            time.sleep(1)
    
#将可视化进行类的封装，Visualization 类可以被扩展来包含其他类型的图表，为了使类更通用，保持方法的独立性和重用性，每个方法都应该仅接受必要的数据作为参数，并返回或保存图像。
class GameDataVisualization:  
     
    @staticmethod
    def normalize_scores(score_df):
        """这个函数负责矩形面积的大小"""
        score_df.loc[:, 'Score_Normalized'] = score_df['statistics_points'] / score_df['statistics_points'].sum()
        return score_df
    
    @staticmethod
    def map_colors(score_df, colormap=plt.cm.viridis):
        """这个函数负责影射矩形的颜色以及颜色设置"""
        min_percentage = score_df['statistics_fieldGoalsPercentage'].min()
        max_percentage = score_df['statistics_fieldGoalsPercentage'].max()
        norm = mcolors.Normalize(min_percentage, max_percentage)
        return [colormap(norm(value)) for value in score_df['statistics_fieldGoalsPercentage']]

    @staticmethod
    def create_labels(score_df):
        """负责标签的制定"""
        return [
            "{}\nPoints: {}\nShooting %: {:.1f}".format(
                row['name'], row['statistics_points'], row['statistics_fieldGoalsPercentage'] * 100
            ) for index, row in score_df.iterrows()
        ]

    @staticmethod
    def display_player_scores(team_id, player_data_parsed, output_path=NBAConfig.TREE_OUT_PATH):
        # Filter the DataFrame for the specified team and positive points.
        score_data = player_data_parsed[
            (player_data_parsed["teamId"] == int(team_id)) &
            (player_data_parsed["statistics_points"] > 0)
        ]
        # Normalize scores and map colors.
        score_data = GameDataVisualization.normalize_scores(score_data)
        colors = GameDataVisualization.map_colors(score_data)
        labels = GameDataVisualization.create_labels(score_data)
        # Plot the treemap.
        fig, ax = plt.subplots(1, figsize=(16, 9))
        squarify.plot(
            sizes=score_data['Score_Normalized'],
            label=labels,
            color=colors,
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
  
class GameDataDisplay:  
    # 实例属性来存储比赛的详细信息
    def __init__(self, game_info_parsed):
        # 首先转换时间
        game_info_parsed["gameTimeBeijing"] =  pd.to_datetime(game_info_parsed["gameTimeUTC"]).dt.tz_convert('Asia/Shanghai').dt.strftime('%Y-%m-%d %H:%M:%S')
        # 然后将 df 转成 dict 进行访问
        game_info_dict = game_info_parsed.to_dict(orient='records')[0]
        self.game_id = game_info_dict["gameId"]
        self.game_start_time_beijing = game_info_dict["gameTimeBeijing"]
        self.game_status = game_info_dict["gameStatus"]
        self.game_period = game_info_dict["period"]
        self.game_clock = game_info_dict["gameClock"]
        self.arena_city = game_info_dict['arenaCity']
        self.arena_name = game_info_dict['arenaName']
        self.home_team_id = game_info_dict['homeTeam_teamId']
        self.home_team_name = game_info_dict['homeTeam_teamName']
        self.home_team_score = game_info_dict['homeTeam_score']
        self.away_team_id = game_info_dict['awayTeam_teamId']
        self.away_team_name = game_info_dict['awayTeam_teamName']
        self.away_team_score = game_info_dict['awayTeam_score']
        # ...可以继续添加更多所需的属性
    
    def display_game_info(self):     
           
        if self.game_status == 1:
            game_info_text = (
            "【比赛信息】 \n"
            f"时间：北京时间 {self.game_start_time_beijing}\n"
            f"地点：{self.arena_city}，{self.arena_name}\n"
            f"比赛双方：{self.home_team_name} vs {self.away_team_name}"
            )        
        elif self.game_status == 2 :          
            game_info_text = f"比赛已经在北京时间 {self.game_start_time_beijing}开始了，当前比赛已经进行到第{self.game_period}节，双方比分{self.home_team_name}{self.home_team_score}:{self.away_team_name}{self.away_team_score},快打开电视收看吧"                
        else:
            game_info_text = f"比赛已经在北京时间 {self.game_start_time_beijing}开始了，现在已经结束啦，最终比分是{self.home_team_name}{self.home_team_score}:{self.away_team_name}{self.away_team_score}"                      
        
        return game_info_text
    
    def display_player_statistic(self,player_id,player_data_parsed): 
                            
        player_filter = (player_data_parsed["personId"] == int(player_id)) 
        the_player_df = player_data_parsed[player_filter]
        the_player_dict = the_player_df.to_dict(orient='records')[0]
        
        self.player_name = the_player_dict["name"]
        self.jersey_number = the_player_dict["jerseyNum"]
        self.status = the_player_dict["status"]
        self.is_played = the_player_dict["played"] #"1"表示摸上球了
        self.not_playing_reason = the_player_dict["notPlayingDescription"] 
        self.points = the_player_dict["statistics_points"]
        self.rebounds = the_player_dict["statistics_reboundsTotal"]
        self.assists = the_player_dict["statistics_assists"]
        self.blocks = the_player_dict["statistics_blocks"]
        self.steals = the_player_dict["statistics_steals"]
        self.plus_minus_points = int(the_player_dict["statistics_plusMinusPoints"])
        self.on_court_minutes = the_player_dict["statistics_minutesCalculated"][2:4]
            
        if self.status == "ACTIVE":
            
            if self.is_played == "1":
                player_text = f"本场比赛{self.player_name}上场时间{self.on_court_minutes}分钟，正负值{self.plus_minus_points},拿下{self.points}分{self.rebounds}篮板{self.assists}助攻{self.blocks}盖帽{self.steals}抢断"                          
            else:
                player_text = f"本场比赛{self.player_name}没有上场"
        
        else:
            player_text = f"本场比赛{self.player_name}不会上场，{self.not_playing_reason}"
        
        return player_text 
                
    @staticmethod
    def display_team_statistic(team_data_parsed):
        #待完善，双方球队在各种统计数据上的比较。
        pass

    @staticmethod
    def combine_action_info(row):
        # 将剩余时间格式化为更常见的格式
        remaining_time = row['clock'][2:4] + '分'+':' + row['clock'][5:7]+ '秒'
        # 格式化字符串，组合提供的信息
        return (f"当前时间{row['timeActualBeijing']}, 比赛进行到了第{row['period']}节，"
                f"本节时间还剩下{remaining_time}，{row['description']}.")
  
    def display_playbyplay(self,player_id,actions_data_parsed):     
         # 将时间转换为北京时间
        actions_data_parsed["timeActualBeijing"] = pd.to_datetime(actions_data_parsed["timeActual"]).dt.tz_convert('Asia/Shanghai').dt.strftime('%Y-%m-%d %H:%M:%S')
        # 筛选特定球员的动作
        player_action_df = actions_data_parsed[actions_data_parsed['personId'] == int(player_id)]
        player_action_df.reset_index(drop=True, inplace=True)
        # 添加组合信息列
        player_action_df['combined_info'] = player_action_df.apply(self.combine_action_info, axis=1)   
        # 获取需要下载视频的行的 actionNumber
        action_numbers = player_action_df[player_action_df['actionType'].isin(['2pt', '3pt', 'block'])]['actionNumber'].tolist()

        # 使用 ThreadPoolExecutor 并行获取视频链接
        video_urls = {}
        game_id = self.game_id
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_action_number = {executor.submit(GameVideoDownload.get_video_url, game_id,action_number): action_number for action_number in action_numbers}
            for future in as_completed(future_to_action_number):
                action_number = future_to_action_number[future]
                video_urls[action_number] = future.result()

        # 将视频链接添加到 DataFrame
        player_action_df['video_url'] = player_action_df['actionNumber'].apply(lambda x: video_urls.get(x))       
        # 返回处理后的 DataFrame
        return player_action_df
    
    def get_actions_gif(self,player_id,actions_data_parsed):     
            # 获取视频链接
            player_action_df = self.display_playbyplay(player_id, actions_data_parsed)         
             # 定义一个辅助函数来创建视频信息
            def create_video_info(row):
                if pd.notna(row['video_url']):
                    name_info = f"{row['playerName']}_{row['actionType']}_{row['subType']}"
                    return (row['video_url'], name_info)
                return None
                        
            # 使用 apply 应用辅助函数
            video_info_list = player_action_df.apply(create_video_info, axis=1).dropna().tolist()    
            # 视频并转换为 GIF
            GameVideoDownload.from_videourl_to_gif(video_info_list)


class NBADataProcessor: 
    def __init__(self, game_date, team_id):       
        team_schedule_df = NBASchedule().filter_team_schedule(team_id=team_id,game_date=game_date)
        self.game_id = TeamScheduleDataParser().get_game_id(team_schedule_df)     
        self.game_boxsocre = GameDataFetcher(self.game_id).fetch_game_boxscore()
        self.game_info_df = GameDataParser().parse_game_data(self.game_boxsocre)
        self.game_display = GameDataDisplay(self.game_info_df)
 
    #展示比赛基本信息
    def process_game_data(self):       
        game_info_text = self.game_display.display_game_info()     
        return game_info_text
    
    def process_player_data(self,player_id):   
        player_df = GameDataParser().parse_player_data(self.game_boxsocre)
        player_text_display = self.game_display.display_player_statistic(player_id,player_df)             
        return player_text_display
    
    def process_playbyplay_data(self,player_id):  
        play_action =GameDataFetcher(self.game_id).fetch_game_playbyplay()
        actions_df = GameDataParser().parse_playbyplay_data(play_action)  
        self.game_display.get_actions_gif(player_id, actions_df)

    def process_treemap_data(self):  
        player_df = GameDataParser().parse_player_data(self.game_boxsocre)  
        GameDataVisualization.display_player_scores(team_id,player_df)     

team_id = '1610612747'   # 假设这是一个有效的球队 ID
game_date = "2024-01-10"  # 假设这是需要查询的比赛日期  
player_id = "2544"

def main():   
    processor = NBADataProcessor(game_date,team_id)
    #展示比赛基本信息
    #processor.process_game_data()
    #processor.process_player_data(player_id)
    processor.process_playbyplay_data(player_id)
    #processor.process_treemap_data()
     
if __name__ == "__main__":
    main()




