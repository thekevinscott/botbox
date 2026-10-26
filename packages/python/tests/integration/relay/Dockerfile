# The relay with what it needs at runtime, plus kcov. Like the agent images, /bin/sh is dash
# and /etc/passwd is writable.
FROM kcov/kcov@sha256:481289ae32e55e5b733019515acd10948a4f76dfed381765577db909664fc603

RUN apt-get update \
    && apt-get install -y --no-install-recommends socat \
    && rm -rf /var/lib/apt/lists/* \
    && chmod 666 /etc/passwd \
    && mkdir -m 1777 /run/botbox /cov

COPY --chmod=755 fakes /opt/fakes
COPY --from=botbox --chmod=755 botbox-relay /usr/local/bin/botbox-relay

ENTRYPOINT []
