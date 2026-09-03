"""Report Engine 主入口。

Usage:
  python generate.py gen --type industry  --subject "咖啡"          --ai mock
  python generate.py gen --type product   --subject "Notion"        --ai openai --formats html,md,pdf
  python generate.py gen --type competitor --subject "Notion vs Obsidian" --ai mock --preset notion-vs-obsidian
  python generate.py gen --from-json ./examples/coffee.json        # 跳过 LLM
  python generate.py serve --port 8765                             # 启动 Web 后端

修复记录（vs 初版）：
- P0: 根路由 / → web/index.html
- P0: 漏斗图 f'{esc(v):,}' bug
- P0: Mock preset 与用户输入错配（强制覆盖 meta.type / meta.subject）
- P0: --from-json 流程补全
- P0: 引入 Pydantic schema 校验，失败重试 + 降级
- P1: 历史报告只返回真实存在的文件
- P1: LLM 调用的超时 / 重试
- P1: 报告目录名加微秒+UUID 后缀防冲突
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import threading
import uuid
from datetime import datetime
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import schemas  # noqa: E402
from llm import extract_json, get_provider  # noqa: E402
from render import html_renderer, md_renderer, pdf_renderer  # noqa: E402


class GenerationCancelled(Exception):
    """用户主动取消生成。"""


# 取消注册表：client_id -> threading.Event。生成开始注册、结束清理。
_CANCEL_EVENTS: dict[str, threading.Event] = {}
_CANCEL_LOCK = threading.Lock()


def _register_cancel(client_id: str) -> threading.Event:
    ev = threading.Event()
    with _CANCEL_LOCK:
        _CANCEL_EVENTS[client_id] = ev
    return ev


def _unregister_cancel(client_id: str) -> None:
    with _CANCEL_LOCK:
        _CANCEL_EVENTS.pop(client_id, None)
from report_model import Report, coerce_report  # noqa: E402
from research import build_plan, run_research, get_searcher, draft_report, attach_evidence  # noqa: E402
from research.drafter import _section_schema_hint  # noqa: E402


# ---------------------------------------------------------------------------
# Prompt 加载
# ---------------------------------------------------------------------------

def load_prompt(report_type: str, subject: str) -> tuple[str, str]:
    system = schemas.SYSTEM_PROMPT
    fname = {
        "industry": "industry_report.md",
        "product": "product_report.md",
        "competitor": "competitor_report.md",
    }[report_type]
    path = os.path.join(HERE, "prompts", fname)
    with open(path, "r", encoding="utf-8") as f:
        body = f.read()
    sections = "\n".join(f"  - {s}" for s in schemas.REPORT_SECTIONS[report_type])
    # 用简单替换而非 str.format，避开 prompt 里的花括号陷阱
    user = (body
            .replace("{subject}", subject)
            .replace("{industry_sections}", sections)
            .replace("{product_sections}", sections)
            .replace("{competitor_sections}", sections)
            .replace("{json_schema}", schemas.JSON_SCHEMA_HINT))
    return system, user


# ---------------------------------------------------------------------------
# LLM 调用：带重试 + 超时 + 校验
# ---------------------------------------------------------------------------

def call_llm_with_retry(provider, system: str, user: str, *, max_retries: int = 1, timeout: int = 60) -> Report:
    """调 LLM，3 步降级（v0.3）：

    1. 第一次：尝试带 json_mode（模型支持时）
    2. 失败 → 第二次：去掉 json_mode，靠 prompt 强约束
    3. 再失败 → 不再重试 LLM，直接抛错（前端显示错误，建议用户换模型）

    关键变更：相比 v0.2 的"重试 2 次"更激进 —— 经验上重试超过 1 次在国产模型上
    几乎不会让格式变好，反而增加 API 成本 + 拉长等待时间。
    """
    last_err: Exception | None = None
    use_json_mode = getattr(provider, "json_mode_supported", True)

    for attempt, json_mode in enumerate([use_json_mode, False]):
        try:
            raw = provider.complete(system, user, json_mode=json_mode)
            data = extract_json(raw)
            return Report.model_validate(data)
        except Exception as e:
            last_err = e
            tag = f"json_mode={json_mode}"
            print(f"  ⚠️  LLM 尝试 {attempt+1} ({tag}) 失败: {e}", file=sys.stderr)
            if attempt < max_retries:
                # 下次重试时强化 prompt
                user += "\n\n【重要】请只输出严格合法的 JSON，不要任何解释文字或 markdown 围栏。"

    raise RuntimeError(f"LLM 调用在 2 次降级后仍失败: {last_err}")


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------

def save_report_json(report: Report, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, ensure_ascii=False, indent=2)
    return path


def render_formats(report: Report, formats: list[str], out_dir: str) -> dict[str, str]:
    """只输出用户请求的格式。每个文件生成成功才计入 outputs。"""
    outputs: dict[str, str] = {}
    # 渲染器期望 dict 输入
    report_dict = report.model_dump()

    if "html" in formats:
        try:
            html = html_renderer.render(report_dict)
            p = os.path.join(out_dir, "report.html")
            with open(p, "w", encoding="utf-8") as f:
                f.write(html)
            outputs["html"] = p
        except Exception as e:
            outputs["html_error"] = str(e)

    if "md" in formats:
        try:
            md = md_renderer.render(report_dict)
            p = os.path.join(out_dir, "report.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(md)
            outputs["md"] = p
        except Exception as e:
            outputs["md_error"] = str(e)

    if "pdf" in formats:
        try:
            p = pdf_renderer.render(report_dict, os.path.join(out_dir, "report.pdf"))
            outputs["pdf"] = p
        except Exception as e:
            outputs["pdf_error"] = str(e)
    return outputs


def make_out_dir(root: str, report_type: str, subject: str) -> str:
    """生成唯一目录名：YYYYMMDD_HHMMSS_us_<type>_<safe>_<short-uuid>"""
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in subject).strip().replace(" ", "_")
    safe = safe[:40] or "report"
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S") + f"_{now.microsecond:06d}"
    short = uuid.uuid4().hex[:6]
    return os.path.join(root, f"{stamp}_{report_type}_{safe}_{short}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def do_generate(report_type: str, subject: str, ai: str, preset: str | None,
                formats: list[str], out_root: str, from_json: str | None,
                on_progress=None, market: str | None = None,
                time_range: str | None = None, audience: str | None = None,
                on_stream=None, cancel_event: threading.Event | None = None) -> tuple[Report, dict[str, str], str]:
    """统一处理 CLI 与 HTTP 入口。返回 (Report, outputs, target_dir)。

    v1（研究流水线）：
      - 非 from_json 路径不再"单次 LLM 生成"，而是走
        意图解析 → 公开检索 → 来源筛选 → 事实抽取 → 交叉验证 → 证据驱动生成；
      - 关键数字全部来自证据链并标注来源编号与核实状态；
      - 离线模式（--ai mock）用演示语料 + 确定性组装，仍可端到端演示。

    on_progress 回调用于 SSE 流式响应：
        on_progress(phase: str, message: str) -> None
        phase ∈ {"init","parse","search","filter","extract","verify","draft","render","done","error"}

    on_stream 回调用于 draft 阶段的细粒度流式事件（可选）：
        on_stream(kind: str, payload: dict) -> None
        kind ∈ {"outline"（骨架节标题列表）, "section"（单节已生成，含 index/section）}
    """
    if report_type not in schemas.SUPPORTED_TYPES:
        raise ValueError(f"type 必须是 {schemas.SUPPORTED_TYPES}，收到: {report_type}")

    def _check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise GenerationCancelled("生成已取消")

    def _progress(phase: str, msg: str):
        _check_cancel()
        print(f"[{phase}] {msg}")
        if on_progress:
            try:
                on_progress(phase, msg)
            except Exception:
                pass

    def _stream(kind: str, payload: dict):
        _check_cancel()
        if on_stream:
            try:
                on_stream(kind, payload)
            except Exception:
                pass

    # 1) 取原始数据
    _progress("init", f"开始生成 {report_type} 报告：{subject}")
    if from_json:
        _progress("init", f"📂 从 {from_json} 读取")
        with open(from_json, "r", encoding="utf-8") as f:
            raw = f.read()
        data = extract_json(raw)
        report = Report.model_validate(data)
    else:
        # ---- 研究流水线 ----
        plan = build_plan(report_type, subject, market=market or "",
                          time_range=time_range or "", audience=audience or "")
        _progress("parse", f"已解析分析任务：{plan.display}")

        # 检索层 + LLM 回调
        if ai == "mock":
            searcher, warn = get_searcher(prefer="curated")
            llm = None
        else:
            provider = get_provider(ai, preset=preset, timeout=240)
            def _complete(system: str, user: str, json_mode: bool = True) -> str:
                # 先按请求模式调用；失败则降级为纯文本重试（部分国产模型不支持
                # response_format=json_object），仍失败才抛错，由流水线兜底。
                # 注意：draft 阶段要求 8 节每节配图 + 要点，LLM 输出可达 5000+ 字符，
                # 实测耗时可达 3 分钟以上，故超时放宽到 240s（见 get_provider timeout）。
                last_err: Exception | None = None
                modes = [json_mode, False] if json_mode else [False]
                for jm in modes:
                    try:
                        return provider.complete(system, user, json_mode=jm)
                    except Exception as e:  # noqa: BLE001
                        last_err = e
                        print(f"  ⚠️  LLM 调用降级 (json_mode={jm}) 失败: {e}", file=sys.stderr)
                raise last_err if last_err else RuntimeError("LLM 调用失败")
            llm = _complete
            searcher, warn = get_searcher(prefer="auto")
        if warn:
            _progress("search", f"⚠️ {warn}")

        # 执行研究流水线
        chain = run_research(plan, searcher, llm=llm, on_progress=_progress)

        # 证据驱动生成（流式：outline 骨架秒回 + 逐节推送）
        _progress("draft", f"基于 {len(chain.facts)} 条事实撰写报告…")

        def _on_outline(titles: list[str]):
            _progress("draft", f"报告骨架已生成：{len(titles)} 节")
            _stream("outline", {"sections": titles, "total": len(titles)})

        def _on_section(idx: int, sec: dict):
            _progress("draft", f"第 {idx + 1} 节《{sec.get('title', '')}》已生成")
            _stream("section", {"index": idx, "section": sec})

        raw = draft_report(plan, chain, llm=llm,
                           on_outline=_on_outline if on_stream else None,
                           on_section=_on_section if on_stream else None)
        raw = attach_evidence(raw, chain)
        # 补齐「证据驱动生成 / 渲染与导出」两步到流水线日志（run_research 只记前 5 步），
        # 使历史报告 report.json 中的 evidence.log 完整 7 步，前端打开历史时可恢复运行日志
        try:
            _steps = raw.get("evidence", {}).get("log", {}).get("steps", [])
            if _steps:
                _steps.append({"name": "证据驱动生成", "status": "done",
                               "message": f"撰写 {len(raw.get('sections', []))} 节报告", "detail": ""})
                _steps.append({"name": "渲染与导出", "status": "done",
                               "message": "渲染 HTML/Markdown 完成", "detail": ""})
        except Exception:
            pass
        report = coerce_report(raw, report_type, subject)

    # 2) 强制覆盖关键 meta（非 from_json 已覆盖，此处兜底）
    raw_dict = report.model_dump()
    report = coerce_report(raw_dict, report_type, subject)

    # 3) 输出
    _progress("render", "💾 写入 report.json ...")
    target = make_out_dir(out_root, report_type, subject)
    save_report_json(report, target)
    _progress("render", f"🎨 渲染 {','.join(formats)} ...")
    outputs = render_formats(report, formats, target)
    _progress("done", f"✅ 已生成报告 → {target}")
    for k, v in outputs.items():
        if k.endswith("_error"):
            _progress("done", f"⚠️  {k}: {v}")
        else:
            rel = os.path.relpath(v, HERE)
            _progress("done", f"  • {k}: {rel}")
    return report, outputs, target


# ---------------------------------------------------------------------------
# CLI 子命令
# ---------------------------------------------------------------------------

def cmd_gen(args) -> int:
    try:
        do_generate(
            report_type=args.type,
            subject=args.subject,
            ai=args.ai,
            preset=args.preset,
            formats=args.formats.split(",") if isinstance(args.formats, str) else args.formats,
            out_root=args.out_dir or os.path.join(os.path.dirname(HERE), "reports"),
            from_json=args.from_json,
            market=args.market,
            time_range=args.time_range,
            audience=args.audience,
        )
        return 0
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


def cmd_serve(args) -> int:
    """启动 Web 后端：根路由 / → web/index.html，提供 /api/generate + /api/history。"""
    import http.server
    import socketserver
    import threading

    workspace_root = os.path.dirname(HERE)  # /Users/.../2026-07-10-01-47-41
    web_dir = os.path.join(workspace_root, "web")
    reports_dir = os.path.join(workspace_root, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=workspace_root, **kw)

        def do_GET(self):  # noqa
            # P0-1: 根路由 → web/index.html
            if self.path in ("/", "/index.html"):
                self.path = "/web/index.html"
                return super().do_GET()
            if self.path == "/api/history":
                return self._json_history()
            if self.path == "/api/projects":
                return self._json({"projects": self._list_projects()})
            return super().do_GET()

        def do_POST(self):  # noqa
            if self.path == "/api/generate":
                return self._handle_generate_sse()
            if self.path == "/api/history/delete":
                return self._handle_delete()
            if self.path == "/api/projects":
                return self._handle_create_project()
            if self.path == "/api/cancel":
                return self._handle_cancel()
            if self.path == "/api/followup":
                return self._handle_followup()
            if self.path == "/api/regenerate-section":
                return self._handle_regenerate_section()
            return self._json({"error": "Not Found"}, 404)

        # ----- /api/generate（SSE 流式） -----
        def _handle_generate_sse(self):
            """v0.3: 改用 SSE，前端能实时看到 init/llm/render/done 4 个阶段。

            协议：
              Content-Type: text/event-stream
              每条 event 形如：data: {"phase": "llm", "message": "..."}\n\n
              最后一条 event 带 done=true，前端可关闭连接。
            """
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}
            except Exception as e:
                return self._json({"error": f"无效 JSON: {e}"}, 400)

            report_type = req.get("type", "industry")
            subject = req.get("subject", "未命名")
            ai = req.get("ai", "mock")
            formats = req.get("formats", ["html"])
            preset = req.get("preset")
            market = req.get("market")
            time_range = req.get("time_range")
            audience = req.get("audience")
            project = self._safe_project(req.get("project"))
            client_id = str(req.get("client_id") or "") or None
            cancel_ev = _register_cancel(client_id) if client_id else None

            # SSE 头
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")  # 禁 nginx 缓冲
            self.end_headers()

            _sse_lock = threading.Lock()

            def emit(phase: str, message: str, **extra):
                payload = {"phase": phase, "message": message, **extra}
                line = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                # 并发逐节生成时多个线程可能同时 emit，写入必须串行化
                with _sse_lock:
                    try:
                        self.wfile.write(line.encode("utf-8"))
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        # 客户端断开，吞掉异常
                        pass

            try:
                out_root = os.path.join(reports_dir, project) if project else reports_dir
                os.makedirs(out_root, exist_ok=True)
                report, outputs, target = do_generate(
                    report_type=report_type,
                    subject=subject,
                    ai=ai,
                    preset=preset,
                    formats=formats,
                    out_root=out_root,
                    from_json=None,
                    on_progress=lambda phase, msg: emit(phase, msg),
                    on_stream=lambda kind, payload: emit(
                        kind, payload.get("message", ""),
                        **{k: v for k, v in payload.items() if k != "message"}),
                    market=market,
                    time_range=time_range,
                    audience=audience,
                    cancel_event=cancel_ev,
                )
                # 证据链摘要（供前端"来源面板 / 冲突提示"使用）
                evidence = report.evidence or {}
                facts = evidence.get("facts") or []
                ev_summary = {
                    "sources": len(evidence.get("sources") or []),
                    "facts": len(facts),
                    "verified": sum(1 for f in facts if f.get("status") == "verified"),
                    "conflicted": sum(1 for f in facts if f.get("status") == "conflicted"),
                    "unverified": sum(1 for f in facts if f.get("status") == "unverified"),
                }
                # 终态事件
                emit("complete", "✅ 报告已生成", done=True, ok=True,
                     dir=os.path.relpath(target, workspace_root),
                     title=report.meta.title,
                     confidence=(report.meta.confidence.model_dump() if report.meta.confidence else None),
                     evidence=ev_summary,
                     files={k: os.path.relpath(v, workspace_root) for k, v in outputs.items()},
                     preview=next((f"reports/{os.path.basename(target)}/report.html"
                                    for k in ("html",) if k in outputs), None))
            except GenerationCancelled:
                emit("cancelled", "⏹ 生成已取消", done=True, ok=False, error="cancelled")
            except Exception as e:
                emit("error", f"❌ {e}", done=True, ok=False, error=str(e))
            finally:
                if cancel_ev is not None:
                    _unregister_cancel(client_id)
            # 关键：显式关闭连接。http.server 默认 HTTP/1.1 keep-alive，
            # 若不关闭，浏览器 fetch 流式读取永远等不到 EOF，收不到 complete 终态。
            self.close_connection = True
            return

        # ----- /api/history（按项目分组） -----
        def _safe_project(self, name) -> str:
            """清洗项目名，仅保留目录安全字符；空/非法返回空字符串（= 默认分组）。"""
            if not name:
                return ""
            safe = re.sub(r'[\\/:*?"<>|\s]+', "_", str(name)).strip("_")[:40]
            if safe in ("", ".", ".."):
                return ""
            return safe

        def _list_projects(self) -> list[str]:
            """reports/ 下一级目录中「不是报告目录」（即含子目录、无自身 report.json）的视为项目。"""
            projects = []
            if os.path.exists(reports_dir):
                for entry in sorted(os.listdir(reports_dir)):
                    full = os.path.join(reports_dir, entry)
                    if os.path.isdir(full) and not os.path.exists(os.path.join(full, "report.json")):
                        projects.append(entry)
            return projects

        def _history_item(self, rel_dir: str, entry: str) -> dict | None:
            """读取单个报告目录的元信息。rel_dir 为相对 reports/ 的路径（可能含项目前缀）。"""
            full = os.path.join(reports_dir, rel_dir)
            json_path = os.path.join(full, "report.json")
            if not os.path.exists(json_path):
                return None
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    r = json.load(f)
                meta = r.get("meta", {})
                files: dict[str, str] = {}
                for ext in ("html", "md", "pdf"):
                    p = os.path.join(full, f"report.{ext}")
                    if os.path.exists(p):
                        files[ext] = f"reports/{rel_dir}/report.{ext}"
                if not files:
                    return None
                return {
                    "dir": rel_dir,
                    "title": meta.get("title", entry),
                    "type": meta.get("type", ""),
                    "subject": meta.get("subject", ""),
                    "date": meta.get("generated_at", ""),
                    "files": files,
                    "html": files.get("html", ""),
                }
            except Exception:
                return None

        def _json_history(self):
            groups: dict[str, list] = {}
            if os.path.exists(reports_dir):
                for entry in sorted(os.listdir(reports_dir), reverse=True):
                    full = os.path.join(reports_dir, entry)
                    if not os.path.isdir(full):
                        continue
                    # 报告目录（自身带 report.json）→ 默认分组
                    if os.path.exists(os.path.join(full, "report.json")):
                        item = self._history_item(entry, entry)
                        if item:
                            groups.setdefault("默认", []).append(item)
                        continue
                    # 项目目录 → 遍历其下的报告
                    proj = entry
                    for sub in sorted(os.listdir(full), reverse=True):
                        subfull = os.path.join(full, sub)
                        if not os.path.isdir(subfull):
                            continue
                        rel = f"{proj}/{sub}"
                        item = self._history_item(rel, sub)
                        if item:
                            groups.setdefault(proj, []).append(item)
            # 默认分组放最后，其余按名排序；空项目也保留（让前端能显示项目组）
            projects = self._list_projects()
            for p in projects:
                if p not in groups:
                    groups[p] = []
            ordered = [g for g in sorted(groups) if g != "默认"] + (["默认"] if "默认" in groups else [])
            payload = [{"name": k, "items": groups[k]} for k in ordered]
            return self._json({"groups": payload, "projects": projects})

        # ----- /api/history/delete（删除报告或项目） -----
        def _handle_delete(self):
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}
            except Exception as e:
                return self._json({"error": f"无效 JSON: {e}"}, 400)
            rel = str(req.get("dir", "")).strip().lstrip("/")
            base = os.path.realpath(reports_dir)
            target = os.path.realpath(os.path.join(base, rel))
            # 防路径穿越：目标必须在 reports/ 内
            if rel in ("", ".", "..") or not (target == base or target.startswith(base + os.sep)):
                return self._json({"error": "非法路径"}, 400)
            if not os.path.isdir(target):
                return self._json({"error": "目标不存在"}, 404)
            shutil.rmtree(target)
            return self._json({"ok": True})

        # ----- /api/cancel（取消指定 client_id 的生成） -----
        def _handle_cancel(self):
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}
            except Exception as e:
                return self._json({"error": f"无效 JSON: {e}"}, 400)
            cid = str(req.get("client_id") or "").strip()
            if not cid:
                return self._json({"error": "缺少 client_id"}, 400)
            with _CANCEL_LOCK:
                ev = _CANCEL_EVENTS.get(cid)
            if ev is not None:
                ev.set()
                return self._json({"ok": True, "cancelled": True})
            return self._json({"ok": False, "cancelled": False, "reason": "任务不存在或已结束"})

        # ----- /api/followup（基于已生成报告的证据链追问） -----
        def _handle_followup(self):
            followup_system = """你是严谨的行业研究助手。基于给定的【事实清单】（每条含核实状态与来源编号）回答用户的追问。
