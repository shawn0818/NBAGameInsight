from typing import Optional, Dict, List, Tuple
from pydantic import BaseModel, Field

# 球队名称到ID的映射
TEAM_ID_MAPPING = {
    # 缩写映射
    'atl': 1610612737, 'bos': 1610612738, 'cle': 1610612739,
    'nop': 1610612740, 'chi': 1610612741, 'dal': 1610612742,
    'den': 1610612743, 'gsw': 1610612744, 'hou': 1610612745,
    'lac': 1610612746, 'lal': 1610612747, 'mia': 1610612748,
    'mil': 1610612749, 'min': 1610612750, 'bkn': 1610612751,
    'nyk': 1610612752, 'orl': 1610612753, 'ind': 1610612754,
    'phi': 1610612755, 'phx': 1610612756, 'por': 1610612757,
    'sac': 1610612758, 'sas': 1610612759, 'okc': 1610612760,
    'tor': 1610612761, 'uta': 1610612762, 'mem': 1610612763,
    'was': 1610612764, 'det': 1610612765, 'cha': 1610612766,
}

# 球队全称和别名映射
TEAM_NAME_VARIANTS = {
    'lakers': ['los angeles', 'la lakers', 'lal'],
    'clippers': ['los angeles', 'la clippers', 'lac'],
    'warriors': ['golden state', 'gsw', 'dubs'],
    'celtics': ['boston', 'bos'],
    'nets': ['brooklyn', 'bkn'],
    'knicks': ['new york', 'ny', 'nyk'],
    'sixers': ['philadelphia', '76ers', 'phi'],
    'raptors': ['toronto', 'tor'],
    'bulls': ['chicago', 'chi'],
    'cavaliers': ['cleveland', 'cavs', 'cle'],
    'pistons': ['detroit', 'det'],
    'pacers': ['indiana', 'ind'],
    'bucks': ['milwaukee', 'mil'],
    'hawks': ['atlanta', 'atl'],
    'hornets': ['charlotte', 'cha'],
    'heat': ['miami', 'mia'],
    'magic': ['orlando', 'orl'],
    'wizards': ['washington', 'wiz', 'was'],
    'nuggets': ['denver', 'den'],
    'timberwolves': ['minnesota', 'wolves', 'min'],
    'thunder': ['oklahoma city', 'okc'],
    'blazers': ['portland', 'trail blazers', 'por'],
    'jazz': ['utah', 'uta'],
    'mavericks': ['dallas', 'mavs', 'dal'],
    'rockets': ['houston', 'hou'],
    'grizzlies': ['memphis', 'griz', 'mem'],
    'pelicans': ['new orleans', 'nola', 'nop'],
    'spurs': ['san antonio', 'sas'],
    'suns': ['phoenix', 'phx'],
    'kings': ['sacramento', 'sac']
}

# 联盟和分区的映射
CONFERENCE_DIVISION_MAPPING = {
    'eastern': {
        'atlantic': ['celtics', 'nets', 'knicks', '76ers', 'raptors'],
        'central': ['bulls', 'cavaliers', 'pistons', 'pacers', 'bucks'],
        'southeast': ['hawks', 'hornets', 'heat', 'magic', 'wizards']
    },
    'western': {
        'northwest': ['nuggets', 'timberwolves', 'thunder', 'trail blazers', 'jazz'],
        'pacific': ['warriors', 'clippers', 'lakers', 'suns', 'kings'],
        'southwest': ['mavericks', 'rockets', 'grizzlies', 'pelicans', 'spurs']
    }
}

def get_team_id(query: str) -> Optional[Tuple[int, str]]:
    """通过名称获取球队ID和标准名称"""
    query = query.lower().strip()
    
    # 1. 直接匹配缩写
    if query in TEAM_ID_MAPPING:
        team_id = TEAM_ID_MAPPING[query]
        # 反查标准名称
        for name, variants in TEAM_NAME_VARIANTS.items():
            if query in variants:
                return team_id, name.title()
        return team_id, query.upper()
    
    # 2. 在所有可能的名称中搜索
    matches = []
    for standard_name, variants in TEAM_NAME_VARIANTS.items():
        # 将标准名称也加入搜索范围
        all_names = [standard_name] + variants
        
        for name in all_names:
            # 完全匹配
            if query == name:
                return TEAM_ID_MAPPING[variants[-1]], standard_name.title()
            
            # 前缀匹配
            if name.startswith(query):
                matches.append((standard_name, len(name) - len(query)))
            
            # 包含匹配
            elif query in name or name in query:
                matches.append((standard_name, len(name)))
    
    # 3. 如果有匹配结果，返回最佳匹配
    if matches:
        # 按匹配长度排序，选择最短的（最精确的）匹配
        best_match = sorted(matches, key=lambda x: x[1])[0][0]
        return TEAM_ID_MAPPING[TEAM_NAME_VARIANTS[best_match][-1]], best_match.title()
    
    # 4. 处理复合城市名称
    if ' ' in query:
        parts = query.split()
        if len(parts) >= 2:
            # 尝试匹配城市名称
            city = ' '.join(parts[:2])  # 取前两个词作为城市名
            for standard_name, variants in TEAM_NAME_VARIANTS.items():
                if any(city in variant.lower() for variant in variants):
                    return TEAM_ID_MAPPING[variants[0]], standard_name.title()
                    
            # 尝试匹配完整名称
            for standard_name, variants in TEAM_NAME_VARIANTS.items():
                if any(query in variant.lower() for variant in variants):
                    return TEAM_ID_MAPPING[variants[0]], standard_name.title()
    
    return None

