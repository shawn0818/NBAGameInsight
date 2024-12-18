import pandas as pd 
from typing import Dict, Optional, List
import logging
from pathlib import Path
import json
from datetime import datetime
from nba.models.game_event_model import PlayerBasicInfo
from nba.parser.player_parser import PlayerNameMapping
from nba.fetcher.player import PlayerFetcher
from config.nba_config import NBAConfig

class NBAMappingService:
    """NBA ID映射服务
    统一管理球员和球队的名称与ID的映射关系，提供缓存机制
    """
    
    def __init__(self):
        """初始化映射服务"""
        self.logger = logging.getLogger(__name__)
        self.player_mapping = PlayerNameMapping()
        self.team_mapping: Dict[str, int] = {}
        self.player_fetcher = PlayerFetcher()
        
        # 缓存相关配置
        self.cache_dir = NBAConfig.PATHS.LEAGUE_CACHE
        self.player_cache_file = self.cache_dir / 'player_mapping.json'
        self.team_cache_file = self.cache_dir / 'team_mapping.json'
        self.cache_duration = NBAConfig.API.PLAYERS_UPDATE_INTERVAL  # 缓存更新间隔（秒）
        
        # 确保缓存目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化映射数据
        self._initialize_mappings()

    def _initialize_mappings(self) -> None:
        """初始化所有映射数据"""
        try:
            self._load_player_mappings()
            self._load_team_mappings()
        except Exception as e:
            self.logger.error(f"Error initializing mappings: {e}")

    def _load_player_mappings(self) -> None:
        """加载球员映射数据（优先使用缓存）"""
        try:
            # 检查缓存是否存在且有效
            if self._is_cache_valid(self.player_cache_file):
                self._load_player_cache()
            else:
                # 获取最新数据
                player_data = self.player_fetcher.get_player_profile()
                if player_data:
                    players = self._parse_player_data(player_data)
                    self._update_player_cache(players)
                    for player in players:
                        self.player_mapping.add_player(player)
        except Exception as e:
            self.logger.error(f"Error loading player mappings: {e}")

    def _load_team_mappings(self) -> None:
        """加载球队映射数据"""
        try:
            if self._is_cache_valid(self.team_cache_file):
                self._load_team_cache()
            else:
                # 从数据文件加载球队信息
                csv_path = NBAConfig.PATHS.DATA_DIR / "nba_team_profile.csv"
                df = pd.read_csv(csv_path)
                
                # 创建不同格式的映射
                for _, row in df.iterrows():
                    team_id = int(row['TEAM_ID'])
                    # 添加各种形式的球队名称映射
                    self.team_mapping[row['ABBREVIATION'].lower()] = team_id
                    self.team_mapping[row['NICKNAME_x'].lower()] = team_id
                    self.team_mapping[f"{row['CITY_x']} {row['NICKNAME_x']}".lower()] = team_id
                
                # 更新缓存
                self._update_team_cache()
        except Exception as e:
            self.logger.error(f"Error loading team mappings: {e}")

    def _is_cache_valid(self, cache_file: Path) -> bool:
        """检查缓存是否有效"""
        try:
            if not cache_file.exists():
                return False
                
            with cache_file.open('r') as f:
                cache_data = json.load(f)
                
            last_update = datetime.fromtimestamp(cache_data.get('timestamp', 0))
            time_diff = (datetime.now() - last_update).total_seconds()
            
            return time_diff < self.cache_duration
        except Exception as e:
            self.logger.error(f"Error checking cache validity: {e}")
            return False

    def _load_player_cache(self) -> None:
        """从缓存加载球员映射"""
        try:
            with self.player_cache_file.open('r') as f:
                cache_data = json.load(f)
                for player_data in cache_data.get('players', []):
                    player = PlayerBasicInfo(**player_data)
                    self.player_mapping.add_player(player)
            self.logger.info("Successfully loaded player mappings from cache")
        except Exception as e:
            self.logger.error(f"Error loading player cache: {e}")

    def _load_team_cache(self) -> None:
        """从缓存加载球队映射"""
        try:
            with self.team_cache_file.open('r') as f:
                cache_data = json.load(f)
                self.team_mapping = {k: int(v) for k, v in cache_data.get('teams', {}).items()}
            self.logger.info("Successfully loaded team mappings from cache")
        except Exception as e:
            self.logger.error(f"Error loading team cache: {e}")

    def _update_player_cache(self, players: List[PlayerBasicInfo]) -> None:
        """更新球员映射缓存"""
        try:
            cache_data = {
                'timestamp': datetime.now().timestamp(),
                'players': [self._player_to_dict(p) for p in players]
            }
            with self.player_cache_file.open('w') as f:
                json.dump(cache_data, f, indent=4)
            self.logger.info("Successfully updated player cache")
        except Exception as e:
            self.logger.error(f"Error updating player cache: {e}")

    def _update_team_cache(self) -> None:
        """更新球队映射缓存"""
        try:
            cache_data = {
                'timestamp': datetime.now().timestamp(),
                'teams': self.team_mapping
            }
            with self.team_cache_file.open('w') as f:
                json.dump(cache_data, f, indent=4)
            self.logger.info("Successfully updated team cache")
        except Exception as e:
            self.logger.error(f"Error updating team cache: {e}")

    @staticmethod
    def _player_to_dict(player: PlayerBasicInfo) -> dict:
        """将PlayerBasicInfo对象转换为可序列化的字典"""
        return {
            'person_id': player.person_id,
            'name': player.name,
            'position': player.position,
            'height': player.height,
            'weight': player.weight,
            'jersey': player.jersey,
            'team_info': player.team_info,
            'draft_info': player.draft_info,
            'career_info': player.career_info,
            'college': player.college,
            'country': player.country
        }

    @staticmethod
    def _parse_player_data(data: Dict) -> List[PlayerBasicInfo]:
        """解析球员数据"""
        from nba.parser.player_parser import PlayerDataParser
        parser = PlayerDataParser()
        return parser.parse_player_list(data)

    # 公共接口方法
    def get_player_id(self, name: str) -> Optional[str]:
        """获取球员ID"""
        return self.player_mapping.get_player_id(name)

    def get_player_name(self, player_id: str) -> Optional[str]:
        """获取球员名字"""
        return self.player_mapping.get_player_name(player_id)

    def get_team_id(self, team_name: str) -> Optional[int]:
        """获取球队ID"""
        return self.team_mapping.get(team_name.lower())

    def refresh_mappings(self) -> None:
        """刷新所有映射数据"""
        self.player_mapping.clear()
        self.team_mapping.clear()
        self._initialize_mappings()

# 使用示例:
"""
# 初始化服务
mapping_service = NBAMappingService()

# 获取球员ID
player_id = mapping_service.get_player_id("Stephen Curry")
print(f"Player ID: {player_id}")

# 获取球队ID
team_id = mapping_service.get_team_id("Warriors")
print(f"Team ID: {team_id}")

# 刷新映射数据
mapping_service.refresh_mappings()
"""