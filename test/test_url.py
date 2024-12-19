import requests
import json
from typing import Dict

def test_nba_api() -> Dict:
    """测试 NBA API 请求"""
    url = "https://stats.nba.com/stats/videodetailsasset"
    
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Host": "stats.nba.com",
        "Origin": "https://www.nba.com",
        "Referer": "https://www.nba.com/",
        "sec-ch-ua": "\"Not_A Brand\";v=\"8\", \"Chromium\";v=\"120\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    


    try:
        response = requests.get(
            url=url,
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
        with open('nba_api_response.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        print("Response saved to nba_api_response.json")
    else:
        print("No data returned")