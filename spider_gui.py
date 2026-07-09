#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modern Web Scraper — Playwright Edition
========================================
• Real Chromium browser engine — handles JavaScript, SPAs, lazy loading
• Extracts: body text, comments (heuristic), video links, images, metadata
• Optional CSS selectors for precise extraction on specific sites
• Cookie support to bypass anti-bot protection (521/403 errors)
• Export results to TXT or JSON

Dependencies:
  pip install playwright beautifulsoup4 lxml
  python -m playwright install chromium
"""

import json
import queue
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

COMMENT_HINTS = [
    "comment", "comments", "reply", "replies", "discuss",
    "review", "feedback", "danmu",
]
VIDEO_EXTS = (".mp4", ".m3u8", ".flv", ".webm", ".mov", ".avi")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")

# Known main-content containers for common blog / CMS platforms.
# Tried in order; the first one with substantial text wins.
COMMON_CONTENT_SELECTORS = [
    "#cnblogs_post_body",        # cnblogs.com
    ".postBody", ".post_body",   # cnblogs / generic blog themes
    "#article_content", ".article-content", ".article__content",
    ".entry-content", ".post-content", ".post-body",
    "#js_content",                # WeChat articles
    ".markdown-body",             # GitHub / many docs sites
    "#content_views",             # CSDN
    ".content-detail", ".detail-content",
    "article", "main",
]

# Elements whose class/id contains any of these are treated as
# navigation / sidebar / recommendation widgets, never as real
# article text or real user comments — even if they also match
# COMMENT_HINTS (e.g. a "Hot Comments Ranking" sidebar widget).
SIDEBAR_HINTS = [
    "sidebar", "side-bar", "aside", "nav", "menu", "footer", "header",
    "recommend", "related", "hot", "rank", "paihang", "tuijian",
    "widget", "banner", "advert", "ad-", "breadcrumb", "toc",
    "share", "social", "tag-list", "catalog",
]


def _is_sidebar(tag) -> bool:
    """True if a tag's class/id marks it as nav/sidebar/recommendation noise."""
    cls = " ".join(tag.get("class") or []) + " " + (tag.get("id") or "")
    cls = cls.lower()
    return any(h in cls for h in SIDEBAR_HINTS)

# ─────────────────────────────────────────────────────────────────────────────
# Scraping pipeline
# ─────────────────────────────────────────────────────────────────────────────

def browser_fetch(url: str, wait_ms: int, cookie: str,
                  scroll: bool, log_q: queue.Queue) -> dict:
    """Launch headless Chromium, render the page, return raw data."""

    def log(msg: str):
        log_q.put(("log", msg))

    log(f"[Browser] Launching Chromium …")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )

        # Inject cookies if provided
        if cookie.strip():
            parsed = urlparse(url)
            domain = parsed.netloc
            cookies = []
            for part in cookie.split(";"):
                part = part.strip()
                if "=" in part:
                    name, _, val = part.partition("=")
                    cookies.append({
                        "name": name.strip(),
                        "value": val.strip(),
                        "domain": domain,
                        "path": "/",
                    })
            if cookies:
                ctx.add_cookies(cookies)
                log(f"[Browser] Injected {len(cookies)} cookie(s).")

        page = ctx.new_page()
        log(f"[Browser] Navigating to {url} …")
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        if scroll:
            log("[Browser] Scrolling page to trigger lazy-loaded content …")
            for _ in range(4):
                page.evaluate("window.scrollBy(0, document.body.scrollHeight / 4)")
                page.wait_for_timeout(500)
            page.evaluate("window.scrollTo(0, 0)")

        log(f"[Browser] Waiting {wait_ms} ms for JavaScript to settle …")
        page.wait_for_timeout(wait_ms)

        html  = page.content()
        title = page.title()
        inner = page.evaluate("document.body.innerText")

        # Collect all <video> src and network-intercepted media URLs
        video_urls = list(page.evaluate("""
            () => {
                const vids = [];
                document.querySelectorAll('video, video source').forEach(el => {
                    if (el.src) vids.push(el.src);
                    if (el.currentSrc) vids.push(el.currentSrc);
                });
                document.querySelectorAll('iframe').forEach(el => {
                    const s = el.src || '';
                    if (s && (s.includes('video') || s.includes('player') ||
                              s.includes('embed') || s.includes('youtube') ||
                              s.includes('bilibili') || s.includes('vimeo'))) {
                        vids.push(s);
                    }
                });
                return [...new Set(vids.filter(Boolean))];
            }
        """))

        browser.close()
        log(f"[Browser] Done. Title: {title!r}")

    return {
        "html": html,
        "inner_text": inner,
        "title": title,
        "url": url,
        "video_urls_from_dom": video_urls,
    }


