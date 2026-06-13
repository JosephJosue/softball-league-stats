"""Unit tests for models/schemas.py validation + insert serialization."""

import datetime

import pytest
from pydantic import ValidationError

from models.schemas import GameCreate, PlayerCreate, PlayerGameStatsCreate, TeamCreate


def test_team_for_insert_drops_none():
    payload = TeamCreate(name="Sharks").for_insert()
    assert payload == {"name": "Sharks"}  # abbreviation/season (None) dropped


def test_game_date_serialized_to_iso():
    payload = GameCreate(game_date=datetime.date(2026, 6, 1), home_score=5).for_insert()
    assert payload["game_date"] == "2026-06-01"
    assert "notes" not in payload  # None dropped
    assert payload["status"] == "final"  # default applied


def test_valid_player_game_stats_drops_pitching_when_absent():
    line = PlayerGameStatsCreate(game_id="g", player_id="p", ab=4, h=2, doubles=1, hr=1)
    payload = line.for_insert()
    assert "ip" not in payload and "er" not in payload  # None pitching dropped
    assert payload["ab"] == 4 and payload["h"] == 2


def test_hits_cannot_exceed_at_bats():
    with pytest.raises(ValidationError):
        PlayerGameStatsCreate(game_id="g", player_id="p", ab=2, h=3)


def test_extra_base_hits_cannot_exceed_hits():
    with pytest.raises(ValidationError):
        PlayerGameStatsCreate(game_id="g", player_id="p", ab=5, h=1, doubles=2)


def test_negative_counting_stat_rejected():
    with pytest.raises(ValidationError):
        PlayerGameStatsCreate(game_id="g", player_id="p", ab=-1)


def test_player_bats_throws_patterns():
    PlayerCreate(name="A", bats="S", throws="R")  # valid
    with pytest.raises(ValidationError):
        PlayerCreate(name="B", bats="X")  # invalid handedness
