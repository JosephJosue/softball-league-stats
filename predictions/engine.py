"""Prediction engine: best hitters, rolling form, optimal batting order, and a
suggested defensive lineup.

Pure functions over pandas/dicts (no Streamlit/DB) so they're unit-testable.

The batting-order optimizer turns each hitter's rate stats into plate-appearance
outcome probabilities and runs a simplified Monte-Carlo inning simulation, then
hill-climbs the order to maximize simulated runs. Base-running is intentionally
simple (single = +1 base, double = +2, triple = +3, HR clears) — enough to
reward getting on base and slugging in the right spots without a full engine.
"""

from __future__ import annotations

import random

import pandas as pd

from config.settings import GAME_INNINGS
from utils.calculations import rate_stats

# Order of outcomes checked against a single random draw.
_HIT_OUTCOMES = ("bb", "1b", "2b", "3b", "hr")
_MAX_BATTERS_PER_INNING = 25  # safety cap against pathological (out-prob 0) cases


# --- Best hitters & rolling form -----------------------------------------

def best_hitters(totals: pd.DataFrame, min_ab: int = 0, top_n: int = 10) -> pd.DataFrame:
    """Top hitters by OPS, optionally requiring a minimum number of at-bats."""
    if totals.empty:
        return totals
    df = totals[totals["ab"] >= min_ab] if "ab" in totals.columns else totals
    return df.sort_values("ops", ascending=False).head(top_n).reset_index(drop=True)


