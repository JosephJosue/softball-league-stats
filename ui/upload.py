"""Upload Data page: import player stat lines from Excel/CSV/PDF.

Pipeline: parse (raw table) -> auto-map columns -> validate -> preview ->
fill details for any NEW players -> resolve names to IDs -> bulk upsert.
Nothing is written until the admin clicks Import.
"""

from __future__ import annotations

import datetime
from dataclasses import replace

import pandas as pd
import streamlit as st

from auth import session as auth
from config.settings import GAME_INNINGS
from ingestion import excel_parser, gamechanger, pdf_parser, validation
from ingestion.gamechanger import GameCard, PlayerStat
from ingestion.matching import find_match, normalize_name
from models.schemas import GameCreate, PlayerCreate, TeamCreate
from services import games as games_svc
from services import players as players_svc
from services import positions as pos_svc
from services import stats as stats_svc
from services import teams as teams_svc
from ui import components
from utils.errors import humanize_db_error

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

    # GameChanger scorecard PDFs get a dedicated full-game import flow.
    if uploaded.name.lower().endswith(".pdf"):
        card = gamechanger.parse(data)
        if card and (card.away_players or card.home_players):
            _render_game_import(client, card)
            return
        st.info("Not a recognized GameChanger scorecard — trying generic table extraction.")

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

    # --- 4b. Fill details for NEW players (avoids editing them afterwards) ---
    new_attrs: dict[str, dict] = {}
    if create_missing:
        new_attrs = _new_player_editor(client, rows)

    for w in validation.reconcile(rows, team_totals):
        st.warning(f"Reconciliation: {w}")

    if st.button("🚀 Import stats", use_container_width=True):
        try:
            _do_import(
                client,
                rows,
                game_id=game_labels[game_pick],
                default_team_id=team_opts[default_team],
                team_opts=team_opts,
                create_missing=create_missing,
                new_attrs=new_attrs,
            )
        except Exception as exc:  # noqa: BLE001 - friendly message instead of a crash
            st.error(humanize_db_error(exc))


def _new_player_editor(client, rows: list[dict]) -> dict[str, dict]:
    """Editable table to fill jersey/bats/throws/position for new players."""
    players_df = players_svc.list_players(client)
    existing = {n.strip().lower() for n in players_df["name"]} if not players_df.empty else set()
    new_names = sorted({r["player_name"] for r in rows if r["player_name"].strip().lower() not in existing})
    if not new_names:
        return {}

    st.markdown("**New players — fill in their details**")
    pos_codes = pos_svc.list_positions(client)["code"].tolist()
    editor_df = pd.DataFrame(
        [{"Player": n, "Jersey": 0, "Bats": "", "Throws": "", "Position": ""} for n in new_names]
    )
    edited = st.data_editor(
        editor_df,
        hide_index=True,
        use_container_width=True,
        disabled=["Player"],
        column_config={
            "Jersey": st.column_config.NumberColumn(min_value=0, step=1),
            "Bats": st.column_config.SelectboxColumn(options=["", "L", "R", "S"]),
            "Throws": st.column_config.SelectboxColumn(options=["", "L", "R"]),
            "Position": st.column_config.SelectboxColumn(options=["", *pos_codes]),
        },
        key="new_players_editor",
    )
    attrs: dict[str, dict] = {}
    for _, er in edited.iterrows():
        attrs[str(er["Player"]).strip().lower()] = {
            "jersey": int(er["Jersey"]) if pd.notna(er["Jersey"]) and er["Jersey"] else None,
            "bats": er["Bats"] or None,
            "throws": er["Throws"] or None,
            "position": er["Position"] or None,
        }
    return attrs


# --------------------------------------------------------------------------
# GameChanger full-game import
# --------------------------------------------------------------------------

def _side_df(players: list[PlayerStat]) -> pd.DataFrame:
    """Editable preview table for one team (all batting + pitching fields)."""
    return pd.DataFrame(
        [
            {
                "Player": p.name, "Pos": p.position or "",
                "AB": p.ab, "R": p.r, "H": p.h, "RBI": p.rbi, "BB": p.bb, "SO": p.so,
                "2B": p.doubles, "3B": p.triples, "HR": p.hr, "E": p.errors,
                "DefInn": p.innings_played,
                "IP": p.ip, "P_H": p.p_h, "P_R": p.p_r, "ER": p.er,
                "P_BB": p.p_bb, "P_SO": p.p_so, "P_HR": p.p_hr,
            }
            for p in players
        ]
    )


