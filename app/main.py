"""CLI Entrypoint for the NSE Market Data Downloader."""

import argparse
from pathlib import Path
import sys
import time
from typing import Dict, Optional

from app.config import AppConfig, config as default_config
from app.logger import get_logger, setup_logger
from app.services.downloader import DatasetDownloadResult, MarketDataDownloader
from app.storage.csv_storage import CSVStorage


def print_summary(
    results: Dict[str, DatasetDownloadResult],
    output_dir: Path,
) -> None:
    """Formats and displays the clean summary table required for CLI runs."""
    print("\nNSE Market Data Downloader")
    print("==========================")

    successful_count = 0
    total_count = len(results)
    latest_output_path: Optional[Path] = None

    for key, res in results.items():
        if res.status == "SUCCESS":
            successful_count += 1
            if res.file_path and res.file_path.parent:
                latest_output_path = res.file_path.parent
            status_symbol = "[✓]"
            details = f"{res.record_count:>5} records  ({res.duration_seconds:.2f}s)"
        else:
            status_symbol = "[✗]"
            err = res.error_message or "Unknown failure"
            # truncate long error strings for concise CLI display
            short_err = err if len(err) <= 35 else f"{err[:32]}..."
            details = f"{short_err}  ({res.duration_seconds:.2f}s)"

        padded_name = f"{res.dataset_name:<26}"
        print(f"{status_symbol} {padded_name} {details}")

    print("\nCompleted:")
    print(f"{successful_count}/{total_count} datasets downloaded successfully")

    display_out_dir = latest_output_path or output_dir
    print("\nOutput directory:")
    print(f"{display_out_dir}/")
    print()


def run_cli(args: Optional[list] = None) -> int:
    """Parses arguments and runs the downloader service.

    Returns:
        Process exit code (0 for success or partial success, 1 for fatal errors).
    """
    parser = argparse.ArgumentParser(
        prog="nse-downloader",
        description="Reliable CLI tool for downloading NSE India market datasets to date-organized CSVs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py
  python main.py --dataset top-gainers-losers
  python main.py --dataset upper-band-hitters --output-dir ./market_data
  python main.py --list-datasets
        """,
    )

    parser.add_argument(
        "-d",
        "--dataset",
        type=str,
        default=None,
        help="Specify an individual dataset key to download (e.g. top-gainers-losers, upper-band-hitters, volume-gainers-spurts, 52-week-high). Defaults to all datasets.",
    )

    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default=None,
        help="Directory where CSV files will be stored (defaults to ./data).",
    )

    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Explicit date override for directory organization (format: YYYY-MM-DD).",
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip writing files that already exist on disk instead of overwriting.",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging verbosity level (default: INFO).",
    )

    parser.add_argument(
        "--list-datasets",
        action="store_true",
        help="List all configured dataset keys and descriptions, then exit.",
    )

    parser.add_argument(
        "--schedule",
        type=int,
        default=None,
        help="Run continuously on a schedule every N minutes.",
    )

    parsed_args = parser.parse_args(args)

    # Initialize Logger
    app_cfg = default_config
    if parsed_args.output_dir:
        custom_out = Path(parsed_args.output_dir)
        app_cfg.output_dir = custom_out if custom_out.is_absolute() else app_cfg.base_dir / custom_out

    log_level = parsed_args.log_level or app_cfg.log_level
    setup_logger(
        log_dir=app_cfg.log_dir,
        log_level=log_level,
    )
    logger = get_logger()

    # Handle --list-datasets
    if parsed_args.list_datasets:
        print("\nConfigured NSE Datasets:")
        print("------------------------")
        for key in app_cfg.list_dataset_keys():
            ds = app_cfg.get_dataset(key)
            name = ds.name if ds else key
            desc = ds.description if ds else ""
            print(f"• {key:<24} - {name} ({desc})")
        print()
        return 0

    overwrite = not parsed_args.skip_existing
    storage = CSVStorage(base_output_dir=app_cfg.output_dir)
    downloader = MarketDataDownloader(app_config=app_cfg, storage=storage)

    def execute_run() -> int:
        logger.info("Starting NSE Market Data Downloader execution")
        start_overall = time.time()

        if parsed_args.dataset:
            # Single dataset requested
            key = parsed_args.dataset.strip()
            if key not in app_cfg.list_dataset_keys():
                logger.error(
                    "Invalid dataset '%s'. Available choices: %s",
                    key,
                    app_cfg.list_dataset_keys(),
                )
                print(f"Error: Unknown dataset '{key}'. Available: {', '.join(app_cfg.list_dataset_keys())}")
                return 1

            result = downloader.download_dataset(
                dataset_key=key,
                overwrite=overwrite,
                target_date=parsed_args.date,
            )
            results = {key: result}
        else:
            # Download all datasets
            results = downloader.download_all(
                overwrite=overwrite,
                target_date=parsed_args.date,
            )

        total_elapsed = time.time() - start_overall
        logger.info("Completed execution in %.2f seconds", total_elapsed)

        print_summary(results, app_cfg.output_dir)

        # Return 0 if at least one dataset succeeded, 1 if all failed
        successful = sum(1 for r in results.values() if r.status == "SUCCESS")
        return 0 if successful > 0 else 1

    if parsed_args.schedule:
        minutes = parsed_args.schedule
        logger.info("Running in scheduled daemon mode every %d minutes (Ctrl+C to stop)...", minutes)
        try:
            while True:
                execute_run()
                logger.info("Sleeping for %d minutes until next run...", minutes)
                time.sleep(minutes * 60)
        except KeyboardInterrupt:
            logger.info("Scheduled execution stopped by user interrupt.")
            return 0

    return execute_run()


if __name__ == "__main__":
    sys.exit(run_cli())
