/*
  socket.js
  ---------
  จัดการการเชื่อมต่อ WebSocket กับ server
  หน้าที่เดียว: เปิด connection, ส่ง message, และแจก message ที่ได้รับให้ตัวอื่นฟัง (callback)
*/

const GameSocket = (function () {
  let socket = null;
  const listeners = {}; // message type -> list ของ callback function

  // แปลง address ที่ผู้ใช้พิมพ์/วางมาให้เป็น ws(s):// URL ที่ใช้ต่อได้จริง
  // - ว่างเปล่า -> ใช้ host เดียวกับที่เปิดหน้าเว็บ + port 8765 (ค่าเดิม เล่น LAN ไม่ต้องพิมพ์อะไรเลย)
  // - มี https://.../ http://... (เช่น URL จาก cloudflared/ngrok tunnel) -> แปลง scheme เป็น wss/ws ตรงๆ
  // - มีแค่ hostname/IP เปล่าๆไม่มี scheme -> เติม ws:// + :8765 ให้ (เดา LAN default)
  function normalizeAddress(rawAddress) {
    const address = (rawAddress || "").trim();
    if (!address) {
      return `ws://${window.location.hostname}:8765`;
    }
    if (address.startsWith("https://")) {
      return "wss://" + address.slice("https://".length);
    }
    if (address.startsWith("http://")) {
      return "ws://" + address.slice("http://".length);
    }
    if (address.startsWith("wss://") || address.startsWith("ws://")) {
      return address;
    }
    return `ws://${address}:8765`;
  }

  function connect(serverAddress, onOpenCallback, onFailCallback) {
    const wsUrl = normalizeAddress(serverAddress);
    let opened = false;
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      opened = true;
      console.log("เชื่อมต่อ server สำเร็จ");
      if (onOpenCallback) onOpenCallback();
    };

    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      const callbacks = listeners[message.type] || [];
      callbacks.forEach((cb) => cb(message));
    };

    socket.onclose = () => {
      console.log("การเชื่อมต่อกับ server ถูกปิด");
      // ถ้าปิดก่อนที่จะเปิดสำเร็จเลย แปลว่าต่อไม่ติดตั้งแต่แรก (URL ผิด/tunnel ไม่ตอบสนอง)
      // ต้องแจ้งผู้ใช้เห็นชัดๆ ไม่ใช่แค่ log เงียบๆ ลง console เหมือนเดิม
      if (!opened && onFailCallback) onFailCallback(wsUrl);
    };

    socket.onerror = (err) => {
      console.error("WebSocket error:", err);
    };
  }

  function send(type, data) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      console.warn("ยังไม่ได้เชื่อมต่อ server");
      return;
    }
    socket.send(JSON.stringify({ type, ...data }));
  }

  // ลงทะเบียนฟังก์ชันที่จะถูกเรียกเมื่อได้รับ message ประเภทนี้จาก server
  function on(messageType, callback) {
    if (!listeners[messageType]) {
      listeners[messageType] = [];
    }
    listeners[messageType].push(callback);
  }

  return { connect, send, on, normalizeAddress };
})();