# Columns that map to integer stat fields (df column -> PlayerStat attr).
_BAT_COLS = {
    "AB": "ab", "R": "r", "H": "h", "RBI": "rbi", "BB": "bb", "SO": "so",
    "2B": "doubles", "3B": "triples", "HR": "hr", "E": "errors",
}
_PIT_COLS = {"P_H": "p_h", "P_R": "p_r", "ER": "er", "P_BB": "p_bb", "P_SO": "p_so", "P_HR": "p_hr"}


def _rows_to_players(originals: list[PlayerStat], edited: pd.DataFrame, valid_pos: set[str]) -> list[PlayerStat]:
    """Rebuild PlayerStat records from the edited table (all fields applied)."""
    out: list[PlayerStat] = []
    for orig, (_, row) in zip(originals, edited.iterrows()):
        name = str(row.get("Player") or "").strip() or orig.name
        pos = str(row.get("Pos") or "").strip().upper() or None
        if pos not in valid_pos:
            pos = None
        bat = {attr: (int(row[col]) if pd.notna(row[col]) else 0) for col, attr in _BAT_COLS.items()}

        di = row.get("DefInn")
        innings_played = float(di) if pd.notna(di) else None

        ip_val = row.get("IP")
        ip = float(ip_val) if pd.notna(ip_val) else None
        if ip is not None:
            pit = {attr: (int(row[col]) if pd.notna(row[col]) else 0) for col, attr in _PIT_COLS.items()}
        else:
            pit = {attr: None for attr in _PIT_COLS.values()}

        out.append(replace(orig, name=name, position=pos, innings_played=innings_played, ip=ip, **bat, **pit))
    return out


def _editor_config(pos_codes: list[str]) -> dict:
    num = st.column_config.NumberColumn(min_value=0, step=1)
    cfg = {col: num for col in [*_BAT_COLS, *_PIT_COLS]}
    cfg["DefInn"] = st.column_config.NumberColumn("DefInn", min_value=0, step=1, help="Defensive innings played")
    cfg["IP"] = st.column_config.NumberColumn(min_value=0.0, step=0.1, format="%.1f")
    cfg["Pos"] = st.column_config.SelectboxColumn(options=["", *pos_codes])
    cfg["Player"] = st.column_config.TextColumn()
    return cfg


def _render_game_import(client, card: GameCard) -> None:
    st.success("GameChanger scorecard detected.")
    st.markdown(f"### {card.away_team}  {card.away_score} – {card.home_score}  {card.home_team}")

    teams_df = teams_svc.list_teams(client)
    existing = list(teams_df["name"]) if not teams_df.empty else []
    team_id_by_name = dict(zip(teams_df["name"], teams_df["id"])) if not teams_df.empty else {}

    def _picker(label: str, parsed_name: str, key: str) -> str:
        create_label = f"➕ Create '{parsed_name}'"
        opts = [*existing, create_label]
        default = parsed_name if parsed_name in existing else create_label
        return st.selectbox(label, opts, index=opts.index(default), key=key)

    c1, c2 = st.columns(2)
    with c1:
        away_choice = _picker("Away team", card.away_team, "gc_away")
    with c2:
        home_choice = _picker("Home team", card.home_team, "gc_home")

    gdate = st.date_input("Game date", value=card.date or datetime.date.today())
    season = st.text_input("Season", placeholder="e.g. 2026-Spring")
    create_missing = st.checkbox("Create players that don't exist yet", value=True)

    st.info(
        "Edit any **Player** name below before importing — useful for fixing "
        "truncated or ambiguous names (e.g. 'Juan Diego' → 'Juan Diego Torres') "
        "so stats go to the right player."
    )
    # Defensive innings ≈ how many innings the team spent on the field, which is
    # the number of innings the OTHER team batted.
    away_def = len(card.home_innings) or GAME_INNINGS
    home_def = len(card.away_innings) or GAME_INNINGS
    away_players = _editable_side(
        client, card.away_team, card.away_players, team_id_by_name.get(away_choice), "gc_edit_away", away_def
    )
    home_players = _editable_side(
        client, card.home_team, card.home_players, team_id_by_name.get(home_choice), "gc_edit_home", home_def
    )

    _reconciliation(card, away_players, home_players)

    if st.button("🚀 Import full game", use_container_width=True):
        try:
            _do_game_import(
                client, card,
                away_players=away_players, home_players=home_players,
                away_choice=away_choice, home_choice=home_choice,
                season=season.strip() or None, gdate=gdate, create_missing=create_missing,
                team_id_by_name=team_id_by_name,
            )
        except Exception as exc:  # noqa: BLE001 - friendly message instead of a crash
            st.error(humanize_db_error(exc))


