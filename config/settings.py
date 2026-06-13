"""Centralized configuration.

Reads secrets from (in order of precedence):
    1. Streamlit secrets  (st.secrets)      -> best for deployment
    2. Environment vars / .env              -> best for local dev

Keeping all config access in one module means the rest of the app never
touches os.environ or st.secrets directly — it just imports from here.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Load a local .env if present (no-op when the file is absent, e.g. on Cloud).
load_dotenv()


def _get(key: str, default: str | None = None) -> str | None:
    """Fetch a config value, preferring Streamlit secrets over env vars.

    st.secrets is only available inside a running Streamlit context and
    raises if no secrets file exists, so we guard the lookup defensively.
    """
    try:
        import streamlit as st

        # `key in st.secrets` can raise if no secrets file exists at all.
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)


# --- Supabase ---
SUPABASE_URL: str | None = _get("SUPABASE_URL")
SUPABASE_ANON_KEY: str | None = _get("SUPABASE_ANON_KEY")


def is_configured() -> bool:
    """True only when both Supabase connection values are present."""
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)


# --- App constants ---
APP_TITLE = "Softball League Stats"
APP_ICON = "🥎"

# Default number of recent games used by rolling-average predictions (Phase 5).
ROLLING_WINDOW_GAMES = 5

# Navigation labels (kept here so app.py and pages stay in sync).
NAV_DASHBOARD = "Dashboard"
NAV_TEAMS = "Teams"
NAV_PLAYERS = "Players"
NAV_GAMES = "Games"
NAV_UPLOAD = "Upload Data"
NAV_PREDICTIONS = "Predictions"
