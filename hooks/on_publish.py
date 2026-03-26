"""
on_publish.py — handler logic for SRS on_publish / on_unpublish callbacks.

SRS POSTs JSON to /on_publish when a stream starts being published,
and to /on_unpublish when the publisher disconnects.

Expected payload (SRS docs):
{
    "action":    "on_publish",
    "client_id": "9308h583",
    "ip":        "192.168.1.10",
    "vhost":     "__defaultVhost__",
    "app":       "live",
    "tcUrl":     "rtmp://x/live",
    "stream":    "livestream",
    "param":     "?token=abc123",
    "server_id": "vid-80h8v"
}

Return 0 in JSON body to allow; any non-zero code rejects the stream.
"""

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# Optional: pull a shared secret from env for stream-key auth
STREAM_SECRET = os.environ.get("STREAM_SECRET", "")


def handle_on_publish(data: dict[str, Any]) -> tuple[int, str]:
    """
    Validate an incoming publish request.

    Returns:
        (code, message) — code 0 means allowed, non-zero rejects the stream.
    """
    stream = data.get("stream", "")
    app = data.get("app", "")
    client_ip = data.get("ip", "unknown")
    param = data.get("param", "")

    logger.info(
        "on_publish  app=%s stream=%s ip=%s param=%s",
        app,
        stream,
        client_ip,
        param,
    )

    # ── Token / stream-key auth ──────────────────────────────────────────────────
    if STREAM_SECRET:
        # Expect ?token=<secret> in the RTMP publish URL param
        token = _parse_param(param, "token")
        if token != STREAM_SECRET:
            logger.warning(
                "on_publish REJECTED — bad token  stream=%s ip=%s", stream, client_ip
            )
            return 403, "invalid stream token"

    # ── Record publish start in a simple flat log ────────────────────────────────
    _append_event(
        {
            "event": "publish_start",
            "ts": int(time.time()),
            "app": app,
            "stream": stream,
            "ip": client_ip,
        }
    )

    logger.info("on_publish ALLOWED  app=%s stream=%s", app, stream)
    return 0, "ok"


def handle_on_unpublish(data: dict[str, Any]) -> tuple[int, str]:
    """
    Called when a publisher disconnects.
    """
    stream = data.get("stream", "")
    app = data.get("app", "")
    client_ip = data.get("ip", "unknown")

    logger.info("on_unpublish  app=%s stream=%s ip=%s", app, stream, client_ip)

    _append_event(
        {
            "event": "publish_stop",
            "ts": int(time.time()),
            "app": app,
            "stream": stream,
            "ip": client_ip,
        }
    )

    return 0, "ok"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_param(param: str, key: str) -> str:
    """Parse ?key=value from an RTMP param string."""
    param = param.lstrip("?")
    for pair in param.split("&"):
        if "=" in pair:
            k, _, v = pair.partition("=")
            if k == key:
                return v
    return ""


def _append_event(record: dict[str, Any]) -> None:
    """Append a JSON-lines entry to the publish event log."""
    import json

    log_path = os.environ.get("EVENT_LOG", "/app/logs/events.jsonl")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as exc:
        logger.error("Failed to write event log: %s", exc)
