"""Tests for fuzzy player-name matching (truncated GameChanger names)."""

from ingestion.matching import find_match, normalize_name


def test_normalize_folds_accents_and_punct():
    assert normalize_name("Leonardo Vá") == "leonardova"
    assert normalize_name("Iván Enoc Agu") == "ivanenocagu"
    assert normalize_name("Juan C. Córd…") == "juanccord"


def _cache(*names):
    return [{"id": n, "name": n, "nkey": normalize_name(n)} for n in names]


def test_prefix_variants_match_same_player():
    cache = _cache("Leonardo V")
    # A fuller spelling matches the truncated stored name.
    m = find_match(normalize_name("Leonardo Vásquez"), cache)
    assert m is not None and m["name"] == "Leonardo V"


def test_truncated_matches_fuller_stored():
    cache = _cache("Roberto Del Castillo")
    m = find_match(normalize_name("Roberto Del"), cache)
    assert m is not None and m["name"] == "Roberto Del Castillo"


def test_distinct_players_not_merged():
    cache = _cache("Juan Diego T", "Juan Diego V")
    # Neither is a prefix of the other -> no match.
    assert find_match(normalize_name("Juan Diego T"), cache)["name"] == "Juan Diego T"
    assert find_match(normalize_name("Sergio Alonso"), cache) is None


def test_ambiguous_prefix_returns_none():
    # Bare 'Juan Diego' is a prefix of two different players -> ambiguous.
    cache = _cache("Juan Diego T", "Juan Diego V")
    assert find_match(normalize_name("Juan Diego"), cache) is None
