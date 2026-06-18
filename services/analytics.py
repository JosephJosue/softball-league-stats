"""Read-only analytics, backed by the SQL views created in db/schema.sql.

The views (v_player_season_totals, v_team_season_totals, v_position_leaders)
already aggregate counting stats and compute AVG/OBP/SLG/OPS in the database,
so these functions are thin wrappers that filter and sort for the UI.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from supabase import Client

from services._base import resolve_client, to_df

V_PLAYER = "v_player_season_totals"
V_TEAM = "v_team_season_totals"
V_POSITION = "v_position_leaders"


def _add_batting_rates(df: pd.DataFrame) -> pd.DataFrame:
    """(Re)compute AVG/OBP/SLG/OPS from counting columns (NaN when AB=0)."""
    ab = df["ab"].replace(0, np.nan)
    df["avg"] = (df["h"] / ab).round(3)
    df["obp"] = ((df["h"] + df["bb"]) / (df["ab"] + df["bb"]).replace(0, np.nan)).round(3)
    df["slg"] = (df["tb"] / ab).round(3)
    df["ops"] = (df["obp"].fillna(0) + df["slg"].fillna(0)).round(3)
    return df


def _aggregate(df: pd.DataFrame, keys: list[str], rates) -> pd.DataFrame:
    """Sum numeric columns over `keys` (collapsing season rows), then recompute
    rate stats with `rates`. Used when no season filter is applied."""
    if df.empty:
        return df
    drop = {"season", "avg", "obp", "slg", "ops", "team_avg", *keys}
    sum_cols = [c for c in df.columns if c not in drop and df[c].dtype.kind in "if"]
    grouped = df.groupby(keys, as_index=False)[sum_cols].sum()
    return rates(grouped) if rates else grouped


def player_season_totals(
    client: Client | None = None,
    season: str | None = None,
    team_id: str | None = None,
) -> pd.DataFrame:
    """Per-player totals + rate stats. Aggregates across seasons when none chosen."""
    query = resolve_client(client).table(V_PLAYER).select("*")
    if season:
        query = query.eq("season", season)
    if team_id:
        query = query.eq("team_id", team_id)
    df = to_df(query.execute())
    if season is None:
        df = _aggregate(df, ["player_id", "player_name", "team_id"], _add_batting_rates)
    return df.sort_values("ops", ascending=False).reset_index(drop=True) if not df.empty else df


def team_season_totals(
    client: Client | None = None, season: str | None = None
) -> pd.DataFrame:
    """Per-team totals. Aggregates across seasons when none chosen."""
    query = resolve_client(client).table(V_TEAM).select("*")
    if season:
        query = query.eq("season", season)
    df = to_df(query.execute())
    if season is None:
        def _team_avg(g: pd.DataFrame) -> pd.DataFrame:
            g["team_avg"] = (g["hits"] / g["ab"].replace(0, np.nan)).round(3)
            return g
        df = _aggregate(df, ["team_id", "team_name"], _team_avg)
    return df.sort_values("runs", ascending=False).reset_index(drop=True) if not df.empty else df


def position_leaders(
    client: Client | None = None,
    position_code: str | None = None,
    season: str | None = None,
) -> pd.DataFrame:
    """Offensive output grouped by position played. Aggregates across seasons."""
    query = resolve_client(client).table(V_POSITION).select("*")
    if position_code:
        query = query.eq("position_code", position_code)
    if season:
        query = query.eq("season", season)
    df = to_df(query.execute())
    if season is None and not df.empty:
        def _avg(g: pd.DataFrame) -> pd.DataFrame:
            g["avg"] = (g["h"] / g["ab"].replace(0, np.nan)).round(3)
            return g
        keys = [k for k in ["position_code", "position_name", "category", "player_id", "player_name"] if k in df.columns]
        df = _aggregate(df, keys, _avg)
    return df.sort_values("avg", ascending=False).reset_index(drop=True) if not df.empty else df


def leaderboard(
    client: Client | None = None,
    stat: str = "ops",
    season: str | None = None,
    min_ab: int = 0,
    top_n: int = 10,
) -> pd.DataFrame:
    """Top-N players by any stat column, with an optional minimum-AB qualifier.

    Done in pandas (not SQL) so the UI can switch the sort stat and min-AB
    threshold instantly without new queries.
    """
    df = player_season_totals(client, season=season)
    if df.empty or stat not in df.columns:
        return df
    if min_ab:
        df = df[df["ab"] >= min_ab]
    return df.sort_values(stat, ascending=False).head(top_n).reset_index(drop=True)
