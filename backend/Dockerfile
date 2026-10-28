FROM debian:12.9-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 suricata ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/ /app/
COPY rules/ /app/rules/
RUN mkdir -p /state && chown -R 10001:10001 /state
USER 10001:10001
ENV STATE_DIR=/state PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python3", "/app/server.py"]
