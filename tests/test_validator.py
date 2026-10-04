"""Unit tests for the DataValidator layer."""

import pytest
from app.validators.data_validator import DataValidator, ValidationResult


def test_valid_data_passes():
    """Verify that a compliant list of records passes validation."""
    validator = DataValidator(
        expected_fields=["symbol", "series", "ltp"],
        primary_key="symbol",
    )
    records = [
        {"symbol": "INFY", "series": "EQ", "ltp": 1500.0, "volume": 1000},
        {"symbol": "TCS", "series": "EQ", "ltp": 3800.0, "volume": 2000},
    ]
    result = validator.validate(records, dataset_name="TestEquity")

    assert result.is_valid is True
    assert result.record_count == 2
    assert result.duplicate_count == 0
    assert result.malformed_count == 0
    assert len(result.errors) == 0
    assert len(result.cleaned_records) == 2


def test_empty_response_fails():
    """Verify that empty list fails validation."""
    validator = DataValidator(expected_fields=["symbol"])
    result = validator.validate([], dataset_name="EmptySet")

    assert result.is_valid is False
    assert result.record_count == 0
    assert any("empty" in err.lower() for err in result.errors)


def test_none_response_fails():
    """Verify that None payload fails validation."""
    validator = DataValidator(expected_fields=["symbol"])
    result = validator.validate(None, dataset_name="NoneSet")

    assert result.is_valid is False
    assert any("empty" in err.lower() or "none" in err.lower() for err in result.errors)


def test_invalid_data_structure_fails():
    """Verify that non-list payloads (e.g. dict or string) fail validation."""
    validator = DataValidator(expected_fields=["symbol"])
    result = validator.validate({"unexpected": "dictionary"}, dataset_name="DictSet")

    assert result.is_valid is False
    assert any("list" in err.lower() for err in result.errors)


def test_missing_expected_columns_fails():
    """Verify that records missing mandatory schema fields fail validation."""
    validator = DataValidator(expected_fields=["symbol", "ltp", "required_field"])
    records = [
        {"symbol": "RELIANCE", "ltp": 2900.0},
    ]
    result = validator.validate(records, dataset_name="MissingFields")

    assert result.is_valid is False
    assert any("missing expected fields" in err.lower() for err in result.errors)


def test_duplicate_rows_detected_and_purged():
    """Verify that duplicate rows by primary key are detected and deduplicated."""
    validator = DataValidator(
        expected_fields=["symbol", "ltp"],
        primary_key="symbol",
    )
    records = [
        {"symbol": "INFY", "ltp": 1500.0},
        {"symbol": "TCS", "ltp": 3800.0},
        {"symbol": "INFY", "ltp": 1510.0},  # Duplicate INFY
        {"symbol": "infy", "ltp": 1512.0},  # Case-insensitive duplicate
    ]
    result = validator.validate(records, dataset_name="Duplicates")

    assert result.is_valid is True
    assert result.record_count == 2
    assert result.duplicate_count == 2
    symbols = [r["symbol"] for r in result.cleaned_records]
    assert symbols == ["INFY", "TCS"]


def test_composite_key_deduplication():
    """Verify that composite keys allow same symbol across different categories."""
    validator = DataValidator(
        expected_fields=["symbol", "category", "ltp"],
        primary_key="symbol",
    )
    records = [
        {"symbol": "NIFTY_STOCK", "category": "GAINER", "ltp": 100.0},
        {"symbol": "NIFTY_STOCK", "category": "LOSER", "ltp": 95.0},
        {"symbol": "NIFTY_STOCK", "category": "GAINER", "ltp": 102.0},  # duplicate gainer
    ]
    result = validator.validate(
        records,
        dataset_name="Composite",
        composite_keys=["symbol", "category"],
    )

    assert result.is_valid is True
    assert result.record_count == 2
    assert result.duplicate_count == 1


def test_malformed_records_filtered():
    """Verify that invalid items (non-dict or missing primary key) are dropped."""
    validator = DataValidator(
        expected_fields=["symbol"],
        primary_key="symbol",
    )
    records = [
        {"symbol": "VALID1", "ltp": 10.0},
        "not-a-dict-string",
        {"missing_symbol": "ABC", "ltp": 20.0},
        {"symbol": "   ", "ltp": 30.0},  # blank symbol
        {"symbol": "VALID2", "ltp": 40.0},
    ]
    result = validator.validate(records, dataset_name="Malformed")

    assert result.is_valid is True
    assert result.record_count == 2
    assert result.malformed_count == 3
    assert [r["symbol"] for r in result.cleaned_records] == ["VALID1", "VALID2"]