def _editable_side(
    client, team_label: str, players: list[PlayerStat], team_id: str | None,
    key: str, def_innings_default: int,
) -> list[PlayerStat]:
    """Editable preview for one team; returns players with all edits applied.

    Defensive innings default to how many innings the team fielded (admin can
    lower them for substitutes). Shows whether each (possibly edited) name will
    merge into an existing roster player or be created new.
    """
    st.markdown(f"**{team_label} — batting/pitching** (all fields editable)")
    pos_codes = pos_svc.list_positions(client)["code"].tolist()
    prepared = [
        replace(p, innings_played=p.innings_played if p.innings_played is not None else def_innings_default)
        for p in players
    ]
    df = _side_df(prepared)
    edited = st.data_editor(
        df,
        hide_index=True,
        use_container_width=True,
        column_config=_editor_config(pos_codes),
        key=key,
    )
    result = _rows_to_players(players, edited, set(pos_codes))

    # Live "where will this land" feedback against the chosen team's roster.
    cache = _roster_cache(client, team_id) if team_id else []
    merges = []
    for q in result:
        m = find_match(normalize_name(q.name), cache)
        if m:
            merges.append(f"{q.name} → {m['name']}")
    if merges:
        st.caption("Will update existing players: " + "; ".join(merges))
    st.caption(f"{len(result) - len(merges)} new player(s), {len(merges)} matched.")

    # Flag within-team look-alikes so the admin can disambiguate (or confirm
    # they really are different people) before importing.
    keys = [(q.name, normalize_name(q.name)) for q in result]
    look_alikes = []
    for i, (na, ka) in enumerate(keys):
        for nb, kb in keys[i + 1:]:
            if ka and kb and ka != kb and (ka.startswith(kb) or kb.startswith(ka)):
                look_alikes.append(f"'{na}' / '{nb}'")
    if look_alikes:
        st.warning(
            "Similar names on this team — if any pair is the **same** player, give "
            "them the same full name; if they're **different** people, leave them. "
            + "; ".join(look_alikes)
        )
    return result


def _reconciliation(card: GameCard, away_players, home_players) -> None:
    """Check the scoresheet math lines up with the final score before importing."""
    rows = []
    for label, score, innings, players, totals in [
        (card.away_team, card.away_score, card.away_innings, away_players, card.away_totals),
        (card.home_team, card.home_score, card.home_innings, home_players, card.home_totals),
    ]:
        line_sum = sum(innings)
        runs_sum = sum(p.r for p in players)
        hits_sum = sum(p.h for p in players)
        rows.append(
            {
                "Team": label,
                "Final": score,
                "Line score Σ": f"{line_sum} {'✅' if line_sum == score else '⚠️'}",
                "Player runs Σ": f"{runs_sum} {'✅' if runs_sum == score else '⚠️'}",
                "Player hits Σ": f"{hits_sum} {'✅' if hits_sum == totals.get('h', hits_sum) else '⚠️'}",
            }
        )
    df = pd.DataFrame(rows)
    ok = all("⚠️" not in " ".join(map(str, r.values())) for r in rows)
    st.markdown("**Reconciliation**")
    st.dataframe(df, use_container_width=True, hide_index=True)
    if ok:
        st.caption("✅ Scoresheet math matches the final score.")
    else:
        st.warning(
            "⚠️ Some totals don't match the final score. Edit the stat lines above "
            "to fix, or import anyway if the scorecard itself is inconsistent."
        )


