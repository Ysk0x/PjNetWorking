"""
game_state.py
-------------
State machine ง่ายๆ สำหรับหนึ่งห้องเกม
waiting  -> ห้องเพิ่งสร้าง / รอผู้เล่นเข้าห้อง ยังไม่เริ่มรอบ
betting  -> เจ้ามือกดเริ่มรอบแล้ว รอผู้เล่นที่ไม่ใช่เจ้ามือวางเดิมพันให้ครบก่อนแจกไพ่
dealing  -> กำลังแจกไพ่ 2 ใบให้ทุกคน + เช็คป๊อก
playing  -> ผู้เล่นแต่ละคนเลือกจั่วไพ่ใบที่ 3 หรืออยู่
reveal   -> เปิดไพ่ทุกคน คำนวณผลแพ้ชนะ

เก็บเป็น string constants ธรรมดา (ไม่ใช้ Enum) เพื่อให้ serialize เป็น JSON ส่งให้ client ได้ตรงๆ
"""

WAITING = "waiting"
BETTING = "betting"
DEALING = "dealing"
PLAYING = "playing"
REVEAL = "reveal"

# ลำดับ state ที่ถูกต้อง ใช้เช็คเวลาเปลี่ยน state ว่าข้ามขั้นตอนหรือไม่
_VALID_TRANSITIONS = {
    WAITING: [BETTING],
    BETTING: [DEALING],
    DEALING: [PLAYING, REVEAL],  # ถ้าทุกคนป๊อกหมด ข้าม PLAYING ไป REVEAL ได้ทันที
    PLAYING: [REVEAL],
    REVEAL: [WAITING, BETTING],  # เริ่มรอบใหม่ได้จากตรงนี้
}


def can_transition(current_state, next_state):
    """เช็คว่าเปลี่ยนจาก state ปัจจุบันไป state ใหม่ได้หรือไม่"""
    return next_state in _VALID_TRANSITIONS.get(current_state, [])
