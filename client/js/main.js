/*
  main.js
  -------
  ผูก DOM event (คลิกปุ่ม) เข้ากับ socket.js (ส่ง message) และ ui.js (วาดผลลัพธ์)
  เป็นไฟล์ "ตัวเชื่อม" ระหว่างสองไฟล์ข้างบน ไม่มี logic ของตัวเองมากนัก
*/

let myConnectionId = null;
let myRoomId = null;
let myPlayerName = ""; // บันทึกไว้ตอนเชื่อมต่อสำเร็จครั้งเดียว ใช้ส่งซ้ำได้ตอน join/create โดยไม่ต้องพิมพ์ใหม่
let latestPlayers = [];
let lastGameState = null; // เก็บ state ก่อนหน้า ไว้เทียบว่าเพิ่งเข้ารอบใหม่/เพิ่งป๊อกหรือยัง
let lastMyStatus = null;
let selectedStake = 100;
let peekedCards = [false, false]; // แง้มไพ่ 2 ใบแรกของตัวเอง รีเซ็ตทุกครั้งที่เริ่มรอบใหม่ (DOM ถูกสร้างใหม่ทุก broadcast จึงต้องเก็บ state ไว้นอก DOM)

document.addEventListener("DOMContentLoaded", () => {
  const nameInput = document.getElementById("player-name-input");
  const addressInput = document.getElementById("server-address-input");
  const roomInput = document.getElementById("room-id-input");

  // prefill host ปัจจุบัน เล่น LAN เดียวกันไม่ต้องพิมพ์อะไรเลย (วาง URL จาก tunnel เองถ้าจะเล่นข้ามที่)
  addressInput.placeholder = window.location.hostname || addressInput.placeholder;

  setupStakePresets();
  setupBetSlider();

  document.getElementById("connect-btn").addEventListener("click", () => {
    const playerName = nameInput.value.trim();
    if (!playerName) {
      document.getElementById("connect-error").textContent = "กรุณาใส่ชื่อผู้เล่น";
      return;
    }
    document.getElementById("connect-error").textContent = "";
    GameSocket.connect(
      addressInput.value.trim(),
      () => {
        myPlayerName = playerName;
        UI.showScreen("room-list-screen");
      },
      (wsUrl) => {
        document.getElementById("connect-error").textContent =
          `เชื่อมต่อ server ไม่สำเร็จ (${wsUrl}) — เช็คว่า "ที่อยู่ server" ถูกต้อง และ tunnel/server ยังเปิดอยู่`;
      }
    );
  });

  document.getElementById("show-create-room-btn").addEventListener("click", () => {
    UI.showEl(document.getElementById("create-room-form"));
  });

  document.getElementById("create-room-btn").addEventListener("click", () => {
    const roomId = roomInput.value.trim();
    if (!roomId) {
      UI.showLobbyError("กรุณาใส่ชื่อห้อง");
      return;
    }
    UI.showLobbyError("");
    GameSocket.send("create_room", {
      room_id: roomId,
      player_name: myPlayerName,
      stake: selectedStake,
    });
  });

  document.getElementById("start-round-btn").addEventListener("click", () => {
    peekedCards = [false, false];
    GameSocket.send("start_round", {});
  });

  document.getElementById("place-bet-btn").addEventListener("click", () => {
    const amount = parseInt(document.getElementById("bet-slider").value, 10);
    if (amount > 0) {
      GameSocket.send("place_bet", { amount });
    }
  });

  document.getElementById("draw-btn").addEventListener("click", () => {
    GameSocket.send("player_draw", {});
  });

  document.getElementById("stay-btn").addEventListener("click", () => {
    GameSocket.send("player_stay", {});
  });

  registerSocketHandlers();
});

// ปุ่ม stake preset (100/500/1000) ตอนสร้างห้อง — เลือกอันเดียว, custom input ล้าง selection ถ้าพิมพ์เอง
function setupStakePresets() {
  const presetButtons = document.querySelectorAll(".stake-preset-btn");
  const customInput = document.getElementById("stake-custom-input");

  presetButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      presetButtons.forEach((b) => b.classList.remove("is-selected"));
      btn.classList.add("is-selected");
      selectedStake = parseInt(btn.dataset.stake, 10);
      customInput.value = "";
    });
  });

  customInput.addEventListener("input", () => {
    const value = parseInt(customInput.value, 10);
    if (value > 0) {
      presetButtons.forEach((b) => b.classList.remove("is-selected"));
      selectedStake = value;
    }
  });
}

// สไลด์เดิมพันต่อรอบ: อัปเดตตัวเลข + ส่วนเติมสีทองของ track แบบ real-time ทุกครั้งที่ลาก
// max/step ถูกตั้งใหม่ทุกครั้งที่เข้าเฟสเดิมพัน (ดู renderGameState) ตาม balance ปัจจุบัน
function setupBetSlider() {
  const slider = document.getElementById("bet-slider");
  const display = document.getElementById("bet-amount-display");

  slider.addEventListener("input", () => {
    updateBetSliderDisplay(slider, display);
  });
}

