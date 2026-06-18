"""Unit tests for ingestion.validation (column mapping + row validation)."""

import pandas as pd

from ingestion import validation


def test_auto_map_handles_messy_headers():
    df = pd.DataFrame(
        {"Player Name": ["A"], "AB ": [4], "Hits": [2], "Home Runs": [1], "Notes": ["x"]}
    )
    mapped, mapping, unmapped = validation.auto_map_columns(df)
    assert set(mapping.values()) == {"player_name", "ab", "h", "hr"}
    assert "Notes" in unmapped
    assert list(mapped.columns) == ["player_name", "ab", "h", "hr"]


def test_validate_rows_coerces_and_validates():
    df = pd.DataFrame(
        {"player": ["Sam", "Lee"], "ab": [4, 3], "h": [2, ""], "hr": [1, 0]}
    )
    mapped, _, _ = validation.auto_map_columns(df)
    rows, totals, errors = validation.validate_stat_rows(mapped)
    assert errors == []
    assert totals is None
    # Mapped values are preserved; columns absent from the file are NOT
    # fabricated (the DB applies its 0 defaults on insert).
    assert rows[0]["player_name"] == "Sam"
    assert rows[0]["ab"] == 4 and rows[0]["h"] == 2 and rows[0]["hr"] == 1
    assert "rbi" not in rows[0] and "bb" not in rows[0]
    # blank hit coerced to 0
    assert rows[1]["h"] == 0


def test_validate_rows_flags_bad_line():
    df = pd.DataFrame({"player": ["Bad"], "ab": [2], "h": [5]})
    mapped, _, _ = validation.auto_map_columns(df)
    rows, _, errors = validation.validate_stat_rows(mapped)
    assert rows == []
    assert len(errors) == 1
    assert "cannot exceed at-bats" in errors[0]


def test_totals_row_extracted_and_reconciled():
    df = pd.DataFrame(
        {"player": ["A", "B", "Totals"], "ab": [3, 3, 6], "h": [2, 1, 4], "r": [1, 1, 2]}
    )
    mapped, _, _ = validation.auto_map_columns(df)
    rows, totals, _ = validation.validate_stat_rows(mapped)
    assert len(rows) == 2  # totals row excluded from player rows
    assert totals["h"] == 4
    warnings = validation.reconcile(rows, totals)
    # players sum to 3 hits, totals say 4 -> one warning about Hits
    assert any("Hits" in w for w in warnings)


def test_no_player_column_returns_error():
    df = pd.DataFrame({"ab": [4], "h": [2]})
    mapped, _, _ = validation.auto_map_columns(df)
    rows, _, errors = validation.validate_stat_rows(mapped)
    assert rows == []
    assert errors and "player" in errors[0].lower()
