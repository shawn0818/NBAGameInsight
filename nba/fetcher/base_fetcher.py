import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Any, Union, List, Callable
from urllib.parse import urlencode

from utils.http_handler import HTTPRequestManager, RetryConfig
from utils.logger_handler import AppLogger


class BaseCacheConfig:
    """基础缓存配置"""

    def __init__(
            self,
            duration: timedelta,
            root_path: Union[str, Path],
            file_pattern: str = "{prefix}_{identifier}.json",
            dynamic_duration: Optional[Dict[Any, timedelta]] = None
    ):
        self.duration = duration
        self.root_path = Path(root_path)
        self.file_pattern = file_pattern
        self.dynamic_duration = dynamic_duration or {}

        try:
            self.root_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Failed to create cache directory: {e}")

    def get_cache_path(self, prefix: str, identifier: str) -> Path:
        """获取缓存文件路径"""
        if not prefix or not identifier:
            raise ValueError("prefix and identifier cannot be empty")
        filename = self.file_pattern.format(prefix=prefix, identifier=identifier)
        return self.root_path / filename

    def get_duration(self, key: Any = None) -> timedelta:
        """获取缓存时长,支持动态缓存时间"""
        if key is not None and key in self.dynamic_duration:
            return self.dynamic_duration[key]
        return self.duration


