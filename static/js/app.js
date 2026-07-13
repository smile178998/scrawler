/* Modern Web Scraper — Frontend */

let currentResult = null;
let isRunning = false;
let scrapeStartedAt = 0;
let pingTimer = null;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const urlInput = $("#url-input");
const scrapeBtn = $("#scrape-btn");
const progressBar = $("#progress-bar");
const statusText = $("#status-text");
const optionsToggle = $("#options-toggle");
const optionsBody = $("#options-body");

optionsToggle.addEventListener("click", () => {
  const open = optionsBody.classList.toggle("open");
  optionsToggle.setAttribute("aria-expanded", open);
});

$$(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".tab").forEach((t) => t.classList.remove("active"));
    $$(".tab-panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    $(`#panel-${tab.dataset.tab}`).classList.add("active");
  });
});

scrapeBtn.addEventListener("click", startScrape);
urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") startScrape();
});

function clamp(value, min, max, fallback) {
  const num = Number.parseInt(value, 10);
  if (Number.isNaN(num)) return fallback;
  return Math.min(max, Math.max(min, num));
}

function needsProxyHint(url) {
  return /youtube\.com|youtu\.be|googlevideo\.com|twitter\.com|(?:^|\.)x\.com|facebook\.com|instagram\.com/i.test(
    url || ""
  );
}

function isVideoPlatformUrl(url) {
  return /bilibili\.com|b23\.tv|youtube\.com|youtu\.be|vimeo\.com|tiktok\.com|douyin\.com|twitch\.tv|dailymotion\.com|nicovideo\.jp|(?:^|\.)twitter\.com|(?:^|\.)x\.com/i.test(
    url || ""
  );
}

function isBilibiliUrl(url) {
  return /bilibili\.com|b23\.tv/i.test(url || "");
}

function applyCommonPresets(url) {
  if (!url) return;
  $("#use-saved-profile").checked = true;
  $("#download-media").checked = true;
  if ($("#headless-mode").value === "hidden") {
    $("#headless-mode").value = "auto";
  }
}

function applyVideoPresets(url) {
  applyCommonPresets(url);
  if (!isVideoPlatformUrl(url)) return;
  if (clamp(fieldValue("wait-ms", "3500"), 500, 30000, 3500) < 7000) {
    const waitEl = document.getElementById("wait-ms");
    if (waitEl) waitEl.value = 8000;
  }
  const autoSel = document.getElementById("auto-selector");
  const autoAi = document.getElementById("auto-selector-ai");
  if (autoSel) autoSel.checked = false;
  if (autoAi) autoAi.checked = false;
}

function fieldChecked(id, fallback = true) {
  const el = document.getElementById(id);
  return el ? el.checked : fallback;
}

function fieldValue(id, fallback = "") {
  const el = document.getElementById(id);
  return el ? el.value.trim() : fallback;
}

function buildRequestBody() {
  return {
    url: urlInput.value.trim(),
    text_selector: fieldValue("text-sel"),
    comment_selector: fieldValue("comment-sel"),
    cookie: fieldValue("cookie"),
    proxy: fieldValue("proxy"),
    wait_ms: clamp(fieldValue("wait-ms", "3500"), 500, 30000, 3500),
    scroll: fieldChecked("scroll", true),
    use_chrome: fieldChecked("use-chrome", true),
    headless: fieldValue("headless-mode", "auto") || "auto",
    max_retries: clamp(fieldValue("max-retries", "2"), 0, 4, 2),
    simulate_human: fieldChecked("simulate-human", true),
    block_resources: fieldChecked("block-resources", false),
    auto_selector: fieldChecked("auto-selector", true),
    auto_selector_ai: fieldChecked("auto-selector-ai", true),
    download_media: fieldChecked("download-media", true),
    use_saved_profile: fieldChecked("use-saved-profile", true),
    ai_api_key: fieldValue("ai-api-key"),
    ai_base_url: fieldValue("ai-base-url"),
    ai_model: fieldValue("ai-model"),
  };
}

function formatApiError(payload) {
  if (Array.isArray(payload.details) && payload.details.length) {
    return payload.details.join("; ");
  }
  return payload.error || payload.detail || "Request failed";
}