规则：
1. 只能使用事实清单中的信息作答，不得编造清单之外的数字、事件或结论；
2. 每个关键论断后用【来源N】标注来源编号（N 为来源列表序号）；
3. 追问涉及事实清单未覆盖的内容时，明确说明「基于现有证据无法确认」，如需分析方向则标注为「推测」；
4. 中文回答，简洁有结构，多用短句。"""
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}
            except Exception as e:
                return self._json({"error": f"无效 JSON: {e}"}, 400)
            rel_dir = str(req.get("dir") or "").strip().lstrip("/")
            question = str(req.get("question") or "").strip()
            if not rel_dir or not question:
                return self._json({"error": "缺少 dir 或 question"}, 400)
            base = os.path.realpath(reports_dir)
            target = os.path.realpath(os.path.join(base, rel_dir))
            if not (target == base or target.startswith(base + os.sep)):
                return self._json({"error": "非法路径"}, 400)
            json_path = os.path.join(target, "report.json")
            if not os.path.exists(json_path):
                return self._json({"error": "报告不存在"}, 404)
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                return self._json({"error": f"读取报告失败: {e}"}, 500)

            ev = data.get("evidence") or {}
            facts = ev.get("facts") or []
            sources = ev.get("sources") or []
            if not facts:
                return self._json({"error": "该报告没有可追问的证据链"}, 400)
            STATUS_CN = {"verified": "已核实", "unverified": "待确认", "conflicted": "冲突", "estimate": "估算"}
            lines = []
            for i, ft in enumerate(facts, 1):
                st = STATUS_CN.get(ft.get("status"), ft.get("status"))
                srcs = ",".join(str(s) for s in (ft.get("evidence") or [])) or "无来源"
                lines.append(f"[事实{i}]({st}) 类别:{ft.get('category','')} 来源:{srcs} | {ft.get('claim','')}")
            src_lines = []
            for i, s in enumerate(sources, 1):
                sn = (s.get("snippet") or "")[:200].replace("\n", " ")
                src_lines.append(f"[{i}] {s.get('title','')} | {s.get('url','')} | {sn}")
            user = (f"报告主题：{data.get('meta',{}).get('title', rel_dir)}\n\n"
                    f"【事实清单】\n" + "\n".join(lines) +
                    f"\n\n【来源列表】\n" + "\n".join(src_lines) +
                    f"\n\n用户追问：{question}")
            try:
                provider = get_provider("openai", timeout=120)
                ans = provider.complete(followup_system, user, json_mode=False)
            except Exception as e:
                return self._json({"error": f"LLM 调用失败: {e}"}, 500)
            return self._json({"ok": True, "answer": (ans or "").strip(), "facts": len(facts), "sources": len(sources)})

        # ----- /api/regenerate-section（基于证据链重写报告单节） -----
        def _handle_regenerate_section(self):
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}
            except Exception as e:
                return self._json({"error": f"无效 JSON: {e}"}, 400)
            rel_dir = str(req.get("dir") or "").strip().lstrip("/")
            try:
                index = int(req.get("index"))
            except (TypeError, ValueError):
                return self._json({"error": "缺少 index"}, 400)
            if not rel_dir:
                return self._json({"error": "缺少 dir"}, 400)
            base = os.path.realpath(reports_dir)
            target = os.path.realpath(os.path.join(base, rel_dir))
            if not (target == base or target.startswith(base + os.sep)):
                return self._json({"error": "非法路径"}, 400)
            json_path = os.path.join(target, "report.json")
            if not os.path.exists(json_path):
                return self._json({"error": "报告不存在"}, 404)
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                return self._json({"error": f"读取报告失败: {e}"}, 500)
            sections = data.get("sections") or []
            if not (0 <= index < len(sections)):
                return self._json({"error": f"index 越界（共 {len(sections)} 节）"}, 400)
            sec = dict(sections[index])
            sec_title = sec.get("title") or f"第{index + 1}节"

            ev = data.get("evidence") or {}
            facts, sources = ev.get("facts") or [], ev.get("sources") or []
            STATUS_CN = {"verified": "已核实", "unverified": "待确认", "conflicted": "冲突", "estimate": "估算"}
            fact_lines = []
            for ft in facts:
                st = STATUS_CN.get(ft.get("status"), ft.get("status"))
                refs = ",".join(str(s) for s in (ft.get("evidence") or [])) or "无来源"
                fact_lines.append(f"- [{st}]（来源 {refs}）{ft.get('claim', '')}")
            src_lines = []
            for i, s in enumerate(sources, 1):
                sn = (s.get("snippet") or "")[:160].replace("\n", " ")
                src_lines.append(f"[{i}] {s.get('title', '')} | {s.get('domain', '')} | {s.get('source_type', '')} | {sn}")
            fact_block = "\n".join(fact_lines) or "（无）"
            src_block = "\n".join(src_lines) or "（无）"

            regen_system = """你是资深商业分析师。基于给定的【事实清单】重写报告的某一节，严格遵守证据纪律：
