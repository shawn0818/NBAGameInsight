import requests
from datetime import datetime,timedelta
from pytz import timezone
import re
import pandas as pd

#判断今天是否有湖人比赛
#第一步得到 nba 的日程表，然后根据球队 id 进行筛选
#可以创建一个日程表的类，默认参数为日期和球队
class NBASchedule:
    def __init__(self, gamedate=None, team_id=None):
        self.base_url = "https://core-api.nba.com/cp/api/v1.3/feeds/gamecardfeed"
        self.team_id = team_id
        self.gamedate = self.parse_date(gamedate) if gamedate else self.get_yesterday_eastern_date()
        self.headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "DNT": "1",
        "Host": "core-api.nba.com",
        "Ocp-Apim-Subscription-Key": "747fa6900c6c4e89a58b81b72f36eb96",
        "Origin": "https://www.nba.com",
        "Pragma": "no-cache",
        "Referer": "https://www.nba.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "Sec-GPC": "1",
        "TE": "trailers",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
        }

    @staticmethod
    def parse_date(date_str):
        if not date_str:
            return None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                # 解析日期字符串
                dt = datetime.strptime(date_str, fmt)
                # 将得到的日期减去一天，以调整为北京时间的前一天
                adjusted_dt = dt - timedelta(days=1)
                return adjusted_dt
            except ValueError:
                continue
        raise ValueError(f"Date format for {date_str} is not supported.")

    @staticmethod
    def get_yesterday_eastern_date() -> datetime.date:
        beijing_tz = timezone('Asia/Shanghai')
        beijing_date_now = datetime.now(beijing_tz).date()
        eastern_date = beijing_date_now - timedelta(days=1)
        return eastern_date
    
    def is_team_playing(self, game_card: dict) -> bool:
        home_team = game_card["cardData"]["homeTeam"]
        away_team = game_card["cardData"]["awayTeam"]
        return home_team["teamId"] == int(self.team_id) or away_team["teamId"] == int(self.team_id)

    def get_all_game_cards(self) -> list:
        gamedate_formatted = self.gamedate.strftime("%m/%d/%Y")
        params = {
            "gamedate": gamedate_formatted,
            "platform": "web",
        }
        try:
            response = requests.get(self.base_url, params=params, headers=self.headers)
            response.raise_for_status()
            #如果 'modules' 存在，它将返回其值；如果不存在，它将返回一个空列表 
            nba_schedule = response.json().get('modules', [])
            #最终返回的内容将是一个包含'cards'信息的列表
            #如果在响应中没有找到这些信息，或者请求失败，函数将返回一个空列表。
            all_game_cards = nba_schedule[0].get("cards", [])
            return all_game_cards if nba_schedule else []
        
        except requests.RequestException as e:
            print(f"Error fetching NBA schedule: {e}")
            return []
                             
    def filter_one_gamecard(self) -> str:
        game_cards = self.get_all_game_cards()
        for game_card in game_cards:
            if self.is_team_playing(game_card):
                game_id = game_card['cardData']['gameId']
                game_images = game_card["cardData"]["images"]["640x360"]
                game_simple_card = {
                    "game_id":game_id,
                    "game_images":game_images
                }
                return game_simple_card
        return None


#如果有比赛的话，返回比赛信息，这里使用类来获取比赛的信息
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
    def fetch_playbyplay(self):
        endpoint = "playbyplay/playbyplay"
        return self.fetch_data(endpoint)
    ### 获取 boxscore 的 json 数据
    def fetch_boxscore(self):
        endpoint = "boxscore/boxscore"
        return self.fetch_data(endpoint)


#获取数据之后进行数据解析
class GameDataParser:

    @staticmethod
    def convert_utc_to_local(utc_time_str, local_tz='Asia/Shanghai'):
        utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone('UTC'))
        local_time = utc_time.astimezone(timezone(local_tz))
        return local_time.strftime('%Y-%m-%d %H:%M:%S')
    
    @staticmethod
    def build_team_statistics_df(team_data):
        team_statistics_df = pd.DataFrame(team_data["statistics"])
        team_statistics_df['team_name'] = team_data["teamName"]
        team_statistics_df['team_id'] = team_data["teamId"]
        return team_statistics_df
    
    @staticmethod
    def build_player_statistics_df(players, team):
        player_df = pd.DataFrame([player['statistics'] for player in players])
        player_df['team'] = team
        player_df['player_id'] = [player['personId'] for player in players]
        player_df['player_name'] = [player['name'] for player in players]
        player_df['player_status'] = [player['status'] for player in players]
        return player_df
  
    def parse_game_info(self,game_info_data):
        if game_info_data:
            game_info = game_info_data['game']
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
            #最终需要的比赛信息
            game_info_parsed = {
            "time": game_time_beijing,
            "place_city": game_place_city,
            "place_arena": game_place_arena,
            "home_team_name": home_team_name,
            "away_team_name": away_team_name}

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
            game_info_text = f"""今日{game_info_parsed['home_team_name']}队比赛：
            时间：北京时间 {game_info_parsed['time']}
            地点：{game_info_parsed['place_city']}，{game_info_parsed['place_arena']}
            比赛双方：{game_info_parsed['home_team_name']} vs {game_info_parsed['away_team_name']}"""
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

    def __init__(self):
        
        self.schedule_fetcher = None
        self.game_data_parser = GameDataParser()
        # GameDataDisplay 直接使用类名调用静态方法，无需实例化
        #self.game_data_fetcher = GameDataFetcher() 这个依赖于 gameid
    
    def get_game_id(self, gamedate, team_id):
        schedule_fetcher = NBASchedule(gamedate=gamedate, team_id=team_id)
        game_info = schedule_fetcher.filter_one_gamecard()
        return game_info.get("game_id") if game_info else None
    
    #展示比赛基本信息
    def process_and_present_game_data(self,gamedate, team_id):

        game_id = self.get_game_id(gamedate, team_id)
        if game_id:
            # 在知道 game_id 后，我们现在实例化 GameDataFetcher
            game_data_fetcher = GameDataFetcher(game_id)            
            game_data = game_data_fetcher.fetch_boxscore()
            game_data_parsed = self.game_data_parser.parse_game_info(game_data)
            game_data_display = GameDataDisplay.display_game_info(game_data_parsed)
            print(game_data_display)
            return game_data_display
        else:
            print("今日无湖人队比赛")

    
def main():
    team_id = '1610612747'  # 假设这是一个有效的球队 ID
    gamedate = "12/21/2023"  # 假设这是需要查询的比赛日期
    processor = NBADataProcessor()
    #展示比赛基本信息
    processor.process_and_present_game_data(gamedate = gamedate,team_id=team_id)
    
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

