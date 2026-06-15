"""Tests for defensive-stats parsing and fielding math."""

import pandas as pd

from ingestion import defense as defense_parser
from services.defense import fielding_pct


def test_fielding_pct():
    assert fielding_pct(3, 1, 2) == round(4 / 6, 3)  # (PO+A)/(PO+A+E)
    assert fielding_pct(0, 0, 0) is None  # no chances


def test_looks_like_defense_detection():
    defensive = pd.DataFrame(columns=["Jugador", "J", "PO", "A", "E", "DP"])
    batting = pd.DataFrame(columns=["Player", "AB", "R", "H", "RBI"])
    assert defense_parser.looks_like_defense(defensive)
    assert not defense_parser.looks_like_defense(batting)


def test_parse_maps_spanish_headers():
    df = pd.DataFrame([
        {"Jugador": "Juan Diego Vásquez", "J": 4, "PO": 3, "A": 1, "E": 2, "DP": 0,
         "OPO": 8, "TIRO BUENO": 3, "TIRO TOTALES": 5},
        {"Jugador": None, "J": None, "PO": None, "A": None, "E": None, "DP": None},
    ])
    rows, errors = defense_parser.parse(df)
    assert errors == []
    assert len(rows) == 1  # blank row skipped
    r = rows[0]
    assert r["player_name"] == "Juan Diego Vásquez"
    assert r["po"] == 3 and r["a"] == 1 and r["e"] == 2
    assert r["good_throws"] == 3 and r["total_throws"] == 5


def test_parse_requires_player_column():
    rows, errors = defense_parser.parse(pd.DataFrame([{"PO": 1, "A": 1, "DP": 0}]))
    assert rows == [] and errors
