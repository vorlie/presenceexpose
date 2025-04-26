const wsUrlInput = document.getElementById("ws-url");
const connectBtn = document.getElementById("connect-btn");
const statusIndicator = document.getElementById("status-indicator");
const connectionStatus = document.getElementById("connection-status");
const subscribeControls = document.getElementById("subscribe-controls");
const userIdsInput = document.getElementById("user-ids");
const subscribeBtn = document.getElementById("subscribe-btn");
const presenceDisplay = document.getElementById("presence-display");

let websocket = null;
// --- Heartbeat variables ---
let heartbeatIntervalId = null;
let serverHeartbeatIntervalMs = null;
// -------------------------

// --- WebSocket OP Codes ---
const OP_EVENT = 0;
const OP_HELLO = 1;
const OP_INITIALIZE = 2; // Client sends this to subscribe
const OP_HEARTBEAT = 3; // Client sends this as ACK or keepalive

// --- Connection Handling ---

function connectWebSocket() {
  const url = wsUrlInput.value.trim();
  if (!url) {
    alert("Please enter a WebSocket URL.");
    return;
  }
  if (!url.startsWith("ws://") && !url.startsWith("wss://")) {
    alert("Invalid WebSocket URL. Must start with ws:// or wss://");
    return;
  }

  if (
    websocket &&
    (websocket.readyState === WebSocket.OPEN ||
      websocket.readyState === WebSocket.CONNECTING)
  ) {
    console.log("WebSocket is already open or connecting.");
    return;
  }

  console.log(`Attempting to connect to ${url}...`);
  updateStatus("Connecting", "connecting");
  wsUrlInput.disabled = true;
  connectBtn.disabled = true;

  websocket = new WebSocket(url);

  websocket.onopen = () => {
    console.log("WebSocket connection established.");
    updateStatus("Connected", "connected");
    connectBtn.textContent = "Disconnect";
    connectBtn.classList.add("disconnect");
    subscribeControls.style.display = "flex";
    connectBtn.disabled = false;
  };

  websocket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      // console.log('Message received:', message);

      switch (message.op) {
        case OP_HELLO:
          const interval = message.d?.heartbeat_interval;
          if (interval) {
            console.log(`Received HELLO, heartbeat interval: ${interval}ms`);
            serverHeartbeatIntervalMs = interval;
            // --- Start sending heartbeats periodically ---
            startHeartbeat();
            // -----------------------------------------
          } else {
            console.warn("HELLO message received without heartbeat_interval.");
          }
          break;
        case OP_EVENT:
          if (message.t === "INIT_STATE" || message.t === "PRESENCE_UPDATE") {
            if (
              message.d &&
              message.d.discord_user &&
              message.d.discord_user.id
            ) {
              updatePresenceDisplay(message.d.discord_user.id, message.d);
            } else {
              console.warn("Received event without user ID:", message.d);
            }
          }
          break;
        default:
          console.log("Received message with unknown OP code:", message.op);
      }
    } catch (error) {
      console.error(
        "Failed to parse message or handle incoming data:",
        error,
        event.data
      );
    }
  };

  websocket.onerror = (error) => {
    console.error("WebSocket Error:", error);
    updateStatus("Error", "error");
    // --- Stop heartbeat on error too ---
    stopHeartbeat();
    // -----------------------------------
    connectBtn.disabled = false;
    wsUrlInput.disabled = false;
  };

  websocket.onclose = (event) => {
    console.log("WebSocket connection closed.", event.code, event.reason);
    updateStatus(`Disconnected (${event.code})`, "disconnected");
    connectBtn.textContent = "Connect";
    connectBtn.classList.remove("disconnect");
    subscribeControls.style.display = "none";
    websocket = null;
    wsUrlInput.disabled = false;
    connectBtn.disabled = false;
    // --- Stop heartbeat on close ---
    stopHeartbeat();
    serverHeartbeatIntervalMs = null;
    // -----------------------------
    // presenceDisplay.innerHTML = '<p>Connection closed. Data might be stale.</p>';
  };
}

function disconnectWebSocket() {
  stopHeartbeat();
  // ---------------------------------------
  if (websocket && websocket.readyState === WebSocket.OPEN) {
    console.log("Closing WebSocket connection...");
    websocket.close(1000, "Client initiated disconnect");
  } else {
    console.log("WebSocket is not connected.");
    updateStatus("Disconnected", "disconnected");
    connectBtn.textContent = "Connect";
    connectBtn.classList.remove("disconnect");
    subscribeControls.style.display = "none";
    websocket = null;
    wsUrlInput.disabled = false;
    connectBtn.disabled = false;
  }
}

function updateStatus(text, className) {
  connectionStatus.textContent = text;
  statusIndicator.className = "";
  statusIndicator.classList.add(className);
}

// --- Subscription Handling ---

