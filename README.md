# 商业分析报告生成器

输入一个行业、产品或竞品主题，自动完成公开信息检索、事实抽取、交叉验证、报告生成与多格式导出。

这个项目不把“大模型生成的文字”直接当作事实。每条关键论断都会尽量绑定公开来源，并标记为**已核实、待确认、冲突或估算**；报告置信度由证据覆盖情况计算，而不是由模型自评。

## 核心能力

- **三类报告**：行业商业模式分析、产品深度拆解、竞品对比分析
- **证据驱动生成**：检索、筛选、事实抽取、交叉验证、引用绑定
- **可信度提示**：区分已核实、待确认、冲突和估算信息
- **实时进度**：通过 SSE 展示 7 个研究阶段，支持中途停止
- **报告工作台**：项目分组、历史记录、来源清单与证据链查看
- **报告后处理**：基于证据追问、单章节重新生成、锚点定位
- **多格式输出**：HTML、Markdown、PDF、JSON
- **内联图表**：条形图、折线图、雷达图、漏斗图、价值链、矩阵和商业画布
- **离线演示**：不配置 API Key 也能用内置语料运行完整流程
- **一键部署**：本地启动脚本、Dockerfile 与 Docker Compose

## 工作流程

```text
意图解析 → 公开检索 → 来源筛选与去重 → 事实抽取 → 交叉验证 → 证据驱动生成 → 渲染与导出
  parse       search          filter          extract       verify          draft          render
```

事实验证规则：

- 两个及以上独立来源支持：`verified`（已核实）
- 高权威官方、财报或行业来源单独支持：`verified`（高权威单源）
- 单一普通来源支持：`unverified`（待确认）
- 同类指标口径不一致：`conflicted`（冲突）
- 没有直接来源：`estimate`（估算）

置信度主要根据已核实事实占比计算；一旦存在冲突，分数会被限制，避免用一个看似精确的高分掩盖证据问题。

## 快速开始

### 网页应用

需要 Python 3.10 或更高版本。

```bash
git clone https://github.com/Elara-code/business-report-generator.git
cd business-report-generator

export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://api.deepseek.com
export OPENAI_MODEL=deepseek-v4-flash

./start.sh
```

打开 <http://127.0.0.1:8781>。

指定端口：

```bash
./start.sh --port 8765
```

`start.sh` 会自动创建虚拟环境并安装依赖。网页模式默认使用真实模型，因此需要配置 API Key。

### 离线命令行演示

不需要 API Key：

```bash
cd report-engine
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python generate.py gen \
  --type industry \
  --subject "中国现制咖啡" \
  --ai mock \
  --preset coffee
```

可用预设：

| 报告类型 | `--type` | 示例主题 | `--preset` |
| --- | --- | --- | --- |
| 行业分析 | `industry` | 中国现制咖啡 | `coffee` |
| 产品拆解 | `product` | Notion | `notion` |
| 竞品对比 | `competitor` | Notion vs Obsidian | `notion-vs-obsidian` |

### 真实检索与生成

```bash
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_MODEL=gpt-4o-mini

python generate.py gen \
  --type competitor \
  --subject "Notion vs Obsidian" \
  --ai openai \
  --market "全球" \
  --time-range "近 1 年" \
  --audience "产品经理" \
  --formats html,md,pdf
```

系统兼容 OpenAI API 协议，可通过环境变量切换 OpenAI、DeepSeek、通义千问等服务。真实检索不可用时会自动回退到离线语料或本地组装，避免整条流水线直接中断。

本地导出 PDF 还需要 WeasyPrint 的系统库；macOS 可执行 `brew install pango libffi`。Docker 镜像已经包含相关运行库。

### 从 JSON 重新渲染

跳过检索和模型调用，直接把已有结构化报告渲染为目标格式：

```bash
python generate.py gen \
  --type industry \
  --subject "中国现制咖啡" \
  --from-json examples/coffee.json \
  --formats html,md,pdf
```

生成结果保存在 `reports/`，每次任务使用独立目录，包含 `report.json` 以及选择的输出文件。

## CLI 参数

| 参数 | 说明 |
| --- | --- |
| `--type` | `industry`、`product` 或 `competitor` |
| `--subject` | 行业、产品或竞品组合 |
| `--ai` | `mock`、`openai` 或兼容项 `workbuddy` |
| `--preset` | mock 模式使用的内置语料 |
| `--formats` | 逗号分隔的 `html,md,pdf` |
| `--out-dir` | 自定义输出根目录 |
| `--from-json` | 从已有 JSON 读取并渲染 |
| `--market` | 市场范围，默认“全国” |
| `--time-range` | 时间范围，默认“近 1 年” |
| `--audience` | 目标读者，默认“普通读者” |

查看完整帮助：

```bash
python generate.py gen --help
python generate.py serve --help
```

