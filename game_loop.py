# game_loop.py
import os, time, random
from typing import List, Optional, Dict
from collections import Counter
from rich.console import Console
from tile import Deck, Tile
from rule_sanming import SanmingRule, HONOR_FLOWER_NAMES
from cli_ui import *

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
        self.dealer_idx: int = 0
        self.consecutive_dealer: int = 0
        self.current_turn: int = 0
        self.game_running: bool = False
        self.last_drawn: Optional[str] = None  # ✅ 确保初始化
        self.skip_turn_increment: bool = False
        self.post_meld_state: Optional[str] = None
        self.is_meld_active: bool = False
        self.game_log: List[str] = []  #  游戏事件日志
        self.next_turn_override: Optional[int] = None 

    def _add_log(self, msg: str):
        """添加日志条目（自动带时间戳或序号）"""
        from datetime import datetime
        # 简化版：仅追加文本，可按需添加时间戳
        self.game_log.append(msg)
        # 限制日志总数，防止内存溢出
        if len(self.game_log) > 50:
            self.game_log = self.game_log[-50:]

    def start_game(self):
        console.print("[bold cyan]🧧 三明福州十六张麻将 v0.1.5[/bold cyan]")
        self.game_running = True
        while self.game_running:
            try: self._run_round()
            except KeyboardInterrupt:
                console.print("\n⏹️ 已终止。"); break
            time.sleep(2)

    def _run_round(self) -> None:
        self._init_round()
        self.deck.setup_wall(*self.deck.roll_dice())
        self._phase_deal()
        self._phase_initial_flowers()

        while True:
            d1, d2 = self.deck.roll_dice()
            jin = self.deck.reveal_jin(d1, d2)
            if not jin: break
            if jin.name in HONOR_FLOWER_NAMES:
                self.player_flowers.append(jin)
                self._add_log(f"🌸 翻出花牌 {jin.name} → 入庄家补花区，重新翻金...")
                continue
            self.rule.set_jin(jin)
            self._add_log(f"🎲 开金掷骰: {d1}+{d2}={d1+d2} → 金: {jin.name}")
            break
        time.sleep(1.5)

        if self._check_special_initial_wins():
            self._show_round_end_reveal()  # ✅ 开局特殊胡牌也摊牌
            self._phase_settlement()
            return

        self._main_play_loop()
        self._show_round_end_reveal()  # ✅ 正常流程结束摊牌
        self._phase_settlement()

    def _init_round(self) -> None:
        self.deck = Deck()
        self.player_hand = []
        self.ai_hands = [[], [], []]
        self.player_flowers = []
        self.ai_flowers = [[], [], []]
        self.player_melds = []
        self.ai_melds = [[], [], []]
        self.discards = []
        self.current_turn = self.dealer_idx  # 🎯 强绑定：庄家永远先手
        self.post_meld_state = None
        self.is_meld_active = False
        self.last_drawn = None
        self.next_turn_override = None
        self._add_log("🔄 新一局开始，发牌中...")

    def _phase_deal(self):
        hands = [[], [], [], []]
        for i in range(4):
            count = 17 if i == self.dealer_idx else 16
            for _ in range(count):
                t = self.deck.draw()
                if t: hands[i].append(t)
                
        self.player_hand = hands[0]
        self.ai_hands = hands[1:]
        self.current_turn = self.dealer_idx

    def _phase_initial_flowers(self):
        self._add_log("🌸 开局集中补花...")
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
        if not jin: return False

        hands = [self.player_hand] + self.ai_hands
        for i, h in enumerate(hands):
            res = self.rule.check_initial_special_wins(h, i, self.dealer_idx, jin)
            if res["type"] != "无":
                # 🎯 核心修正：仅抢金允许将翻出的金纳入手牌，天胡/三金倒保持发牌原貌
                if "抢金" in res["type"]:
                    h.append(jin)
                    
                # 开局特殊胜利统一按高倍率结算（is_zimo=True 触发 ×2 倍率，可按需调整）
                self._declare_win(i, res, is_zimo=True)
                return True
        return False

    def _main_play_loop(self):
        dealer_skip_done = False
        while self.game_running:
            # 🎯 核心拦截：一旦牌墙≤20张，立刻转入分张阶段
            if self.deck.remaining <= 20:
                self._phase_final_draw()
                return  # 分张内部已处理结算，直接返回本局
            
            p_idx = self.current_turn
            hand = self.player_hand if p_idx == 0 else self.ai_hands[p_idx - 1]

            # 🃏 摸牌逻辑：仅庄家首轮跳过，其余严格按状态机执行
            should_draw = True
            if not dealer_skip_done and p_idx == self.dealer_idx:
                should_draw = False
                dealer_skip_done = True  # ✅ 庄家首轮行动后，标记解除，后续正常摸牌

            if should_draw:
                if self.post_meld_state == "chi_pong":
                    pass  # 吃碰后跳过摸牌
                else:
                    self._draw_and_handle_flowers(p_idx)

            # 🎨 渲染 UI
            clear_screen(); self._render_screen()

            # ⚙️ 回合行动
            if p_idx == 0:
                if not self._player_turn(hand): return
            else:
                self._ai_turn(hand, p_idx)
                if not self.game_running: return

            # 🔄 清理状态 & 轮转
            self.is_meld_active = False

            # 🎯 拦截重定向逻辑：优先使用标记，否则默认顺时针+1
            if self.next_turn_override is not None:
                self.current_turn = self.next_turn_override
                self.next_turn_override = None  # 消费标记
            else:
                self.current_turn = (self.current_turn + 1) % 4
            
            time.sleep(0.4)
    
    def _phase_final_draw(self):
        """🀄 分张阶段：剩20张时，每人依次摸1张，可自摸，不可出牌"""
        self._add_log("⏳ 牌墙剩20张，进入分张阶段（每人限摸1张，不可出牌）...")
        clear_screen(); self._render_screen()

        for _ in range(4):
            p_idx = self.current_turn
            hand = self.player_hand if p_idx == 0 else self.ai_hands[p_idx - 1]
            flw_list = self.player_flowers if p_idx == 0 else self.ai_flowers[p_idx - 1]
            name = '你' if p_idx==0 else f'AI{p_idx}'

            # 1. 摸牌 & 自动补花循环
            tile = self.deck.draw()
            self._add_log(f"📥 {name} 分张")
            while tile and tile.name in HONOR_FLOWER_NAMES:
                flw_list.append(tile)
                self._add_log(f"🌸 {name} 分张补花")
                tile = self.deck.draw()

            if not tile:
                self._add_log("⚠️ 牌墙已空，提前结束分张。")
                break

            hand.append(tile)
            if p_idx == 0: self.last_drawn = tile.name

            # 2. 立即检查自摸
            num_m = len(self.player_melds) if p_idx == 0 else len(self.ai_melds[p_idx-1])
            is_dealer = (p_idx == self.dealer_idx)
            res = self.rule.resolve_win(hand, tile, is_dealer, True, num_melds=num_m)

            if res["priority"] > 0:
                self._add_log(f"🎉 {name} 分张自摸！")
                clear_screen(); self._render_screen()
                self._declare_win(p_idx, res, is_zimo=True)
                return  # 🎯 有人胡牌，直接终止分张并结算

            # 3. 未胡，刷新UI并轮到下家
            clear_screen(); self._render_screen()
            time.sleep(0.8)  # 留出视觉缓冲，让玩家看清摸牌结果
            self.current_turn = (self.current_turn + 1) % 4

        # 4. 四人全部分完，无人胡牌 → 荒庄流局
        self._add_log(f"🏁 分张完毕无人胡牌，荒庄流局，庄家连庄！")
        clear_screen(); self._render_screen()
        self.consecutive_dealer += 1
        self._show_round_end_reveal()
        self._phase_settlement()

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
            return True

        # 自摸检测
        num_m = len(self.player_melds)
        res = self.rule.resolve_win(hand, hand[-1] if hand else None, (0 == self.dealer_idx), True, num_melds=num_m)
        if res["priority"] > 0:
            self._declare_win(0, res, True); self.game_running = False; return False

        return self._player_discard_phase(hand)

    def _player_discard_phase(self, hand: List[Tile]) -> bool:
        jin_name = self.rule.jin_tile.name if self.rule.jin_tile else None
        console.print(f"\n👇 出牌 (输入序号 / q退出):")
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
                self._add_log(f"📤 你打出: {target.name}")
                # ✅ 立即清屏并刷新，让玩家直观看到手牌减少
                clear_screen(); self._render_screen()                
                # 触发拦截
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
            # 50%概率暗杠
            if random.random() > 0.5:
                g_name = random.choice(an_gangs)
                removed = []
                for _ in range(4):
                    for t in list(hand):
                        if t.name == g_name:
                            hand.remove(t); removed.append(t); break
                self.ai_melds[p_idx-1].append(removed)
                self._add_log(f"🤖 AI{p_idx} 暗杠")
                
                # 🆕 暗杠后必须同步执行：补死墙牌 → 立即出牌 → 设置下家
                self._draw_kong_tile(p_idx)
                self._ai_discard_after_meld(p_idx)
                # next_turn_override 已在 _ai_discard_after_meld 中设置
                return  # 🚫 阻断后续正常摸打逻辑，防止重复出牌

        # AI 正常出牌
        num_m = len(self.ai_melds[p_idx-1])
        res = self.rule.resolve_win(hand, hand[-1] if hand else None, (p_idx == self.dealer_idx), True, num_melds=num_m)
        if res["priority"] > 0:
            clear_screen(); self._render_screen()
            self._declare_win(p_idx, res, True); self.game_running = False; return

        jin_name = self.rule.jin_tile.name if self.rule.jin_tile else ""
        out = self._ai_evaluate_discard(hand, jin_name)
        if out:
            hand.remove(out)
            self.discards.append(out)
            self._add_log(f"🤖 AI{p_idx} 打出: {out.name}")    
            clear_screen(); self._render_screen()
            self._handle_global_interception(out, p_idx)
    
    def _draw_and_handle_flowers(self, p_idx: int):
        """摸牌及自动补花循环（活墙抽牌 → 遇花去死墙补 → 递归至非花）"""
        hand = self.player_hand if p_idx == 0 else self.ai_hands[p_idx-1]
        flw_list = self.player_flowers if p_idx == 0 else self.ai_flowers[p_idx-1]

        tile = self.deck.draw()
        self._add_log((f"📥 你" if p_idx == 0 else f"🤖 AI{p_idx}") + " 摸牌") 
        while tile and tile.name in HONOR_FLOWER_NAMES:
            flw_list.append(tile)
            tile = self.deck.draw_from_dead()
            self._add_log((f"📥 你" if p_idx == 0 else f"🤖 AI{p_idx}") + " 补花") 

        if tile:
            hand.append(tile)
            if p_idx == 0:
                self.last_drawn = tile.name

    def _check_an_gang(self) -> bool:
        an_gangs = self.rule.check_an_gang(self.player_hand)
        if not an_gangs: return False

        console.print(f"\n🔨 检测到可暗杠: {' / '.join(an_gangs)}")
        # 🆕 构建数字菜单
        menu_items = [f"[bold cyan]{i+1}. 暗杠 {name}[/]" for i, name in enumerate(an_gangs)]
        menu_items.append(f"[dim]{len(an_gangs)+1}. 过[/]")
        console.print("  ".join(menu_items))
        
        try:
            c = console.input("👉 选择序号: ").strip()
            if c.lower() == 'q': self.game_running = False; return False
            idx = int(c) - 1
            if 0 <= idx < len(an_gangs):
                chosen_name = an_gangs[idx]
                # 1. 移除4张牌至副露区
                removed = []
                for _ in range(4):
                    for t in list(self.player_hand):  # list() 避免遍历中修改
                        if t.name == chosen_name:
                            self.player_hand.remove(t)
                            removed.append(t)
                            break
                self.player_melds.append(removed)
                self._add_log(f"🀂 你暗杠")

                # 2. 🚨 立即从死墙补牌 + 递归补花
                tile = self.deck.draw_from_dead()
                self._add_log(f"📥 暗杠补牌")
                while tile and tile.name in HONOR_FLOWER_NAMES:
                    self.player_flowers.append(tile)
                    self._add_log(f"🌸 补花")
                    tile = self.deck.draw_from_dead()

                if tile:
                    self.player_hand.append(tile)
                    self.last_drawn = tile.name
                else:
                    self._add_log("⚠️ 死墙已空，暗杠后无牌可补")

                # 3. 同步进入出牌阶段
                self._prompt_discard_synchronous()
                return True
            else:
                console.print("⏭️ 选择过，继续流程")
                return False
        except ValueError:
            console.print("[red]❌ 输入无效，视为过[/red]")
            return False

    def _execute_meld_flow(self, player_idx: int, discard: Tile, action_opt: Dict, combo_idx: int = -1) -> bool:
        hand = self.player_hand if player_idx == 0 else self.ai_hands[player_idx-1]
        melds = self.player_melds if player_idx == 0 else self.ai_melds[player_idx-1]
        
        success, group = self.rule.execute_meld(hand, action_opt["type"], discard, combo_idx)
        if not success: return False
        
        melds.append(group)
        self._add_log(f"✅ {'你' if player_idx==0 else f'AI{player_idx}'} 执行: {action_opt['type']}")
        self.last_drawn = None  # 鸣牌后新牌标记清除
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
                                                    (0 == self.dealer_idx), False, num_melds=num_m)
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
                            if self._execute_meld_flow(0, discard, chosen):
                                self._draw_kong_tile(0)              # 🆕 立即从死墙补牌
                                self._prompt_discard_synchronous()   # 🆕 同步阻塞，等待玩家出牌
                            return
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
                win_res = self.rule.resolve_win(hand + [discard], discard, (p_idx == self.dealer_idx), False, num_melds=num_m)
                if win_res["priority"] > 0:
                    hand.append(discard)
                    self._declare_win(p_idx, win_res, False)
                    self.game_running = False
                    return
            elif chosen["type"] in ("吃", "碰", "明杠"):  # ✅ 统一走执行流
                if self._execute_meld_flow(p_idx, discard, chosen, combo_idx):
                    if chosen["type"] == "明杠":
                        self._draw_kong_tile(p_idx)  # 🆕 AI 立即补死墙牌
                    self._ai_discard_after_meld(p_idx)  # 🆕 统一走 AI 跟打逻辑

    def _ai_discard_after_meld(self, p_idx: int):
        """AI 吃/碰成功后，立即从14张手牌中打出一张"""
        hand = self.ai_hands[p_idx-1]
        if len(hand) < 1: return
        
        jin_name = self.rule.jin_tile.name if self.rule.jin_tile else ""
        out_tile = self._ai_evaluate_discard(hand, jin_name)
        if out_tile:
            hand.remove(out_tile)
            self.discards.append(out_tile)
            self._add_log(f"🤖 AI{p_idx} {out_tile.name} (鸣牌后跟打)")
            clear_screen(); self._render_screen()
            # ✅ 预设下一回合为当前拦截者的下家
            self.next_turn_override = (p_idx + 1) % 4
            # 🔄 递归检查新打出的牌是否被拦截（若发生新拦截，next_turn_override 会被覆盖）
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
                self._add_log(f"📤 你打出: {target.name}")
                clear_screen(); self._render_screen()
                # 打出后继续检查是否有其他人可拦截
                # ✅ 预设下一回合为玩家的下一家(AI1)
                self.next_turn_override = 1 
                self._handle_global_interception(target, 0)
            else:
                console.print("[red]❌ 序号无效，默认跳过[/red]")
        except ValueError:
            console.print("[red]❌ 输入无效，跳过[/red]")

    def _declare_win(self, p_idx: int, win_info: Dict, is_zimo: bool):
        hand = self.player_hand if p_idx==0 else self.ai_hands[p_idx-1]
        flw = self.player_flowers if p_idx==0 else self.ai_flowers[p_idx-1]
        flw_pts = sum(6 if c>=4 else c for c in Counter(t.name for t in flw).values())
        score = self.rule.calculate_score(hand, win_info, base=5, flower_pts=flw_pts,
                                          dealer_bonus=self.consecutive_dealer, is_self_draw=is_zimo)
        name = "你" if p_idx==0 else f"AI{p_idx}"
        base_type = win_info["type"]
        if base_type in ("天胡", "三金倒", "庄家抢金", "闲家抢金"):
            win_label = base_type
        else:
            win_label = f"{base_type} (自摸)" if is_zimo else f"{base_type} (点炮)"
            
        self._add_log(f"🎉 {name} {win_label} 胡牌！得分: {score}")
        console.print(f"\n🎉 [bold green]{name} 胡牌![/bold green] [{win_label}] 得分: {score}")
        
        if p_idx == self.dealer_idx:
            self.consecutive_dealer += 1
            self._add_log(f"👑 庄家连庄！当前连庄数: {self.consecutive_dealer}")
        else:
            self.dealer_idx = (self.dealer_idx + 1) % 4  # 庄家下台，顺时针轮换
            self.consecutive_dealer = 0
            self._add_log("🔄 庄家轮换至下家。")

    def _show_round_end_reveal(self):
        """本局结束，展示所有玩家手牌"""
        console.print("[bold yellow]🔚 本局结束，所有玩家摊牌：[/bold yellow]")
        jin_name = self.rule.jin_tile.name if self.rule.jin_tile else ""
        from cli_ui import render_reveal_hand
        
        # 👤 玩家摊牌：显示手牌+副露
        console.print(render_reveal_hand(
            self.player_hand, jin_name, f"👤 你的手牌 ({len(self.player_hand) + sum(len(group) for group in self.player_melds)}张, {len(self.player_flowers)}🌸)", 
            melds=self.player_melds, hide_flowers=True
        ))
        
        # 🤖 AI 摊牌：显示手牌+副露，花牌单独显示
        for i, ai_h in enumerate(self.ai_hands, 1):
            console.print(render_reveal_hand(
                ai_h, jin_name, f"🤖 AI {i} 手牌 ({len(self.ai_hands[i-1]) + sum(len(group) for group in self.ai_melds[i-1])}张, {len(self.ai_flowers[i-1])}🌸)", 
                melds=self.ai_melds[i-1], hide_flowers=True
            ))

    def _phase_settlement(self):
        console.print("\n📊 结算完毕。按 Enter 继续，按 Ctrl+C 退出..."); console.input()
        self.game_running = True

    def _render_screen(self):
        jin = self.rule.jin_tile.name if self.rule.jin_tile else "未开"
        console.print(render_status(self.deck.remaining, jin, self.current_turn, self.dealer_idx))
        console.print(render_river(self.discards))
        console.print(render_game_log(self.game_log))
        console.print(render_hand(self.player_hand, jin))
        console.print(render_melds(self.player_melds))
        console.print(render_flowers(self.player_flowers))

if __name__ == "__main__":
    import sys
    if sys.platform == "win32": sys.stdout.reconfigure(encoding="utf-8")
    SanmingGame().start_game()