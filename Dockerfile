FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

# DB lives here (mounted as a volume in docker-compose)
ENV DB_PATH=/data/ledger.db \
    PORT=3000

VOLUME ["/data"]
EXPOSE 3000

CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 60 app:app"]
