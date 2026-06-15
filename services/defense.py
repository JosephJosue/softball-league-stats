"""Read/write + aggregation for manually-compiled defensive stats.

Source data is per-player (PO/A/E/DP, chances, throws). Fielding % and throw
accuracy are derived here so the UI/predictions don't duplicate the math.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from supabase import Client

from services._base import first, resolve_client, to_df

TABLE = "player_defensive_stats"
SUM_COLS = ["games", "po", "a", "e", "dp", "opo", "good_throws", "total_throws"]


def list_defense(client: Client | None = None, season: str | None = None) -> pd.DataFrame:
    """Raw defensive rows (optionally filtered by season)."""
    query = resolve_client(client).table(TABLE).select("*")
    if season:
        query = query.eq("season", season)
    return to_df(query.execute())


def upsert_defense(payload: dict, client: Client | None = None) -> dict | None:
    """Insert/update a player's defensive line. Requires authed client."""
    resp = (
        resolve_client(client)
        .table(TABLE)
        .upsert(payload, on_conflict="player_id,season")
        .execute()
    )
    return first(resp)


def fielding_pct(po: int, a: int, e: int) -> float | None:
    """Fielding % = (PO + A) / (PO + A + E); None when no chances."""
    chances = po + a + e
    return round((po + a) / chances, 3) if chances else None


def by_player(client: Client | None = None, season: str | None = None) -> pd.DataFrame:
    """One row per player: summed counting stats + fielding % + throw accuracy."""
    df = list_defense(client, season)
    if df.empty:
        return df
    present = [c for c in SUM_COLS if c in df.columns]
    g = df.groupby("player_id", as_index=False)[present].sum()
    chances = (g["po"] + g["a"] + g["e"]).replace(0, np.nan)
    g["fpct"] = ((g["po"] + g["a"]) / chances).round(3)
    tt = g["total_throws"].replace(0, np.nan)
    g["throw_pct"] = (g["good_throws"] / tt).round(3)
    return g