function subscribeToUsers() {
  if (!websocket || websocket.readyState !== WebSocket.OPEN) {
    alert("WebSocket is not connected.");
    return;
  }
  const idsString = userIdsInput.value.trim();
  if (!idsString) {
    alert("Please enter User IDs to subscribe to.");
    return;
  }
  const userIds = idsString
    .split(",")
    .map((id) => id.trim())
    .filter((id) => /^\d+$/.test(id));
  if (userIds.length === 0) {
    alert("No valid numeric User IDs found.");
    return;
  }
  console.log(`Subscribing to User IDs: ${userIds.join(", ")}`);
  const message = {
    op: OP_INITIALIZE,
    d: {
      subscribe_to_ids: userIds,
    },
  };
  websocket.send(JSON.stringify(message));
  presenceDisplay.innerHTML = "";
  userIds.forEach((id) => {
    updatePresenceDisplay(id, null);
  });
}

// --- Display Logic ---

function updatePresenceDisplay(userId, data) {
  let card = document.getElementById(`user-${userId}`);
  if (!card) {
    card = document.createElement("div");
    card.classList.add("presence-card");
    card.id = `user-${userId}`;
    presenceDisplay.appendChild(card);
  }
  if (!data) {
    card.innerHTML = `<h3>User ID: ${userId}</h3><p><i>Waiting for data...</i></p>`;
    return;
  }
  const user = data.discord_user;
  const avatarUrl =
    user.avatar || "https://cdn.discordapp.com/embed/avatars/0.png";
  let activitiesHtml = "<p>No activities.</p>";
  if (data.activities && data.activities.length > 0) {
    activitiesHtml = '<ul class="activities-list">';
    data.activities.forEach((act) => {
      if (act.name === "Spotify" && data.spotify) return;
      activitiesHtml += `<li><strong>${escapeHtml(
        act.name || "Unknown Activity"
      )}</strong>`;
      if (act.details) activitiesHtml += `<br/>${escapeHtml(act.details)}`;
      if (act.state) activitiesHtml += `<br/><em>${escapeHtml(act.state)}</em>`;
      activitiesHtml += "</li>";
    });
    activitiesHtml += "</ul>";
  }
  let spotifyHtml = "";
  if (data.spotify) {
    spotifyHtml = `
            <div class="spotify-info">
                <strong>Listening to Spotify</strong>
                ${escapeHtml(data.spotify.details || "Unknown Title")}<br>
                by ${escapeHtml(data.spotify.state || "Unknown Artist")}<br>
                on ${escapeHtml(data.spotify.album || "Unknown Album")}
            </div>
        `;
  }
  card.innerHTML = `
        <h3>
            <img src="${escapeHtml(
              avatarUrl
            )}" alt="Avatar" width="32" height="32">
            ${escapeHtml(user.username)}#${escapeHtml(user.discriminator)}
            (${user.id})
        </h3>
        <p>Status: <span class="status ${escapeHtml(
          data.discord_status
        )}">${escapeHtml(data.discord_status)}</span></p>
        <p>Platform: ${data.client_status?.desktop ? "Desktop " : ""}${
    data.client_status?.mobile ? "Mobile " : ""
  }${data.client_status?.web ? "Web " : ""}</p>
        <h4>Activities:</h4>
        ${activitiesHtml}
        ${spotifyHtml}
    `;
}

function escapeHtml(unsafe) {
  if (!unsafe) return "";
  return unsafe
    .toString()
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// --- Heartbeat Functions ---
function startHeartbeat() {
  stopHeartbeat();
  if (!serverHeartbeatIntervalMs || serverHeartbeatIntervalMs <= 0) {
    console.warn(
      "Invalid heartbeat interval received from server. Cannot start heartbeat."
    );
    return;
  }

  console.log(
    `Starting client heartbeat every ${serverHeartbeatIntervalMs}ms.`
  );
  heartbeatIntervalId = setInterval(() => {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      console.debug("Sending heartbeat (OP 3)");
      websocket.send(JSON.stringify({ op: OP_HEARTBEAT }));
    } else {
      console.warn("WebSocket not open, stopping heartbeat.");
      stopHeartbeat();
    }
  }, serverHeartbeatIntervalMs);
}

function stopHeartbeat() {
  if (heartbeatIntervalId) {
    console.log("Stopping client heartbeat.");
    clearInterval(heartbeatIntervalId);
    heartbeatIntervalId = null;
  }
}
// -------------------------

// --- Event Listeners ---
connectBtn.addEventListener("click", () => {
  if (
    !websocket ||
    websocket.readyState === WebSocket.CLOSED ||
    websocket.readyState === WebSocket.CLOSING
  ) {
    connectWebSocket();
  } else {
    disconnectWebSocket();
  }
});
subscribeBtn.addEventListener("click", subscribeToUsers);

// --- Initial State ---
updateStatus("Disconnected", "disconnected");
