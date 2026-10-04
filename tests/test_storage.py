"""Unit tests for the CSVStorage adapter."""

from pathlib import Path
import pandas as pd
import pytest

from app.storage.csv_storage import CSVStorage, StorageError


def test_successful_csv_creation(tmp_path: Path):
    """Verify that records are accurately written to CSV with pandas."""
    storage = CSVStorage(base_output_dir=tmp_path)
    records = [
        {"symbol": "INFY", "series": "EQ", "ltp": 1500.0},
        {"symbol": "TCS", "series": "EQ", "ltp": 3800.0},
    ]

    saved_path = storage.save_records(
        records=records,
        filename="test_dataset",
        target_date="2026-10-04",
    )

    assert saved_path.exists()
    assert saved_path.name == "test_dataset.csv"
    assert saved_path.parent.name == "2026-10-04"

    # Verify content read back via pandas
    df = pd.read_csv(saved_path)
    assert len(df) == 2
    assert list(df["symbol"]) == ["INFY", "TCS"]


def test_date_organization_subfolder(tmp_path: Path):
    """Verify that target dates create dedicated YYYY-MM-DD subfolders."""
    storage = CSVStorage(base_output_dir=tmp_path)
    records = [{"symbol": "SBIN", "ltp": 800.0}]

    path_1 = storage.save_records(records, "data1", target_date="2026-09-30")
    path_2 = storage.save_records(records, "data2", target_date="2026-10-01")

    assert path_1.parent == tmp_path / "2026-09-30"
    assert path_2.parent == tmp_path / "2026-10-01"


def test_duplicate_file_handling_overwrite(tmp_path: Path):
    """Verify that running on the same date overwrites cleanly without duplicate names."""
    storage = CSVStorage(base_output_dir=tmp_path)

    initial_records = [{"symbol": "INFY", "ltp": 1500.0}]
    updated_records = [{"symbol": "INFY", "ltp": 1550.0}, {"symbol": "TCS", "ltp": 3900.0}]

    # Run 1
    path1 = storage.save_records(initial_records, "stocks", target_date="2026-10-04", overwrite=True)
    df1 = pd.read_csv(path1)
    assert len(df1) == 1

    # Run 2 on same day
    path2 = storage.save_records(updated_records, "stocks", target_date="2026-10-04", overwrite=True)
    assert path1 == path2  # Same exact path, no stocks_1.csv or final.csv created

    df2 = pd.read_csv(path2)
    assert len(df2) == 2
    assert float(df2.loc[df2["symbol"] == "INFY", "ltp"].iloc[0]) == 1550.0


def test_duplicate_file_handling_skip(tmp_path: Path):
    """Verify that skip_if_exists leaves the original file content intact."""
    storage = CSVStorage(base_output_dir=tmp_path)

    records_original = [{"symbol": "ORIGINAL", "ltp": 100.0}]
    records_new = [{"symbol": "REPLACED", "ltp": 200.0}]

    file_path = storage.save_records(records_original, "skip_test", target_date="2026-10-04")
    # Call with skip_if_exists=True and overwrite=False
    storage.save_records(records_new, "skip_test", target_date="2026-10-04", overwrite=False, skip_if_exists=True)

    df = pd.read_csv(file_path)
    assert list(df["symbol"]) == ["ORIGINAL"]


def test_storage_error_on_empty_records(tmp_path: Path):
    """Verify that attempting to save empty records raises StorageError."""
    storage = CSVStorage(base_output_dir=tmp_path)
    with pytest.raises(StorageError, match="Cannot save empty records"):
        storage.save_records([], "empty_test", target_date="2026-10-04")
