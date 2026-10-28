FROM debian:12.9-slim
ARG APT_MIRROR=http://mirrors.ustc.edu.cn
RUN sed -i "s|http://deb.debian.org|${APT_MIRROR}|g; s|http://security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && printf 'Acquire::http::Timeout "30";\nAcquire::https::Timeout "30";\nAcquire::Retries "2";\n' > /etc/apt/apt.conf.d/80-download-timeout \
    && apt-get update -o APT::Update::Error-Mode=any \
    && apt-get install -y --no-install-recommends python3 suricata ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/ /app/
COPY rules/ /app/rules/
RUN mkdir -p /state && chown -R 10001:10001 /state
USER 10001:10001
ENV STATE_DIR=/state PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python3", "/app/server.py"]
