**Fixed**: SIGTERM while a box's agent container is starting no longer leaves that container behind. The container is named (`botbox-agent-<id>`) and recorded for removal before Docker creates it.
