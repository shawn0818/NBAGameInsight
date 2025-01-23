import json
import logging

from nba.models.game_model import Game
from nba.parser.game_parser import GameDataParser

# 设置 logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

# 加载 JSON 数据 (假设你已经读取了 JSON 文件到以下变量)
with open('boxscore_0022400358.json', 'r') as f:
    boxscore_data = json.load(f)

with open('playbyplay_0022400358.json', 'r') as f:
    playbyplay_data = json.load(f)

# 合并数据
merged_data = {**boxscore_data, 'playByPlay': playbyplay_data}

# 创建解析器实例
parser = GameDataParser()

# 解析数据
game: Game | None = parser.parse_game_data(merged_data)

# 处理结果
if game:
    logging.info("Game data parsed successfully!")

    # 打印一些关键信息以验证解析结果
    logging.info(f"Game ID: {game.game.gameId}")
    logging.info(f"Home Team: {game.game.homeTeam.teamName}, Score: {game.game.homeTeam.score}")
    logging.info(f"Away Team: {game.game.awayTeam.teamName}, Score: {game.game.awayTeam.score}")

    if game.playByPlay:
        logging.info(f"Total Actions: {len(game.playByPlay.actions)}")
        if len(game.playByPlay.actions) > 0:
            # 打印第一条event的信息，用于检查结构
            first_event = game.playByPlay.actions[0]
            logging.info(f"First action type: {first_event.actionType}")
            logging.info(f"First action details: {first_event.dict()}")

else:
    logging.error("Game data parsing failed.")