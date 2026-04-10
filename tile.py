# tile.py (仅替换 Deck 类及顶部映射)
import os, random
from dataclasses import dataclass
from typing import List, Optional

RENDER_UNICODE = False
LARGE_TILE_MODE = True
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SVG_DIR = os.path.join(BASE_DIR, "assets", "mahjong_svg")

# 🌸 新增 8 张花牌映射 (按你的 SVG 命名规则补齐)
UNICODE_TO_FILE = {
    "东": "1f000", "南": "1f001", "西": "1f002", "北": "1f003",
    "中": "1f004", "发": "1f005", "白": "1f006",
    "1万": "1f007", "2万": "1f008", "3万": "1f009", "4万": "1f00a",
    "5万": "1f00b", "6万": "1f00c", "7万": "1f00d", "8万": "1f00e", "9万": "1f00f",
    "1条": "1f010", "2条": "1f011", "3条": "1f012", "4条": "1f013",
    "5条": "1f014", "6条": "1f015", "7条": "1f016", "8条": "1f017", "9条": "1f018",
    "1筒": "1f019", "2筒": "1f01a", "3筒": "1f01b", "4筒": "1f01c",
    "5筒": "1f01d", "6筒": "1f01e", "7筒": "1f01f", "8筒": "1f020", "9筒": "1f021",
    # 花牌 (请根据实际 SVG 文件名调整后缀)
    "梅": "1f022", "兰": "1f023", "竹": "1f024", "菊": "1f025",
    "春": "1f026", "夏": "1f027", "秋": "1f028", "冬": "1f029"
}

@dataclass(frozen=True)
class Tile:
    display: str
    name: str
    category: str  # wind | dragon | suited | flower
    value: int
    svg_path: str = ""
    def __str__(self) -> str:
        return self.display if RENDER_UNICODE else f"[{self.name}]"

class Deck:
    def __init__(self) -> None:
        self._tiles: List[Tile] = []
        self._build()
        random.shuffle(self._tiles)
        
        # 📍 电子麻将标准双端指针：永不冲突，永不越界
        self.live_ptr = len(self._tiles) - 1  # 活墙：正常摸牌/出牌（从尾部倒序）
        self.dead_ptr = 0                     # 死墙：补花/开金（从头部正序）
        self.jin_tile: Optional[Tile] = None

    def roll_dice(self) -> tuple[int, int]:
        """掷两颗骰子"""
        return random.randint(1, 6), random.randint(1, 6)

    def setup_wall(self, d1: int, d2: int) -> int:
        """记录切墙骰子结果（双指针模型下仅用于逻辑标记与后续UI扩展）"""
        self.wall_cut_sum = d1 + d2
        return self.wall_cut_sum

    def _build(self) -> None:
        for name, code in UNICODE_TO_FILE.items():
            if name in "东南西北":
                cat, val = "wind", 0
            elif name in "中发白":
                cat, val = "dragon", 0
            elif name in "梅兰竹菊春夏秋冬":
                cat, val = "flower", 0  # ✅ 修复：明确指定类别与数值
            else:
                cat, val = "suited", int(name[0])

            svg = os.path.join(SVG_DIR, f"mahjong_{code}.svg")
            self._tiles.extend([
                Tile(display=chr(int(code, 16)), name=name, category=cat, value=val, svg_path=svg)
                for _ in range(4)
            ])

    def deal_hands(self, num_players: int = 4) -> List[List[Tile]]:
        counts = [17] + [16] * (num_players - 1)
        hands = [[] for _ in range(num_players)]
        for i, c in enumerate(counts):
            for _ in range(c):
                if self.live_ptr >= self.dead_ptr:
                    hands[i].append(self._tiles.pop())
                    self.live_ptr -= 1
        return hands

    def draw(self) -> Optional[Tile]:
        if self.live_ptr < self.dead_ptr: return None
        tile = self._tiles[self.live_ptr]
        self.live_ptr -= 1
        return tile

    def draw_from_dead(self) -> Optional[Tile]:
        if self.dead_ptr > self.live_ptr: return None
        tile = self._tiles[self.dead_ptr]
        self.dead_ptr += 1
        return tile

    def reveal_jin(self, d1: int, d2: int) -> Optional[Tile]:
        # 从死墙侧按骰子和偏移开金，确保 100% 有牌
        steps = (d1 + d2) % 10 + 1
        idx = self.dead_ptr + steps
        if idx <= self.live_ptr:
            self.jin_tile = self._tiles[idx]
            return self.jin_tile
        # 兜底：死墙不足时从活墙尾部取
        if self.live_ptr >= self.dead_ptr:
            self.jin_tile = self._tiles[self.live_ptr]
            self.live_ptr -= 1
            return self.jin_tile
        return None

    @property
    def remaining(self) -> int:
        return max(0, self.live_ptr - self.dead_ptr + 1)