"""Ingestion validation + column mapping (shared by the Excel and PDF parsers).

Responsibilities:
  * auto_map_columns  -> fuzzy-match messy headers to our canonical stat fields
  * validate_stat_rows -> coerce numbers, run the same logical checks as manual
    entry (reusing models.schemas), and split out a team-totals row if present
  * reconcile         -> warn when player rows don't sum to the team totals

Deliberately free of Streamlit/DB imports so it can be unit-tested in isolation.
"""

from __future__ import annotations

import re

import pandas as pd
from pydantic import ValidationError

from models.schemas import PlayerGameStatsCreate

# Canonical field -> accepted header spellings (normalized before matching).
COLUMN_ALIASES: dict[str, list[str]] = {
    "player_name": ["player", "name", "batter", "player name"],
    "team_name": ["team", "club"],
    "position": ["pos", "position"],
    # Batting
    "ab": ["ab", "at bats", "at-bats", "atbats"],
    "r": ["r", "run", "runs"],
    "h": ["h", "hit", "hits"],
    "rbi": ["rbi", "rbis", "runs batted in"],
    "bb": ["bb", "walk", "walks", "base on balls"],
    "so": ["so", "k", "ks", "strikeout", "strikeouts"],
    "doubles": ["2b", "double", "doubles"],
    "triples": ["3b", "triple", "triples"],
    "hr": ["hr", "hrs", "home run", "home runs", "homerun", "homeruns"],
    "lob": ["lob", "left on base"],
    "errors": ["e", "error", "errors"],
    # Pitching
    "ip": ["ip", "innings pitched", "innings"],
    "er": ["er", "earned runs"],
    "p_h": ["hits allowed", "ha", "h allowed"],
    "p_r": ["runs allowed", "ra", "r allowed"],
    "p_bb": ["walks allowed", "bb allowed"],
    "p_so": ["strikeouts pitched", "k allowed"],
    "p_hr": ["home runs allowed", "hr allowed"],
}

BATTING_FIELDS = ["ab", "r", "h", "rbi", "bb", "so", "doubles", "triples", "hr", "lob", "errors"]
PITCHING_INT_FIELDS = ["p_h", "p_r", "er", "p_bb", "p_so", "p_hr"]

# Rows whose "name" is one of these are treated as the team totals line.
_TOTALS_NAMES = {"total", "totals", "team", "teamtotals", "teamtotal"}


def _norm(value: object) -> str:
    """Normalize a header/cell for matching: lowercase, alphanumeric only."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


# Reverse lookup: normalized alias -> canonical field.
_ALIAS_TO_FIELD: dict[str, str] = {
    _norm(alias): field for field, aliases in COLUMN_ALIASES.items() for alias in aliases
}


def auto_map_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    """Rename recognized columns to canonical names.

    Returns (mapped_df, mapping, unmapped):
      * mapped_df  -> only the recognized columns, renamed to canonical fields
      * mapping    -> {original_header: canonical_field}
      * unmapped   -> original headers we couldn't recognize (shown as a warning)
    """
    mapping: dict[str, str] = {}
    unmapped: list[str] = []
    used: set[str] = set()

    for col in df.columns:
        field = _ALIAS_TO_FIELD.get(_norm(col))
        # Keep the first column that maps to a given field (ignore duplicates).
        if field and field not in used:
            mapping[col] = field
            used.add(field)
        else:
            unmapped.append(str(col))

    mapped_df = df[list(mapping.keys())].rename(columns=mapping)
    return mapped_df, mapping, unmapped


def _to_int(value: object) -> int:
    n = pd.to_numeric(value, errors="coerce")
    return 0 if pd.isna(n) else int(n)


def _to_int_or_none(value: object) -> int | None:
    n = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(n) else int(n)


def _to_float_or_none(value: object) -> float | None:
    n = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(n) else float(n)


def _extract_numbers(row: pd.Series) -> dict:
    """Pull canonical stat values from a mapped row (NaN-safe)."""
    out: dict = {}
    for f in BATTING_FIELDS:
        if f in row.index:
            out[f] = _to_int(row[f])
    if "ip" in row.index:
        ip = _to_float_or_none(row["ip"])
        if ip is not None:
            out["ip"] = ip
    for f in PITCHING_INT_FIELDS:
        if f in row.index:
            n = _to_int_or_none(row[f])
            if n is not None:
                out[f] = n
    return out


def _fmt_error(exc: ValidationError) -> str:
    """First validation message, stripped of Pydantic's wrapper text."""
    err = exc.errors()[0]
    return err.get("msg", "invalid value").replace("Value error, ", "")


def validate_stat_rows(
    mapped_df: pd.DataFrame,
) -> tuple[list[dict], dict | None, list[str]]:
    """Validate mapped rows into clean stat dicts.

    Returns (rows, team_totals, errors):
      * rows        -> validated player stat dicts (player_name + stats, no IDs)
      * team_totals -> numbers from a 'Totals' row if present, else None
      * errors      -> human-readable "Row N (name): message" strings
    """
    rows: list[dict] = []
    errors: list[str] = []
    team_totals: dict | None = None

    if mapped_df.empty or "player_name" not in mapped_df.columns:
        return rows, team_totals, ["No 'player'/'name' column found after mapping."]

    for i, (_, row) in enumerate(mapped_df.iterrows(), start=1):
        name = str(row.get("player_name") or "").strip()
        if not name:
            continue
        if _norm(name) in _TOTALS_NAMES:
            team_totals = _extract_numbers(row)
            continue

        stats = _extract_numbers(row)
        # Reuse the manual-entry validators (placeholder IDs, dropped after).
        try:
            PlayerGameStatsCreate(game_id="_", player_id="_", **stats)
        except ValidationError as exc:
            errors.append(f"Row {i} ({name}): {_fmt_error(exc)}")
            continue

        entry: dict = {"player_name": name, **stats}
        if "team_name" in row.index and pd.notna(row["team_name"]):
            entry["team_name"] = str(row["team_name"]).strip()
        if "position" in row.index and pd.notna(row["position"]):
            entry["position"] = str(row["position"]).strip().upper()
        rows.append(entry)

    return rows, team_totals, errors


def reconcile(rows: list[dict], team_totals: dict | None) -> list[str]:
    """Warn when summed player stats disagree with the team totals line."""
    warnings: list[str] = []
    if not team_totals:
        return warnings
    for field, label in [("h", "Hits"), ("r", "Runs"), ("ab", "At-bats")]:
        total = team_totals.get(field)
        if total is None:
            continue
        summed = sum(r.get(field, 0) for r in rows)
        if summed != total:
            warnings.append(f"{label}: player rows sum to {summed}, team total says {total}.")
    return warnings