function processSseLine(line, onEvent) {
  if (!line.startsWith("data: ")) return;
  try {
    onEvent(JSON.parse(line.slice(6)));
  } catch (_) {
    /* ignore malformed chunks */
  }
}

async function startScrape() {
  const url = urlInput.value.trim();
  if (!url) {
    urlInput.focus();
    setStatus("Please enter a target URL");
    return;
  }
  if (isRunning) return;

  isRunning = true;
  scrapeStartedAt = Date.now();
  setBusy(true);
  startPingTimer();
  clearResults(false);
  appendLog(`▶  Target: ${url}\n\n`);
  appendLog("⏳  Starting browser — visible mode may take 30-90s, watch the Log tab …\n");
  switchToTab("log");

  applyCommonPresets(url);
  applyVideoPresets(url);
  if (needsProxyHint(url) && fieldValue("proxy")) {
    appendLog("ℹ  Proxy field is set — ensure the proxy app is running.\n");
  }
  if (!$("#cookie").value.trim() && !$("#use-saved-profile").checked) {
    appendLog(
      "⚠  Tip: enable「Remember login」to stay signed in on any site without copying Cookie\n",
      "err"
    );
  }

  const body = buildRequestBody();

  try {
    const resp = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      const payload = await resp.json().catch(() => ({}));
      throw new Error(formatApiError(payload));
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        processSseLine(line, handleEvent);
      }
    }

    if (buffer.trim()) {
      processSseLine(buffer.trim(), handleEvent);
    }
  } catch (err) {
    appendLog(`\n❌  ${err.message}\n`, "err");
    setStatus(`❌  ${err.message}`);
  } finally {
    stopPingTimer();
    isRunning = false;
    setBusy(false);
  }
}

function startPingTimer() {
  stopPingTimer();
  pingTimer = setInterval(() => {
    if (!isRunning) return;
    const sec = Math.floor((Date.now() - scrapeStartedAt) / 1000);
    setStatus(`⏳  Scraping… ${sec}s (browser may be open in background)`);
  }, 1000);
}

function stopPingTimer() {
  if (pingTimer) {
    clearInterval(pingTimer);
    pingTimer = null;
  }
}

function handleEvent(evt) {
  const { type, data } = evt;
  if (type === "ping") {
    const sec = data?.elapsed ?? Math.floor((Date.now() - scrapeStartedAt) / 1000);
    setStatus(`⏳  Scraping… ${sec}s (browser may be open in background)`);
    return;
  }
  if (type === "log") {
    appendLog(`${data}\n`);
    setStatus(data.slice(-80));
  } else if (type === "done") {
    currentResult = data;
    renderResults(data);
    const platform = data.platform || "";
    const ok = platform || !isVideoPlatformUrl(data.url);
    setStatus(
      ok && platform
        ? `✅  Scrape complete! (${platform})`
        : ok
          ? "✅  Scrape complete!"
          : "⚠  Scrape done — video parser may have failed (see Log)"
    );
    $("#save-txt").disabled = false;
    $("#save-json").disabled = false;
    appendLog(
      `\n✅  Summary\n` +
        `   Paragraphs : ${data.text_paragraphs.length}\n` +
        `   Comments   : ${data.comments.length}\n` +
        `   Videos     : ${data.videos.length}\n` +
        `   Images     : ${data.images.length}\n` +
        `   Meta tags  : ${Object.keys(data.meta).length}\n` +
        (data.downloads
          ? `   Downloaded : ${data.downloads.images.length} image(s), ${data.downloads.videos.length} video file(s)\n` +
            `   Folder     : ${data.downloads.dir}\n`
          : "") +
        (data.warnings?.length ? `   Warnings   : ${data.warnings.join(" ")}\n` : "") +
        (data.platform ? `   Platform   : ${data.platform} ✅\n` : ""),
      "ok"
    );
    switchToTab("text");
  } else if (type === "error") {
    appendLog(`\n❌  ${data}\n`, "err");
    setStatus(`❌  ${data}`);
  }
}

function switchToTab(name) {
  const tab = document.querySelector(`.tab[data-tab="${name}"]`);
  if (tab) tab.click();
}

