FROM node:24.20.0-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates python3 ripgrep fd-find && \
    rm -rf /var/lib/apt/lists/* && \
    ln -s /usr/bin/fdfind /usr/local/bin/fd

RUN npm install -g @earendil-works/pi-coding-agent@0.74.0

RUN usermod --login user --home /home/user --move-home node && groupmod --new-name user node

RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} +

USER user

ENV PI_CODING_AGENT_DIR=/home/user/.pi/agent
