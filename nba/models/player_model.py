from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from nba.models.team_model import TeamProfile

class PlayerDraft(BaseModel):
    """选秀信息"""
    year: Optional[int] = None
    round: Optional[int] = None
    number: Optional[int] = None
    model_config = ConfigDict(populate_by_name=True)

class PlayerCareer(BaseModel):
    """生涯数据"""
    from_year: str
    to_year: str
    points: float = Field(default=0.0)
    rebounds: float = Field(default=0.0)
    assists: float = Field(default=0.0)
    stats_timeframe: str = Field(default="Season")
    model_config = ConfigDict(populate_by_name=True)

class PlayerRegistry:
    """管理球员ID和姓名的映射关系"""
    _instance = None
    
    def __init__(self):
        self._id_to_name = {}  # id -> full_name
        self._name_to_id = {}  # normalized name -> id
        
    @classmethod
    def get_instance(cls) -> 'PlayerRegistry':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = PlayerRegistry()
        return cls._instance
    
    def register(self, player_id: int, first_name: str, last_name: str) -> None:
        """注册球员信息"""
        full_name = f"{first_name} {last_name}"
        normalized_name = PlayerProfile.normalize_name(full_name).lower()
        
        # 记录ID到姓名的映射
        self._id_to_name[player_id] = full_name
        
        # 记录全名到ID的映射
        self._name_to_id[normalized_name] = player_id
        
        # 处理姓氏映射
        last_name_lower = last_name.lower()
        if last_name_lower in self._name_to_id and self._name_to_id[last_name_lower] != player_id:
            # 如果姓氏已存在且对应不同的球员，移除姓氏映射以避免歧义
            del self._name_to_id[last_name_lower]
        else:
            self._name_to_id[last_name_lower] = player_id
    
    def get_id(self, name: str) -> Optional[int]:
        """通过姓名获取球员ID"""
        if not isinstance(name, str):
            return None
            
        try:
            normalized_name = PlayerProfile.normalize_name(name).lower()
            return self._name_to_id.get(normalized_name)
        except Exception as e:
            return None
    
    def get_name(self, player_id: int) -> Optional[str]:
        """通过ID获取球员姓名"""
        return self._id_to_name.get(player_id)
    
    def clear(self) -> None:
        """清空注册信息"""
        self._id_to_name.clear()
        self._name_to_id.clear()

class PlayerProfile(BaseModel):
    """球员基本信息"""
    person_id: int
    last_name: str
    first_name: str
    player_slug: str
    team_id: int
    jersey_number: Optional[str] = None
    position: str
    height: str
    weight: str
    college: Optional[str] = None
    country: Optional[str] = None
    draft: PlayerDraft
    roster_status: float = Field(default=1.0)
    career: PlayerCareer

    model_config = ConfigDict(populate_by_name=True)

    def __init__(self, **data):
        super().__init__(**data)
        # 在创建实例时自动注册
        PlayerRegistry.get_instance().register(
            self.person_id, 
            self.first_name, 
            self.last_name
        )

    @property
    def team(self) -> Optional[TeamProfile]:
        """获取关联的球队信息"""
        return TeamProfile.from_id(self.team_id)

    @property
    def full_name(self) -> str:
        """获取球员全名"""
        return f"{self.first_name} {self.last_name}"

    @property
    def headshot_url(self) -> str:
        """获取球员头像URL"""
        return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{self.person_id}.png"

    @classmethod
    def find_by_name(cls, name: str) -> Optional[int]:
        """通过姓名查找球员ID"""
        return PlayerRegistry.get_instance().get_id(name)

    @classmethod
    def find_by_id(cls, player_id: int) -> Optional[str]:
        """通过ID查找球员姓名"""
        return PlayerRegistry.get_instance().get_name(player_id)

    @staticmethod
    def normalize_name(name: str) -> str:
        """标准化球员姓名格式"""
        special_prefixes = ['de', 'le', 'la', 'mc', 'van', 'von']
        words = name.lower().split()
        normalized = []
        
        for word in words:
            special_case = False
            # 先检查特殊前缀
            for prefix in special_prefixes:
                if word.startswith(prefix) and len(word) > len(prefix):
                    # 前缀首字母大写，且前缀后的第一个字母也大写
                    word = prefix.capitalize() + word[len(prefix)].upper() + word[len(prefix)+1:]
                    special_case = True
                    break
                    
            # 如果不是特殊情况，则首字母大写
            if not special_case:
                word = word.capitalize()
                
            normalized.append(word)
            
        return " ".join(normalized)