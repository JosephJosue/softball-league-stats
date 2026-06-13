"""CRUD for players."""

from __future__ import annotations

import pandas as pd
from supabase import Client

from services._base import first, resolve_client, to_df

TABLE = "players"


def list_players(
    client: Client | None = None,
    team_id: str | None = None,
    active_only: bool = False,
) -> pd.DataFrame:
    """Players, optionally filtered by team and active flag, ordered by name."""
    query = resolve_client(client).table(TABLE).select("*")
    if team_id:
        query = query.eq("team_id", team_id)
    if active_only:
        query = query.eq("active", True)
    return to_df(query.order("name").execute())


def get_player(player_id: str, client: Client | None = None) -> dict | None:
    """Single player by id."""
    resp = (
        resolve_client(client).table(TABLE).select("*").eq("id", player_id).execute()
    )
    return first(resp)


def create_player(payload: dict, client: Client | None = None) -> dict | None:
    """Insert a player. Requires an authenticated client (RLS)."""
    resp = resolve_client(client).table(TABLE).insert(payload).execute()
    return first(resp)


def update_player(player_id: str, payload: dict, client: Client | None = None) -> dict | None:
    """Update a player. Requires an authenticated client (RLS)."""
    resp = (
        resolve_client(client)
        .table(TABLE)
        .update(payload)
        .eq("id", player_id)
        .execute()
    )
    return first(resp)


def delete_player(player_id: str, client: Client | None = None) -> None:
    """Delete a player. Requires an authenticated client (RLS)."""
    resolve_client(client).table(TABLE).delete().eq("id", player_id).execute()


def name_to_id(client: Client | None = None, team_id: str | None = None) -> dict[str, str]:
    """Map player name -> id (used by ingestion + forms)."""
    df = list_players(client, team_id=team_id)
    if df.empty:
        return {}
    return dict(zip(df["name"], df["id"]))
