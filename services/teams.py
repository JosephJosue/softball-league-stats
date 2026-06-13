"""CRUD for teams."""

from __future__ import annotations

import pandas as pd
from supabase import Client

from services._base import first, resolve_client, to_df

TABLE = "teams"


def list_teams(client: Client | None = None, season: str | None = None) -> pd.DataFrame:
    """All teams (optionally filtered by season), ordered by name."""
    query = resolve_client(client).table(TABLE).select("*")
    if season:
        query = query.eq("season", season)
    return to_df(query.order("name").execute())


def get_team(team_id: str, client: Client | None = None) -> dict | None:
    """Single team by id."""
    resp = resolve_client(client).table(TABLE).select("*").eq("id", team_id).execute()
    return first(resp)


def create_team(payload: dict, client: Client | None = None) -> dict | None:
    """Insert a team. Requires an authenticated client (RLS)."""
    resp = resolve_client(client).table(TABLE).insert(payload).execute()
    return first(resp)


def update_team(team_id: str, payload: dict, client: Client | None = None) -> dict | None:
    """Update a team. Requires an authenticated client (RLS)."""
    resp = (
        resolve_client(client)
        .table(TABLE)
        .update(payload)
        .eq("id", team_id)
        .execute()
    )
    return first(resp)


def delete_team(team_id: str, client: Client | None = None) -> None:
    """Delete a team. Requires an authenticated client (RLS)."""
    resolve_client(client).table(TABLE).delete().eq("id", team_id).execute()


def name_to_id(client: Client | None = None, season: str | None = None) -> dict[str, str]:
    """Map team name -> id (used by ingestion + forms)."""
    df = list_teams(client, season)
    if df.empty:
        return {}
    return dict(zip(df["name"], df["id"]))
