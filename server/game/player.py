"""
player.py
---------
นิยาม class Player เก็บข้อมูลผู้เล่น 1 คนในห้อง
"""

# สถานะของผู้เล่นในแต่ละรอบ ใช้แสดงบน UI ว่าใครกำลังทำอะไร
STATUS_WAITING = "waiting"      # ยังไม่แจกไพ่ / รอรอบใหม่
STATUS_THINKING = "thinking"    # แจกไพ่แล้ว กำลังตัดสินใจจั่ว/อยู่
STATUS_POK = "pok"              # ป๊อกแล้ว (จบตาตัวเองทันที)
STATUS_STAY = "stay"            # เลือก "อยู่" ไม่จั่วเพิ่ม
STATUS_DRAWN = "drawn"          # จั่วไพ่ใบที่ 3 แล้ว
STATUS_OUT_OF_MONEY = "out_of_money"  # เงินหมด ไม่สามารถเดิมพัน/เล่นต่อในห้องนี้ได้แล้ว


class Player:
    """ตัวแทนผู้เล่น 1 คน (รวมถึงเจ้ามือ ก็ใช้ class เดียวกันนี้)"""

    def __init__(self, connection_id, name, is_dealer=False):
        self.connection_id = connection_id  # ไว้ผูกกับ websocket connection ฝั่ง network layer
        self.name = name
        self.is_dealer = is_dealer
        self.hand = []                      # list ของ Card ในมือ
        self.status = STATUS_WAITING
        self.balance = 0                    # เงินคงเหลือ ตั้งตอน add_player ตาม stake ของห้อง
        self.current_bet = 0                # จำนวนที่วางเดิมพันไว้ในรอบนี้ (0 ถ้ายังไม่วาง/เป็นเจ้ามือ)
        self.has_bet = False                # วางเดิมพันรอบนี้แล้วหรือยัง

    def reset_for_new_round(self):
        """เคลียร์มือไพ่/เดิมพัน เตรียมรอบใหม่ (สถานะเงินหมดค้างข้ามรอบ ไม่รีเซ็ต)"""
        self.hand = []
        self.current_bet = 0
        self.has_bet = False
        if self.status != STATUS_OUT_OF_MONEY:
            self.status = STATUS_WAITING

    def place_bet(self, amount):
        """วางเดิมพันจำนวน amount สำหรับรอบนี้ (validate ที่ Room เพราะต้องรู้ state/บาลานซ์)"""
        self.current_bet = amount
        self.has_bet = True

    def receive_card(self, card):
        self.hand.append(card)

    def to_dict(self, reveal_cards=False):
        """
        แปลงข้อมูลผู้เล่นเป็น dict สำหรับส่งให้ client
        reveal_cards=False ตอนยังเล่นอยู่ (ผู้เล่นอื่นไม่ควรเห็นไพ่กัน)
        reveal_cards=True ตอนเปิดไพ่ท้ายรอบ (reveal state)

        balance/current_bet/has_bet ไม่ใช่ข้อมูลไพ่ จึงส่งแบบไม่มีเงื่อนไขเสมอ
        (ต่างจาก hand ที่ต้องกรองตาม reveal_cards เพื่อไม่ให้เห็นไพ่คนอื่นก่อนเปิด)
        """
        data = {
            "connection_id": self.connection_id,
            "name": self.name,
            "is_dealer": self.is_dealer,
            "status": self.status,
            "card_count": len(self.hand),
            "balance": self.balance,
            "current_bet": self.current_bet,
            "has_bet": self.has_bet,
        }
        if reveal_cards:
            data["hand"] = [card.to_dict() for card in self.hand]
        return data