## 网页功能

生成过程中，前端会依次展示：

```text
任务解析 / 公开检索 / 来源筛选 / 事实抽取 / 交叉验证 / 报告生成 / 渲染导出
```

报告完成后可以：

- 查看正文、证据链和来源清单
- 点击引用编号回到原始来源
- 针对当前报告继续追问
- 重新生成指定章节
- 导出 HTML、Markdown 或 PDF
- 复制当前报告链接
- 按项目管理、查看或删除历史报告

主要接口：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/generate` | 创建报告并以 SSE 返回进度 |
| `POST` | `/api/cancel` | 停止指定生成任务 |
| `GET` | `/api/history` | 获取按项目分组的历史报告 |
| `POST` | `/api/history/delete` | 删除报告或项目 |
| `GET/POST` | `/api/projects` | 获取或创建项目 |
| `POST` | `/api/followup` | 基于当前证据链回答追问 |
| `POST` | `/api/regenerate-section` | 重新生成单个章节 |
| `POST` | `/api/export` | 导出报告文件 |

## 项目结构

```text
.
├── report-engine/
│   ├── generate.py              # CLI、HTTP 服务、SSE 与接口入口
│   ├── llm.py                   # mock / OpenAI 兼容模型提供器
│   ├── report_model.py          # Pydantic 报告模型与校验
│   ├── schemas.py               # 报告类型与结构常量
│   ├── prompts/                 # 三类报告提示词
│   ├── research/
│   │   ├── planner.py           # 意图解析与检索计划
│   │   ├── searcher.py          # DuckDuckGo / 离线语料检索
│   │   ├── extractor.py         # 事实抽取与重试
│   │   ├── verifier.py          # 交叉验证与置信度计算
│   │   ├── drafter.py           # 证据驱动起草
│   │   ├── pipeline.py          # 研究流水线编排
│   │   └── corpus/              # 离线演示语料
│   ├── render/
│   │   ├── html_renderer.py     # HTML 渲染与安全清洗
│   │   ├── md_renderer.py
│   │   ├── pdf_renderer.py
│   │   └── svg_templates/       # 7 类原生 SVG 图表
│   ├── examples/                # 示例报告 JSON
│   └── tests/                   # 自动化测试
├── web/                         # 原生 HTML / CSS / JavaScript 前端
├── reports/                     # 本地生成结果（Git 忽略）
├── Dockerfile
├── docker-compose.yml
└── start.sh
```

## 技术选型

- **Python + Pydantic**：统一命令行、服务端和结构化数据校验
- **OpenAI 兼容协议**：避免绑定单一模型供应商
- **DuckDuckGo**：无需额外搜索 API Key 的公开检索入口
- **SSE**：适合生成任务的服务端单向进度推送
- **原生 SVG**：报告单文件可携带、可打印，不依赖前端图表库
- **Bleach**：清洗模型生成的 HTML，降低 XSS 风险
- **WeasyPrint**：将同一份 HTML 报告导出为 PDF

## Docker 部署

```bash
cp .env.example .env
# 编辑 .env，填写 OPENAI_API_KEY 等配置
docker compose up -d --build
```

访问 <http://127.0.0.1:8781>。`reports/` 会挂载到宿主机，容器重启后生成结果仍然保留。

单独使用 Docker：

```bash
docker build -t business-report-generator .
docker run --rm -p 8781:8781 \
  -e OPENAI_API_KEY=sk-xxx \
  -v "$PWD/reports:/app/reports" \
  business-report-generator
```

## 测试

```bash
cd report-engine
source .venv/bin/activate
python -m pytest tests/ -q
```

当前测试集包含 **85 项测试**，覆盖研究计划、垂直检索、来源去重、事实抽取重试、多源数值验证、置信度、Pydantic 校验、图表规范化、HTML 安全清洗、任务取消和报告锚点等核心路径。

## 安全与边界

- 模型生成的 HTML 会经过标签、属性和 CSS 白名单清洗。
- API Key 只通过环境变量传入，不应提交到仓库。
- “已核实”表示满足当前程序的来源规则，不等于经过专业审计。
- 不同网站可能转载同一原始内容，现有独立来源判断无法完全识别转载关系。
- 搜索摘要、网页变化、模型能力和来源质量都会影响报告结果。
- 分享功能复制的是当前可访问地址；公网分享仍需自行部署并配置访问控制。
- 重要商业、投资或合规决策应回到原始来源人工复核。

## 后续方向

- 建立固定评测集，持续衡量事实准确率、引用覆盖率和无效链接率
- 增强网页正文解析、转载识别和原始出处追踪
- 将长任务迁移到持久化任务队列，支持多实例部署
- 增加用户鉴权、限流、审计日志和团队协作
- 扩展 PPT、DOCX 与用户材料导入

## License

MIT
