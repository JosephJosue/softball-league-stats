"""Live read-only smoke test against your Supabase project.

Validates the full stack end-to-end WITHOUT writing anything:
    settings -> supabase client (anon) -> service layer -> live DB

Run from the project root (needs .env with SUPABASE_URL + SUPABASE_ANON_KEY):
    uv run python scripts/check_connection.py

Expected: 12 positions (the seed), plus current team/player/game counts.
"""

from __future__ import annotations

import pathlib
import sys

# Running a script file puts scripts/ (not the project root) on sys.path, so the
# project packages aren't importable. Add the project root explicitly.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from config.settings import is_configured
from services.analytics import player_season_totals
from services.games import list_games
from services.players import list_players
from services.positions import list_positions
from services.teams import list_teams


def main() -> None:
    if not is_configured():
        print("✗ Supabase not configured. Set SUPABASE_URL + SUPABASE_ANON_KEY in .env")
        raise SystemExit(1)

    positions = list_positions()
    print(f"✓ positions:           {len(positions):>4}  (expected 12 from the seed)")
    print(f"✓ teams:               {len(list_teams()):>4}")
    print(f"✓ players:             {len(list_players()):>4}")
    print(f"✓ games:               {len(list_games()):>4}")
    print(f"✓ player season view:  {len(player_season_totals()):>4} rows")
    print("\nService layer reached Supabase successfully (read-only).")


if __name__ == "__main__":
    main()
