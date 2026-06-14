"""Players page: roster, per-player offense/defense stats, and admin CRUD."""

from __future__ import annotations

import pandas as pd
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
from utils import calculations, filters


def _as_list(value) -> list[str]:
    """Coerce a positions cell (list / NaN / None) to a clean list of codes."""
    return list(value) if isinstance(value, list) else []


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
        if "positions" in disp.columns:
            disp["pos"] = disp["positions"].apply(lambda v: ", ".join(_as_list(v)) or "—")
        cols = [c for c in ["name", "team", "pos", "jersey_number", "bats", "throws", "active"] if c in disp.columns]
        st.dataframe(
            disp[cols].rename(
                columns={"name": "Player", "team": "Team", "pos": "Pos", "jersey_number": "#",
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


def _skill_scores(client, player_id: str, scope: str = "League") -> dict[str, float] | None:
    """Six skill axes as percentile ranks (0-100) for the radar chart.

    Aggregates each player ACROSS seasons first, then percentile-ranks them
    against either the whole league or just the player's own team (`scope`).
    """
    df = analytics.player_season_totals(client)
    if df.empty or player_id not in set(df["player_id"]):
        return None
    cols = ["ab", "h", "bb", "tb", "rbi", "errors", "games", "innings_played"]
    for c in cols:
        if c not in df.columns:
            df[c] = 0
    if "team_id" not in df.columns:
        df["team_id"] = None
    agg = df.groupby("player_id", as_index=False).agg({**{c: "sum" for c in cols}, "team_id": "first"})

    # Restrict the comparison pool to teammates when scope == "Team".
    if scope == "Team":
        team_id = agg.loc[agg["player_id"] == player_id, "team_id"].iloc[0]
        agg = agg[agg["team_id"] == team_id]

    ab = agg["ab"].replace(0, pd.NA)
    abbb = (agg["ab"] + agg["bb"]).replace(0, pd.NA)
    games = agg["games"].replace(0, pd.NA)
    agg["contact"] = agg["h"] / ab
    agg["power"] = agg["tb"] / ab
    agg["onbase"] = (agg["h"] + agg["bb"]) / abbb
    agg["discipline"] = agg["bb"] / abbb
    agg["production"] = agg["rbi"] / games
    denom = agg["innings_played"].where(agg["innings_played"] > 0, agg["games"]).replace(0, pd.NA)
    agg["defense"] = -(agg["errors"] / denom)  # fewer errors per inning ranks higher

    axes = {
        "Contact": "contact", "Power": "power", "On-Base": "onbase",
        "Discipline": "discipline", "Production": "production", "Defense": "defense",
    }
    ranks = pd.DataFrame({label: (agg[col].rank(pct=True) * 100).round(0) for label, col in axes.items()})
    ranks["player_id"] = agg["player_id"].values
    row = ranks[ranks["player_id"] == player_id]
    if row.empty:
        return None
    row = row.iloc[0]
    return {label: float(row[label]) if pd.notna(row[label]) else 0.0 for label in axes}


def _player_detail(client, player_id: str, player_name: str) -> None:
    """Offense + defense views for one player, on switchable tabs."""
    player = players_svc.get_player(player_id, client=client) or {}
    lines = stats_svc.list_player_game_stats(client, player_id=player_id)

    # Skill radar (percentile across 6 axes) with a comparison-scope toggle.
    scope = st.radio(
        "Compare against", ["League", "Team"], horizontal=True, key="radar_scope",
        help="Rank this player vs. the whole league or just his own teammates.",
    )
    scores = _skill_scores(client, player_id, scope=scope)
    if scores:
        baseline = "teammates" if scope == "Team" else "the league"
        st.caption(f"Skill profile — percentile rank vs. {baseline} (0–100).")
        st.plotly_chart(components.skill_radar(scores), use_container_width=True)

    tab_off, tab_def = st.tabs(["⚾ Offense", "🧤 Defense"])
    with tab_off:
        _offense_view(client, player_id, player_name, lines)
    with tab_def:
        _defense_view(client, player, lines)


def _rate(value) -> str:
    """Format a rate stat as .333, or '.000' when undefined (e.g. 0 AB)."""
    return f"{value:.3f}" if pd.notna(value) else ".000"


def _int(value) -> int:
    return int(value) if pd.notna(value) else 0


def _offense_view(client, player_id: str, player_name: str, lines: pd.DataFrame) -> None:
    totals = analytics.player_season_totals(client)
    mine = totals[totals["player_id"] == player_id] if not totals.empty else totals
    if not mine.empty:
        # Sum across season rows (a player can span more than one season group).
        s = mine[["ab", "h", "bb", "tb", "rbi", "hr"]].sum()
        rates = calculations.rate_stats(_int(s["ab"]), _int(s["h"]), _int(s["bb"]), _int(s["tb"]))
        components.metric_row(
            [("AVG", _rate(rates["avg"])), ("OBP", _rate(rates["obp"])), ("OPS", _rate(rates["ops"])),
             ("HR", _int(s["hr"])), ("RBI", _int(s["rbi"])), ("H", _int(s["h"]))],
            per_row=3,
        )
        if _int(s["ab"]) == 0:
            st.caption("No at-bats recorded — rate stats shown as .000.")
    else:
        st.caption("No batting stats recorded yet for this player.")

    if lines.empty:
        return
    games_df = games_svc.list_games(client)
    log = lines.copy()
    if not games_df.empty:
        gmap = games_df.set_index("id")["game_date"].to_dict()
        log["date"] = log["game_id"].map(gmap)
        log = log.sort_values("date", ascending=False)
    st.markdown(f"**Game log — {player_name}**")
    keep = [c for c in ["date", "ab", "r", "h", "rbi", "bb", "so", "doubles", "triples", "hr", "tb"] if c in log.columns]
    components.show_stat_table(log[keep], card_title_col="date", key="player_log")


def _defense_view(client, player: dict, lines: pd.DataFrame) -> None:
    eligible = _as_list(player.get("positions"))
    st.write("**Eligible positions:** " + (", ".join(eligible) if eligible else "—"))

    if lines.empty or "position_id" not in lines.columns:
        st.caption("No defensive appearances recorded yet.")
        return

    id2code = pos_svc.id_to_code(client)
    d = lines.copy()
    d["Position"] = d["position_id"].map(id2code).fillna("—")
    if "innings_played" not in d.columns:
        d["innings_played"] = 0
    d["innings_played"] = d["innings_played"].fillna(0)

    total_inn = float(d["innings_played"].sum())
    total_err = int(d["errors"].sum())
    e_per_inn = round(total_err / total_inn, 3) if total_inn else 0.0
    components.metric_row(
        [("Appearances", int(len(d))), ("Def innings", total_inn),
         ("Errors", total_err), ("E / inning", e_per_inn)],
        per_row=2,
    )

    summary = (
        d.groupby("Position")
        .agg(Games=("id", "count"), Innings=("innings_played", "sum"), Errors=("errors", "sum"))
        .reset_index()
        .sort_values("Innings", ascending=False)
    )
    st.markdown("**By position**")
    st.dataframe(summary, use_container_width=True, hide_index=True)

    # Pitching (also a defensive role) — only when the player has pitched.
    _pitching_view(d)


def _pitching_view(lines: pd.DataFrame) -> None:
    """Aggregate pitching stats from a player's game lines, if any."""
    if "ip" not in lines.columns:
        return
    pitched = lines[lines["ip"].notna()]
    if pitched.empty:
        return

    # Sum innings correctly via outs (.1/.2 are thirds, not decimals).
    total_outs = sum(calculations.ip_to_outs(float(x)) for x in pitched["ip"])
    ip_total = calculations.outs_to_ip(total_outs)
    er = int(pitched["er"].fillna(0).sum())
    era = calculations.era(er, ip_total)

    def _sum(col: str) -> int:
        return int(pitched[col].fillna(0).sum()) if col in pitched.columns else 0

    st.markdown("**Pitching**")
    components.metric_row(
        [("Apps", int(len(pitched))), ("IP", ip_total), ("ERA", f"{era:.2f}")], per_row=3
    )
    components.metric_row(
        [("H", _sum("p_h")), ("R", _sum("p_r")), ("ER", er),
         ("BB", _sum("p_bb")), ("SO", _sum("p_so")), ("HR", _sum("p_hr"))],
        per_row=3,
    )


def _admin_section(client, roster) -> None:
    st.divider()
    st.markdown("### 🔧 Admin")

    teams_df = teams_svc.list_teams(client)
    team_opts = dict(zip(teams_df["name"], teams_df["id"])) if not teams_df.empty else {}
    pos_df = pos_svc.list_positions(client)
    pos_codes = pos_df["code"].tolist() if not pos_df.empty else []
    pos_opts = dict(zip(pos_df["code"], pos_df["id"])) if not pos_df.empty else {}

    with st.expander("➕ Add player"):
        if not team_opts:
            st.info("Create a team first — every player must belong to a team.")
        else:
            with st.form("add_player", clear_on_submit=True):
                name = st.text_input("Name *")
                team = st.selectbox("Team *", list(team_opts.keys()))
                number = st.number_input("Jersey #", min_value=0, value=0, step=1)
                positions = st.multiselect("Positions (defensive)", pos_codes)
                c1, c2 = st.columns(2)
                bats = c1.selectbox("Bats", ["—", "L", "R", "S"])
                throws = c2.selectbox("Throws", ["—", "L", "R"])
                if st.form_submit_button("Create player", use_container_width=True):
                    if not name.strip():
                        st.error("Name is required.")
                    else:
                        payload = PlayerCreate(
                            name=name.strip(),
                            team_id=team_opts[team],
                            jersey_number=int(number) or None,
                            primary_position_id=pos_opts.get(positions[0]) if positions else None,
                            positions=positions or None,
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
                cur_team = next((k for k, v in team_opts.items() if v == row.get("team_id")), team_keys[0])
                team = st.selectbox("Team *", team_keys, index=team_keys.index(cur_team))
                jersey = row.get("jersey_number")
                number = st.number_input(
                    "Jersey #", min_value=0, value=int(jersey) if pd.notna(jersey) else 0, step=1
                )

                cur_positions = [p for p in _as_list(row.get("positions")) if p in pos_codes]
                positions = st.multiselect("Positions (defensive)", pos_codes, default=cur_positions)

                bats_opts = ["—", "L", "R", "S"]
                throws_opts = ["—", "L", "R"]
                cur_bats = row.get("bats") if row.get("bats") in bats_opts else "—"
                cur_throws = row.get("throws") if row.get("throws") in throws_opts else "—"
                bc, tc = st.columns(2)
                bats = bc.selectbox("Bats", bats_opts, index=bats_opts.index(cur_bats))
                throws = tc.selectbox("Throws", throws_opts, index=throws_opts.index(cur_throws))

                active = st.checkbox("Active", value=bool(row.get("active", True)))
                c1, c2 = st.columns(2)
                if c1.form_submit_button("Save", use_container_width=True):
                    players_svc.update_player(
                        names[sel],
                        {
                            "name": name.strip(),
                            "team_id": team_opts[team],
                            "jersey_number": int(number) or None,
                            "primary_position_id": pos_opts.get(positions[0]) if positions else None,
                            "positions": positions or None,
                            "bats": None if bats == "—" else bats,
                            "throws": None if throws == "—" else throws,
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
