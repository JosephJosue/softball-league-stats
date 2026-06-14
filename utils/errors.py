"""Translate raw database/API errors into plain-language messages for the UI.

Supabase/PostgREST raise errors whose default string form is a raw dict like
{'message': ..., 'code': 'PGRST204', ...}. This module turns the common ones
into short, actionable sentences a non-technical user can act on.
"""

from __future__ import annotations

import json


def _extract(exc: Exception) -> tuple[str | None, str]:
    """Best-effort (code, message) extraction from a supabase/PostgREST error."""
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None)
    if not message and getattr(exc, "args", None):
        arg = exc.args[0]
        raw = None
        if isinstance(arg, dict):
            raw = arg
        elif isinstance(arg, str):
            try:
                raw = json.loads(arg.replace("'", '"'))
            except Exception:
                raw = None
        if isinstance(raw, dict):
            code = raw.get("code", code)
            message = raw.get("message")
    return code, (message or str(exc))


def humanize_db_error(exc: Exception) -> str:
    """Return a friendly, actionable message for a database error."""
    code, message = _extract(exc)

    if code == "PGRST204" or "schema cache" in message:
        return (
            "⚠️ The database is missing a recent update. In Supabase → SQL Editor, "
            "run the newest file in `db/migrations/`, then reload the app. "
            f"(Details: {message})"
        )
    if code == "21000" or "affect row a second time" in message:
        return (
            "⚠️ Two players in this import resolved to the same person, so their "
            "stats would collide. In the preview table above, give the similarly "
            "named players distinct names, then import again."
        )
    if code == "23505":  # unique_violation
        return (
            "⚠️ This already exists. It looks like a duplicate — it may have been "
            "imported already."
        )
    if code == "23503":  # foreign_key_violation
        return (
            "⚠️ This record is still linked to others, so it can't be changed or "
            "deleted directly."
        )
    if code == "23502":  # not_null_violation
        return f"⚠️ A required field is missing. ({message})"
    if code == "42501" or "row-level security" in message.lower():
        return "⚠️ You don't have permission for that. Log in as an admin and try again."

    return f"⚠️ Something went wrong: {message}"
