"""Tests for friendly DB error translation."""

from utils.errors import humanize_db_error


class _ApiError(Exception):
    def __init__(self, payload: dict):
        self.code = payload.get("code")
        self.message = payload.get("message")
        super().__init__(payload)


def test_missing_column_points_to_migration():
    msg = humanize_db_error(
        _ApiError({"code": "PGRST204", "message": "Could not find the 'x' column ... schema cache"})
    )
    assert "migration" in msg.lower()


def test_conflict_explains_duplicate_player():
    msg = humanize_db_error(
        _ApiError({"code": "21000", "message": "ON CONFLICT DO UPDATE ... affect row a second time"})
    )
    assert "same person" in msg or "distinct names" in msg


def test_foreign_key_is_friendly():
    assert "linked" in humanize_db_error(_ApiError({"code": "23503", "message": "fk"}))


def test_plain_exception_falls_back():
    assert "boom" in humanize_db_error(ValueError("boom"))
