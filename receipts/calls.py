"""The call format and its canonical JSON encoding (the exact bytes that get hashed)."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re

FIELDS = (
    "asset_type", "baseline", "confidence", "created_at", "direction", "event",
    "horizon_end_date", "horizon_start_date", "thesis_sha256", "ticker",
)
BASELINE = "close on horizon_start_date"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.\-/]{0,15}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class CallError(ValueError):
    pass


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate(call: dict) -> dict:
    """Check every field; returns a clean copy. Raises CallError with a plain-English reason."""
    if not isinstance(call, dict):
        raise CallError("a call must be a JSON object")
    extra = set(call) - set(FIELDS)
    missing = set(FIELDS) - set(call)
    if extra:
        raise CallError(f"unknown field(s): {sorted(extra)}")
    if missing:
        raise CallError(f"missing field(s): {sorted(missing)}")
    c = dict(call)
    if not isinstance(c["ticker"], str) or not _TICKER.match(c["ticker"]):
        raise CallError("ticker must be uppercase letters/digits, e.g. HOOD or PURR")
    if c["asset_type"] not in ("equity", "crypto"):
        raise CallError('asset_type must be "equity" or "crypto"')
    if not isinstance(c["event"], str) or not 1 <= len(c["event"]) <= 80:
        raise CallError("event must be 1-80 characters, e.g. \"Q4 FY2026 earnings\" or \"price horizon\"")
    if c["direction"] not in ("up", "down"):
        raise CallError('direction must be "up" or "down"')
    for k in ("horizon_start_date", "horizon_end_date"):
        if not isinstance(c[k], str) or not _DATE.match(c[k]):
            raise CallError(f"{k} must be YYYY-MM-DD")
        dt.date.fromisoformat(c[k])
    if c["horizon_end_date"] <= c["horizon_start_date"]:
        raise CallError("horizon_end_date must be after horizon_start_date")
    if c["baseline"] != BASELINE:
        raise CallError(f'baseline must be exactly "{BASELINE}"')
    conf = c["confidence"]
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0.5 <= conf <= 0.99:
        raise CallError("confidence must be a number from 0.50 to 0.99")
    if round(conf, 2) != conf:
        raise CallError("confidence: use at most 2 decimals (e.g. 0.65)")
    if not isinstance(c["thesis_sha256"], str) or not _HEX64.match(c["thesis_sha256"]):
        raise CallError("thesis_sha256 must be 64 lowercase hex characters")
    if not isinstance(c["created_at"], str) or not _TS.match(c["created_at"]):
        raise CallError("created_at must be UTC like 2027-01-20T14:00:00Z")
    return c


def canonical_json(call: dict) -> str:
    """Sorted keys, no whitespace, UTF-8. These exact bytes are what the commitment hashes."""
    return json.dumps(validate(call), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
