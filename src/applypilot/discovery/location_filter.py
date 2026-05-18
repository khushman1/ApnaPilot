"""Location filtering helpers shared by discovery scrapers."""

from __future__ import annotations

import re
from dataclasses import dataclass

REMOTE_TERMS = ("remote", "anywhere", "work from home", "wfh", "distributed")


@dataclass(frozen=True)
class LocationFilter:
    """Normalized location filtering config."""

    accept: tuple[str, ...]
    reject: tuple[str, ...]
    remote_anywhere: bool


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value or "").strip())
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            result.append(cleaned)
    return tuple(result)


def _derive_accept_patterns(search_cfg: dict) -> list[str]:
    patterns: list[str] = []

    default_location = search_cfg.get("defaults", {}).get("location")
    if default_location:
        patterns.append(default_location)

    country = search_cfg.get("country")
    if country:
        patterns.append(country)

    for loc in search_cfg.get("locations", []):
        location = loc.get("location") if isinstance(loc, dict) else loc
        if not location:
            continue
        patterns.append(location)
        for part in re.split(r"[,/|]", str(location)):
            part = part.strip()
            if len(part) >= 3:
                patterns.append(part)

    return patterns


def load_location_filter(search_cfg: dict | None) -> LocationFilter:
    """Load normalized accept/reject location rules from searches.yaml.

    Supports both the current nested schema:

        location:
          accept_patterns: [...]
          reject_patterns: [...]
          remote_anywhere: false

    and the older top-level keys:

        location_accept: [...]
        location_reject_non_remote: [...]

    If no explicit accept list is provided, derive one from configured search
    locations. When an accept list exists, remote jobs must match it unless
    `remote_anywhere: true` is set explicitly.
    """
    search_cfg = search_cfg or {}
    location_cfg = search_cfg.get("location", {}) or {}

    accept = list(search_cfg.get("location_accept", []) or [])
    accept.extend(location_cfg.get("accept_patterns", []) or [])
    if not accept:
        accept.extend(_derive_accept_patterns(search_cfg))

    reject = list(search_cfg.get("location_reject_non_remote", []) or [])
    reject.extend(location_cfg.get("reject_patterns", []) or [])

    accept_tuple = _dedupe(accept)
    remote_anywhere = location_cfg.get("remote_anywhere")
    if remote_anywhere is None:
        remote_anywhere = not bool(accept_tuple)

    return LocationFilter(
        accept=accept_tuple,
        reject=_dedupe(reject),
        remote_anywhere=bool(remote_anywhere),
    )


def location_ok(location: str | None, filt: LocationFilter) -> bool:
    """Return whether a job location is allowed by the normalized filter."""
    if not location:
        return True

    loc = location.lower()

    for pattern in filt.reject:
        if pattern.lower() in loc:
            return False

    has_remote_term = any(term in loc for term in REMOTE_TERMS)
    if has_remote_term and filt.remote_anywhere:
        return True

    for pattern in filt.accept:
        if pattern.lower() in loc:
            return True

    if has_remote_term:
        return False

    return not filt.accept
