# rule_sanming.py
from typing import List, Optional, Dict, Tuple
from collections import Counter
from tile import Tile

# 📊 规则常量配置
WIN_PRIORITY = {
    "天胡": 10, "三金倒": 9, "闲家抢金": 8, "庄家抢金": 7,
    "清一色": 6, "混一色": 5, "金龙": 4, "金雀": 3, "平胡": 2, "无": 0
}

SPECIAL_BASE_SCORE = {
    "天胡": 30, "抢金": 30, "三金倒": 40, "金坎": 60, "金雀": 60,
    "金龙": 120, "混一色": 120, "清一色": 240
}

HONOR_FLOWER_NAMES = {
    "梅", "兰", "竹", "菊", "春", "夏", "秋", "冬",
    "东", "西", "南", "北", "中", "发", "白"
}

class SanmingRule:
    def __init__(self) -> None:
        self.jin_tile: Optional[Tile] = None
        self.consecutive_dealer: int = 0  # 连庄数

    def set_jin(self, tile: Tile) -> None:
        self.jin_tile = tile

    def is_joker(self, tile: Tile) -> bool:
        """判断是否为金牌（百搭）"""
        if not self.jin_tile: return False
        return tile.name == self.jin_tile.name and self.jin_tile.name not in ("梅","兰","竹","菊","春","夏","秋","冬")

    # ================= 核心牌型分析 =================
    def _analyze_hand(self, hand: List[Tile]) -> Dict:
        """统计手牌结构（修复 KeyError 并优化清混色判定）"""
        jokers = 0
        flowers = 0
        suits = {"万": 0, "条": 0, "筒": 0}
        normal_counts = Counter()

        for t in hand:
            if self.is_joker(t):
                jokers += 1
            elif t.category == "suited":
                suits[t.name[-1]] += 1
                normal_counts[t.name] += 1
            elif t.name in HONOR_FLOWER_NAMES or t.category in ("wind", "dragon"):
                # 字牌与花牌不计入花色，统一累加到花分统计
                flowers += 1

        # 仅统计实际存在的数牌花色
        active_suits = [s for s in ("万", "条", "筒") if suits[s] > 0]
        has_jokers = jokers > 0

        return {
            "jokers": jokers,
            "flowers": flowers,
            "normal_counts": normal_counts,
            "is_mixed_one": len(active_suits) == 1 and has_jokers,
            "is_pure_one": len(active_suits) == 1 and not has_jokers,
            "active_suits": active_suits
        }

    def _check_pinghu(self, counts: Counter, jokers: int) -> bool:
        """递归检测：能否组成 N面子 + 1将 (适配动态手牌数)"""
        # 🎯 修正基线：无普通牌时，金数量必须为0(天然成牌) 或 ≥2(金做将)
        if not counts:
            return jokers == 0 or jokers >= 2
            
        first = min(counts.keys())
        cnt = counts[first]

        # 1. 刻子 AAA
        if cnt >= 3:
            nc = counts.copy(); nc[first] -= 3
            if nc[first] == 0: del nc[first]
            if self._check_pinghu(nc, jokers): return True

        # 2. 顺子 ABC
        if first[0].isdigit():
            v, s = int(first[0]), first[1]
            if v <= 7 and counts.get(f"{v+1}{s}", 0) > 0 and counts.get(f"{v+2}{s}", 0) > 0:
                nc = counts.copy()
                nc[first] -= 1; nc[f"{v+1}{s}"] -= 1; nc[f"{v+2}{s}"] -= 1
                for k in (first, f"{v+1}{s}", f"{v+2}{s}"):
                    if nc.get(k, 0) == 0: nc.pop(k, None)
                if self._check_pinghu(nc, jokers): return True

        # 3. 金补牌 (简化核心：AA+金 / A+2金 / 3金 / 顺子缺牌)
        if jokers > 0:
            if cnt >= 2 and self._check_pinghu({k:v for k,v in counts.items() if k!=first}, jokers-1): return True
            if cnt >= 1 and jokers >= 2 and self._check_pinghu({k:v for k,v in counts.items() if k!=first}, jokers-2): return True
            if jokers >= 3:
                if self._check_pinghu(counts, jokers-3): return True

        return False

    def _is_ready_hand(self, hand: List[Tile]) -> bool:
        """检测听牌/已成型 (17张=5面1将, 16张=4面2将 或 5面0将+1张)"""
        stats = self._analyze_hand(hand)
        if not stats["normal_counts"] and stats["jokers"] >= 2:
            return True  # 纯金将直接听
            
        # 枚举所有可能的将牌组合
        for name, cnt in list(stats["normal_counts"].items()):
            for pair_size in (2,):  # 三明通常以2张为将
                if cnt >= pair_size:
                    nc = stats["normal_counts"].copy()
                    nc[name] -= pair_size
                    if nc[name] == 0: del nc[name]
                    if self._check_pinghu(nc, stats["jokers"]): return True

        # 金做将
        if stats["jokers"] >= 2:
            if self._check_pinghu(stats["normal_counts"], stats["jokers"] - 2): return True
        return False

    def _check_jinkan_wait(self, hand: List[Tile], win_tile: Optional[Tile]) -> bool:
        """检测是否为金坎单吊 (单吊金牌)"""
        if not win_tile or not self.is_joker(win_tile): return False
        # 移除一张金，检查剩余牌是否只差一张金即可胡
        test_hand = [t for t in hand if not self.is_joker(t)] + [t for t in hand if self.is_joker(t)][:len([t for t in hand if self.is_joker(t)])-1]
        # 简单判定：手牌缺的刚好是金，且为单面听/坎张听
        stats = self._analyze_hand(test_hand)
        if stats["jokers"] == 0:
            # 检查是否缺顺子中间或边张，且只能等金
            return self._is_ready_hand(test_hand + [win_tile])
        return False

    # ================= 胡牌判定与优先级 =================
    def _can_form_melds(self, counts: Counter, jokers: int) -> bool:
        """递归检测剩余牌+金能否全部组成面子（顺子/刻子）"""
        if not counts:
            return True  # 无自然牌即视为成型（总牌数已在外层校验）
            
        first = min(counts.keys())
        cnt = counts[first]

        # 1. 自然刻子 (AAA)
        if cnt >= 3:
            nc = counts.copy(); nc[first] -= 3
            if nc[first] == 0: del nc[first]
            if self._can_form_melds(nc, jokers): return True

        # 2. 自然顺子 (ABC)
        if first[0].isdigit():
            v, s = int(first[0]), first[1]
            n1, n2 = f"{v+1}{s}", f"{v+2}{s}"
            if counts.get(n1, 0) > 0 and counts.get(n2, 0) > 0:
                nc = counts.copy()
                nc[first] -= 1; nc[n1] -= 1; nc[n2] -= 1
                for k in (first, n1, n2):
                    if nc.get(k, 0) == 0: nc.pop(k, None)
                if self._can_form_melds(nc, jokers): return True

        # 3. 金牌补牌逻辑
        if jokers > 0:
            # 3a. 金补刻子 (AA+金 / A+2金 / 3金)
            for use_j in (1, 2, 3):
                if jokers >= use_j and cnt >= (3 - use_j):
                    nc = counts.copy()
                    if 3 - use_j > 0:
                        nc[first] -= (3 - use_j)
                        if nc.get(first, 0) == 0: nc.pop(first, None)
                    if self._can_form_melds(nc, jokers - use_j): return True

            # 3b. 金补顺子 (仅数牌，修复原版缺失的 A_金_C 和 A_B_金)
            if first[0].isdigit():
                v, s = int(first[0]), first[1]
                # 情况1: A + 金 + C (缺中间)
                if v <= 7 and counts.get(f"{v+2}{s}", 0) > 0:
                    nc = counts.copy(); nc[first] -= 1; nc[f"{v+2}{s}"] -= 1
                    for k in (first, f"{v+2}{s}"):
                        if nc.get(k, 0) == 0: nc.pop(k, None)
                    if self._can_form_melds(nc, jokers - 1): return True
                # 情况2: A + B + 金 (缺后张)
                if v <= 7 and counts.get(f"{v+1}{s}", 0) > 0:
                    nc = counts.copy(); nc[first] -= 1; nc[f"{v+1}{s}"] -= 1
                    for k in (first, f"{v+1}{s}"):
                        if nc.get(k, 0) == 0: nc.pop(k, None)
                    if self._can_form_melds(nc, jokers - 1): return True

        return False

    def _check_win_structure(self, counts: Counter, jokers: int) -> bool:
        """完整胡牌结构校验：N面子 + 1将"""
        # 1. 尝试自然牌做将
        for name, cnt in list(counts.items()):
            if cnt >= 2:
                nc = counts.copy()
                nc[name] -= 2
                if nc[name] == 0: del nc[name]
                if self._can_form_melds(nc, jokers): return True
        # 2. 尝试金牌做将 (需≥2张)
        if jokers >= 2:
            if self._can_form_melds(counts, jokers - 2): return True
        return False

    def resolve_win(self, hand: List[Tile], win_tile: Optional[Tile], is_dealer: bool, is_self_draw: bool, num_melds: int = 0, can_qiang_jin: bool = False) -> Dict:
        expected_len = 17 - 3 * num_melds
        if len(hand) != expected_len:
            return {"type": "无", "priority": 0, "special_score": 0, "is_pinghu": False}

        stats = self._analyze_hand(hand)
        is_valid = self._check_win_structure(stats["normal_counts"], stats["jokers"])

        results = []
        if is_dealer and num_melds == 0 and is_valid: results.append("天胡")
        if stats["jokers"] >= 3: results.append("三金倒")
        
        # 🔒 严格门控：仅开局阶段传入 can_qiang_jin=True 时才允许判定抢金
        if can_qiang_jin and win_tile and self.is_joker(win_tile) and is_valid:
            results.append("闲家抢金" if not is_dealer else "庄家抢金")
            
        if is_valid:
            if stats["is_pure_one"]: results.append("清一色")
            elif stats["is_mixed_one"]: results.append("混一色")
            else: results.append("平胡")

        if not results:
            return {"type": "无", "priority": 0, "special_score": 0, "is_pinghu": False}

        best = max(results, key=lambda x: WIN_PRIORITY[x])
        return {
            "type": best,
            "priority": WIN_PRIORITY[best],
            "special_score": SPECIAL_BASE_SCORE.get(best, 0),
            "is_pinghu": best in ("平胡", "抢金", "三金倒")
        }

    # ================= 计分公式 =================
    def calculate_score(self, hand: List[Tile], win_info: Dict, 
                        base: int = 5, flower_pts: int = 0, 
                        kong_pts: int = 0, dealer_bonus: int = 0,
                        is_self_draw: bool = False) -> int:
        stats = self._analyze_hand(hand)
        gold_pts = stats["jokers"] * 1  # 每张金1分
        
        # 花牌统计 (规则：花+字牌=1分/张)
        total_flower_pts = stats["flowers"] + flower_pts
        
        # 连庄分 (每庄+1)
        total_dealer_bonus = dealer_bonus + (self.consecutive_dealer if win_info["type"] != "天胡" else 0)

        multiplier = 2 if is_self_draw else 1
        
        # 公式: (底分+金分+花分+连庄分+杠分) × 倍率 + 特殊最高分
        raw_score = (base + gold_pts + total_flower_pts + total_dealer_bonus + kong_pts) * multiplier
        final_score = raw_score + win_info["special_score"]
        
        return final_score
    
    # ================= 鸣牌拦截逻辑 =================
    def check_an_gang(self, hand: List[Tile]) -> List[str]:
        """检测可暗杠的牌名（手牌≥4张）"""
        counts = Counter(t.name for t in hand)
        return [name for name, cnt in counts.items() if cnt >= 4]

    def check_meld_options(self, hand: List[Tile], discard: Tile, is_next: bool, num_melds: int = 0) -> List[Dict]:
        """按优先级返回可执行动作，传入当前副露数"""
        opts = []
        test_hand = hand + [discard]
        
        # 1. 胡 (动态校验牌数)
        if len(test_hand) == 17 - 3 * num_melds:
            if self.resolve_win(test_hand, discard, False, False, num_melds)["priority"] > 0:
                opts.append({"type": "胡"})
                
        counts = Counter(t.name for t in hand)
        d_name = discard.name
        
        # 2. 明杠 / 3. 碰
        if counts.get(d_name, 0) == 3: opts.append({"type": "明杠"})
        elif counts.get(d_name, 0) == 2: opts.append({"type": "碰"})
            
        # 4. 吃
        if is_next and discard.category == "suited":
            v, s = discard.value, discard.name[-1]
            combos = []
            for c1, c2 in [(f"{v-2}{s}", f"{v-1}{s}"), (f"{v-1}{s}", f"{v+1}{s}"), (f"{v+1}{s}", f"{v+2}{s}")]:
                if counts.get(c1, 0) > 0 and counts.get(c2, 0) > 0:
                    combos.append([c1, c2])
            if combos: opts.append({"type": "吃", "combos": combos})
                
        return opts if opts else [{"type": "过"}]

    def execute_meld(self, hand: List[Tile], action: str, discard: Tile, combo_idx: int = -1) -> Tuple[bool, List[Tile]]:
        """执行鸣牌。返回 (成功与否, 组成副露的Tile列表)"""
        if action == "过": return False, []
        if action == "胡":
            hand.append(discard)
            return True, []

        group = [discard]  # 副露组先放入打出的牌

        if action in ("明杠", "碰"):
            need = 3 if action == "明杠" else 2
            removed = 0
            for t in list(hand):
                if t.name == discard.name and removed < need:
                    hand.remove(t)
                    group.append(t)
                    removed += 1
            return removed == need, group

        if action == "吃":
            opts = self.check_meld_options(hand, discard, True)
            chi_opt = next((o for o in opts if o["type"] == "吃"), None)
            if not chi_opt or combo_idx < 0 or combo_idx >= len(chi_opt["combos"]):
                return False, []
            targets = chi_opt["combos"][combo_idx]  # e.g. ["5万", "6万"]
            removed = 0
            for tgt in targets:
                for t in list(hand):
                    if t.name == tgt:
                        hand.remove(t)
                        group.append(t)
                        removed += 1
                        break
            return removed == 2, group
        return False, []