function updateBetSliderDisplay(slider, display) {
  const min = parseInt(slider.min, 10) || 0;
  const max = parseInt(slider.max, 10) || 100;
  const value = parseInt(slider.value, 10) || 0;
  const percent = max > min ? ((value - min) / (max - min)) * 100 : 0;
  slider.style.setProperty("--fill-percent", `${percent}%`);
  display.innerHTML = UI.moneyLabel(value);
}

function registerSocketHandlers() {
  GameSocket.on("room_list", (message) => {
    UI.renderRoomList(message.data, (roomId) => {
      GameSocket.send("join_room", { room_id: roomId, player_name: myPlayerName });
    });
  });

  GameSocket.on("room_joined", (message) => {
    myConnectionId = message.connection_id;
    myRoomId = message.room_id;
    document.getElementById("room-label").textContent = `ห้อง: ${myRoomId}`;
    UI.showScreen("game-screen");
  });

  GameSocket.on("error", (message) => {
    UI.showLobbyError(message.message);
  });

  GameSocket.on("game_state", (message) => {
    renderGameState(message.data);
  });

  GameSocket.on("round_result", (message) => {
    UI.renderRevealAtSeats(message.data, latestPlayers, myConnectionId);
  });
}

function renderGameState(state) {
  latestPlayers = state.players;
  UI.renderTable(state.players, myConnectionId);
  UI.renderBetPile(state.players);

  const me = state.players.find((p) => p.connection_id === myConnectionId);
  const isDealer = me ? me.is_dealer : false;

  // ปุ่ม "เริ่มรอบใหม่" ให้เจ้ามือกดได้เมื่อ state เป็น waiting หรือ reveal เท่านั้น
  const startBtn = document.getElementById("start-round-btn");
  const canStart = isDealer && (state.state === "waiting" || state.state === "reveal");
  startBtn.classList.toggle("hidden", !canStart);

  // เพิ่งเข้ารอบใหม่ (state ก่อนหน้าไม่ใช่ dealing/playing แต่ตอนนี้เป็นแล้ว) -> เตรียม animate แจกไพ่
  const justStartedDealing =
    (state.state === "dealing" || state.state === "playing") &&
    lastGameState !== "dealing" &&
    lastGameState !== "playing";

  if (!me) {
    lastGameState = state.state;
    return;
  }

  const myHandEl = document.getElementById("my-hand");
  const myStatusEl = document.getElementById("my-status");
  const actionButtons = document.getElementById("action-buttons");
  const bettingSection = document.getElementById("betting-section");
  const balanceLabel = document.getElementById("my-balance-label");

  // เฟสเดิมพัน: โชว์ #betting-section ให้ผู้เล่นที่ไม่ใช่เจ้ามือ ยังไม่เดิมพัน และยังไม่เงินหมด
  const showBetting =
    state.state === "betting" && !isDealer && !me.has_bet && me.status !== "out_of_money";
  if (showBetting) {
    balanceLabel.innerHTML = UI.moneyLabel(me.balance);
    const slider = document.getElementById("bet-slider");
    const display = document.getElementById("bet-amount-display");
    slider.max = me.balance;
    slider.step = Math.max(10, Math.round((me.balance * 0.05) / 10) * 10);
    if (parseInt(slider.value, 10) > me.balance) {
      slider.value = me.balance;
    }
    updateBetSliderDisplay(slider, display);
    UI.showEl(bettingSection);
  } else {
    UI.hideEl(bettingSection);
  }

  // server ส่ง "hand" มาให้เฉพาะของเรา (room.to_dict_for ในฝั่ง server เปิดไพ่แค่คนที่ดูอยู่)
  if (me.hand) {
    UI.renderOwnHand(myHandEl, me.hand, peekedCards, {
      animate: justStartedDealing ? "deal" : undefined,
      onPeeked: (i) => {
        peekedCards[i] = true;
      },
    });
  }

  // ตรวจจับว่าตัวเองเพิ่งป๊อก (status เปลี่ยนเป็น "pok" ในบรอดคาสต์นี้) -> เล่น signature moment
  if (me.status === "pok" && lastMyStatus !== "pok") {
    UI.showPokStamp();
  }
  lastMyStatus = me.status;

  myStatusEl.textContent = statusText(state.state, me.status, me.card_count);

  const showActions = me.status === "thinking";
  if (showActions) {
    UI.showEl(actionButtons);
  } else {
    UI.hideEl(actionButtons);
  }

  lastGameState = state.state;
}

function statusText(gameState, status, cardCount) {
  if (gameState === "betting") {
    if (status === "out_of_money") return "เงินหมด รอบนี้ไม่ได้เล่น";
    return "รอวางเดิมพัน...";
  }
  const labels = {
    waiting: "รอเจ้ามือเริ่มรอบใหม่",
    thinking: `มีไพ่ ${cardCount} ใบ — เลือกจั่วเพิ่มหรืออยู่ (กดค้างไพ่เพื่อแง้มดู)`,
    pok: "ป๊อก! รอเปิดไพ่",
    stay: "เลือกอยู่แล้ว รอเปิดไพ่",
    drawn: "จั่วไพ่ใบที่ 3 แล้ว รอเปิดไพ่",
    out_of_money: "เงินหมด รอบนี้ไม่ได้เล่น",
  };
  return labels[status] || status;
}