def _resolve_team(client, choice: str, parsed_name: str, season, team_id_by_name: dict) -> str:
    """Return a team id, creating the team only if it truly doesn't exist yet.

    Always looks the name up first (fresh), so repeated imports / failed retries
    never create duplicate teams — which in turn keeps game de-duplication (by
    team id) reliable.
    """
    name = parsed_name if choice.startswith("➕ Create") else choice
    existing_id = teams_svc.name_to_id(client).get(name)
    if existing_id:
        return existing_id
    return teams_svc.create_team(
        TeamCreate(name=name, season=season).for_insert(), client=client
    )["id"]


def _roster_cache(client, team_id: str) -> list[dict]:
    """Existing players on a team as [{id, name, nkey}] for fuzzy matching."""
    df = players_svc.list_players(client, team_id=team_id)
    if df.empty:
        return []
    return [
        {"id": i, "name": n, "nkey": normalize_name(n)}
        for n, i in zip(df["name"], df["id"])
    ]


def _resolve_or_create(client, name: str, cache: list[dict], create_missing: bool, build_kwargs, used_ids: set) -> str | None:
    """Match a name to an existing player (prefix-aware) or create one.

    `used_ids` holds player ids already claimed in this import. If a name would
    match a player that's already been used (e.g. ambiguous 'Juan Diego T' and
    'Juan Diego V' both matching a stored 'Juan Diego'), we create a distinct
    player instead — avoiding a duplicate (game_id, player_id) in the upsert.

    When a fuller name arrives for an already-stored truncated one (e.g.
    'Leonardo Vásquez' for 'Leonardo V'), the stored name is upgraded.
    """
    nkey = normalize_name(name)
    if not nkey:
        return None
    match = find_match(nkey, cache)
    if match and match["id"] not in used_ids:
        if len(nkey) > len(match["nkey"]):  # incoming name is fuller -> upgrade
            players_svc.update_player(match["id"], {"name": name}, client=client)
            match["name"], match["nkey"] = name, nkey
        return match["id"]
    if not create_missing:
        return None
    created = players_svc.create_player(
        PlayerCreate(name=name, **build_kwargs()).for_insert(), client=client
    )
    cache.append({"id": created["id"], "name": name, "nkey": nkey})
    return created["id"]


def _import_side(
    client, players: list[PlayerStat], *, game_id: str, team_id: str,
    pos_map: dict, create_missing: bool,
) -> int:
    """Create/match players for one team (fuzzy) and upsert their stat lines."""
    cache = _roster_cache(client, team_id)
    used_ids: set = set()
    payloads: list[dict] = []
    for p in players:
        pos_code = p.position if p.position in pos_map else None
        pid = _resolve_or_create(
            client, p.name, cache, create_missing,
            lambda team_id=team_id, pos_code=pos_code: dict(
                team_id=team_id,
                primary_position_id=pos_map.get(pos_code) if pos_code else None,
                positions=[pos_code] if pos_code else None,
            ),
            used_ids,
        )
        if not pid or pid in used_ids:
            continue
        used_ids.add(pid)
        payload = {
            "game_id": game_id, "player_id": pid, "team_id": team_id,
            "position_id": pos_map.get(pos_code) if pos_code else None,
            "ab": p.ab, "r": p.r, "h": p.h, "rbi": p.rbi, "bb": p.bb, "so": p.so,
            "doubles": p.doubles, "triples": p.triples, "hr": p.hr, "errors": p.errors,
        }
        if p.innings_played is not None:
            payload["innings_played"] = p.innings_played
        if p.ip is not None:
            payload.update(
                ip=p.ip, p_h=p.p_h, p_r=p.p_r, er=p.er,
                p_bb=p.p_bb, p_so=p.p_so, p_hr=p.p_hr,
            )
        payloads.append(payload)
    if payloads:
        stats_svc.bulk_upsert_player_game_stats(payloads, client=client)
    return len(payloads)


