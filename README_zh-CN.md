# Modern Web Scraper

基于 Playwright 的 Web 爬虫，配有 FastAPI Web 界面。使用真实 Chromium/Chrome 浏览器渲染页面，提取结构化内容（正文、评论、视频、图片和元数据）。

**语言 / Language：** [English](README.md) | **简体中文**

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey) ![Version](https://img.shields.io/badge/version-1.3.0-blue) ![License](https://img.shields.io/badge/license-MIT-green)

---

## 使用演示

![使用演示](demo.gif)

*输入 URL → 打开高级选项 → 开始抓取 → 查看正文、日志与选择器选项卡。*

![截图](image.png)

## 功能特性

### 内容提取
- 真实浏览器渲染（Playwright）— 支持 JS、SPA 和懒加载内容
- 自动识别正文 + 可选 CSS 选择器覆盖
- 启发式评论提取 + 可选 CSS 选择器覆盖
- 视频与图片链接提取（支持 `data-src` 等懒加载属性）
- 智能图片过滤 — 自动跳过图标、UI 资源、推荐缩略图和无效链接
- 从 `<meta>` 标签提取元数据
- 导出结果为 TXT 或 JSON

### 视频平台（`video_platforms/`）
- 自动识别主流视频站：**哔哩哔哩**、**YouTube**、**Vimeo**、**TikTok**、**抖音**、**Twitter/X**、**Twitch**、**Dailymotion**、**Niconico**
- **B 站** — 专用处理器：`__INITIAL_STATE__`、`__playinfo__`、WBI 评论分页、DASH 流媒体
- **其他平台** — 通用处理器：Open Graph、JSON-LD、`ytInitialPlayerResponse`、DOM `<video>` 标签
- 统一结果结构：`platform`、`platform_data`、精选图片（封面 / 头像 / 首帧）
- 视频平台 URL 会自动跳过通用自动选择器

### 媒体下载与页面内播放
- **自动下载** 图片和视频到本地 `downloads/` 目录
- 按文件魔数校验视频内容 — 拒绝 HTML 错误页（不会出现假 `.bin` / `.mp4`）
- **ffmpeg** 转封装：将 B 站 DASH（`.m4s`）合并为浏览器可播放的 `.mp4`
- **Videos 选项卡** — 内嵌 `<video>` 播放器，点击 ▶ 即可观看本地文件
- `/downloads/...` 以正确的 `video/mp4` MIME 类型提供服务

### 记住登录（全站通用）
- **Remember login** — 持久化 Chrome 配置保存在 `.chrome_profile/`
- 在 **Visible browser** 模式下各站登录一次，后续抓取自动复用会话
- 适用于 B 站、YouTube、论坛及任何需要登录的网站
- 高级选项中的 Cookie 可在需要时覆盖已保存的会话

### 智能自动选择器
- **启发式 DOM 评分** — 无需手动填写 CSS 选择器即可定位正文与评论区域
- **稳定 CSS 生成** — 优先使用 `#id` 和语义化 class，跳过动态哈希 class
- **AI 兜底** — 启发式失败时调用 OpenAI 兼容 API（OpenAI、DeepSeek、Ollama）
- **选择器验证** — 重新提取内容并保留最优结果
- **Selectors 选项卡** — 显示方法、置信度与发现的选择器，一键应用到表单

### 反检测与可靠性
- **隐秘 Fetcher**（`fetcher.py`）— 基于 `curl_cffi` 的快速 HTTP：浏览器 TLS/JA3 指纹、真实标头、可选 HTTP/3
- **动态 Fetcher**（`dynamic_fetcher.py`）— 完整 Playwright 浏览器加载 JS/SPA 页面；支持 Chromium 或系统 **Google Chrome**
- **反机器人 Fetcher**（`stealthy_fetcher.py`）— Patchright/Playwright + fingerprint 伪装；`solve_cloudflare` 处理 Turnstile/Interstitial
- **系统 Chrome** 支持（指纹比内置 Chromium 更真实）
- **playwright-stealth** + 内置指纹补丁（webdriver、WebGL、请求头）
- 随机浏览器配置（UA、分辨率、语言、时区）
- 模拟人类行为（鼠标移动、滚动）
- Cloudflare / WAF 挑战页检测与自动等待
- 多策略重试：无头 → 延长等待 → 有界面浏览器回退
- 网络错误自动重试导航；失效的环境变量代理自动跳过
- HTTP/SOCKS5 **代理** 支持（界面填写或 `SCRAPER_PROXY` / `HTTP_PROXY` 环境变量）
- **ProxyRotator** — 所有 Session 支持轮询 / 随机 / 自定义策略；单次请求可用 `proxy=` 覆盖
- **域名 / 广告屏蔽** — 浏览器 Fetcher 支持 `blocked_domains` + `block_ads`（约 3500 个追踪域名）
- 可配置 JS 等待时间与自动滚动
- **端口自动选择** — 8000 被占用时自动尝试 8001+

---

## 项目结构

```
spaider_crawler/
├── app.py              # FastAPI Web 服务 + SSE API + /downloads 媒体路由
├── scraper_core.py     # Playwright 管道 + 内容解析
├── selector_engine.py  # 智能 CSS 选择器发现（启发式 + AI）
├── media_downloader.py # 自动下载图片/视频；ffmpeg 合并；MIME 类型
├── fetcher.py          # 隐秘 HTTP 客户端（TLS 指纹 + HTTP/3，基于 curl_cffi）
├── dynamic_fetcher.py  # Playwright DynamicFetcher（Chromium / Google Chrome）
├── stealthy_fetcher.py # StealthyFetcher — 指纹伪装 + Cloudflare 挑战处理
├── session_store.py    # Cookie / 状态持久化工具
├── sessions.py         # 统一导出：FetcherSession / DynamicSession / StealthySession
├── proxy_rotator.py    # ProxyRotator — 轮询 / 随机 / 自定义策略
├── request_blocking.py # 浏览器 Fetcher：域名 / 广告请求屏蔽
├── ad_domains.py       # 内置约 3500 个广告/追踪域名加载器
├── data/
│   └── ad_domains.txt  # Peter Lowe 广告域名列表
├── video_platforms/    # 多平台视频元数据与流媒体提取
│   ├── __init__.py     # 检测 / 提取 / 合并入口
│   ├── registry.py     # 平台 URL 匹配与调度
│   ├── bilibili.py     # B 站处理器（WBI 评论、DASH 流）
│   ├── generic.py      # YouTube、Vimeo、TikTok 等
│   └── merge.py        # 统一结果合并 → platform_data
├── image_utils.py      # 图片 URL 规范化与垃圾过滤
├── requirements.txt
├── payload.json        # API 请求示例
├── demo.gif            # README 使用演示动图
├── .env.example        # 环境变量模板（复制为 .env）
├── templates/
│   └── index.html      # Web 界面
├── static/
│   ├── css/style.css
│   └── js/app.js
└── scripts/
    ├── start.ps1       # 清理旧进程并在 8000 端口启动（Windows）
    ├── scrape_video.py # CLI：抓取任意支持的视频 URL → JSON
    └── record_demo_gif.py
```

---

## 环境要求

- Python 3.10+
- `pip` 及可写的 Python 环境
- Google Chrome（可选，推荐用于更强反检测）
- **ffmpeg**（可选，推荐用于将 DASH 流合并为可播放 MP4）

依赖见 `requirements.txt`。

---

## 安装

1. 创建并激活虚拟环境（推荐）：

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

2. 安装 Python 依赖：

```bash
pip install -r requirements.txt
```

3. 安装 Playwright 浏览器：

```bash
python -m playwright install chromium
```

> **提示：** 安装 [Google Chrome](https://www.google.com/chrome/) 并在高级选项中启用 **Use system Chrome**，可获得更好的指纹伪装效果。

4.（可选）配置环境变量 — 将 `.env.example` 复制为 `.env`：

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

```env
OPENAI_API_KEY=sk-your-key-here

# 可选代理（也可从 HTTP_PROXY / HTTPS_PROXY 读取）
# SCRAPER_PROXY=http://127.0.0.1:7890

# 可选 B 站 Cookie 覆盖（优先使用已保存的 Chrome 配置）
# BILI_COOKIE=SESSDATA=...; bili_jct=...
```

---

## 快速开始

**Windows（推荐）：**

```powershell
.\scripts\start.ps1
```

**或手动启动：**

```bash
python app.py
```

在终端显示的地址打开（通常为 `http://127.0.0.1:8000/`），确认页眉显示 **v1.3.0**。

输入 URL，点击 **Start Scrape**。

或直接使用 uvicorn：

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

### 示例：B 站视频

```
https://www.bilibili.com/video/BV1yk7X6KEz4
```

| 选项 | 建议值 |
|------|--------|
| Remember login | 开启（Visible 模式登录一次） |
| JS wait | `8000` ms |
| Auto-scroll | 开启 |
| Use system Chrome | 开启 |
| Auto-download | 开启 |
| Smart auto-selector | 关闭（视频平台会自动禁用） |
| Browser mode | Visible（首次运行 / 验证码） |

### 示例：YouTube 视频

```
https://www.youtube.com/watch?v=...
```

| 选项 | 建议值 |
|------|--------|
| Remember login | 开启 |
| JS wait | `8000` ms |
| Use system Chrome | 开启 |
| Visible browser | 开启（获取流媒体地址需要） |
| Auto-download | 开启 |
| Proxy | 仅在网络需要时填写 |

结果可在 **Text**、**Videos**（内嵌播放器）、**Images** 和 **Metadata**（`platform`、`platform_data`）中查看。

### 命令行抓取

```bash
python scripts/scrape_video.py "https://www.bilibili.com/video/BV1yk7X6KEz4" output.json
```

---

## Web 界面选项

| 选项 | 说明 |
|------|------|
| Text / Comment selector | CSS 选择器；留空则自动识别 |
| **Remember login** | 持久化 `.chrome_profile/` — 在 Visible 模式各站登录一次 |
| Cookie | 可选会话覆盖（`key1=val1; key2=val2`） |
| Proxy | `http://host:port` 或 `socks5://user:pass@host:port`；留空则直连 |
| JS wait (ms) | 页面加载后等待 JS 的时间（500–30000） |
| Browser mode | `Auto` / `Headless only` / `Visible browser` |
| Max retries | 备用策略重试次数（0–4） |
| Use system Chrome | 优先使用本机 Chrome 而非内置 Chromium |
| Simulate human | 随机鼠标移动与滚动 |
| Block resources | 跳过图片/字体以加速（可能触发检测） |
| **Auto-download** | 保存图片和视频到 `downloads/`；在 Videos 选项卡播放 |
| Smart auto-selector | DOM 评分自动发现正文/评论 CSS 选择器 |
| Enable AI fallback | 启发式失败时调用 LLM（需 API Key） |
| AI API key / base URL / model | 覆盖环境变量；支持 OpenAI 兼容服务商 |

**需要登录的站点：** Remember login + **Visible** 模式 + 系统 Chrome；必要时再填 Cookie。

**视频平台：** 选择器留空即可，`video_platforms/` 自动运行；开启 Auto-download 可本地播放。

**未知页面结构：** CSS 选择器留空，启用 **Smart auto-selector**；复杂页面配置 API Key。

---

## 智能自动选择器

当正文/评论 CSS 选择器为空（或提取效果差）时，每次抓取结束后会自动运行：

```
HTML → DOM 评分 → 生成 CSS 选择器 → 验证 → 重新提取
                              ↓（效果不佳时）
                         AI 分析 → 新选择器 → 重新提取
```

| 方法 | 说明 |
|------|------|
| `heuristic` | DOM 文本密度、段落数、语义化 class 名 |
| `ai` | LLM 分析简化 HTML 并返回选择器 |
| `hybrid` | 启发式部分命中，AI 进一步优化 |

发现的选择器显示在 **Selectors** 选项卡，API 响应中位于 `discovered_selectors` / `applied_selectors` 字段。

> **说明：** 已知视频平台链接会跳过通用自动选择器，改用 `video_platforms/` 模块解析。

---

## 隐秘 Fetcher（HTTP）

`fetcher.py` 基于 **curl_cffi**，提供快速、隐秘的 HTTP 请求（无需浏览器）。适合 API、CDN 媒体与静态页面。

| 能力 | 说明 |
|------|------|
| TLS 指纹 | 模拟 Chrome / Edge / Safari（`impersonate="chrome"`） |
| 请求头 | 与浏览器匹配的标头 + 可选 `stealthy_headers`（`Sec-Fetch-*`、语言、Referer） |
| HTTP/3 | `http3=True` 启用（对端不支持 QUIC 时自动回退） |
| 回退 | 未安装 `curl_cffi` 时使用 `urllib`（无指纹伪装） |

媒体下载已走 Fetcher。独立用法：

```python
from fetcher import Fetcher, FetcherSession

# 单次 GET，带 Chrome TLS 指纹
r = Fetcher.get("https://example.com", stealthy_headers=True)
print(r.status_code, r.text[:200])

# 服务器支持时优先 HTTP/3
r = Fetcher.get("https://cloudflare-http3-demo.zone", http3=True, impersonate="chrome")

# 会话 + Cookie + 代理
with FetcherSession(proxy="http://127.0.0.1:7890", impersonate="chrome") as s:
    s.get("https://example.com/login")
    data = s.post("https://example.com/api", json_body={"q": "test"}).json()
```

---

## 动态 Fetcher（浏览器）

`dynamic_fetcher.py` 使用 **Playwright** 加载依赖 JavaScript 的页面。支持内置 **Chromium** 与系统已安装的 **Google Chrome**。

| 选项 | 含义 |
|------|------|
| `real_chrome=True`（或 `use_chrome=True`） | 启动系统 Google Chrome；不可用时回退 Chromium |
| `headless` | 无头（默认）或有界面 |
| `network_idle` / `wait` / `wait_selector` | 导航后的等待策略 |
| `page_action` / `page_setup` | 自定义 Playwright 钩子 |
| `disable_resources` | 屏蔽图片/字体/CSS 以加速 |
| `blocked_domains` | 要屏蔽的域名集合（含子域名） |
| `block_ads` | 启用内置约 3500 个广告/追踪域名列表 |
| `proxy` / `cookies` / `extra_headers` | 会话控制 |

```python
from dynamic_fetcher import DynamicFetcher, DynamicSession

r = DynamicFetcher.fetch(
    "https://spa.example.com",
    real_chrome=True,
    headless=True,
    network_idle=True,
    wait=1500,
    wait_selector="main",
)
print(r.title, r.status_code, r.browser_engine)

# 复用同一浏览器打开多个页面
with DynamicSession(real_chrome=True, headless=True) as session:
    home = session.fetch("https://example.com")
    about = session.fetch("https://example.com/about")
```

> 静态页 / API / CDN 优先用 **Fetcher**；DOM 由 JavaScript 生成时用 **DynamicFetcher**。

---

## 反机器人 Fetcher（Stealthy）

`stealthy_fetcher.py` 是本地最强的浏览器层级：优先 **Patchright**（已安装时），否则 Playwright；并提供 fingerprint 伪装与 Cloudflare 挑战自动化。

| 选项 | 含义 |
|------|------|
| `solve_cloudflare=True` | 检测并处理 Turnstile / 间隙页（managed / interactive / non-interactive / embedded） |
| `hide_canvas=True` | Canvas 噪声防指纹 |
| `block_webrtc=True` | 阻止 WebRTC 泄露本地 IP |
| `allow_webgl=True` | 保持 WebGL 开启（推荐，很多 WAF 会检查） |
| `real_chrome=True` | 优先系统 Google Chrome |
| `humanize=True` | 鼠标抖动（启用 CF 求解时自动打开） |

```python
from stealthy_fetcher import StealthyFetcher, StealthySession

r = StealthyFetcher.fetch(
    "https://protected.example",
    solve_cloudflare=True,
    hide_canvas=True,
    block_webrtc=True,
    real_chrome=True,
    headless=True,
    timeout=60000,
)
print(r.title, r.extras.get("cloudflare_solved"), r.browser_engine)

# 推荐安装更强引擎：
#   pip install patchright
#   python -m patchright install chrome
```

> Cloudflare 求解是通过更真实的浏览器环境 + UI 自动化让挑战自行通过，并非破解验证码密码学。最难的站点请配合「有界面」模式与干净的住宅代理。

---

## Session 管理

三类 Session 都在跨请求间保留 **Cookie** 和自定义 **`state`**，并可持久化到 JSON：

| 类 | 引擎 | 适用场景 |
|------|------|----------|
| `FetcherSession` | curl_cffi HTTP | 登录 API、Token 刷新、CDN 下载 |
| `DynamicSession` | Playwright | 多页 JS 流程，同一浏览器上下文 |
| `StealthySession` | Patchright/Playwright | 带 Cloudflare 的多步流程 |

统一 API：`get_cookies` / `set_cookies` / `clear_cookies` / `save` / `load` / `snapshot` / `restore` / `state`。

```python
from sessions import FetcherSession, DynamicSession, StealthySession

# HTTP — 退出上下文时自动保存 cookies
with FetcherSession(session_file=".sessions/api.json") as s:
    s.get("https://httpbin.org/cookies/set?session=abc")
    s.state["role"] = "user"
    print(s.cookies_map())

# 浏览器 — 同一 context，cookie 跨页面保留
with DynamicSession(real_chrome=True, session_file=".sessions/web.json") as s:
    s.fetch("https://example.com")
    s.set_cookies({"sid": "xyz"}, url="https://example.com")
    s.fetch("https://example.com/account")
    snap = s.snapshot()

# 稍后恢复
with DynamicSession(real_chrome=True) as s:
    s.restore(snap, url="https://example.com")
    s.fetch("https://example.com/dashboard")
```

也可从各模块直接导入：`from fetcher import FetcherSession` 等。

---

## Proxy 轮换

内置 ``ProxyRotator``，适用于**所有 Session 类型**。默认轮询；可传入自定义策略函数。单次请求的 ``proxy=`` 始终覆盖旋转器。

```python
from sessions import FetcherSession, DynamicSession, ProxyRotator, random_rotation

rotator = ProxyRotator([
    "http://1.2.3.4:8080",
    {"server": "http://5.6.7.8:8080", "username": "u", "password": "p"},
])

with FetcherSession(proxy_rotator=rotator) as s:
    s.get("https://example.com/a")   # 代理 #1
    s.get("https://example.com/b")   # 代理 #2
    s.get("https://example.com/c")   # 再次 #1
    # 单次强制指定代理：
    s.get("https://example.com/d", proxy="http://9.9.9.9:3128")
    # 单次直连（不用代理）：
    s.get("https://example.com/e", proxy=None)
    print(s.last_proxy)

# 随机策略
rotator = ProxyRotator(proxies, strategy=random_rotation)

# 自定义：始终用第一个
def sticky(proxies, idx):
    return proxies[0], idx

with DynamicSession(proxy_rotator=ProxyRotator(proxies, strategy=sticky)) as s:
    s.fetch("https://example.com")
```

失败代理可跳过：``rotator.mark_failed(proxy)`` / ``rotator.reset_failures()``。

---

## 域名与广告屏蔽

浏览器 Fetcher（`DynamicSession` / `StealthySession`）可在请求发出前直接 abort——被屏蔽域名不会产生 DNS/TCP。

| 选项 | 作用 |
|------|------|
| `blocked_domains={"tracker.net", "ads.example.com"}` | 屏蔽这些域名及其**所有子域名** |
| `block_ads=True` | 屏蔽约 3,500 个已知广告/追踪域名（Peter Lowe 列表） |
| `disable_resources=True` | 同时丢弃图片/字体/样式表/媒体（加速） |

```python
from dynamic_fetcher import DynamicFetcher
from stealthy_fetcher import StealthySession

r = DynamicFetcher.fetch(
    "https://news.example",
    block_ads=True,
    blocked_domains={"metrics.vendor.com", "cdn.doubleclick.net"},
)

with StealthySession(block_ads=True, blocked_domains={"evil.tracker"}) as s:
    page = s.fetch("https://protected.example")
```

查看列表规模：``from ad_domains import ad_domain_count; print(ad_domain_count())``。

---

## API 参考

### `GET /api/health`

健康检查与版本信息。

```json
{
  "status": "ok",
  "version": "1.3.0",
  "features": ["video_platforms", "wbi_comments", "download_media", "saved_profile", "stealth_fetcher", "dynamic_fetcher", "stealthy_fetcher", "session_manager"]
}
```

### `GET /downloads/{path}`

以正确 MIME 类型（如 `video/mp4`）提供已下载的媒体文件，供浏览器内播放。

### `POST /api/scrape`

启动抓取任务，返回 **Server-Sent Events (SSE)** 流。

**请求体：**

```json
{
  "url": "https://example.com",
  "text_selector": "",
  "comment_selector": "",
  "cookie": "",
  "proxy": "",
  "wait_ms": 3500,
  "scroll": true,
  "use_chrome": true,
  "headless": "auto",
  "max_retries": 2,
  "simulate_human": true,
  "block_resources": false,
  "auto_selector": true,
  "auto_selector_ai": true,
  "ai_api_key": "",
  "ai_base_url": "",
  "ai_model": "",
  "download_media": true,
  "use_saved_profile": true
}
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | string | *必填* | 目标 URL |
| `text_selector` | string | `""` | 正文 CSS 选择器 |
| `comment_selector` | string | `""` | 评论 CSS 选择器 |
| `cookie` | string | `""` | 认证 Cookie |
| `proxy` | string | `""` | 代理地址 |
| `wait_ms` | int | `3500` | JS 稳定等待时间（500–30000） |
| `scroll` | bool | `true` | 自动滚动触发懒加载 |
| `use_chrome` | bool | `true` | 优先使用系统 Chrome |
| `headless` | string | `"auto"` | `"auto"`、`"hidden"` 或 `"visible"` |
| `max_retries` | int | `2` | 最大重试次数（0–4） |
| `simulate_human` | bool | `true` | 模拟鼠标/滚动行为 |
| `block_resources` | bool | `false` | 屏蔽图片/字体/样式 |
| `auto_selector` | bool | `true` | 启用智能 CSS 选择器发现 |
| `auto_selector_ai` | bool | `true` | 启发式失败时使用 AI |
| `ai_api_key` | string | `""` | API Key（回退到 `OPENAI_API_KEY` 环境变量） |
| `ai_base_url` | string | `""` | API 基础 URL（默认 OpenAI） |
| `ai_model` | string | `""` | 模型名称（默认 `gpt-4o-mini`） |
| `download_media` | bool | `true` | 下载图片/视频到 `downloads/` |
| `use_saved_profile` | bool | `true` | 使用持久化 `.chrome_profile/` 登录态 |

**SSE 事件：**

| 事件 | 说明 |
|------|------|
| `log` | 进度日志 |
| `ping` | 心跳（含已用秒数，长时间抓取时保持界面响应） |
| `done` | 最终 JSON 结果 |
| `error` | 错误信息（可读提示） |

**校验失败** 返回 HTTP `422` 及 JSON 响应：

```json
{
  "error": "Invalid request",
  "details": ["headless: Input should be 'auto', 'hidden' or 'visible'"]
}
```

### 示例（Python）

```python
import json
import urllib.request

body = json.dumps({
    "url": "https://www.bilibili.com/video/BV1yk7X6KEz4",
    "wait_ms": 8000,
    "use_chrome": True,
    "download_media": True,
    "use_saved_profile": True,
    "auto_selector": False,
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/scrape",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=300) as resp:
    for line in resp.read().decode().splitlines():
        if line.startswith("data: "):
            print(line[6:])
```

### 示例（PowerShell）

```powershell
Invoke-WebRequest `
  -Uri http://127.0.0.1:8000/api/scrape `
  -Method Post `
  -Body (Get-Content payload.json -Raw) `
  -ContentType "application/json" `
  -OutFile sse_response.txt
```

---

## API 输出

抓取成功后，`done` 事件包含：

```json
{
  "url": "https://www.bilibili.com/video/BV1yk7X6KEz4",
  "title": "视频标题",
  "platform": "bilibili",
  "text_paragraphs": ["播放 5,574,174 · 点赞 182,118 · ...", "UP主: ...", "简介..."],
  "comments": ["用户: 评论内容"],
  "videos": ["/downloads/My_Video_1234567890/videos/My_Video.mp4"],
  "images": [
    "https://i2.hdslb.com/bfs/archive/cover.jpg",
    "https://i1.hdslb.com/bfs/face/avatar.jpg"
  ],
  "meta": {
    "video_platform": "bilibili",
    "bilibili_bvid": "BV1yk7X6KEz4",
    "bilibili_aid": "116686023891513",
    "bilibili_cid": "38829687897"
  },
  "platform_data": {
    "platform": "bilibili",
    "bvid": "BV1yk7X6KEz4",
    "aid": 116686023891513,
    "title": "...",
    "description": "...",
    "owner": { "name": "...", "face": "..." },
    "stat": { "view": 5574174, "like": 182118, "reply": 1791 },
    "video_streams": [{ "url": "...", "width": 1920, "height": 1080 }],
    "audio_streams": [{ "url": "..." }],
    "comments": ["用户: 评论内容"]
  },
  "downloads": {
    "dir": "C:\\...\\downloads\\My_Video_1234567890",
    "web_dir": "/downloads/My_Video_1234567890",
    "images": [
      { "url": "https://...", "path": "...", "web_path": "/downloads/.../images/001.jpg", "filename": "001.jpg" }
    ],
    "videos": [
      {
        "url": "https://...",
        "path": "...",
        "web_path": "/downloads/.../videos/My_Video.mp4",
        "filename": "My_Video.mp4",
        "mime": "video/mp4",
        "playable": true
      }
    ]
  }
}
```

结果展示在多个选项卡（Text / Comments / **Videos** / Images / **Selectors** / Metadata / Log），可导出为 TXT 或 JSON。

---

## 可选：Docker（实验性）

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install chromium
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

> 容器环境可能需要额外系统库（字体、GTK 等）及额外启动参数。

---

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| Playwright 无法启动 | 运行 `python -m playwright install chromium` |
| 端口 8000 被占用 | 运行 `.\scripts\start.ps1`（Windows）或使用终端显示的端口（如 8001） |
| 导航报 `ERR_CONNECTION_CLOSED` | 清除失效的 `HTTP_PROXY` 环境变量；Proxy 留空直连；尝试 Visible + 系统 Chrome |
| Cloudflare / WAF 拦截 | 使用 **Visible** 模式 + 系统 Chrome + 代理 |
| SPA 内容为空 | 增加 JS 等待时间；启用自动滚动 |
| 出现 CAPTCHA | 切换到 **Visible** 模式，开启 Remember login，手动完成一次验证 |
| 找不到系统 Chrome | 取消 **Use system Chrome** 或安装 Chrome |
| 提取内容不正确 | 选择器留空；启用 **Smart auto-selector** |
| AI 选择器未触发 | 在 `.env` 设置 `OPENAI_API_KEY` 或在界面填入 Key |
| 视频平台：仅通用抓取 | 开启 Remember login + Visible 浏览器；查看 Log 是否有验证码 |
| 视频无法播放（黑屏） | 重新抓取并开启 Auto-download；安装 **ffmpeg** 合并 DASH |
| 下载到的是 HTML 而非视频 | 流地址过期或需登录 — 使用 Visible 模式 + 已保存配置 |
| B 站：图片数量异常 | 已修复 — 仅保留封面 / 头像 / 首帧 |
| B 站：评论很少或为空 | 开启 Remember login 或在高级选项粘贴 `BILI_COOKIE` |
| B 站 / YouTube：视频链接过期 | CDN 链接带签名有时效，请尽快下载 |
| `.m4s` 分片 | 安装 ffmpeg — 可用时自动合并为 `.mp4` |
| Profile locked 错误 | 关闭其他占用 `.chrome_profile/` 的 Chrome / 爬虫窗口 |

---

## 使用须知

- 仅抓取你有权访问的内容，遵守 `robots.txt` 和网站服务条款。
- 本工具仅供学习与合法研究，无法绕过所有 CAPTCHA 或商业 WAF。
- `cookie` 选项仅用于你自己的会话，切勿使用他人凭证。
- 视频流可能受版权保护，请合法使用抓取结果。

---

## 许可证

MIT License — 见 [LICENSE](LICENSE)。
