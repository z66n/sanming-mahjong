# tile.py (仅替换 Deck 类及顶部映射)
import os, random
from dataclasses import dataclass
from typing import List, Optional

RENDER_UNICODE = False
LARGE_TILE_MODE = True
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SVG_DIR = os.path.join(BASE_DIR, "assets", "mahjong_svg")

UNICODE_TO_FILE = {
    "1万": "1f007", "2万": "1f008", "3万": "1f009", "4万": "1f00a",
    "5万": "1f00b", "6万": "1f00c", "7万": "1f00d", "8万": "1f00e", "9万": "1f00f",
    "1条": "1f010", "2条": "1f011", "3条": "1f012", "4条": "1f013",
    "5条": "1f014", "6条": "1f015", "7条": "1f016", "8条": "1f017", "9条": "1f018",
    "1筒": "1f019", "2筒": "1f01a", "3筒": "1f01b", "4筒": "1f01c",
    "5筒": "1f01d", "6筒": "1f01e", "7筒": "1f01f", "8筒": "1f020", "9筒": "1f021",
    # 花牌
    "梅": "1f022", "兰": "1f023", "竹": "1f024", "菊": "1f025",
    "春": "1f026", "夏": "1f027", "秋": "1f028", "冬": "1f029",
    "东": "1f000", "南": "1f001", "西": "1f002", "北": "1f003",
    "中": "1f004", "发": "1f005", "白": "1f006",
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
        
        # 📍 双端指针：严格分离“墙头发牌”与“墙尾补花/开金”
        self.deal_ptr = 0   # 墙头起点，向右移动（索引递增）
        self.tail_ptr = 0   # 墙尾起点，向左移动（索引递减）
        self.jin_tile: Optional[Tile] = None
        self._wall_ready = False

    def roll_dice(self) -> tuple[int, int]:
        """掷两颗骰子"""
        return random.randint(1, 6), random.randint(1, 6)

    def setup_wall(self, d1: int, d2: int) -> int:
        dice_sum = d1 + d2
        small_die = min(d1, d2)
        
        # 🎯 逆时针数玩家：庄=1, AI1=2, AI2=3, AI3=4 → 映射为索引 0~3
        self.wall_start_player = (dice_sum - 1) % 4
        
        # 📐 精确切点计算：跳过前面玩家整墙 + 当前玩家墙从右往左留小骰子墩数
        # 每人36张(18墩)，留 small_die*2 张在墙尾侧
        cut_idx = (self.wall_start_player + 1) * 36 - small_die * 2
        
        # ✂️ 模拟物理切墙：分割 → 反转 → 拼接
        # 反转后，索引0自然成为实际墙头第一张，索引143成为墙尾最后一张
        self._tiles = self._tiles[:cut_idx][::-1] + self._tiles[cut_idx:][::-1]
        
        self.deal_ptr = 0
        self.tail_ptr = 143
        self._wall_ready = True
        return self.wall_start_player
    
    def _build(self) -> None:
        for name, code in UNICODE_TO_FILE.items():
            # 🎯 核心修复：花牌仅生成1张，其余生成4张
            if name in "梅兰竹菊春夏秋冬":
                count = 1
                cat, val = "flower", 0
            elif name in "东南西北":
                count = 4
                cat, val = "wind", 0
            elif name in "中发白":
                count = 4
                cat, val = "dragon", 0
            else:
                count = 4
                cat, val = "suited", int(name[0])

            svg = os.path.join(SVG_DIR, f"mahjong_{code}.svg")
            self._tiles.extend([
                Tile(display=chr(int(code, 16)), name=name, category=cat, value=val, svg_path=svg)
                for _ in range(count)
            ])
            
        # 🛡️ 启动时强校验：确保严格等于144张
        if len(self._tiles) != 144:
            raise ValueError(f"🚨 牌库构建异常！当前 {len(self._tiles)} 张，期望 144 张")

    def draw(self) -> Optional[Tile]:
        """从墙头拿牌（发牌/常规摸牌）"""
        if not self._wall_ready or self.deal_ptr > self.tail_ptr: return None
        tile = self._tiles[self.deal_ptr]
        self.deal_ptr += 1
        return tile

    def draw_from_tail(self) -> Optional[Tile]:
        """从墙尾拿牌（补花/开金计数基准）"""
        if not self._wall_ready or self.tail_ptr < self.deal_ptr: return None
        tile = self._tiles[self.tail_ptr]
        self.tail_ptr -= 1
        return tile

    def reveal_jin(self, d1: int, d2: int) -> Optional[Tile]:
        """🎲 规则4：第二次掷骰开金（从墙尾逆时针数牌数翻牌）"""
        steps = d1 + d2
        # 逆时针数 steps 张 = 从 tail_ptr 向左数
        idx = self.tail_ptr - (steps - 1)
        
        if self.deal_ptr <= idx <= self.tail_ptr:
            self.jin_tile = self._tiles[idx]
            # 🛡️ 物理剔除：将目标牌与 tail_ptr 交换，tail_ptr 左移1位
            self._tiles[idx], self._tiles[self.tail_ptr] = self._tiles[self.tail_ptr], self._tiles[idx]
            self.tail_ptr -= 1
            return self.jin_tile
        return None

    @property
    def remaining(self) -> int:
        return max(0, self.tail_ptr - self.deal_ptr + 1)