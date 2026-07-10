# 📊 商业分析报告生成器

> 一句话：根据你输入的**行业**或**产品名**，自动生成一份**图文并茂**的商业分析报告。
> 支持：行业商业模式分析 / 产品深度拆解 / 竞品对比分析 · 输出 HTML / Markdown / PDF

由 **WorkBuddy AI · 2026-07-10** 启动项目作为示范。

## ✨ 它能做什么

| 输入 | 报告类型 | 典型场景 |
| --- | --- | --- |
| `咖啡` / `新能源汽车` / `SaaS` | **行业商业模式分析** | 投资人看赛道、创业者选方向 |
| `Notion` / `瑞幸咖啡` / `飞书` | **产品拆解** | 产品经理学习竞品、找借鉴 |
| `Notion vs Obsidian` / `美团 vs 饿了么` | **竞品对比** | 选型决策 / 找差异化机会 |

每份报告包含 **8-9 个章节**（执行摘要、市场概览、价值链、商业画布、竞争格局、关键玩家、趋势机会、风险建议）+ **6+ 张内联 SVG 矢量图**（条形图、折线图、雷达图、漏斗图、价值链、2x2 象限、商业画布 9 宫格），**无需任何图表库**，纯 SVG + 响应式 CSS，文件小、可直接打印。

## 🚀 快速开始

### 1. 命令行（推荐先试）

```bash
cd report-engine
source .venv/bin/activate

# 看 3 份预生成报告（无需任何 API Key）
python generate.py --type industry    --subject "中国现制咖啡"     --ai mock --preset coffee
python generate.py --type product     --subject "Notion"            --ai mock --preset notion
python generate.py --type competitor  --subject "Notion vs Obsidian" --ai mock --preset notion-vs-obsidian

# 真实 AI 生成（需要 OPENAI_API_KEY）
export OPENAI_API_KEY=sk-xxx
python generate.py --type industry --subject "咖啡" --ai openai --formats html,md,pdf
```

输出在 `reports/20260710_HHMMSS_<type>_<subject>/`，含 `report.html` / `report.md` / `report.pdf` / `report.json`。

### 2. 网页应用

```bash
cd report-engine
source .venv/bin/activate
python generate.py serve --port 8765
```

然后浏览器打开 http://127.0.0.1:8765
- 左侧表单输入主题、选 AI、选格式
- 右侧实时日志 + 报告预览
- 顶部「历史报告」入口查看所有产出

## 🤖 AI 提供商

| Provider | 配置 | 适用 |
| --- | --- | --- |
| `mock` | 无需配置，使用 `examples/*.json` 预生成报告 | 演示 / 试用 / 离线 |
| `openai` | `export OPENAI_API_KEY=sk-xxx` | 真实生成（兼容 DeepSeek / 通义千问等，自定义 `OPENAI_BASE_URL` + `OPENAI_MODEL`） |
| `workbuddy` | 无需配置 | 在 WorkBuddy 对话中直接说"用咖啡行业生成一份"，AI 把 JSON 存到 `examples/your.json`，CLI 跑渲染流程 |

### OpenAI 兼容协议示例

```bash
# DeepSeek
export OPENAI_BASE_URL=https://api.deepseek.com/v1
export OPENAI_MODEL=deepseek-chat
export OPENAI_API_KEY=sk-xxx

# 通义千问
export OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export OPENAI_MODEL=qwen-plus
export OPENAI_API_KEY=sk-xxx
```

## 📦 项目结构

```
.
├── README.md                          ← 本文件
├── report-engine/                     ← 命令行生成器
│   ├── generate.py                    ← 主入口（CLI + 后端服务）
│   ├── llm.py                         ← LLM 客户端（mock / openai / workbuddy）
│   ├── schemas.py                     ← 报告结构定义
│   ├── prompts/                       ← 3 个类型 prompt 模板
│   │   ├── industry_report.md
│   │   ├── product_report.md
│   │   └── competitor_report.md
│   ├── render/                        ← 渲染器
│   │   ├── html_renderer.py
│   │   ├── md_renderer.py
│   │   ├── pdf_renderer.py
│   │   └── svg_templates/             ← 7 个 SVG 模板（零依赖）
│   │       ├── bar.py / line.py / radar.py
│   │       ├── canvas.py / funnel.py
│   │       ├── value_chain.py / matrix.py
│   │       └── _common.py
│   ├── examples/                      ← 3 份预生成报告
│   │   ├── coffee.json
│   │   ├── notion.json
│   │   └── notion-vs-obsidian.json
│   └── requirements.txt
├── web/                               ← 网页前端
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── report.css                     ← 报告样式（独立可复用）
└── reports/                           ← 生成的报告（按时间戳分目录）
    └── 20260710_HHMMSS_<type>_<subject>/
        ├── report.html
        ├── report.md
        ├── report.pdf（可选）
        └── report.json
```

## 🎨 报告样例

打开下面任一文件即可看到效果：

- [reports/20260710_015953_industry_中国现制咖啡/report.html](reports/20260710_015953_industry_中国现制咖啡/report.html)
- [reports/20260710_015959_product_Notion/report.html](reports/20260710_015959_product_Notion/report.html)
- [reports/20260710_015959_competitor_Notion_vs_Obsidian/report.html](reports/20260710_015959_competitor_Notion_vs_Obsidian/report.html)

## 🛠 进阶用法

### 自定义 / 二次开发

1. **改 prompt**：编辑 `report-engine/prompts/*.md`，调整章节结构或输出风格
2. **加图表类型**：在 `report-engine/render/svg_templates/` 加一个 `your_chart.py`，实现 `def render(data, title) -> str`
3. **改 UI 主题**：编辑 `web/style.css` 主色变量 `:root`

### 数据格式（LLM 输出 JSON）

每份报告都是一份 JSON，方便二次处理：

```json
{
  "meta": {"title", "subject", "type", "generated_at"},
  "summary": "执行摘要",
  "sections": [
    {
      "title": "章节标题",
      "content": "Markdown 文本",
      "chart": {
        "type": "bar | line | radar | canvas | funnel | value_chain | matrix",
        "title": "图表标题",
        "data": { /* 与 type 对应 */ }
      }
    }
  ],
  "appendix": {"data_sources": [...], "limitations": "..."}
}
```

### PDF 输出（可选）

```bash
# macOS
brew install pango libffi
pip install weasyprint

# 已在 report-engine/.venv 中预装
```

## ❓ FAQ

**Q: 没 API Key 能用吗？**
A: 可以！`--ai mock` 用 `examples/` 下 3 份预生成报告跑完整流程，立刻看到效果。

**Q: 支持哪些 LLM？**
A: 任何 **OpenAI 兼容协议** 的服务（OpenAI / DeepSeek / 通义千问 / 月之暗面等），配 `OPENAI_BASE_URL` + `OPENAI_MODEL` 即可。

**Q: 报告长度？**
A: 8-9 个章节 + 6+ 张图，HTML 文件约 30-50KB，可直接打印（带 `@media print` 优化）。

**Q: 能否用于商业用途？**
A: 项目代码 MIT 协议，但 LLM 生成的报告内容需自行校验数据准确性。

## 📄 License

MIT
