"""Dashboard: league leaders, team standings, and a quick activity snapshot."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from auth import session as auth
from services import analytics
from services import games as games_svc
from services import players as players_svc
from services import positions as pos_svc
from services import teams as teams_svc
from export import excel_export
from ui import components
from utils import filters


def render() -> None:
    st.subheader("📊 Dashboard")
    client = auth.get_db()

    # --- Filters (inline for mobile) ---
    with st.expander("Filters", expanded=False):
        season = filters.season_selectbox(client, key="dash_season")

    # --- Snapshot metrics ---
    teams_df = teams_svc.list_teams(client, season=season)
    players_df = players_svc.list_players(client)
    games_df = games_svc.list_games(client, season=season)
    components.metric_row(
        [("Teams", len(teams_df)), ("Players", len(players_df)), ("Games", len(games_df))]
    )

    st.divider()

    # --- League leaders ---
    st.markdown("### 🏆 League Leaders")
    c1, c2 = st.columns(2)
    stat = c1.selectbox(
        "Stat",
        ["ops", "avg", "obp", "slg", "hr", "rbi", "h", "r"],
        format_func=lambda s: components.STAT_LABELS.get(s, s.upper()),
        key="dash_stat",
    )
    min_ab = c2.number_input("Min AB", min_value=0, value=0, step=5, key="dash_minab")

    leaders = analytics.leaderboard(
        client, stat=stat, season=season, min_ab=int(min_ab), top_n=10
    )
    if leaders.empty:
        st.info("No stats yet. Add a game with player stats to populate leaders.")
    else:
        keep = ["player_name", "games", "ab", "h", "hr", "rbi", stat]
        keep = list(dict.fromkeys(c for c in keep if c in leaders.columns))
        components.show_stat_table(
            leaders[keep], card_title_col="player_name", key="dash_leaders"
        )

    st.divider()

    # --- Team standings / run production ---
    st.markdown("### 🥎 Team Run Production")
    team_totals = analytics.team_season_totals(client, season=season)
    if team_totals.empty:
        st.info("No team game stats yet.")
    else:
        fig = px.bar(
            team_totals.sort_values("runs", ascending=False),
            x="team_name",
            y="runs",
            labels={"team_name": "Team", "runs": "Runs"},
        )
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=320)
        st.plotly_chart(fig, use_container_width=True)
        components.show_stat_table(team_totals, key="dash_team_totals")

    st.divider()

    # --- Position analytics ---
    st.markdown("### 🧤 Stats by Position")
    pos_df = pos_svc.list_positions(client)
    codes = pos_df["code"].tolist() if not pos_df.empty else []
    code = st.selectbox("Position", ["All", *codes], key="dash_pos")
    leaders = analytics.position_leaders(
        client, position_code=None if code == "All" else code, season=season
    )
    if leaders.empty:
        st.info("No position stats yet.")
    else:
        keep = [c for c in ["position_code", "player_name", "ab", "h", "hr", "rbi", "errors", "avg"] if c in leaders.columns]
        components.show_stat_table(
            leaders[keep].rename(columns={"position_code": "Pos"}),
            card_title_col="player_name",
            key="dash_pos_leaders",
        )

    # --- Export ---
    st.divider()
    st.markdown("### ⬇️ Export")
    player_totals = analytics.player_season_totals(client, season=season)
    workbook = excel_export.build_workbook(
        {
            "Players": player_totals,
            "Teams": team_totals,
            "Positions": analytics.position_leaders(client, season=season),
        }
    )
    label = f"softball_stats{('_' + season) if season else ''}.xlsx"
    st.download_button(
        "Download stats (Excel)",
        data=workbook,
        file_name=label,
        mime=excel_export.XLSX_MIME,
        use_container_width=True,
    )
