import requests
from datetime import datetime,timedelta
from pytz import timezone
import re
import pandas as pd
import numpy as np
import os
import json



#可以创建一个日程表的类，默认参数为日期和球队
#调用方法：先实例化 nba_schedule = NBASchedule()
#team_schedule = nba_schedule.filter_team_schedule(team_id=team_id,game_date=game_date)
class NBASchedule:
    def __init__(self):
        self.json_file_path = r"C:\Users\tong\lebron_bot\nba_schedule.json"
        self.schedule_url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"
        self.schedule_headers = {
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
            "User-Agent": "Mozilla/5.0 (Your User Agent)"  
            }
                  
    def get_nba_schedule(self):      
        if os.path.exists(self.json_file_path):
            with open(self.json_file_path, "r") as file:
                schedule_data = json.load(file)
            return schedule_data       
        try:
            response = requests.get(url=self.schedule_url,headers=self.schedule_headers)
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
        all_team_schedule_df = all_team_schedule_df.copy()   
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
#获取 game_id = team_schedule_dict["gameId"]
class TeamScheduleDataParser:
   
    @staticmethod    
    def get_schedule_as_dict(team_schedule_data):
        team_schedule_dict = team_schedule_data.to_dict(orient='records')[0]
        return team_schedule_dict 


#使用 GameDataFetcher 获得某一场比赛 game_id 的动态信息，比如实时比分，实时 playbyplay 等。
class GameDataFetcher:
    def __init__(self, game_id):
        self.game_id = game_id
        self.base_url = "https://cdn.nba.com/static/json/liveData"
        self.session = requests.Session()
        self.session.headers.update({
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
            "User-Agent": "Mozilla/5.0 (Your User Agent)"
        })

    def fetch_data(self, endpoint):
        url = f"{self.base_url}/{endpoint}_{self.game_id}.json"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"请求错误：{e}")
            return None
          
    ### 获取 playbypaly 的 json 数据
    def fetch_game_playbyplay(self):
        endpoint = "playbyplay/playbyplay"
        return self.fetch_data(endpoint)
    ### 获取 boxscore 的 json 数据
    def fetch_game_boxscore(self):
        endpoint = "boxscore/boxscore"
        return self.fetch_data(endpoint)

#获取数据之后进行数据解析
class GameDataParser:
    
    def __init__(self):
        # 初始化时设置属性
        self.game_info_df = None
        self.home_all_df = None
        self.away_all_df = None
        self.home_player_df = None
        self.away_player_df = None

    @staticmethod
    def convert_utc_to_local(utc_time_str, local_tz='Asia/Shanghai'):
        utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone('UTC'))
        local_time = utc_time.astimezone(timezone(local_tz))
        return local_time.strftime('%Y-%m-%d %H:%M:%S')
      
    def parse_game_data(self,game_data):
        game_df = pd.json_normalize(game_data,errors="ignore",sep='_')
        self.game_info_df = game_df.iloc[:, 4:24]  
        self.home_all_df = game_df.iloc[:, 26:96] 
        self.away_all_df =  game_df.iloc[:, 97:166] 
        
        home_record_path = ["game","homeTeam","players"]
        home_meta = [["game","homeTeam","teamId"],["game","homeTeam","teamName"],["game","homeTeam","teamCity"],["game","homeTeam","teamTricode"],["game","homeTeam","score"]]
        self.home_player_df = pd.json_normalize(game_data,record_path=home_record_path,meta=home_meta,errors="ignore",sep='_')

        away_record_path = ["game","awayTeam","players"]
        away_meta = [["game","awayTeam","teamId"],["game","awayTeam","teamName"],["game","awayTeam","teamCity"],["game","awayTeam","teamTricode"],["game","awayTeam","score"]]
        self.away_player_df = pd.json_normalize(game_data,record_path=away_record_path,meta=away_meta,errors="ignore",sep='_')
        
       
    def parse_game_info(self,game_info_data):
            
        game_info_data = self.parse_game_data().game_info_df
        # game_info['gameTimeUTC'] 是一个字符串，包含了 UTC 时间
        utc_time_str = game_info['gameTimeUTC']
        #转成本地北京时间
        game_time_beijing = GameDataParser.convert_utc_to_local(utc_time_str)                         
        #比赛地点
        game_place_city = game_info['arena']["arenaCity"]
        game_place_arena = game_info['arena']["arenaName"]
        #比赛双方
        home_team_name = game_info["homeTeam"]["teamName"]
        away_team_name = game_info["awayTeam"]["teamName"]
        # 判断查询的 team_id 是主队还是客队
        team_role = None
        team_role = None
        home_team_role = "主场"
        away_team_role = "客场"            
        if game_info["homeTeam"]["teamId"] == team_id:
            team_role = home_team_role
        elif game_info["awayTeam"]["teamId"] == team_id:
            team_role = away_team_role          
        #最终需要的比赛信息
        game_info_parsed = {
        "time": game_time_beijing,
        "place_city": game_place_city,
        "place_arena": game_place_arena,
        "home_team": f"{home_team_name} ({home_team_role})",
        "away_team": f"{away_team_name} ({away_team_role})",
        "team_role": team_role
        }

        return game_info_parsed
            
    def parse_realtime_score(self, score_data):
        if score_data:
            # 这里假设'score_data' JSON 结构中有'homeTeam'和'awayTeam'的得分信息
            home_team = score_data['game']['homeTeam']
            away_team = score_data['game']['awayTeam']

            #获取比赛状态，比赛目前进行到第几节
            game_status = score_data["game"]['gameStatus']
            game_period = score_data["game"]['period']
            game_clock =  score_data["game"]['gameClock']
            # 使用正则表达式来匹配分钟和秒
            matches = re.match(r"PT(\d{2})M(\d{2})S", game_clock)
            # 提取分钟和秒，现在 minutes 和 seconds 包含了剩余的分钟和秒数
            game_clock_minutes = matches.group(1)
            game_clock_seconds = matches.group(2)

            #双方球队目前得分
            home_score = home_team["score"]
            away_score = away_team["score"]

            #球队统计数据，不止是得分维度
            team_statistics_df = pd.concat([
                self.build_team_statistics_df(home_team),
                self.build_team_statistics_df(away_team)
            ], ignore_index=True)

            #球员统计数据，不止是得分维度
            player_statistics_df = pd.concat([
                self.build_player_statistics_df(home_team["players"], 'Home'),
                self.build_player_statistics_df(away_team["players"], 'Away')
            ], ignore_index=True)

            realtime_box_score = {
                "game_status":game_status,
                "game_period":game_period,
                "game_clock_minutes":game_clock_minutes,
                "game_clock_seconds":game_clock_seconds,
                "home_score":home_score,
                "away_score":away_score
            }
            
            return realtime_box_score,team_statistics_df,player_statistics_df 
 
    def parse_gameover_score(self, score_data):

        if score_data:
            # 这里假设'score_data' JSON 结构中有'homeTeam'和'awayTeam'的得分信息
            home_team = score_data['game']['homeTeam']
            away_team = score_data['game']['awayTeam']

            #球队统计数据，不止是得分维度
            team_statistics_df = pd.concat([
                self.build_team_statistics_df(home_team),
                self.build_team_statistics_df(away_team)
            ], ignore_index=True)

            #球员统计数据，不止是得分维度
            player_statistics_df = pd.concat([
                self.build_player_statistics_df(home_team["players"], 'Home'),
                self.build_player_statistics_df(away_team["players"], 'Away')
            ], ignore_index=True)

            return team_statistics_df,player_statistics_df 
        
    def parse_playbyplay(self, actions_data):
        if actions_data:
            actions_df = pd.json_normalize(actions_data, record_path=['game', 'actions'])
            return actions_df
        