def get_division_rivals(team_name: str) -> List[str]:
    """获取同一分区的竞争对手
    
    根据球队名称获取同一分区的其他球队列表。
    
    Args:
        team_name: 球队名称（支持多种格式）
        
    Returns:
        List[str]: 同分区竞争对手列表，标准名称格式
        
    Example:
        >>> get_division_rivals('celtics')
        ['Nets', 'Knicks', '76ers', 'Raptors']
    """
    result = get_team_id(team_name)
    if not result:
        return []
        
    _, standard_name = result
    standard_name = standard_name.lower()
    
    for conference in CONFERENCE_DIVISION_MAPPING.values():
        for division_teams in conference.values():
            if standard_name in division_teams:
                return [team.title() for team in division_teams if team != standard_name]
    return []

def get_conference_teams(conference: str) -> List[str]:
    """获取指定联盟的所有球队"""
    conf = conference.lower()
    if conf not in CONFERENCE_DIVISION_MAPPING:
        return []
    
    teams = []
    for division_teams in CONFERENCE_DIVISION_MAPPING[conf].values():
        teams.extend(division_teams)
    return [team.title() for team in teams]

def are_division_rivals(team1: str, team2: str) -> bool:
    """判断两支球队是否为分区竞争对手
    
    Args:
        team1: 第一支球队名称
        team2: 第二支球队名称
        
    Returns:
        bool: 是否为同一分区的竞争对手
        
    Example:
        >>> are_division_rivals('celtics', 'nets')
        True
        >>> are_division_rivals('celtics', 'lakers')
        False
    """
    rivals = get_division_rivals(team1)
    result = get_team_id(team2)
    return result is not None and result[1] in rivals

class TeamSocialSite(BaseModel):
    """球队社交媒体信息"""
    account_type: str
    website_link: str

class TeamAward(BaseModel):
    """球队荣誉信息
    
    Attributes:
        year_awarded: 获奖年份
        opposite_team: 对手球队名称（如果适用）
    """
    year_awarded: int
    opposite_team: Optional[str] = None

class TeamHofPlayer(BaseModel):
    """名人堂球员信息
    
    Attributes:
        player_id: 球员ID
        player: 球员姓名
        position: 场上位置
        jersey: 球衣号码
        seasons_with_team: 效力球队的赛季
        year: 入选名人堂年份
    """
    player_id: Optional[int]
    player: str
    position: Optional[str]
    jersey: Optional[str]
    seasons_with_team: Optional[str]
    year: int

class TeamRetiredPlayer(BaseModel):
    """退役球衣球员信息
    
    Attributes:
        player_id: 球员ID
        player: 球员姓名
        position: 场上位置
        jersey: 退役的球衣号码
        seasons_with_team: 效力球队的赛季
        year: 球衣退役年份
    """
    player_id: Optional[int]
    player: str
    position: str
    jersey: str
    seasons_with_team: str
    year: int

class TeamProfile(BaseModel):
    """球队详细信息模型
    
    包含球队的完整信息，包括：
    1. 基础信息（队名、城市、场馆等）
    2. 管理层信息（老板、总经理、主教练）
    3. 历史荣誉（总冠军、分区冠军等）
    4. 名人堂成员
    5. 退役球衣
    
    所有属性都是只读的，创建后不可修改。
    """
    # 基础信息
    team_id: Optional[int] = None
    abbreviation: Optional[str] = None
    nickname: Optional[str] = None
    year_founded: Optional[int] = None
    city: Optional[str] = None
    arena: Optional[str] = None
    arena_capacity: Optional[str] = None
    owner: Optional[str] = None
    general_manager: Optional[str] = None
    head_coach: Optional[str] = None
    dleague_affiliation: Optional[str] = None

    # 扩展信息
    championships: List[TeamAward] = Field(default_factory=list)
    conference_titles: List[TeamAward] = Field(default_factory=list)
    division_titles: List[TeamAward] = Field(default_factory=list)
    hof_players: List[TeamHofPlayer] = Field(default_factory=list)
    retired_numbers: List[TeamRetiredPlayer] = Field(default_factory=list)

    class Config:
        """Pydantic配置"""
        frozen = True

    @property
    def full_name(self) -> str:
        """获取球队全名（城市+昵称）"""
        return f"{self.city} {self.nickname}" if self.city else self.nickname

    @property
    def total_championships(self) -> int:
        """获取球队总冠军数"""
        return len(self.championships)
    
    @property
    def latest_championship(self) -> Optional[TeamAward]:
        """获取最近一次冠军信息"""
        return max(self.championships, key=lambda x: x.year_awarded) if self.championships else None
    
    @property
    def titles_by_decade(self) -> Dict[str, int]:
        """按十年代统计冠军数量
        
        Returns:
            Dict[str, int]: 每个十年代的冠军数量
            
        Example:
            >>> team.titles_by_decade
            {'1960s': 8, '1970s': 1, '1980s': 3}
        """
        decades = {}
        for award in self.championships:
            decade = f"{award.year_awarded // 10 * 10}s"
            decades[decade] = decades.get(decade, 0) + 1
        return decades

    @classmethod
    def get_team_by_id(cls, team_id: int) -> Optional['TeamProfile']:
        """根据ID获取球队信息
        
        Args:
            team_id: 球队ID
            
        Returns:
            Optional[TeamProfile]: 球队信息对象，如果未找到返回None
        """
        try:
            from nba.fetcher.team_fetcher import TeamFetcher
            fetcher = TeamFetcher()
            return fetcher.get_team_details(team_id)
        except Exception:
            return None