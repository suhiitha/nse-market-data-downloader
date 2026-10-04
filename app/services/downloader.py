"""Core orchestration service for fetching, parsing, validating, and persisting NSE datasets."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import re

from app.clients.nse_client import NSEClient, NSEClientError
from app.config import AppConfig, DatasetConfig, config as default_config
from app.logger import get_logger
from app.storage.csv_storage import CSVStorage, StorageError
from app.validators.data_validator import DataValidator, ValidationResult

logger = get_logger()


@dataclass
class DatasetDownloadResult:
    """Outcome of an individual dataset download operation."""

    dataset_key: str
    dataset_name: str
    status: str  # "SUCCESS", "FAILED", "SKIPPED"
    record_count: int = 0
    file_path: Optional[Path] = None
    error_message: Optional[str] = None
    duration_seconds: float = 0.0


class MarketDataDownloader:
    """Orchestrator for managing multi-dataset NSE acquisition pipelines."""

    def __init__(
        self,
        app_config: Optional[AppConfig] = None,
        client: Optional[NSEClient] = None,
        storage: Optional[CSVStorage] = None,
    ):
        self.config = app_config or default_config
        self.client = client or NSEClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
            max_retries=self.config.max_retries,
            initial_backoff=self.config.initial_backoff_seconds,
            backoff_multiplier=self.config.backoff_multiplier,
            max_backoff=self.config.max_backoff_seconds,
            user_agent=self.config.user_agent,
        )
        self.storage = storage or CSVStorage(base_output_dir=self.config.output_dir)

    def extract_trading_date(self, raw_payload: Any) -> Optional[str]:
        """Attempts to infer trading date in YYYY-MM-DD from payload timestamps.

        NSE payloads often carry timestamp strings such as '01-Oct-2026 16:00:00'
        or '01-Oct-2026'.
        """
        if not isinstance(raw_payload, dict):
            return None

        # Check common timestamp keys
        candidate = raw_payload.get("timestamp") or raw_payload.get("time") or raw_payload.get("asOnDate")
        if not candidate or not isinstance(candidate, str):
            return None

        # Look for pattern DD-Mon-YYYY
        match = re.search(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", candidate)
        if match:
            day, mon, year = match.groups()
            try:
                dt = datetime.strptime(f"{day}-{mon}-{year}", "%d-%b-%Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Look for YYYY-MM-DD
        match_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", candidate)
        if match_iso:
            return match_iso.group(0)

        return None

    def fetch_top_gainers_losers(self, ds_cfg: DatasetConfig) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """Fetches and merges both gainers and losers sub-feeds with category tags."""
        combined_records: List[Dict[str, Any]] = []
        inferred_date: Optional[str] = None

        sources = ds_cfg.sources or [
            {"category": "GAINER", "params": {"index": "gainers"}},
            {"category": "LOSER", "params": {"index": "loosers"}},
        ]

        for src in sources:
            category = src.get("category", "UNKNOWN")
            params = src.get("params", {})
            logger.info("Fetching %s segment for %s...", category, ds_cfg.name)

            data = self.client.get_json(
                endpoint=ds_cfg.endpoint,
                params=params,
                referer=ds_cfg.web_url,
            )

            if not inferred_date:
                inferred_date = self.extract_trading_date(data)

            # NSE variations endpoint returns dict with 'allSec' or 'NIFTY' lists
            records_list: List[Dict[str, Any]] = []
            if isinstance(data, dict):
                # Prefer 'allSec' (all securities) or fallback to 'NIFTY' or 'data'
                if "allSec" in data and isinstance(data["allSec"], dict):
                    records_list = data["allSec"].get("data", [])
                elif "allSec" in data and isinstance(data["allSec"], list):
                    records_list = data["allSec"]
                elif "NIFTY" in data and isinstance(data["NIFTY"], dict):
                    records_list = data["NIFTY"].get("data", [])
                elif "data" in data and isinstance(data["data"], list):
                    records_list = data["data"]
            elif isinstance(data, list):
                records_list = data

            # Tag each record with category
            for rec in records_list:
                if isinstance(rec, dict):
                    item = dict(rec)
                    item["category"] = category
                    combined_records.append(item)

        return combined_records, inferred_date

    def fetch_upper_band_hitters(self, ds_cfg: DatasetConfig) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """Fetches upper circuit band hitting securities."""
        data = self.client.get_json(
            endpoint=ds_cfg.endpoint,
            referer=ds_cfg.web_url,
        )
        inferred_date = self.extract_trading_date(data)

        records_list: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            # Structure: data['upper']['AllSec']['data'] or data['upper']['data']
            upper_data = data.get("upper", {})
            if isinstance(upper_data, dict):
                if "AllSec" in upper_data and isinstance(upper_data["AllSec"], dict):
                    records_list = upper_data["AllSec"].get("data", [])
                elif "data" in upper_data and isinstance(upper_data["data"], list):
                    records_list = upper_data["data"]
            elif isinstance(upper_data, list):
                records_list = upper_data
            elif "data" in data and isinstance(data["data"], list):
                records_list = data["data"]
        elif isinstance(data, list):
            records_list = data

        return records_list, inferred_date

    def fetch_volume_gainers_spurts(self, ds_cfg: DatasetConfig) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """Fetches volume spurts / surge securities."""
        data = self.client.get_json(
            endpoint=ds_cfg.endpoint,
            referer=ds_cfg.web_url,
        )
        inferred_date = self.extract_trading_date(data)

        records_list: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                records_list = data["data"]
        elif isinstance(data, list):
            records_list = data

        return records_list, inferred_date

    def fetch_52_week_high(self, ds_cfg: DatasetConfig) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """Fetches 52-week high equity market securities."""
        data = self.client.get_json(
            endpoint=ds_cfg.endpoint,
            referer=ds_cfg.web_url,
        )
        inferred_date = self.extract_trading_date(data)

        records_list: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                records_list = data["data"]
        elif isinstance(data, list):
            records_list = data

        return records_list, inferred_date

    def download_dataset(
        self,
        dataset_key: str,
        overwrite: bool = True,
        target_date: Optional[str] = None,
    ) -> DatasetDownloadResult:
        """Executes full download pipeline for a single dataset with error containment.

        Args:
            dataset_key: Key matching datasets.yaml (e.g. 'top-gainers-losers').
            overwrite: Whether to overwrite existing CSV if already present.
            target_date: Optional explicit date override (YYYY-MM-DD).

        Returns:
            DatasetDownloadResult detailing status, counts, output file, or error.
        """
        start_time = time.time()
        ds_cfg = self.config.get_dataset(dataset_key)

        if not ds_cfg:
            duration = time.time() - start_time
            msg = f"Unknown dataset key: '{dataset_key}'. Configured keys: {self.config.list_dataset_keys()}"
            logger.error(msg)
            return DatasetDownloadResult(
                dataset_key=dataset_key,
                dataset_name=dataset_key,
                status="FAILED",
                error_message=msg,
                duration_seconds=duration,
            )

        logger.info("Starting download for '%s' (%s)", ds_cfg.name, dataset_key)

        try:
            # 1. Fetch raw data based on dataset key
            if dataset_key == "top-gainers-losers":
                raw_records, inferred_date = self.fetch_top_gainers_losers(ds_cfg)
                composite_keys = ["symbol", "category"]
            elif dataset_key == "upper-band-hitters":
                raw_records, inferred_date = self.fetch_upper_band_hitters(ds_cfg)
                composite_keys = ["symbol"]
            elif dataset_key == "volume-gainers-spurts":
                raw_records, inferred_date = self.fetch_volume_gainers_spurts(ds_cfg)
                composite_keys = ["symbol"]
            elif dataset_key == "52-week-high":
                raw_records, inferred_date = self.fetch_52_week_high(ds_cfg)
                composite_keys = ["symbol"]
            else:
                # Generic fallback for custom configured endpoints
                raw_data = self.client.get_json(endpoint=ds_cfg.endpoint, referer=ds_cfg.web_url)
                inferred_date = self.extract_trading_date(raw_data)
                raw_records = (
                    raw_data.get("data", []) if isinstance(raw_data, dict) else raw_data
                )
                composite_keys = [ds_cfg.primary_key]

            # 2. Validation
            validator = DataValidator(
                expected_fields=ds_cfg.expected_fields,
                primary_key=ds_cfg.primary_key,
            )
            val_result: ValidationResult = validator.validate(
                records=raw_records,
                dataset_name=ds_cfg.name,
                composite_keys=composite_keys,
            )

            if not val_result.is_valid:
                error_details = "; ".join(val_result.errors)
                logger.error("Validation failed for %s: %s", ds_cfg.name, error_details)
                duration = time.time() - start_time
                return DatasetDownloadResult(
                    dataset_key=dataset_key,
                    dataset_name=ds_cfg.name,
                    status="FAILED",
                    error_message=f"Validation failed: {error_details}",
                    duration_seconds=duration,
                )

            # 3. Storage
            resolved_date = (
                target_date
                or inferred_date
                or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            )
            saved_file = self.storage.save_records(
                records=val_result.cleaned_records,
                filename=ds_cfg.output_filename,
                target_date=resolved_date,
                overwrite=overwrite,
            )

            duration = time.time() - start_time
            logger.info(
                "Successfully completed download for '%s': %d records saved to %s in %.2fs",
                ds_cfg.name,
                val_result.record_count,
                saved_file,
                duration,
            )

            return DatasetDownloadResult(
                dataset_key=dataset_key,
                dataset_name=ds_cfg.name,
                status="SUCCESS",
                record_count=val_result.record_count,
                file_path=saved_file,
                duration_seconds=duration,
            )

        except (NSEClientError, StorageError) as exc:
            duration = time.time() - start_time
            err_msg = str(exc)
            logger.error("Pipeline failure for '%s': %s", ds_cfg.name, err_msg)
            return DatasetDownloadResult(
                dataset_key=dataset_key,
                dataset_name=ds_cfg.name,
                status="FAILED",
                error_message=err_msg,
                duration_seconds=duration,
            )
        except Exception as exc:
            duration = time.time() - start_time
            err_msg = f"Unexpected failure: {exc}"
            logger.exception("Unexpected error during download for '%s': %s", ds_cfg.name, exc)
            return DatasetDownloadResult(
                dataset_key=dataset_key,
                dataset_name=ds_cfg.name,
                status="FAILED",
                error_message=err_msg,
                duration_seconds=duration,
            )

    def download_all(
        self,
        overwrite: bool = True,
        target_date: Optional[str] = None,
    ) -> Dict[str, DatasetDownloadResult]:
        """Executes download pipeline for all configured datasets with complete fault isolation.

        Returns:
            Dictionary mapping dataset keys to their respective DatasetDownloadResult.
        """
        results: Dict[str, DatasetDownloadResult] = {}
        dataset_keys = self.config.list_dataset_keys()

        logger.info("Executing download pipeline for %d datasets: %s", len(dataset_keys), dataset_keys)

        for key in dataset_keys:
            res = self.download_dataset(
                dataset_key=key,
                overwrite=overwrite,
                target_date=target_date,
            )
            results[key] = res

        successful = sum(1 for r in results.values() if r.status == "SUCCESS")
        logger.info(
            "Completed download pipeline: %d/%d datasets downloaded successfully",
            successful,
            len(results),
        )

        return results