function renderResults(r) {
  const warnBanner = (r.warnings || [])
    .map((w) => `<div class="download-banner warn">${esc(w)}</div>`)
    .join("");
  const platformBanner =
    r.platform
      ? `<div class="download-banner">Video platform: ${esc(r.platform)} — ${esc(r.title || "")}</div>`
      : isVideoPlatformUrl(r.url) && !r.platform
        ? `<div class="download-banner warn">Generic scrape only — video parser failed. Enable Remember login + Visible browser.</div>`
        : "";

  const emptyText = $("#empty-text");
  const textEl = $("#content-text");

  if (r.text_paragraphs.length) {
    emptyText.classList.add("hidden");
    textEl.innerHTML =
      warnBanner +
      platformBanner +
      r.text_paragraphs
      .map(
        (p, i) =>
          `<div class="content-item"><span class="idx">#${i + 1}</span><div>${esc(p)}</div></div>`
      )
      .join("");
  } else {
    emptyText.classList.remove("hidden");
    textEl.innerHTML = warnBanner + platformBanner;
  }
  $("#count-text").textContent = r.text_paragraphs.length;

  $("#content-comments").innerHTML = r.comments.length
    ? r.comments
        .map(
          (c, i) =>
            `<div class="comment-item"><strong>#${i + 1}</strong> ${esc(c)}</div>`
        )
        .join("")
    : `<div class="empty-state"><p>No comments found. Try adding a comment selector.</p></div>`;
  $("#count-comments").textContent = r.comments.length;

  const localImageMap = {};
  (r.downloads?.images || []).forEach((item) => {
    localImageMap[normalizeImgUrl(item.url)] = item.web_path;
  });

  const displayImages = (r.images || []).map(normalizeImgUrl).filter(Boolean);

  const videoHeader =
    r.downloads?.videos?.length
      ? `<div class="download-banner">✓ ${r.downloads.videos.length} video(s) saved — click play below or open in new tab</div>`
      : "";

  const playableItems = (r.downloads?.videos || [])
    .filter((d) => d.playable !== false)
    .map((d, i) => {
      const src = escAttr(d.web_path);
      const name = esc(d.filename || d.path?.split(/[/\\]/).pop() || `video_${i + 1}`);
      const mime = escAttr(d.mime || videoMimeFromExt(name));
      return `<div class="video-card">
          <video controls preload="metadata" playsinline
            onerror="handleVideoError(this)">
            <source src="${src}" type="${mime}" />
          </video>
          <div class="video-meta">
            <a class="video-name" href="${src}" target="_blank" rel="noopener">${name}</a>
            <span class="muted">local · click ▶ to play</span>
          </div>
        </div>`;
    })
    .join("");

  const remoteItems = (r.videos || [])
    .filter((v) => v && !v.startsWith("blob:") && !v.startsWith("/downloads/"))
    .map((v, i) => {
      const local = (r.downloads?.videos || []).find((d) => d.url === v);
      if (local) return "";
      return `<div class="link-item link-item-muted"><span class="idx">${i + 1}</span><span>${esc(v)}</span> <span class="muted">(remote — not saved)</span></div>`;
    })
    .filter(Boolean)
    .join("");

  $("#content-videos").innerHTML =
    videoHeader +
    (playableItems || remoteItems
      ? `<div class="video-grid">${playableItems}</div>${remoteItems}`
      : `<div class="empty-state"><p>No playable videos. Enable「Auto-download」and try again.</p></div>`);
  $("#count-videos").textContent = Math.max(
    (r.downloads?.videos || []).length,
    (r.videos || []).filter((v) => v && !v.startsWith("blob:")).length
  );

  $("#content-images").innerHTML = displayImages.length
    ? displayImages
        .map((img, i) => {
          const norm = normalizeImgUrl(img);
          const local = localImageMap[norm];
          const primary = local || norm;
          return `<div class="image-card" data-url="${escAttr(primary)}">
              <img src="${escAttr(primary)}" alt="Image ${i + 1}" loading="lazy"
                referrerpolicy="no-referrer"
                data-remote="${escAttr(norm)}"
                data-local="${escAttr(local || "")}"
                onerror="handleImgError(this)" />
              <span class="img-idx">${i + 1}</span>
            </div>`;
        })
        .join("")
    : `<div class="empty-state"><p>No images found.</p></div>`;
  $("#count-images").textContent = displayImages.length;

  $("#content-images").querySelectorAll(".image-card").forEach((card) => {
    card.addEventListener("click", () => {
      window.open(card.dataset.url, "_blank", "noopener");
    });
  });

  const metaPreview = {
    url: r.url,
    title: r.title,
    platform: r.platform,
    text_paragraphs: r.text_paragraphs,
    comments: r.comments,
    videos: r.videos,
    images: displayImages,
    meta: r.meta,
    platform_data: r.platform_data,
    downloads: r.downloads,
    discovered_selectors: r.discovered_selectors,
    applied_selectors: r.applied_selectors,
  };
  $("#content-meta").textContent = JSON.stringify(metaPreview, null, 2);
  renderSelectors(r);
}

