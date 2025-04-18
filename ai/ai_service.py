#ai/ai_service.py
from typing import Dict, Any, Optional, List, Union
import json
from utils.logger_handler import AppLogger
from nba.services.game_data_service import GameDataService
from ai.ai_processor import AIProcessor, AIConfig
from ai.ai_context_preparer import AIContextPreparer
from ai.ai_content_generator import WeiboContentGenerator


class AIService:
    """AI 服务对外接口

    负责协调数据准备和 AI 处理，提供统一的业务接口。
    使用 AIContextPreparer 准备数据，通过 WeiboContentGenerator 生成内容。
    """

    def __init__(self, game_data_service: GameDataService,
                 ai_processor: Optional[AIProcessor] = None,
                 ai_config: Optional[AIConfig] = None):
        """初始化 AI 服务

        Args:
            game_data_service: 游戏数据服务实例
            ai_processor: 预配置的AI处理器（如果提供）
            ai_config: AI配置（当ai_processor未提供时使用）
        """
        self.logger = AppLogger.get_logger(__name__, app_name='ai_services')
        self.game_data_service = game_data_service

        # 优先使用传入的processor，否则根据配置创建
        if ai_processor:
            self.ai_processor = ai_processor
        else:
            # 使用提供的配置或默认配置创建处理器
            config = ai_config or AIConfig()
            self.ai_processor = AIProcessor(config)

        # 初始化上下文准备器和内容生成器
        self.context_preparer = AIContextPreparer(game_data_service)
        self.content_generator = WeiboContentGenerator(self.ai_processor)

    def prepare_content_data(self, team_id: Optional[int] = None,
                             game_id: Optional[str] = None,
                             player_id: Optional[int] = None,
                             force_update: bool = False) -> Dict[str, Any]:
        """准备内容生成所需的数据

        Args:
            team_id: 球队ID
            game_id: 比赛ID
            player_id: 球员ID
            force_update: 是否强制更新数据

        Returns:
            Dict[str, Any]: 结构化的数据字典，或包含错误信息的字典
        """
        try:
            # 调用上下文准备器获取结构化数据
            data = self.context_preparer.prepare_ai_data(
                team_id=team_id,
                game_id=game_id,
                player_id=player_id,
                force_update=force_update
            )

            if "error" in data:
                self.logger.error(f"准备内容数据失败: {data['error']}")
                return data

            self.logger.info(
                f"成功准备内容数据: game_id={data.get('game_info', {}).get('basic', {}).get('game_id', 'unknown')}")
            return data

        except Exception as e:
            self.logger.error(f"准备内容数据时发生异常: {e}", exc_info=True)
            return {"error": f"准备内容数据失败: {str(e)}"}

    def generate_game_content(self, team_id: Optional[int] = None,
                              game_id: Optional[str] = None,
                              force_update: bool = False) -> Dict[str, Any]:
        """生成比赛相关内容

        Args:
            team_id: 球队ID
            game_id: 比赛ID
            force_update: 是否强制更新数据

        Returns:
            Dict[str, Any]: 包含生成内容和状态的字典
        """
        try:
            # 1. 准备数据
            data = self.prepare_content_data(
                team_id=team_id,
                game_id=game_id,
                force_update=force_update
            )
            if "error" in data:
                return {"status": "error", "message": data["error"]}

            # 2. 生成内容
            game_title = self.content_generator.generate_game_title(data)
            game_summary = self.content_generator.generate_game_summary(data)

            # 3. 返回结果
            return {
                "status": "success",
                "content": {
                    "title": game_title,
                    "summary": game_summary
                },
                "game_id": data.get("game_info", {}).get("basic", {}).get("game_id"),
                "teams": {
                    "home": data.get("game_info", {}).get("basic", {}).get("teams", {}).get("home", {}).get(
                        "full_name"),
                    "away": data.get("game_info", {}).get("basic", {}).get("teams", {}).get("away", {}).get("full_name")
                }
            }

        except Exception as e:
            self.logger.error(f"生成比赛内容时发生异常: {e}", exc_info=True)
            return {"status": "error", "message": f"生成比赛内容失败: {str(e)}"}

    def generate_player_content(self, player_id: int,
                                game_id: Optional[str] = None,
                                team_id: Optional[int] = None,
                                include_shot_chart: bool = True,
                                include_rounds: bool = False,
                                force_update: bool = False) -> Dict[str, Any]:
        """生成球员相关内容

        Args:
            player_id: 球员ID
            game_id: 比赛ID
            team_id: 球队ID（可选，用于辅助确定比赛）
            include_shot_chart: 是否包含投篮图解说
            include_rounds: 是否包含回合解说
            force_update: 是否强制更新数据

        Returns:
            Dict[str, Any]: 包含生成内容和状态的字典
        """
        try:
            # 1. 准备数据
            data = self.prepare_content_data(
                team_id=team_id,
                game_id=game_id,
                player_id=player_id,
                force_update=force_update
            )

            if "error" in data:
                return {"status": "error", "message": data["error"]}

            # 2. 生成内容
            result = {
                "status": "success",
                "content": {},
                "player_id": player_id,
                "player_name": data.get("player_info", {}).get("basic", {}).get("name", "未知球员"),
                "game_id": data.get("game_info", {}).get("basic", {}).get("game_id")
            }

            # 生成球员分析
            player_analysis = self.content_generator.generate_player_analysis(data)
            result["content"]["player_analysis"] = player_analysis

            # 生成投篮图解说（如果需要）
            if include_shot_chart and "shot_data" in data:
                shot_chart_text = self.content_generator.generate_shot_chart_text(data)
                result["content"]["shot_chart_text"] = shot_chart_text

            # 生成回合解说（如果需要）
            if include_rounds and "rounds" in data:
                rounds = data.get("rounds", [])
                if rounds:
                    # 仅选择前5个回合进行解说
                    round_ids = [round_data["action_number"] for round_data in rounds[:5]]
                    round_analyses = self.content_generator._batch_generate_round_analyses(
                        data, round_ids, result["player_name"]
                    )
                    result["content"]["round_analyses"] = round_analyses

            return result

        except Exception as e:
            self.logger.error(f"生成球员内容时发生异常: {e}", exc_info=True)
            return {"status": "error", "message": f"生成球员内容失败: {str(e)}"}

    def generate_team_content(self, team_id: int,
                              game_id: Optional[str] = None,
                              include_shot_chart: bool = True,
                              force_update: bool = False) -> Dict[str, Any]:
        """生成球队相关内容

        Args:
            team_id: 球队ID
            game_id: 比赛ID
            include_shot_chart: 是否包含投篮图解说
            force_update: 是否强制更新数据

        Returns:
            Dict[str, Any]: 包含生成内容和状态的字典
        """
        try:
            # 1. 准备数据
            data = self.prepare_content_data(
                team_id=team_id,
                game_id=game_id,
                force_update=force_update
            )

            if "error" in data:
                return {"status": "error", "message": data["error"]}

            # 确保数据中包含球队信息
            if "team_info" not in data:
                # 手动添加球队信息
                team_name = self.game_data_service.get_team_name_by_id(team_id)
                data["team_info"] = {
                    "team_id": team_id,
                    "team_name": team_name,
                    "is_home": data.get("game_info", {}).get("basic", {}).get("teams", {}).get("home", {}).get(
                        "id") == team_id
                }

            # 2. 生成内容
            result = {
                "status": "success",
                "content": {},
                "team_id": team_id,
                "team_name": self.game_data_service.get_team_name_by_id(team_id),
                "game_id": data.get("game_info", {}).get("basic", {}).get("game_id")
            }

            # 生成比赛标题和摘要
            result["content"]["title"] = self.content_generator.generate_game_title(data)
            result["content"]["summary"] = self.content_generator.generate_game_summary(data)

            # 生成球队投篮分析（如果需要）
            if include_shot_chart and "shot_data" in data:
                team_shot_analysis = self.content_generator.generate_team_shot_analysis(data)
                result["content"]["team_shot_analysis"] = team_shot_analysis

            return result

        except Exception as e:
            self.logger.error(f"生成球队内容时发生异常: {e}", exc_info=True)
            return {"status": "error", "message": f"生成球队内容失败: {str(e)}"}

    def generate_content_for_weibo(self, content_type: str, data: Dict[str, Any],
                                   **kwargs) -> Dict[str, Any]:
        """根据内容类型生成用于微博发布的内容

        Args:
            content_type: 内容类型 (game_title, game_summary, player_analysis, etc.)
            data: 预处理后的结构化数据
            **kwargs: 额外参数

        Returns:
            Dict[str, Any]: 包含生成内容和状态的字典
        """
        try:
            # 根据内容类型调用相应的生成方法
            if content_type == "game_title":
                content = self.content_generator.generate_game_title(data)
            elif content_type == "game_summary":
                content = self.content_generator.generate_game_summary(data)
            elif content_type == "player_analysis":
                content = self.content_generator.generate_player_analysis(data)
            elif content_type == "shot_chart_text":
                content = self.content_generator.generate_shot_chart_text(data)
            elif content_type == "team_shot_analysis":
                content = self.content_generator.generate_team_shot_analysis(data)
            elif content_type == "round_analysis":
                round_id = kwargs.get("round_id")
                if not round_id:
                    return {"status": "error", "message": "未提供回合ID"}
                content = self.content_generator.generate_round_analysis(data, round_id)
            elif content_type == "batch_round_analyses":
                round_ids = kwargs.get("round_ids", [])
                player_name = kwargs.get("player_name", "球员")
                if not round_ids:
                    return {"status": "error", "message": "未提供回合ID列表"}
                content = self.content_generator._batch_generate_round_analyses(data, round_ids, player_name)
            else:
                return {"status": "error", "message": f"不支持的内容类型: {content_type}"}

            return {
                "status": "success",
                "content": content,
                "content_type": content_type
            }

        except Exception as e:
            self.logger.error(f"生成内容 {content_type} 时发生异常: {e}", exc_info=True)
            return {"status": "error", "message": f"生成内容失败: {str(e)}"}

    def generate_custom_content(self, custom_prompt: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """使用自定义提示词生成内容

        Args:
            custom_prompt: 自定义提示词
            data: 预处理后的结构化数据

        Returns:
            Dict[str, Any]: 包含生成内容和状态的字典
        """
        try:
            # 将数据嵌入提示词中
            formatted_prompt = custom_prompt.format(
                data=json.dumps(data, ensure_ascii=False)
            )

            # 调用AI处理器生成内容
            content = self.ai_processor.generate(formatted_prompt)

            return {
                "status": "success",
                "content": content,
                "content_type": "custom"
            }

        except Exception as e:
            self.logger.error(f"生成自定义内容时发生异常: {e}", exc_info=True)
            return {"status": "error", "message": f"生成自定义内容失败: {str(e)}"}