def _do_game_import(
    client, card: GameCard, *, away_players, home_players,
    away_choice, home_choice, season, gdate, create_missing, team_id_by_name,
) -> None:
    away_id = _resolve_team(client, away_choice, card.away_team, season, team_id_by_name)
    home_id = _resolve_team(client, home_choice, card.home_team, season, team_id_by_name)
    pos_map = pos_svc.code_to_id(client)

    # Reuse an existing game for the same date + teams, else create one.
    games_df = games_svc.list_games(client)
    game_id = None
    if not games_df.empty:
        match = games_df[
            (games_df["game_date"] == gdate.isoformat())
            & (games_df["home_team_id"] == home_id)
            & (games_df["away_team_id"] == away_id)
        ]
        if not match.empty:
            game_id = match.iloc[0]["id"]
    payload = GameCreate(
        game_date=gdate, season=season, away_team_id=away_id, home_team_id=home_id,
        away_score=card.away_score, home_score=card.home_score, status="final",
    ).for_insert()
    reused = bool(game_id)
    if game_id:
        games_svc.update_game(game_id, payload, client=client)
    else:
        game_id = games_svc.create_game(payload, client=client)["id"]

    # Player stat lines (using any admin name edits).
    n_away = _import_side(client, away_players, game_id=game_id, team_id=away_id,
                          pos_map=pos_map, create_missing=create_missing)
    n_home = _import_side(client, home_players, game_id=game_id, team_id=home_id,
                          pos_map=pos_map, create_missing=create_missing)

    # Line score (away = top, home = bottom).
    for i, runs in enumerate(card.away_innings, start=1):
        stats_svc.upsert_inning(
            {"game_id": game_id, "team_id": away_id, "inning_number": i, "half": "top", "runs": runs},
            client=client,
        )
    for i, runs in enumerate(card.home_innings, start=1):
        stats_svc.upsert_inning(
            {"game_id": game_id, "team_id": home_id, "inning_number": i, "half": "bottom", "runs": runs},
            client=client,
        )

    # Team totals.
    for team_id, score, totals, team_e, lob in [
        (away_id, card.away_score, card.away_totals, card.away_team_e, card.away_lob),
        (home_id, card.home_score, card.home_totals, card.home_team_e, card.home_lob),
    ]:
        stats_svc.upsert_team_game_stats(
            {
                "game_id": game_id, "team_id": team_id, "runs": score,
                "hits": totals.get("h", 0), "errors": team_e or 0, "lob": lob or 0,
                "ab": totals.get("ab", 0), "bb": totals.get("bb", 0), "so": totals.get("so", 0),
            },
            client=client,
        )

    action = "Updated" if reused else "Imported"
    st.success(
        f"✅ {action} game **{card.away_team} {card.away_score}–{card.home_score} "
        f"{card.home_team}** ({gdate}): {n_away} away + {n_home} home stat lines, "
        "line score, and team totals saved."
    )
    st.balloons()


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
    new_attrs: dict[str, dict],
) -> None:
    """Resolve names -> IDs (fuzzy, creating players if asked) and bulk upsert."""
    team_lower = {n.strip().lower(): i for n, i in team_opts.items()}
    pos_map = pos_svc.code_to_id(client)
    caches: dict[str, list[dict]] = {}  # per-team roster cache for fuzzy matching
    used_ids: set = set()  # players already claimed in this import (one game)

    payloads: list[dict] = []
    skipped: list[str] = []

    for row in rows:
        name = row["player_name"]
        team_id = team_lower.get(str(row.get("team_name", "")).lower(), default_team_id)
        cache = caches.setdefault(team_id, _roster_cache(client, team_id))

        attrs = new_attrs.get(name.lower(), {})
        roster_pos = attrs.get("position")
        player_id = _resolve_or_create(
            client, name, cache, create_missing,
            lambda team_id=team_id, attrs=attrs, roster_pos=roster_pos: dict(
                team_id=team_id,
                jersey_number=attrs.get("jersey"),
                bats=attrs.get("bats"),
                throws=attrs.get("throws"),
                primary_position_id=pos_map.get(roster_pos) if roster_pos else None,
                positions=[roster_pos] if roster_pos else None,
            ),
            used_ids,
        )
        if not player_id or player_id in used_ids:
            skipped.append(name)
            continue
        used_ids.add(player_id)

        payload = {
            "game_id": game_id,
            "player_id": player_id,
            "team_id": team_id,
            "position_id": pos_map.get(str(row.get("position", "")).upper()),
        }
        for k, v in row.items():
            if k not in ("player_name", "team_name", "position"):
                payload[k] = v
        payloads.append(payload)

    if payloads:
        stats_svc.bulk_upsert_player_game_stats(payloads, client=client)
        st.success(f"✅ Imported {len(payloads)} stat line(s) into the selected game.")
        st.balloons()
    if skipped:
        st.warning(f"Skipped (no matching player): {', '.join(skipped)}")
