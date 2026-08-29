"""Data pipeline for HeatGov AI.

Shared helpers used by the ``pull_*`` scripts:

* building an authenticated FortyGuard client
* metering the real credit cost of every fetch
* a *fingerprinted* cache

The fingerprint is the important part. A cached Parquet file is only reused
when the SHA-256 of the request that produced it still matches the request we
are about to make. Change the study polygon, the dates or the threshold and the
fingerprint changes, so the stale file is refetched instead of being silently
reused against a different area.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config  # noqa: E402
from fortyguard import FortyGuardClient  # noqa: E402

__all__ = [
    "make_client",
    "fingerprint",
    "CreditMeter",
    "cache_status",
    "write_meta",
    "load_manifest",
    "record_manifest",
    "utc_now",
    "rule",
]


def make_client() -> FortyGuardClient:
    """Return a client authenticated from the .env file."""
    if not config.FORTYGUARD_API_KEY:
        raise RuntimeError(
            "FORTYGUARD_API_KEY is missing. Copy .env.example to .env and fill it in."
        )
    return FortyGuardClient(
        api_key=config.FORTYGUARD_API_KEY,
        base_url=config.FORTYGUARD_BASE_URL,
        timeout=120.0,
    )


def fingerprint(payload: dict) -> str:
    """Stable short hash of a request payload."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rule(char: str = "-", width: int = 78) -> str:
    return char * width


class CreditMeter:
    """Reads the billing endpoint so every fetch reports its true cost."""

    def __init__(self, client: FortyGuardClient) -> None:
        self.client = client
        self.session_start = self.used()

    def _summary(self) -> dict:
        return self.client.fetch_api_key_usage()["credit_summary"]

    def used(self) -> int:
        return int(self._summary()["total_credits_used"])

    def remaining(self) -> int:
        return int(self._summary()["total_remaining_credits"])

    def session_total(self) -> int:
        return self.used() - self.session_start


def cache_status(key: str, fp: str) -> str:
    """Return 'hit', 'stale' or 'miss' for a cached dataset.

    * hit   - file exists and its fingerprint matches the pending request
    * stale - file exists but was produced by a different request
    * miss  - no file at all
    """
    path = config.cache_path(key)
    meta = config.meta_path(key)
    if not path.exists():
        return "miss"
    if not meta.exists():
        return "stale"
    try:
        stored = json.loads(meta.read_text(encoding="utf-8")).get("fingerprint")
    except json.JSONDecodeError:
        return "stale"
    return "hit" if stored == fp else "stale"


def write_meta(key: str, entry: dict) -> None:
    config.meta_path(key).write_text(json.dumps(entry, indent=2), encoding="utf-8")


def load_manifest() -> dict:
    if config.MANIFEST_PATH.exists():
        try:
            return json.loads(config.MANIFEST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def record_manifest(key: str, entry: dict) -> None:
    manifest = load_manifest()
    manifest[key] = entry
    config.MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
