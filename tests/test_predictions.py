"""Tests for the predictions engine."""

import pandas as pd

from predictions import engine


def _totals():
    return pd.DataFrame([
        {"player_name": "Slugger", "ab": 40, "h": 16, "bb": 4, "tb": 30, "doubles": 4,
         "triples": 0, "hr": 4, "rbi": 15, "games": 10, "obp": 0.45, "slg": 0.75, "ops": 1.20, "errors": 1, "innings_played": 60},
        {"player_name": "OnBase", "ab": 30, "h": 12, "bb": 12, "tb": 15, "doubles": 3,
         "triples": 0, "hr": 0, "rbi": 6, "games": 10, "obp": 0.50, "slg": 0.50, "ops": 1.00, "errors": 0, "innings_played": 60},
        {"player_name": "Weak", "ab": 25, "h": 4, "bb": 1, "tb": 4, "doubles": 0,
         "triples": 0, "hr": 0, "rbi": 1, "games": 10, "obp": 0.19, "slg": 0.16, "ops": 0.35, "errors": 3, "innings_played": 60},
    ])


def test_batter_probs_sum_to_one():
    p = engine.batter_probs({"ab": 10, "bb": 2, "h": 4, "doubles": 1, "triples": 0, "hr": 1})
    assert abs(sum(p.values()) - 1.0) < 1e-9
    assert engine.batter_probs({"ab": 0, "bb": 0}) is None


def test_expected_runs_positive_and_deterministic():
    players = engine._players_with_probs(_totals())
    r1 = engine.expected_runs(players, innings=6, sims=200, seed=1)
    r2 = engine.expected_runs(players, innings=6, sims=200, seed=1)
    assert r1 == r2  # reproducible with a fixed seed
    assert r1 > 0


def test_optimize_returns_full_order():
    order, runs = engine.optimize_batting_order(_totals(), innings=6, sims=120, iterations=10)
    assert len(order) == 3
    assert {p["name"] for p in order} == {"Slugger", "OnBase", "Weak"}
    assert runs > 0


def test_best_hitters_sorted_and_filtered():
    bh = engine.best_hitters(_totals(), min_ab=28, top_n=5)
    assert list(bh["player_name"]) == ["Slugger", "OnBase"]  # Weak (25 AB) filtered out


def test_defensive_lineup_assigns_by_eligibility():
    players = [
        {"name": "A", "eligible": {"SS", "2B"}, "rating": 0.95, "apps": 5},
        {"name": "B", "eligible": {"SS"}, "rating": 0.90, "apps": 5},
        {"name": "C", "eligible": {"P"}, "rating": 0.80, "apps": 5},
    ]
    lineup = engine.defensive_lineup(players, positions=["P", "SS", "2B"])
    # B only plays SS, so scarcity puts B->SS; A then covers 2B; C->P
    assert lineup["SS"]["name"] == "B"
    assert lineup["2B"]["name"] == "A"
    assert lineup["P"]["name"] == "C"


def test_rolling_form_uses_recent_games():
    lines = pd.DataFrame([
        {"player_id": "p", "date": "2026-06-01", "ab": 4, "h": 0, "bb": 0, "tb": 0},
        {"player_id": "p", "date": "2026-06-08", "ab": 4, "h": 3, "bb": 0, "tb": 5},
    ])
    form = engine.rolling_form(lines, window=1)  # only the most recent game
    row = form.iloc[0]
    assert row["games"] == 1 and row["h"] == 3 and row["avg"] == 0.75
