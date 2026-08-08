"""
สคริปต์ทดสอบ end-to-end ผ่าน WebSocket จริง (จำลองผู้เล่นหลายคนต่อเข้าห้องเดียวกัน)
รันด้วย: py test_ws_e2e.py (ต้องเปิด server ไว้ก่อนที่ py -m server.main)
"""

import asyncio
import json

import websockets

WS_URL = "ws://localhost:8765"


async def player_flow(name, room_id, is_creator, results, action_plan, expected_players=3):
    async with websockets.connect(WS_URL) as ws:
        msg_type = "create_room" if is_creator else "join_room"
        await ws.send(json.dumps({"type": msg_type, "room_id": room_id, "player_name": name}))

        my_connection_id = None
        acted_this_round = False
        bet_this_round = False
        round_started = False

        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(raw)

            if data["type"] == "room_joined":
                my_connection_id = data["connection_id"]
                print(f"[{name}] joined room, connection_id={my_connection_id}")

            elif data["type"] == "game_state":
                state = data["data"]
                # เจ้ามือรอให้ทุกคนเข้าห้องครบก่อนเริ่มรอบ (แทน sleep คงที่ ซึ่ง flaky ถ้า connect ช้า)
                if is_creator and not round_started and len(state["players"]) >= expected_players:
                    round_started = True
                    await ws.send(json.dumps({"type": "start_round"}))
                me = next((p for p in state["players"] if p["connection_id"] == my_connection_id), None)
                if me:
                    print(f"[{name}] state={state['state']} my_status={me['status']} hand={me.get('hand')}")
                    if state["state"] == "betting" and not me["is_dealer"] and not bet_this_round:
                        bet_this_round = True
                        await ws.send(json.dumps({"type": "place_bet", "amount": 10}))
                    if me["status"] == "thinking" and not acted_this_round:
                        acted_this_round = True
                        action = action_plan(me.get("hand", []))
                        await ws.send(json.dumps({"type": action}))
                if state["state"] == "reveal":
                    acted_this_round = False
                    bet_this_round = False

            elif data["type"] == "round_result":
                print(f"[{name}] ROUND RESULT: {data['data']}")
                results[name] = data["data"]
                return  # จบการทดสอบของผู้เล่นคนนี้หลังได้ผลลัพธ์รอบแรก


async def main():
    results = {}
    room_id = "e2e-test-room"

    await asyncio.gather(
        player_flow("Dealer", room_id, True, results, lambda hand: "player_stay"),
        player_flow("Alice", room_id, False, results, lambda hand: "player_draw"),
        player_flow("Bob", room_id, False, results, lambda hand: "player_stay"),
    )

    assert "Dealer" in results and "Alice" in results and "Bob" in results
    print("\nE2E TEST PASSED — ทุกคนได้รับผลลัพธ์รอบเปิดไพ่ครบ")


if __name__ == "__main__":
    asyncio.run(main())
