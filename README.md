# 🥎 Softball League Stats

A web app for tracking and analyzing an amateur softball league — game results,
player & team statistics (offense **and** defense), league leaderboards, and
data-driven suggestions for the best batting order and defensive lineup.

Built **mobile-first** (it's mostly used from a phone at the field) on
**Streamlit + Supabase**.

---

## What it does

**📊 Dashboard** — league leaders by any stat (with a minimum-AB filter), team
run-production chart, and stats grouped by position. Totals roll up across the
whole league.

**🏟️ Teams & 👤 Players** — rosters with multiple eligible positions per player,
and a per-player detail view with two tabs:
- **Offense** — AVG / OBP / SLG / OPS, home runs, RBI, and a full game log.
- **Defense** — putouts, assists, errors, double plays, **fielding %**, and throw
  accuracy.
- A **hexagonal skill radar** (Contact · Power · On-Base · Discipline · Production
  · Defense) showing the player's percentile rank — togglable between the whole
  **league** and just his **teammates**.

**🥎 Games** — schedule/results, full **box scores** (inning-by-inning line score,
batting and pitching lines), and admin entry for new games and stat lines.

**📤 Data ingestion** — three ways to get data in, all with an editable preview
before anything is saved:
- **GameChanger scorecard PDFs** — parses the two-team layout, including
  extra-base hits and errors that only appear in the footnotes.
- **Batting CSV/Excel** — flexible header auto-matching.
- **Defensive-stats spreadsheet** — the manually-tracked PO/A/E/DP sheet.
- Smart name matching merges differently-truncated spellings of the same player,
  flags look-alikes, and reconciles totals against the final score.

**🔮 Predictions** — best hitters, recent form (rolling last-N games), a
**Monte-Carlo–optimized batting order** that simulates many games to maximize
expected runs, and a suggested **defensive lineup** built from fielding % and
each player's eligible positions.

**⬇️ Export** — one-click styled Excel downloads from the Dashboard, Players, and
Games pages.

---

## Roles & access

Security is enforced by Supabase **Row Level Security**, not just the UI:

- **Viewer** — no account, no login. Reads stats with the public anon key.
- **Admin** — logs in (email/password) to create, edit, import, and delete. The
  anon key physically cannot write, even if the UI is bypassed.

By default viewers see **Players** and **Predictions**; admins see the full menu.

---

## Statistics tracked

**Batting:** AB, R, H, RBI, BB, SO, 2B, 3B, HR, TB, LOB → AVG, OBP, SLG, OPS.
**Pitching:** IP, H, R, ER, BB, SO, HR → ERA (scaled to the league's 6-inning games).
**Defense:** Games, PO, A, E, DP, chances, throws → **Fielding % = (PO + A) / (PO + A + E)**
and throw accuracy. Defensive data is compiled manually from game replays.

---

## Tech stack

| Layer            | Choice                                       |
| ---------------- | -------------------------------------------- |
| Frontend + logic | Streamlit                                    |
| Database + Auth  | Supabase (PostgreSQL, RLS)                   |
| Data / analytics | pandas, numpy                                |
| Charts           | Plotly                                       |
| Ingestion        | pdfplumber (PDF), openpyxl (Excel)           |
| Packaging        | [uv](https://docs.astral.sh/uv/)             |

### Project layout

```
app.py          Entry point: navigation, auth gating, routing
config/         Settings (st.secrets / .env)
db/             Supabase client, schema.sql, migrations/
auth/           Login / session / admin gating
models/         Pydantic models + validation
services/       CRUD + analytics + defensive aggregation
ingestion/      GameChanger PDF, CSV/Excel, defensive sheet, name matching
predictions/    Lineup simulation + heuristics
export/         Styled Excel export
ui/             Page render functions (mobile-first)
utils/          Stat calculations, filters, error messages
tests/          pytest suite
```

---

## Running it

**Backend (once):** create a Supabase project, run [`db/schema.sql`](db/schema.sql)
in the SQL Editor (creates tables, RLS, analytics views, and seeds positions),
enable the **Email** auth provider, and add one admin user. Incremental schema
changes live in [`db/migrations/`](db/migrations) for already-provisioned
databases.

**Local:**

```bash
uv sync
cp .env.example .env          # add SUPABASE_URL + SUPABASE_ANON_KEY
uv run streamlit run app.py
```

**Deploy (Streamlit Community Cloud):** point it at this repo / `main` / `app.py`,
set Python 3.11, and add `SUPABASE_URL` and `SUPABASE_ANON_KEY` under **Secrets**.

> The app reads `st.secrets` first, then `.env`. Never commit real keys. The
> `service_role` key is intentionally unused — only the public anon key reaches
> the client, exactly as RLS expects.

**Tests:** `uv run pytest`  ·  **Lint:** `uv run ruff check .`

---

## Notes

- **ERA, line scores, and the lineup simulator use 6-inning games** (the league's
  regulation length), configurable in `config/settings.py`.
- A `truststore` shim lets the app connect through corporate TLS-inspection
  proxies (validates against the OS certificate store).
