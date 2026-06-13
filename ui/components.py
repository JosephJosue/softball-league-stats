"""Shared UI rendering helpers (stat tables, cards, metrics).

Centralizes the mobile-first display logic so every page renders stats the same
way: friendly column labels, .3f-formatted rate stats, hidden UUID columns, and
an optional card view for narrow screens.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from services import teams as teams_svc

# Rate stats are formatted as .333 (3 decimals).
RATE_COLS = ["avg", "obp", "slg", "ops", "era", "team_avg"]

# UUID / bookkeeping columns we never want to show in a table.
ID_COLS = ["id", "player_id", "team_id", "game_id", "position_id", "created_at"]

# Short, familiar stat-line labels (baseball-card style).
STAT_LABELS = {
    "player_name": "Player",
    "team_name": "Team",
    "season": "Season",
    "games": "G",
    "ab": "AB",
    "r": "R",
    "h": "H",
    "rbi": "RBI",
    "bb": "BB",
    "so": "SO",
    "doubles": "2B",
    "triples": "3B",
    "hr": "HR",
    "tb": "TB",
    "lob": "LOB",
    "errors": "E",
    "avg": "AVG",
    "obp": "OBP",
    "slg": "SLG",
    "ops": "OPS",
    "ip": "IP",
    "er": "ER",
    "era": "ERA",
}


def team_id_to_name(client) -> dict[str, str]:
    """Map team id -> name (for labeling rows that only carry team_id)."""
    df = teams_svc.list_teams(client)
    return dict(zip(df["id"], df["name"])) if not df.empty else {}


def build_column_config(df: pd.DataFrame) -> dict:
    """Friendly labels + numeric formatting for known stat columns."""
    cfg: dict = {}
    for col in df.columns:
        label = STAT_LABELS.get(col, col)
        if col in RATE_COLS:
            cfg[col] = st.column_config.NumberColumn(label, format="%.3f")
        elif col in STAT_LABELS:
            cfg[col] = st.column_config.Column(label)
    return cfg


def show_stat_table(
    df: pd.DataFrame,
    *,
    empty_msg: str = "No data yet.",
    card_title_col: str | None = None,
    key: str | None = None,
) -> None:
    """Render a stats DataFrame mobile-first.

    Drops UUID columns, applies friendly labels, and (when card_title_col is
    given) offers a 📱 Card view toggle that stacks each row vertically — much
    easier to read than a wide grid on a phone.
    """
    if df is None or df.empty:
        st.info(empty_msg)
        return

    view = df.drop(columns=[c for c in ID_COLS if c in df.columns])

    card_mode = False
    if card_title_col and card_title_col in df.columns:
        card_mode = st.toggle("📱 Card view", key=f"cards_{key}", value=False)

    if card_mode:
        labels = {c: STAT_LABELS.get(c, c) for c in view.columns}
        for _, row in view.iterrows():
            title = row.get(card_title_col, "—")
            with st.expander(str(title)):
                for col in view.columns:
                    if col == card_title_col:
                        continue
                    val = row[col]
                    if col in RATE_COLS and isinstance(val, (int, float)):
                        val = f"{val:.3f}"
                    st.write(f"**{labels[col]}:** {val}")
    else:
        st.dataframe(
            view,
            use_container_width=True,
            hide_index=True,
            column_config=build_column_config(view),
        )


def metric_row(metrics: list[tuple[str, object]], per_row: int = 3) -> None:
    """Render metrics in rows of `per_row` columns (kept low for phones)."""
    for i in range(0, len(metrics), per_row):
        chunk = metrics[i : i + per_row]
        cols = st.columns(len(chunk))
        for col, (label, value) in zip(cols, chunk):
            col.metric(label, value)
