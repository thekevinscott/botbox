FROM node:24.20.0-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates socat && \
    rm -rf /var/lib/apt/lists/*

RUN npm install -g @openai/codex@0.162.1

RUN usermod --login user --home /home/user --move-home node && groupmod --new-name user node

# The agent runs as the host's uid, which may not be this one.
RUN mkdir -p /home/user/.codex/sessions && \
    cd /home/user && chmod 777 . .codex .codex/sessions

RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} + && chmod 666 /etc/passwd

COPY --from=botbox --chmod=755 botbox-relay /usr/local/bin/botbox-relay

USER user

ENV CODEX_HOME=/home/user/.codex
