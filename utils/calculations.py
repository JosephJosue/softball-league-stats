"""Pure stat calculations — no I/O, no Streamlit, no DB.

Kept dependency-light so it can be unit-tested in isolation and reused by the
UI, analytics, predictions, and export layers. All rate stats are rounded to
3 decimals (the baseball/softball convention, e.g. .333).
"""

from __future__ import annotations

import pandas as pd

# Single source of truth for regulation game length (6 innings in this league).
# ERA is scaled to this rather than MLB's 9.
from config.settings import GAME_INNINGS


def _safe_div(numerator: float, denominator: float, ndigits: int = 3) -> float:
    """Divide, returning 0.0 when the denominator is zero (avoids div-by-zero)."""
    if not denominator:
        return 0.0
    return round(numerator / denominator, ndigits)


# --- Offensive rate stats -------------------------------------------------

def batting_average(h: int, ab: int) -> float:
    """AVG = H / AB."""
    return _safe_div(h, ab)


def on_base_pct(h: int, bb: int, ab: int) -> float:
    """OBP = (H + BB) / (AB + BB).

    Simplified for this league: no HBP or sacrifice flies are tracked, so they
    are omitted from the denominator.
    """
    return _safe_div(h + bb, ab + bb)


def total_bases(h: int, doubles: int, triples: int, hr: int) -> int:
    """TB = singles + 2*2B + 3*3B + 4*HR  ==  H + 2B + 2*3B + 3*HR.

    Matches the generated `tb` column in the database.
    """
    return h + doubles + 2 * triples + 3 * hr


def slugging(tb: int, ab: int) -> float:
    """SLG = TB / AB."""
    return _safe_div(tb, ab)


def ops(obp: float, slg: float) -> float:
    """OPS = OBP + SLG."""
    return round(obp + slg, 3)


def rate_stats(ab: int, h: int, bb: int, tb: int) -> dict[str, float]:
    """Compute AVG/OBP/SLG/OPS from raw totals in one call."""
    avg = batting_average(h, ab)
    obp = on_base_pct(h, bb, ab)
    slg = slugging(tb, ab)
    return {"avg": avg, "obp": obp, "slg": slg, "ops": ops(obp, slg)}


# --- Pitching -------------------------------------------------------------

def ip_to_outs(ip: float) -> int:
    """Convert innings-pitched notation to outs.

    Softball/baseball write partial innings as .1 (one out) and .2 (two outs),
    NOT decimals — so 5.2 IP == 5 innings + 2 outs == 17 outs.
    """
    whole = int(ip)
    thirds = int(round((ip - whole) * 10))  # .1 -> 1 out, .2 -> 2 outs
    return whole * 3 + thirds


def outs_to_ip(outs: int) -> float:
    """Inverse of ip_to_outs: 17 outs -> 5.2 IP."""
    return outs // 3 + (outs % 3) / 10


def era(er: int, ip: float, innings: int = GAME_INNINGS) -> float:
    """ERA = ER * innings_per_game / IP (scaled to a full game)."""
    outs = ip_to_outs(ip)
    return round(er * innings * 3 / outs, 2) if outs else 0.0


# --- DataFrame helper -----------------------------------------------------

def add_rate_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Append avg/obp/slg/ops columns to a totals DataFrame.

    Expects integer columns: ab, h, bb, tb. Returns a copy so the caller's
    DataFrame is untouched. Useful when working from raw sums rather than the
    pre-computed SQL views.
    """
    if df.empty:
        return df.assign(avg=[], obp=[], slg=[], ops=[])
    out = df.copy()
    out["avg"] = out.apply(lambda r: batting_average(r["h"], r["ab"]), axis=1)
    out["obp"] = out.apply(lambda r: on_base_pct(r["h"], r["bb"], r["ab"]), axis=1)
    out["slg"] = out.apply(lambda r: slugging(r["tb"], r["ab"]), axis=1)
    out["ops"] = (out["obp"] + out["slg"]).round(3)
    return out
