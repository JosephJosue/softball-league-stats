"""Fuzzy player-name matching for imports.

GameChanger truncates last names differently depending on column width, so the
same player shows up as 'Leonardo V', 'Leonardo Vá', 'Leonardo Vásquez' across
games. We treat names as matching when one is a prefix of the other (after
folding accents and punctuation), which merges those variants while keeping
genuinely different people (e.g. 'Juan Diego T' vs 'Juan Diego V') apart.
"""

from __future__ import annotations

import re
import unicodedata


def normalize_name(name: str) -> str:
    """Fold accents, lowercase, strip non-alphanumerics. 'Leonardo Vá' -> 'leonardova'."""
    decomposed = unicodedata.normalize("NFKD", str(name))
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_only.lower())


def find_match(nkey: str, cache: list[dict]) -> dict | None:
    """Find the roster entry matching a normalized name key.

    `cache` is a list of dicts each having an 'nkey'. Returns an exact match if
    present; otherwise a prefix match ONLY when it's unambiguous (exactly one
    candidate). Ambiguous prefixes (e.g. bare 'Juan Diego' matching both
    'Juan Diego T' and 'Juan Diego V') return None so the caller can create a
    distinct player rather than guess.
    """
    if not nkey:
        return None
    for entry in cache:
        if entry["nkey"] == nkey:
            return entry
    prefix = [
        e for e in cache
        if e["nkey"] and (e["nkey"].startswith(nkey) or nkey.startswith(e["nkey"]))
    ]
    return prefix[0] if len(prefix) == 1 else None
