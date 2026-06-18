"""Admin authentication via Supabase Auth.

Security model recap:
  * Viewers are anonymous and never log in — reads use the shared anon client
    (db.client.get_client()), governed by the public-read RLS policies.
  * Admins log in here. Each login creates its OWN supabase client that carries
    the user's JWT, stored in st.session_state. That client runs queries as the
    `authenticated` role, which the write RLS policies allow.

Why a per-session client (not the cached anon one): st.cache_resource is shared
across ALL browser sessions on the server. If we mutated that shared client's
auth token on login, one admin's credentials could bleed into other users'
sessions. Keeping the authed client in st.session_state isolates it per browser.
"""

from __future__ import annotations

import streamlit as st
from supabase import Client, create_client

from config.settings import SUPABASE_ANON_KEY, SUPABASE_URL
from db.client import get_client

# Key under which we stash the logged-in admin's state.
_SESSION_KEY = "_admin_auth"


def login(email: str, password: str) -> tuple[bool, str]:
    """Attempt an email/password login.

    Returns (success, message). On success the authenticated client + user
    identity are saved to st.session_state.
    """
    try:
        # Fresh client for this browser session (not the shared anon one).
        client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        res = client.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        if res.user is None:
            return False, "Invalid email or password."

        st.session_state[_SESSION_KEY] = {
            "client": client,
            "email": res.user.email,
            "user_id": res.user.id,
        }
        return True, f"Signed in as {res.user.email}."
    except Exception as exc:  # noqa: BLE001 - surface auth errors to the UI
        return False, f"Login failed: {exc}"


def logout() -> None:
    """Sign out and clear the admin session."""
    auth = st.session_state.get(_SESSION_KEY)
    if auth:
        try:
            auth["client"].auth.sign_out()
        except Exception:
            pass  # best-effort; we clear local state regardless
    st.session_state.pop(_SESSION_KEY, None)


def is_admin() -> bool:
    """True when an admin is currently logged in for this session."""
    return _SESSION_KEY in st.session_state


def current_email() -> str | None:
    """Email of the logged-in admin, or None."""
    auth = st.session_state.get(_SESSION_KEY)
    return auth["email"] if auth else None


def get_db() -> Client:
    """Return the client to use for DB calls in the current session.

    Authenticated client when an admin is logged in (so writes pass RLS),
    otherwise the shared anon client (read-only). Reads work with either.
    """
    auth = st.session_state.get(_SESSION_KEY)
    if auth:
        return auth["client"]
    return get_client()


def require_admin() -> None:
    """Guard for write paths; raises if no admin is logged in."""
    if not is_admin():
        raise PermissionError("Admin login is required for this action.")
