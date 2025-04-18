from typing import Dict, Optional, Any, List
from datetime import timedelta
from pathlib import Path
from io import BytesIO
import time
from PIL import Image, ImageDraw, ImageEnhance

from .base_fetcher import BaseNBAFetcher, BaseRequestConfig, BaseCacheConfig
from config import NBAConfig


class PlayerCacheEnum:
    """球员缓存类型枚举"""
    ACTIVE = "active"  # 活跃球员 - 不缓存
    HISTORICAL = "historical"  # 历史球员 - 永久缓存
    IMAGE_RAW = "image_raw"  # 原始图像 - 缓存90天
    IMAGE_PROCESSED = "image_processed"  # 处理后图像 - 缓存30天


class PlayerConfig:
    """球员数据配置"""
    # API接口
    BASE_URL: str = "https://stats.nba.com/stats"
    PLAYER_INFO_ENDPOINT: str = "commonplayerinfo"
    PLAYERS_LIST_ENDPOINT: str = "commonallplayers"

    # 图像服务
    IMAGE_BASE_URL: str = "https://cdn.nba.com/headshots/nba/latest"

    # 缓存路径
    CACHE_PATH = NBAConfig.PATHS.PLAYER_CACHE_DIR
    IMAGE_CACHE_PATH = NBAConfig.PATHS.DATA_DIR / "cache" / "player_images"

    # 缓存策略
    CACHE_DURATION: Dict[str, timedelta] = {
        PlayerCacheEnum.ACTIVE: timedelta(seconds=0),  # 活跃球员不缓存
        PlayerCacheEnum.HISTORICAL: timedelta(days=365 * 10),  # 历史球员缓存10年
        PlayerCacheEnum.IMAGE_RAW: timedelta(days=90),  # 原始图像缓存90天
        PlayerCacheEnum.IMAGE_PROCESSED: timedelta(days=30)  # 处理后图像缓存30天
    }


