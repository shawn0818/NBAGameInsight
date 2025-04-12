# database/db_service.py
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from contextlib import contextmanager
from database.db_session import DBSession
from database.sync.sync_manager import SyncManager
from utils.logger_handler import AppLogger


# 导入仓库类
from database.repositories.schedule_repository import ScheduleRepository
from database.repositories.team_repository import TeamRepository
from database.repositories.player_repository import PlayerRepository
from database.repositories.boxscore_repository import BoxscoreRepository
from database.repositories.playbyplay_repository import PlayByPlayRepository

# 导入模型类
from database.models.base_models import Team, Game
from database.models.stats_models import GameStatsSyncHistory


class DatabaseService:
    """数据库服务统一接口 - 包含增强的模糊查询

    提供数据库访问和核心同步操作的高级API。
    主要负责：
    1. 初始化数据库连接。
    2. 首次启动时自动同步核心数据。
    3. 提供增量并行同步比赛统计数据的方法。
    4. 提供新赛季核心数据更新的方法。
    5. 提供带上下文处理的模糊 ID 查询功能 (球员和球队)。
    """

    def __init__(self, env: str = "default", max_global_concurrency: int = 20):
        """初始化数据库服务

        参数:
            env: 环境配置名称，默认为"default"
            max_global_concurrency: 全局最大并发数，默认为20
        """
        # 初始化日志记录器
        self.logger = AppLogger.get_logger(__name__, app_name='sqlite')
        # 保存环境配置和并发设置
        self.env = env
        self.max_global_concurrency = max_global_concurrency
        # 初始化数据库会话管理器
        self.db_session = DBSession.get_instance()
        # 初始化同步管理器
        self.sync_manager = SyncManager(max_global_concurrency=max_global_concurrency)

        # 初始化各种数据仓库
        self.schedule_repo = ScheduleRepository()  # 赛程仓库
        self.team_repo = TeamRepository()  # 球队仓库
        self.player_repo = PlayerRepository()  # 球员仓库
        self.boxscore_repo = BoxscoreRepository()  # 数据统计仓库
        self.playbyplay_repo = PlayByPlayRepository()  # 比赛回放仓库

        # 服务初始化状态标志
        self._initialized = False

    # 新增会话管理方法
    @contextmanager
    def service_session(self, db_name='nba'):
        """提供服务层级别的会话上下文管理

        Args:
            db_name: 数据库名称，默认为'nba'

        Yields:
            SQLAlchemy会话对象
        """
        session = self.db_session.get_scoped_session(db_name)
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"服务层会话操作失败: {e}", exc_info=True)
            raise
        finally:
            self.db_session.remove_scoped_session(db_name)


    def initialize(self, create_tables: bool = True) -> bool:
        """初始化数据库连接和服务

        参数:
            create_tables: 是否创建不存在的表，默认为True

        返回:
            bool: 初始化是否成功
        """
        try:
            # 初始化数据库会话
            self.db_session.initialize(env=self.env, create_tables=create_tables)
            self.logger.info(f"数据库会话初始化成功，环境: {self.env}")

            # 检查核心数据库是否为空，执行首次数据同步
            if self._is_nba_database_empty():
                self.logger.info("检测到核心数据库为空，开始自动执行首次核心数据同步...")
                sync_result = self._perform_initial_core_sync()

                # 根据同步结果设置初始化状态
                if sync_result.get("status") == "success":
                    self.logger.info("首次核心数据同步成功")
                    self._initialized = True
                elif sync_result.get("status") == "partially_failed":
                    self.logger.warning(f"首次核心数据同步部分失败: {sync_result}")
                    # 部分失败情况下，根据具体失败内容决定是否继续
                    # 如果球队和球员同步成功，可以视为基本初始化完成
                    if (sync_result.get("details", {}).get("teams", {}).get("status") == "success" and
                            sync_result.get("details", {}).get("players", {}).get("status") == "success"):
                        self.logger.info("核心球队和球员数据同步成功，视为基本初始化完成")
                        self._initialized = True
                    else:
                        self.logger.error("核心球队或球员数据同步失败，初始化未完成")
                        self._initialized = False
                else:
                    self.logger.error(f"首次核心数据同步失败: {sync_result}")
                    self._initialized = False
            else:
                self.logger.info("核心数据库已存在数据，跳过首次自动同步")
                self._initialized = True

            return self._initialized

        except Exception as e:
            self.logger.error(f"数据库服务初始化失败: {e}", exc_info=True)
            self._initialized = False
            return False

    def _is_nba_database_empty(self) -> bool:
        """检查核心数据库(nba.db)是否为空

        返回:
            bool: 数据库是否为空
        """
        try:
            with self.db_session.session_scope('nba') as session:
                # 检查球队表是否有数据作为判断依据
                team_count = session.query(Team).count()
                return team_count == 0
        except Exception as e:
            self.logger.error(f"检查核心数据库是否为空失败: {e}", exc_info=True)
            # 出错时默认假设数据库为空，以便尝试执行初始同步
            return True

    def _perform_initial_core_sync(self) -> Dict[str, Any]:
        """执行首次核心数据同步（球队、球员、所有赛程）

        返回:
            Dict[str, Any]: 同步结果详情
        """
        start_time = datetime.now()
        self.logger.info("开始首次核心数据同步...")
        results = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "details": {}
        }
        all_success = True

        try:
            # 1. 同步球队数据 (强制更新)
            self.logger.info("同步球队信息...")
            team_result = self.sync_manager.sync_teams(force_update=True)
            results["details"]["teams"] = team_result
            if team_result.get("status") != "success":
                all_success = False
                self.logger.error(f"首次同步球队信息失败: {team_result.get('error', '未知错误')}")

            # 2. 同步球员数据 (强制更新)
            self.logger.info("同步球员信息...")
            player_result = self.sync_manager.sync_players(force_update=True)
            results["details"]["players"] = player_result
            if player_result.get("status") != "success":
                all_success = False
                self.logger.error(f"首次同步球员信息失败: {player_result.get('error', '未知错误')}")

            # 3. 同步所有赛季赛程数据 (强制更新)
            self.logger.info("同步所有赛季赛程信息...")
            schedule_result = self.sync_manager.sync_schedules(force_update=True, all_seasons=True)
            results["details"]["schedules"] = schedule_result
            if schedule_result.get("status") != "success":
                all_success = False
                self.logger.error(f"首次同步所有赛程信息失败: {schedule_result.get('error', '未知错误')}")

            # 根据同步结果设置整体状态
            if not all_success:
                results["status"] = "partially_failed"

        except Exception as e:
            self.logger.error(f"首次核心数据同步过程中发生异常: {e}", exc_info=True)
            results["status"] = "failed"
            results["error"] = str(e)

        # 记录完成时间和总耗时
        end_time = datetime.now()
        results["end_time"] = end_time.isoformat()
        results["duration"] = (end_time - start_time).total_seconds()
        self.logger.info(f"首次核心数据同步完成，状态: {results['status']}, 耗时: {results['duration']:.2f}秒")
        return results

    def sync_remaining_data_parallel(self, force_update: bool = False, max_workers: int = 10,
                                     batch_size: int = 50, reverse_order: bool = False,
                                     with_retry: bool = True, max_retries: int = 3,
                                     batch_interval: int = 60) -> Dict[str, Any]:
        """并行同步剩余未同步的比赛统计数据 (gamedb)

        参数:
            force_update: 是否强制更新已同步数据
            max_workers: 最大工作线程数
            batch_size: 每批次处理的比赛数量
            reverse_order: 是否按时间倒序处理
            with_retry: 是否启用重试机制
            max_retries: 最大重试次数
            batch_interval: 批次间隔时间(秒)

        返回:
            Dict[str, Any]: 同步结果详情
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法执行并行同步")
            return {"status": "failed", "error": "数据库服务未初始化"}

        self.logger.info(f"开始并行同步剩余未同步的比赛统计数据，最大线程数: {max_workers}, 批次大小: {batch_size}")
        return self.sync_manager.sync_remaining_game_stats_parallel(
            force_update=force_update,
            max_workers=max_workers,
            batch_size=batch_size,
            reverse_order=reverse_order,
            with_retry=with_retry,
            max_retries=max_retries,
            batch_interval=batch_interval
        )

    def sync_single_game(self, game_id: str, force_update: bool = False,
                         with_retry: bool = True) -> Dict[str, Any]:
        """同步单场比赛的统计数据，支持重试机制

        参数:
            game_id: 比赛ID
            force_update: 是否强制更新
            with_retry: 是否启用重试机制

        返回:
            Dict[str, Any]: 同步结果详情
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法同步单场比赛")
            return {"status": "failed", "error": "数据库服务未初始化"}

        self.logger.info(f"开始同步单场比赛(ID:{game_id})，强制更新: {force_update}, 使用重试机制: {with_retry}")
        return self.sync_manager.sync_game_stats(game_id, force_update, with_retry)

    def sync_new_season_core_data(self, force_update: bool = True) -> Dict[str, Any]:
        """同步新赛季的核心数据 (nba.db)

        参数:
            force_update: 是否强制更新，默认为True

        返回:
            Dict[str, Any]: 同步结果详情
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法同步新赛季核心数据")
            return {"status": "failed", "error": "数据库服务未初始化"}

        start_time = datetime.now()
        self.logger.info("开始同步新赛季核心数据...")
        results = {
            "start_time": start_time.isoformat(),
            "status": "success",
            "details": {}
        }
        all_success = True

        try:
            # 1. 同步球队信息 (强制更新)
            self.logger.info("强制更新球队信息...")
            team_result = self.sync_manager.sync_teams(force_update=force_update)
            results["details"]["teams"] = team_result
            if team_result.get("status") != "success":
                all_success = False
                self.logger.error(f"新赛季同步球队信息失败: {team_result.get('error', '未知错误')}")

            # 2. 同步球员信息 (强制更新)
            self.logger.info("强制更新球员信息...")
            player_result = self.sync_manager.sync_players(force_update=force_update)
            results["details"]["players"] = player_result
            if player_result.get("status") != "success":
                all_success = False
                self.logger.error(f"新赛季同步球员信息失败: {player_result.get('error', '未知错误')}")

            # 3. 同步当前赛季赛程 (强制更新)
            self.logger.info("同步当前赛季赛程信息...")
            schedule_result = self.sync_manager.sync_schedules(force_update=force_update, all_seasons=False)
            results["details"]["schedules"] = schedule_result
            if schedule_result.get("status") != "success":
                all_success = False
                self.logger.error(f"新赛季同步当前赛程信息失败: {schedule_result.get('error', '未知错误')}")

            # 根据同步结果设置整体状态
            if not all_success:
                results["status"] = "partially_failed"

        except Exception as e:
            self.logger.error(f"新赛季核心数据同步过程中发生异常: {e}", exc_info=True)
            results["status"] = "failed"
            results["error"] = str(e)

        # 记录完成时间和总耗时
        end_time = datetime.now()
        results["end_time"] = end_time.isoformat()
        results["duration"] = (end_time - start_time).total_seconds()
        self.logger.info(f"新赛季核心数据同步完成，状态: {results['status']}, 耗时: {results['duration']:.2f}秒")
        return results

    def sync_player_details(self, player_ids: Optional[List[int]] = None,
                            force_update: bool = False,
                            only_active: bool = True) -> Dict[str, Any]:
        """同步球员详细信息

        参数:
            player_ids: 指定球员ID列表，为None时同步所有球员
            force_update: 是否强制更新已有数据
            only_active: 是否仅同步活跃球员

        返回:
            Dict[str, Any]: 同步结果详情
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法同步球员详细信息")
            return {"status": "failed", "error": "数据库服务未初始化"}

        self.logger.info(
            f"开始同步球员详细信息，球员数量: {len(player_ids) if player_ids else '所有'}, 仅活跃球员: {only_active}")
        return self.sync_manager.sync_player_details(
            player_ids=player_ids,
            force_update=force_update,
            only_active=only_active
        )

    def get_team_id_by_name(self, team_name: str) -> Optional[int]:
        """获取球队ID (使用TeamRepository的模糊匹配)

        参数:
            team_name: 球队名称、缩写或拼音

        返回:
            Optional[int]: 球队ID，未找到时返回None
        """
        if not self._initialized or not team_name:
            return None

        try:
            team_id = self.team_repo.get_team_id_by_name(team_name)
            self.logger.debug(f"查询球队ID: {team_name} -> {team_id}")
            return team_id
        except Exception as e:
            self.logger.error(f"获取球队ID失败: {e}", exc_info=True)
            return None

    def get_player_id_by_name(self, name: str) -> Union[int, List[Dict[str, Any]], None]:
        """通过球员名称查询ID，支持球队上下文和优化决策逻辑"""
        if not self._initialized or not name:
            return None

        try:
            # 解析查询，检查是否包含球队标识符
            team_identifier, player_name_part = self.team_repo.check_team_identifier(name)

            if not player_name_part:
                self.logger.info(f"查询 '{name}' 只包含球队信息，无法查询球员。")
                return None

            input_team_id = None

            # 解析球队ID (如果提供了标识符)
            if team_identifier:
                input_team_id = self.team_repo.get_team_id_by_name(team_identifier)
                if input_team_id:
                    self.logger.info(f"检测到球队上下文: {team_identifier} (ID: {input_team_id})")
                else:
                    self.logger.warning(f"未找到球队标识符 '{team_identifier}'，将忽略球队信息搜索。")

            # 获取候选球员
            candidates_dicts = self.player_repo.get_candidates_by_name(player_name_part, input_team_id)
            if not candidates_dicts:
                self.logger.info(f"未找到与 '{player_name_part}' 匹配的球员。")
                return None

            # 对候选球员进行评分
            scored_results = self.player_repo.score_player_candidates(player_name_part, candidates_dicts)
            if not scored_results:
                self.logger.info(f"找到候选但评分均未达标: {player_name_part}")
                return None

            # 获取最高分结果
            top_result = scored_results[0]
            top_score = top_result["score"]
            top_player_dict = top_result["player"]

            # 阈值设置 - 修改的关键部分
            MIN_ACCEPTABLE_SCORE = 60  # 最低可接受分数
            TEAM_CONTEXT_THRESHOLD = 65  # 降低有球队上下文时的阈值 (从80降至65)
            HIGH_CONFIDENCE_THRESHOLD = 85  # 略微降低高置信度阈值 (从90降至85)
            MIN_SCORE_DIFFERENCE = 8  # 设置最低分差要求

            # 检查球队上下文匹配
            is_team_specified_and_matched = input_team_id is not None and top_player_dict.get(
                'team_id') == input_team_id

            # ===== 决策逻辑 =====

            # 1. 只有一个候选的情况
            if len(scored_results) == 1:
                if top_score >= MIN_ACCEPTABLE_SCORE:
                    self.logger.info(
                        f"唯一匹配: {top_player_dict.get('display_first_last', 'N/A')}, 分数={top_score:.1f}")
                    return top_player_dict.get('person_id')
                else:
                    self.logger.info(f"唯一匹配但分数 ({top_score:.1f}) 过低，建议用户确认")
                    return [{
                        "name": top_player_dict.get('display_first_last', 'N/A'),
                        "id": top_player_dict.get('person_id'),
                        "score": round(top_score)
                    }]

            # 2. 多个候选的情况
            else:
                second_result = scored_results[1]
                second_score = second_result["score"]
                score_difference = top_score - second_score

                # 球队上下文中的智能决策
                if is_team_specified_and_matched:
                    # 2.1 球队上下文中的高分匹配：降低分数差异要求
                    if top_score >= TEAM_CONTEXT_THRESHOLD:
                        # 新的分差计算 - 对分数在75以上的情况进一步放宽要求
                        if top_score >= 75:
                            required_diff = max(3, 10 - (top_score - 65) / 3)  # 更激进的递减函数
                        else:
                            required_diff = max(5, 12 - (top_score - TEAM_CONTEXT_THRESHOLD) / 2)

                        if score_difference >= required_diff:
                            self.logger.info(
                                f"球队上下文中的高置信度匹配: {top_player_dict.get('display_first_last', 'N/A')}, "
                                f"分数={top_score:.1f}, 与第二名差距={score_difference:.1f}"
                            )
                            return top_player_dict.get('person_id')

                    # 2.2 球队上下文中的超高分匹配：直接返回
                    if top_score >= HIGH_CONFIDENCE_THRESHOLD:
                        self.logger.info(
                            f"球队上下文中的超高置信度匹配: {top_player_dict.get('display_first_last', 'N/A')}, "
                            f"分数={top_score:.1f}"
                        )
                        return top_player_dict.get('person_id')

                    # 2.3 新增：球队上下文中的足够分差 - 即使分数不高但分差足够大
                    if score_difference >= MIN_SCORE_DIFFERENCE * 1.5 and top_score >= MIN_ACCEPTABLE_SCORE:
                        self.logger.info(
                            f"球队上下文中的显著分差匹配: {top_player_dict.get('display_first_last', 'N/A')}, "
                            f"分数={top_score:.1f}, 与第二名差距={score_difference:.1f}"
                        )
                        return top_player_dict.get('person_id')

                # 3. 无球队上下文的情况下，如果分差显著且分数可接受，也可以直接返回
                else:
                    if score_difference >= MIN_SCORE_DIFFERENCE * 2 and top_score >= MIN_ACCEPTABLE_SCORE + 10:
                        self.logger.info(
                            f"无球队上下文但分差显著的匹配: {top_player_dict.get('display_first_last', 'N/A')}, "
                            f"分数={top_score:.1f}, 与第二名差距={score_difference:.1f}"
                        )
                        return top_player_dict.get('person_id')

                # 4. 无球队上下文或匹配未达标准，返回候选列表
                self.logger.info(
                    f"找到多个可能匹配项 (Top: {top_player_dict.get('display_first_last', 'N/A')}, "
                    f"分数={top_score:.1f}, 与第二名差距={score_difference:.1f})，需要用户选择。"
                )

                # 在日志中列出所有候选项（新增部分）
                for idx, result in enumerate(scored_results[:5], 1):  # 最多显示前5个
                    if result["score"] > MIN_ACCEPTABLE_SCORE:
                        player_info = result["player"]
                        team_name = "无球队"
                        if player_info.get('team_id'):
                            team = self.team_repo.get_team_by_id(player_info.get('team_id'))
                            if team:
                                team_name = team.get('nickname', '未知球队')

                        self.logger.info(
                            f"候选{idx}: {player_info.get('display_first_last', 'N/A')} - "
                            f"球队: {team_name}, "
                            f"活跃: {'是' if player_info.get('is_active', False) else '否'}, "
                            f"匹配度: {round(result['score'])}分"
                        )

                # 构建候选列表
                candidates_for_prompt = []
                for result in scored_results[:5]:  # 最多返回前5个
                    if result["score"] > MIN_ACCEPTABLE_SCORE:
                        player_info_dict = result["player"]
                        if player_info_dict and player_info_dict.get('person_id') is not None:
                            candidates_for_prompt.append({
                                "name": player_info_dict.get('display_first_last', 'N/A'),
                                "id": player_info_dict.get('person_id'),
                                "score": round(result["score"])
                            })

                return candidates_for_prompt if candidates_for_prompt else None

        except Exception as e:
            self.logger.error(f"数据库服务查询球员ID失败 ('{name}'): {e}", exc_info=True)
            return None

    def get_player(self, identifier: Union[int, str]) -> Optional[Dict]:
        """
        统一的球员信息获取方法，支持ID、名称等多种查询方式

        参数:
            identifier: 球员标识符，可以是:
                        - 整数: 作为球员ID直接查询
                        - 字符串: 通过名称等查询

        返回:
            Optional[Dict]: 球员信息字典，未找到时返回None
        """
        if not self._initialized:
            return None

        try:
            if isinstance(identifier, int):
                player_info = self.player_repo.get_player_by_id(identifier)  # 返回字典或None
                self.logger.debug(
                    f"通过ID {identifier} 查询球员: {player_info['display_first_last'] if player_info else '未找到'}")
                return player_info
            elif isinstance(identifier, str):
                identifier = identifier.strip()
                player_id_result = self.get_player_id_by_name(identifier)  # 返回 int, List[Dict] 或 None
                if isinstance(player_id_result, int):
                    player_info = self.player_repo.get_player_by_id(player_id_result)  # 返回字典或None
                    self.logger.debug(
                        f"通过名称 '{identifier}' 查询到球员: {player_info['display_first_last'] if player_info else '未找到'}")
                    return player_info
                # 如果是候选列表或None，明确返回None，因为get_player期望返回单个球员信息
                self.logger.debug(f"通过名称 '{identifier}' 未找到唯一球员匹配或找到多个候选")
                return None
            return None
        except Exception as e:
            self.logger.error(f"获取球员信息失败(标识符:{identifier}): {e}")
            return None

    def get_game_id(self, team_id: int, date_str: str = "last") -> Optional[str]:
        """查找指定球队在特定日期的比赛ID

        参数:
            team_id: 球队ID
            date_str: 日期字符串，"last"表示最近一场比赛

        返回:
            Optional[str]: 比赛ID，未找到时返回None
        """
        if not self._initialized:
            return None

        try:
            if date_str.lower() == 'last':
                # 获取上一场比赛
                last_game = self.schedule_repo.get_team_last_schedule(team_id)
                if last_game:
                    game_id = last_game.get('game_id')
                    formatted_time = self.schedule_repo.format_game_time(last_game)

                    # 添加比赛双方名称和比分信息
                    home_team = last_game.get('home_team_name', '')
                    away_team = last_game.get('away_team_name', '')
                    home_score = last_game.get('home_team_score', 0)
                    away_score = last_game.get('away_team_score', 0)

                    # 根据game_status确定比赛状态
                    game_status = last_game.get('game_status', 0)
                    status_text = "已完成" if game_status == 3 else "进行中" if game_status == 2 else "未开始"

                    # 更丰富的日志信息
                    self.logger.info(
                        f"找到球队ID={team_id}最近{status_text}的比赛: ID={game_id}, 北京时间={formatted_time}, "
                        f"比赛: {away_team}({away_score}) vs {home_team}({home_score})"
                    )
                    return game_id
                else:
                    self.logger.warning(f"未找到球队ID={team_id}的最近比赛")
                    return None
            else:
                # 使用ScheduleRepository的get_game_id方法查找特定日期的比赛
                game_id = self.schedule_repo.get_game_id(team_id, date_str)
                self.logger.info(f"查找球队ID={team_id}在日期{date_str}的比赛: ID={game_id}")
                return game_id
        except Exception as e:
            self.logger.error(f"获取比赛ID失败: {e}", exc_info=True)
            return None

    def get_sync_progress(self) -> Dict[str, Any]:
        """获取比赛统计数据(gamedb)的同步进度

        返回:
            Dict[str, Any]: 同步进度详情
        """
        if not self._initialized:
            self.logger.error("数据库服务未初始化，无法获取同步进度")
            return {"error": "数据库服务未初始化"}

        try:
            # 获取所有已完成比赛总数
            total_finished_games = 0
            with self.db_session.session_scope('nba') as session:
                total_finished_games = session.query(Game).filter(
                    Game.game_status == 3  # 状态3表示已完成比赛
                ).count()

            # 获取已成功同步的boxscore比赛数
            synced_games = 0
            with self.db_session.session_scope('game') as session:
                synced_games = session.query(GameStatsSyncHistory.game_id).filter(
                    GameStatsSyncHistory.sync_type == 'boxscore',
                    GameStatsSyncHistory.status == 'success'
                ).distinct().count()

            # 计算进度百分比
            progress_percentage = 0
            if total_finished_games > 0:
                progress_percentage = (synced_games / total_finished_games) * 100

            # 构建结果字典
            result = {
                "total_games": total_finished_games,
                "synced_games": synced_games,
                "remaining_games": total_finished_games - synced_games,
                "progress_percentage": round(progress_percentage, 2),
                "timestamp": datetime.now().isoformat()
            }

            return result

        except Exception as e:
            self.logger.error(f"获取同步进度失败: {e}", exc_info=True)
            return {"error": str(e)}

    def close(self) -> None:
        """关闭数据库连接"""
        if self._initialized:
            try:
                self.db_session.close_all()
                self.logger.info("数据库连接已关闭")
                self._initialized = False
            except Exception as e:
                self.logger.error(f"关闭数据库连接失败: {e}", exc_info=True)

    # --- 委托给其他仓库的方法 (Boxscore, PlayByPlay) ---
    # 修改统计数据访问方法，使用service_session
    def get_player_stats_for_game(self, game_id: str, player_id: int) -> Optional[Dict]:
        """获取指定球员在指定比赛中的统计数据"""
        if not self._initialized:
            return None

        try:
            with self.service_session('game') as session:
                stats_list = self.boxscore_repo.get_player_stats(game_id, player_id, session)
                if stats_list:
                    # 使用模型自带的to_dict方法转换为字典
                    return stats_list[0].to_dict()
                return None
        except Exception as e:
            self.logger.error(f"获取球员比赛统计数据失败: {e}")
            return None

    def get_all_player_stats_for_game(self, game_id: str) -> List[Dict]:
        """获取指定比赛中所有球员的统计数据"""
        if not self._initialized:
            return []

        try:
            with self.service_session('game') as session:
                stats = self.boxscore_repo.get_player_stats(game_id, session=session)
                return [stat.to_dict() for stat in stats]
        except Exception as e:
            self.logger.error(f"获取比赛所有球员统计数据失败: {e}")
            return []

    def get_play_by_play_for_game(self, game_id: str) -> List[Dict]:
        """获取指定比赛的回放记录"""
        if not self._initialized:
            return []

        try:
            with self.service_session('game') as session:
                events = self.playbyplay_repo.get_play_actions(game_id, session=session)
                return [event.to_dict() for event in events]
        except Exception as e:
            self.logger.error(f"获取比赛回放记录失败: {e}")
            return []