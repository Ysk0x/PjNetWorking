"""
room.py
-------
Room = ห้องเกม 1 ห้อง มีเจ้ามือ 1 คน + ลูกมือ 2-7 คน
RoomManager = ตัวจัดการหลายห้องพร้อมกัน (server รองรับหลายห้องในเวลาเดียวกันได้)

ไฟล์นี้ยังไม่รู้จัก websocket เลย รับแค่ connection_id (string) มาผูกกับผู้เล่น
เพื่อให้ทดสอบ logic ทั้งห้องได้โดยไม่ต้องรัน network จริง
"""

from server.game import game_state, rules
from server.game.card import Deck
from server.game.player import (
    Player,
    STATUS_DRAWN,
    STATUS_OUT_OF_MONEY,
    STATUS_POK,
    STATUS_STAY,
    STATUS_THINKING,
)

MIN_PLAYERS_TO_START = 2  # ไม่รวมเจ้ามือ (เจ้ามือ + ลูกมืออย่างน้อย 1 คน ก็เริ่มได้ แต่ทดสอบง่ายด้วยค่านี้)


class Room:
    """ห้องเกม 1 ห้อง เก็บผู้เล่นทั้งหมด, สำรับไพ่, และ state ปัจจุบัน"""

    def __init__(self, room_id, max_players=8, stake=100):
        self.room_id = room_id
        self.max_players = max_players
        self.stake = stake  # เงินเริ่มต้นของทุกคนที่เข้าห้องนี้ (รีเซ็ตทุกครั้งที่สร้างห้องใหม่ ไม่มี persistence)
        self.players = {}  # connection_id -> Player, ใช้ dict เพื่อหาผู้เล่นตัดสินใจได้เร็ว
        self.deck = None
        self.state = game_state.WAITING
        self._round_summary = None  # cache ผลลัพธ์ reveal ของรอบปัจจุบัน กัน settle ซ้ำถ้ามีหลาย action มาถึง state REVEAL พร้อมกัน (race condition)

    # ---------- จัดการผู้เล่นเข้า/ออกห้อง ----------

    def add_player(self, connection_id, name):
        if len(self.players) >= self.max_players:
            raise ValueError("ห้องเต็มแล้ว")
        # คนแรกที่เข้าห้องเป็นเจ้ามือโดยอัตโนมัติ (ตามสเปก MVP)
        is_dealer = len(self.players) == 0
        player = Player(connection_id, name, is_dealer=is_dealer)
        player.balance = self.stake
        self.players[connection_id] = player
        return player

    def remove_player(self, connection_id):
        player = self.players.pop(connection_id, None)
        if player and player.is_dealer and self.players:
            # เจ้ามือหลุดออกจากห้อง โอนตำแหน่งเจ้ามือให้คนแรกที่เหลือ เพื่อให้ห้องเล่นต่อได้
            new_dealer = next(iter(self.players.values()))
            new_dealer.is_dealer = True

    def get_dealer(self):
        for player in self.players.values():
            if player.is_dealer:
                return player
        return None

    def get_non_dealer_players(self):
        return [p for p in self.players.values() if not p.is_dealer]

    def get_active_bettors(self):
        """ผู้เล่นที่ต้องวางเดิมพันในรอบนี้ (ไม่ใช่เจ้ามือ และยังไม่เงินหมด)"""
        return [p for p in self.get_non_dealer_players() if p.status != STATUS_OUT_OF_MONEY]

    # ---------- เริ่มรอบใหม่: เข้าเฟสเดิมพันก่อนแจกไพ่ ----------

    def start_round(self):
        """
        เข้าเฟสเดิมพัน (waiting/reveal -> betting) เคลียร์มือไพ่/เดิมพันของทุกคนเตรียมรอบใหม่
        การแจกไพ่จริงจะเกิดขึ้นหลังผู้เล่นที่ active ทุกคนวางเดิมพันครบแล้ว (ดู _deal_cards)
        """
        for player in self.players.values():
            player.reset_for_new_round()
        self._round_summary = None

        if not self.get_active_bettors():
            raise ValueError("ไม่มีผู้เล่นที่สามารถเดิมพันได้ในรอบนี้")

        self.state = game_state.BETTING

    def player_place_bet(self, connection_id, amount):
        """ผู้เล่น (ไม่ใช่เจ้ามือ) วางเดิมพันสำหรับรอบนี้"""
        if self.state != game_state.BETTING:
            raise ValueError("ตอนนี้ไม่ใช่จังหวะเดิมพัน")

        player = self.players.get(connection_id)
        if player is None:
            raise ValueError("ไม่พบผู้เล่นนี้ในห้อง")
        if player.is_dealer:
            raise ValueError("เจ้ามือไม่ต้องวางเดิมพัน")
        if player.status == STATUS_OUT_OF_MONEY:
            raise ValueError("เงินหมดแล้ว ไม่สามารถเดิมพันได้")
        if player.has_bet:
            raise ValueError("วางเดิมพันไปแล้วในรอบนี้")
        if amount <= 0 or amount > player.balance:
            raise ValueError("จำนวนเดิมพันไม่ถูกต้อง")

        player.place_bet(amount)
        self._deal_cards_if_ready()

    def _deal_cards_if_ready(self):
        active = self.get_active_bettors()
        if all(p.has_bet for p in active):
            self._deal_cards()

    def _deal_cards(self):
        """
        แจกไพ่ 2 ใบให้ทุกคน (สับสำรับใหม่ทุกรอบ) แล้วเช็คป๊อกทันที
        เปลี่ยน state: betting -> dealing
        ผู้เล่นที่เงินหมด (status out_of_money) ไม่ได้รับไพ่ในรอบนี้
        """
        self.deck = Deck()
        self.state = game_state.DEALING

        for player in self.players.values():
            if player.status == STATUS_OUT_OF_MONEY:
                continue

            player.receive_card(self.deck.draw())
            player.receive_card(self.deck.draw())

            pok, _ = rules.is_pok(player.hand)
            player.status = STATUS_POK if pok else STATUS_THINKING

        # ถ้าทุกคนป๊อกหมด (รวมเจ้ามือ) ไม่ต้องรอจั่วใบที่ 3 ข้ามไปเปิดไพ่ได้เลย
        if self.all_players_done():
            self.state = game_state.REVEAL
        else:
            self.state = game_state.PLAYING

    # ---------- ตาจั่วไพ่ใบที่ 3 ----------

    def player_draw_card(self, connection_id):
        """ผู้เล่นเลือก 'จั่วเพิ่ม' ไพ่ใบที่ 3"""
        player = self.players.get(connection_id)
        if player is None:
            raise ValueError("ไม่พบผู้เล่นนี้ในห้อง")
        if player.status != STATUS_THINKING:
            raise ValueError("ผู้เล่นคนนี้ตัดสินใจไปแล้ว หรือป๊อกไปแล้ว")

        player.receive_card(self.deck.draw())
        player.status = STATUS_DRAWN
        self._advance_state_if_ready()

    def player_stay(self, connection_id):
        """ผู้เล่นเลือก 'อยู่' ไม่จั่วเพิ่ม"""
        player = self.players.get(connection_id)
        if player is None:
            raise ValueError("ไม่พบผู้เล่นนี้ในห้อง")
        if player.status != STATUS_THINKING:
            raise ValueError("ผู้เล่นคนนี้ตัดสินใจไปแล้ว หรือป๊อกไปแล้ว")

        player.status = STATUS_STAY
        self._advance_state_if_ready()

    def all_players_done(self):
        """เช็คว่าทุกคนตัดสินใจแล้วหรือยัง (ป๊อก/จั่วแล้ว/อยู่แล้ว/เงินหมด ถือว่า done)"""
        done_statuses = (STATUS_POK, STATUS_DRAWN, STATUS_STAY, STATUS_OUT_OF_MONEY)
        return all(p.status in done_statuses for p in self.players.values())

    def _advance_state_if_ready(self):
        if self.all_players_done():
            self.state = game_state.REVEAL

    # ---------- เปิดไพ่และตัดสินผล ----------

    def reveal_and_settle(self):
        """
        เปิดไพ่ทุกคน เทียบกับเจ้ามือทีละคน ปรับ balance ตามผลแพ้ชนะ คืน dict สรุปผลทั้งห้อง
        เรียกได้เมื่อ state เป็น REVEAL เท่านั้น

        หมายเหตุ: ป๊อกเด้งไม่ใช่กระดานเดิมพันกองเดียวแบบโป๊กเกอร์ แต่ละผู้เล่นตัดสินผล/เงินเดิมพัน
        แยกกันเป็นคู่กับเจ้ามือ (ไม่มี shared pot) — ผู้เล่นที่เงินหมด (out_of_money) ถูกข้าม ไม่มีเดิมพันให้ตัดสิน

        Idempotent ต่อรอบ: cache ผลลัพธ์ไว้ที่ self._round_summary เพราะ ws_server.py เรียกจากหลาย handler
        (place_bet/player_draw/player_stay) ทุกครั้งที่ state กลายเป็น reveal — ถ้า action ของผู้เล่นสองคน
        มาถึงพร้อมกัน (asyncio interleave) ทั้งสอง handler จะเห็น state==reveal และเรียกฟังก์ชันนี้ซ้ำได้
        ถ้าไม่ cache ไว้ balance จะถูกหักซ้ำสองครั้งจากรอบเดียว
        """
        if self._round_summary is not None:
            return self._round_summary

        dealer = self.get_dealer()
        if dealer is None:
            raise ValueError("ห้องนี้ยังไม่มีเจ้ามือ")

        results = {}
        for player in self.get_non_dealer_players():
            if player.status == STATUS_OUT_OF_MONEY:
                continue

            result = rules.compare(dealer.hand, player.hand)
            # เพิ่ม hand ของผู้เล่นเข้าไปเอง (rules.compare คืนแค่แต้ม/ป๊อก ไม่มีไพ่จริง)
            # ฝั่ง client ต้องใช้ไพ่จริงนี้ render การ์ด flip ตอน reveal cascade
            result["hand"] = [card.to_dict() for card in player.hand]

            bet = player.current_bet
            multiplier = result["player"]["multiplier"]
            delta = bet * multiplier if result["winner"] == "player" else -bet * multiplier
            player.balance += delta
            dealer.balance -= delta

            if player.balance <= 0:
                player.status = STATUS_OUT_OF_MONEY

            result["bet"] = bet
            result["balance"] = player.balance
            results[player.connection_id] = result

        self._round_summary = {
            "dealer": dealer.to_dict(reveal_cards=True),
            "results": results,
        }
        return self._round_summary

    def to_dict(self, reveal_cards=False):
        """สรุป state ทั้งห้องเป็น dict ไว้ส่งให้ client (broadcast game_state)"""
        return {
            "room_id": self.room_id,
            "state": self.state,
            "players": [p.to_dict(reveal_cards=reveal_cards) for p in self.players.values()],
        }

    def to_dict_for(self, viewer_connection_id):
        """
        เหมือน to_dict() แต่เปิดไพ่ให้เห็นเฉพาะของ "ตัวเอง" เท่านั้น (คนอื่นในห้องเห็นแค่ card_count)
        ใช้ตอน broadcast game_state ระหว่างเล่น เพื่อให้แต่ละคนเห็นไพ่ตัวเองได้โดยไม่เห็นไพ่คนอื่น
        """
        players_data = []
        for player in self.players.values():
            reveal = player.connection_id == viewer_connection_id
            players_data.append(player.to_dict(reveal_cards=reveal))
        return {
            "room_id": self.room_id,
            "state": self.state,
            "players": players_data,
        }


