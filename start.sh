#!/usr/bin/env bash
# 一键启动 Report Engine（本地开发 / 部署）
# 用法: ./start.sh [--port 8781]
set -e
cd "$(dirname "$0")"

PORT=8781
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

# bash 不读 ~/.zshrc：若环境变量未导出，从 .zshrc 补充 OPENAI_*
if [ -z "$OPENAI_API_KEY" ] && [ -f "$HOME/.zshrc" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$HOME/.zshrc" >/dev/null 2>&1 || true
  set +a
fi

if [ -z "$OPENAI_API_KEY" ]; then
  echo "⚠️  未检测到 OPENAI_API_KEY。"
  echo "   请在 ~/.zshrc 中配置后重试："
  echo "     export OPENAI_API_KEY=sk-xxx"
  echo "     export OPENAI_BASE_URL=https://api.deepseek.com"
  echo "     export OPENAI_MODEL=deepseek-v4-flash"
  echo "   前端未配置 key 时生成会失败。"
  exit 1
fi
echo "🤖 真实模型: ${OPENAI_MODEL:-未设置} (${OPENAI_BASE_URL:-https://api.openai.com/v1})"

cd report-engine
if [ ! -d .venv ]; then
  echo "📦 创建虚拟环境 .venv ..."
  python3 -m venv .venv
fi
echo "📦 安装依赖 ..."
.venv/bin/pip install -q -r requirements.txt

echo "🚀 启动服务: http://127.0.0.1:$PORT"
exec .venv/bin/python generate.py serve --port "$PORT"
