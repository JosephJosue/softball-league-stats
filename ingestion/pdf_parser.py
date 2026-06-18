"""PDF scorecard parsing with pdfplumber.

Scorecards vary wildly, so this is best-effort: extract every table on every
page, then pick the one that looks most like a stat sheet (the most columns we
recognize, and a player/name column present). The chosen raw table is handed
back for the same auto-mapping + validation pipeline used for Excel.
"""

from __future__ import annotations

import io

import pandas as pd
import pdfplumber

from ingestion.validation import auto_map_columns


def extract_tables(data: bytes) -> list[pd.DataFrame]:
    """Every table found across all pages (first row treated as the header)."""
    tables: list[pd.DataFrame] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            for raw in page.extract_tables():
                if raw and len(raw) > 1:
                    header, *body = raw
                    # Replace blank/None headers with positional names.
                    cols = [c if c else f"col_{i}" for i, c in enumerate(header)]
                    tables.append(pd.DataFrame(body, columns=cols))
    return tables


def _score(df: pd.DataFrame) -> int:
    """How stat-sheet-like a table is: recognized columns, 0 if no player col."""
    _, mapping, _ = auto_map_columns(df)
    fields = set(mapping.values())
    return len(fields) if "player_name" in fields else 0


def extract_best_stat_table(data: bytes) -> pd.DataFrame | None:
    """Return the most stat-like table, or None if nothing usable was found."""
    best: pd.DataFrame | None = None
    best_score = 0
    for df in extract_tables(data):
        s = _score(df)
        if s > best_score:
            best, best_score = df, s
    return best


def extract_text(data: bytes) -> str:
    """All page text concatenated (useful for debugging tricky scorecards)."""
    chunks: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks)