class PlayerFetcher(BaseNBAFetcher):
    """NBA球员数据获取器
    特点:
    1. 支持批量获取球员详细信息
    2. 简化的缓存策略: 历史球员永久缓存，活跃球员不缓存，球员列表不缓存
    3. 根据ROSTERSTATUS判断球员是否活跃
    4. 支持获取和处理球员头像图片
    """

    def __init__(self, custom_config: Optional[PlayerConfig] = None):
        """初始化球员数据获取器"""
        self.player_config = custom_config or PlayerConfig()

        # 配置缓存 - 默认不缓存，仅历史球员使用缓存
        cache_config = BaseCacheConfig(
            duration=timedelta(seconds=0),  # 默认不缓存
            root_path=self.player_config.CACHE_PATH,
            dynamic_duration=self.player_config.CACHE_DURATION  # 使用动态缓存时间
        )

        # 创建基础请求配置
        base_config = BaseRequestConfig(
            base_url=self.player_config.BASE_URL,
            cache_config=cache_config
        )

        # 初始化基类
        super().__init__(base_config)

        # 添加内部缓存，用于存储球员状态 (活跃/历史)
        self._player_status_cache = {}

        # 确保图像缓存目录存在
        self.player_config.IMAGE_CACHE_PATH.mkdir(parents=True, exist_ok=True)
        for subdir in ['raw', 'processed']:
            (self.player_config.IMAGE_CACHE_PATH / subdir).mkdir(exist_ok=True)

    # === 球员基本信息相关方法 ===

    def _is_active_player(self, player_data: Dict[str, Any]) -> bool:
        try:
            # 从commonplayerinfo结果中提取球员状态
            if 'resultSets' not in player_data:
                self.logger.debug("球员数据缺少resultSets字段，默认为活跃球员")
                return True  # 默认为活跃

            for result_set in player_data['resultSets']:
                if result_set['name'] == 'CommonPlayerInfo' and result_set['rowSet']:
                    # 获取headers和数据行
                    headers = result_set['headers']
                    row = result_set['rowSet'][0]

                    # 找到ROSTERSTATUS的索引
                    if 'ROSTERSTATUS' in headers:
                        roster_status_idx = headers.index('ROSTERSTATUS')
                        roster_status = row[roster_status_idx]

                        # 记录状态值
                        self.logger.debug(f"检测到球员ROSTERSTATUS={roster_status}")

                        # 直接检查ROSTERSTATUS字段
                        if isinstance(roster_status, str) and roster_status.lower() == "inactive":
                            return False

                        # 也兼容数字格式的状态值
                        if roster_status == 0:
                            return False

            # 默认为活跃
            return True

        except Exception as e:
            self.logger.error(f"球员状态判断失败 | error={str(e)}", exc_info=True)
            return True  # 出错时默认为活跃

    def _get_player_status(self, player_id: int, player_data: Optional[Dict[str, Any]] = None) -> str:
        # 如果状态已缓存，直接返回
        if player_id in self._player_status_cache:
            status = self._player_status_cache[player_id]
            self.logger.debug(f"球员状态缓存命中 | player_id={player_id} | status={status}")
            return status

        # 如果提供了球员数据，则从数据中判断
        if player_data:
            is_active = self._is_active_player(player_data)
            status = PlayerCacheEnum.ACTIVE if is_active else PlayerCacheEnum.HISTORICAL

            # 缓存状态
            self._player_status_cache[player_id] = status
            self.logger.debug(f"球员状态计算完成 | player_id={player_id} | is_active={is_active} | status={status}")
            return status

        # 默认为活跃
        self.logger.debug(f"未提供球员数据，默认为活跃球员 | player_id={player_id}")
        return PlayerCacheEnum.ACTIVE

    def get_player_info(self, player_id: int, force_update: bool = False) -> Optional[Dict[str, Any]]:
        """
        获取单个球员的详细信息

        Args:
            player_id: 球员ID
            force_update: 是否强制更新缓存

        Returns:
            Dict: 球员详细信息
        """
        try:
            cache_key = f"player_info_{player_id}"

            # 尝试获取缓存数据
            cached_data = self.cache_manager.get(
                prefix=self.__class__.__name__.lower(),
                identifier=cache_key
            )

            cached_status = None
            # 如果有缓存且不强制更新，检查是否为历史球员
            if cached_data is not None and not force_update:
                cached_status = self._get_player_status(player_id, cached_data)

                # 如果是历史球员，直接使用缓存
                if cached_status == PlayerCacheEnum.HISTORICAL:
                    return cached_data

                # 否则是活跃球员，请求新数据

            # 请求参数
            params = {
                "PlayerID": player_id,
                "LeagueID": ""  # LeagueID 可以为空字符串
            }

            # 获取新数据
            data = self.fetch_data(
                endpoint=self.player_config.PLAYER_INFO_ENDPOINT,
                params=params,
                cache_key=cache_key,
                force_update=True,  # 活跃球员总是获取最新数据
                cache_status_key=cached_status
            )

            # 增加数据检查
            if data and 'resultSets' in data:
                # 判断球员状态
                current_status = self._get_player_status(player_id, data)

                # 如果是历史球员，设置长期缓存
                if current_status == PlayerCacheEnum.HISTORICAL:
                    metadata = {"player_id": player_id, "player_status": current_status}
                    self.cache_manager.set(
                        prefix=self.__class__.__name__.lower(),
                        identifier=cache_key,
                        data=data,
                        metadata=metadata
                    )

                return data

            self.logger.warning(f"获取球员ID {player_id} 的信息返回无效数据格式")
            return None

        except Exception as e:
            self.logger.error(f"获取球员ID为 {player_id} 的信息失败: {e}")
            return None

    def batch_get_players_info(self, player_ids: List[int],
                               force_update: bool = False) -> Dict[str, Dict]:
        """
        批量获取多个球员信息

        Args:
            player_ids: 球员ID列表
            force_update: 是否强制更新缓存

        Returns:
            Dict[str, Dict]: 球员信息字典，key为球员ID字符串
        """
        self.logger.info(f"开始球员数据同步任务 | player_count={len(player_ids)} | force_update={force_update}")

        # 定义单个获取函数
        def fetch_single_player(player_id):
            return self.get_player_info(player_id, force_update)

        # 使用基类的批量获取实现
        results = self.batch_fetch(
            ids=player_ids,
            fetch_func=fetch_single_player,
            task_name="player_info_batch",
            batch_size=20  # 每批20个请求
        )

        return results

    def get_all_players_info(self, current_season_only: bool = False) -> Optional[Dict[str, Any]]:
        """
        获取所有NBA球员数据 - 始终获取最新数据，不缓存
        Args:
            current_season_only: 是否只获取当前赛季球员

        Returns:
            Dict: 所有球员数据
        """
        try:
            # 请求参数
            params = {
                "LeagueID": "00",  # 00表示NBA联盟
                "IsOnlyCurrentSeason": 1 if current_season_only else 0
            }

            # 获取新数据 - 不设置cache_key，不缓存
            self.logger.info(f"获取NBA球员名册 | current_season_only={current_season_only} | cache_policy=no_cache")
            data = self.fetch_data(
                endpoint=self.player_config.PLAYERS_LIST_ENDPOINT,
                params=params,
                cache_key=None,  # 不缓存
            )

            # 增加数据检查
            if data and 'resultSets' in data:
                return data

            self.logger.warning("获取球员名册返回无效数据格式")
            return None

        except Exception as e:
            self.logger.error(f"获取所有球员数据失败: {e}")
            return None

    # === 球员图像相关方法 ===

    def get_player_headshot_url(self, player_id: int, size: str = "260x190") -> str:
        """获取NBA官方球员头像URL

        Args:
            player_id: 球员ID
            size: 图像大小，可以是"260x190"(小)或"1040x760"(大)

        Returns:
            str: 图像URL
        """
        valid_sizes = ["260x190", "1040x760"]
        if size not in valid_sizes:
            self.logger.warning(f"无效的图像尺寸 {size}，使用默认值 260x190")
            size = "260x190"

        return f"{self.player_config.IMAGE_BASE_URL}/{size}/{player_id}.png"

    def _get_image_raw_cache_path(self, player_id: int, size: str = "260x190") -> Path:
        """获取原始图像缓存路径

        Args:
            player_id: 球员ID
            size: 图像尺寸

        Returns:
            Path: 缓存文件路径
        """
        return self.player_config.IMAGE_CACHE_PATH / f"raw/player_{player_id}_{size}.png"

    def _get_image_processed_cache_path(self, player_id: int, size: int, is_circle: bool) -> Path:
        """获取处理后图像的缓存路径

        Args:
            player_id: 球员ID
            size: 图像大小
            is_circle: 是否为圆形

        Returns:
            Path: 缓存文件路径
        """
        return self.player_config.IMAGE_CACHE_PATH / f"processed/player_{player_id}_s{size}_c{int(is_circle)}.png"

    def fetch_player_image_raw(self, player_id: int, size: str = "260x190",
                               force_update: bool = False) -> Optional[bytes]:
        """获取球员原始图像数据

        Args:
            player_id: 球员ID
            size: 图像大小，可以是"260x190"(小)或"1040x760"(大)
            force_update: 是否强制更新缓存

        Returns:
            Optional[bytes]: 图像二进制数据，失败时返回None
        """
        # 尝试从缓存获取
        cache_path = self._get_image_raw_cache_path(player_id, size)

        if not force_update and cache_path.exists():
            # 检查文件修改时间，决定是否使用缓存
            file_age = time.time() - cache_path.stat().st_mtime
            max_age = self.player_config.CACHE_DURATION[PlayerCacheEnum.IMAGE_RAW].total_seconds()

            if file_age < max_age:
                try:
                    self.logger.debug(f"从缓存读取球员图像: {player_id}")
                    with open(cache_path, 'rb') as f:
                        return f.read()
                except Exception as e:
                    self.logger.error(f"读取缓存图像失败: {e}")

        # 从API获取
        url = self.get_player_headshot_url(player_id, size)
        self.logger.info(f"获取球员 {player_id} 图像")

        try:
            image_data = self.http_manager.make_binary_request(url=url)

            if not image_data:
                self.logger.error(f"获取球员图像失败: 未返回数据")
                return None

            # 保存到缓存
            with open(cache_path, 'wb') as f:
                f.write(image_data)

            self.logger.debug(f"已缓存球员 {player_id} 图像: {len(image_data)} 字节")
            return image_data

        except Exception as e:
            self.logger.error(f"获取球员图像失败: {e}")
            return None

    def _process_image(self, image_data: bytes, target_size: int = 100,
                       is_circle: bool = True) -> Optional[Image.Image]:
        """处理图像数据

        Args:
            image_data: 原始图像二进制数据
            target_size: 目标大小
            is_circle: 是否制作圆形头像

        Returns:
            Optional[Image.Image]: 处理后的PIL图像对象
        """
        try:
            img = Image.open(BytesIO(image_data))

            # 1. 将图像转换为RGBA模式以支持透明度
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # 2. 裁剪为正方形（从中心裁剪）
            width, height = img.size
            crop_size = min(width, height)
            left = (width - crop_size) // 2
            top = (height - crop_size) // 2
            img = img.crop((left, top, left + crop_size, top + crop_size))

            # 3. 调整到目标大小
            img = img.resize((target_size, target_size), Image.Resampling.LANCZOS)

            # 4. 如果需要圆形处理
            if is_circle:
                # 创建一个圆形mask
                mask = Image.new('L', (target_size, target_size), 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, target_size - 1, target_size - 1), fill=255)

                # 创建新的透明背景图像
                circle_img = Image.new('RGBA', (target_size, target_size), (0, 0, 0, 0))
                # 将头像应用mask后贴到透明背景上
                circle_img.paste(img, (0, 0), mask)

                # 增强图像效果
                enhancer = ImageEnhance.Contrast(circle_img)
                circle_img = enhancer.enhance(1.2)

                return circle_img

            return img

        except Exception as e:
            self.logger.error(f"图像处理错误: {e}")
            return None

    def get_player_image(self, player_id: int, size: int = 100,
                         is_circle: bool = True, force_update: bool = False) -> Image.Image:
        """获取处理后的球员头像

        Args:
            player_id: 球员ID
            size: 目标图像大小（像素）
            is_circle: 是否返回圆形头像
            force_update: 是否强制更新缓存

        Returns:
            Image.Image: 处理后的图像，出错时返回占位图像
        """
        # 检查处理后图像缓存
        cache_path = self._get_image_processed_cache_path(player_id, size, is_circle)

        if not force_update and cache_path.exists():
            # 检查文件修改时间
            file_age = time.time() - cache_path.stat().st_mtime
            max_age = self.player_config.CACHE_DURATION[PlayerCacheEnum.IMAGE_PROCESSED].total_seconds()

            if file_age < max_age:
                try:
                    self.logger.debug(f"从缓存加载处理后图像: {player_id}")
                    return Image.open(cache_path)
                except Exception as e:
                    self.logger.error(f"读取处理后图像缓存失败: {e}")

        # 获取原始图像
        image_data = self.fetch_player_image_raw(player_id, force_update=force_update)

        if not image_data:
            self.logger.warning(f"未能获取球员 {player_id} 图像，返回占位图")
            return self._create_placeholder()

        # 处理图像
        processed_image = self._process_image(image_data, size, is_circle)

        if not processed_image:
            self.logger.warning(f"处理球员 {player_id} 图像失败，返回占位图")
            return self._create_placeholder()

        # 缓存处理后的图像
        try:
            processed_image.save(cache_path, "PNG")
            self.logger.debug(f"已缓存处理后的球员 {player_id} 图像")
        except Exception as e:
            self.logger.error(f"缓存处理后图像失败: {e}")

        return processed_image

    @staticmethod
    def _create_placeholder(size: int = 100) -> Image.Image:
        """创建占位图像
        Args:
            size: 图像大小
        Returns:
            Image.Image: 占位图像
        """
        placeholder = Image.new('RGBA', (size, size), (200, 200, 200, 255))
        return placeholder

    def get_player_info_with_image(self, player_id: int, image_size: int = 100,
                                   is_circle: bool = True, force_update: bool = False) -> Dict[str, Any]:
        """获取球员信息和头像

        Args:
            player_id: 球员ID
            image_size: 图像大小
            is_circle: 是否圆形图像
            force_update: 是否强制更新

        Returns:
            Dict: 包含球员信息和图像的字典
        """
        # 同时获取球员信息和图像
        player_info = self.get_player_info(player_id, force_update)
        player_image = self.get_player_image(player_id, image_size, is_circle, force_update)

        result = {
            "player_id": player_id,
            "info": player_info,
            "image": player_image
        }

        return result

    def cleanup_cache(self, older_than: Optional[timedelta] = None) -> None:
        """
        清理缓存数据 - 包括球员信息和图像缓存

        Args:
            older_than: 可选的时间间隔，清理该时间之前的缓存
        """
        try:
            # 清理球员信息缓存
            prefix = self.__class__.__name__.lower()
            self.logger.info(f"正在清理球员信息缓存")
            self.cache_manager.clear(prefix=prefix, age=older_than)

            # 清空状态缓存
            self._player_status_cache = {}

            # 清理图像缓存
            self.logger.info(f"正在清理球员图像缓存")

            # 如果未提供时间间隔，使用默认值
            if not older_than:
                raw_age = self.player_config.CACHE_DURATION[PlayerCacheEnum.IMAGE_RAW]
                processed_age = self.player_config.CACHE_DURATION[PlayerCacheEnum.IMAGE_PROCESSED]
            else:
                raw_age = older_than
                processed_age = older_than

            # 清理原始图像
            self._clean_image_directory(
                self.player_config.IMAGE_CACHE_PATH / "raw",
                raw_age
            )

            # 清理处理后图像
            self._clean_image_directory(
                self.player_config.IMAGE_CACHE_PATH / "processed",
                processed_age
            )

        except Exception as e:
            self.logger.error(f"清理缓存失败: {e}")

    def _clean_image_directory(self, directory: Path, max_age: timedelta) -> None:
        """清理指定目录中的过期图像文件

        Args:
            directory: 目录路径
            max_age: 最大文件年龄
        """
        if not directory.exists():
            return

        count = 0
        cutoff_time = time.time() - max_age.total_seconds()

        for file_path in directory.glob("*.png"):
            if file_path.stat().st_mtime < cutoff_time:
                try:
                    file_path.unlink()
                    count += 1
                except Exception as e:
                    self.logger.error(f"删除文件失败 {file_path}: {e}")

        self.logger.info(f"已从 {directory} 清理 {count} 个图像文件")
