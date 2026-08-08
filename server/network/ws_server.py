"""
ws_server.py
------------
WebSocket server: รับ connection จาก client แต่ละคน, แปลง JSON message เป็น action,
เรียก game logic ใน server/game/ แล้ว broadcast state กลับไปให้ทุกคนในห้อง

หมายเหตุเรื่อง async/await (เผื่อยังไม่คุ้นเคย):
- `async def` คือฟังก์ชันที่ "รอ" งานอื่นได้โดยไม่บล็อกทั้งโปรแกรม
- `await` คือจุดที่ "หยุดรอ" งานนั้นเสร็จ แล้วปล่อยให้ event loop ไปทำงานอื่นก่อนได้
- เพราะเรามีผู้เล่นหลายคนต่อพร้อมกัน server ต้องคุยกับทุกคนพร้อมๆกันได้ (ไม่ใช่ทีละคนตามลำดับ)
  async/await คือกลไกที่ทำให้ทำแบบนั้นได้โดยไม่ต้องเปิดหลาย thread เอง
"""

import asyncio
import json
import uuid

import websockets
from websockets.asyncio.server import serve

from server.game.room import RoomManager
from server.network import protocol

room_manager = RoomManager()

# เก็บว่า websocket connection แต่ละอันผูกกับ connection_id และอยู่ห้องไหน
# key = websocket object, value = {"connection_id": str, "room_id": str}
connections = {}


async def handler(websocket):
    """
    ฟังก์ชันหลักที่รันแยกกันสำหรับ "แต่ละ" client ที่เชื่อมต่อเข้ามา
    (websockets library เรียกฟังก์ชันนี้ให้อัตโนมัติทุกครั้งที่มีคนต่อเข้ามาใหม่)
    """
    connection_id = str(uuid.uuid4())
    connections[websocket] = {"connection_id": connection_id, "room_id": None}

    # ยังไม่ได้เข้าห้อง (room_id เป็น None) = อยู่หน้า lobby -> ส่งลิสต์ห้องปัจจุบันให้ทันทีที่ต่อเข้ามา
    await send_to(websocket, protocol.make_message(
        protocol.ROOM_LIST, data=room_manager.list_rooms_summary()
    ))

    try:
        # วน loop รอรับ message จาก client คนนี้ไปตลอดจนกว่าจะหลุดการเชื่อมต่อ
        async for raw_message in websocket:
            await handle_message(websocket, raw_message)
    except websockets.exceptions.ConnectionClosed:
        pass  # client ปิดเบราว์เซอร์/หลุดเน็ต ถือเป็นเรื่องปกติ ไม่ต้อง error
    finally:
        await handle_disconnect(websocket)


async def handle_message(websocket, raw_message):
    """แปลง JSON string เป็น dict แล้วสั่งงานตาม type"""
    try:
        data = json.loads(raw_message)
    except json.JSONDecodeError:
        await send_to(websocket, protocol.make_error("ข้อความไม่ใช่ JSON ที่ถูกต้อง"))
        return

    msg_type = data.get("type")
    info = connections[websocket]

    try:
        if msg_type == protocol.CREATE_ROOM:
            await on_create_room(websocket, info, data)
        elif msg_type == protocol.JOIN_ROOM:
            await on_join_room(websocket, info, data)
        elif msg_type == protocol.START_ROUND:
            await on_start_round(websocket, info)
        elif msg_type == protocol.PLACE_BET:
            await on_place_bet(websocket, info, data)
        elif msg_type == protocol.PLAYER_DRAW:
            await on_player_draw(websocket, info)
        elif msg_type == protocol.PLAYER_STAY:
            await on_player_stay(websocket, info)
        else:
            await send_to(websocket, protocol.make_error(f"ไม่รู้จัก message type: {msg_type}"))
    except ValueError as exc:
        # ValueError คือ error ที่ game logic (room.py) ตั้งใจ raise เมื่อ action ไม่ถูกต้อง เช่น ห้องเต็ม
        await send_to(websocket, protocol.make_error(str(exc)))


async def on_create_room(websocket, info, data):
    room_id = data.get("room_id", "").strip()
    player_name = data.get("player_name", "").strip()
    if not room_id or not player_name:
        raise ValueError("ต้องระบุชื่อห้องและชื่อผู้เล่น")

    try:
        stake = int(data.get("stake", 100))
    except (TypeError, ValueError):
        raise ValueError("จำนวนเงินเริ่มต้นไม่ถูกต้อง")
    if stake <= 0:
        raise ValueError("จำนวนเงินเริ่มต้นต้องมากกว่า 0")

    room = room_manager.create_room(room_id, stake=stake)
    room.add_player(info["connection_id"], player_name)
    info["room_id"] = room_id

    await send_to(websocket, protocol.make_message(
        protocol.ROOM_JOINED, connection_id=info["connection_id"], room_id=room_id
    ))
    await broadcast_game_state(room)
    await broadcast_room_list()


async def on_join_room(websocket, info, data):
    room_id = data.get("room_id", "").strip()
    player_name = data.get("player_name", "").strip()
    room = room_manager.get_room(room_id)
    if room is None:
        raise ValueError("ไม่พบห้องนี้")
    if not player_name:
        raise ValueError("ต้องระบุชื่อผู้เล่น")

    room.add_player(info["connection_id"], player_name)
    info["room_id"] = room_id

    await send_to(websocket, protocol.make_message(
        protocol.ROOM_JOINED, connection_id=info["connection_id"], room_id=room_id
    ))
    await broadcast_game_state(room)
    await broadcast_room_list()


