"""Shared filter widgets (season / team / player / date).

Rendered inline at the top of pages (not the sidebar) so they're reachable on
phones, where the sidebar is collapsed. Each helper returns the selected value
(an id or None for "all") so pages can pass it straight to the service layer.
"""

from __future__ import annotations

import datetime

import pandas as pd
import streamlit as st

from services import players as players_svc
from services import teams as teams_svc


def get_seasons(client) -> list[str]:
    """Distinct, sorted season labels across teams (newest-ish first)."""
    df = teams_svc.list_teams(client)
    if df.empty or "season" not in df.columns:
        return []
    seasons = pd.Series(df["season"]).dropna().unique().tolist()
    return sorted(seasons, reverse=True)


def season_selectbox(client, key: str = "season") -> str | None:
    """Season picker; returns None for 'All seasons'."""
    options = ["All seasons", *get_seasons(client)]
    choice = st.selectbox("Season", options, key=key)
    return None if choice == "All seasons" else choice


def team_selectbox(
    client,
    season: str | None = None,
    key: str = "team",
    label: str = "Team",
    include_all: bool = True,
) -> str | None:
    """Team picker; returns the team id, or None for 'All teams'/empty."""
    df = teams_svc.list_teams(client, season=season)
    mapping = dict(zip(df["name"], df["id"])) if not df.empty else {}
    options = (["All teams"] if include_all else []) + list(mapping.keys())
    if not options:
        st.caption("No teams yet.")
        return None
    choice = st.selectbox(label, options, key=key)
    return None if choice == "All teams" else mapping.get(choice)


def player_selectbox(
    client, team_id: str | None = None, key: str = "player", label: str = "Player"
) -> tuple[str | None, str | None]:
    """Player picker; returns (player_id, player_name) or (None, None)."""
    df = players_svc.list_players(client, team_id=team_id)
    mapping = dict(zip(df["name"], df["id"])) if not df.empty else {}
    if not mapping:
        st.caption("No players yet.")
        return None, None
    name = st.selectbox(label, list(mapping.keys()), key=key)
    return mapping.get(name), name


def date_range(key: str = "dates") -> tuple[str | None, str | None]:
    """Two date inputs; returns (from_iso, to_iso), each possibly None."""
    c1, c2 = st.columns(2)
    start: datetime.date | None = c1.date_input("From", value=None, key=f"{key}_from")
    end: datetime.date | None = c2.date_input("To", value=None, key=f"{key}_to")
    return (
        start.isoformat() if start else None,
        end.isoformat() if end else None,
    )
