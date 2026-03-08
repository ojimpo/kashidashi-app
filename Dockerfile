FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    KASHIDASHI_PORT=18080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests
COPY docs ./docs
COPY package.json ./

RUN mkdir -p /data

EXPOSE 18080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${KASHIDASHI_PORT:-18080}"]