function renderSelectors(r) {
  const panel = $("#content-selectors");
  const empty = $("#empty-selectors");
  const discovered = r.discovered_selectors;
  const applied = r.applied_selectors;

  if (!discovered && !applied) {
    empty.classList.remove("hidden");
    panel.innerHTML = "";
    return;
  }

  empty.classList.add("hidden");
  const textSel = applied?.text_selector || discovered?.text_selector || "";
  const commentSel = applied?.comment_selector || discovered?.comment_selector || "";
  const method = discovered?.method || "none";
  const confidence = discovered?.confidence ? `${(discovered.confidence * 100).toFixed(0)}%` : "—";
  const reasoning = discovered?.reasoning || "";

  panel.innerHTML = `
    <div class="selector-card">
      <div class="selector-row"><span class="selector-label">Method</span><span class="selector-value">${esc(method)}</span></div>
      <div class="selector-row"><span class="selector-label">Confidence</span><span class="selector-value">${esc(confidence)}</span></div>
      <div class="selector-row"><span class="selector-label">Text selector</span><code class="selector-code">${esc(textSel || "(none)")}</code></div>
      <div class="selector-row"><span class="selector-label">Comment selector</span><code class="selector-code">${esc(commentSel || "(none)")}</code></div>
      ${reasoning ? `<div class="selector-row"><span class="selector-label">AI reasoning</span><span class="selector-value">${esc(reasoning)}</span></div>` : ""}
      <div class="selector-actions">
        <button class="btn btn-ghost btn-sm" id="apply-selectors-btn" ${textSel || commentSel ? "" : "disabled"}>Apply to form</button>
      </div>
    </div>`;

  const applyBtn = $("#apply-selectors-btn");
  if (applyBtn) {
    applyBtn.addEventListener("click", () => {
      if (textSel) $("#text-sel").value = textSel;
      if (commentSel) $("#comment-sel").value = commentSel;
      setStatus("Selectors applied to Advanced Options");
    });
  }
}

$("#save-json").addEventListener("click", () => {
  if (!currentResult) return;
  download(
    "scrape_result.json",
    JSON.stringify(currentResult, null, 2),
    "application/json"
  );
});

$("#save-txt").addEventListener("click", () => {
  if (!currentResult) return;
  const r = currentResult;
  const txt =
    `Title  : ${r.title}\nURL    : ${r.url}\n\n` +
    `===== BODY TEXT =====\n\n${r.text_paragraphs.join("\n\n") || "(none)"}\n\n` +
    `===== COMMENTS =====\n\n${r.comments.join("\n\n") || "(none)"}\n\n` +
    `===== VIDEOS =====\n\n${r.videos.join("\n") || "(none)"}\n\n` +
    `===== IMAGES =====\n\n${r.images.join("\n") || "(none)"}`;
  download("scrape_result.txt", txt, "text/plain");
});

function download(filename, content, mime) {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
  setStatus(`Saved → ${filename}`);
}

$("#clear-btn").addEventListener("click", () => clearResults(true));