class CacheManager:
    """缓存管理器"""

    def __init__(self, config: BaseCacheConfig):
        if not isinstance(config, BaseCacheConfig):
            raise TypeError("config must be an instance of BaseCacheConfig")
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    def get(self, prefix: str, identifier: str, cache_key: Any = None) -> Optional[Dict]:
        """获取缓存数据

        Args:
            prefix: 缓存前缀
            identifier: 缓存标识符
            cache_key: 用于动态确定缓存时长的key
        """
        if not prefix or not identifier:
            raise ValueError("prefix and identifier cannot be empty")

        cache_path = self.config.get_cache_path(prefix, identifier)
        if not cache_path.exists():
            return None

        try:
            with cache_path.open('r', encoding='utf-8') as f:
                cache_data = json.load(f)

            timestamp = datetime.fromtimestamp(cache_data.get('timestamp', 0))
            duration = self.config.get_duration(cache_key)

            if datetime.now() - timestamp < duration:
                return cache_data.get('data')

        except json.JSONDecodeError as e:
            self.logger.error(f"缓存文件JSON解析失败: {e}")
        except Exception as e:
            self.logger.error(f"读取缓存失败: {e}")

        return None

    def set(self, prefix: str, identifier: str, data: Dict, metadata: Optional[Dict] = None) -> None:
        """设置缓存数据

        Args:
            prefix: 缓存前缀
            identifier: 缓存标识符
            data: 要缓存的数据
            metadata: 额外的元数据
        """
        if not prefix or not identifier:
            raise ValueError("prefix and identifier cannot be empty")
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        cache_path = self.config.get_cache_path(prefix, identifier)
        cache_data = {
            'timestamp': datetime.now().timestamp(),
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data': data
        }

        if metadata:
            cache_data['metadata'] = metadata

        temp_path = cache_path.with_suffix('.tmp')
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False) # type: ignore
            temp_path.replace(cache_path)
        except Exception as e:
            self.logger.error(f"写入缓存失败: {e}")
            raise
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception as e:
                    self.logger.error(f"删除临时文件失败: {e}")

    def clear(self, prefix: str, identifier: Optional[str] = None,
              age: Optional[timedelta] = None) -> None:
        """清理缓存

        Args:
            prefix: 缓存前缀
            identifier: 缓存标识符，如果指定则只清理该标识符的缓存
            age: 清理早于指定时间的缓存
        """
        if not prefix:
            raise ValueError("prefix cannot be empty")

        now = datetime.now()
        if identifier:
            cache_file = self.config.get_cache_path(prefix, identifier)
            if cache_file.exists():
                try:
                    cache_file.unlink()
                except Exception as e:
                    self.logger.error(f"删除缓存文件失败 {cache_file}: {e}")
            return

        for cache_file in self.config.root_path.glob(f"{prefix}_*.json"):
            try:
                if not cache_file.exists():
                    continue

                with cache_file.open('r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                timestamp = datetime.fromtimestamp(cache_data.get('timestamp', 0))

                if age is None or (now - timestamp) > age:
                    cache_file.unlink()

            except Exception as e:
                self.logger.error(f"清理缓存文件失败 {cache_file}: {e}")


class BatchRequestTracker:
    """批量请求进度跟踪器 - 内部使用，不暴露给外部"""

    def __init__(self, task_name: str, cache_root: Path):
        """初始化进度跟踪器"""
        self.task_name = task_name
        self.progress_file = cache_root / f"batch_{task_name}_progress.json"
        self.completed_ids = set()
        self.failed_ids = {}
        self.metadata = {
            "started_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }

        # 加载已有进度
        self._load_progress()

    def _load_progress(self):
        """从文件加载进度"""
        if not self.progress_file.exists():
            return

        try:
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.completed_ids = set(data.get('completed_ids', []))
                self.failed_ids = data.get('failed_ids', {})
                self.metadata = data.get('metadata', {})

        except Exception as e:
            print(f"加载进度文件失败: {e}")

    def save_progress(self):
        """保存进度到文件"""
        try:
            # 更新时间戳
            self.metadata["last_updated"] = datetime.now().isoformat()

            # 准备数据
            data = {
                'completed_ids': list(self.completed_ids),
                'failed_ids': self.failed_ids,
                'metadata': self.metadata,
                'stats': self.get_stats()
            }

            # 使用临时文件写入
            temp_file = self.progress_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)  # type: ignore

            # 原子替换
            temp_file.replace(self.progress_file)
        except Exception as e:
            print(f"保存进度失败: {e}")

    def mark_completed(self, item_id):
        """标记ID为已完成"""
        self.completed_ids.add(str(item_id))
        if str(item_id) in self.failed_ids:
            del self.failed_ids[str(item_id)]

    def mark_failed(self, item_id, error):
        """标记ID为失败"""
        self.failed_ids[str(item_id)] = str(error)

    def is_completed(self, item_id):
        """检查ID是否已处理完成"""
        return str(item_id) in self.completed_ids

    def get_pending_ids(self, all_ids):
        """获取待处理的ID"""
        all_ids_set = set(str(item_id) for item_id in all_ids)
        return list(all_ids_set - self.completed_ids)

    def get_stats(self):
        """获取进度统计"""
        total = len(self.completed_ids) + len(self.failed_ids)
        return {
            'total': total,
            'completed': len(self.completed_ids),
            'failed': len(self.failed_ids),
            'progress': f"{len(self.completed_ids)}/{total}" if total else "0/0",
            'completion_percentage': round(len(self.completed_ids) / total * 100, 2) if total else 0
        }

class BaseRequestConfig:
    """基础请求配置"""

    def __init__(
        self,
        cache_config: BaseCacheConfig,
        base_url: Optional[str] = None,  # 改为可选参数
        retry_config: Optional[RetryConfig] = None,
        request_timeout: int = 30
    ):
        # base_url 现在是可选的
        self.base_url = base_url
        self.cache_config = cache_config
        self.retry_config = retry_config or RetryConfig()
        self.request_timeout = request_timeout

class BaseNBAFetcher:
    """NBA数据获取基类"""

    @staticmethod
    def _get_default_headers() -> Dict[str, str]:
        """获取默认请求头"""
        return {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "no-cache",
        "connection": "keep-alive",
        "dnt": "1",
        #"host": "stats.nba.com",  #会影响cdn.nba,com
        "origin": "https://www.nba.com",
        "pragma": "no-cache",
        "referer": "https://www.nba.com/",
        "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    }

    def __init__(self, config: BaseRequestConfig):
        """初始化"""
        if not isinstance(config, BaseRequestConfig):
            raise TypeError("config must be an instance of BaseRequestConfig")

        self.config = config
        self.cache_manager = CacheManager(config.cache_config)
        self.logger = AppLogger.get_logger(__name__, app_name='nba')

        self.http_manager = HTTPRequestManager(
            headers=self._get_default_headers(),
            timeout=config.request_timeout
        )
        if config.retry_config:
            self.http_manager.retry_strategy.config = config.retry_config

    def fetch_data(self, url: Optional[str] = None, endpoint: Optional[str] = None,
                   params: Optional[Dict] = None,
                   data: Optional[Dict] = None, cache_key: Optional[str] = None,
                   cache_status_key: Any = None,
                   force_update: bool = False,
                   metadata: Optional[Dict] = None) -> Optional[Dict]:
        """获取数据

        Args:
            url: 完整的请求URL
            endpoint: API端点
            params: URL参数
            data: POST数据
            cache_key: 缓存键
            cache_status_key: 用于确定缓存时长的状态键
            force_update: 是否强制更新
            metadata: 额外的缓存元数据
        """
        if url is None and endpoint is None:
            raise ValueError("Must provide either url or endpoint")

        # 如果有缓存key且不强制更新，尝试获取缓存数据
        if cache_key and not force_update:
            cached_data = self.cache_manager.get(
                prefix=self.__class__.__name__.lower(),
                identifier=cache_key,
                cache_key=cache_status_key
            )
            if cached_data is not None:
                # 直接返回data字段内容
                return cached_data.get('data') if isinstance(cached_data,
                                                             dict) and 'data' in cached_data else cached_data

        # 获取新数据
        try:
            if endpoint is not None:
                # 构建基础URL（不包含查询参数）
                base_url = self.config.base_url
                if base_url:
                    request_url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
                else:
                    request_url = endpoint

                # 让HTTP库处理参数编码
                data = self.http_manager.make_request(
                    url=request_url,
                    params=params,
                    data=data
                )
            else:

                data = self.http_manager.make_request(
                    url=url,
                    data=data
                )

            # 如果获取成功且需要缓存，则更新缓存
            if data is not None and cache_key:
                try:
                    self.cache_manager.set(
                        prefix=self.__class__.__name__.lower(),
                        identifier=cache_key,
                        data=data,
                        metadata=metadata
                    )
                except Exception as e:
                    self.logger.error(f"更新缓存失败: {e}")

            return data

        except Exception as e:
            self.logger.error(f"请求失败: {str(e)}")
            return None

    # 新增内部方法，不影响原有接口
    def _batch_fetch_internal(self,
                              ids: List[Any],
                              fetch_func: Callable[[Any], Dict],
                              task_name: str,
                              batch_size: int = 20,
                              save_interval: int = 50) -> Dict[str, Any]:
        """
        批量获取数据的内部实现，支持断点续传

        Args:
            ids: 要获取的ID列表
            fetch_func: 获取单个ID数据的函数
            task_name: 任务名称，用于区分不同任务的进度
            batch_size: 批处理大小
            save_interval: 保存进度的间隔

        Returns:
            Dict: 获取结果，key为ID，value为获取的数据
        """
        # 创建进度跟踪器
        tracker = BatchRequestTracker(
            task_name=task_name,
            cache_root=self.config.cache_config.root_path
        )

        # 创建ID到类型的映射，以便在处理后恢复原始类型
        id_type_map = {str(id_): type(id_) for id_ in ids}

        # 获取未处理的ID (字符串格式)
        pending_ids_str = tracker.get_pending_ids(ids)
        self.logger.info(f"总共 {len(ids)} 个ID，其中 {len(pending_ids_str)} 个待处理")

        results = {}
        processed = 0

        # 批量处理
        for i in range(0, len(pending_ids_str), batch_size):
            batch_ids_str = pending_ids_str[i:i + batch_size]
            self.logger.info(
                f"处理批次 {i // batch_size + 1}/{(len(pending_ids_str) - 1) // batch_size + 1}，包含 {len(batch_ids_str)} 个ID")

            for item_id_str in batch_ids_str:
                try:
                    # 尝试将字符串ID转换回原始类型
                    original_type = id_type_map.get(item_id_str, int)  # 默认假设为int类型
                    try:
                        # 对于数字类型，转换回数字
                        if original_type in (int, float):
                            item_id = original_type(item_id_str)
                        else:
                            item_id = item_id_str  # 保持原样
                    except (ValueError, TypeError):
                        # 如果转换失败，保持为字符串
                        item_id = item_id_str

                    # 调用提供的获取函数，使用转换后的ID
                    data = fetch_func(item_id)

                    if data:
                        # 保存结果使用字符串ID作为键（与tracker兼容）
                        results[item_id_str] = data
                        tracker.mark_completed(item_id_str)
                    else:
                        tracker.mark_failed(item_id_str, "返回数据为空")
                except Exception as e:
                    self.logger.error(f"处理ID {item_id_str} 时出错: {str(e)}")
                    tracker.mark_failed(item_id_str, str(e))

                processed += 1
                # 定期保存进度
                if processed % save_interval == 0:
                    tracker.save_progress()
                    stats = tracker.get_stats()
                    self.logger.info(f"进度: {stats['completion_percentage']}% ({stats['progress']})")

            # 每批次结束后保存进度
            tracker.save_progress()

        # 最终保存
        tracker.save_progress()
        final_stats = tracker.get_stats()
        self.logger.info(
            f"批量获取完成。总计: {final_stats['total']}, 成功: {final_stats['completed']}, 失败: {final_stats['failed']}")

        return results

    def batch_fetch(self,
                    ids: List[Any],
                    fetch_func: Callable,
                    task_name: str = None,
                    batch_size: int = 20) -> Dict[str, Any]:
        """
        批量获取数据，支持断点续传 - 对外公开方法，包装内部实现

        Args:
            ids: 要获取的ID列表
            fetch_func: 获取单个ID数据的函数
            task_name: 任务名称，默认使用当前类名
            batch_size: 批处理大小

        Returns:
            Dict: 获取结果，key为ID，value为获取的数据
        """
        # 如果未提供任务名称，使用类名
        if task_name is None:
            task_name = self.__class__.__name__.lower()

        return self._batch_fetch_internal(
            ids=ids,
            fetch_func=fetch_func,
            task_name=task_name,
            batch_size=batch_size
        )