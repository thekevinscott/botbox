FROM alpine:3.22.2@sha256:4b7ce07002c69e8f3d704a9c5d6fd3053be500b7f1c69fc0d80990c2ad8dd412

RUN apk add --no-cache tinyproxy=1.11.2-r0

COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf

# tinyproxy's `User` line is a setuid(2) needing CAP_SETUID: under cap_drop=ALL it exits 77.
USER tinyproxy

CMD ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
