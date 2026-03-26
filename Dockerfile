# ── SRS (Simple Realtime Server) image ────────────────────────────────────────
# Based on the official SRS image; extends it with our custom config.
#
# Build:
#   docker build -t srs-server .
#
# Run standalone (without Compose):
#   docker run --rm -p 1935:1935 -p 8080:8080 -p 1985:1985 srs-server

FROM ossrs/srs:6

LABEL maintainer="srs-server"
LABEL description="SRS realtime streaming server with custom config, HLS, DVR, and HTTP hooks"

# ── Copy our config ────────────────────────────────────────────────────────────
COPY conf/srs.conf /usr/local/srs/conf/srs.conf

# ── Create DVR and log directories ─────────────────────────────────────────────
RUN mkdir -p /usr/local/srs/dvr /usr/local/srs/objs/logs

# ── Expose ports ───────────────────────────────────────────────────────────────
# 1935 — RTMP
# 8080 — HTTP (HLS, HTTP-FLV, console)
# 1985 — HTTP API
# 8000/udp — WebRTC (WHIP/WHEP)
EXPOSE 1935 8080 1985 8000/udp

WORKDIR /usr/local/srs

CMD ["./objs/srs", "-c", "conf/srs.conf"]
