"""Players page: roster, per-player stats, and admin CRUD."""

from __future__ import annotations

import streamlit as st

from auth import session as auth
from models.schemas import PlayerCreate
from services import analytics
from services import games as games_svc
from services import players as players_svc
from services import positions as pos_svc
from services import stats as stats_svc
from services import teams as teams_svc
from ui import components
from utils import filters


def render() -> None:
    st.subheader("👤 Players")
    client = auth.get_db()

    with st.expander("Filters", expanded=False):
        team_id = filters.team_selectbox(client, key="players_team")

    roster = players_svc.list_players(client, team_id=team_id)
    team_names = components.team_id_to_name(client)

    if roster.empty:
        st.info("No players yet." + (" Add one below." if auth.is_admin() else ""))
    else:
        disp = roster.copy()
        disp["team"] = disp["team_id"].map(team_names).fillna("—")
        cols = [c for c in ["name", "team", "jersey_number", "bats", "throws", "active"] if c in disp.columns]
        st.dataframe(
            disp[cols].rename(
                columns={"name": "Player", "team": "Team", "jersey_number": "#",
                         "bats": "B", "throws": "T", "active": "Active"}
            ),
            use_container_width=True,
            hide_index=True,
        )

        # --- Player detail ---
        st.divider()
        st.markdown("### 📈 Player detail")
        pick_id, pick_name = filters.player_selectbox(client, team_id=team_id, key="player_detail")
        if pick_id:
            _player_detail(client, pick_id, pick_name)

    if auth.is_admin():
        _admin_section(client, roster)


def _player_detail(client, player_id: str, player_name: str) -> None:
    """Season totals + game-by-game log for one player."""
    totals = analytics.player_season_totals(client)
    mine = totals[totals["player_id"] == player_id] if not totals.empty else totals

    if not mine.empty:
        agg = mine.iloc[0]
        components.metric_row(
            [("AVG", f"{agg['avg']:.3f}"), ("OBP", f"{agg['obp']:.3f}"), ("OPS", f"{agg['ops']:.3f}"),
             ("HR", int(agg["hr"])), ("RBI", int(agg["rbi"])), ("H", int(agg["h"]))],
            per_row=3,
        )
    else:
        st.caption("No batting stats recorded yet for this player.")

    # Game log: join stat lines with game dates/opponents.
    lines = stats_svc.list_player_game_stats(client, player_id=player_id)
    if lines.empty:
        return
    games_df = games_svc.list_games(client)
    if not games_df.empty:
        gmap = games_df.set_index("id")["game_date"].to_dict()
        lines = lines.copy()
        lines["date"] = lines["game_id"].map(gmap)
        lines = lines.sort_values("date", ascending=False)
    st.markdown(f"**Game log — {player_name}**")
    keep = [c for c in ["date", "ab", "r", "h", "rbi", "bb", "so", "doubles", "triples", "hr", "tb", "errors"] if c in lines.columns]
    components.show_stat_table(lines[keep], card_title_col="date", key="player_log")


def _admin_section(client, roster) -> None:
    st.divider()
    st.markdown("### 🔧 Admin")

    teams_df = teams_svc.list_teams(client)
    team_opts = dict(zip(teams_df["name"], teams_df["id"])) if not teams_df.empty else {}
    pos_df = pos_svc.list_positions(client)
    pos_opts = dict(zip(pos_df["code"], pos_df["id"])) if not pos_df.empty else {}

    with st.expander("➕ Add player"):
        with st.form("add_player", clear_on_submit=True):
            name = st.text_input("Name *")
            team = st.selectbox("Team", ["—", *team_opts.keys()])
            number = st.number_input("Jersey #", min_value=0, value=0, step=1)
            pos = st.selectbox("Primary position", ["—", *pos_opts.keys()])
            c1, c2 = st.columns(2)
            bats = c1.selectbox("Bats", ["—", "L", "R", "S"])
            throws = c2.selectbox("Throws", ["—", "L", "R"])
            if st.form_submit_button("Create player", use_container_width=True):
                if not name.strip():
                    st.error("Name is required.")
                else:
                    payload = PlayerCreate(
                        name=name.strip(),
                        team_id=team_opts.get(team),
                        jersey_number=int(number) or None,
                        primary_position_id=pos_opts.get(pos),
                        bats=None if bats == "—" else bats,
                        throws=None if throws == "—" else throws,
                    ).for_insert()
                    players_svc.create_player(payload, client=client)
                    st.success(f"Created {name}.")
                    st.rerun()

    if not roster.empty:
        with st.expander("✏️ Edit / delete player"):
            names = dict(zip(roster["name"], roster["id"]))
            sel = st.selectbox("Player", list(names.keys()), key="edit_player_sel")
            row = roster[roster["id"] == names[sel]].iloc[0]
            with st.form("edit_player"):
                name = st.text_input("Name", value=row.get("name", ""))
                team_keys = list(team_opts.keys())
                cur_team = next((k for k, v in team_opts.items() if v == row.get("team_id")), "—")
                team = st.selectbox("Team", ["—", *team_keys], index=(["—", *team_keys].index(cur_team)))
                number = st.number_input("Jersey #", min_value=0, value=int(row.get("jersey_number") or 0), step=1)
                active = st.checkbox("Active", value=bool(row.get("active", True)))
                c1, c2 = st.columns(2)
                if c1.form_submit_button("Save", use_container_width=True):
                    players_svc.update_player(
                        names[sel],
                        {
                            "name": name.strip(),
                            "team_id": team_opts.get(team),
                            "jersey_number": int(number) or None,
                            "active": active,
                        },
                        client=client,
                    )
                    st.success("Saved.")
                    st.rerun()
                if c2.form_submit_button("🗑️ Delete", use_container_width=True):
                    players_svc.delete_player(names[sel], client=client)
                    st.warning(f"Deleted {sel}.")
                    st.rerun()
