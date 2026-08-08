"""
protocol.py
-----------
นิยาม message type ทั้งหมดที่ใช้คุยกันระหว่าง client <-> server ผ่าน WebSocket
ทุก message เป็น JSON รูปแบบ {"type": "...", ...}

การรวม message type ไว้ที่นี่ที่เดียว ช่วยกันพิมพ์ผิด และทำให้เห็นภาพรวม protocol ทั้งหมดในไฟล์เดียว
"""

# ----- message จาก client -> server -----
CREATE_ROOM = "create_room"        # {"type": "create_room", "room_id": "...", "player_name": "...", "stake": 100}
JOIN_ROOM = "join_room"            # {"type": "join_room", "room_id": "...", "player_name": "..."}
START_ROUND = "start_round"        # {"type": "start_round"}  (เจ้ามือกดเริ่มรอบ -> เข้าเฟสเดิมพัน)
PLACE_BET = "place_bet"            # {"type": "place_bet", "amount": 50}  (ผู้เล่นวางเดิมพันก่อนแจกไพ่)
PLAYER_DRAW = "player_draw"        # {"type": "player_draw"}  (ผู้เล่นกด "จั่วเพิ่ม")
PLAYER_STAY = "player_stay"        # {"type": "player_stay"}  (ผู้เล่นกด "อยู่")

# ----- message จาก server -> client -----
ROOM_JOINED = "room_joined"        # ยืนยันว่าเข้าห้องสำเร็จ พร้อม connection_id ของตัวเอง
GAME_STATE = "game_state"          # broadcast state ปัจจุบันของห้องให้ทุกคน
ROUND_RESULT = "round_result"      # ผลลัพธ์ตอนเปิดไพ่ (reveal)
ERROR = "error"                    # แจ้ง error กลับไปยัง client ที่ทำ action ผิด
ROOM_LIST = "room_list"            # รายการห้องทั้งหมด (เฉพาะ metadata ระดับห้อง ไม่มีข้อมูลผู้เล่น/ไพ่)
                                    # ส่งให้ connection ที่ยังอยู่ lobby (ยังไม่เข้าห้อง) ตอนต่อครั้งแรก
                                    # และ broadcast ซ้ำทุกครั้งที่ห้อง/จำนวนผู้เล่นเปลี่ยน


def make_message(msg_type, **kwargs):
    """สร้าง dict message ตาม type ที่กำหนด (ยังไม่ได้ json.dumps ให้ ws_server.py ทำเอง)"""
    message = {"type": msg_type}
    message.update(kwargs)
    return message


def make_error(text):
    return make_message(ERROR, message=text)
