class NBAConfig:
    """创建一个类负责解决硬编码的部分，比如路径、文件地址等"""
    # url集合
    SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"
    liveData_URL = "https://cdn.nba.com/static/json/liveData"
    VideoData_URL = 'https://stats.nba.com/stats/videoeventsasset'
    # 文件路径集合
    TREE_OUT_PATH = "pictures/plt_tree.png"
    VIDEO_TO_PICTURE_PATH = "video_gif"
    JSON_FILE_PATH = "nba_schedule.json"
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