class GameDataDisplay:

    @staticmethod
    def display_game_info(game_info_parsed):

        if game_info_parsed:
            game_info_text = (
            "【今日比赛】 \n"
            f"时间：北京时间 {game_info_parsed['time']}\n"
            f"地点：{game_info_parsed['place_city']}，{game_info_parsed['place_arena']}\n"
            f"比赛双方：{game_info_parsed['home_team']} vs {game_info_parsed['away_team']}"
            )
            return game_info_text
        return None
    
    @staticmethod
    def display_realtime_score(score_data_parsed):         
        pass      
   
    @staticmethod
    def display_gameover_score(score_data_parsed):
        pass
   
    @staticmethod
    def display_playbyplay(actions_data_parsed):
        #这里主要是想解析出来球员的得分篮板助攻盖帽抢断等回合
        # 接下来你可以进行筛选
        team_id = 1610612747
        person_id = 2544
        action_types = ['2pt', 'block', '3pt', 'steal']

        player_action_df = actions_data_parsed[
            (actions_data_parsed['teamId'] == team_id) &
            (actions_data_parsed['personId'] == person_id) &
            (actions_data_parsed['actionType'].isin(action_types))
        ]
        #下载视频需要的 eventid 就是 actionNumber 列
        return player_action_df
       

#使用类负责整个流程的协调
#而不是在 main 函数中手动管理这些实例和它们之间的交互
class NBADataProcessor:

    #展示比赛基本信息
    def process_and_present_game_data(game_date, team_id):
        
        #先实例化 NBASchedule 类，筛选获得对应日期的比赛
        schedule_fetcher = NBASchedule() 
        team_schedule =  schedule_fetcher.filter_team_schedule(game_date=game_date, team_id=team_id)
        
         
        if not team_schedule.empty:
            
            #如果存在比赛的话，找到关键的 game_id
            game_id = team_schedule["gameId"].iloc[0]
            
            # 通过我们 game_id，现在实例化 GameDataFetcher
            game_data_fetcher = GameDataFetcher(game_id)            
            game_data = game_data_fetcher.fetch_boxscore()
            
            #实例化 GameDataparser
            game_data_parser = GameDataParser()
            game_data_parsed = game_data_parser.parse_game_info(team_id=team_id,game_info_data=game_data)
            
            #实例化 GameDataDisplay
            game_data_display = GameDataDisplay.display_game_info(game_data_parsed)
            print(game_data_display)
            return game_data_display
        else:
            print("【今日无比赛】")

    
def main():
    team_id = '1610612747'  # 假设这是一个有效的球队 ID
    game_date = "12/24/2023"  # 假设这是需要查询的比赛日期
    processor = NBADataProcessor()
    #展示比赛基本信息
    processor.process_and_present_game_data(game_date = game_date,team_id=team_id)
    
if __name__ == "__main__":
    main()


'''
赛中访问比分板 boxscore，
通过其不同的统计项目  scores

得到某一类型 plays
的视频 videos
或者图片 chats

还是利用 pandas 返回 pd。这也方便进行筛选，比较，运算
'''

