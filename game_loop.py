# game_loop.py
import os, time, random
from typing import List, Optional, Dict
from collections import Counter
from rich.console import Console
from tile import Deck, Tile
from rule_sanming import SanmingRule, HONOR_FLOWER_NAMES
from cli_ui import clear_screen, render_hand, render_river, render_status, render_flowers, render_melds, render_discard_prompt, _sort_tiles

console = Console()

class SanmingGame:
    def __init__(self):
        self.deck = None
        self.rule = SanmingRule()
        self.player_hand: List[Tile] = []
        self.ai_hands: List[List[Tile]] = [[], [], []]
        self.player_flowers: List[Tile] = []
        self.ai_flowers: List[List[Tile]] = [[], [], []]
        self.player_melds: List[List[Tile]] = []
        self.ai_melds: List[List[List[Tile]]] = [[], [], []]
        self.discards: List[Tile] = []
        self.is_dealer: bool = True
        self.consecutive_dealer: int = 0
        self.current_turn: int = 0
        self.game_running: bool = False
        self.last_drawn: Optional[str] = None  # ✅ 确保初始化
        self.skip_turn_increment: bool = False
        self.post_meld_state: Optional[str] = None
        self.is_meld_active: bool = False

    def start_game(self):
        console.print("[bold cyan]🀄 福州三明十六张麻将 v1.3 (鸣牌版)[/bold cyan]")
        self.game_running = True
        while self.game_running:
            try: self._run_round()
            except KeyboardInterrupt:
                console.print("\n⏹️ 已终止。"); break
            time.sleep(2)

    def _run_round(self):
        self._init_round()
        self.deck.setup_wall(*self.deck.roll_dice())
        self._phase_deal()
        self._phase_initial_flowers()

        # 🔑 金牌非花校验：翻到花直接入庄家花区并重翻
        while True:
            d1, d2 = self.deck.roll_dice()
            jin = self.deck.reveal_jin(d1, d2)
            if not jin: break
            if jin.name in HONOR_FLOWER_NAMES:
                self.player_flowers.append(jin)
                console.print(f"🌸 翻出花牌 {jin.name} → 入庄家补花区，重新翻金...")
                continue
            self.rule.set_jin(jin)
            console.print(f"🎲 开金: {d1}+{d2}={d1+d2} | 金牌: [bold yellow]{jin.name}[/]")
            break
        time.sleep(1.5)

        if self._check_special_initial_wins(): return
        self._main_play_loop()
        self._phase_settlement()

    def _init_round(self):
        self.deck = Deck()
        self.player_hand = []
        self.ai_hands = [[], [], []]
        self.player_flowers = []
        self.ai_flowers = [[], [], []]
        self.player_melds = []
        self.ai_melds = [[], [], []]
        self.post_meld_state = None
        self.is_meld_active = False
        self.discards = []
        self.current_turn = 0
        self.last_drawn = None
        console.print("🔄 新一局开始...")

    def _phase_deal(self):
        # 确定庄家索引：0=玩家，1=AI1（固定座位简化）
        dealer_idx = 0 if self.is_dealer else 1
        self.current_turn = dealer_idx

        # 庄家17张，闲家16张
        hands = [[], [], [], []]
        for i in range(4):
            count = 17 if i == dealer_idx else 16
            for _ in range(count):
                t = self.deck.draw()
                if t: hands[i].append(t)

        self.player_hand = hands[0]
        self.ai_hands = hands[1:]

    def _phase_initial_flowers(self):
        console.print("🌸 开局集中补花...")
        changed = True
        while changed:
            changed = False
            for p in range(4):
                hand = self.player_hand if p==0 else self.ai_hands[p-1]
                flw = self.player_flowers if p==0 else self.ai_flowers[p-1]
                for t in list(hand):
                    if t.name in HONOR_FLOWER_NAMES:
                        hand.remove(t); flw.append(t)
                        new_t = self.deck.draw_from_dead()
                        if new_t: hand.append(new_t); changed = True
            if changed: time.sleep(0.2)

    def _check_special_initial_wins(self) -> bool:
        jin = self.rule.jin_tile
        hands = [self.player_hand] + self.ai_hands

        # 1. 🔑 开局专属：抢金判定（仅此时 can_qiang_jin=True）
        if jin:
            for i, h in enumerate(hands):
                # 模拟拿进翻出的金牌是否胡牌
                res = self.rule.resolve_win(h + [jin], jin, i == 0, False, num_melds=0, can_qiang_jin=True)
                if res["type"] in ("庄家抢金", "闲家抢金"):
                    h.append(jin)  # 金牌实际加入手牌
                    self._declare_win(i, res, is_zimo=False)
                    return True

        # 2. 三金倒检测
        for i, h in enumerate(hands):
            if sum(1 for t in h if self.rule.is_joker(t)) >= 3:
                self._declare_win(i, {"type":"三金倒","priority":9,"special_score":40,"is_pinghu":False}, False)
                return True

        # 3. 天胡检测 (庄家)
        if self.is_dealer:
            res = self.rule.resolve_win(self.player_hand, None, True, False, num_melds=0)
            if res["type"] == "天胡":
                self._declare_win(0, res, False)
                return True

        return False

    def _main_play_loop(self):
        is_first_action = True  # 🚦 标记本局是否还未有人执行过出牌
        while self.deck.remaining >= 20 and self.game_running:
            p_idx = self.current_turn
            hand = self.player_hand if p_idx == 0 else self.ai_hands[p_idx - 1]

            # 🃏 摸牌阶段逻辑
            should_draw = True
            if is_first_action:
                # 首手判定：庄家不摸牌直接打，闲家需先摸牌至17张
                is_dealer_turn = (self.is_dealer and p_idx == 0) or (not self.is_dealer and p_idx == 1)
                if is_dealer_turn:
                    should_draw = False
                is_first_action = False  # 第一人行动后，解除首手限制

            if should_draw:
                if self.post_meld_state == "chi_pong":
                    pass  # 吃/碰后跳过摸牌
                elif self.post_meld_state == "draw_kong":
                    self._draw_kong_tile(p_idx)
                    self.post_meld_state = None
                else:
                    self._draw_and_handle_flowers(p_idx)

            clear_screen()
            self._render_screen()
            console.print(f"[dim]手牌: {len(hand)}张 | 角色: {'庄家' if is_dealer_turn else '闲家'}[/dim]")
            console.print()

            if p_idx == 0:
                if not self._player_turn(hand): return
            else:
                self._ai_turn(hand, p_idx)
                if not self.game_running: return

            # 清理同步状态 & 轮转
            self.is_meld_active = False
            self.current_turn = (self.current_turn + 1) % 4
            time.sleep(0.4)

        # 流局处理
        console.print("\n⏳ 牌墙剩20张，分张流局。")
        for _ in range(5):
            for h in [self.player_hand]+self.ai_hands:
                t = self.deck.draw()
                if t: h.append(t)
        self.is_dealer = False; self.consecutive_dealer = 0

    def _draw_with_flower_replacement(self, p_idx: int, hand: List[Tile]):
        tile = self.deck.draw()
        flw_list = self.player_flowers if p_idx==0 else self.ai_flowers[p_idx-1]
        while tile and tile.name in HONOR_FLOWER_NAMES:
            flw_list.append(tile)
            tile = self.deck.draw_from_dead()
        if tile:
            hand.append(tile)
            self.last_drawn = tile.name  # 标记新牌
        return tile
    
    def _draw_kong_tile(self, p_idx: int):
        """杠后专用：从死墙摸牌，遇花递归补花"""
        hand = self.player_hand if p_idx == 0 else self.ai_hands[p_idx-1]
        flw_list = self.player_flowers if p_idx == 0 else self.ai_flowers[p_idx-1]

        tile = self.deck.draw_from_dead()  # 杠从死墙抽
        while tile and tile.name in HONOR_FLOWER_NAMES:
            flw_list.append(tile)
            tile = self.deck.draw_from_dead()
            
        if tile:
            hand.append(tile)
            if p_idx == 0: self.last_drawn = tile.name

    def _player_turn(self, hand: List[Tile]) -> bool:
        # 暗杠检测 (摸牌后、出牌前)
        if self._check_an_gang():
            clear_screen(); self._render_screen(); console.print()

        # 自摸检测
        num_m = len(self.player_melds)
        res = self.rule.resolve_win(hand, hand[-1] if hand else None, self.is_dealer, True, num_melds=num_m)
        if res["priority"] > 0:
            self._declare_win(0, res, True); self.game_running = False; return False

        return self._player_discard_phase(hand)

    def _player_discard_phase(self, hand: List[Tile]) -> bool:
        jin_name = self.rule.jin_tile.name if self.rule.jin_tile else None
        # Prompt 紧接在空白行后打印，保证不被覆盖
        console.print(f"👇 出牌 (输入序号 / q退出):")
        console.print(render_discard_prompt(self.player_hand, jin_name, self.last_drawn))
        
        try:
            c = console.input("👉 ").strip()
            if c.lower() == 'q': self.game_running = False; return False
            idx = int(c) - 1
            sorted_h = _sort_tiles(self.player_hand, jin_name)
            if 0 <= idx < len(sorted_h):
                target = sorted_h[idx]
                self.player_hand.remove(target)
                self.last_drawn = None
                self.discards.append(target)
                
                # 打出后立即触发拦截，拦截流会自动控制 skip_turn_increment
                self._handle_global_interception(target, 0)
                return True
            console.print("[red]❌ 序号超出范围[/red]"); return True
        except ValueError:
            console.print("[red]❌ 请输入有效数字[/red]"); return True

    def _ai_evaluate_discard(self, hand: List[Tile], jin_name: str) -> Tile:
        """AI 智能出牌评估：返回最该打出的牌"""
        if not hand: return None

        # 🔒 绝对过滤金牌（除非手牌只剩金，否则永不打出）
        candidates = [t for t in hand if t.name != jin_name]
        if not candidates: candidates = hand  # 极端兜底

        best_tile = None
        max_score = -999

        for t in candidates:
            score = 0
            
            # 1. 刻子/对子价值
            pair_cnt = sum(1 for x in hand if x.name == t.name)
            if pair_cnt >= 3: score -= 80      # 暗刻/明刻核心，极力保留
            elif pair_cnt == 2: score -= 50     # 将牌/碰牌潜力
            else: score += 20                   # 单张基础分

            # 2. 顺子关联度（仅数牌）
            if t.category == "suited":
                v, s = t.value, t.name[-1]
                neighbors = sum(1 for x in hand if x.name in (f"{v-1}{s}", f"{v+1}{s}"))
                if neighbors >= 2: score -= 40  # 两面搭子（如 4万 有 3万+5万）
                elif neighbors == 1: score -= 15 # 边/坎张搭子
                else: score += 15               # 完全孤张，优先处理

            # 3. 字牌/花牌处理
            if t.category in ("wind", "dragon"):
                if pair_cnt == 0: score += 35   # 孤张字牌价值极低
                else: score -= 30               # 成对字牌保留碰/杠

            # 4. 安全修正：已副露的牌型关联牌不打（简化版）
            # 可根据需要加入“牌河危险牌过滤”

            if score > max_score:
                max_score = score
                best_tile = t

        return best_tile or hand[0]  # 兜底返回第一张

    def _ai_turn(self, hand: List[Tile], p_idx: int):
        # AI 暗杠检测
        an_gangs = self.rule.check_an_gang(hand)
        if an_gangs:
            # AI 随机决定是否暗杠 (50%概率)
            if random.random() > 0.5:
                g_name = random.choice(an_gangs)
                removed = []
                for _ in range(4):
                    for t in hand:
                        if t.name == g_name: hand.remove(t); removed.append(t); break
                self.ai_melds[p_idx-1].append(removed)
                console.print(f"🤖 AI{p_idx} 暗杠 {g_name}")
                new_t = self.deck.draw_from_dead()
                if new_t: hand.append(new_t)
                return

        # AI 正常出牌
        num_m = len(self.ai_melds[p_idx-1])
        res = self.rule.resolve_win(hand, hand[-1] if hand else None, False, True, num_melds=num_m)
        if res["priority"] > 0:
            clear_screen(); self._render_screen()
            console.print(f"\n🤖 AI{p_idx} 自摸胡牌! 类型: {res['type']}")
            self._declare_win(p_idx, res, True); self.game_running = False; return

        jin_name = self.rule.jin_tile.name if self.rule.jin_tile else ""
        out = self._ai_evaluate_discard(hand, jin_name)
        if out:
            hand.remove(out)
            self.discards.append(out)
            
        clear_screen(); self._render_screen()
        console.print(f"🤖 AI{p_idx} 打出: {out.name if out else '???'}")
        self._handle_global_interception(out, p_idx)
    
    def _draw_and_handle_flowers(self, p_idx: int):
        """摸牌及自动补花循环（活墙抽牌 → 遇花去死墙补 → 递归至非花）"""
        hand = self.player_hand if p_idx == 0 else self.ai_hands[p_idx-1]
        flw_list = self.player_flowers if p_idx == 0 else self.ai_flowers[p_idx-1]

        tile = self.deck.draw()
        while tile and tile.name in HONOR_FLOWER_NAMES:
            flw_list.append(tile)
            tile = self.deck.draw_from_dead()

        if tile:
            hand.append(tile)
            if p_idx == 0:
                self.last_drawn = tile.name

    def _check_an_gang(self) -> bool:
        an_gangs = self.rule.check_an_gang(self.player_hand)
        if not an_gangs: return False
        console.print(f"\n🔨 手牌已含暗杠: {' / '.join(an_gangs)}")
        try:
            c = console.input("👉 输入牌名暗杠 / 任意键跳过: ").strip()
            if c in an_gangs:
                removed = []
                for _ in range(4):
                    for t in self.player_hand:
                        if t.name == c: self.player_hand.remove(t); removed.append(t); break
                self.player_melds.append(removed)
                console.print("✅ 暗杠成功，下轮从死墙补牌")
                self.post_meld_state = "draw_kong"  # 仅标记杠状态
                return True
        except: pass
        return False

    def _execute_meld_flow(self, player_idx: int, discard: Tile, action_opt: Dict, combo_idx: int = -1) -> bool:
        hand = self.player_hand if player_idx == 0 else self.ai_hands[player_idx-1]
        melds = self.player_melds if player_idx == 0 else self.ai_melds[player_idx-1]
        
        success, group = self.rule.execute_meld(hand, action_opt["type"], discard, combo_idx)
        if not success: return False
        
        melds.append(group)
        console.print(f"✅ {'你' if player_idx==0 else f'AI{player_idx}'} 执行: {action_opt['type']}")
        self.last_drawn = None  # 吃碰后新牌标记清除
        return True
    
    def _handle_global_interception(self, discard: Tile, discarder_idx: int):
        # 🌍 全局优先级扫描：胡 > 明杠 > 碰 > 吃
        # 同一优先级按座位顺序 (+1, +2, +3) 判定，先匹配到者直接获得拦截权
        priority_types = ["胡", "明杠", "碰", "吃"]
        winner_idx = -1
        
        for act_type in priority_types:
            for i in range(1, 4):
                p_idx = (discarder_idx + i) % 4
                hand = self.player_hand if p_idx == 0 else self.ai_hands[p_idx-1]
                num_m = len(self.player_melds) if p_idx == 0 else len(self.ai_melds[p_idx-1])
                is_next = (i == 1)
                
                opts = self.rule.check_meld_options(hand, discard, is_next, num_melds=num_m)
                if any(o["type"] == act_type for o in opts):
                    winner_idx = p_idx
                    break
            if winner_idx != -1: break

        if winner_idx == -1: return  # 无人拦截

        # 🎯 仅触发赢家逻辑，其他玩家自动跳过（优先级规则生效）
        if winner_idx == 0:
            self._player_intercept_prompt(discard, discarder_idx)
        else:
            self._ai_intercept_execute(winner_idx, discard, discarder_idx) 

    def _player_intercept_prompt(self, discard: Tile, discarder_idx: int):
        """赢家统一菜单：显示所有可用操作，按优先级排序"""
        num_m = len(self.player_melds)
        is_next = (discarder_idx + 1) % 4 == 0
        all_opts = self.rule.check_meld_options(self.player_hand, discard, is_next, num_melds=num_m)
        valid_opts = [o for o in all_opts if o["type"] in ("胡", "明杠", "碰", "吃")]
        
        if not valid_opts: return

        # 构建菜单：1.胡 2.明杠 3.碰 4.吃 5.过（动态过滤不可用项）
        menu_str = " / ".join(o["type"] for o in valid_opts)
        console.print(f"\n⚡ 拦截权归属你 | 可选: {menu_str} / 过")
        console.print("  ".join(f"{i+1}.{o['type']}" for i, o in enumerate(valid_opts)) + f"  {len(valid_opts)+1}.过")

        try:
            val = int(console.input("👉 选择: ").strip())
            if 1 <= val <= len(valid_opts):
                chosen = valid_opts[val-1]
                if chosen["type"] == "胡":
                    win_res = self.rule.resolve_win(self.player_hand + [discard], discard, 
                                                    self.is_dealer, False, num_melds=num_m)
                    if win_res["priority"] > 0:
                        self.player_hand.append(discard)
                        self._declare_win(0, win_res, False)
                        self.game_running = False
                        return
                    else:
                        console.print("[red]❌ 实际未满足胡牌条件，视为过。[/red]")
                        return
                        
                elif chosen["type"] == "吃":
                    # 吃牌多选分支
                    combos = chosen["combos"]
                    if len(combos) > 1:
                        console.print(f"🍜 选择吃牌组合:")
                        for i, c in enumerate(combos): console.print(f"  {i+1}. {c[0]}+{c[1]}")
                        c_val = int(console.input("👉 组合序号: ").strip()) - 1
                        combo_idx = c_val if 0 <= c_val < len(combos) else 0
                    else: combo_idx = 0
                    
                    if self._execute_meld_flow(0, discard, chosen, combo_idx):
                        self.is_meld_active = True
                        self._prompt_discard_synchronous()
                else:
                    if self._execute_meld_flow(0, discard, chosen):
                        if chosen["type"] in ("吃", "碰"):
                            self.is_meld_active = True
                            self._prompt_discard_synchronous()
                        elif chosen["type"] == "明杠":
                            self.post_meld_state = "draw_kong"
                return
            else:
                console.print("⏭️ 选择过，继续流程")
        except ValueError:
            console.print("[red]❌ 输入无效，视为过[/red]")
        
    def _ai_intercept_execute(self, p_idx: int, discard: Tile, discarder_idx: int):
        """AI 赢家自动决策并执行"""
        hand = self.ai_hands[p_idx-1]
        num_m = len(self.ai_melds[p_idx-1])
        is_next = (p_idx == (discarder_idx + 1) % 4)  # ✅ 现在已定义
        opts = self.rule.check_meld_options(hand, discard, is_next, num_melds=num_m)
        valid_opts = [o for o in opts if o["type"] in ("胡", "明杠", "碰", "吃")]
        if not valid_opts: return

        act_probs = {"胡": 1.0, "明杠": 1.0, "碰": 0.7, "吃": 0.5}
        chosen = next((o for o in valid_opts if random.random() < act_probs.get(o["type"], 0)), None)
        
        if chosen:
            combo_idx = 0
            if chosen["type"] == "胡":
                win_res = self.rule.resolve_win(hand + [discard], discard, False, False, num_melds=num_m)
                if win_res["priority"] > 0:
                    hand.append(discard)
                    self._declare_win(p_idx, win_res, False)
                    self.game_running = False
                    return
            elif chosen["type"] == "吃":
                combo_idx = 0
            elif self._execute_meld_flow(p_idx, discard, chosen, combo_idx):
                self._ai_discard_after_meld(p_idx)

    def _ai_discard_after_meld(self, p_idx: int):
        """AI 吃/碰成功后，立即从14张手牌中打出一张"""
        hand = self.ai_hands[p_idx-1]
        if len(hand) < 1: return
        
        jin_name = self.rule.jin_tile.name if self.rule.jin_tile else ""
        out_tile = self._ai_evaluate_discard(hand, jin_name)
        if out_tile:
            hand.remove(out_tile)
            self.discards.append(out_tile)
            console.print(f"🤖 AI{p_idx} {out_tile.name} (吃碰后跟打)")
            # 🔄 递归检查新打出的牌是否被拦截
            self._handle_global_interception(out_tile, p_idx)

    def _prompt_discard_synchronous(self):
        """吃/碰成功后，立即从14张手牌中打出一张（同步阻塞）"""
        jin_name = self.rule.jin_tile.name if self.rule.jin_tile else None
        console.print("\n🃏 吃/碰成功，请打出一张牌:")
        console.print(render_discard_prompt(self.player_hand, jin_name, self.last_drawn))
        
        try:
            c = console.input("👉 打出序号: ").strip()
            if c.lower() == 'q': self.game_running = False; return
            idx = int(c) - 1
            sorted_h = _sort_tiles(self.player_hand, jin_name)
            if 0 <= idx < len(sorted_h):
                target = sorted_h[idx]
                self.player_hand.remove(target)
                self.last_drawn = None  # 清除新牌标记
                self.discards.append(target)
                clear_screen()
                self._render_screen()
                console.print(f"🗑️ 你打出: {target.name}")
                # 打出后继续检查是否有其他人可拦截
                self._handle_global_interception(target, 0)
            else:
                console.print("[red]❌ 序号无效，默认跳过[/red]")
        except ValueError:
            console.print("[red]❌ 输入无效，跳过[/red]")

    def _check_melds_for_discard(self, discard: Tile, discarder_idx: int):
        """动态鸣牌拦截菜单（严格对齐规则引擎返回结果）"""
        # 仅拦截玩家（下家）
        if (discarder_idx + 1) % 4 != 0: return
        
        hand = self.player_hand
        actions = self.rule.check_meld_options(hand, discard, is_next_player=True)
        if actions == ["过"]: return

        console.print(f"\n⚡ 拦截 {discard.name} | 可选: {' / '.join(actions)}")
        # 动态生成序号菜单
        menu = {str(i+1): act for i, act in enumerate(actions)}
        console.print("  ".join(f"{k}.{v}" for k, v in menu.items()))
        
        try:
            val = console.input("👉 选择: ").strip()
            act = menu.get(val, "过")
        except: act = "过"

        if act == "过":
            console.print("⏭️ 放弃拦截")
            return

        # 执行拦截
        success = self.rule.execute_meld(hand, act, discard)
        if not success:
            console.print("[red]❌ 条件不足，视为过。[/red]")
            return

        if act == "胡":
            # 二次严格校验，防止引擎边界漏洞
            res = self.rule.resolve_win(hand, discard, self.is_dealer, False)
            if res["priority"] > 0:
                self._declare_win(0, res, False)
                self.game_running = False
            else:
                console.print("[red]❌ 实际未达成胡牌，回滚视为过。[/red]")
                hand.pop()  # 安全回滚
        else:
            console.print(f"✅ 成功执行: {act}")
            # 鸣牌后跳过摸牌，直接进玩家出牌回合
            self.current_turn = 0
            self._player_turn(hand)

    def _declare_win(self, p_idx: int, win_info: Dict, is_zimo: bool):
        hand = self.player_hand if p_idx==0 else self.ai_hands[p_idx-1]
        flw = self.player_flowers if p_idx==0 else self.ai_flowers[p_idx-1]
        flw_pts = sum(6 if c>=4 else c for c in Counter(t.name for t in flw).values())
        score = self.rule.calculate_score(hand, win_info, base=5, flower_pts=flw_pts,
                                          dealer_bonus=self.consecutive_dealer, is_self_draw=is_zimo)
        name = "你" if p_idx==0 else f"AI{p_idx}"
        console.print(f"\n🎉 [bold green]{name} 胡牌![/bold green] [{win_info['type']}] 得分: {score}")
        if p_idx==0: self.consecutive_dealer += 1
        else: self.is_dealer=False; self.consecutive_dealer=0

    def _phase_settlement(self):
        console.print("\n📊 结算完毕。按 Enter 继续..."); console.input()
        self.game_running = True

    def _render_screen(self):
        jin = self.rule.jin_tile.name if self.rule.jin_tile else "未开"
        console.print(render_status(self.deck.remaining, jin, self.current_turn+1, self.is_dealer))
        console.print(render_river(self.discards))
        console.print(render_hand(self.player_hand, jin))
        console.print(render_flowers(self.player_flowers))
        console.print(render_melds(self.player_melds)) # ✅ 新增副露区

if __name__ == "__main__":
    import sys
    if sys.platform == "win32": sys.stdout.reconfigure(encoding="utf-8")
    SanmingGame().start_game()