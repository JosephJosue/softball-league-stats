"""Predictions page — best hitters / lineup suggestions (built in Phase 5)."""

from __future__ import annotations

import streamlit as st


def render() -> None:
    st.subheader("🔮 Predictions")
    st.info(
        "The predictions engine arrives in **Phase 5**: rolling-average form, "
        "best-hitter suggestions, and a recommended defensive lineup based on "
        "recent performance. It will read the stats you enter on the Games page."
    )