class RoomManager:
    """จัดการหลายห้องพร้อมกัน สร้าง/ค้นหา/ลบห้อง"""

    def __init__(self):
        self.rooms = {}  # room_id -> Room

    def create_room(self, room_id, max_players=8, stake=100):
        if room_id in self.rooms:
            raise ValueError("ชื่อห้องนี้มีคนใช้แล้ว")
        room = Room(room_id, max_players=max_players, stake=stake)
        self.rooms[room_id] = room
        return room

    def get_room(self, room_id):
        return self.rooms.get(room_id)

    def remove_room(self, room_id):
        self.rooms.pop(room_id, None)

    def remove_player_from_all_rooms(self, connection_id):
        """เวลาผู้เล่นหลุดการเชื่อมต่อ ให้ลบออกจากห้องที่เขาอยู่ (ไม่รู้ว่าอยู่ห้องไหน จึงไล่เช็คทุกห้อง)"""
        for room in list(self.rooms.values()):
            if connection_id in room.players:
                room.remove_player(connection_id)
                # ถ้าห้องไม่มีคนเหลือแล้ว ลบห้องทิ้งไปเลยเพื่อไม่ให้ค้างอยู่ใน memory
                if not room.players:
                    self.remove_room(room.room_id)

    def list_rooms_summary(self):
        """สรุปรายการห้องทั้งหมดไว้ให้หน้า lobby แสดงเป็นลิสต์ real-time
        ส่งแค่ metadata ระดับห้องเท่านั้น (ไม่มีชื่อผู้เล่น/ไพ่/เงินรายบุคคล) เพื่อไม่ให้หลุดข้อมูลห้องอื่น"""
        return [
            {
                "room_id": room.room_id,
                "player_count": len(room.players),
                "max_players": room.max_players,
                "stake": room.stake,
                "state": room.state,
            }
            for room in self.rooms.values()
        ]
