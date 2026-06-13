# 🥎 Softball League Stats

A production-ready **Streamlit + Supabase** app for managing a softball league:
game/score tracking, player & team stats (offense + defense), league analytics,
simple predictions, PDF/Excel ingestion, and Excel export.

Built mobile-first — it's meant to be used mostly from a phone.

---

## Tech stack

| Layer            | Choice                                             |
| ---------------- | -------------------------------------------------- |
| Frontend + logic | Streamlit                                          |
| Database + Auth  | Supabase (PostgreSQL)                              |
| DB access        | `supabase-py` client                               |
| Data processing  | pandas / numpy                                      |
| Charts           | Plotly                                             |
| Ingestion        | pdfplumber (PDF), openpyxl/pandas (Excel)         |
| Packaging        | [uv](https://docs.astral.sh/uv/)                   |

### Roles (enforced by Row Level Security, not the UI)

- **Viewer** — no account, no login. Reads stats using the public **anon** key.
- **Admin** — logs in via Supabase Auth (email/password). Any authenticated user
  may create/edit data. The anon key physically cannot write, even if the UI is
  bypassed.

---

## Project layout

```
app.py            Streamlit entry: nav shell + connectivity check
config/           Settings (reads st.secrets / .env)
db/               Supabase client + schema.sql (run this in Supabase)
auth/             Login / session / admin gating          (Phase 2)
models/           Pydantic data models                     (Phase 2)
services/         CRUD + analytics                          (Phase 2)
ui/               Page render functions                     (Phase 3)
ingestion/        PDF + Excel parsers + validation          (Phase 4)
predictions/      Rolling averages + heuristics             (Phase 5)
export/           Excel export                              (Phase 6)
utils/            Stat calculations + shared filters
```

---

## Setup

### 1. Supabase

1. Create a project at [supabase.com](https://supabase.com) and copy the
   **Project URL** and the **anon** public key
   (Project Settings → API).
2. Open the **SQL Editor**, paste the contents of [`db/schema.sql`](db/schema.sql),
   and run it. This creates all tables, indexes, RLS policies, analytics views,
   and seeds the `positions` table.
3. Go to **Authentication → Providers** and enable **Email**. Then
   **Authentication → Users → Add user** to create your single admin login.

Verify in the SQL Editor:

```sql
select tablename from pg_tables where schemaname = 'public';
select * from pg_policies where schemaname = 'public';
```

### 2. Local app (with `uv`)

```bash
# Install uv once (if needed):
#   curl -LsSf https://astral.sh/uv/install.sh | sh

uv sync                      # creates .venv and installs all dependencies
cp .env.example .env         # then fill in SUPABASE_URL + SUPABASE_ANON_KEY
uv run streamlit run app.py  # uv manages the virtualenv for you
```

The app opens in your browser. On the Phase 1 scaffold you should see a green
**"Connected to Supabase ✅"** message once your keys and schema are in place.

> Secrets: the app reads `st.secrets` first, then falls back to `.env`. Both
> `.env` and `.streamlit/secrets.toml` are git-ignored — never commit real keys.
> The `service_role` key is intentionally unused; it bypasses RLS and must never
> reach the client.

### Migrations

On an **existing** database, apply incremental changes from `db/migrations/` in
the Supabase SQL Editor (new installs already include them via `schema.sql`):

- `001_add_player_positions.sql` — adds the `players.positions` (eligible
  defensive positions) column.

---

## Troubleshooting

**`SSL: CERTIFICATE_VERIFY_FAILED` / "unable to get local issuer certificate"**

Common on corporate networks that do TLS inspection — their internal root CA is
trusted by your OS/browser but not by Python's bundled `certifi` certs. The app
ships with [`truststore`](https://truststore.readthedocs.io/) and calls
`truststore.inject_into_ssl()` at startup, which makes Python validate against the
**OS certificate store** (where the corporate CA already lives). After pulling
this change, run `uv sync` and restart the app. If you still see the error, your
OS may be missing the corporate root CA — ask IT, or as a fallback point Python at
a CA bundle: `export SSL_CERT_FILE=/path/to/corp-ca.pem` (Windows PowerShell:
`$env:SSL_CERT_FILE="C:\path\to\corp-ca.pem"`).

---

## Build phases

This project is built and reviewed in phases:

1. **Architecture & Setup** ✅ — structure, schema, config, scaffold.
2. **Core Backend** — models, auth/session, CRUD + analytics services.
3. **Streamlit UI** — navigation, pages, mobile-first tables & charts.
4. **Data Ingestion** — PDF + Excel parsers, validation/reconciliation.
5. **Predictions** — rolling averages + lineup heuristics.
6. **Export + Polish** — Excel export, UX refinement.
