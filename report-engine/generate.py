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
import sys
import uuid
from datetime import datetime
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import schemas  # noqa: E402
from llm import extract_json, get_provider  # noqa: E402
from render import html_renderer, md_renderer, pdf_renderer  # noqa: E402
from report_model import Report, coerce_report  # noqa: E402


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
                on_progress=None) -> tuple[Report, dict[str, str], str]:
    """统一处理 CLI 与 HTTP 入口。返回 (Report, outputs, target_dir)。

    on_progress 回调用于 SSE 流式响应：
        on_progress(phase: str, message: str) -> None
        phase ∈ {"init", "llm", "render", "done", "error"}
    """
    if report_type not in schemas.SUPPORTED_TYPES:
        raise ValueError(f"type 必须是 {schemas.SUPPORTED_TYPES}，收到: {report_type}")

    def _progress(phase: str, msg: str):
        print(f"[{phase}] {msg}")
        if on_progress:
            try:
                on_progress(phase, msg)
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
        try:
            provider = get_provider(ai, preset=preset)
        except Exception as e:
            raise RuntimeError(f"LLM 初始化失败: {e}") from e
        system, user = load_prompt(report_type, subject)
        _progress("llm", f"🤖 调 LLM ({provider.name}) ...")
        report = call_llm_with_retry(provider, system, user)
        _progress("llm", "✅ LLM 返回完成")

    # 2) 强制覆盖关键 meta
    raw_dict = report.model_dump()
    coerced = coerce_report(raw_dict, report_type, subject)
    report = coerced

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
            return super().do_GET()

        def do_POST(self):  # noqa
            if self.path == "/api/generate":
                return self._handle_generate_sse()
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

            # SSE 头
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")  # 禁 nginx 缓冲
            self.end_headers()

            def emit(phase: str, message: str, **extra):
                payload = {"phase": phase, "message": message, **extra}
                line = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                try:
                    self.wfile.write(line.encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    # 客户端断开，吞掉异常
                    pass

            try:
                report, outputs, target = do_generate(
                    report_type=report_type,
                    subject=subject,
                    ai=ai,
                    preset=preset,
                    formats=formats,
                    out_root=reports_dir,
                    from_json=None,
                    on_progress=lambda phase, msg: emit(phase, msg),
                )
                # 终态事件
                emit("complete", "✅ 报告已生成", done=True, ok=True,
                     dir=os.path.relpath(target, workspace_root),
                     title=report.meta.title,
                     confidence=(report.meta.confidence.model_dump() if report.meta.confidence else None),
                     files={k: os.path.relpath(v, workspace_root) for k, v in outputs.items()},
                     preview=next((f"reports/{os.path.basename(target)}/report.html"
                                    for k in ("html",) if k in outputs), None))
            except Exception as e:
                emit("error", f"❌ {e}", done=True, ok=False, error=str(e))
            return

        # ----- /api/history -----
        def _json_history(self):
            items = []
            if os.path.exists(reports_dir):
                for entry in sorted(os.listdir(reports_dir), reverse=True):
                    full = os.path.join(reports_dir, entry)
                    if not os.path.isdir(full):
                        continue
                    json_path = os.path.join(full, "report.json")
                    if not os.path.exists(json_path):
                        continue
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            r = json.load(f)
                        meta = r.get("meta", {})
                        # P1: 只返回真实存在的文件
                        files: dict[str, str] = {}
                        for ext in ("html", "md", "pdf"):
                            p = os.path.join(full, f"report.{ext}")
                            if os.path.exists(p):
                                files[ext] = f"reports/{entry}/report.{ext}"
                        if not files:
                            continue
                        items.append({
                            "dir": entry,
                            "title": meta.get("title", entry),
                            "type": meta.get("type", ""),
                            "subject": meta.get("subject", ""),
                            "date": meta.get("generated_at", ""),
                            "files": files,
                            # 兼容字段：单一 html
                            "html": files.get("html", ""),
                        })
                    except Exception:
                        continue
            return self._json({"items": items})

        def _json(self, obj, code=200):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):  # noqa
            print(f"[{self.log_date_time_string()}] {self.address_string()} {format % args}")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as httpd:
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
    g.add_argument("--preset", help="mock 模式下使用哪份预生成报告 (coffee / notion / notion-vs-obsidian)")
    g.add_argument("--formats", default="html,md", help="逗号分隔: html,md,pdf")
    g.add_argument("--out-dir", help="输出根目录（默认 ./reports）")
    g.add_argument("--from-json", help="跳过 LLM，直接从 JSON 文件读取并渲染")
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
