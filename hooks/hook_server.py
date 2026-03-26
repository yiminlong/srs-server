"""
hook_server.py — Flask HTTP server that receives SRS event callbacks.

Endpoints (all POST):
    /on_connect     — client connects to SRS
    /on_close       — client disconnects
    /on_publish     — publisher starts a stream
    /on_unpublish   — publisher stops a stream
    /on_play        — viewer starts playback
    /on_stop        — viewer stops playback
    /on_dvr         — DVR segment written to disk

SRS expects a JSON response: {"code": 0} to allow, non-zero to reject.

Run:
    python hook_server.py
    # or via gunicorn:
    gunicorn -w 2 -b 0.0.0.0:5000 hook_server:app
"""

import logging
import os

from flask import Flask, jsonify, request

from on_dvr import handle_on_dvr
from on_publish import handle_on_publish, handle_on_unpublish

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)


def _ok():
    return jsonify({"code": 0}), 200


def _err(code: int, msg: str):
    return jsonify({"code": code, "msg": msg}), 200  # SRS reads the JSON code field


def _payload() -> dict:
    data = request.get_json(silent=True) or {}
    logger.debug("incoming payload: %s", data)
    return data


# ── Generic pass-through hooks ────────────────────────────────────────────────

@app.post("/on_connect")
def on_connect():
    data = _payload()
    logger.info(
        "on_connect  client_id=%s ip=%s app=%s",
        data.get("client_id"),
        data.get("ip"),
        data.get("app"),
    )
    return _ok()


@app.post("/on_close")
def on_close():
    data = _payload()
    logger.info(
        "on_close  client_id=%s ip=%s",
        data.get("client_id"),
        data.get("ip"),
    )
    return _ok()


@app.post("/on_play")
def on_play():
    data = _payload()
    logger.info(
        "on_play  app=%s stream=%s ip=%s",
        data.get("app"),
        data.get("stream"),
        data.get("ip"),
    )
    return _ok()


@app.post("/on_stop")
def on_stop():
    data = _payload()
    logger.info(
        "on_stop  app=%s stream=%s ip=%s",
        data.get("app"),
        data.get("stream"),
        data.get("ip"),
    )
    return _ok()


# ── Business-logic hooks ──────────────────────────────────────────────────────

@app.post("/on_publish")
def on_publish():
    data = _payload()
    code, msg = handle_on_publish(data)
    if code != 0:
        return _err(code, msg)
    return _ok()


@app.post("/on_unpublish")
def on_unpublish():
    data = _payload()
    code, msg = handle_on_unpublish(data)
    if code != 0:
        return _err(code, msg)
    return _ok()


@app.post("/on_dvr")
def on_dvr():
    data = _payload()
    code, msg = handle_on_dvr(data)
    if code != 0:
        return _err(code, msg)
    return _ok()


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("HOOK_PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    logger.info("hook server starting on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=debug)
