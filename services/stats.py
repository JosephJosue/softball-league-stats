"""CRUD for the stat tables: innings, player_game_stats, team_game_stats.

Box-score lines use `upsert` keyed on a natural unique constraint so re-entering
or re-importing a game updates the existing row instead of duplicating it:
  * player_game_stats -> unique (game_id, player_id)
  * team_game_stats   -> unique (game_id, team_id)
  * innings           -> unique (game_id, inning_number, half)
"""

from __future__ import annotations

import pandas as pd
from supabase import Client

from services._base import first, resolve_client, to_df

PLAYER_STATS = "player_game_stats"
TEAM_STATS = "team_game_stats"
INNINGS = "innings"


# --- Player game stats ----------------------------------------------------

def list_player_game_stats(
    client: Client | None = None,
    game_id: str | None = None,
    player_id: str | None = None,
    team_id: str | None = None,
) -> pd.DataFrame:
    """Player box-score lines filtered by game / player / team."""
    query = resolve_client(client).table(PLAYER_STATS).select("*")
    if game_id:
        query = query.eq("game_id", game_id)
    if player_id:
        query = query.eq("player_id", player_id)
    if team_id:
        query = query.eq("team_id", team_id)
    return to_df(query.execute())


def upsert_player_game_stats(payload: dict, client: Client | None = None) -> dict | None:
    """Insert-or-update one player's line for a game. Requires authed client."""
    resp = (
        resolve_client(client)
        .table(PLAYER_STATS)
        .upsert(payload, on_conflict="game_id,player_id")
        .execute()
    )
    return first(resp)


def bulk_upsert_player_game_stats(
    rows: list[dict], client: Client | None = None
) -> pd.DataFrame:
    """Upsert many player lines at once (used by ingestion). Authed client."""
    if not rows:
        return pd.DataFrame()
    resp = (
        resolve_client(client)
        .table(PLAYER_STATS)
        .upsert(rows, on_conflict="game_id,player_id")
        .execute()
    )
    return to_df(resp)


def delete_player_game_stat(stat_id: str, client: Client | None = None) -> None:
    """Delete a single player line. Requires authed client."""
    resolve_client(client).table(PLAYER_STATS).delete().eq("id", stat_id).execute()


# --- Team game stats ------------------------------------------------------

def list_team_game_stats(
    client: Client | None = None, game_id: str | None = None, team_id: str | None = None
) -> pd.DataFrame:
    """Team box totals filtered by game / team."""
    query = resolve_client(client).table(TEAM_STATS).select("*")
    if game_id:
        query = query.eq("game_id", game_id)
    if team_id:
        query = query.eq("team_id", team_id)
    return to_df(query.execute())


def upsert_team_game_stats(payload: dict, client: Client | None = None) -> dict | None:
    """Insert-or-update a team's totals for a game. Requires authed client."""
    resp = (
        resolve_client(client)
        .table(TEAM_STATS)
        .upsert(payload, on_conflict="game_id,team_id")
        .execute()
    )
    return first(resp)


# --- Innings (line score) -------------------------------------------------

def list_innings(game_id: str, client: Client | None = None) -> pd.DataFrame:
    """All inning rows for a game, ordered for line-score display."""
    resp = (
        resolve_client(client)
        .table(INNINGS)
        .select("*")
        .eq("game_id", game_id)
        .order("inning_number")
        .order("half")
        .execute()
    )
    return to_df(resp)


def upsert_inning(payload: dict, client: Client | None = None) -> dict | None:
    """Insert-or-update one inning-half. Requires authed client."""
    resp = (
        resolve_client(client)
        .table(INNINGS)
        .upsert(payload, on_conflict="game_id,inning_number,half")
        .execute()
    )
    return first(resp)


def delete_inning(inning_id: str, client: Client | None = None) -> None:
    """Delete a single inning row. Requires authed client."""
    resolve_client(client).table(INNINGS).delete().eq("id", inning_id).execute()
