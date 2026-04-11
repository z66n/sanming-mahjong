# cli_ui.py
import os
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from tile import Tile

console = Console()

def clear_screen() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')

def _sort_tiles(hand: List[Tile], jin_name: Optional[str] = None) -> List[Tile]:
    suit_prio = {"万": 1, "条": 2, "筒": 3}
    honor_prio = {"东":1, "南":2, "西":3, "北":4, "中":5, "发":6, "白":7,
                  "梅":1, "兰":2, "竹":3, "菊":4, "春":5, "夏":6, "秋":7, "冬":8}
    def key(t: Tile):
        if jin_name and t.name == jin_name: return (0, 0, "")
        if t.category == "suited": return (suit_prio.get(t.name[-1], 9), t.value, "")
        return (4, honor_prio.get(t.name, 99), "")
    return sorted(hand, key=key)

def _get_tile_bg_style(t: Tile, jin_name: str) -> str:
    """根据牌型返回 Rich 背景色样式"""
    if t.name == jin_name: return "on grey82 dark_orange3"
    if t.category == "suited":
        if t.name.endswith("万"): return "on grey82 dark_blue"
        if t.name.endswith("条"): return "on grey82 dark_green"
        if t.name.endswith("筒"): return "on grey82 dark_red"
    return "on grey37 white bold"

def render_discard_prompt(hand: List[Tile], jin_name: Optional[str] = None, new_tile_name: Optional[str] = None) -> str:
    """横向排版出牌选项，带背景色分类与新牌标记（仅标记同名最右侧一张）"""
    s = _sort_tiles(hand, jin_name)
    
    # 🔍 预扫描：定位新牌在排序列表中的最右侧索引
    rightmost_idx = -1
    if new_tile_name:
        for idx, t in enumerate(s):
            if t.name == new_tile_name:
                rightmost_idx = idx  # 循环结束后自然指向最右侧的匹配项

    parts = []
    for i, t in enumerate(s):
        style = _get_tile_bg_style(t, jin_name or "")
        # 标记放在样式标签外，确保 ▲ 不受背景色影响，视觉更清晰
        marker = " ▲" if i == rightmost_idx else ""
        parts.append(f"{i+1:2}. [{style}]{t.name}[/]{marker}")
        
    return "  ".join(parts)

def render_hand(hand: List[Tile], jin_name: Optional[str] = None) -> Panel:
    """手牌面板（无交互，仅展示）"""
    s = _sort_tiles(hand, jin_name)
    content = "  ".join(f"[{_get_tile_bg_style(t, jin_name or '')}]{t.name}[/]" for t in s)
    return Panel(content, title=f"✋ 手牌 ({len(hand)}张)", border_style="blue", padding=(0, 1))

def render_river(discards: List[Tile]) -> Panel:
    if not discards: return Panel("等待出牌...", title="🌊 牌河", border_style="green")
    row = "  ".join(f"[on grey23]{t.name}[/]" for t in discards[-30:])
    return Panel(row, title="🌊 牌河", border_style="green")

def render_flowers(flowers: List[Tile]) -> Panel:
    if not flowers: return Panel("暂无", title=f"🌸 花牌", border_style="magenta")
    return Panel("  ".join(f"[on grey82 magenta]{t.name}[/]" for t in flowers), title=f"🌸 花牌 ({len(flowers)}张)", border_style="magenta")

def render_melds(melds: List[List[Tile]]) -> Panel:
    """渲染吃/碰/杠/暗杠区"""
    if not melds:
        return Panel("暂无副露", title=f"📢 副露", border_style="grey50")
    total_tiles = sum(len(group) for group in melds)
    rows = []
    for group in melds:
        row = "  ".join(f"[on grey23]{t.name}[/]" for t in group)
        rows.append(row)
    return Panel("  |  ".join(rows), title=f"📢 副露 ({total_tiles}张)", border_style="grey50")

def render_status(deck_rem: int, jin_name: str, current_turn_idx: int, dealer_idx: int) -> Panel:
    seat_names = ["你", "AI1", "AI2", "AI3"]
    curr_name = seat_names[current_turn_idx % 4]
    dealer_name = seat_names[dealer_idx % 4]

    info = Text(f"当前回合: {curr_name}  |  墙余: {deck_rem}  |  ")
    # 🎯 明确显示庄家身份，并高亮
    info.append(f"庄家: {dealer_name}", style="bold yellow")
    info.append(f"  |  金: {jin_name or '待定'}", style="dim")
    
    return Panel(info, title="📊 状态", border_style="yellow")

def render_reveal_hand(hand: List[Tile], jin_name: Optional[str] = None, title: str = "手牌", 
                       melds: Optional[List[List[Tile]]] = None, hide_flowers: bool = False) -> Panel:
    """渲染摊牌面板（支持副露区 + 隐藏花牌）"""
    from rule_sanming import HONOR_FLOWER_NAMES
    
    # 🚫 过滤花牌（用于AI摊牌时不显示花牌在手牌区）
    display_hand = [t for t in hand if not (hide_flowers and t.name in HONOR_FLOWER_NAMES)]
    s = _sort_tiles(display_hand, jin_name)
    
    content = "  ".join(f"[{_get_tile_bg_style(t, jin_name or '')}]{t.name}[/]" for t in s)
    
    if melds:
        for group in melds:
            if content: content += "  |  "
            content += "  ".join(f"[on grey23]{t.name}[/]" for t in group)
    
    return Panel(content, title=title, border_style="cyan", padding=(0, 1))

def render_game_log(logs: List[str], max_lines: int = 12) -> Panel:
    """渲染游戏日志面板（最新在底部，自动滚动）"""
    if not logs:
        return Panel("[dim]等待游戏开始...[/dim]", title="📜 事件日志", border_style="grey50")
    
    # 截取最新 N 条
    recent_logs = logs[-max_lines:]
    text = Text()
    
    for i, log in enumerate(recent_logs):
        # 智能着色：根据日志关键词
        if "胡牌" in log or "天胡" in log or "抢金" in log:
            style = "bold green"
        elif "杠" in log:
            style = "bold yellow"
        elif "碰" in log or "吃" in log:
            style = "cyan"
        elif "打出" in log or "过" in log:
            style = "dim"
        elif "庄家" in log or "连庄" in log:
            style = "bold magenta"
        elif "摸到" in log or "补花" in log:
            style = "blue"
        else:
            style = "white"
        
        text.append(log + "\n", style=style)
    
    return Panel(text, title="📜 事件日志", border_style="grey50", padding=(0, 1))

__all__ = ["clear_screen", "render_discard_prompt", "render_hand", "render_river", 
           "render_status", "render_flowers", "render_melds", "_sort_tiles", "render_reveal_hand", "render_game_log"]