1. 只能使用事实清单中的内容；量化数字必须来自事实清单并标注来源编号；
2. 正文引用格式为 [N]（N 为来源编号），放在论断末尾；
3. 事实清单中标"估算/待确认/冲突"的内容，要明确写"（估算）""（待确认）""（两种口径）"，不得写成确定结论；
4. 不得编造未在事实清单中出现的来源或数据；
5. 只输出该节的 JSON，不要任何多余文字。"""
            old_kp = "；".join((sec.get("key_points") or [])[:4]) or "（无）"
            user = (f"报告主题：{data.get('meta', {}).get('title', rel_dir)}\n"
                    f"报告类型：{data.get('meta', {}).get('type', 'industry')}\n"
                    f"你正在重写第 {index + 1} 节《{sec_title}》。\n\n"
                    f"## 事实清单（只允许引用这里的内容）\n{fact_block}"
                    f"\n\n## 来源清单\n{src_block}"
                    f"\n\n## 本节原内容（供参考，可保留或改进）\n"
                    f"原导语：{str(sec.get('content', '') or '')[:120]}\n原要点：{old_kp}"
                    f"\n\n## 单节输出格式（严格 JSON）\n{_section_schema_hint()}")
            try:
                provider = get_provider("openai", timeout=120)
                ans = provider.complete(regen_system, user, json_mode=True)
            except Exception as e:
                return self._json({"error": f"LLM 调用失败: {e}"}, 500)
            text = (ans or "").strip()
            m = re.search(r"\{[\s\S]*\}", text)
            try:
                new_sec = json.loads(m.group(0)) if m else json.loads(text)
            except Exception:
                return self._json({"error": "LLM 输出解析失败，请重试"}, 500)
            if not isinstance(new_sec, dict):
                return self._json({"error": "LLM 输出格式错误"}, 500)
            # 合并回原节：标题保留原标题（重写不改骨架），内容/要点/图表可更新
            if new_sec.get("content"):
                sec["content"] = new_sec["content"]
            if new_sec.get("key_points"):
                sec["key_points"] = new_sec["key_points"]
            if isinstance(new_sec.get("chart"), dict):
                sec["chart"] = new_sec["chart"]
            sections[index] = sec
            data["sections"] = sections
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # 重新渲染 HTML（覆盖 report.html）
            try:
                report = coerce_report(data, data.get("meta", {}).get("type", "industry"),
                                       data.get("meta", {}).get("subject", ""))
                html = html_renderer.render(report.model_dump())
                with open(os.path.join(target, "report.html"), "w", encoding="utf-8") as f:
                    f.write(html)
                if "md" in os.listdir(target):
                    md = md_renderer.render(report.model_dump())
                    with open(os.path.join(target, "report.md"), "w", encoding="utf-8") as f:
                        f.write(md)
            except Exception as e:
                pass  # 渲染失败不阻塞返回，前端可刷新
            return self._json({"ok": True, "section": sec, "title": sec_title})

        # ----- /api/projects（创建项目 = 在 reports/ 下建目录） -----
        def _handle_create_project(self):
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = self.rfile.read(length).decode("utf-8")
                req = json.loads(body) if body else {}
            except Exception as e:
                return self._json({"error": f"无效 JSON: {e}"}, 400)
            name = self._safe_project(req.get("name"))
            if not name:
                return self._json({"error": "项目名不能为空或含非法字符"}, 400)
            os.makedirs(os.path.join(reports_dir, name), exist_ok=True)
            return self._json({"ok": True, "name": name, "projects": self._list_projects()})

        def _json(self, obj, code=200):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):  # noqa
            print(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}")

    # 多线程 TCPServer：SSE 生成请求是长连接（可达数分钟），若用单线程 TCPServer
    # 会阻塞浏览器加载页面 / 其他 API 请求。必须每个连接一个线程。
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", args.port), Handler) as httpd:
        url = f"http://127.0.0.1:{args.port}"
        print(f"🚀 Report Engine 已启动")
        print(f"   打开浏览器访问：{url}")
        print(f"   按 Ctrl+C 停止")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 已停止")
    return 0


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="商业分析报告生成器")
    sub = parser.add_subparsers(dest="cmd")

    g = sub.add_parser("gen", help="生成报告")
    g.add_argument("--type", choices=schemas.SUPPORTED_TYPES, required=True)
    g.add_argument("--subject", required=True, help="行业名 / 产品名 / 竞品组合")
    g.add_argument("--ai", choices=schemas.SUPPORTED_AI, default="mock")
    g.add_argument("--preset", help="mock 模式下使用哪份演示语料 (coffee / notion / notion-vs-obsidian)")
    g.add_argument("--formats", default="html,md", help="逗号分隔: html,md,pdf")
    g.add_argument("--out-dir", help="输出根目录（默认 ./reports）")
    g.add_argument("--from-json", help="跳过研究流水线，直接从 JSON 文件读取并渲染")
    g.add_argument("--market", help="市场范围（默认 全国）")
    g.add_argument("--time-range", help="时间范围（默认 近1年）")
    g.add_argument("--audience", help="目标读者（默认 普通读者）")
    g.set_defaults(func=cmd_gen)

    s = sub.add_parser("serve", help="启动网页后端")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    if args.cmd in ("gen", "serve"):
        return args.func(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
