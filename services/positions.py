"""Read-only access to the seeded `positions` reference table.

(Not in the original plan's file list, but positions are needed by the players,
stats, and UI layers, so a tiny dedicated module keeps lookups in one place.)
"""

from __future__ import annotations

import pandas as pd
from supabase import Client

from services._base import resolve_client, to_df

TABLE = "positions"


def list_positions(client: Client | None = None) -> pd.DataFrame:
    """All positions ordered by category then code."""
    resp = (
        resolve_client(client)
        .table(TABLE)
        .select("*")
        .order("category")
        .order("code")
        .execute()
    )
    return to_df(resp)


def code_to_id(client: Client | None = None) -> dict[str, str]:
    """Map position code ('SS') -> id. Handy for ingestion/forms."""
    df = list_positions(client)
    if df.empty:
        return {}
    return dict(zip(df["code"], df["id"]))


def id_to_code(client: Client | None = None) -> dict[str, str]:
    """Map position id -> code, for labeling rows pulled from the DB."""
    df = list_positions(client)
    if df.empty:
        return {}
    return dict(zip(df["id"], df["code"]))
