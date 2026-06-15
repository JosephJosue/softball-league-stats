"""Parser for the manually-compiled defensive-stats spreadsheet.

Maps Spanish/English headers (Jugador/J/PO/A/E/DP/OPO/TIRO BUENO/TIRO TOTALES)
to canonical fields, NaN-safe. Reuses the name normalization from validation.
"""

from __future__ import annotations

import pandas as pd

from ingestion.validation import _norm  # normalized-header matcher

# canonical field -> accepted header spellings (normalized before matching)
DEFENSE_ALIASES: dict[str, list[str]] = {
    "player_name": ["jugador", "player", "name"],
    "games": ["j", "juegos", "games", "g"],
    "po": ["po", "putouts"],
    "a": ["a", "asistencias", "assists"],
    "e": ["e", "errores", "errors"],
    "dp": ["dp", "double plays", "dobles plays"],
    "opo": ["opo", "oportunidades", "chances"],
    "good_throws": ["tiro bueno", "good throws"],
    "total_throws": ["tiro totales", "total throws", "tiros totales"],
}

_INT_FIELDS = ["games", "po", "a", "e", "dp", "opo", "good_throws", "total_throws"]
_ALIAS_TO_FIELD = {
    _norm(alias): field for field, aliases in DEFENSE_ALIASES.items() for alias in aliases
}


def looks_like_defense(df: pd.DataFrame) -> bool:
    """True if the table has the hallmark defensive columns (PO + A + DP)."""
    fields = {_ALIAS_TO_FIELD.get(_norm(c)) for c in df.columns}
    return {"po", "a", "dp"}.issubset(fields)


def _to_int(value: object) -> int:
    n = pd.to_numeric(value, errors="coerce")
    return 0 if pd.isna(n) else int(n)


def parse(df: pd.DataFrame) -> tuple[list[dict], list[str]]:
    """Return (rows, errors). Each row: player_name + integer defensive stats."""
    mapping = {c: _ALIAS_TO_FIELD[_norm(c)] for c in df.columns if _norm(c) in _ALIAS_TO_FIELD}
    if "player_name" not in mapping.values():
        return [], ["No 'Jugador'/player column found."]
    mapped = df[list(mapping)].rename(columns=mapping)

    rows: list[dict] = []
    for _, row in mapped.iterrows():
        name = str(row.get("player_name") or "").strip()
        if not name or name.lower() == "nan":
            continue
        entry = {"player_name": name}
        for f in _INT_FIELDS:
            if f in mapped.columns:
                entry[f] = _to_int(row[f])
        rows.append(entry)
    return rows, []
