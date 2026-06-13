"""CRUD for games."""

from __future__ import annotations

import pandas as pd
from supabase import Client

from services._base import first, resolve_client, to_df

TABLE = "games"


def list_games(
    client: Client | None = None,
    season: str | None = None,
    team_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> pd.DataFrame:
    """Games with optional filters, newest first.

    `team_id` matches games where the team is EITHER home or away.
    `date_from`/`date_to` are ISO date strings (inclusive).
    """
    query = resolve_client(client).table(TABLE).select("*")
    if season:
        query = query.eq("season", season)
    if team_id:
        # PostgREST OR filter: home_team_id == tid OR away_team_id == tid.
        query = query.or_(f"home_team_id.eq.{team_id},away_team_id.eq.{team_id}")
    if date_from:
        query = query.gte("game_date", date_from)
    if date_to:
        query = query.lte("game_date", date_to)
    return to_df(query.order("game_date", desc=True).execute())


def get_game(game_id: str, client: Client | None = None) -> dict | None:
    """Single game by id."""
    resp = resolve_client(client).table(TABLE).select("*").eq("id", game_id).execute()
    return first(resp)


def create_game(payload: dict, client: Client | None = None) -> dict | None:
    """Insert a game. Requires an authenticated client (RLS)."""
    resp = resolve_client(client).table(TABLE).insert(payload).execute()
    return first(resp)


def update_game(game_id: str, payload: dict, client: Client | None = None) -> dict | None:
    """Update a game. Requires an authenticated client (RLS)."""
    resp = (
        resolve_client(client)
        .table(TABLE)
        .update(payload)
        .eq("id", game_id)
        .execute()
    )
    return first(resp)


def delete_game(game_id: str, client: Client | None = None) -> None:
    """Delete a game (cascades to innings + stats). Requires authed client."""
    resolve_client(client).table(TABLE).delete().eq("id", game_id).execute()
