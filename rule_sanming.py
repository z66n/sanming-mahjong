# rule_sanming.py
from typing import List, Optional, Dict, Tuple
from collections import Counter
from tile import Tile

# 📊 规则常量配置
WIN_PRIORITY = {
    "天胡": 10, "三金倒": 9, "闲家抢金": 8, "庄家抢金": 7,
    "清一色": 6, "混一色": 5, "金龙": 4, "金雀": 3, "金坎": 2, "平胡": 1, "无": 0
}

SPECIAL_BASE_SCORE = {
    "天胡": 30, "三金倒": 40, "闲家抢金": 30, "庄家抢金": 30, 
    "清一色": 240, "混一色": 120, "金龙": 120, "金雀": 60, "金坎": 60
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
        """🔍 仅分析手牌内部结构（供听牌/AI/暗杠使用，不感知副露）"""
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

        return {
            "jokers": jokers,
            "flowers": flowers,
            "normal_counts": normal_counts,
            "active_suits": active_suits
        }
    
    def _analyze_full_state(self, hand: List[Tile], melds: List[List[Tile]]) -> Dict:
        """🌍 合并手牌与副露进行全局分析（仅用于胡牌定档/清混色判定）"""
        all_tiles = hand + [t for group in (melds or []) for t in group]
        jokers = 0
        flowers = 0
        suits = {"万": 0, "条": 0, "筒": 0}
        normal_counts = Counter()

        for t in all_tiles:
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

        return {
            "jokers": jokers,
            "flowers": flowers,
            "normal_counts": normal_counts,
            "is_mixed_one": len(active_suits) == 1 and jokers > 0,
            "is_pure_one": len(active_suits) == 1 and jokers == 0,
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
        """🔍 听牌检测：枚举将牌来源，验证剩余牌+金能否全组面子"""
        stats = self._analyze_hand(hand)
        counts, jokers = stats["normal_counts"], stats["jokers"]

        # 1️⃣ 普通牌作将 (常规听牌)
        for name, cnt in counts.items():
            if cnt >= 2:
                nc = counts.copy()
                nc[name] -= 2
                if nc[name] == 0: del nc[name]
                if self._check_pinghu(nc, jokers): return True

        # 2️⃣ 金牌作将 (金雀/金将听牌)
        if jokers >= 2:
            if self._check_pinghu(counts, jokers - 2): return True

        return False

    def _is_strict_jin_wait_shape(self, n1: str, n2: str, jin_name: str) -> bool:
        """辅助：严格检测是否为单吊金坎的边/坎张形状"""
        if n1[-1] != n2[-1] or n1[-1] != jin_name[-1]: return False # 必须同花色且同金花色
        v1, v2 = int(n1[0]), int(n2[0])
        v1, v2 = sorted([v1, v2])
        
        if v2 - v1 == 2:  # 坎张：2,4 单吊 3
            return f"{v1+1}{n1[-1]}" == jin_name
        if v2 - v1 == 1:  # 连张：仅允许边张单吊
            if v1 == 1 and f"{v2+1}{n1[-1]}" == jin_name: return True  # 1,2 单吊 3
            if v2 == 9 and f"{v1-1}{n1[-1]}" == jin_name: return True  # 8,9 单吊 7
        return False  # 4,5 等3/6 属于两面听，排除
    
    def _is_single_wait_for_joker(self, hand: List[Tile], win_tile: Tile) -> bool:
        """🎯 金坎判定：严格单吊金牌 (4面子 + 边/坎张搭子 只等金)"""
        if not self.is_joker(win_tile): return False
        
        # 1. 移除胡掉的那张金
        remaining = hand.copy()
        removed = False
        for i, t in enumerate(remaining):
            if t.name == win_tile.name:
                remaining.pop(i); removed = True; break
        if not removed: return False

        # 2. 金坎要求剩余牌中无其他金牌
        stats = self._analyze_hand(remaining)
        if stats["jokers"] > 0: return False

        # 3. 尝试找出 4面子 + 2张搭子 的合法拆分
        counts = stats["normal_counts"]
        tile_names = [n for n, c in counts.items() for _ in range(c)]
        
        for i in range(len(tile_names)):
            for j in range(i + 1, len(tile_names)):
                pair = [tile_names[i], tile_names[j]]
                rest_counts = counts.copy()
                for n in pair:
                    rest_counts[n] -= 1
                    if rest_counts[n] == 0: del rest_counts[n]

                # 若剩余牌能全组成面子，且这2张构成严格单吊金
                if self._can_form_melds(rest_counts, 0):
                    if self._is_strict_jin_wait_shape(pair[0], pair[1], win_tile.name):
                        return True
        return False
    
    def _check_jinque(self, counts: Counter, jokers: int) -> bool:
        """金雀辅助：验证是否可用2张金牌作将牌成型"""
        if jokers < 2: return False
        return self._can_form_melds(counts, jokers - 2)
    
    def _check_jinlong(self, counts: Counter, jokers: int) -> bool:
        """🎯 金龙判定：3金独立预留，剩余牌必须自成胡型"""
        if jokers < 3: return False
        # 扣掉3张金，检查剩余牌能否成型（允许用剩余的金，但这3张绝不参与拼搭）
        return self._check_win_structure(counts, jokers - 3)

    # ================= 胡牌判定与优先级 =================
    def _can_form_melds(self, counts: Counter, jokers: int) -> bool:
        """严格递归：剩余牌+金能否全组成面子（顺/刻），修复顺子位置盲区"""
        if jokers < 0: return False
        if not counts: return True

        first = min(counts.keys())
        cnt = counts[first]
        v, s = int(first[0]), first[1]

        # 1️⃣ 尝试刻子 (AAA)
        for use_j in range(min(3, jokers) + 1):
            need = 3 - use_j
            if cnt >= need:
                nc = counts.copy()
                if need > 0:
                    nc[first] -= need
                    if nc.get(first, 0) == 0: nc.pop(first, None)
                if self._can_form_melds(nc, jokers - use_j): return True

        # 2️⃣ 尝试顺子 (仅数牌)
        if first[0].isdigit() and v <= 7:
            n1, n2 = f"{v+1}{s}", f"{v+2}{s}"
            c1, c2 = counts.get(n1, 0), counts.get(n2, 0)

            # 2.1 first 作为顺子第1张: first + n1 + n2 (可缺0~2张用金补)
            if jokers >= 0:
                # 全自然
                if c1 > 0 and c2 > 0:
                    nc = counts.copy(); nc[first]-=1; nc[n1]-=1; nc[n2]-=1
                    for t in (first, n1, n2):
                        if nc.get(t, 0) == 0: nc.pop(t, None)
                    if self._can_form_melds(nc, jokers): return True
                # 缺1张
                if jokers >= 1:
                    if c1 > 0: # first + n1 + 金
                        nc = counts.copy(); nc[first]-=1; nc[n1]-=1
                        for t in (first, n1):
                            if nc.get(t, 0) == 0: nc.pop(t, None)
                        if self._can_form_melds(nc, jokers-1): return True
                    if c2 > 0: # first + 金 + n2
                        nc = counts.copy(); nc[first]-=1; nc[n2]-=1
                        for t in (first, n2):
                            if nc.get(t, 0) == 0: nc.pop(t, None)
                        if self._can_form_melds(nc, jokers-1): return True
                # 缺2张
                if jokers >= 2:
                    nc = counts.copy(); nc[first]-=1
                    if nc.get(first, 0) == 0: nc.pop(first, None)
                    if self._can_form_melds(nc, jokers-2): return True

        # 3️⃣ first 作为顺子第2张: (first-1) + first + (first+1) [缺 first-1，需1金]
        if first[0].isdigit() and v >= 2 and v+1 <= 9 and jokers >= 1:
            n_prev, n_next = f"{v-1}{s}", f"{v+1}{s}"
            if counts.get(n_next, 0) > 0:
                nc = counts.copy(); nc[first]-=1; nc[n_next]-=1
                for t in (first, n_next):
                    if nc.get(t, 0) == 0: nc.pop(t, None)
                if self._can_form_melds(nc, jokers-1): return True

        # 4️⃣ first 作为顺子第3张: (first-2) + (first-1) + first [缺前两张，需2金]
        if first[0].isdigit() and v >= 3 and jokers >= 2:
            nc = counts.copy(); nc[first]-=1
            if nc.get(first, 0) == 0: nc.pop(first, None)
            if self._can_form_melds(nc, jokers-2): return True

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
    
    def check_initial_special_wins(self, hand: List[Tile], player_idx: int, dealer_idx: int, jin_tile: Tile) -> Dict:
        """🎯 严格限定：仅开金后、庄家行动前检测 天胡/三金倒/抢金"""
        if not jin_tile: return {"type": "无", "priority": 0}

        is_dealer = (player_idx == dealer_idx)
        results = []

        # 1. 天胡：仅庄家，且17张初始手牌不含金且自身已成型
        if is_dealer and self._check_win_structure(
            self._analyze_hand(hand)["normal_counts"],
            self._analyze_hand(hand)["jokers"]
        ):
            results.append("天胡")

        # 2. 三金倒：任意座位，初始手牌含 ≥3 张金
        if sum(1 for t in hand if self.is_joker(t)) >= 3:
            results.append("三金倒")

        # 3. 抢金：任意座位，初始手牌 + 翻出的金 能成型
        if is_dealer:
            # 庄家抢金：17张中任意移除1张，剩余16张听金
            for i in range(len(hand)):
                temp_16 = hand[:i] + hand[i+1:]
                # 检查 temp_16 + 金 是否成胡（等价于“听金”）
                test_stats = self._analyze_hand(temp_16 + [jin_tile])
                if self._check_win_structure(test_stats["normal_counts"], test_stats["jokers"]):
                    results.append("庄家抢金")
        else:
            # 闲家抢金：16张手牌 + 翻出的金 直接成胡
            test_stats = self._analyze_hand(hand + [jin_tile])
            if self._check_win_structure(test_stats["normal_counts"], test_stats["jokers"]):
                results.append("闲家抢金")

        if not results:
            return {"type": "无", "priority": 0}

        # 🎯 自动取最高优先级（天胡10 > 三金倒9 > 闲家抢金8 > 庄家抢金7）
        best = max(results, key=lambda x: WIN_PRIORITY[x])
        return {
            "type": best,
            "priority": WIN_PRIORITY[best],
            "special_score": SPECIAL_BASE_SCORE[best],
            "is_pinghu": False
        }

    def resolve_win(self, hand: List[Tile], win_tile: Optional[Tile], is_dealer: bool, 
                    is_self_draw: bool, num_melds: int = 0, melds: List[List[Tile]] = None) -> Dict:
        expected_len = 17 - 3 * num_melds
        if len(hand) != expected_len:
            return {"type": "无", "priority": 0, "special_score": 0, "is_pinghu": False}

        # ✅ 纳入副露检查清/混一色
        stats = self._analyze_full_state(hand, melds)
        is_valid = self._check_win_structure(stats["normal_counts"], stats["jokers"])
        if not is_valid:
            return {"type": "无", "priority": 0, "special_score": 0, "is_pinghu": False}

        results = []

        # 0. 三金倒 (手牌含 ≥3 张金)
        if sum(1 for t in hand if self.is_joker(t)) >= 3:
            results.append("三金倒")

        # 1. 金坎 (严格单吊金牌)
        if self._is_single_wait_for_joker(hand, win_tile):
            results.append("金坎")
        
        # 2. 清/混一色 (基于全局牌色)
        if stats["is_pure_one"]: results.append("清一色")
        elif stats["is_mixed_one"]: results.append("混一色")
        
        # 3. 金龙 (手牌共含3张金牌组成面子)
        if self._check_jinlong(stats["normal_counts"], stats["jokers"]):
            results.append("金龙")
        
        # 4. 金雀 (手牌共含2张金牌组成雀/将牌)
        if self._check_jinque(stats["normal_counts"], stats["jokers"]):
            results.append("金雀")
        
        # 5. 兜底平胡
        results.append("平胡")

        best = max(results, key=lambda x: WIN_PRIORITY[x])
        return {
            "type": best, "priority": WIN_PRIORITY[best],
            "special_score": SPECIAL_BASE_SCORE.get(best, 0),
            "is_pinghu": best == "平胡", "is_jinkan": best == "金坎"
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

    def check_meld_options(self, hand: List[Tile], discard: Tile, is_next: bool, 
                           num_melds: int = 0, melds: List[List[Tile]] = None) -> List[Dict]:
        """按优先级返回可执行动作，传入当前副露数"""
        opts = []
        
        # 🚫 金牌不能被吃/碰/明杠（但依然可以胡）
        if self.is_joker(discard):
            return [{"type": "过"}]
        
        test_hand = hand + [discard]
        
        # 1. 胡牌检测 (动态校验牌数)
        if len(test_hand) == 17 - 3 * num_melds:
            if self.resolve_win(test_hand, discard, False, False, num_melds, melds)["priority"] > 0:
                opts.append({"type": "胡"})
        
        # 🚫 手牌中的金牌不参与吃碰杠计数（金牌只能用于胡牌或做百搭，不能用于鸣牌）
        counts = Counter(t.name for t in hand if not self.is_joker(t))
        d_name = discard.name
        
        # 2. 明杠 / 3. 碰
        count = counts.get(d_name, 0)
        if count == 3:
            opts.append({"type": "明杠"})
            opts.append({"type": "碰"})  # 🎯 核心修复：3张时同时开放碰的选项（留1张在手）
        elif count == 2:
            opts.append({"type": "碰"})
            
        # 4. 吃 (仅数牌 + 上家)
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