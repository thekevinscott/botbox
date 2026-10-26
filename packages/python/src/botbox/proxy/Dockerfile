FROM alpine:3.22.2@sha256:4b7ce07002c69e8f3d704a9c5d6fd3053be500b7f1c69fc0d80990c2ad8dd412

RUN apk add --no-cache tinyproxy=1.11.2-r0 socat=1.8.1.3-r0

COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
COPY --chmod=755 botbox-proxy /usr/local/bin/botbox-proxy
# The run's empty volume mounted here copies this directory's owner and mode, so the proxy can
# make its socket there. The credential proxy runs in gid 101 too and makes its own; the sticky
# bit stops it removing the proxy's. botbox-proxy writes the filter from the environment.
RUN install -d -o tinyproxy -g tinyproxy -m 1775 /run/botbox \
    && install -o tinyproxy -g tinyproxy -m 0644 /dev/null /etc/tinyproxy/filter

# tinyproxy's `User` line is a setuid(2) needing CAP_SETUID: under cap_drop=ALL it exits 77.
# A uid apart from the agent's, so the agent can't signal or trace the proxy it shares PIDs with.
USER tinyproxy

CMD ["/usr/local/bin/botbox-proxy"]
