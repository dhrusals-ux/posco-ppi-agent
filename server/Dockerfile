# 매매일지 서버 이미지
#   docker build -f server/Dockerfile -t maemae-journal .
#   docker run -d -p 8000:8000 -v $PWD/data:/app/data \
#     -e TJ_SECRET="$(openssl rand -hex 32)" maemae-journal
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 TJ_DB=/app/data/journal.db

COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY server ./server
COPY trading-journal ./trading-journal

RUN mkdir -p /app/data
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
