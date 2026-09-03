# Report Engine 部署镜像
# 构建: docker build -t report-engine .
# 运行: docker run -p 8781:8781 -e OPENAI_API_KEY=sk-xxx -v $PWD/reports:/app/reports report-engine
FROM python:3.13-slim

# weasyprint 依赖（PDF 渲染）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libffi-dev fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY report-engine/requirements.txt report-engine/requirements.txt
RUN pip install --no-cache-dir -r report-engine/requirements.txt

COPY report-engine report-engine
COPY web web

WORKDIR /app/report-engine

ENV OPENAI_BASE_URL="https://api.deepseek.com"
ENV OPENAI_MODEL="deepseek-v4-flash"
ENV PORT=8781

EXPOSE 8781
CMD ["sh", "-c", "python generate.py serve --port $PORT"]
