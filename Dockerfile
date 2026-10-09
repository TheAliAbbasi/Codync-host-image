# Unofficial thin image of one upstream Codync host archive.
# The publisher stages $TARGETARCH/{codync-host,LICENSE,...} before this build.
FROM ubuntu:24.04

ARG UPSTREAM_VERSION=unknown

LABEL org.opencontainers.image.title="codync-host" \
      org.opencontainers.image.description="Unofficial image of the Codync host" \
      org.opencontainers.image.source="https://github.com/TheAliAbbasi/codync-host-image" \
      org.opencontainers.image.url="https://github.com/leepokai/Codync" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${UPSTREAM_VERSION}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --home-dir /var/lib/codync-host --shell /usr/sbin/nologin codync \
    && mkdir -p /usr/local/share/codync-host \
    && chown codync:codync /var/lib/codync-host

ARG TARGETARCH
COPY ${TARGETARCH}/ /tmp/codync-host-stage/

# Filenames come from the archive. codync-screen and cua-driver are optional.
# LICENSE is the upstream license copied out of that archive.
RUN set -eu \
    && test -f /tmp/codync-host-stage/codync-host \
    && test -f /tmp/codync-host-stage/LICENSE \
    && install -m 0755 /tmp/codync-host-stage/codync-host /usr/local/bin/codync-host \
    && if [ -f /tmp/codync-host-stage/codync-screen ]; then \
         install -m 0755 /tmp/codync-host-stage/codync-screen /usr/local/bin/codync-screen; \
       fi \
    && if [ -f /tmp/codync-host-stage/cua-driver ]; then \
         install -m 0755 /tmp/codync-host-stage/cua-driver /usr/local/bin/cua-driver; \
       fi \
    && cp /tmp/codync-host-stage/LICENSE /usr/local/share/codync-host/LICENSE \
    && rm -rf /tmp/codync-host-stage

ENV HOME=/var/lib/codync-host
VOLUME /var/lib/codync-host
EXPOSE 19222
USER codync
WORKDIR /var/lib/codync-host
ENTRYPOINT ["codync-host"]
CMD ["serve"]
