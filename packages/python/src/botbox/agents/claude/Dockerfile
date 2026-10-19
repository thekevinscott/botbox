FROM node:24.20.0-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code@2.1.296

RUN usermod --login user --home /home/user --move-home node && groupmod --new-name user node

RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} +

USER user

ENV DISABLE_AUTOUPDATER=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    CLAUDE_CONFIG_DIR=/home/user/.claude
