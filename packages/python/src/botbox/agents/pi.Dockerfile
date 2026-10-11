FROM node:24.20.0-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates ripgrep fd-find && \
    rm -rf /var/lib/apt/lists/* && \
    ln -s /usr/bin/fdfind /usr/local/bin/fd

RUN npm install -g @earendil-works/pi-coding-agent@0.74.0

RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} +

USER node

ENV PI_CODING_AGENT_DIR=/home/node/.pi/agent
