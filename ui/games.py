"""Games page: schedule/results list, box score view, and admin data entry."""

from __future__ import annotations

import datetime

import pandas as pd
import streamlit as st

from auth import session as auth
from config.settings import GAME_INNINGS
from models.schemas import GameCreate, PlayerGameStatsCreate
from services import games as games_svc
from services import players as players_svc
from services import positions as pos_svc
from services import stats as stats_svc
from services import teams as teams_svc
from ui import components
from utils import filters


def render() -> None:
    st.subheader("🥎 Games")
    client = auth.get_db()
    team_names = components.team_id_to_name(client)

    with st.expander("Filters", expanded=False):
        season = filters.season_selectbox(client, key="games_season")
        team_id = filters.team_selectbox(client, season=season, key="games_team")
        date_from, date_to = filters.date_range(key="games_dates")

    if auth.is_admin():
        _new_game_form(client)

    games_df = games_svc.list_games(
        client, season=season, team_id=team_id, date_from=date_from, date_to=date_to
    )
    if games_df.empty:
        st.info("No games found for these filters.")
        return

    # Results list with friendly team names + score.
    disp = games_df.copy()
    disp["Away"] = disp["away_team_id"].map(team_names).fillna("—")
    disp["Home"] = disp["home_team_id"].map(team_names).fillna("—")
    disp["Score"] = disp["away_score"].astype(str) + " – " + disp["home_score"].astype(str)
    st.dataframe(
        disp[["game_date", "Away", "Home", "Score", "status"]].rename(
            columns={"game_date": "Date", "status": "Status"}
        ),
        use_container_width=True,
        hide_index=True,
    )

    # Box score drill-down.
    st.divider()
    labels = {
        f"{r['game_date']}  {team_names.get(r['away_team_id'], '—')} @ "
        f"{team_names.get(r['home_team_id'], '—')}": r["id"]
        for _, r in games_df.iterrows()
    }
    pick = st.selectbox("Box score", ["—", *labels.keys()], key="games_box_pick")
    if pick != "—":
        game = games_df[games_df["id"] == labels[pick]].iloc[0].to_dict()
        _box_score(client, game, team_names)
        if auth.is_admin():
            _admin_game_entry(client, game, team_names)


# --------------------------------------------------------------------------
# Box score (read)
# --------------------------------------------------------------------------

def _box_score(client, game: dict, team_names: dict) -> None:
    away = team_names.get(game.get("away_team_id"), "Away")
    home = team_names.get(game.get("home_team_id"), "Home")
    st.markdown(f"### {away} @ {home}")
    st.caption(f"{game.get('game_date')} · {game.get('location') or 'TBD'} · {game.get('status')}")
    components.metric_row(
        [(away, game.get("away_score", 0)), (home, game.get("home_score", 0))], per_row=2
    )

    # Line score grid (runs by inning).
    innings = stats_svc.list_innings(game["id"], client=client)
    if not innings.empty:
        grid = _line_score_grid(innings, game, team_names)
        st.dataframe(grid, use_container_width=True)

    # Batting + pitching tables per team.
    lines = stats_svc.list_player_game_stats(client, game_id=game["id"])
    if lines.empty:
        st.caption("No player stats entered for this game yet.")
        return
    pmap = _player_name_map(client)
    lines = lines.copy()
    lines["Player"] = lines["player_id"].map(pmap).fillna("—")

    for team_id, team_label in [
        (game.get("away_team_id"), away),
        (game.get("home_team_id"), home),
    ]:
        team_lines = lines[lines["team_id"] == team_id]
        if team_lines.empty:
            continue
        st.markdown(f"**{team_label} — batting**")
        bat_cols = ["Player", "ab", "r", "h", "rbi", "bb", "so", "doubles", "triples", "hr", "tb", "errors"]
        components.show_stat_table(
            team_lines[[c for c in bat_cols if c in team_lines.columns]],
            card_title_col="Player",
            key=f"box_bat_{team_id}",
        )
        pitchers = team_lines[team_lines["ip"].notna()]
        if not pitchers.empty:
            st.markdown(f"**{team_label} — pitching**")
            pit_cols = ["Player", "ip", "p_h", "p_r", "er", "p_bb", "p_so", "p_hr"]
            st.dataframe(
                pitchers[[c for c in pit_cols if c in pitchers.columns]].rename(
                    columns={"p_h": "H", "p_r": "R", "p_bb": "BB", "p_so": "SO", "p_hr": "HR", "ip": "IP"}
                ),
                use_container_width=True,
                hide_index=True,
            )


