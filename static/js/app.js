/* Modern Web Scraper — Frontend */

let currentResult = null;
let isRunning = false;

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

function buildRequestBody() {
  return {
    url: urlInput.value.trim(),
    text_selector: $("#text-sel").value.trim(),
    comment_selector: $("#comment-sel").value.trim(),
    cookie: $("#cookie").value.trim(),
    proxy: $("#proxy").value.trim(),
    wait_ms: clamp($("#wait-ms").value, 500, 30000, 3500),
    scroll: $("#scroll").checked,
    use_chrome: $("#use-chrome").checked,
    headless: $("#headless-mode").value,
    max_retries: clamp($("#max-retries").value, 0, 4, 2),
    simulate_human: $("#simulate-human").checked,
    block_resources: $("#block-resources").checked,
    auto_selector: $("#auto-selector").checked,
    auto_selector_ai: $("#auto-selector-ai").checked,
    download_media: $("#download-media").checked,
    ai_api_key: $("#ai-api-key").value.trim(),
    ai_base_url: $("#ai-base-url").value.trim(),
    ai_model: $("#ai-model").value.trim(),
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
  setBusy(true);
  clearResults(false);
  appendLog(`▶  Target: ${url}\n\n`);
  switchToTab("log");

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
    isRunning = false;
    setBusy(false);
  }
}

function handleEvent(evt) {
  const { type, data } = evt;
  if (type === "log") {
    appendLog(`${data}\n`);
    setStatus(data.slice(-80));
  } else if (type === "done") {
    currentResult = data;
    renderResults(data);
    setStatus("✅  Scrape complete!");
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
          : ""),
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
  const emptyText = $("#empty-text");
  const textEl = $("#content-text");

  if (r.text_paragraphs.length) {
    emptyText.classList.add("hidden");
    textEl.innerHTML = r.text_paragraphs
      .map(
        (p, i) =>
          `<div class="content-item"><span class="idx">#${i + 1}</span><div>${esc(p)}</div></div>`
      )
      .join("");
  } else {
    emptyText.classList.remove("hidden");
    textEl.innerHTML = "";
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
      ? `<div class="download-banner">Downloaded ${r.downloads.videos.length} file(s) to <code>${esc(r.downloads.dir)}</code></div>`
      : "";

  const downloadedItems = (r.downloads?.videos || [])
    .map(
      (d) =>
        `<div class="link-item"><span class="idx">✓</span><a href="${escAttr(d.web_path)}" target="_blank" rel="noopener">${esc(d.path.split(/[/\\]/).pop())}</a> <span class="muted">(local)</span></div>`
    )
    .join("");

  const streamItems = r.videos
    .map((v, i) => {
      const local = (r.downloads?.videos || []).find((d) => d.url === v);
      if (local) return "";
      return `<div class="link-item"><span class="idx">${i + 1}</span><a href="${escAttr(v)}" target="_blank" rel="noopener">${esc(v)}</a></div>`;
    })
    .filter(Boolean)
    .join("");

  $("#content-videos").innerHTML =
    videoHeader +
    (downloadedItems || streamItems
      ? downloadedItems + streamItems
      : `<div class="empty-state"><p>No video links found.</p></div>`);
  $("#count-videos").textContent = Math.max(
    r.videos.length,
    (r.downloads?.videos || []).length
  );

  $("#content-images").innerHTML = displayImages.length
    ? displayImages
        .map((img, i) => {
          const src = localImageMap[img] || img;
          return `<div class="image-card" data-url="${escAttr(src)}">
              <img src="${escAttr(src)}" alt="Image ${i + 1}" loading="lazy" onerror="this.parentElement.style.display='none'" />
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
    bilibili: r.bilibili,
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
  if (url.startsWith("//")) return `https:${url}`;
  return url;
}

function esc(text) {
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

function escAttr(text) {
  return esc(text).replace(/"/g, "&quot;");
}

const style = document.createElement("style");
style.textContent = `@keyframes spin { to { transform: rotate(360deg); } }`;
document.head.appendChild(style);
