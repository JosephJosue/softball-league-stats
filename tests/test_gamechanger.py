"""Tests for the GameChanger PDF parser against real sample scorecards.

Samples live in tests/fixtures/. If they're absent (e.g. not committed), the
tests skip rather than fail.
"""

import datetime
from pathlib import Path

import pytest

from ingestion import gamechanger as gc

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "zikions_vs_calientabancas.pdf"


@pytest.fixture
def card():
    if not SAMPLE.exists():
        pytest.skip("sample scorecard PDF not present")
    return gc.parse(SAMPLE.read_bytes())


def test_header_and_score(card):
    assert card.away_team == "Zikions IESC"
    assert card.home_team == "Calientabancas IESC"
    assert card.away_score == 12
    assert card.home_score == 13
    assert card.date == datetime.date(2026, 6, 11)


def test_line_score_sums_match_final(card):
    assert sum(card.away_innings) == card.away_score
    assert sum(card.home_innings) == card.home_score


def test_player_counts_and_totals(card):
    assert sum(p.h for p in card.away_players) == card.away_totals["h"]
    assert sum(p.h for p in card.home_players) == card.home_totals["h"]


def test_extra_base_hits_from_annotations(card):
    # Carlos Polack (truncated in the table) had 2 doubles + 1 triple.
    polack = next(p for p in card.away_players if p.name.startswith("Carlos Pola"))
    assert polack.doubles == 2
    assert polack.triples == 1


def test_pitching_and_errors(card):
    pitchers = [p for p in card.away_players if p.ip is not None]
    assert pitchers and pitchers[0].ip == 5.1
    # errors are recovered from the "E:" annotation line
    assert any(p.errors > 0 for p in card.away_players)
