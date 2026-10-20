FROM node:24.20.0-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN npm install -g @openai/codex@0.162.1

RUN usermod --login user --home /home/user --move-home node && groupmod --new-name user node

RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} +

USER user

ENV CODEX_HOME=/home/user/.codex
