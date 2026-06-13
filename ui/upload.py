"""Upload Data page — PDF + Excel ingestion (built in Phase 4)."""

from __future__ import annotations

import streamlit as st

from auth import session as auth


def render() -> None:
    st.subheader("📤 Upload Data")

    if not auth.is_admin():
        st.warning("Admin login required to import data. Use the sidebar to log in.")
        return

    st.info(
        "Bulk import from **PDF scorecards** and **Excel** files arrives in "
        "**Phase 4** (with a validation + reconciliation step before anything is "
        "written). For now, enter games and stats manually on the **Games** page."
    )
    st.file_uploader(
        "Preview the uploader (parsing wired up in Phase 4)",
        type=["pdf", "xlsx", "xls"],
        disabled=True,
    )
