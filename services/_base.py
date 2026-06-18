"""Shared helpers for the service layer.

Services depend only on the supabase client (never on Streamlit), so they stay
unit-testable. Each function takes an optional `client`:
  * pass an authenticated client (from auth.session.get_db()) for writes
  * omit it for reads -> falls back to the shared anon client
"""

from __future__ import annotations

import pandas as pd
from supabase import Client

from db.client import get_client


def resolve_client(client: Client | None = None) -> Client:
    """Return the given client, or the shared anon client for reads."""
    return client or get_client()


def to_df(resp) -> pd.DataFrame:
    """Convert a supabase response into a DataFrame (empty-safe)."""
    return pd.DataFrame(resp.data or [])


def first(resp):
    """Return the first row of a response, or None."""
    data = resp.data or []
    return data[0] if data else None
