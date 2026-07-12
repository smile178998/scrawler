# Modern Web Scraper

基于 Playwright 的 Web 爬虫，配有 FastAPI Web 界面。使用真实 Chromium/Chrome 浏览器渲染页面，提取结构化内容（正文、评论、视频、图片和元数据）。

**语言 / Language：** [English](README.md) | **简体中文**

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey) ![License](https://img.shields.io/badge/license-MIT-green)

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
- 智能图片过滤 — 自动跳过图标、UI 资源和无效缩略图
- 从 `<meta>` 标签提取元数据
- 导出结果为 TXT 或 JSON

### 平台支持：哔哩哔哩 (Bilibili)
- 自动识别 `bilibili.com` 视频页面
- 提取标题、简介、UP 主、播放量/点赞/投币等统计数据
- 解析 `__INITIAL_STATE__` 和 `__playinfo__` 获取 **DASH 视频/音频流地址**
- 精选图片：仅保留封面、UP 头像、首帧预览（过滤推荐区缩略图）
- 支持部分评论抓取；完整评论需登录 Cookie

### 智能自动选择器
- **启发式 DOM 评分** — 无需手动填写 CSS 选择器即可定位正文与评论区域
- **稳定 CSS 生成** — 优先使用 `#id` 和语义化 class，跳过动态哈希 class
- **AI 兜底** — 启发式失败时调用 OpenAI 兼容 API（OpenAI、DeepSeek、Ollama）
- **选择器验证** — 重新提取内容并保留最优结果
- **Selectors 选项卡** — 显示方法、置信度与发现的选择器，一键应用到表单

### 反检测与可靠性
- **系统 Chrome** 支持（指纹比内置 Chromium 更真实）
- **playwright-stealth** + 内置指纹补丁（webdriver、WebGL、请求头）
- 随机浏览器配置（UA、分辨率、语言、时区）
- 模拟人类行为（鼠标移动、滚动）
- Cloudflare / WAF 挑战页检测与自动等待
- 多策略重试：无头 → 延长等待 → 有界面浏览器回退
- HTTP/SOCKS5 **代理** 支持（可选认证）
- Cookie 注入以维持登录态
- 可配置 JS 等待时间与自动滚动

---

## 项目结构

```
spaider_crawler/
├── app.py              # FastAPI Web 服务 + SSE API
├── scraper_core.py     # Playwright 管道 + 内容解析
├── selector_engine.py  # 智能 CSS 选择器发现（启发式 + AI）
├── bilibili_parser.py  # B 站视频元数据与流媒体提取
├── image_utils.py      # 图片 URL 规范化与垃圾过滤
├── requirements.txt
├── payload.json        # API 请求示例
├── demo.gif            # README 使用演示动图
├── .env.example        # AI API Key 模板（复制为 .env）
├── templates/
│   └── index.html      # Web 界面
├── static/
│   ├── css/style.css
│   └── js/app.js
└── scripts/
    └── record_demo_gif.py  # 重新生成 README 演示 GIF
```

---

## 环境要求

- Python 3.10+
- `pip` 及可写的 Python 环境
- Google Chrome（可选，推荐用于更强反检测）

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

4.（可选）配置 AI 选择器兜底 — 将 `.env.example` 复制为 `.env` 并填入 API Key：

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

```env
OPENAI_API_KEY=sk-your-key-here
# DeepSeek: AI_BASE_URL=https://api.deepseek.com/v1  AI_MODEL=deepseek-chat
# Ollama:   AI_BASE_URL=http://127.0.0.1:11434/v1   AI_MODEL=llama3.2
```

---

## 快速开始

启动 Web 界面：

```bash
python app.py
```

在浏览器打开 `http://127.0.0.1:8000/`，输入 URL，点击 **Start Scrape**。

或直接使用 uvicorn：

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

### 示例：抓取 B 站视频

```
https://www.bilibili.com/video/BV1yk7X6KEz4
```

推荐设置：

| 选项 | 建议值 |
|------|--------|
| JS wait | `5000–8000` ms |
| Auto-scroll | 开启 |
| Use system Chrome | 开启 |
| Smart auto-selector | 可选（B 站使用专用解析器） |
| Cookie | 粘贴 B 站登录 Cookie 以抓取完整评论 |

结果可在 **Text**、**Videos**、**Images** 和 **Metadata**（`bilibili` 字段）中查看。

---

## Web 界面选项

| 选项 | 说明 |
|------|------|
| Text / Comment selector | CSS 选择器；留空则自动识别 |
| Cookie | 会话 Cookie（`key1=val1; key2=val2`） |
| Proxy | `http://host:port` 或 `socks5://user:pass@host:port` |
| JS wait (ms) | 页面加载后等待 JS 的时间（500–30000） |
| Browser mode | `Auto` / `Headless only` / `Visible browser` |
| Max retries | 备用策略重试次数（0–4） |
| Use system Chrome | 优先使用本机 Chrome 而非内置 Chromium |
| Simulate human | 随机鼠标移动与滚动 |
| Block resources | 跳过图片/字体以加速（可能触发检测） |
| Smart auto-selector | DOM 评分自动发现正文/评论 CSS 选择器 |
| Enable AI fallback | 启发式失败时调用 LLM（需 API Key） |
| AI API key / base URL / model | 覆盖环境变量；支持 OpenAI 兼容服务商 |

**受保护站点推荐：** 浏览器模式选 **Auto** 或 **Visible**，启用 **Use system Chrome**，IP 被封时配置代理。

**未知页面结构推荐：** CSS 选择器留空，启用 **Smart auto-selector**；复杂页面配置 API Key。

**B 站视频：** 选择器留空即可，自动启用 B 站专用解析器；完整评论需填写 Cookie。

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

> **说明：** B 站链接会跳过通用自动选择器，改用 `bilibili_parser.py` 专用解析。

---

## API 参考

### `GET /api/health`

健康检查。

```json
{ "status": "ok" }
```

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
  "ai_model": ""
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

**SSE 事件：**

| 事件 | 说明 |
|------|------|
| `log` | 进度日志 |
| `done` | 最终 JSON 结果 |
| `error` | 错误信息 |

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
    "wait_ms": 6000,
    "use_chrome": True,
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/scrape",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=180) as resp:
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
  "videos": ["https://...m4s?..."],
  "images": [
    "https://i2.hdslb.com/bfs/archive/cover.jpg",
    "https://i1.hdslb.com/bfs/face/avatar.jpg"
  ],
  "meta": {
    "bilibili_bvid": "BV1yk7X6KEz4",
    "bilibili_aid": "116686023891513",
    "bilibili_cid": "38829687897"
  },
  "bilibili": {
    "bvid": "BV1yk7X6KEz4",
    "aid": 116686023891513,
    "cid": 38829687897,
    "title": "...",
    "description": "...",
    "owner": { "name": "...", "face": "..." },
    "stat": { "view": 5574174, "like": 182118, "reply": 1791 },
    "video_streams": [{ "url": "...", "width": 1920, "height": 1080 }],
    "audio_streams": [{ "url": "..." }]
  }
}
```

结果展示在多个选项卡（Text / Comments / Videos / Images / **Selectors** / Metadata / Log），可导出为 TXT 或 JSON。

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
| 端口 8000 被占用 | 结束占用进程：`netstat -ano \| findstr :8000`（Windows） |
| Cloudflare / WAF 拦截 | 使用 **Visible** 模式 + 系统 Chrome + 代理 |
| SPA 内容为空 | 增加 JS 等待时间；启用自动滚动 |
| 出现 CAPTCHA | 切换到 **Visible** 模式手动完成验证 |
| 找不到系统 Chrome | 取消 **Use system Chrome** 或安装 Chrome |
| 提取内容不正确 | 选择器留空；启用 **Smart auto-selector** |
| AI 选择器未触发 | 在 `.env` 设置 `OPENAI_API_KEY` 或在界面填入 Key |
| AI 请求失败 | 检查 `ai_base_url` / `ai_model`；确认服务商兼容性 |
| B 站：图片数量异常/无法加载 | 最新版已修复 — 仅保留封面/头像/首帧 |
| B 站：评论很少或为空 | 在高级选项粘贴登录 Cookie（`SESSDATA`、`bili_jct`） |
| B 站：视频链接过期 | CDN 链接带签名有时效，请尽快下载 |
| B 站：`.m4s` 分片 | DASH 流媒体分片，需用 ffmpeg 合并为完整 MP4 |

---

## 使用须知

- 仅抓取你有权访问的内容，遵守 `robots.txt` 和网站服务条款。
- 本工具仅供学习与合法研究，无法绕过所有 CAPTCHA 或商业 WAF。
- `cookie` 选项仅用于你自己的会话，切勿使用他人凭证。
- B 站视频流可能受版权保护，请合法使用抓取结果。

---

## 许可证

MIT License — 见 [LICENSE](LICENSE)。
