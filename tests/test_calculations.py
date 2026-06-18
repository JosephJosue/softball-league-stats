"""Unit tests for utils/calculations.py (pure logic, no DB or secrets)."""

import pandas as pd

from utils import calculations as c


def test_batting_average():
    assert c.batting_average(3, 10) == 0.300
    assert c.batting_average(0, 0) == 0.0  # safe div-by-zero


def test_on_base_pct():
    # (H + BB) / (AB + BB) = (3 + 1) / (9 + 1) = .400
    assert c.on_base_pct(h=3, bb=1, ab=9) == 0.400


def test_total_bases_matches_db_formula():
    # 4 hits: one is a double, one is a HR -> 2 singles(2) + double(2) + HR(4) = 8
    assert c.total_bases(h=4, doubles=1, triples=0, hr=1) == 8


def test_slugging_and_ops():
    slg = c.slugging(tb=8, ab=10)  # .800
    obp = c.on_base_pct(h=4, bb=0, ab=10)  # .400
    assert slg == 0.800
    assert c.ops(obp, slg) == 1.200


def test_rate_stats_bundle():
    rs = c.rate_stats(ab=10, h=3, bb=1, tb=5)
    assert rs == {"avg": 0.300, "obp": 0.364, "slg": 0.500, "ops": 0.864}


def test_ip_outs_roundtrip():
    # Softball/baseball partial-inning notation: 5.2 IP == 17 outs.
    assert c.ip_to_outs(5.2) == 17
    assert c.outs_to_ip(17) == 5.2
    assert c.ip_to_outs(6.0) == 18


def test_era_scaled_to_six_innings():
    # League is 6 innings: 2 ER over a full 6-IP game -> 2.00
    assert c.era(er=2, ip=6.0) == 2.00
    assert c.era(er=0, ip=0.0) == 0.0  # safe div-by-zero


def test_add_rate_columns():
    df = pd.DataFrame([{"ab": 10, "h": 3, "bb": 1, "tb": 5}])
    out = c.add_rate_columns(df)
    assert out.loc[0, "avg"] == 0.300
    assert out.loc[0, "ops"] == 0.864
    # original DataFrame is untouched (function returns a copy)
    assert "avg" not in df.columns


def test_add_rate_columns_empty():
    out = c.add_rate_columns(pd.DataFrame(columns=["ab", "h", "bb", "tb"]))
    assert out.empty
