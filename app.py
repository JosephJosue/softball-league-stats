"""Softball League Stats — Streamlit entry point.

Phase 1 placeholder: verifies configuration and Supabase connectivity, and
establishes the mobile-first page setup + sidebar navigation shell. The real
pages (Dashboard, Teams, Players, Games, Upload, Predictions) are wired up in
Phase 3.
"""

from __future__ import annotations

# Validate TLS against the OS certificate store instead of the bundled certifi
# certs. This fixes "CERTIFICATE_VERIFY_FAILED" on corporate networks that do
# TLS inspection (their internal root CA lives in the OS store, not in certifi).
# Best-effort: a no-op if truststore isn't installed, so it never breaks startup.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

import streamlit as st

from config.settings import (
    APP_ICON,
    APP_TITLE,
    NAV_DASHBOARD,
    NAV_GAMES,
    NAV_PLAYERS,
    NAV_PREDICTIONS,
    NAV_TEAMS,
    NAV_UPLOAD,
    is_configured,
)

# Mobile-first: "centered" layout reads far better than "wide" on phones.
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="centered",
    initial_sidebar_state="collapsed",
)


def _check_connection() -> None:
    """Show Supabase configuration / connectivity status (Phase 1 smoke test)."""
    if not is_configured():
        st.warning(
            "Supabase is not configured yet. Copy `.env.example` to `.env` "
            "(or `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`) "
            "and add your `SUPABASE_URL` and `SUPABASE_ANON_KEY`."
        )
        return

    try:
        from db.client import get_client

        client = get_client()
        # Lightweight read against the seeded reference table.
        result = client.table("positions").select("code").limit(1).execute()
        if result.data:
            st.success("Connected to Supabase ✅ (schema detected).")
        else:
            st.info(
                "Connected to Supabase, but no positions found. "
                "Did you run `db/schema.sql` in the SQL Editor?"
            )
    except Exception as exc:  # noqa: BLE001 - surface any setup error to the user
        st.error(f"Could not reach Supabase: {exc}")


def main() -> None:
    # Sidebar navigation shell (pages wired up in Phase 3).
    pages = [
        NAV_DASHBOARD,
        NAV_TEAMS,
        NAV_PLAYERS,
        NAV_GAMES,
        NAV_UPLOAD,
        NAV_PREDICTIONS,
    ]
    with st.sidebar:
        st.title(f"{APP_ICON} {APP_TITLE}")
        choice = st.radio("Navigate", pages, label_visibility="collapsed")
        st.caption("Admin login arrives in Phase 2.")

    st.title(f"{APP_ICON} {APP_TITLE}")
    st.subheader(choice)
    _check_connection()
    st.info(
        "Phase 1 scaffold is live. Backend services and pages are built in "
        "the next phases."
    )


if __name__ == "__main__":
    main()
