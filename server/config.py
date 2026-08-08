"""
config.py
---------
ค่าตั้งค่าต่างๆ ของ server รวมไว้ที่เดียว แก้ตรงนี้จุดเดียวพอ
"""

HOST = "0.0.0.0"      # 0.0.0.0 = รับ connection จากทุก IP ในวง LAN ได้ (ไม่ใช่แค่ localhost)
WS_PORT = 8765         # port สำหรับ WebSocket server (เกม logic แบบ real-time)
HTTP_PORT = 8000       # port สำหรับ static file server (serve หน้าเว็บ client/)

MIN_PLAYERS = 3        # จำนวนผู้เล่นขั้นต่ำต่อห้อง (รวมเจ้ามือ)
MAX_PLAYERS = 8        # จำนวนผู้เล่นสูงสุดต่อห้อง (รวมเจ้ามือ)
