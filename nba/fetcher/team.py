from pathlib import Path
import pandas as pd
from typing import Optional, Dict, Union
from config.nba_config import NBAConfig
import logging

class TeamInfo:
    """NBA球队信息处理类-能够根据球队名称获取球队 ID、获取球队详细信息及其 logo 文件路径。
    它支持通过多种方式（缩写、昵称、全名）查找球队，并使用缓存机制来提高查询效率"""

    def __init__(self):
        """初始化TeamInfo类"""
        self.logger = logging.getLogger(self.__class__.__name__)
        self._load_team_data()
        self._create_lookup_maps()

    def _load_team_data(self):
        """加载球队数据"""
        csv_path = Path(NBAConfig.PATHS.DATA_DIR) / 'nba_team_profile.csv'  # Adjust the filename as necessary
        try:
            self.team_data = pd.read_csv(csv_path)
            # 设置 TEAM_ID 为索引，便于快速查找
            self.team_data.set_index('TEAM_ID', inplace=True)
            self.logger.debug(f"成功加载球队数据，共 {len(self.team_data)} 支球队。")
        except FileNotFoundError:
            raise FileNotFoundError(
                f"找不到球队数据文件，请确保 nba_team_profile.csv 文件位于以下目录：{NBAConfig.PATHS.DATA_DIR}"
            )
        except pd.errors.EmptyDataError:
            raise ValueError(f"球队数据文件 {csv_path} 是空的或格式错误。")
        except Exception as e:
            raise RuntimeError(f"加载球队数据时发生错误: {e}")

    def _create_lookup_maps(self):
        """创建球队名称到ID的映射"""
        # 将所有可能的键转换为小写，实现不区分大小写的查找
        mappings = []

        # 缩写
        abbrs = self.team_data['ABBREVIATION'].dropna().str.lower()
        team_ids_abbr = self.team_data.index[self.team_data['ABBREVIATION'].notna()]
        mappings.extend(zip(abbrs, team_ids_abbr))

        # 昵称
        nicknames = self.team_data['NICKNAME_x'].dropna().str.lower()
        team_ids_nick = self.team_data.index[self.team_data['NICKNAME_x'].notna()]
        mappings.extend(zip(nicknames, team_ids_nick))

        # 全名（城市 + 昵称）
        full_names = (self.team_data['CITY_x'].dropna() + ' ' + self.team_data['NICKNAME_x'].dropna()).str.lower()
        team_ids_full = self.team_data.index[self.team_data['CITY_x'].notna() & self.team_data['NICKNAME_x'].notna()]
        mappings.extend(zip(full_names, team_ids_full))

        # 创建映射字典
        self.team_maps = dict(mappings)
        self.logger.debug(f"创建了球队名称到ID的映射，共有 {len(self.team_maps)} 个条目。")

    def get_team_id(self, team_name: str) -> Optional[int]:
        """
        根据球队名称获取team_id

        Args:
            team_name (str): 球队名称（可以是缩写、昵称或全名）

        Returns:
            Optional[int]: 如果找到匹配的球队则返回team_id，否则返回None
        """
        team_id = self.team_maps.get(team_name.lower())
        if team_id is None:
            self.logger.warning(f"未找到球队名称: {team_name}")
        return team_id

    def get_team_logo_path(self, team_name: str) -> Optional[Path]:
        """
        获取球队logo的文件路径

        Args:
            team_name (str): 球队名称

        Returns:
            Optional[Path]: logo文件的路径，如果未找到返回None
        """
        team_id = self.get_team_id(team_name)
        if team_id is None:
            self.logger.error(f"无法获取球队ID，无法查找logo路径: {team_name}")
            return None

        try:
            # 获取对应的缩写
            abbr = self.team_data.at[team_id, 'ABBREVIATION']
            if pd.isna(abbr):
                self.logger.error(f"球队ID {team_id} 没有有效的缩写.")
                return None

            # 构建logo文件路径
            logo_path = NBAConfig.PATHS.DATA_DIR / "nba-team-logo" / f"{abbr} logo.png"

            if logo_path.exists():
                self.logger.debug(f"找到球队logo: {logo_path}")
                return logo_path
            else:
                self.logger.error(f"Logo文件不存在: {logo_path}")
                return None
        except KeyError:
            self.logger.error(f"球队ID {team_id} 不存在于球队数据中.")
            return None
        except Exception as e:
            self.logger.error(f"获取球队logo路径时出错: {e}")
            return None

    def get_team_info(self, team_name: str) -> Optional[Dict[str, Union[str, int, Path]]]:
        """
        获取球队的详细信息

        Args:
            team_name (str): 球队名称

        Returns:
            Optional[Dict]: 包含球队信息的字典，如果未找到返回None
        """
        team_id = self.get_team_id(team_name)
        if team_id is None:
            self.logger.error(f"无法获取球队信息，未找到球队ID: {team_name}")
            return None

        try:
            team_row = self.team_data.loc[team_id]
            team_info = {
                'team_id': team_id,
                'abbreviation': team_row['ABBREVIATION'],
                'nickname': team_row['NICKNAME_x'],
                'city': team_row['CITY_x'],
                'arena': team_row['ARENA'],
                'arena_capacity': team_row['ARENACAPACITY'],
                'owner': team_row['OWNER'],
                'general_manager': team_row['GENERALMANAGER'],
                'head_coach': team_row['HEADCOACH'],
                'logo_path': self.get_team_logo_path(team_name)
            }
            self.logger.debug(f"获取到球队信息: {team_info}")
            return team_info
        except KeyError:
            self.logger.error(f"球队ID {team_id} 在数据中不存在.")
            return None
        except Exception as e:
            self.logger.error(f"获取球队信息时出错: {e}")
            return None

    def __getitem__(self, team_name: str) -> Optional[int]:
        """
        允许使用字典语法获取team_id

        Example:
            team_info = TeamInfo()
            lakers_id = team_info['LAL']
        """
        return self.get_team_id(team_name)