def rolling_form(lines: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """Recent-form rate stats from each player's last `window` games.

    Expects columns: player_id, date, ab, h, bb, tb.
    """
    if lines.empty:
        return pd.DataFrame(columns=["player_id", "games", "ab", "h", "avg", "ops"])
    d = lines.sort_values("date", ascending=False)
    rows = []
    for pid, grp in d.groupby("player_id"):
        recent = grp.head(window)
        ab, h = int(recent["ab"].sum()), int(recent["h"].sum())
        bb, tb = int(recent["bb"].sum()), int(recent["tb"].sum())
        rs = rate_stats(ab, h, bb, tb)
        rows.append(
            {"player_id": pid, "games": len(recent), "ab": ab, "h": h,
             "avg": rs["avg"], "ops": rs["ops"]}
        )
    return pd.DataFrame(rows)


# --- Batting-order optimization (Monte-Carlo) ----------------------------

def batter_probs(row: dict) -> dict | None:
    """Per-PA outcome probabilities from a player's counting stats."""
    ab = int(row.get("ab", 0) or 0)
    bb = int(row.get("bb", 0) or 0)
    pa = ab + bb
    if pa <= 0:
        return None
    h = int(row.get("h", 0) or 0)
    doubles = int(row.get("doubles", 0) or 0)
    triples = int(row.get("triples", 0) or 0)
    hr = int(row.get("hr", 0) or 0)
    singles = max(h - doubles - triples - hr, 0)
    p = {
        "bb": bb / pa, "1b": singles / pa, "2b": doubles / pa,
        "3b": triples / pa, "hr": hr / pa,
    }
    p["out"] = max(1.0 - sum(p.values()), 0.0)
    return p


def _draw(probs: dict, rng: random.Random) -> str:
    r = rng.random()
    cum = 0.0
    for outcome in _HIT_OUTCOMES:
        cum += probs[outcome]
        if r < cum:
            return outcome
    return "out"


def _apply(outcome: str, bases: list[bool]) -> int:
    """Advance runners for a non-out outcome; return runs scored."""
    runs = 0
    if outcome == "bb":
        if bases[0] and bases[1] and bases[2]:
            runs += 1
        elif bases[0] and bases[1]:
            bases[2] = True
        elif bases[0]:
            bases[1] = True
        bases[0] = True
    elif outcome == "1b":
        runs += bases[2]
        bases[2], bases[1], bases[0] = bases[1], bases[0], True
    elif outcome == "2b":
        runs += bases[2] + bases[1]
        bases[2], bases[1], bases[0] = bases[0], True, False
    elif outcome == "3b":
        runs += bases[0] + bases[1] + bases[2]
        bases[0], bases[1], bases[2] = False, False, True
    elif outcome == "hr":
        runs += bases[0] + bases[1] + bases[2] + 1
        bases[0] = bases[1] = bases[2] = False
    return runs


def _simulate_game(order_probs: list[dict], innings: int, rng: random.Random) -> int:
    total = 0
    idx = 0
    for _ in range(innings):
        bases = [False, False, False]
        outs = 0
        batters = 0
        while outs < 3 and batters < _MAX_BATTERS_PER_INNING:
            outcome = _draw(order_probs[idx % len(order_probs)], rng)
            idx += 1
            batters += 1
            if outcome == "out":
                outs += 1
            else:
                total += _apply(outcome, bases)
    return total


def expected_runs(order: list[dict], innings: int, sims: int, seed: int = 42) -> float:
    """Mean runs/game for a batting order over `sims` simulated games."""
    if not order:
        return 0.0
    probs = [p["probs"] for p in order]
    rng = random.Random(seed)
    total = sum(_simulate_game(probs, innings, rng) for _ in range(sims))
    return round(total / sims, 2)


def _players_with_probs(totals: pd.DataFrame) -> list[dict]:
    players = []
    for _, row in totals.iterrows():
        p = batter_probs(row)
        if p is None:
            continue
        players.append(
            {"name": row.get("player_name", "?"), "probs": p,
             "obp": float(row.get("obp") or 0), "slg": float(row.get("slg") or 0),
             "ops": float(row.get("ops") or 0)}
        )
    return players


def _heuristic_order(players: list[dict]) -> list[dict]:
    """Table-setters (OBP) at the top, power (SLG) in the RBI spots."""
    rem = players[:]
    order: list[dict] = []

    def take(key: str) -> None:
        if rem:
            best = max(range(len(rem)), key=lambda i: rem[i][key])
            order.append(rem.pop(best))

    for key in ("obp", "obp", "ops", "slg", "slg"):
        take(key)
    order.extend(sorted(rem, key=lambda x: x["ops"], reverse=True))
    return order


def optimize_batting_order(
    totals: pd.DataFrame,
    innings: int = GAME_INNINGS,
    sims: int = 300,
    iterations: int = 40,
    seed: int = 42,
) -> tuple[list[dict], float]:
    """Return (ordered players, estimated runs/game) maximizing simulated runs.

    Evaluates a few sensible starting orders, then hill-climbs by swapping pairs
    and keeping improvements. Uses a fixed seed (common random numbers) so order
    comparisons are fair and the result is reproducible.
    """
    players = _players_with_probs(totals)
    if not players:
        return [], 0.0

    candidates = [
        _heuristic_order(players),
        sorted(players, key=lambda x: x["ops"], reverse=True),
        sorted(players, key=lambda x: x["obp"], reverse=True),
    ]
    best = max(candidates, key=lambda c: expected_runs(c, innings, sims, seed))
    best_runs = expected_runs(best, innings, sims, seed)

    rng = random.Random(seed)
    current, current_runs = best[:], best_runs
    for _ in range(iterations):
        if len(current) < 2:
            break
        i, j = rng.sample(range(len(current)), 2)
        cand = current[:]
        cand[i], cand[j] = cand[j], cand[i]
        runs = expected_runs(cand, innings, sims, seed)
        if runs > current_runs:
            current, current_runs = cand, runs
    return current, current_runs


# --- Defensive lineup -----------------------------------------------------

# Standard field positions to fill (softball includes a short fielder / rover).
FIELD_POSITIONS = ["P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "SF"]


def defensive_lineup(players: list[dict], positions: list[str] = FIELD_POSITIONS) -> dict[str, dict | None]:
    """Greedy best-fielder-per-position assignment.

    players: [{name, eligible: set[str], fielding: float (lower=better), apps}]
    Fills the scarcest positions first (fewest eligible players), picking the
    best fielder still available. Returns {position: player_or_None}.
    """
    assigned: dict[str, dict | None] = {}
    used: set[str] = set()

    def available(pos: str) -> list[dict]:
        return [p for p in players if pos in p["eligible"] and p["name"] not in used]

    for pos in sorted(positions, key=lambda x: len(available(x))):
        cands = available(pos)
        if not cands:
            assigned[pos] = None
            continue
        best = min(cands, key=lambda p: (p["fielding"], -p["apps"]))
        assigned[pos] = best
        used.add(best["name"])
    return assigned
