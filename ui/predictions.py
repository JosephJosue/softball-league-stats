"""Predictions page: best hitters, recent form, an optimized batting order
(Monte-Carlo), and a suggested defensive lineup."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from auth import session as auth
from config.settings import GAME_INNINGS, ROLLING_WINDOW_GAMES
from predictions import engine
from services import analytics
from services import games as games_svc
from services import players as players_svc
from services import stats as stats_svc
from ui import components
from utils import filters


def _as_list(value) -> list[str]:
    return list(value) if isinstance(value, list) else []


@st.cache_data(show_spinner="Simulating batting orders…")
def _optimize(totals: pd.DataFrame, innings: int, sims: int, iterations: int):
    return engine.optimize_batting_order(totals, innings=innings, sims=sims, iterations=iterations)


def render() -> None:
    st.subheader("🔮 Predictions")
    client = auth.get_db()

    with st.expander("Filters", expanded=True):
        season = filters.season_selectbox(client, key="pred_season")
        team_id = filters.team_selectbox(client, season=season, key="pred_team")
        window = st.slider("Recent-form window (games)", 3, 15, ROLLING_WINDOW_GAMES)

    totals = analytics.player_season_totals(client, season=season, team_id=team_id)
    if totals.empty:
        st.info("No stats yet. Import or enter some games first.")
        return

    # --- Best hitters ---
    st.markdown("### 🏆 Best hitters")
    min_ab = st.number_input("Minimum AB", min_value=0, value=0, step=5, key="pred_minab")
    bh = engine.best_hitters(totals, min_ab=int(min_ab), top_n=10)
    keep = [c for c in ["player_name", "games", "ab", "h", "hr", "rbi", "avg", "obp", "slg", "ops"] if c in bh.columns]
    components.show_stat_table(bh[keep], card_title_col="player_name", key="pred_best")

    if not team_id:
        st.info("Pick a team above to get an optimized batting order and a defensive lineup.")
        _form_section(client, team_id, window)
        return

    # --- Optimized batting order ---
    st.divider()
    st.markdown("### ⚾ Suggested batting order")
    st.caption(
        "Each hitter's stats become plate-appearance probabilities; orders are "
        "simulated over many games and the best is kept (table-setters up top, "
        "power in the RBI spots)."
    )
    order, est_runs = _optimize(totals, GAME_INNINGS, 250, 30)
    if not order:
        st.info("Not enough batting data for this team yet.")
    else:
        components.metric_row([("Est. runs / game", est_runs), ("Batters", len(order))], per_row=2)
        order_df = pd.DataFrame(
            [{"Slot": i + 1, "Player": p["name"], "OBP": p["obp"], "SLG": p["slg"], "OPS": p["ops"]}
             for i, p in enumerate(order)]
        )
        st.dataframe(
            order_df,
            use_container_width=True,
            hide_index=True,
            column_config={c: st.column_config.NumberColumn(c, format="%.3f") for c in ["OBP", "SLG", "OPS"]},
        )

    # --- Defensive lineup ---
    st.divider()
    st.markdown("### 🧤 Suggested defensive lineup")
    _defensive_section(client, team_id, totals)

    # --- Recent form ---
    st.divider()
    _form_section(client, team_id, window)


def _defensive_section(client, team_id: str, totals: pd.DataFrame) -> None:
    roster = players_svc.list_players(client, team_id=team_id)
    if roster.empty:
        st.info("No players on this team.")
        return
    tmap = totals.set_index("player_id") if "player_id" in totals.columns else pd.DataFrame()

    players = []
    no_positions = []
    for _, r in roster.iterrows():
        eligible = set(_as_list(r.get("positions")))
        if not eligible:
            no_positions.append(r["name"])
        errors = innings = games = 0
        if not tmap.empty and r["id"] in tmap.index:
            t = tmap.loc[r["id"]]
            errors = int(t.get("errors", 0) or 0)
            innings = float(t.get("innings_played", 0) or 0)
            games = int(t.get("games", 0) or 0)
        denom = innings if innings > 0 else (games if games > 0 else 1)
        players.append(
            {"name": r["name"], "eligible": eligible,
             "fielding": round(errors / denom, 3), "apps": games}
        )

    lineup = engine.defensive_lineup(players)
    rows = [
        {"Position": pos, "Player": (p["name"] if p else "—"),
         "E/inn": (p["fielding"] if p else None), "Apps": (p["apps"] if p else None)}
        for pos, p in lineup.items()
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if no_positions:
        st.caption(
            "No eligible positions set for: " + ", ".join(no_positions)
            + " — add positions on the Players page to include them."
        )


def _form_section(client, team_id, window: int) -> None:
    st.markdown(f"### 🔥 Recent form (last {window} games)")
    lines = stats_svc.list_player_game_stats(client, team_id=team_id)
    if lines.empty:
        st.info("No game stats yet.")
        return
    games_df = games_svc.list_games(client)
    if not games_df.empty:
        gmap = games_df.set_index("id")["game_date"].to_dict()
        lines = lines.copy()
        lines["date"] = lines["game_id"].map(gmap)
    form = engine.rolling_form(lines, window=window)
    if form.empty:
        st.info("Not enough recent games.")
        return
    name_map = dict(zip(players_svc.list_players(client)["id"], players_svc.list_players(client)["name"]))
    form["Player"] = form["player_id"].map(name_map)
    form = form.sort_values("ops", ascending=False)
    show = form[["Player", "games", "ab", "h", "avg", "ops"]].rename(columns={"games": "G", "ab": "AB", "h": "H"})
    st.dataframe(
        show,
        use_container_width=True,
        hide_index=True,
        column_config={c: st.column_config.NumberColumn(c, format="%.3f") for c in ["avg", "ops"]},
    )
