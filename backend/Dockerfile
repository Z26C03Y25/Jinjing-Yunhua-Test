FROM debian:12.9-slim
ARG APT_MIRROR=http://mirrors.ustc.edu.cn
ARG SURICATA_VERSION=1:7.0.10-1~bpo12+1
RUN sed -i "s|http://deb.debian.org|${APT_MIRROR}|g; s|http://security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && printf 'deb %s/debian bookworm-backports main\n' "${APT_MIRROR}" > /etc/apt/sources.list.d/backports.list \
    && printf 'Acquire::http::Timeout "30";\nAcquire::https::Timeout "30";\nAcquire::Retries "2";\n' > /etc/apt/apt.conf.d/80-download-timeout \
    && apt-get update -o APT::Update::Error-Mode=any \
    && apt-get install -y --no-install-recommends python3 ca-certificates \
    && apt-get install -y --no-install-recommends -t bookworm-backports "suricata=${SURICATA_VERSION}" \
    && suricata --build-info \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/ /app/
COPY rules/ /app/rules/
RUN dpkg-query -W -f='${Package}\t${Version}\n' > /app/system-packages.tsv \
    && suricata --build-info > /app/engine-build-info.txt
RUN chmod -R a+rX /app && mkdir -p /state && chown -R 10001:10001 /state
USER 10001:10001
ENV STATE_DIR=/state PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python3", "/app/server.py"]
