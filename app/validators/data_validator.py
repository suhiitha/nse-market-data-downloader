"""Data validation layer ensuring schema integrity, type correctness, and deduplication."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from app.logger import get_logger

logger = get_logger()


@dataclass
class ValidationResult:
    """Encapsulates the outcome of validating a dataset."""

    is_valid: bool
    record_count: int = 0
    duplicate_count: int = 0
    malformed_count: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    cleaned_records: List[Dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        """Returns a concise text summary of validation results."""
        status = "PASSED" if self.is_valid else "FAILED"
        return (
            f"Validation [{status}]: {self.record_count} valid records, "
            f"{self.duplicate_count} duplicates removed, {self.malformed_count} malformed dropped. "
            f"Errors: {len(self.errors)}"
        )


class DataValidator:
    """Validates raw records against expected schemas and business integrity constraints."""

    def __init__(self, expected_fields: Optional[List[str]] = None, primary_key: str = "symbol"):
        self.expected_fields = expected_fields or []
        self.primary_key = primary_key

    def validate(
        self,
        records: Any,
        dataset_name: str = "dataset",
        composite_keys: Optional[List[str]] = None,
    ) -> ValidationResult:
        """Validates records collection, checks fields, purges malformed data, and deduplicates.

        Args:
            records: Raw records to validate (expected to be a list of dictionaries).
            dataset_name: Human-readable identifier for reporting.
            composite_keys: Optional list of fields to formulate a composite uniqueness key.

        Returns:
            ValidationResult with validation status, counts, and sanitized records.
        """
        result = ValidationResult(is_valid=False)

        # 1. Structure check: must be a non-empty list
        if records is None:
            result.errors.append(f"Payload for '{dataset_name}' is None/empty.")
            logger.error("Validation failed: %s", result.errors[-1])
            return result

        if not isinstance(records, list):
            result.errors.append(
                f"Payload for '{dataset_name}' must be a list of records, got {type(records).__name__}."
            )
            logger.error("Validation failed: %s", result.errors[-1])
            return result

        if len(records) == 0:
            result.errors.append(f"Record set for '{dataset_name}' is empty (0 records received).")
            logger.error("Validation failed: %s", result.errors[-1])
            return result

        # 2. Check schema fields on records
        # Check if the required expected fields exist across the dataset
        if self.expected_fields:
            first_valid_dict = next((r for r in records if isinstance(r, dict)), None)
            if not first_valid_dict:
                result.errors.append(f"No dictionary records found in '{dataset_name}'.")
                return result

            missing_fields = [
                field for field in self.expected_fields if field not in first_valid_dict
            ]
            if missing_fields:
                result.errors.append(
                    f"Dataset '{dataset_name}' is missing expected fields: {missing_fields}"
                )
                logger.error("Validation failed: %s", result.errors[-1])
                return result

        # 3. Record-level inspection: malformed records & deduplication
        seen_keys: Set[str] = set()
        deduped_records: List[Dict[str, Any]] = []

        for idx, item in enumerate(records):
            if not isinstance(item, dict):
                result.malformed_count += 1
                result.warnings.append(f"Record at index {idx} dropped: not a dictionary ({item}).")
                continue

            # Primary key existence and validation
            key_val = item.get(self.primary_key)
            if key_val is None or str(key_val).strip() == "":
                result.malformed_count += 1
                result.warnings.append(
                    f"Record at index {idx} dropped: missing primary key '{self.primary_key}'."
                )
                continue

            # Composite key resolution for deduplication (e.g. symbol + category)
            if composite_keys:
                key_elements = [str(item.get(k, "")).strip().upper() for k in composite_keys]
                dedup_key = "::".join(key_elements)
            else:
                dedup_key = str(key_val).strip().upper()

            if dedup_key in seen_keys:
                result.duplicate_count += 1
                result.warnings.append(f"Duplicate record with key '{dedup_key}' omitted at index {idx}.")
                continue

            seen_keys.add(dedup_key)
            deduped_records.append(item)

        # 4. Final count verification
        if not deduped_records:
            result.errors.append(
                f"No valid records remained for '{dataset_name}' after dropping malformed items."
            )
            return result

        result.cleaned_records = deduped_records
        result.record_count = len(deduped_records)
        result.is_valid = True

        logger.info(
            "Validation successful for %s: %d records, %d duplicates removed, %d malformed dropped",
            dataset_name,
            result.record_count,
            result.duplicate_count,
            result.malformed_count,
        )
        return result
