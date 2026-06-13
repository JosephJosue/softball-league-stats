"""Upload Data page: import player stat lines from Excel/CSV/PDF.

Pipeline: parse (raw table) -> auto-map columns -> validate -> preview ->
resolve player/team names to IDs -> bulk upsert. Nothing is written until the
admin clicks Import.
"""

from __future__ import annotations

import streamlit as st

from auth import session as auth
from ingestion import excel_parser, pdf_parser, validation
from models.schemas import PlayerCreate
from services import games as games_svc
from services import players as players_svc
from services import positions as pos_svc
from services import stats as stats_svc
from services import teams as teams_svc
from ui import components

EXPECTED = (
    "Expected columns (headers are auto-matched, any order/spelling): "
    "**Player**, AB, R, H, RBI, BB, SO, 2B, 3B, HR, LOB, E. "
    "Optional pitching: IP, ER. A **Totals** row is used to cross-check sums."
)


def render() -> None:
    st.subheader("📤 Upload Data")
    client = auth.get_db()

    if not auth.is_admin():
        st.warning("Admin login required to import data. Use the sidebar to log in.")
        return

    st.caption(EXPECTED)
    uploaded = st.file_uploader("Scorecard / stats file", type=["xlsx", "csv", "pdf"])
    if not uploaded:
        return

    data = uploaded.getvalue()
    raw = _parse(uploaded.name, data)
    if raw is None or raw.empty:
        st.error("Couldn't extract a table from this file.")
        return

    st.markdown("**1. Raw data**")
    st.dataframe(raw.head(50), use_container_width=True, hide_index=True)

    # --- 2. Auto-map columns ---
    mapped, mapping, unmapped = validation.auto_map_columns(raw)
    st.markdown("**2. Column mapping**")
    st.write({orig: canon for orig, canon in mapping.items()})
    if unmapped:
        st.caption(f"Ignored unrecognized columns: {', '.join(unmapped)}")

    # --- 3. Validate ---
    rows, team_totals, errors = validation.validate_stat_rows(mapped)
    st.markdown("**3. Validation**")
    if errors:
        for e in errors:
            st.error(e)
    if not rows:
        st.warning("No valid rows to import.")
        return
    st.success(f"{len(rows)} valid player row(s) ready.")
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # --- 4. Target + import ---
    st.markdown("**4. Import target**")
    games_df = games_svc.list_games(client)
    teams_df = teams_svc.list_teams(client)
    if games_df.empty or teams_df.empty:
        st.info("Create at least one team and game first (Teams / Games pages).")
        return

    team_names = components.team_id_to_name(client)
    game_labels = {
        f"{r['game_date']}  "
        f"{team_names.get(r['away_team_id'], '—')} @ {team_names.get(r['home_team_id'], '—')}": r["id"]
        for _, r in games_df.iterrows()
    }
    game_pick = st.selectbox("Game", list(game_labels.keys()))
    team_opts = dict(zip(teams_df["name"], teams_df["id"]))
    default_team = st.selectbox("Team for these stats", list(team_opts.keys()))
    create_missing = st.checkbox("Create players that don't exist yet", value=True)

    warns = validation.reconcile(rows, team_totals)
    for w in warns:
        st.warning(f"Reconciliation: {w}")

    if st.button("🚀 Import stats", use_container_width=True):
        _do_import(
            client,
            rows,
            game_id=game_labels[game_pick],
            default_team_id=team_opts[default_team],
            team_opts=team_opts,
            create_missing=create_missing,
        )


def _parse(filename: str, data: bytes):
    """Dispatch to the right parser based on file extension."""
    lower = filename.lower()
    try:
        if lower.endswith(".pdf"):
            return pdf_parser.extract_best_stat_table(data)
        if lower.endswith(".csv"):
            return excel_parser.read_csv(data)
        sheets = excel_parser.list_sheets(data)
        sheet = st.selectbox("Sheet", sheets) if len(sheets) > 1 else 0
        return excel_parser.read_excel(data, sheet)
    except Exception as exc:  # noqa: BLE001 - surface parse errors in the UI
        st.error(f"Failed to read file: {exc}")
        return None


def _do_import(
    client,
    rows: list[dict],
    *,
    game_id: str,
    default_team_id: str,
    team_opts: dict[str, str],
    create_missing: bool,
) -> None:
    """Resolve names -> IDs (creating players if asked) and bulk upsert."""
    # Lookups (lowercased for forgiving matching).
    players_df = players_svc.list_players(client)
    player_map = (
        {n.strip().lower(): i for n, i in zip(players_df["name"], players_df["id"])}
        if not players_df.empty
        else {}
    )
    team_lower = {n.strip().lower(): i for n, i in team_opts.items()}
    pos_map = pos_svc.code_to_id(client)

    payloads: list[dict] = []
    skipped: list[str] = []

    for row in rows:
        name = row["player_name"]
        team_id = team_lower.get(str(row.get("team_name", "")).lower(), default_team_id)

        player_id = player_map.get(name.lower())
        if not player_id:
            if not create_missing:
                skipped.append(name)
                continue
            created = players_svc.create_player(
                PlayerCreate(name=name, team_id=team_id).for_insert(), client=client
            )
            player_id = created["id"]
            player_map[name.lower()] = player_id

        payload = {
            "game_id": game_id,
            "player_id": player_id,
            "team_id": team_id,
            "position_id": pos_map.get(str(row.get("position", "")).upper()),
        }
        # Copy over all stat fields (batting + any pitching).
        for k, v in row.items():
            if k not in ("player_name", "team_name", "position"):
                payload[k] = v
        payloads.append(payload)

    if payloads:
        stats_svc.bulk_upsert_player_game_stats(payloads, client=client)
        st.success(f"Imported {len(payloads)} stat line(s) into the selected game.")
    if skipped:
        st.warning(f"Skipped (no matching player): {', '.join(skipped)}")
    if payloads:
        st.rerun()
