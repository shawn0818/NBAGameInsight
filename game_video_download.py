import subprocess
import time
import re
import requests
from game_config import NBAConfig


# 将视频下载进行类的封装
class GameVideoDownload:
    @staticmethod
    def get_video_url(game_id, action_number):
        try:
            url = NBAConfig.VideoData_URL
            headers = NBAConfig.HEADERS
            params = {'GameID': str(game_id), 'GameEventID': str(action_number)}
            # 参数很多，contextMeasure 参数的值 "FGM","REB"， 'PlayerID'等参数
            # actionType 的值如果是 block 类型会出现返回空值的的现象
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()  # 抛出异常如果 HTTP 状态码不是 200
            response_data = response.json()  # Parse response as JSON
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
    def from_video_to_gif(video_info_list):
        output_folder = NBAConfig.VIDEO_TO_PICTURE_PATH
        for idx, (video_url, name_info) in enumerate(video_info_list, start=1):
            # 构建文件名
            safe_name = re.sub(r'\W+', '_', name_info)  # 将非字母数字字符替换为下划线
            output_path = f"{output_folder}/{idx}_{safe_name}.gif"
            download_command = (f'ffmpeg -hide_banner -i "{video_url}" -vf "fps=12,'
                                f'scale=960:-1:flags=lanczos,split['
                                f's1][s2];[s1]palettegen[p];[s2][p]paletteuse" -c:v gif "{output_path}"')
            subprocess.run(download_command, shell=True)
            time.sleep(1)

