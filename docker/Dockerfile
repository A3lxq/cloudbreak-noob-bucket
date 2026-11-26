FROM debian:12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-server \
        sudo \
        python3 \
        tar \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /data /opt/seed

COPY seed-public-assets/ /opt/seed/public-assets/
COPY seed-backups/ /opt/seed/backups/
COPY seed-private/ /opt/seed/private/
COPY generate_flags.py /opt/generate_flags.py
COPY s3server.py /opt/s3server.py
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

EXPOSE 22 9000

ENTRYPOINT ["/opt/entrypoint.sh"]