def _line_score_grid(innings: pd.DataFrame, game: dict, team_names: dict) -> pd.DataFrame:
    """Build a runs-by-inning grid: rows = teams, cols = 1..GAME_INNINGS + R."""
    rows = {}
    for team_id, half in [
        (game.get("away_team_id"), "top"),
        (game.get("home_team_id"), "bottom"),
    ]:
        label = team_names.get(team_id, half)
        team_inn = innings[(innings["team_id"] == team_id)]
        runs = {str(n): 0 for n in range(1, GAME_INNINGS + 1)}
        for _, r in team_inn.iterrows():
            runs[str(int(r["inning_number"]))] = int(r["runs"])
        runs["R"] = sum(runs[str(n)] for n in range(1, GAME_INNINGS + 1))
        rows[label] = runs
    return pd.DataFrame(rows).T


# --------------------------------------------------------------------------
# Admin: new game + stat entry
# --------------------------------------------------------------------------

def _new_game_form(client) -> None:
    teams_df = teams_svc.list_teams(client)
    team_opts = dict(zip(teams_df["name"], teams_df["id"])) if not teams_df.empty else {}
    with st.expander("➕ New game"):
        if len(team_opts) < 1:
            st.caption("Add teams first (Teams page).")
            return
        with st.form("new_game", clear_on_submit=True):
            gdate = st.date_input("Date", value=datetime.date.today())
            season = st.text_input("Season", placeholder="e.g. 2026-Spring")
            c1, c2 = st.columns(2)
            away = c1.selectbox("Away team", list(team_opts.keys()), key="ng_away")
            home = c2.selectbox("Home team", list(team_opts.keys()), key="ng_home")
            c3, c4 = st.columns(2)
            away_score = c3.number_input("Away score", min_value=0, value=0, step=1)
            home_score = c4.number_input("Home score", min_value=0, value=0, step=1)
            location = st.text_input("Location")
            status = st.selectbox("Status", ["final", "scheduled", "in_progress"])
            if st.form_submit_button("Create game", use_container_width=True):
                if away == home:
                    st.error("Away and home teams must differ.")
                else:
                    payload = GameCreate(
                        game_date=gdate,
                        season=season.strip() or None,
                        away_team_id=team_opts[away],
                        home_team_id=team_opts[home],
                        away_score=int(away_score),
                        home_score=int(home_score),
                        location=location.strip() or None,
                        status=status,
                    ).for_insert()
                    games_svc.create_game(payload, client=client)
                    st.success("Game created.")
                    st.rerun()


def _admin_game_entry(client, game: dict, team_names: dict) -> None:
    st.divider()
    st.markdown("### 🔧 Admin — edit this game")

    _line_score_editor(client, game, team_names)
    _player_line_entry(client, game, team_names)


def _line_score_editor(client, game: dict, team_names: dict) -> None:
    with st.expander("Line score (runs by inning)"):
        innings = stats_svc.list_innings(game["id"], client=client)
        editable = {}
        for team_id, half in [
            (game.get("away_team_id"), "top"),
            (game.get("home_team_id"), "bottom"),
        ]:
            label = team_names.get(team_id, half)
            existing = innings[innings["team_id"] == team_id]
            row = {str(n): 0 for n in range(1, GAME_INNINGS + 1)}
            for _, r in existing.iterrows():
                row[str(int(r["inning_number"]))] = int(r["runs"])
            editable[label] = row
        df = pd.DataFrame(editable).T
        edited = st.data_editor(df, use_container_width=True, key="line_editor")
        if st.button("Save line score", use_container_width=True):
            for team_id, half in [
                (game.get("away_team_id"), "top"),
                (game.get("home_team_id"), "bottom"),
            ]:
                label = team_names.get(team_id, half)
                for n in range(1, GAME_INNINGS + 1):
                    stats_svc.upsert_inning(
                        {
                            "game_id": game["id"],
                            "team_id": team_id,
                            "inning_number": n,
                            "half": half,
                            "runs": int(edited.loc[label, str(n)]),
                        },
                        client=client,
                    )
            st.success("Line score saved.")
            st.rerun()