async def on_start_round(websocket, info):
    # เริ่มรอบใหม่แค่เข้าเฟสเดิมพัน (betting) เท่านั้น การแจกไพ่จริงจะเกิดขึ้นหลังทุกคนวางเดิมพันครบ
    # (ดู on_place_bet) จึง state จะไม่ข้ามไป reveal ตรงนี้ได้เลยเหมือน flow เดิม
    room = _get_room_or_raise(info)
    room.start_round()
    await broadcast_game_state(room)


async def on_place_bet(websocket, info, data):
    room = _get_room_or_raise(info)
    try:
        amount = int(data.get("amount"))
    except (TypeError, ValueError):
        raise ValueError("จำนวนเดิมพันไม่ถูกต้อง")

    room.player_place_bet(info["connection_id"], amount)
    await broadcast_game_state(room)
    if room.state == "reveal":
        await broadcast_round_result(room)


async def on_player_draw(websocket, info):
    room = _get_room_or_raise(info)
    room.player_draw_card(info["connection_id"])
    await broadcast_game_state(room)
    if room.state == "reveal":
        await broadcast_round_result(room)


async def on_player_stay(websocket, info):
    room = _get_room_or_raise(info)
    room.player_stay(info["connection_id"])
    await broadcast_game_state(room)
    if room.state == "reveal":
        await broadcast_round_result(room)


def _get_room_or_raise(info):
    room = room_manager.get_room(info["room_id"]) if info["room_id"] else None
    if room is None:
        raise ValueError("คุณยังไม่ได้เข้าห้อง")
    return room


async def handle_disconnect(websocket):
    """เวลา client หลุดการเชื่อมต่อ ลบผู้เล่นออกจากห้อง แล้วแจ้งคนที่เหลือ"""
    info = connections.pop(websocket, None)
    if info is None:
        return

    room = room_manager.get_room(info["room_id"]) if info["room_id"] else None
    if room is not None:
        room.remove_player(info["connection_id"])
        if room_manager.get_room(room.room_id) is not None:  # ห้องอาจถูกลบไปแล้วถ้าไม่มีคนเหลือ
            await broadcast_game_state(room)
        await broadcast_room_list()


# ---------- ฟังก์ชันช่วยส่ง message ----------

async def send_to(websocket, message_dict):
    await websocket.send(json.dumps(message_dict))


async def broadcast_game_state(room):
    """
    ส่ง state ปัจจุบันของห้องให้ทุกคนในห้อง
    แต่ละคนได้รับ message "เฉพาะตัว" ที่เปิดไพ่ให้เห็นแค่ของตัวเอง (คนอื่นเห็นแค่ card_count)
    """
    targets = _room_websockets(room)
    if not targets:
        return

    async def send_one(ws, connection_id):
        data = room.to_dict_for(connection_id)
        message = protocol.make_message(protocol.GAME_STATE, data=data)
        await ws.send(json.dumps(message))

    # asyncio.gather ส่งให้ทุกคนพร้อมกัน ไม่ต้องรอคนแรกส่งเสร็จก่อนค่อยส่งคนที่สอง
    await asyncio.gather(
        *(send_one(ws, connections[ws]["connection_id"]) for ws in targets),
        return_exceptions=True,
    )


async def broadcast_round_result(room):
    """ส่งผลลัพธ์ตอนเปิดไพ่ (reveal) ให้ทุกคนเห็นไพ่ทุกคนในห้อง"""
    summary = room.reveal_and_settle()
    message = protocol.make_message(protocol.ROUND_RESULT, data=summary)
    await _broadcast_to_room(room, message)


def _room_websockets(room):
    return [ws for ws, info in connections.items() if info["room_id"] == room.room_id]


async def broadcast_room_list():
    """ส่งลิสต์ห้องล่าสุดให้ทุก connection ที่ยังอยู่หน้า lobby (room_id เป็น None) เท่านั้น
    คนที่เข้าห้องไปแล้วไม่ต้องได้รับ (ไม่เกี่ยวกับเขาแล้ว)"""
    targets = [ws for ws, info in connections.items() if info["room_id"] is None]
    if not targets:
        return
    payload = json.dumps(protocol.make_message(
        protocol.ROOM_LIST, data=room_manager.list_rooms_summary()
    ))
    await asyncio.gather(*(ws.send(payload) for ws in targets), return_exceptions=True)


async def _broadcast_to_room(room, message_dict):
    """ส่ง message เดียวกันให้ทุก websocket ที่อยู่ในห้องนี้ พร้อมกัน (ไม่รอทีละคน)"""
    payload = json.dumps(message_dict)
    targets = _room_websockets(room)
    if not targets:
        return
    await asyncio.gather(*(ws.send(payload) for ws in targets), return_exceptions=True)


async def run_server(host, port):
    """เปิด WebSocket server แล้วรอไปตลอด (จนกว่าโปรแกรมจะถูกปิด)"""
    async with serve(handler, host, port):
        await asyncio.get_running_loop().create_future()  # ค้าง await ตลอดไป เพื่อให้ server ไม่ปิดตัวเอง
