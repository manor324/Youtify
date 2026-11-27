const state = {
  spotify: { connected: false, configured: false, user: null, message: "" },
  ytmusic: { connected: false, message: "" },
  playlists: [],
  likedTotal: 0,
  libraryLoaded: false,
  activeEventSource: null,
};

document.addEventListener("DOMContentLoaded", () => {
  const delayInput = document.getElementById("range-delay");
  const delayLabel = document.getElementById("label-delay");
  delayInput.addEventListener("input", () => {
    delayLabel.textContent = `${parseFloat(delayInput.value).toFixed(1)}s`;
  });

  refreshStatus();
});

function showToast(message, isError = true) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.className = `fixed bottom-5 right-5 max-w-sm px-4 py-3 rounded-xl shadow-2xl text-xs z-50 border ${
    isError
      ? "bg-zinc-900 border-rose-500/40 text-rose-200"
      : "bg-zinc-900 border-emerald-500/40 text-emerald-200"
  }`;
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), 4500);
}

async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    state.spotify = data.spotify;
    state.ytmusic = data.ytmusic;
    renderStatusPills();
  } catch (err) {
    showToast("Could not reach backend server.");
  }
}

function renderStatusPills() {
  const dotSp = document.getElementById("dot-spotify");
  const lblSp = document.getElementById("label-spotify");
  if (state.spotify.connected) {
    dotSp.className = "w-2 h-2 rounded-full bg-emerald-400";
    lblSp.textContent = `Spotify: ${state.spotify.user}`;
  } else {
    dotSp.className = "w-2 h-2 rounded-full bg-amber-400";
    lblSp.textContent = state.spotify.configured ? "Spotify: Click to Connect" : "Spotify: Missing .env";
  }

  const dotYt = document.getElementById("dot-ytm");
  const lblYt = document.getElementById("label-ytm");
  if (state.ytmusic.connected) {
    dotYt.className = "w-2 h-2 rounded-full bg-emerald-400";
    lblYt.textContent = "YT Music: Connected";
  } else {
    dotYt.className = "w-2 h-2 rounded-full bg-rose-500";
    lblYt.textContent = "YT Music: Click to Setup";
  }
}

function switchTab(tab) {
  const panelUrl = document.getElementById("panel-url");
  const panelLib = document.getElementById("panel-library");
  const tabUrl = document.getElementById("tab-url");
  const tabLib = document.getElementById("tab-library");

  if (tab === "url") {
    panelUrl.classList.remove("hidden");
    panelLib.classList.add("hidden");
    tabUrl.className = "px-3.5 py-1.5 rounded-lg text-xs font-medium transition bg-zinc-800 text-white";
    tabLib.className = "px-3.5 py-1.5 rounded-lg text-xs font-medium transition text-zinc-400 hover:text-zinc-200";
  } else {
    panelUrl.classList.add("hidden");
    panelLib.classList.remove("hidden");
    tabLib.className = "px-3.5 py-1.5 rounded-lg text-xs font-medium transition bg-zinc-800 text-white";
    tabUrl.className = "px-3.5 py-1.5 rounded-lg text-xs font-medium transition text-zinc-400 hover:text-zinc-200";
    if (state.spotify.connected && !state.libraryLoaded) {
      loadLibrary();
    }
  }
}

// --- Modals & Auth ---

function openSpotifyModal() {
  const msg = document.getElementById("modal-spotify-msg");
  msg.textContent = state.spotify.connected
    ? `Currently connected as ${state.spotify.user}. You can re-authorize below if needed.`
    : state.spotify.message || "Connect your Spotify account.";
  document.getElementById("modal-spotify").classList.remove("hidden");
}

function openYtmModal() {
  const msg = document.getElementById("modal-ytm-msg");
  msg.textContent = state.ytmusic.connected
    ? `Currently connected (${state.ytmusic.auth_file}). You can update credentials below.`
    : state.ytmusic.message || "YouTube Music credentials required.";
  document.getElementById("modal-ytm").classList.remove("hidden");
}

