"""Teams page: roster overview + admin CRUD."""

from __future__ import annotations

import streamlit as st

from auth import session as auth
from models.schemas import TeamCreate
from services import players as players_svc
from services import teams as teams_svc


def render() -> None:
    st.subheader("🏟️ Teams")
    client = auth.get_db()

    teams_df = teams_svc.list_teams(client)
    if teams_df.empty:
        st.info("No teams yet." + (" Add one below." if auth.is_admin() else ""))
    else:
        show = teams_df[[c for c in ["name", "abbreviation", "season"] if c in teams_df.columns]]
        st.dataframe(
            show.rename(columns={"name": "Team", "abbreviation": "Abbr", "season": "Season"}),
            use_container_width=True,
            hide_index=True,
        )

        # Drill-down: roster for a selected team.
        names = dict(zip(teams_df["name"], teams_df["id"]))
        pick = st.selectbox("View roster", ["—", *names.keys()], key="teams_roster_pick")
        if pick != "—":
            roster = players_svc.list_players(client, team_id=names[pick])
            st.markdown(f"**{pick} roster** ({len(roster)} players)")
            if roster.empty:
                st.caption("No players on this team yet.")
            else:
                cols = [c for c in ["name", "jersey_number", "bats", "throws", "active"] if c in roster.columns]
                st.dataframe(
                    roster[cols].rename(
                        columns={"name": "Player", "jersey_number": "#", "bats": "B", "throws": "T", "active": "Active"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

    if not auth.is_admin():
        return

    # --- Admin: add / edit / delete ---
    st.divider()
    st.markdown("### 🔧 Admin")

    with st.expander("➕ Add team"):
        with st.form("add_team", clear_on_submit=True):
            name = st.text_input("Name *")
            abbr = st.text_input("Abbreviation")
            season = st.text_input("Season", placeholder="e.g. 2026-Spring")
            if st.form_submit_button("Create team", use_container_width=True):
                if not name.strip():
                    st.error("Name is required.")
                else:
                    payload = TeamCreate(
                        name=name.strip(),
                        abbreviation=abbr.strip() or None,
                        season=season.strip() or None,
                    ).for_insert()
                    teams_svc.create_team(payload, client=client)
                    st.success(f"Created {name}.")
                    st.rerun()

    if not teams_df.empty:
        with st.expander("✏️ Edit / delete team"):
            names = dict(zip(teams_df["name"], teams_df["id"]))
            sel = st.selectbox("Team", list(names.keys()), key="edit_team_sel")
            row = teams_df[teams_df["id"] == names[sel]].iloc[0]
            with st.form("edit_team"):
                name = st.text_input("Name", value=row.get("name", ""))
                abbr = st.text_input("Abbreviation", value=row.get("abbreviation") or "")
                season = st.text_input("Season", value=row.get("season") or "")
                c1, c2 = st.columns(2)
                if c1.form_submit_button("Save", use_container_width=True):
                    teams_svc.update_team(
                        names[sel],
                        TeamCreate(
                            name=name.strip(),
                            abbreviation=abbr.strip() or None,
                            season=season.strip() or None,
                        ).for_insert(),
                        client=client,
                    )
                    st.success("Saved.")
                    st.rerun()
                if c2.form_submit_button("🗑️ Delete", use_container_width=True):
                    teams_svc.delete_team(names[sel], client=client)
                    st.warning(f"Deleted {sel}.")
                    st.rerun()
