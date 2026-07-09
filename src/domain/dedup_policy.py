from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_QUERY_PREFIXES = ("utm_", "fbclid", "gclid", "mc_eid", "mc_cid")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_job_url(url: str) -> str:
    normalized = url.strip()
    if not normalized:
        return ""

    parsed = urlparse(normalized)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"

    filtered_query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith(_TRACKING_QUERY_PREFIXES):
            continue
        filtered_query.append((key, value))
    filtered_query.sort()
    query = urlencode(filtered_query)

    return urlunparse((scheme, netloc, path, "", query, ""))


def compute_identity_key(*, url: str) -> str:
    return f"url:{normalize_job_url(url)}"


def derive_canonical_id(identity_key: str) -> str:
    digest = hashlib.sha256(identity_key.encode("utf-8")).hexdigest()[:32]
    return f"job-{digest}"


@dataclass(frozen=True, slots=True)
class JobDuplicateLink:
    canonical_id: str
    identity_key: str
    career_source_id: str
    external_id: str
    duplicate_reason: str
    suppressed_at: datetime = _utc_now()
