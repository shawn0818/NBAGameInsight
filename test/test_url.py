import requests
import json
from typing import Dict

def test_nba_api() -> Dict:
    """测试 NBA API 请求"""
    #url = "https://stats.nba.com/stats/videodetailsasset?LeagueID=00&Season=2024-25&SeasonType=Regular+Season&TeamID=0&PlayerID=2544&GameID=0022400408&Outcome=&Location=&Month=0&SeasonSegment=&DateFrom=&DateTo=&OpponentTeamID=0&VsConference=&VsDivision=&Position=&RookieYear=&GameSegment=&Period=0&LastNGames=0&ClutchTime=&AheadBehind=&PointDiff=&RangeType=0&StartPeriod=0&EndPeriod=0&StartRange=0&EndRange=28800&ContextFilter=&ContextMeasure=FGM&OppPlayerID="
    url = "https://stats.nba.com/stats/teamdetails?TeamID="
    url2 = "https://cdn.nba.com/static/json/staticData/playerIndex.json"
    url3 = "https://stats.nba.com/stats/commonallplayers?LeagueID=00"
    url4 = "https://stats.nba.com/stats/teaminfocommon?LeagueID=00&Season=2024-25&SeasonType=Regular+Season&TeamID=1610612742"
    url5 = "https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_0022400596.json"
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Host": "stats.nba.com",
        "Origin": "https://www.nba.com",
        "Referer": "https://www.nba.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    


    try:
        response = requests.get(
            url=url2,
            headers=headers,
            timeout=30,
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        
        if response.ok:
            return response.json()
        else:
            print(f"Error response: {response.text}")
            return {}
            
    except Exception as e:
        print(f"Request failed: {e}")
        return {}

if __name__ == "__main__":

    result = test_nba_api()
    if result:
        # 保存结果到文件
        with open('test.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)

        print("Response saved to game_videodetail.json")
    else:
        print("No data returned")