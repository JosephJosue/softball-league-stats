"""Softball League Stats — Streamlit entry point.

Sets up mobile-first page config, the sidebar (navigation + admin login), and
routes to the page render functions in ui/. Pages read via auth.get_db() and
reveal admin controls only when auth.is_admin() is true.
"""

from __future__ import annotations

import streamlit as st

from auth import session as auth
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
from ui import dashboard, games, players, predictions, teams, upload

# Mobile-first: centered layout reads best on phones; sidebar collapses to a
# hamburger automatically on small screens.
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Map nav labels -> page render functions.
PAGES = {
    NAV_DASHBOARD: dashboard.render,
    NAV_TEAMS: teams.render,
    NAV_PLAYERS: players.render,
    NAV_GAMES: games.render,
    NAV_UPLOAD: upload.render,
    NAV_PREDICTIONS: predictions.render,
}


def _sidebar_auth() -> None:
    """Admin login / logout panel in the sidebar."""
    st.divider()
    if auth.is_admin():
        st.success(f"Admin: {auth.current_email()}")
        if st.button("Log out", use_container_width=True):
            auth.logout()
            st.rerun()
    else:
        with st.expander("🔐 Admin login"):
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Log in", use_container_width=True):
                    ok, msg = auth.login(email, password)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        st.caption("Viewers can browse all stats without logging in.")


def main() -> None:
    if not is_configured():
        st.error(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY "
            "in `.env` or `.streamlit/secrets.toml`, then restart."
        )
        return

    with st.sidebar:
        st.title(f"{APP_ICON} {APP_TITLE}")
        choice = st.radio("Navigate", list(PAGES), label_visibility="collapsed")
        _sidebar_auth()

    st.title(f"{APP_ICON} {APP_TITLE}")
    try:
        PAGES[choice]()
    except Exception as exc:  # noqa: BLE001 - show a friendly message, not a stack trace
        from utils.errors import humanize_db_error

        st.error(humanize_db_error(exc))

    st.divider()
    role = "Admin" if auth.is_admin() else "Viewer (read-only)"
    st.caption(f"{APP_ICON} {APP_TITLE} · {role} · data via Supabase")


if __name__ == "__main__":
    main()
