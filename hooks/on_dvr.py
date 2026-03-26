"""
on_dvr.py — handler logic for SRS on_dvr callback.

SRS POSTs JSON to /on_dvr when a DVR segment (FLV file) has been written
to disk and is ready for post-processing (e.g. upload to S3, remux to MP4,
generate thumbnail, update a database).

Expected payload (SRS docs):
{
    "action":    "on_dvr",
    "client_id": "9308h583",
    "ip":        "192.168.1.10",
    "vhost":     "__defaultVhost__",
    "app":       "live",
    "stream":    "livestream",
    "param":     "",
    "cwd":       "/usr/local/srs",
    "file":      "./dvr/live/livestream.1711234567.flv"
}
"""

import json
import logging
import os
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)

DVR_OUTPUT_DIR = os.environ.get("DVR_OUTPUT_DIR", "/app/dvr")
S3_BUCKET = os.environ.get("S3_BUCKET", "")           # optional S3 upload
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")


def handle_on_dvr(data: dict[str, Any]) -> tuple[int, str]:
    """
    Process a completed DVR segment.

    Pipeline:
        1. Resolve the absolute path of the recorded FLV.
        2. Remux FLV → MP4 with FFmpeg (fast copy, no re-encode).
        3. Optionally upload the MP4 to S3.
        4. Log the event.

    Returns:
        (code, message) — SRS ignores the return value for on_dvr,
        but we still return 0 on success and non-zero on failure.
    """
    cwd = data.get("cwd", "/usr/local/srs")
    raw_path = data.get("file", "")
    app = data.get("app", "")
    stream = data.get("stream", "")

    # Resolve to absolute path
    flv_path = raw_path if os.path.isabs(raw_path) else os.path.join(cwd, raw_path)
    flv_path = os.path.normpath(flv_path)

    logger.info("on_dvr  app=%s stream=%s file=%s", app, stream, flv_path)

    if not os.path.isfile(flv_path):
        logger.error("on_dvr: file not found: %s", flv_path)
        return 500, "file not found"

    # ── Remux FLV → MP4 ──────────────────────────────────────────────────────────
    mp4_path = _flv_to_mp4(flv_path)
    if mp4_path is None:
        return 500, "remux failed"

    # ── Optional S3 upload ────────────────────────────────────────────────────────
    if S3_BUCKET:
        _upload_to_s3(mp4_path, app, stream)

    # ── Record DVR event ──────────────────────────────────────────────────────────
    _append_event(
        {
            "event": "dvr_segment",
            "ts": int(time.time()),
            "app": app,
            "stream": stream,
            "flv": flv_path,
            "mp4": mp4_path,
        }
    )

    return 0, "ok"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _flv_to_mp4(flv_path: str) -> str | None:
    """
    Remux an FLV file to MP4 using FFmpeg stream copy.
    Saves the MP4 alongside the FLV in DVR_OUTPUT_DIR.
    Returns the MP4 path on success, None on failure.
    """
    base = os.path.splitext(os.path.basename(flv_path))[0]
    out_dir = DVR_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    mp4_path = os.path.join(out_dir, base + ".mp4")

    cmd = [
        FFMPEG_BIN,
        "-y",                   # overwrite if exists
        "-i", flv_path,
        "-c", "copy",           # stream copy, no re-encode
        "-movflags", "+faststart",
        mp4_path,
    ]

    logger.info("remuxing  %s → %s", flv_path, mp4_path)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            logger.error("ffmpeg failed:\n%s", result.stderr)
            return None
        logger.info("remux OK  %s", mp4_path)
        return mp4_path
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("ffmpeg error: %s", exc)
        return None


def _upload_to_s3(mp4_path: str, app: str, stream: str) -> None:
    """
    Upload the MP4 to S3 using the AWS CLI.
    Requires AWS credentials in the environment (AWS_ACCESS_KEY_ID, etc.)
    or an IAM instance role.
    """
    key = f"{app}/{stream}/{os.path.basename(mp4_path)}"
    cmd = ["aws", "s3", "cp", mp4_path, f"s3://{S3_BUCKET}/{key}", "--no-progress"]
    logger.info("uploading to s3://%s/%s", S3_BUCKET, key)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logger.error("s3 upload failed:\n%s", result.stderr)
        else:
            logger.info("s3 upload OK  s3://%s/%s", S3_BUCKET, key)
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("s3 upload error: %s", exc)


def _append_event(record: dict[str, Any]) -> None:
    log_path = os.environ.get("EVENT_LOG", "/app/logs/events.jsonl")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as exc:
        logger.error("Failed to write event log: %s", exc)
