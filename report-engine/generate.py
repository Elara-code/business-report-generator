"""Report Engine 主入口。

Usage:
  python generate.py --type industry  --subject "咖啡"          --ai mock --out ./reports
  python generate.py --type product   --subject "Notion"        --ai openai --formats html,md,pdf
  python generate.py --type competitor --subject "Notion vs Obsidian" --ai workbuddy --preset notion-vs-obsidian
  python generate.py --type industry  --subject "咖啡" --serve 8080   # 启动 Web 后端
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import schemas  # noqa: E402
from llm import extract_json, get_provider  # noqa: E402
from render import html_renderer, md_renderer, pdf_renderer  # noqa: E402


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


def fix_meta(report: dict, report_type: str, subject: str) -> dict:
    """补全 / 修正 meta 字段，保证渲染器能跑。"""
    report.setdefault("meta", {})
    report["meta"].setdefault("type", report_type)
    report["meta"].setdefault("subject", subject)
    report["meta"].setdefault("generated_at", datetime.now().isoformat(timespec="seconds"))
    report["meta"].setdefault("title", f"{subject}分析报告")
    report.setdefault("summary", "")
    report.setdefault("sections", [])
    report.setdefault("appendix", {"data_sources": [], "limitations": ""})
    # 给没有图表的章节加占位（但保持尽量不破坏原始内容）
    return report


def save_report_json(report: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path


def render_formats(report: dict, formats: list[str], out_dir: str) -> dict[str, str]:
    outputs: dict[str, str] = {}
    if "html" in formats:
        html = html_renderer.render(report)
        p = os.path.join(out_dir, "report.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(html)
        outputs["html"] = p
    if "md" in formats:
        md = md_renderer.render(report)
        p = os.path.join(out_dir, "report.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(md)
        outputs["md"] = p
    if "pdf" in formats:
        try:
            p = pdf_renderer.render(report, os.path.join(out_dir, "report.pdf"))
            outputs["pdf"] = p
        except Exception as e:
            outputs["pdf_error"] = str(e)
    return outputs


def make_out_dir(root: str, report_type: str, subject: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in subject).strip().replace(" ", "_")
    safe = safe[:40] or "report"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(root, f"{stamp}_{report_type}_{safe}")


def cmd_generate(args) -> int:
    if args.type not in schemas.SUPPORTED_TYPES:
        print(f"❌ --type 必须是 {schemas.SUPPORTED_TYPES}", file=sys.stderr)
        return 2

    # 1) 取报告 JSON
    if args.from_json:
        with open(args.from_json, "r", encoding="utf-8") as f:
            raw = f.read()
        print(f"📂 从 {args.from_json} 读取报告")
    else:
        try:
            provider = get_provider(args.ai, preset=args.preset)
        except Exception as e:
            print(f"❌ LLM 初始化失败: {e}", file=sys.stderr)
            return 1
        system, user = load_prompt(args.type, args.subject)
        print(f"🤖 调 LLM ({provider.name}) 生成 {args.type} 报告：{args.subject}")
        raw = provider.complete(system, user, json_mode=True)
        try:
            report = extract_json(raw)
        except Exception as e:
            print(f"❌ JSON 解析失败: {e}\n原始输出片段：\n{raw[:500]}", file=sys.stderr)
            return 1

    report = fix_meta(report, args.type, args.subject)

    # 2) 输出
    out_dir = args.out_dir or os.path.join(
        os.path.dirname(HERE), "reports"
    )
    target = make_out_dir(out_dir, args.type, args.subject)
    save_report_json(report, target)
    outputs = render_formats(report, args.formats, target)
    print(f"✅ 已生成报告 → {target}")
    for k, v in outputs.items():
        if k.endswith("_error"):
            print(f"  ⚠️  {k}: {v}")
        else:
            rel = os.path.relpath(v, HERE)
            print(f"  • {k}: {rel}")
    return 0


def cmd_serve(args) -> int:
    """启动一个简易 HTTP 服务：静态网页 + /api/generate JSON 接口。"""
    import http.server
    import socketserver
    import threading
    import urllib.parse

    web_dir = os.path.join(os.path.dirname(HERE), "web")
    reports_dir = os.path.join(os.path.dirname(HERE), "reports")
    os.makedirs(reports_dir, exist_ok=True)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            # 用工作区根目录作为基础（这样 web/* 和 reports/* 都能服务）
            super().__init__(*a, directory=os.path.dirname(HERE), **kw)

        def do_POST(self):  # noqa
            if self.path == "/api/generate":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                try:
                    req = json.loads(body)
                except Exception as e:
                    self._json({"error": f"无效 JSON: {e}"}, 400)
                    return
                # 转发到 generate 流程
                report_type = req.get("type", "industry")
                subject = req.get("subject", "未命名")
                ai = req.get("ai", "mock")
                formats = req.get("formats", ["html"])
                preset = req.get("preset")

                try:
                    provider = get_provider(ai, preset=preset)
                except Exception as e:
                    self._json({"error": f"AI 初始化失败: {e}"}, 500)
                    return
                system, user = load_prompt(report_type, subject)
                raw = provider.complete(system, user, json_mode=True)
                try:
                    report = extract_json(raw)
                except Exception as e:
                    self._json({"error": f"JSON 解析失败: {e}", "raw": raw[:500]}, 500)
                    return
                report = fix_meta(report, report_type, subject)
                target = make_out_dir(reports_dir, report_type, subject)
                save_report_json(report, target)
                outputs = render_formats(report, formats, target)
                self._json({
                    "ok": True,
                    "dir": target,
                    "files": {k: os.path.relpath(v, os.path.dirname(HERE)) for k, v in outputs.items()},
                })
            else:
                self._json({"error": "Not Found"}, 404)

        def do_GET(self):  # noqa
            if self.path == "/api/history":
                self._json_history()
                return
            return super().do_GET()

        def _json(self, obj, code=200):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

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
                        items.append({
                            "dir": entry,
                            "title": meta.get("title", entry),
                            "type": meta.get("type", ""),
                            "subject": meta.get("subject", ""),
                            "date": meta.get("generated_at", ""),
                            "html": f"reports/{entry}/report.html",
                            "md": f"reports/{entry}/report.md",
                        })
                    except Exception:
                        continue
            self._json({"items": items})

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


def main():
    parser = argparse.ArgumentParser(description="商业分析报告生成器")
    sub = parser.add_subparsers(dest="cmd")

    g = sub.add_parser("gen", help="生成报告")
    g.add_argument("--type", choices=schemas.SUPPORTED_TYPES, required=True)
    g.add_argument("--subject", required=True, help="行业名 / 产品名 / 竞品组合")
    g.add_argument("--ai", choices=schemas.SUPPORTED_AI, default="mock")
    g.add_argument("--preset", help="WorkBuddy/Mock 模式下使用哪份预生成报告 (coffee / notion / notion-vs-obsidian)")
    g.add_argument("--formats", default="html,md", help="逗号分隔: html,md,pdf")
    g.add_argument("--out-dir", help="输出根目录（默认 ./reports）")
    g.add_argument("--from-json", help="跳过 LLM，直接从 JSON 文件读取")
    g.set_defaults(func=cmd_generate)

    s = sub.add_parser("serve", help="启动网页后端")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_serve)

    # 向后兼容：老式参数也可直接 generate
    parser.add_argument("--type", choices=schemas.SUPPORTED_TYPES)
    parser.add_argument("--subject")
    parser.add_argument("--ai", choices=schemas.SUPPORTED_AI, default="mock")
    parser.add_argument("--preset")
    parser.add_argument("--formats", default="html,md")
    parser.add_argument("--out-dir")
    parser.add_argument("--from-json")
    parser.add_argument("--serve", type=int, nargs="?", const=8765, default=None)
    parser.add_argument("--port", type=int, default=8765)

    args = parser.parse_args()

    if args.cmd == "gen":
        return args.func(args)
    if args.cmd == "serve":
        return args.func(args)
    # 默认 generate 模式
    if args.subject and args.type:
        return cmd_generate(args)
    if args.serve is not None:
        args.port = args.serve
        return cmd_serve(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
