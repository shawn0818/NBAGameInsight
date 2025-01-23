import json
from enum import IntEnum
from typing import Dict, Optional
from datetime import timedelta, datetime
from dataclasses import dataclass
from config.nba_config import NBAConfig
from .base_fetcher import BaseNBAFetcher


class GameStatusEnum(IntEnum):
    """比赛状态"""
    NOT_STARTED = 1
    IN_PROGRESS = 2
    FINISHED = 3


@dataclass
class GameConfig:
    """比赛数据配置"""
    BASE_URL: str = "https://cdn.nba.com/static/json/liveData"
    CACHE_PATH: str = NBAConfig.PATHS.GAME_CACHE_DIR

    # 不同状态的缓存时间
    CACHE_DURATION = {
        GameStatusEnum.NOT_STARTED: timedelta(minutes=1),  # 未开始缓存1分钟
        GameStatusEnum.IN_PROGRESS: timedelta(seconds=0),  # 进行中不缓存
        GameStatusEnum.FINISHED: timedelta(days=365)  # 已结束缓存一年
    }

    # 缓存文件名
    CACHE_FILES = {
        'boxscore': 'boxscores_{game_id}.json',
        'playbyplay': 'playbyplay_{game_id}.json'
    }


class GameFetcher(BaseNBAFetcher):
    game_config = GameConfig()

    def __init__(self):
        super().__init__()  # 这里也会初始化 self.logger
        self._game_status = None  # 添加状态缓存

    def get_boxscore(self, game_id: str, force_update: bool = False) -> Optional[Dict]:
        """获取比赛统计数据"""
        try:
            # 1. 构建缓存路径
            cache_file = self.game_config.CACHE_PATH / self.game_config.CACHE_FILES['boxscore'].format(game_id=game_id)

            # 2. 如果不是强制更新,先检查缓存
            if not force_update and cache_file.exists():
                try:
                    with cache_file.open('r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                        # 检查缓存时间和比赛状态
                        timestamp = datetime.fromtimestamp(cache_data.get('timestamp', 0))
                        game_status = GameStatusEnum(cache_data.get('game_status', 1))
                        cache_duration = self.game_config.CACHE_DURATION[game_status]

                        # 如果缓存未过期,直接返回
                        if datetime.now() - timestamp < cache_duration:
                            self._game_status = game_status  # 保存状态
                            self.logger.debug(f"使用缓存的 boxscore 数据: {game_id}")
                            return cache_data.get('data')
                except Exception as e:
                    self.logger.error(f"读取缓存出错: {e}")

            # 3. 如果没有有效缓存,发送API请求
            url = f"{self.game_config.BASE_URL}/boxscore/boxscore_{game_id}.json"
            data = self.fetch_data(url=url)
            if not data:
                return None

            # 4. 写入新的缓存
            self._game_status = self._get_game_status(data)  # 保存状态
            if self.game_config.CACHE_DURATION[self._game_status].total_seconds() > 0:
                cache_data = {
                    'timestamp': datetime.now().timestamp(),
                    'game_status': self._game_status.value,
                    'data': data
                }
                # 使用临时文件进行原子写入
                temp_file = cache_file.with_suffix('.tmp')
                try:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    with temp_file.open('w', encoding='utf-8') as f:
                        json.dump(cache_data, f, indent=2)
                    temp_file.replace(cache_file)
                    self.logger.debug(f"已缓存 boxscore 数据: {game_id}")
                except Exception as e:
                    self.logger.error(f"写入缓存失败: {e}")
                    if temp_file.exists():
                        temp_file.unlink()

            return data

        except Exception as e:
            self.logger.error(f"获取 boxscore 数据出错: {e}")
            return None

    def get_playbyplay(self, game_id: str, force_update: bool = False) -> Optional[Dict]:
        """获取比赛回放数据"""
        try:
            # 1. 优先使用缓存
            cache_file = self.game_config.CACHE_PATH / self.game_config.CACHE_FILES['playbyplay'].format(game_id=game_id)

            if not force_update and cache_file.exists():
                try:
                    with cache_file.open('r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                        self.logger.info(f"使用缓存的 playbyplay 数据: {game_id}")
                        return cache_data.get('data')
                except Exception as e:
                    self.logger.error(f"读取缓存出错: {e}")

            # 2. 如果没有缓存或强制更新，发送API请求
            url = f"{self.game_config.BASE_URL}/playbyplay/playbyplay_{game_id}.json"
            data = self.fetch_data(url=url)

            # 3. 即使数据获取失败也继续运行
            if not data:
                self.logger.warning(f"无法获取 playbyplay 数据: {game_id}")
                return None

            # 4. 写入缓存
            if self._game_status and self.game_config.CACHE_DURATION[self._game_status].total_seconds() > 0:
                cache_data = {
                    'timestamp': datetime.now().timestamp(),
                    'game_status': self._game_status.value,
                    'data': data
                }
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                with cache_file.open('w', encoding='utf-8') as f:
                    json.dump(cache_data, f, indent=2)

            return data

        except Exception as e:
            self.logger.error(f"获取 playbyplay 数据出错: {e}")
            return None


    def _get_game_status(self, data: Dict) -> GameStatusEnum:
        """
        从比赛数据中获取比赛状态

        Args:
            data (Dict): 比赛数据(boxscore)

        Returns:
            GameStatusEnum: 比赛状态枚举值
        """
        try:
            # 从数据中获取比赛状态
            game = data.get('game', {})
            status_text = game.get('gameStatus', 1)  # 默认为未开始

            # NBA API 返回的状态转换为我们的枚举
            status_mapping = {
                1: GameStatusEnum.NOT_STARTED,  # 未开始
                2: GameStatusEnum.IN_PROGRESS,  # 进行中
                3: GameStatusEnum.FINISHED  # 已结束
            }

            return status_mapping.get(status_text, GameStatusEnum.NOT_STARTED)

        except Exception as e:
            self.logger.error(f"获取比赛状态时出错: {e}")
            return GameStatusEnum.NOT_STARTED  # 出错时默认返回未开始状态

    def clear_cache(self, game_id: Optional[str] = None) -> None:
        """清理缓存"""
        try:
            if game_id:
                for data_type in self.game_config.CACHE_FILES:
                    cache_file = self.game_config.CACHE_PATH / self.game_config.CACHE_FILES[data_type].format(game_id=game_id)
                    if cache_file.exists():
                        cache_file.unlink()
                self.logger.info(f"已清理比赛 {game_id} 的缓存")
            else:
                # 清理过期缓存
                now = datetime.now()
                for cache_file in self.game_config.CACHE_PATH.glob('*.json'):
                    try:
                        with cache_file.open('r') as f:
                            cache_data = json.load(f)
                        timestamp = datetime.fromtimestamp(cache_data.get('timestamp', 0))
                        game_status = GameStatusEnum(cache_data.get('game_status', 1))
                        if now - timestamp > self.game_config.CACHE_DURATION[game_status]:
                            cache_file.unlink()
                    except Exception as e:
                        self.logger.error(f"清理缓存文件失败 {cache_file}: {e}")
        except Exception as e:
            self.logger.error(f"清理缓存出错: {e}")