"""Supabase client factory.

Two client "modes" share one underlying connection style:

    * Anon client  -> used for all reads (viewers). Created once and cached
      for the whole app via st.cache_resource.

    * Authenticated client -> after an admin logs in (Phase 2: auth/session),
      we attach their access token so writes run as the `authenticated` role
      and pass RLS. We reuse the same client instance and just set the auth
      session on it.

Why cache_resource: the Supabase client holds an HTTP session; we want a
single shared instance per server process, not one per script rerun.
"""

from __future__ import annotations

# Validate TLS against the OS certificate store before any client is created.
# Centralized here so EVERY entry point that touches the DB (app, scripts,
# tests) gets the fix — not just app.py. Fixes CERTIFICATE_VERIFY_FAILED on
# corporate networks that do TLS inspection. No-op if truststore is absent.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

import streamlit as st
from supabase import Client, create_client

from config.settings import SUPABASE_ANON_KEY, SUPABASE_URL, is_configured


@st.cache_resource(show_spinner=False)
def get_client() -> Client:
    """Return the shared Supabase client (anon key).

    Raises a clear error if the project isn't configured yet so the UI can
    show a friendly setup message instead of a stack trace.
    """
    if not is_configured():
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and "
            "SUPABASE_ANON_KEY in your .env or .streamlit/secrets.toml."
        )
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
