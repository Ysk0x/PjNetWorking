/*
  Pok Deng Premium UI
  -------------------
  This file replaces the old main.js + ui.js presentation layer.
  Keep the repository's existing client/js/socket.js.

  Existing server message types used:
  create_room, join_room, start_round, place_bet, player_draw, player_stay
  room_list, room_joined, game_state, round_result, error
*/

(() => {
  "use strict";

  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];

  const state = {
    connected: false,
    name: "",
    connectionId: null,
    roomId: null,
    roomStake: 100,
    selectedStake: 100,
    players: [],
    game: null,
    roomFilter: "all",
    search: "",
    ready: false,
    sound: true,
    lastStatus: null,
    lastGameState: null
  };

  const sampleRooms = [
    {room_id:"Royal-01", stake:100, player_count:6, max_players:8, kind:"popular", vip:false},
    {room_id:"Beginner-02", stake:100, player_count:3, max_players:8, kind:"beginner", vip:false},
    {room_id:"Neon-VIP", stake:1000, player_count:7, max_players:8, kind:"vip", vip:true},
    {room_id:"Night-07", stake:500, player_count:5, max_players:8, kind:"popular", vip:false},
    {room_id:"Lucky-88", stake:500, player_count:4, max_players:8, kind:"all", vip:false},
    {room_id:"HighRoller", stake:1000, player_count:8, max_players:8, kind:"vip", vip:true}
  ];

  const statusLabels = {
    waiting: "WAITING",
    betting: "BETTING",
    dealing: "DEALING",
    thinking: "THINKING",
    stay: "STAY",
    pok: "POK!",
    out_of_money: "OUT",
    done: "DONE"
  };

  function money(value) {
    const n = Number(value || 0);
    return `฿${n.toLocaleString("en-US")}`;
  }

  function showToast(message) {
    const el = $("#toast");
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(showToast.t);
    showToast.t = setTimeout(() => el.classList.remove("show"), 2200);
  }

  function setPage(name) {
    if (["waiting", "game"].includes(name)) {
      $("#waiting-screen").classList.toggle("active-page", name === "waiting");
      $("#game-screen").classList.toggle("active-page", name === "game");
      if (name === "waiting") renderWaiting();
      return;
    }
    $$(".page:not(#waiting-screen):not(#game-screen)").forEach(p => p.classList.remove("active-page"));
    const page = $(`#${name}-screen`);
    if (page) page.classList.add("active-page");
    $$(".nav-item").forEach(btn => btn.classList.toggle("active", btn.dataset.nav === name));
  }

  function openShell() {
    $("#connect-screen").classList.add("hidden");
    $("#app-shell").classList.remove("hidden");
  }

  function connect() {
    const name = $("#player-name-input").value.trim();
    const address = $("#server-address-input").value.trim();
    if (!name) {
      $("#connect-error").textContent = "Please enter a player name.";
      return;
    }
    $("#connect-error").textContent = "";
    state.name = name;
    GameSocket.connect(address, () => {
      state.connected = true;
      openShell();
      updateProfile();
      setPage("home");
      showToast("Connected to Pok Deng server");
    }, wsUrl => {
      $("#connect-error").textContent = `Could not connect to ${wsUrl}`;
    });
  }

  function updateProfile() {
    const letter = (state.name[0] || "P").toUpperCase();
    $("#top-player-name").textContent = state.name || "Player";
    $("#top-avatar").textContent = letter;
    $("#top-avatar-2").textContent = letter;
    $("#top-balance").textContent = "1,250";
  }

  function openCreateModal() {
    $("#create-modal").classList.remove("hidden");
    setTimeout(() => $("#room-id-input").focus(), 20);
  }
  function closeCreateModal() {
    $("#create-modal").classList.add("hidden");
    $("#lobby-error").textContent = "";
  }

  function createRoom() {
    const roomId = $("#room-id-input").value.trim();
    const custom = Number($("#stake-custom-input").value);
    if (custom > 0) state.selectedStake = custom;
    if (!roomId) {
      $("#lobby-error").textContent = "Enter a room ID.";
      return;
    }
    $("#lobby-error").textContent = "";
    GameSocket.send("create_room", {
      room_id: roomId,
      player_name: state.name,
      stake: state.selectedStake
    });
    closeCreateModal();
  }

  function joinRoom(roomId) {
    if (!state.connected) return showToast("Connect to the server first.");
    GameSocket.send("join_room", { room_id: roomId, player_name: state.name });
  }

  function renderRoomCard(room, index = 0) {
    const vip = room.vip || Number(room.stake) >= 1000 || room.kind === "vip";
    const kind = room.kind || (vip ? "vip" : "all");
    return `
      <article class="room-card ${vip ? "vip" : ""}" style="animation-delay:${index * 40}ms">
        <div class="room-top">
          <span class="room-id">${escapeHtml(room.room_id)}</span>
          <span class="badge ${vip ? "vip" : ""}">${vip ? "VIP" : "NORMAL"}</span>
        </div>
        <div class="room-meta">
          <div><span>MIN BET</span><b>${money(room.stake)}</b></div>
          <div><span>PLAYERS</span><b>${room.player_count}/${room.max_players}</b></div>
        </div>
        <div class="room-bottom">
          <span class="room-status"><i></i>${room.player_count >= room.max_players ? "FULL" : "OPEN"}</span>
          <button class="btn ${vip ? "btn-pink" : "btn-primary"} join-room" data-room="${escapeAttr(room.room_id)}">${room.player_count >= room.max_players ? "FULL" : "JOIN TABLE"}</button>
        </div>
      </article>`;
  }

  function getRooms() {
    const source = state.rooms && state.rooms.length ? state.rooms : sampleRooms;
    return source.map(r => ({
      ...r,
      max_players: r.max_players || 8,
      player_count: r.player_count ?? 0,
      stake: r.stake ?? 100
    }));
  }

  function renderRooms() {
    const rooms = getRooms().filter(room => {
      const q = state.search.toLowerCase();
      const matchSearch = !q || String(room.room_id).toLowerCase().includes(q);
      const vip = room.vip || Number(room.stake) >= 1000 || room.kind === "vip";
      const filterOk =
        state.roomFilter === "all" ||
        (state.roomFilter === "vip" && vip) ||
        (state.roomFilter === "beginner" && (room.kind === "beginner" || Number(room.stake) <= 100)) ||
        (state.roomFilter === "popular" && (room.kind === "popular" || Number(room.player_count) >= 5));
      return matchSearch && filterOk;
    });
    $("#room-list").innerHTML = rooms.map(renderRoomCard).join("");
    $("#lobby-empty").classList.toggle("hidden", rooms.length !== 0);
    $$(".join-room").forEach(btn => btn.addEventListener("click", () => {
      if (btn.textContent.trim() !== "FULL") joinRoom(btn.dataset.room);
    }));
    $("#home-room-preview").innerHTML = getRooms().slice(0, 3).map(renderRoomCard).join("");
    $$("#home-room-preview .join-room").forEach(btn => btn.addEventListener("click", () => joinRoom(btn.dataset.room)));
  }

  function renderWaiting() {
    $("#waiting-room-title").textContent = state.roomId ? state.roomId.toUpperCase() : "ROOM";
    $("#waiting-room-id").textContent = state.roomId || "—";
    $("#waiting-stake").textContent = money(state.roomStake);
    $("#waiting-player-count").textContent = `${state.players.length}/8`;
    const seats = $("#waiting-seats");
    seats.innerHTML = "";
    const players = state.players.slice(0, 8);
    for (let i = 0; i < 8; i++) {
      const p = players[i];
      const seat = document.createElement("div");
      seat.className = `waiting-seat ${p ? "occupied" : ""} ${p && p.connection_id === state.connectionId && state.ready ? "ready" : ""}`;
      seat.innerHTML = p
        ? `<div class="seat-avatar">${escapeHtml((p.name || "?")[0].toUpperCase())}</div><span>${escapeHtml(p.name)}${p.connection_id === state.connectionId ? " (YOU)" : ""}</span>${p.connection_id === state.connectionId && state.ready ? "<em>READY</em>" : ""}`
        : `<div class="seat-avatar">+</div><span>Waiting...</span>`;
      seats.appendChild(seat);
    }
  }

  function enterGameFromState(gameState) {
    setPage("game");
    renderGameState(gameState);
  }

  function renderGameState(game) {
    state.game = game;
    state.players = game.players || state.players;
    const me = state.players.find(p => p.connection_id === state.connectionId);
    if (me && me.balance != null) $("#top-balance").textContent = Number(me.balance).toLocaleString("en-US");

    $("#game-phase").textContent = String(game.state || "waiting").toUpperCase();
    $("#room-label").textContent = state.roomId ? `ROOM ${state.roomId}` : "ROOM";
    $("#start-round-btn").classList.toggle("hidden", !(me && me.is_dealer && ["waiting","reveal"].includes(game.state)));

    renderTable(state.players, me);
    renderOwnHand(me);
    renderControls(game, me);
  }

  function renderTable(players, me) {
    const container = $("#game-seats");
    container.innerHTML = "";
    const others = players.filter(p => !me || p.connection_id !== me.connection_id).slice(0, 6);
    const positions = ["seat-pos-1","seat-pos-2","seat-pos-3","seat-pos-4","seat-pos-5","seat-pos-6"];

    const dealer = players.find(p => p.is_dealer);
    $("#dealer-seat").innerHTML = dealer ? playerBadge(dealer, true) : "";

    others.forEach((p, i) => {
      const seat = document.createElement("div");
      seat.className = `game-seat ${positions[i] || positions[5]}`;
      seat.innerHTML = playerBadge(p, false);
      container.appendChild(seat);
    });

    const pot = players.reduce((sum, p) => sum + Number(p.current_bet || 0), 0);
    $("#pot-value").textContent = money(pot);
    $("#center-chips").innerHTML = players.filter(p => p.has_bet && Number(p.current_bet) > 0)
      .map(p => `<div class="chip" title="${escapeAttr(p.name)}">${Number(p.current_bet)}</div>`).join("");
  }

  function playerBadge(p, dealer = false) {
    const status = p.status || "waiting";
    const cards = [];
    const count = Number(p.card_count || 0);
    for (let i = 0; i < count; i++) cards.push(`<div class="mini-card back">?</div>`);
    return `<div class="player-badge ${status === "thinking" ? "is-turn" : ""} ${status === "pok" ? "is-pok" : ""}">
      <div class="mini-avatar">${escapeHtml((p.name || "?")[0].toUpperCase())}</div>
      <div class="player-name">${escapeHtml(p.name || "Player")}${dealer ? " ♛" : ""}</div>
      <div class="player-balance">${money(p.balance)}</div>
      <div class="status-tag ${escapeAttr(status)}">${statusLabels[status] || status}</div>
      ${cards.length ? `<div class="seat-cards">${cards.join("")}</div>` : ""}
    </div>`;
  }

  function renderOwnHand(me) {
    const hand = me && Array.isArray(me.hand) ? me.hand : [];
    $("#my-hand").innerHTML = hand.length
      ? hand.map((c, i) => cardHtml(c, i)).join("")
      : `<div class="muted small" style="align-self:center">Your cards will appear here.</div>`;
    $("#my-status").textContent = me ? statusLabels[me.status] || me.status || "Waiting..." : "Waiting...";
    $("#my-balance-label").textContent = me ? money(me.balance) : "฿0";
  }

  function cardHtml(card, index) {
    const suit = card.suit || "";
    const symbol = {Heart:"♥",Diamond:"♦",Club:"♣",Spade:"♠"}[suit] || suit;
    const red = suit === "Heart" || suit === "Diamond";
    return `<div class="playing-card ${red ? "red" : ""} deal" style="animation-delay:${index * 90}ms">${escapeHtml(card.rank || "?")}<span>${symbol}</span></div>`;
  }

  function renderControls(game, me) {
    const betting = game.state === "betting" && me && !me.is_dealer && !me.has_bet && me.status !== "out_of_money";
    $("#betting-section").classList.toggle("hidden", !betting);
    $("#action-buttons").classList.toggle("hidden", !(me && me.status === "thinking"));

    if (betting) {
      const slider = $("#bet-slider");
      slider.max = Math.max(1, Number(me.balance || 0));
      slider.step = Math.max(1, Math.round(Number(me.balance || 100) * .05));
      if (Number(slider.value) > Number(slider.max)) slider.value = slider.max;
      updateBetDisplay();
    }
  }

  function updateBetDisplay() {
    $("#bet-amount-display").textContent = money($("#bet-slider").value);
  }

  function goBackLobby() {
    // The current server does not expose a leave_room message.
    // This only changes the UI; reconnecting is required to truly leave.
    state.roomId = null;
    state.game = null;
    state.players = [];
    setPage("home");
    renderRooms();
    showToast("Returned to lobby");
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;" }[c]));
  }
  function escapeAttr(value) { return escapeHtml(value); }

  // ---------- events ----------
  document.addEventListener("DOMContentLoaded", () => {
    $("#server-address-input").placeholder = window.location.hostname || "Leave blank for LAN";

    $("#connect-btn").addEventListener("click", connect);
    $("#player-name-input").addEventListener("keydown", e => { if (e.key === "Enter") connect(); });

    $$(".nav-item").forEach(btn => btn.addEventListener("click", () => setPage(btn.dataset.nav)));
    $$("[data-nav]").forEach(btn => {
      if (!btn.classList.contains("nav-item")) btn.addEventListener("click", () => setPage(btn.dataset.nav));
    });

    $$("[data-action='create']").forEach(btn => btn.addEventListener("click", openCreateModal));
    $$("[data-action='quick-play']").forEach(btn => btn.addEventListener("click", () => {
      const rooms = getRooms().filter(r => r.player_count < r.max_players);
      if (rooms[0]) joinRoom(rooms[0].room_id);
      else showToast("No open table found.");
    }));
    $$("[data-action='back-lobby']").forEach(btn => btn.addEventListener("click", goBackLobby));
    $$("[data-close-modal]").forEach(btn => btn.addEventListener("click", closeCreateModal));
    $("#create-modal").addEventListener("click", e => { if (e.target.id === "create-modal") closeCreateModal(); });

    $$(".stake-btn").forEach(btn => btn.addEventListener("click", () => {
      $$(".stake-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.selectedStake = Number(btn.dataset.stake);
      $("#stake-custom-input").value = "";
    }));
    $("#stake-custom-input").addEventListener("input", e => {
      const n = Number(e.target.value);
      if (n > 0) {
        state.selectedStake = n;
        $$(".stake-btn").forEach(b => b.classList.remove("active"));
      }
    });
    $("#create-room-btn").addEventListener("click", createRoom);

    $$("#room-tabs .tab").forEach(tab => tab.addEventListener("click", () => {
      $$("#room-tabs .tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      state.roomFilter = tab.dataset.filter;
      renderRooms();
    }));
    $("#room-search").addEventListener("input", e => { state.search = e.target.value; renderRooms(); });

    $("#ready-btn").addEventListener("click", () => {
      state.ready = !state.ready;
      $("#ready-btn").textContent = state.ready ? "✓ READY" : "READY";
      $("#ready-btn").classList.toggle("btn-green", state.ready);
      renderWaiting();
      showToast(state.ready ? "You are ready" : "Ready cancelled");
    });

    $("#bet-slider").addEventListener("input", updateBetDisplay);
    $("#place-bet-btn").addEventListener("click", () => {
      const amount = Number($("#bet-slider").value);
      if (amount > 0) GameSocket.send("place_bet", { amount });
    });
    $("#draw-btn").addEventListener("click", () => GameSocket.send("player_draw", {}));
    $("#stay-btn").addEventListener("click", () => GameSocket.send("player_stay", {}));
    $("#start-round-btn").addEventListener("click", () => GameSocket.send("start_round", {}));

    $("#coin-plus").addEventListener("click", () => showToast("Coin shop is a UI placeholder."));
    $("#sound-toggle").addEventListener("click", () => {
      state.sound = !state.sound;
      $("#sound-toggle").textContent = state.sound ? "♫" : "×";
    });
    $$(".toggle").forEach(toggle => toggle.addEventListener("click", () => toggle.classList.toggle("on")));

    renderRooms();

    // Room list from the real server
    GameSocket.on("room_list", message => {
      state.rooms = message.data || [];
      renderRooms();
    });

    GameSocket.on("room_joined", message => {
      state.connectionId = message.connection_id;
      state.roomId = message.room_id;
      state.roomStake = message.stake || state.roomStake;
      state.ready = false;
      renderWaiting();

      // Existing backend has no separate ready phase, so show the waiting screen briefly.
      setPage("waiting");
      $("#waiting-countdown").textContent = "—";
      showToast(`Joined ${state.roomId}`);
    });

    GameSocket.on("game_state", message => {
      enterGameFromState(message.data);
    });

    GameSocket.on("round_result", message => {
      // The next game_state contains the authoritative balances/cards.
      if (message.data) {
        showToast("Round complete");
      }
    });

    GameSocket.on("error", message => {
      const text = message.message || "Server error";
      $("#lobby-error").textContent = text;
      showToast(text);
    });

    // If a room is joined and the server sends game_state immediately,
    // the game screen takes over automatically.
  });
})();
