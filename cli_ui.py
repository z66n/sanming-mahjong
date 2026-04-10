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
    return Panel(content, title="🃏 手牌", border_style="blue", padding=(0, 1))

def render_river(discards: List[Tile]) -> Panel:
    if not discards: return Panel("等待出牌...", title="🌊 牌河", border_style="green")
    row = "  ".join(f"[on grey23]{t.name}[/]" for t in discards[-30:])
    return Panel(row, title="🌊 牌河", border_style="green")

def render_flowers(flowers: List[Tile]) -> Panel:
    if not flowers: return Panel("暂无", title="🌸 花牌", border_style="magenta")
    return Panel("  ".join(f"[on grey82 magenta]{t.name}[/]" for t in flowers), title="🌸 补花区", border_style="magenta")

def render_melds(melds: List[List[Tile]], title: str = "🀂 副露区") -> Panel:
    """渲染吃/碰/杠/暗杠区"""
    if not melds:
        return Panel("暂无副露", title=title, border_style="grey50")
    rows = []
    for group in melds:
        row = "  ".join(f"[on grey23]{t.name}[/]" for t in group)
        rows.append(row)
    return Panel("  |  ".join(rows), title=title, border_style="grey50")

def render_status(deck_rem: int, jin_name: str, turn: int, dealer: bool) -> Panel:
    info = Text(f"回合: {turn}  |  墙余: {deck_rem}  |  ")
    info.append("庄家" if dealer else "闲家", style="bold yellow" if dealer else "dim")
    info.append(f"  |  金: {jin_name or '待定'}")
    return Panel(info, title="📊 状态", border_style="yellow")

__all__ = ["clear_screen", "render_discard_prompt", "render_hand", "render_river", 
           "render_status", "render_flowers", "render_melds", "_sort_tiles"]