function clearResults(confirmAction) {
  if (
    confirmAction &&
    currentResult &&
    !window.confirm("Are you sure you want to clear all results?")
  ) {
    return;
  }
  currentResult = null;
  $("#content-text").innerHTML = "";
  $("#content-comments").innerHTML = "";
  $("#content-videos").innerHTML = "";
  $("#content-images").innerHTML = "";
  $("#content-meta").textContent = "";
  $("#content-selectors").innerHTML = "";
  $("#empty-selectors").classList.remove("hidden");
  $("#content-log").innerHTML = "";
  $("#empty-text").classList.remove("hidden");
  ["text", "comments", "videos", "images"].forEach((t) => {
    $(`#count-${t}`).textContent = "0";
  });
  $("#save-txt").disabled = true;
  $("#save-json").disabled = true;
  setStatus("Ready");
}

function setBusy(busy) {
  scrapeBtn.disabled = busy;
  progressBar.classList.toggle("hidden", !busy);
  scrapeBtn.innerHTML = busy
    ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation:spin 1s linear infinite"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg> Scraping…`
    : `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg> Start Scrape`;
}

function setStatus(msg) {
  statusText.textContent = msg;
}

function appendLog(text, cls) {
  const log = $("#content-log");
  const span = document.createElement("span");
  if (cls) span.className = `log-${cls}`;
  span.textContent = text;
  log.appendChild(span);
  log.scrollTop = log.scrollHeight;
}

function normalizeImgUrl(url) {
  if (!url) return "";
  let u = url.trim();
  if (u.startsWith("//")) u = `https:${u}`;
  if (u.startsWith("http://")) u = `https://${u.slice(7)}`;
  // Bilibili CDN: strip @resize suffix for stable preview
  if (u.includes("hdslb.com") && u.includes("@")) {
    u = u.replace(/@[^/]*$/, "");
  }
  return u;
}

function videoMimeFromExt(filename) {
  const lower = (filename || "").toLowerCase();
  if (lower.endsWith(".webm")) return "video/webm";
  if (lower.endsWith(".mov")) return "video/quicktime";
  if (lower.endsWith(".mkv")) return "video/x-matroska";
  return "video/mp4";
}

function handleVideoError(video) {
  const card = video.closest(".video-card");
  if (!card || card.classList.contains("video-failed")) return;
  card.classList.add("video-failed");
  const meta = card.querySelector(".video-meta .muted");
  if (meta) {
    meta.textContent = "Cannot play — file may be corrupt or needs ffmpeg remux. Re-scrape with Visible browser.";
  }
}

window.handleVideoError = handleVideoError;

function handleImgError(img) {
  const remote = img.dataset.remote || "";
  const local = img.dataset.local || "";
  const step = img.dataset.errStep || "0";
  if (step === "0" && local && remote) {
    img.dataset.errStep = "1";
    img.src = remote;
    return;
  }
  img.onerror = null;
  img.classList.add("img-broken");
  img.alt = "Preview failed";
  img.parentElement?.classList.add("img-failed");
}

function imagePreviewSrc(url, localMap) {
  const norm = normalizeImgUrl(url);
  if (localMap[norm]) return localMap[norm];
  return norm;
}

function esc(text) {
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

function escAttr(text) {
  return esc(text).replace(/"/g, "&quot;");
}

async function loadAppVersion() {
  try {
    const resp = await fetch("/api/health");
    if (!resp.ok) return;
    const data = await resp.json();
    const el = $("#app-version");
    const port = window.location.port || "80";
    if (el && data.version) {
      el.textContent = `v${data.version} · :${port}`;
      el.title = (data.features || []).join(", ");
    }
    const badge = document.querySelector(".header-badge");
    if (badge && data.version) {
      badge.innerHTML = `<span class="pulse-dot"></span> v${data.version} · :${port}`;
      if (port !== "8000" && port !== "80" && port !== "") {
        badge.title = `Non-default port — bookmark http://${window.location.host}`;
      }
    }
  } catch (_) {
    /* ignore */
  }
}

loadAppVersion();

window.handleImgError = handleImgError;

const style = document.createElement("style");
style.textContent = `@keyframes spin { to { transform: rotate(360deg); } }`;
document.head.appendChild(style);
