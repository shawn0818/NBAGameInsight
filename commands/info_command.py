"""
信息查询命令 - 用于显示比赛和球员详细信息
"""
from typing import Dict, Any, Optional

from commands.base_command import NBACommand, error_handler


class InfoCommand(NBACommand):
    """比赛信息查询命令"""

    @error_handler
    def execute(self, app) -> bool:
        self._log_section("比赛基本信息")

        # 获取比赛数据 (Game Object)
        game = app.get_game_data()
        if not game:
            return False # Error message printed in get_game_data

        # 获取用于AI/显示的数据结构 (Prepared Data Dictionary)
        prepared_data = app.get_prepared_data(game_id=game.game_data.game_id)
        if not prepared_data or "error" in prepared_data:
            print(f"× 获取结构化数据失败: {prepared_data.get('error', '未知错误')}")
            return False

        # 显示比赛基本信息
        self._display_game_basic_info(prepared_data)

        # 显示首发阵容和伤病名单
        self._display_team_rosters(prepared_data)

        # 显示比赛状态和结果
        self._display_game_status_and_result(prepared_data)

        # 显示球队统计对比
        self._display_team_stats_comparison(prepared_data)

        # 如果指定了球员，显示球员统计数据
        if app.config.player:
            player_id = app.get_player_id(app.config.player)
            if player_id:
                player_prepared_data = app.get_prepared_data(game_id=game.game_data.game_id, player_id=player_id)
                if player_prepared_data and "error" not in player_prepared_data:
                     self._display_player_stats(player_prepared_data)
                else:
                     print(f"× 获取球员 {app.config.player} 的详细数据失败。")

        return True

    # --- Display methods operate on the prepared_data dict ---
    def _display_game_basic_info(self, prepared_data: Dict) -> None:
        """显示比赛基本信息"""
        game_info = prepared_data.get("game_info", {})
        if not game_info:
            print("  (无比赛基本信息)")
            return

        basic_info = game_info.get("basic", {})
        print("\n比赛信息:")
        print(f"  比赛ID: {basic_info.get('game_id', 'N/A')}")

        teams = basic_info.get("teams", {})
        home_team = teams.get('home', {})
        away_team = teams.get('away', {})
        print(f"  对阵: {home_team.get('full_name', '主队')} vs {away_team.get('full_name', '客队')}")

        date_info = basic_info.get("date", {})
        print(f"  日期 (北京): {date_info.get('beijing', 'N/A')}")
        print(f"  开赛时间 (北京): {date_info.get('time_beijing', 'N/A')}")

        arena = basic_info.get("arena", {})
        print(f"  场馆: {arena.get('full_location', 'N/A')}")

    def _display_team_rosters(self, prepared_data: Dict) -> None:
        """显示球队阵容信息"""
        game_info = prepared_data.get("game_info", {})
        basic_info = game_info.get("basic", {})
        teams = basic_info.get("teams", {})
        home_team_info = teams.get('home', {})
        away_team_info = teams.get('away', {})

        starters = prepared_data.get("starters", {})
        injuries = prepared_data.get("injuries", {})

        print("\n首发阵容:")
        for team_type, team_info in [("home", home_team_info), ("away", away_team_info)]:
            tricode = team_info.get('tricode', team_type.upper())
            print(f"  {tricode}:")
            team_starters = starters.get(team_type, [])
            if team_starters:
                for i, player in enumerate(team_starters, 1):
                    print(f"    {i}. {player.get('name', '?')} ({player.get('position', '?')}) #{player.get('jersey_num', '?')}")
            else:
                print("    (无首发信息)")

        print("\n伤病名单:")
        for team_type, team_info in [("home", home_team_info), ("away", away_team_info)]:
            tricode = team_info.get('tricode', team_type.upper())
            team_injuries = injuries.get(team_type, [])
            if team_injuries:
                print(f"  {tricode}:")
                for i, player in enumerate(team_injuries, 1):
                    reason = player.get('reason', '?')
                    desc = player.get('description', '') or player.get('detailed', '')
                    print(f"    {i}. {player.get('name', '?')} ({reason}) {desc}")
            else:
                print(f"  {tricode}: 无伤病报告")

    def _display_game_status_and_result(self, prepared_data: Dict) -> None:
        """显示比赛状态和结果"""
        game_info = prepared_data.get("game_info", {})
        status = game_info.get("status", {})
        result = game_info.get("result")

        print("\n比赛状态:")
        print(f"  状态: {status.get('state', 'N/A')}")
        if status.get('state', '').lower() != 'final':
             print(f"  节数: {status.get('period', {}).get('name', 'N/A')}")
             print(f"  剩余时间: {status.get('time_remaining', 'N/A')}")

        score = status.get("score", {})
        home_score = score.get('home', {})
        away_score = score.get('away', {})
        print(f"  比分: {home_score.get('team', '主')} {home_score.get('points', 0)} - {away_score.get('team', '客')} {away_score.get('points', 0)}")

        if result:
            print("\n比赛结果:")
            print(f"  最终比分: {result.get('final_score', 'N/A')}")
            winner = result.get('winner', {})
            loser = result.get('loser', {})
            print(f"  胜者: {winner.get('team_name', '?')} ({winner.get('score', 0)})")
            print(f"  败者: {loser.get('team_name', '?')} ({loser.get('score', 0)})")
            print(f"  分差: {result.get('score_difference', 0)}")
            attendance = result.get('attendance', {})
            print(f"  观众: {attendance.get('count', 'N/A')}")
            print(f"  时长: {result.get('duration', 'N/A')}")

    def _display_team_stats_comparison(self, prepared_data: Dict) -> None:
        """显示球队统计数据对比"""
        team_stats = prepared_data.get("team_stats", {})
        home = team_stats.get("home", {})
        away = team_stats.get("away", {})

        if not home or not away:
            print("\n(缺少球队统计数据)")
            return

        print("\n球队统计对比:")
        home_tricode = home.get("basic", {}).get("team_tricode", "主")
        away_tricode = away.get("basic", {}).get("team_tricode", "客")
        print(f"  指标        | {home_tricode.ljust(8)} | {away_tricode.ljust(8)}")
        print( "--------------|------------|-----------")

        def format_stat(home_val, away_val, is_percent=False):
            fmt = "{:.1%}" if is_percent else "{}"
            hv = fmt.format(home_val) if home_val is not None else 'N/A'
            av = fmt.format(away_val) if away_val is not None else 'N/A'
            return f"{hv.ljust(10)} | {av.ljust(10)}"

        hs, hsh, hr, ho, hd, hf, ha = [home.get(k, {}) for k in ["basic", "shooting", "rebounds", "offense", "defense", "fouls", "advanced"]]
        aws, awsh, awr, awo, awd, awf, awa = [away.get(k, {}) for k in ["basic", "shooting", "rebounds", "offense", "defense", "fouls", "advanced"]]

        print(f"  得分        | {format_stat(hs.get('score'), aws.get('score'))}")
        hfg = hsh.get('field_goals', {})
        awfg = awsh.get('field_goals', {})
        print(f"  命中率      | {format_stat(hfg.get('percentage'), awfg.get('percentage'), True)} ({hfg.get('made',0)}/{hfg.get('attempted',0)}) vs ({awfg.get('made',0)}/{awfg.get('attempted',0)})")
        h3p = hsh.get('three_pointers', {})
        aw3p = awsh.get('three_pointers', {})
        print(f"  三分命中率  | {format_stat(h3p.get('percentage'), aw3p.get('percentage'), True)} ({h3p.get('made',0)}/{h3p.get('attempted',0)}) vs ({aw3p.get('made',0)}/{aw3p.get('attempted',0)})")
        hft = hsh.get('free_throws', {})
        awft = awsh.get('free_throws', {})
        print(f"  罚球命中率  | {format_stat(hft.get('percentage'), awft.get('percentage'), True)} ({hft.get('made',0)}/{hft.get('attempted',0)}) vs ({awft.get('made',0)}/{awft.get('attempted',0)})")
        print(f"  篮板        | {format_stat(hr.get('total'), awr.get('total'))} (进攻 {hr.get('offensive', 0)} vs {awr.get('offensive', 0)})")
        print(f"  助攻        | {format_stat(ho.get('assists'), awo.get('assists'))}")
        print(f"  失误        | {format_stat(hd.get('turnovers', {}).get('total'), awd.get('turnovers', {}).get('total'))}")
        print(f"  抢断        | {format_stat(hd.get('steals'), awd.get('steals'))}")
        print(f"  盖帽        | {format_stat(hd.get('blocks'), awd.get('blocks'))}")
        print(f"  快攻得分    | {format_stat(ho.get('fast_break_points'), awo.get('fast_break_points'))}")
        print(f"  内线得分    | {format_stat(ho.get('points_in_paint'), awo.get('points_in_paint'))}")
        print(f"  替补得分    | {format_stat(ho.get('bench_points'), awo.get('bench_points'))}")

    def _display_player_stats(self, player_prepared_data: Dict) -> None:
        """显示特定球员的统计数据"""
        player_info = player_prepared_data.get("player_info")
        if not player_info:
            print("  (无球员数据)")
            return

        basic = player_info.get("basic", {})
        player_name = basic.get('name', '未知球员')
        print(f"\n{player_name} 详细数据:")

        if basic.get("played", False):
            print(f"  球队: {player_info.get('team', {}).get('team_name', 'N/A')} ({'主' if player_info.get('team', {}).get('is_home') else '客'})")
            print(f"  位置: {basic.get('position', 'N/A')} | 号码: {basic.get('jersey_num', 'N/A')} | {'首发' if basic.get('starter') else '替补'}")
            print(f"  时间: {basic.get('minutes', '0:00')}")
            print(f"  数据: {basic.get('points', 0)}分 {basic.get('rebounds', 0)}板 {basic.get('assists', 0)}助 | +/-: {basic.get('plus_minus', 0)}")

            shooting = player_info.get("shooting", {})
            fg = shooting.get("field_goals", {})
            tp = shooting.get("three_pointers", {})
            ft = shooting.get("free_throws", {})
            print(f"  投篮: {fg.get('made', 0)}/{fg.get('attempted', 0)} ({fg.get('percentage', 0):.1%}) | "
                  f"三分: {tp.get('made', 0)}/{tp.get('attempted', 0)} ({tp.get('percentage', 0):.1%}) | "
                  f"罚球: {ft.get('made', 0)}/{ft.get('attempted', 0)} ({ft.get('percentage', 0):.1%})")

            other = player_info.get("other_stats", {})
            fouls = other.get('fouls', {})
            print(f"  其他: {other.get('rebounds', {}).get('offensive', 0)}前场 {other.get('rebounds', {}).get('defensive', 0)}后场 | "
                  f"{other.get('steals', 0)}断 {other.get('blocks', 0)}帽 | {other.get('turnovers', 0)}失误 {fouls.get('personal', 0)}犯规")
        else:
            # Player did not play (likely injury)
            status = player_info.get("status", {})
            injury_info = status.get("injury", {})
            reason = injury_info.get("reason", "未上场")
            desc = injury_info.get("description", "") or injury_info.get("detailed", "")
            print(f"  {player_name} 本场未出战 ({reason}) {desc}")