def _player_line_entry(client, game: dict, team_names: dict) -> None:
    with st.expander("Add / update a player's stat line"):
        players_df = players_svc.list_players(client)
        if players_df.empty:
            st.caption("Add players first (Players page).")
            return
        player_opts = dict(zip(players_df["name"], players_df["id"]))
        player_team = dict(zip(players_df["id"], players_df["team_id"]))
        pos_df = pos_svc.list_positions(client)
        pos_opts = dict(zip(pos_df["code"], pos_df["id"])) if not pos_df.empty else {}

        with st.form("player_line", clear_on_submit=False):
            pname = st.selectbox("Player", list(player_opts.keys()))
            position = st.selectbox("Position", ["—", *pos_opts.keys()])
            st.markdown("**Batting**")
            c = st.columns(4)
            ab = c[0].number_input("AB", 0, step=1)
            r = c[1].number_input("R", 0, step=1)
            h = c[2].number_input("H", 0, step=1)
            rbi = c[3].number_input("RBI", 0, step=1)
            c = st.columns(4)
            bb = c[0].number_input("BB", 0, step=1)
            so = c[1].number_input("SO", 0, step=1)
            lob = c[2].number_input("LOB", 0, step=1)
            errors = c[3].number_input("E", 0, step=1)
            c = st.columns(3)
            doubles = c[0].number_input("2B", 0, step=1)
            triples = c[1].number_input("3B", 0, step=1)
            hr = c[2].number_input("HR", 0, step=1)

            pitched = st.checkbox("This player pitched")
            ip = pr = ph = er = pbb = pso = phr = None
            if pitched:
                st.markdown("**Pitching**")
                pc = st.columns(4)
                ip = pc[0].number_input("IP (e.g. 5.2)", 0.0, step=0.1, format="%.1f")
                ph = pc[1].number_input("H allowed", 0, step=1)
                pr = pc[2].number_input("R allowed", 0, step=1)
                er = pc[3].number_input("ER", 0, step=1)
                pc = st.columns(3)
                pbb = pc[0].number_input("BB", 0, step=1, key="p_bb")
                pso = pc[1].number_input("SO", 0, step=1, key="p_so")
                phr = pc[2].number_input("HR", 0, step=1, key="p_hr")

            if st.form_submit_button("Save stat line", use_container_width=True):
                pid = player_opts[pname]
                try:
                    payload = PlayerGameStatsCreate(
                        game_id=game["id"],
                        player_id=pid,
                        team_id=player_team.get(pid),
                        position_id=pos_opts.get(position),
                        ab=int(ab), r=int(r), h=int(h), rbi=int(rbi),
                        bb=int(bb), so=int(so), doubles=int(doubles),
                        triples=int(triples), hr=int(hr), lob=int(lob), errors=int(errors),
                        ip=float(ip) if pitched else None,
                        p_h=int(ph) if pitched else None,
                        p_r=int(pr) if pitched else None,
                        er=int(er) if pitched else None,
                        p_bb=int(pbb) if pitched else None,
                        p_so=int(pso) if pitched else None,
                        p_hr=int(phr) if pitched else None,
                    ).for_insert()
                except ValueError as exc:
                    st.error(f"Invalid stat line: {exc}")
                    return
                stats_svc.upsert_player_game_stats(payload, client=client)
                st.success(f"Saved {pname}'s line.")
                st.rerun()

        # Existing lines with delete.
        lines = stats_svc.list_player_game_stats(client, game_id=game["id"])
        if not lines.empty:
            pmap = _player_name_map(client)
            st.markdown("**Entered lines**")
            for _, row in lines.iterrows():
                cols = st.columns([3, 1])
                cols[0].write(
                    f"{pmap.get(row['player_id'], '—')}: "
                    f"{row['ab']} AB, {row['h']} H, {row['hr']} HR, {row['rbi']} RBI"
                )
                if cols[1].button("🗑️", key=f"del_{row['id']}"):
                    stats_svc.delete_player_game_stat(row["id"], client=client)
                    st.rerun()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _player_name_map(client) -> dict[str, str]:
    df = players_svc.list_players(client)
    return dict(zip(df["id"], df["name"])) if not df.empty else {}