def parse_content(data: dict, text_sel: str, comment_sel: str) -> dict:
    """Parse HTML with BeautifulSoup, extract text / comments / videos / images."""
    soup    = BeautifulSoup(data["html"], "lxml")
    base    = data["url"]
    title   = data["title"] or _bs_title(soup)

    # ── Text ──
    paragraphs = _extract_text(soup, text_sel)

    # ── Comments ──
    comments = _extract_comments(soup, comment_sel)

    # ── Videos ──
    videos = list(data["video_urls_from_dom"])
    for a in soup.find_all("a", href=True):
        if a["href"].lower().endswith(VIDEO_EXTS):
            videos.append(urljoin(base, a["href"]))
    videos = _dedup(videos)

    # ── Images ──
    images = []
    for img in soup.find_all("img", src=True):
        src = urljoin(base, img["src"])
        if src not in images:
            images.append(src)
    images = images[:50]

    # ── Metadata ──
    meta = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property") or ""
        content = tag.get("content", "")
        if name and content:
            meta[name] = content

    return {
        "url": base,
        "title": title,
        "text_paragraphs": paragraphs,
        "comments": comments,
        "videos": videos,
        "images": images,
        "meta": meta,
    }


def _bs_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else "(no title)"


def _extract_text(soup: BeautifulSoup, sel: str) -> list:
    if sel:
        nodes = soup.select(sel)
        result = [n.get_text(strip=True, separator=" ") for n in nodes if n.get_text(strip=True)]
        if result:
            return result

    # 1) Try known blog/CMS main-content containers first — this avoids
    #    picking up sidebar "recommended posts" / "hot ranking" widgets
    #    that a bare <article> or whole-page scan would sweep in.
    container = None
    for css in COMMON_CONTENT_SELECTORS:
        node = soup.select_one(css)
        if node and len(node.get_text(strip=True)) > 200:
            container = node
            break
    if container is None:
        container = soup.find("article") or soup

    # 2) Pull structural text nodes (headings, paragraphs, list items,
    #    code blocks) so tutorials/code-heavy articles aren't truncated.
    paras = [p.get_text(strip=True, separator=" ")
             for p in container.find_all(["p", "h2", "h3", "h4", "h5",
                                           "li", "pre", "code", "blockquote"])
             if len(p.get_text(strip=True)) > 1 and not _is_sidebar(p)]

    # 3) Fallback: scan raw <div> blocks, but skip anything sidebar-like.
    if len(paras) < 3:
        seen, paras = set(), []
        for div in container.find_all("div"):
            if _is_sidebar(div):
                continue
            t = div.get_text(strip=True, separator=" ")
            if len(t) > 50 and t not in seen:
                seen.add(t)
                paras.append(t)
        paras = paras[:60]

    return paras


def _extract_comments(soup: BeautifulSoup, sel: str) -> list:
    if sel:
        return [n.get_text(strip=True, separator=" ")
                for n in soup.select(sel) if n.get_text(strip=True)]

    seen, results = set(), []
    for tag in soup.find_all(["div", "li", "section"]):
        # Skip nav/sidebar/"hot ranking"/"recommended" widgets — these
        # often contain the word "comment" in their class/id (e.g. a
        # "Popular Comments Ranking" sidebar panel) but are not actual
        # user comments on this article.
        if _is_sidebar(tag):
            continue
        cls = " ".join(tag.get("class") or []) + " " + (tag.get("id") or "")
        if any(h in cls.lower() for h in COMMENT_HINTS):
            txt = tag.get_text(strip=True, separator=" ")
            if txt and 5 < len(txt) < 2000 and txt not in seen:
                seen.add(txt)
                results.append(txt)
    return results[:200]


def _dedup(lst: list) -> list:
    seen, out = set(), []
    for x in lst:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def run_pipeline(url: str, text_sel: str, comment_sel: str,
                 cookie: str, wait_ms: int, scroll: bool,
                 log_q: queue.Queue):
    try:
        raw    = browser_fetch(url, wait_ms, cookie, scroll, log_q)
        result = parse_content(raw, text_sel, comment_sel)
        log_q.put(("done", result))
    except Exception as exc:
        log_q.put(("error", str(exc)))


# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────

BG      = "#1a1a2e"
PANEL   = "#16213e"
CARD    = "#0f3460"
ACCENT  = "#e94560"
ACCENT2 = "#53d8fb"
FG      = "#eaeaea"
DIM     = "#8888aa"
SUCCESS = "#4ade80"
ERR     = "#f87171"
MONO    = ("Consolas", 9)
UI      = ("Segoe UI", 10)
BOLD    = ("Segoe UI Semibold", 10)
H1      = ("Segoe UI Semibold", 14)


class ScraperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Modern Web Scraper — Playwright Edition")
        self.geometry("1120x800")
        self.minsize(900, 640)
        self.configure(bg=BG)

        self._q: queue.Queue = queue.Queue()
        self._result: dict | None = None

        self._style()
        self._build()
        self._poll()

    # ── Theming ────────────────────────────────────────────────────────────
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG,
                    fieldbackground=PANEL, font=UI, bordercolor=CARD)

        s.configure("TFrame",  background=BG)
        s.configure("Card.TFrame", background=PANEL)
        s.configure("TLabel",  background=BG,    foreground=FG,  font=UI)
        s.configure("Dim.TLabel", background=BG, foreground=DIM, font=("Segoe UI", 9))
        s.configure("H1.TLabel",  background=BG, foreground=FG,  font=H1)
        s.configure("Tag.TLabel", background=CARD, foreground=ACCENT2,
                    font=("Segoe UI", 9), padding=(6, 2))

        s.configure("TEntry", fieldbackground=PANEL, foreground=FG,
                    insertcolor=FG, bordercolor=CARD,
                    lightcolor=CARD, darkcolor=CARD)

        s.configure("TButton", background=ACCENT, foreground="#fff",
                    font=BOLD, padding=(14, 7), borderwidth=0, relief="flat")
        s.map("TButton",
              background=[("active", "#c73652"), ("disabled", "#444")],
              foreground=[("disabled", "#777")])

        s.configure("Ghost.TButton", background=PANEL, foreground=ACCENT2,
                    font=UI, padding=(10, 5), borderwidth=0)
        s.map("Ghost.TButton", background=[("active", CARD)])

        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=PANEL, foreground=DIM,
                    padding=(16, 7), font=UI)
        s.map("TNotebook.Tab",
              background=[("selected", BG)],
              foreground=[("selected", ACCENT)])

        s.configure("TLabelframe", background=BG, bordercolor=CARD)
        s.configure("TLabelframe.Label", background=BG, foreground=DIM,
                    font=("Segoe UI", 9))

        s.configure("TCheckbutton", background=BG, foreground=FG, font=UI)
        s.map("TCheckbutton", background=[("active", BG)])

        s.configure("TProgressbar", troughcolor=PANEL,
                    background=ACCENT, borderwidth=0)
        s.configure("TSeparator", background=CARD)

        # Spinbox style (ttk.Spinbox doesn't accept background/foreground/
        # buttonbackground as direct constructor kwargs — must go through Style)
        s.configure("TSpinbox", fieldbackground=PANEL, foreground=FG,
                    background=PANEL, bordercolor=CARD,
                    arrowcolor=FG, insertcolor=FG)
        s.map("TSpinbox",
              fieldbackground=[("readonly", PANEL)],
              background=[("active", CARD)])

    # ── Layout ─────────────────────────────────────────────────────────────
    def _build(self):
        P = dict(padx=14, pady=6)

        # ── Header ──────────────────────────────────────────────
        hdr = ttk.Frame(self)
        hdr.pack(fill="x", padx=14, pady=(14, 6))

        tk.Label(hdr, text="🕷  Modern Web Scraper",
                 bg=BG, fg=ACCENT, font=H1).pack(side="left")
        tk.Label(hdr, text="  Real Chromium browser · handles JS / SPAs / lazy-load",
                 bg=BG, fg=DIM, font=("Segoe UI", 9)).pack(side="left", padx=6)

        ttk.Separator(self).pack(fill="x", padx=14, pady=(4, 10))

        # ── URL ─────────────────────────────────────────────────
        url_row = ttk.Frame(self)
        url_row.pack(fill="x", **P)
        tk.Label(url_row, text="URL", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.url_var = tk.StringVar()
        ttk.Entry(url_row, textvariable=self.url_var,
                  font=("Segoe UI", 11)).grid(row=0, column=1, sticky="we", padx=(0, 10))
        self.run_btn = ttk.Button(url_row, text="▶  Scrape", command=self._start)
        self.run_btn.grid(row=0, column=2)
        url_row.columnconfigure(1, weight=1)

        # ── Options card ────────────────────────────────────────
        opt = ttk.LabelFrame(self, text="  Options")
        opt.pack(fill="x", **P)

        # Row 0 — selectors
        tk.Label(opt, text="Text selector", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=(8, 4), pady=6)
        self.text_sel_var = tk.StringVar()
        ttk.Entry(opt, textvariable=self.text_sel_var,
                  width=30).grid(row=0, column=1, sticky="we", padx=(0, 18))

        tk.Label(opt, text="Comment selector", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w", padx=(0, 4))
        self.cmt_sel_var = tk.StringVar()
        ttk.Entry(opt, textvariable=self.cmt_sel_var,
                  width=30).grid(row=0, column=3, sticky="we", padx=(0, 18))

        opt.columnconfigure(1, weight=1)
        opt.columnconfigure(3, weight=1)

        # Row 1 — cookie
        tk.Label(opt, text="Cookie (optional)", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", padx=(8, 4), pady=4)
        self.cookie_var = tk.StringVar()
        ttk.Entry(opt, textvariable=self.cookie_var,
                  show="•").grid(row=1, column=1, columnspan=3,
                                 sticky="we", padx=(0, 8), pady=4)

        # Row 2 — JS wait + scroll toggle
        tk.Label(opt, text="JS wait (ms)", bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", padx=(8, 4), pady=(4, 8))
        self.wait_var = tk.IntVar(value=2500)
        ttk.Spinbox(opt, from_=500, to=12000, increment=500,
                    textvariable=self.wait_var, width=8,
                    style="TSpinbox").grid(row=2, column=1, sticky="w", pady=(4, 8))

        self.scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="Auto-scroll (triggers lazy images/comments)",
                        variable=self.scroll_var).grid(
            row=2, column=2, columnspan=2, sticky="w", padx=(0, 8), pady=(4, 8))

        tk.Label(opt,
                 text="Tip: leave selectors blank for auto-detection. "
                      "Increase JS wait for slow React/Vue SPAs.",
                 bg=BG, fg=DIM, font=("Segoe UI", 8)).grid(
            row=3, column=0, columnspan=4, sticky="w", padx=(8, 8), pady=(0, 6))

        # ── Progress ────────────────────────────────────────────
        self.prog = ttk.Progressbar(self, mode="indeterminate")

        # ── Tabs ────────────────────────────────────────────────
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=14, pady=6)

        self.text_box    = self._tab("📄  Body Text")
        self.comment_box = self._tab("💬  Comments")
        self.video_box   = self._tab("🎬  Videos")
        self.image_box   = self._tab("🖼  Images")
        self.meta_box    = self._tab("🏷  Meta / JSON")
        self.log_box     = self._tab("📡  Log")

        # ── Bottom bar ──────────────────────────────────────────
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=14, pady=(2, 10))

        for label, cmd in [
            ("Save TXT",  self._save_txt),
            ("Save JSON", self._save_json),
            ("Clear",     self._clear),
        ]:
            ttk.Button(bar, text=label, style="Ghost.TButton",
                       command=cmd).pack(side="left", padx=(0, 6))

        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(bar, textvariable=self.status_var,
                 bg=BG, fg=DIM, font=("Segoe UI", 9)).pack(side="left", padx=8)

    def _tab(self, label: str) -> scrolledtext.ScrolledText:
        frame = ttk.Frame(self.nb)
        self.nb.add(frame, text=label)
        box = scrolledtext.ScrolledText(
            frame, wrap="word", font=MONO,
            bg=PANEL, fg=FG, insertbackground=FG,
            selectbackground=ACCENT, relief="flat", borderwidth=0)
        box.pack(fill="both", expand=True, padx=4, pady=4)
        box.configure(state="disabled")
        return box

    # ── Queue polling ──────────────────────────────────────────────────────
    def _poll(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "log":
                    self._append(self.log_box, payload + "\n")
                    self.status_var.set(payload[-90:])
                elif kind == "done":
                    self._result = payload
                    self._render(payload)
                    self._set_idle("✅  Done!")
                elif kind == "error":
                    self._append(self.log_box, f"\n❌  {payload}\n", ERR)
                    self._set_idle(f"❌  {payload[:90]}")
                    messagebox.showerror("Error", payload)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    # ── Start ──────────────────────────────────────────────────────────────
    def _start(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Enter a URL first.")
            return
        if not urlparse(url).scheme:
            url = "https://" + url
            self.url_var.set(url)

        self._clear(confirm=False)
        self._set_busy("Starting browser …")
        self._append(self.log_box, f"▶  Target: {url}\n\n")

        threading.Thread(
            target=run_pipeline,
            args=(url,
                  self.text_sel_var.get().strip(),
                  self.cmt_sel_var.get().strip(),
                  self.cookie_var.get().strip(),
                  self.wait_var.get(),
                  self.scroll_var.get(),
                  self._q),
            daemon=True,
        ).start()

    # ── Render results ─────────────────────────────────────────────────────
    def _render(self, r: dict):
        # Text
        lines = [f"Title : {r['title']}", f"URL   : {r['url']}", "=" * 60, ""]
        for i, p in enumerate(r["text_paragraphs"], 1):
            lines.append(f"[{i}]  {p}\n")
        if not r["text_paragraphs"]:
            lines.append("(Nothing found — try adding a Text selector in Options)")
        self._set_text(self.text_box, "\n".join(lines))

        # Comments
        if r["comments"]:
            self._set_text(self.comment_box,
                           "\n\n".join(f"[{i}]  {c}" for i, c in enumerate(r["comments"], 1)))
        else:
            self._set_text(self.comment_box,
                "No comments found.\n\n"
                "Most modern sites load comments via JavaScript after page load.\n"
                "Try: open DevTools → Network → XHR to find the comment API endpoint,\n"
                "or add a Comment selector in Options (e.g. '.comment-body').")

        # Videos
        if r["videos"]:
            self._set_text(self.video_box,
                           "\n".join(f"[{i}]  {v}" for i, v in enumerate(r["videos"], 1)))
        else:
            self._set_text(self.video_box, "(No <video> tags or known embeds found.)")

        # Images
        if r["images"]:
            self._set_text(self.image_box,
                           "\n".join(f"[{i}]  {v}" for i, v in enumerate(r["images"], 1)))
        else:
            self._set_text(self.image_box, "(No images found.)")

        # Meta / full JSON
        self._set_text(self.meta_box, json.dumps(r, ensure_ascii=False, indent=2))

        # Switch to text tab
        self.nb.select(0)

        # Update log with summary
        self._append(self.log_box,
            f"\n✅ Summary\n"
            f"   Paragraphs : {len(r['text_paragraphs'])}\n"
            f"   Comments   : {len(r['comments'])}\n"
            f"   Videos     : {len(r['videos'])}\n"
            f"   Images     : {len(r['images'])}\n"
            f"   Meta tags  : {len(r['meta'])}\n",
            SUCCESS)

    # ── Save ───────────────────────────────────────────────────────────────
    def _save_json(self):
        if not self._result:
            messagebox.showinfo("Nothing to save", "Run a scrape first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            initialfile="scrape_result.json")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._result, f, ensure_ascii=False, indent=2)
            self.status_var.set(f"Saved → {path}")

    def _save_txt(self):
        if not self._result:
            messagebox.showinfo("Nothing to save", "Run a scrape first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Text", "*.txt")],
            initialfile="scrape_result.txt")
        if path:
            r = self._result
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"Title  : {r['title']}\nURL    : {r['url']}\n\n")
                f.write("===== BODY TEXT =====\n\n")
                f.write("\n\n".join(r["text_paragraphs"]) or "(none)")
                f.write("\n\n===== COMMENTS =====\n\n")
                f.write("\n\n".join(r["comments"]) or "(none)")
                f.write("\n\n===== VIDEOS =====\n\n")
                f.write("\n".join(r["videos"]) or "(none)")
                f.write("\n\n===== IMAGES =====\n\n")
                f.write("\n".join(r["images"]) or "(none)")
            self.status_var.set(f"Saved → {path}")

    def _clear(self, confirm=True):
        if confirm and not messagebox.askyesno("Clear", "Clear all results?"):
            return
        self._result = None
        for box in (self.text_box, self.comment_box, self.video_box,
                    self.image_box, self.meta_box, self.log_box):
            self._set_text(box, "")
        self.status_var.set("Ready.")

    # ── Helpers ────────────────────────────────────────────────────────────
    def _set_busy(self, msg: str):
        self.run_btn.config(state="disabled")
        self.prog.pack(fill="x", padx=14, pady=(0, 4))
        self.prog.start(10)
        self.status_var.set(msg)

    def _set_idle(self, msg: str):
        self.prog.stop()
        self.prog.pack_forget()
        self.run_btn.config(state="normal")
        self.status_var.set(msg)

    def _append(self, box, text: str, color: str = ""):
        box.configure(state="normal")
        if color:
            tag = f"c{color[1:]}"
            box.tag_configure(tag, foreground=color)
            box.insert("end", text, tag)
        else:
            box.insert("end", text)
        box.see("end")
        box.configure(state="disabled")

    def _set_text(self, box, text: str):
        box.configure(state="normal")
        box.delete("1.0", "end")
        if text:
            box.insert("1.0", text)
        box.configure(state="disabled")


if __name__ == "__main__":
    app = ScraperApp()
    app.mainloop()