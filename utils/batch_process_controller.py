# utils/batch_process_controller.py
import logging
import time
import random


class BatchProcessController:
    """批次处理控制器 - 管理API请求批次间隔和自适应策略"""

    def __init__(self, batch_interval=60, adaptive=True):
        """初始化批次处理控制器

        Args:
            batch_interval: 基础批次间隔时间(秒)
            adaptive: 是否启用自适应调整
        """
        self.base_interval = batch_interval  # 基础批次间隔(秒)
        self.last_batch_time = 0
        self.batch_count = 0
        self.adaptive = adaptive
        self.logger = logging.getLogger(__name__)

        # 基于批次数量的间隔调整
        self.batch_thresholds = {
            10: 1.5,  # 10批后增加50%
            15: 2.0,  # 15批后加倍
            17: 3.0,  # 17批后增加3倍
            20: 5.0  # 20批后增加5倍
        }

        # 长暂停阈值
        self.long_pause_thresholds = [
            {"batch": 16, "pause": 180, "message": "完成16批处理，暂停180秒让API冷却"},
            {"batch": 30, "pause": 300, "message": "完成30批处理，暂停300秒让API冷却"},
            {"batch": 50, "pause": 600, "message": "完成50批处理，暂停600秒让API冷却"}
        ]

    def wait_for_next_batch(self):
        """等待直到可以处理下一批次，支持动态调整等待时间"""
        current_time = time.time()
        elapsed = current_time - self.last_batch_time

        # 计算应用的间隔时间
        interval = self.base_interval

        # 如果启用自适应模式，根据已处理批次数动态调整间隔
        if self.adaptive:
            # 检查是否需要长暂停
            for threshold in self.long_pause_thresholds:
                if self.batch_count == threshold["batch"]:
                    pause_time = threshold["pause"]
                    self.logger.warning(threshold["message"])
                    time.sleep(pause_time)
                    break

            # 应用批次阈值调整
            for batch_num, factor in sorted(self.batch_thresholds.items(), reverse=True):
                if self.batch_count >= batch_num:
                    interval *= factor
                    break

        # 检查是否需要等待
        if elapsed < interval and self.last_batch_time > 0:
            wait_time = interval - elapsed

            # 根据间隔长度决定日志级别
            if wait_time > 60:
                self.logger.warning(f"批次{self.batch_count}后等待较长时间: {wait_time:.1f}秒")
            else:
                self.logger.info(f"批次{self.batch_count}后等待: {wait_time:.1f}秒")

            time.sleep(wait_time)

        # 更新计数和时间
        self.batch_count += 1
        self.last_batch_time = time.time()

        # 添加一些随机性，避免完全规律的请求模式
        if random.random() < 0.2:  # 20%概率
            extra_delay = random.uniform(0.5, 3.0)
            self.logger.debug(f"添加额外随机延迟: {extra_delay:.1f}秒")
            time.sleep(extra_delay)

        return interval  # 返回实际应用的间隔，便于调试