function closeModals() {
  document.getElementById("modal-spotify").classList.add("hidden");
  document.getElementById("modal-ytm").classList.add("hidden");
}

async function openSpotifyLoginUrl() {
  try {
    const res = await fetch("/api/auth/spotify/url");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to generate URL");
    window.open(data.url, "_blank", "noopener,noreferrer");
  } catch (err) {
    showToast(err.message);
  }
}

async function submitSpotifyCallback() {
  const redirectUrl = document.getElementById("input-spotify-callback").value.trim();
  if (!redirectUrl) {
    showToast("Paste the redirected URL first.");
    return;
  }
  try {
    const res = await fetch("/api/auth/spotify/callback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ redirect_url: redirectUrl }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Authorization failed");
    state.spotify = data;
    renderStatusPills();
    closeModals();
    showToast(`Spotify connected as ${data.user}!`, false);
  } catch (err) {
    showToast(err.message);
  }
}

async function submitYtmHeaders() {
  const headersRaw = document.getElementById("input-ytm-headers").value.trim();
  if (!headersRaw) {
    showToast("Paste your request headers first.");
    return;
  }
  try {
    const res = await fetch("/api/auth/ytmusic/browser", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ headers_raw: headersRaw }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to save headers");
    state.ytmusic = data;
    renderStatusPills();
    closeModals();
    showToast("YouTube Music connected via browser.json!", false);
  } catch (err) {
    showToast(err.message);
  }
}

// --- Playlist Preview & Library ---

async function previewPlaylist() {
  const playlistInput = document.getElementById("input-playlist-url").value.trim();
  if (!playlistInput) {
    showToast("Enter a Spotify playlist link or ID.");
    return;
  }

  try {
    const res = await fetch("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ playlist: playlistInput }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not preview playlist");

    const card = document.getElementById("preview-card");
    const img = document.getElementById("preview-img");
    document.getElementById("preview-name").textContent = data.name;
    document.getElementById("preview-meta").textContent = `By ${data.owner} • ${data.track_count} tracks`;
    document.getElementById("preview-desc").textContent = data.description || "";
    if (data.image_url) {
      img.src = data.image_url;
      img.classList.remove("hidden");
    } else {
      img.classList.add("hidden");
    }
    card.classList.remove("hidden");
  } catch (err) {
    showToast(err.message);
  }
}

async function loadLibrary() {
  const grid = document.getElementById("playlists-grid");
  grid.innerHTML = `<div class="col-span-full text-center py-8 text-xs text-zinc-400">Loading your Spotify library...</div>`;

  try {
    const res = await fetch("/api/playlists");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to load playlists");

    state.playlists = data.playlists || [];
    state.likedTotal = data.liked_total || 0;
    state.libraryLoaded = true;
    document.getElementById("liked-count-label").textContent = `${state.likedTotal} saved tracks`;
    renderPlaylists();
  } catch (err) {
    grid.innerHTML = "";
    const msg = document.createElement("div");
    msg.className = "col-span-full text-center py-8 text-xs text-rose-400";
    msg.textContent = err.message;
    grid.appendChild(msg);
  }
}

