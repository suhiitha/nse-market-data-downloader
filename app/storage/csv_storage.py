"""CSV Storage adapter for saving structured market datasets by date."""

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

from app.logger import get_logger

logger = get_logger()


class StorageError(Exception):
    """Base exception for storage write failures."""
    pass


class CSVStorage:
    """Manages writing datasets to deterministic CSV files organized by date."""

    def __init__(self, base_output_dir: Path):
        self.base_output_dir = Path(base_output_dir)

    def resolve_date_directory(self, target_date: Optional[str] = None) -> Path:
        """Resolves the subfolder for the target date (format: YYYY-MM-DD).

        Args:
            target_date: Optional date string in YYYY-MM-DD format. Defaults to today's UTC/IST date.

        Returns:
            Path object pointing to the date directory (e.g. data/2026-10-04).
        """
        if not target_date:
            target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Sanitize date to prevent path traversal
        clean_date = target_date.strip().replace("/", "-")
        date_dir = self.base_output_dir / clean_date
        return date_dir

    def save_records(
        self,
        records: List[Dict[str, Any]],
        filename: str,
        target_date: Optional[str] = None,
        overwrite: bool = True,
        skip_if_exists: bool = False,
    ) -> Path:
        """Writes records list to a deterministic CSV file inside the dated subfolder.

        Args:
            records: Validated list of dictionary records.
            filename: Target file name (e.g. 'top_gainers_losers' or 'top_gainers_losers.csv').
            target_date: Optional date string YYYY-MM-DD. Defaults to current date.
            overwrite: Whether to safely overwrite if the file already exists.
            skip_if_exists: If True and file exists, skips re-writing and logs decision.

        Returns:
            Absolute Path to written CSV file.

        Raises:
            StorageError: On I/O or permissions failures.
        """
        if not records:
            raise StorageError("Cannot save empty records list to CSV.")

        if not filename.endswith(".csv"):
            filename = f"{filename}.csv"

        date_dir = self.resolve_date_directory(target_date)

        try:
            date_dir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise StorageError(f"Failed to create output directory {date_dir}: {err}") from err

        target_file = date_dir / filename

        # Check existing file status
        if target_file.exists():
            if skip_if_exists and not overwrite:
                logger.info(
                    "Target file already exists and skip requested: %s (leaving existing file untouched)",
                    target_file,
                )
                return target_file
            logger.info("Target file already exists. Overwriting deterministically: %s", target_file)

        try:
            df = pd.DataFrame(records)
            # Write to temporary file first then replace for atomic persistence
            temp_file = date_dir / f".tmp_{filename}"
            df.to_csv(temp_file, index=False, encoding="utf-8")
            temp_file.replace(target_file)

            logger.info("Saved %d records: %s", len(records), target_file)
            return target_file

        except PermissionError as err:
            logger.error("Permission denied writing to %s: %s", target_file, err)
            raise StorageError(f"Permission denied writing to {target_file}: {err}") from err
        except Exception as err:
            logger.error("Failed to write CSV file %s: %s", target_file, err)
            raise StorageError(f"Failed to write CSV to {target_file}: {err}") from err
