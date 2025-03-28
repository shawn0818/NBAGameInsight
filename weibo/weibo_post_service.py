import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

from weibo.weibo_picture_publisher import WeiboImagePublisher
from weibo.weibo_video_publisher import WeiboVideoPublisher
from utils.logger_handler import AppLogger


class WeiboPostService:
    """微博发布服务，提供统一的发布接口"""

    def __init__(self, cookie: Optional[str] = None, content_generator=None):
        """初始化服务

        Args:
            cookie: 用户登录Cookie，如果不提供会尝试从环境变量获取
            content_generator: 内容生成器实例
        """
        self.logger = AppLogger.get_logger(__name__, app_name='weibo')
        self.content_generator = content_generator

        # 优先使用传入的cookie，否则尝试从环境变量获取
        self.cookie = cookie
        if not self.cookie:
            self.cookie = os.getenv("WB_COOKIES")
            if not self.cookie:
                self.logger.error("未设置WB_COOKIES环境变量且未提供cookie参数")
                raise ValueError("微博Cookie未提供且环境变量WB_COOKIES未设置")

        self.image_publisher = WeiboImagePublisher(self.cookie)
        self.video_publisher = WeiboVideoPublisher(self.cookie)

    # === 基础发布方法 ===

    def post_picture(self, content: str, image_paths: Union[str, List[str]],
                     ) -> Dict[str, Any]:
        """发布图片微博

        Args:
            content: 微博文本内容
            image_paths: 单个图片路径或图片路径列表

        Returns:
            Dict: 包含成功状态和消息的字典
        """
        try:
            self.logger.info(f"开始发布图片微博，图片数量: {len(image_paths) if isinstance(image_paths, list) else 1}")

            # 直接使用图片发布器的方法发布图片
            result = self.image_publisher.publish_images(image_paths, content)

            # 添加详细日志，记录完整的返回结果
            self.logger.debug(f"微博API返回结果: {result}")

            # WeiboImagePublisher中的publish_images方法已经处理了成功/失败的判断
            # 并返回了统一格式的结果，我们只需要信任这个结果
            if result and result.get("success") == True:
                self.logger.info(f"图片微博发布成功")
                return {"success": True, "message": result.get("message", "发布成功"), "data": result.get("data", {})}
            else:
                error_message = result.get("message", "未知错误")
                self.logger.error(f"图片微博发布失败: {error_message}")
                return {"success": False, "message": error_message, "data": result.get("data", {})}

        except Exception as e:
            error_message = f"发布图片微博失败: {str(e)}"
            self.logger.error(error_message, exc_info=True)
            return {"success": False, "message": error_message}

    def post_video(self, video_path: str, title: str, content: str,
                   cover_path: Optional[str] = None, is_original: bool = True,
                   album_id: Optional[str] = None, channel_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """发布视频微博

        Args:
            video_path: 视频文件路径
            title: 视频标题
            content: 微博正文内容
            cover_path: 封面图片路径 (可选)
            is_original: 是否为原创内容
            album_id: 合集ID (可选)
            channel_ids: 频道ID列表 (可选)

        Returns:
            Dict: 包含成功状态和消息的字典
        """
        try:
            self.logger.info(f"开始发布视频微博，视频路径: {video_path}")

            # 添加视频文件检查
            if not self._check_file_exists(video_path, "视频文件"):
                return {"success": False, "message": f"视频文件不存在: {video_path}"}

            # 上传封面（如果有）
            cover_pid = None
            if cover_path:
                self.logger.info(f"上传视频封面: {cover_path}")
                try:
                    if self._check_file_exists(cover_path, "封面图片"):
                        cover_info = self.image_publisher.upload_image(cover_path)
                        if cover_info:
                            cover_pid = cover_info.get('pid')
                            self.logger.info(f"封面上传成功，PID: {cover_pid}")
                except Exception as cover_error:
                    self.logger.warning(f"封面上传失败，将使用默认封面: {str(cover_error)}")

            # 使用进度回调函数
            def progress_callback(current, total, percentage):
                self.logger.info(f"视频上传进度: {current}/{total} 块 ({percentage:.2f}%)")

            # 上传并发布视频
            self.logger.info("开始上传视频...")
            upload_result = self.video_publisher.upload_video(
                file_path=video_path,
                progress_callback=progress_callback
            )

            if not upload_result or 'media_id' not in upload_result:
                error_message = "视频上传失败，未获取到media_id"
                self.logger.error(error_message)
                return {"success": False, "message": error_message}

            media_id = upload_result.get('media_id')
            self.logger.info(f"视频上传成功，media_id: {media_id}")

            # 发布视频
            self.logger.info("开始发布视频内容...")
            publish_result = self.video_publisher.publish_video(
                media_id=media_id,
                title=title,
                content=content,
                cover_pid=cover_pid,
                is_original=is_original,
                album_id=album_id,
                channel_ids=channel_ids
            )

            # 详细记录API返回
            self.logger.debug(f"发布视频API返回: {publish_result}")

            # 简化判断逻辑
            if publish_result.get('ok') == 1 or publish_result.get('code') == 100000 or "success" in str(
                    publish_result).lower():
                self.logger.info(f"视频微博发布成功!")
                return {"success": True, "message": "视频微博发布成功", "data": publish_result}
            else:
                message = publish_result.get('msg', '发布失败')
                self.logger.error(f"视频微博发布失败: {message}")
                return {"success": False, "message": message, "data": publish_result}

        except Exception as e:
            error_message = f"发布视频微博失败: {str(e)}"
            self.logger.error(error_message, exc_info=True)
            return {"success": False, "message": error_message}

    # === 内容发布方法（使用内容生成器） ===

    def post_team_video(self, video_path, game_data):
        """发布球队集锦视频到微博"""
        self.logger.info("开始发布球队集锦视频")

        if not self._check_file_exists(video_path, "球队集锦视频"):
            return {"success": False, "message": "视频文件不存在"}

        if not self.content_generator:
            self.logger.error("内容生成器未初始化，跳过发布")
            return {"success": False, "message": "内容生成器未初始化"}

        try:
            # 获取team_id
            team_id = game_data.get("team_info", {}).get("team_id")
            if not team_id:
                self.logger.error("未能从game_data中获取team_id")
                return {"success": False, "message": "未能获取team_id"}

            # 使用统一内容生成接口获取内容
            content_package = self.content_generator.generate_content(
                content_type=ContentType.TEAM_VIDEO.value,
                game_data=game_data,
                team_id=team_id
            )

            self.logger.info(
                f"生成的内容：标题: {content_package['title']}, 内容长度: {len(content_package['content'])}")

            # 发布视频
            result = self.post_video(
                video_path=str(video_path),
                title=content_package["title"],
                content=content_package["content"],
                is_original=True
            )

            if result and result.get("success"):
                self.logger.info(f"球队集锦视频发布成功: {result.get('message', '')}")
                return result
            else:
                self.logger.error(f"球队集锦视频发布失败: {result.get('message', '未知错误')}")
                return result

        except Exception as e:
            self.logger.error(f"发布球队集锦视频失败: {e}", exc_info=True)
            return {"success": False, "message": f"发布失败: {str(e)}"}

    def post_player_video(self, video_path, player_data, player_name):
        """发布球员集锦视频到微博"""
        self.logger.info(f"开始发布{player_name}球员集锦视频")

        if not self._check_file_exists(video_path, "球员集锦视频"):
            return {"success": False, "message": "视频文件不存在"}

        if not self.content_generator:
            self.logger.error("内容生成器未初始化，跳过发布")
            return {"success": False, "message": "内容生成器未初始化"}

        try:
            # 获取player_id
            player_id = player_data.get("player_info", {}).get("player_id")
            if not player_id:
                self.logger.error(f"未能获取{player_name}的player_id")
                return {"success": False, "message": f"未能获取{player_name}的player_id"}

            # 使用统一内容生成接口获取内容
            content_package = self.content_generator.generate_content(
                content_type=ContentType.PLAYER_VIDEO.value,
                game_data=player_data,
                player_id=player_id
            )

            self.logger.info(
                f"生成的内容：标题: {content_package['title']}, 内容长度: {len(content_package['content'])}")

            # 发布视频
            result = self.post_video(
                video_path=str(video_path),
                title=content_package["title"],
                content=content_package["content"],
                is_original=True
            )

            if result and result.get("success"):
                self.logger.info(f"球员集锦视频发布成功: {result.get('message', '')}")
                return result
            else:
                self.logger.error(f"球员集锦视频发布失败: {result.get('message', '未知错误')}")
                return result

        except Exception as e:
            self.logger.error(f"发布球员集锦视频失败: {e}", exc_info=True)
            return {"success": False, "message": f"发布失败: {str(e)}"}

    def post_player_chart(self, chart_path, player_data, player_name):
        """发布球员投篮图到微博"""
        self.logger.info(f"开始发布{player_name}投篮图")

        if not self._check_file_exists(chart_path, "投篮图"):
            return {"success": False, "message": "投篮图文件不存在"}

        if not self.content_generator:
            self.logger.error("内容生成器未初始化，跳过发布")
            return {"success": False, "message": "内容生成器未初始化"}

        try:
            # 获取player_id
            player_id = player_data.get("player_info", {}).get("player_id")
            if not player_id:
                self.logger.error(f"未能获取{player_name}的player_id")
                return {"success": False, "message": f"未能获取{player_name}的player_id"}

            # 使用统一内容生成接口获取内容
            content_package = self.content_generator.generate_content(
                content_type=ContentType.PLAYER_CHART.value,
                game_data=player_data,
                player_id=player_id
            )

            self.logger.info(f"生成的内容：内容长度: {len(content_package['content'])}")

            # 发布图片
            result = self.post_picture(
                content=content_package["content"],
                image_paths=str(chart_path)
            )

            if result and result.get("success"):
                self.logger.info(f"球员投篮图发布成功: {result.get('message', '')}")
                return result
            else:
                self.logger.error(f"球员投篮图发布失败: {result.get('message', '未知错误')}")
                return result

        except Exception as e:
            self.logger.error(f"发布球员投篮图失败: {e}", exc_info=True)
            return {"success": False, "message": f"发布失败: {str(e)}"}

    def post_team_chart(self, chart_path, team_data, team_name):
        """发布球队投篮图到微博"""
        self.logger.info(f"开始发布{team_name}球队投篮图")

        if not self._check_file_exists(chart_path, "球队投篮图"):
            return {"success": False, "message": "球队投篮图文件不存在"}

        if not self.content_generator:
            self.logger.error("内容生成器未初始化，跳过发布")
            return {"success": False, "message": "内容生成器未初始化"}

        try:
            # 获取team_id
            team_id = team_data.get("team_info", {}).get("team_id")
            if not team_id:
                self.logger.error(f"未能获取{team_name}的team_id")
                return {"success": False, "message": f"未能获取{team_name}的team_id"}

            # 使用统一内容生成接口获取内容
            content_package = self.content_generator.generate_content(
                content_type=ContentType.TEAM_CHART.value,
                game_data=team_data,
                team_id=team_id
            )

            self.logger.info(f"生成的内容：内容长度: {len(content_package['content'])}")

            # 发布图片
            result = self.post_picture(
                content=content_package["content"],
                image_paths=str(chart_path)
            )

            if result and result.get("success"):
                self.logger.info(f"球队投篮图发布成功: {result.get('message', '')}")
                return result
            else:
                self.logger.error(f"球队投篮图发布失败: {result.get('message', '未知错误')}")
                return result

        except Exception as e:
            self.logger.error(f"发布球队投篮图失败: {e}", exc_info=True)
            return {"success": False, "message": f"发布失败: {str(e)}"}

    def post_player_rounds(self, round_gifs, player_data, player_name, nba_service):
        """发布球员回合解说和GIF到微博"""
        self.logger.info(f"开始发布{player_name}回合解说和GIF")
        import random
        import time

        if not round_gifs:
            self.logger.error("没有回合GIF，跳过发布")
            return {"success": False, "message": "没有回合GIF"}

        if not self.content_generator:
            self.logger.error("内容生成器未初始化，跳过发布")
            return {"success": False, "message": "内容生成器未初始化"}

        try:
            # 获取球员ID
            player_id = nba_service.get_player_id_by_name(player_name)
            if not player_id:
                self.logger.error(f"未找到球员 {player_name} 的ID")
                return {"success": False, "message": f"未找到球员 {player_name} 的ID"}

            # 在调用generate_content之前，确保player_data包含完整的回合数据
            if "rounds" not in player_data or not player_data.get("rounds"):
                # 检查是否有events数据
                if "events" in player_data and "data" in player_data["events"]:
                    player_data["rounds"] = player_data["events"]["data"]
                    self.logger.info(f"从events数据中导入了{len(player_data['rounds'])}个回合")

            # 按事件ID顺序排序 - 使用整数排序
            sorted_rounds = sorted(
                round_gifs.items(),
                key=lambda x: int(x[0]) if x[0].isdigit() else float('inf')
            )

            self.logger.info(f"准备发布 {len(sorted_rounds)} 个回合GIF (按事件顺序)")

            # 获取回合ID列表
            round_ids = [int(event_id) for event_id, _ in sorted_rounds]

            # 使用统一内容生成接口批量生成回合解说
            self.logger.info(f"正在为{player_name}(ID:{player_id})的相关回合生成中文解说内容...")
            content_result = self.content_generator.generate_content(
                content_type=ContentType.ROUND_ANALYSIS.value,
                game_data=player_data,
                player_id=player_id,
                round_ids=round_ids
            )

            all_round_analyses = content_result.get("analyses", {})

            self.logger.info(f"成功生成 {len(all_round_analyses)} 个回合解说")

            # 发布回合
            success_count = 0
            failure_count = 0
            results = []

            for i, (event_id, gif_path) in enumerate(sorted_rounds):
                try:
                    # 获取解说内容
                    event_id_str = str(event_id)
                    round_content = all_round_analyses.get(event_id_str, "")

                    # 使用RoundAnalysisService的方法格式化内容
                    round_service = self.content_generator.services.get(ContentType.ROUND_ANALYSIS.value)
                    if round_service:
                        formatted_content = round_service.format_round_content(
                            analysis_text=round_content,
                            player_name=player_name,
                            round_id=int(event_id),
                            round_index=i + 1,
                            total_rounds=len(sorted_rounds)
                        )
                    else:
                        # 备用格式化方案
                        formatted_content = f"{player_name}本场表现回顾{i + 1}/{len(sorted_rounds)}\n\n{round_content}\n\n#NBA# #湖人# #勒布朗# #詹姆斯#"

                    # 检查文件是否存在
                    if not self._check_file_exists(gif_path, f"回合 #{event_id} 的GIF"):
                        failure_count += 1
                        continue

                    self.logger.info(f"发布回合 #{event_id} 解说和GIF: {gif_path.name}")

                    # 发布图片
                    result = self.post_picture(
                        content=formatted_content,
                        image_paths=str(gif_path)
                    )

                    results.append(result)

                    # 检查结果
                    if result and result.get("success"):
                        self.logger.info(f"回合 #{event_id} 发布成功")
                        success_count += 1
                    else:
                        self.logger.error(f"回合 #{event_id} 发布失败: {result.get('message', '未知错误')}")
                        failure_count += 1

                    # 随机延迟20-30秒
                    if i < len(sorted_rounds) - 1:
                        delay_time = random.randint(20, 30)
                        self.logger.info(f"等待 {delay_time} 秒后继续发布下一个回合...")
                        time.sleep(delay_time)

                except Exception as e:
                    self.logger.error(f"发布回合 #{event_id} 失败: {str(e)}", exc_info=True)
                    failure_count += 1
                    # 发生错误后增加一些额外等待
                    self.logger.info("发生错误，等待 20 秒后继续...")
                    time.sleep(20)
                    continue

            self.logger.info(
                f"回合发布完成! 成功发布 {success_count}/{len(sorted_rounds)} 个回合, 失败 {failure_count} 个")

            return {
                "success": success_count > 0,
                "message": f"成功发布 {success_count}/{len(sorted_rounds)} 个回合, 失败 {failure_count} 个",
                "data": {"success_count": success_count, "failure_count": failure_count, "results": results}
            }

        except Exception as e:
            self.logger.error(f"发布球员回合解说和GIF失败: {e}", exc_info=True)
            return {"success": False, "message": f"发布失败: {str(e)}"}

    def post_team_rating(self, team_data, team_name):
        """发布球队赛后评级到微博"""
        self.logger.info(f"开始发布{team_name}球队赛后评级")

        if not self.content_generator:
            self.logger.error("内容生成器未初始化，跳过发布")
            return {"success": False, "message": "内容生成器未初始化"}

        try:
            # 获取team_id
            team_id = team_data.get("team_info", {}).get("team_id")
            if not team_id:
                self.logger.error(f"未能获取{team_name}的team_id")
                return {"success": False, "message": f"未能获取{team_name}的team_id"}

            # 使用统一内容生成接口获取内容
            content_package = self.content_generator.generate_content(
                content_type=ContentType.TEAM_RATING.value,
                game_data=team_data,
                team_id=team_id
            )

            self.logger.info(
                f"生成的内容：标题: {content_package['title']}, 内容长度: {len(content_package['content'])}")

            # 发布纯文本内容
            result = self.post_picture(
                content=content_package["content"],
                image_paths=[]  # 空列表表示纯文本发布
            )

            if result and result.get("success"):
                self.logger.info(f"球队赛后评级发布成功: {result.get('message', '')}")
                return result
            else:
                self.logger.error(f"球队赛后评级发布失败: {result.get('message', '未知错误')}")
                return result

        except Exception as e:
            self.logger.error(f"发布球队赛后评级失败: {e}", exc_info=True)
            return {"success": False, "message": f"发布失败: {str(e)}"}

    # === 高级发布接口 ===

    def post_content(self, content_type: str, media_path: Union[str, Path, Dict[str, Path]],
                     data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """统一发布接口

        Args:
            content_type: 内容类型，如"team_video"，"player_video"等
            media_path: 媒体文件路径(视频或图片)或多个GIF路径的字典(用于round_analysis)
            data: 数据(游戏数据或球员数据)
            **kwargs: 其他参数，如player_name, team_name, nba_service等

        Returns:
            Dict: 包含成功状态和消息的字典
        """
        self.logger.info(f"开始发布 {content_type} 类型内容")

        # 检查媒体文件是否存在(对于非round_analysis和非team_rating类型)
        if content_type not in ["round_analysis", "team_rating"] and not self._check_file_exists(media_path):
            error_msg = f"媒体文件不存在: {media_path}"
            self.logger.error(error_msg)
            return {"success": False, "message": error_msg}

        # 检查round_analysis类型的输入是否有效
        if content_type == "round_analysis" and (not isinstance(media_path, dict) or not media_path):
            error_msg = "回合分析需要提供有效的GIF路径字典"
            self.logger.error(error_msg)
            return {"success": False, "message": error_msg}

        if not self.content_generator:
            error_msg = "内容生成器未初始化"
            self.logger.error(error_msg)
            return {"success": False, "message": error_msg}

        try:
            # 根据内容类型调用对应方法
            if content_type == ContentType.TEAM_VIDEO.value:
                result = self.post_team_video(media_path, data)

            elif content_type == ContentType.PLAYER_VIDEO.value:
                player_name = kwargs.get("player_name")
                if not player_name:
                    error_msg = "缺少player_name参数"
                    self.logger.error(error_msg)
                    return {"success": False, "message": error_msg}
                result = self.post_player_video(media_path, data, player_name)

            elif content_type == ContentType.PLAYER_CHART.value:
                player_name = kwargs.get("player_name")
                if not player_name:
                    error_msg = "缺少player_name参数"
                    self.logger.error(error_msg)
                    return {"success": False, "message": error_msg}
                result = self.post_player_chart(media_path, data, player_name)

            elif content_type == ContentType.TEAM_CHART.value:
                team_name = kwargs.get("team_name")
                if not team_name:
                    error_msg = "缺少team_name参数"
                    self.logger.error(error_msg)
                    return {"success": False, "message": error_msg}
                result = self.post_team_chart(media_path, data, team_name)

            elif content_type == ContentType.ROUND_ANALYSIS.value:
                player_name = kwargs.get("player_name")
                nba_service = kwargs.get("nba_service")
                if not player_name or not nba_service:
                    error_msg = "缺少player_name或nba_service参数"
                    self.logger.error(error_msg)
                    return {"success": False, "message": error_msg}
                # 对于round_analysis类型，media_path是GIF路径字典
                if not isinstance(media_path, dict):
                    error_msg = "回合GIF路径必须是字典类型"
                    self.logger.error(error_msg)
                    return {"success": False, "message": error_msg}
                result = self.post_player_rounds(media_path, data, player_name, nba_service)

            elif content_type == ContentType.TEAM_RATING.value:
                team_name = kwargs.get("team_name")
                if not team_name:
                    error_msg = "缺少team_name参数"
                    self.logger.error(error_msg)
                    return {"success": False, "message": error_msg}
                result = self.post_team_rating(data, team_name)

            else:
                error_msg = f"不支持的内容类型: {content_type}"
                self.logger.error(error_msg)
                return {"success": False, "message": error_msg}

            # 记录发布结果
            if result.get("success"):
                self.logger.info(f"{content_type} 发布成功: {result.get('message', '')}")
            else:
                self.logger.error(f"{content_type} 发布失败: {result.get('message', '未知错误')}")

            return result

        except Exception as e:
            error_msg = f"发布 {content_type} 内容时发生错误: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return {"success": False, "message": error_msg}

    def post_all_content(self, nba_service, video_paths, chart_paths, player_name=None):
        """批量发布多种类型内容

        Args:
            nba_service: NBA服务实例
            video_paths: 视频路径字典，包含'team_video'和'player_video'键
            chart_paths: 图表路径字典，包含'player_chart'等键
            player_name: 可选的球员名称

        Returns:
            bool: 发布是否成功
        """
        print("\n=== 发布所有内容到微博 ===")

        if not self.content_generator:
            self.logger.error("内容生成器未初始化，跳过发布")
            return False

        try:
            # 获取比赛和AI数据
            game_data = nba_service.data_service.get_game(nba_service.config.default_team)
            if not game_data:
                print(f"  获取比赛信息失败")
                return False

            ai_data = game_data.prepare_ai_data()
            if "error" in ai_data:
                print(f"  获取AI友好数据失败: {ai_data['error']}")
                return False

            results = []

            # 发布球队集锦视频
            if "team_video" in video_paths:
                result = self.post_content(
                    content_type="team_video",
                    media_path=video_paths["team_video"],
                    data=ai_data
                )
                results.append(result)
                print(
                    f"  {'✓' if result.get('success') else '×'} 球队集锦视频发布{'成功' if result.get('success') else '失败'}")

            # 如果指定了球员，发布球员相关内容
            if player_name:
                # 准备球员数据
                player_id = nba_service.get_player_id_by_name(player_name)
                if player_id:
                    player_data = game_data.prepare_ai_data(player_id=player_id)

                    # 发布球员集锦视频
                    if "player_video" in video_paths:
                        result = self.post_content(
                            content_type="player_video",
                            media_path=video_paths["player_video"],
                            data=player_data,
                            player_name=player_name
                        )
                        results.append(result)
                        print(
                            f"  {'✓' if result.get('success') else '×'} 球员集锦视频发布{'成功' if result.get('success') else '失败'}")

                    # 发布球员投篮图
                    if "player_chart" in chart_paths:
                        result = self.post_content(
                            content_type="player_chart",
                            media_path=chart_paths["player_chart"],
                            data=player_data,
                            player_name=player_name
                        )
                        results.append(result)
                        print(
                            f"  {'✓' if result.get('success') else '×'} 球员投篮图发布{'成功' if result.get('success') else '失败'}")
                else:
                    print(f"  × 未找到球员: {player_name}")

            # 判断总体成功状态
            success_count = sum(1 for r in results if r.get("success"))
            if results and success_count > 0:
                print(f"  ✓ 成功发布 {success_count}/{len(results)} 个内容")
                return True
            else:
                print("  × 所有内容发布失败")
                return False

        except Exception as e:
            self.logger.error(f"发布内容到微博时发生错误: {e}", exc_info=True)
            print(f"  × 发布内容到微博时发生错误: {e}")
            return False

    # === 资源管理方法 ===

    def close(self):
        """清理资源"""
        if hasattr(self, 'image_publisher'):
            del self.image_publisher
        if hasattr(self, 'video_publisher'):
            del self.video_publisher

    def __enter__(self):
        """支持使用with语句"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出with语句块时自动关闭资源"""
        self.close()

    # === 内部辅助方法 ===

    def _check_file_exists(self, file_path: Union[str, Path], file_type: str = "文件") -> bool:
        """检查文件是否存在，并记录日志

        Args:
            file_path: 文件路径
            file_type: 文件类型描述

        Returns:
            bool: 文件是否存在
        """
        if not file_path:
            self.logger.error(f"未指定{file_type}路径")
            return False

        path = Path(file_path) if isinstance(file_path, str) else file_path
        if not path.exists():
            self.logger.error(f"{file_type}不存在: {path}")
            return False

        self.logger.info(f"找到{file_type}: {path}")
        return True