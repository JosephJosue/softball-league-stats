"""Read-only analytics, backed by the SQL views created in db/schema.sql.

The views (v_player_season_totals, v_team_season_totals, v_position_leaders)
already aggregate counting stats and compute AVG/OBP/SLG/OPS in the database,
so these functions are thin wrappers that filter and sort for the UI.
"""

from __future__ import annotations

import pandas as pd
from supabase import Client

from services._base import resolve_client, to_df

V_PLAYER = "v_player_season_totals"
V_TEAM = "v_team_season_totals"
V_POSITION = "v_position_leaders"


def player_season_totals(
    client: Client | None = None,
    season: str | None = None,
    team_id: str | None = None,
) -> pd.DataFrame:
    """Per-player season totals + rate stats."""
    query = resolve_client(client).table(V_PLAYER).select("*")
    if season:
        query = query.eq("season", season)
    if team_id:
        query = query.eq("team_id", team_id)
    return to_df(query.order("ops", desc=True).execute())


def team_season_totals(
    client: Client | None = None, season: str | None = None
) -> pd.DataFrame:
    """Per-team season totals."""
    query = resolve_client(client).table(V_TEAM).select("*")
    if season:
        query = query.eq("season", season)
    return to_df(query.order("runs", desc=True).execute())


def position_leaders(
    client: Client | None = None,
    position_code: str | None = None,
    season: str | None = None,
) -> pd.DataFrame:
    """Offensive output grouped by position played (for position analytics)."""
    query = resolve_client(client).table(V_POSITION).select("*")
    if position_code:
        query = query.eq("position_code", position_code)
    if season:
        query = query.eq("season", season)
    return to_df(query.order("avg", desc=True).execute())


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