function renderPlaylists() {
  const grid = document.getElementById("playlists-grid");
  const filterText = document.getElementById("input-filter-playlists").value.trim().toLowerCase();
  const filtered = state.playlists.filter((p) => p.name.toLowerCase().includes(filterText));

  grid.innerHTML = "";
  if (filtered.length === 0) {
    const empty = document.createElement("div");
    empty.className = "col-span-full text-center py-8 text-xs text-zinc-500";
    empty.textContent = "No matching playlists found.";
    grid.appendChild(empty);
    return;
  }

  for (const p of filtered) {
    const card = document.createElement("div");
    card.className = "bg-zinc-950/80 border border-zinc-800/90 hover:border-zinc-700 rounded-xl p-3 flex items-center gap-3 transition";

    if (p.image_url) {
      const img = document.createElement("img");
      img.src = p.image_url;
      img.alt = p.name;
      img.className = "w-12 h-12 rounded-lg object-cover shrink-0 bg-zinc-800";
      card.appendChild(img);
    } else {
      const placeholder = document.createElement("div");
      placeholder.className = "w-12 h-12 rounded-lg bg-zinc-800 flex items-center justify-center text-zinc-500 text-xs font-mono shrink-0";
      placeholder.textContent = "PL";
      card.appendChild(placeholder);
    }

    const info = document.createElement("div");
    info.className = "min-w-0 flex-1";
    const title = document.createElement("div");
    title.className = "text-xs font-semibold text-zinc-100 truncate";
    title.textContent = p.name;
    const meta = document.createElement("div");
    meta.className = "text-[11px] text-zinc-400 mt-0.5";
    meta.textContent = `${p.track_count} tracks`;
    info.appendChild(title);
    info.appendChild(meta);
    card.appendChild(info);

    const btn = document.createElement("button");
    btn.className = "px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-emerald-500/15 hover:bg-emerald-500 text-emerald-300 hover:text-zinc-950 border border-emerald-500/30 transition shrink-0";
    btn.textContent = "Transfer";
    btn.addEventListener("click", () => startTransfer({ mode: "playlist", playlist: p.id }));
    card.appendChild(btn);

    grid.appendChild(card);
  }
}

// --- Migration Execution & SSE Streaming ---

function startUrlTransfer() {
  const playlist = document.getElementById("input-playlist-url").value.trim();
  if (!playlist) {
    showToast("Paste a Spotify playlist URL or ID first.");
    return;
  }
  const customName = document.getElementById("input-custom-name").value.trim();
  startTransfer({
    mode: "playlist",
    playlist,
    custom_name: customName || null,
  });
}

async function startTransfer(payload) {
  if (!state.spotify.connected) {
    openSpotifyModal();
    showToast("Connect Spotify first.");
    return;
  }
  if (!state.ytmusic.connected) {
    openYtmModal();
    showToast("Connect YouTube Music first.");
    return;
  }

  if (state.activeEventSource) {
    state.activeEventSource.close();
    state.activeEventSource = null;
  }

  const privacy = document.getElementById("select-privacy").value;
  const delay = parseFloat(document.getElementById("range-delay").value);

  const progressSection = document.getElementById("progress-section");
  const trackLog = document.getElementById("track-log");
  const summaryBanner = document.getElementById("summary-banner");
  const openYtmLink = document.getElementById("link-open-ytm");
  const failedLink = document.getElementById("link-failed-tracks");

  progressSection.classList.remove("hidden");
  summaryBanner.classList.add("hidden");
  openYtmLink.classList.add("hidden");
  failedLink.classList.add("hidden");
  trackLog.innerHTML = "";
  updateProgressBar(0, "Starting job...", "Connecting to Spotify & YouTube Music");

  progressSection.scrollIntoView({ behavior: "smooth", block: "nearest" });

  try {
    const res = await fetch("/api/transfer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, privacy, delay }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not start transfer");

    subscribeToJob(data.job_id);
  } catch (err) {
    showToast(err.message);
    updateProgressBar(0, "Transfer failed to start", err.message);
  }
}

function subscribeToJob(jobId) {
  const es = new EventSource(`/api/transfer/${jobId}/stream`);
  state.activeEventSource = es;

  es.onmessage = (event) => {
    const evt = JSON.parse(event.data);
    handleJobEvent(evt);
  };

  es.addEventListener("end", () => {
    es.close();
    if (state.activeEventSource === es) {
      state.activeEventSource = null;
    }
  });

  es.onerror = () => {
    es.close();
    if (state.activeEventSource === es) {
      state.activeEventSource = null;
    }
  };
}

function updateProgressBar(percent, title, subtitle) {
  const pct = Math.max(0, Math.min(100, Math.round(percent)));
  document.getElementById("progress-bar").style.width = `${pct}%`;
  document.getElementById("progress-counter").textContent = `${pct}%`;
  if (title !== null) document.getElementById("progress-title").textContent = title;
  if (subtitle !== null) document.getElementById("progress-subtitle").textContent = subtitle;
}

