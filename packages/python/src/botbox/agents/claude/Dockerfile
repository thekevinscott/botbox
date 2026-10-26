FROM node:24.20.0-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates socat && \
    rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code@2.1.296

RUN usermod --login user --home /home/user --move-home node && groupmod --new-name user node

# The agent runs as the host's uid, which may not be this one.
RUN mkdir -p /home/user/.claude/projects && \
    cd /home/user && chmod 777 . .claude .claude/projects

RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} + && chmod 666 /etc/passwd

COPY --from=botbox --chmod=755 botbox-relay /usr/local/bin/botbox-relay

USER user

ENV DISABLE_AUTOUPDATER=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    CLAUDE_CONFIG_DIR=/home/user/.claude
