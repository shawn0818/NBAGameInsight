from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


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
        self._id_to_name[player_id] = full_name
        self._name_to_id[full_name.lower()] = player_id

        # 处理姓氏映射
        last_name_lower = last_name.lower()
        if last_name_lower in self._name_to_id and self._name_to_id[last_name_lower] != player_id:
            del self._name_to_id[last_name_lower]
        else:
            self._name_to_id[last_name_lower] = player_id

    def get_id(self, name: str) -> Optional[int]:
        """通过姓名获取球员ID"""
        if not isinstance(name, str):
            return None
        return self._name_to_id.get(name.lower())

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
    first_name: str
    last_name: str
    player_slug: str
    team_id: Optional[int] = None
    team_slug: Optional[str] = None
    team_city: Optional[str] = None
    team_name: Optional[str] = None
    team_abbreviation: Optional[str] = None
    jersey_number: Optional[str] = None
    position: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    college: Optional[str] = None
    country: Optional[str] = None
    roster_status: float = Field(default=1.0)

    model_config = ConfigDict(populate_by_name=True)

    def __init__(self, **data):
        super().__init__(**data)
        if self.person_id and self.first_name and self.last_name:
            PlayerRegistry.get_instance().register(
                self.person_id,
                self.first_name,
                self.last_name
            )

    @property
    def full_name(self) -> str:
        """获取球员标准全名"""
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