function appendLog(symbol, text, colorClass) {
  const log = document.getElementById("track-log");
  const row = document.createElement("div");
  row.className = `flex items-start gap-2 py-0.5 ${colorClass}`;

  const icon = document.createElement("span");
  icon.className = "shrink-0";
  icon.textContent = symbol;

  const msg = document.createElement("span");
  msg.className = "break-all";
  msg.textContent = text;

  row.appendChild(icon);
  row.appendChild(msg);
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
}

function handleJobEvent(evt) {
  switch (evt.type) {
    case "status":
      updateProgressBar(0, "Preparing...", evt.message);
      appendLog("...", evt.message, "text-zinc-400");
      break;

    case "batch_playlist":
      updateProgressBar(0, `Batch [${evt.index}/${evt.total_playlists}]: ${evt.name}`, "Starting next playlist...");
      appendLog(">>", `Playlist [${evt.index}/${evt.total_playlists}]: ${evt.name}`, "text-indigo-300 font-semibold pt-2");
      break;

    case "playlist_created":
      updateProgressBar(0, `Transferring: ${evt.name}`, `Created YouTube playlist (${evt.total} songs)`);
      appendLog("[+]", `Created YT playlist '${evt.name}' (${evt.playlist_id})`, "text-emerald-300");
      break;

    case "track": {
      const pct = evt.total > 0 ? (evt.index / evt.total) * 100 : 100;
      updateProgressBar(pct, null, `Processed ${evt.index} of ${evt.total} songs`);
      if (evt.status === "added") {
        appendLog("[ok]", `[${evt.index}/${evt.total}] ${evt.title} - ${evt.artist}`, "text-emerald-400/90");
      } else {
        appendLog("[--]", `[${evt.index}/${evt.total}] ${evt.title} - ${evt.artist} (${evt.error || "Failed"})`, "text-rose-400/90");
      }
      break;
    }

    case "retry_start":
      updateProgressBar(95, "Retrying failed tracks...", `Attempting fallback title search for ${evt.count} song(s)`);
      appendLog("[..]", `Retrying ${evt.count} unmatched track(s)...`, "text-amber-300 pt-1");
      break;

    case "retry_track":
      if (evt.status === "added") {
        appendLog("[ok]", `[Retry ${evt.index}/${evt.total}] Recovered: ${evt.title}`, "text-emerald-300");
      } else {
        appendLog("[--]", `[Retry ${evt.index}/${evt.total}] Still not found: ${evt.title}`, "text-rose-400");
      }
      break;

    case "complete": {
      updateProgressBar(100, "Transfer Complete", `${evt.added} of ${evt.total} songs added`);
      const summary = document.getElementById("summary-banner");
      const headline = document.getElementById("summary-headline");
      const stats = document.getElementById("summary-stats");
      const openLink = document.getElementById("link-open-ytm");
      const failedLink = document.getElementById("link-failed-tracks");

      const failedCount = (evt.failed || []).length;
      headline.textContent = failedCount === 0 ? "All tracks transferred." : "Transfer finished with some unmatched tracks.";
      headline.className = failedCount === 0 ? "text-sm font-semibold text-emerald-400" : "text-sm font-semibold text-amber-300";
      stats.textContent = `Added: ${evt.added} | Failed: ${failedCount} | Total: ${evt.total}`;

      if (evt.playlist_id) {
        openLink.href = `https://music.youtube.com/playlist?list=${encodeURIComponent(evt.playlist_id)}`;
        openLink.classList.remove("hidden");
      }
      if (failedCount > 0) {
        failedLink.classList.remove("hidden");
      }
      summary.classList.remove("hidden");
      break;
    }

    case "batch_complete":
      updateProgressBar(100, "All Playlists Migrated", `Processed ${evt.playlists.length} playlist(s)`);
      appendLog("[done]", `Batch migration finished (${evt.playlists.length} playlists).`, "text-emerald-300 font-semibold pt-1");
      break;

    case "error":
      appendLog("[err]", evt.message, "text-rose-400 font-semibold");
      showToast(evt.message);
      updateProgressBar(0, "Transfer Error", evt.message);
      break;
  }
}
