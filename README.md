# NSE Market Data Downloader

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: PEP 8](https://img.shields.io/badge/code%20style-PEP%208-brightgreen.svg)](https://www.python.org/dev/peps/pep-0008/)
[![Tests: Pytest](https://img.shields.io/badge/tests-24%20passed-success.svg)](https://docs.pytest.org/)

A reliable, production-minded Python command-line data acquisition pipeline that retrieves real-time and end-of-day market data from the **National Stock Exchange of India (NSE)** and persists it into date-partitioned CSV files.

Built as an engineering assignment following clean architecture, defensive network programming, schema validation, fault isolation, and deterministic storage.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Supported Datasets](#supported-datasets)
- [Project Architecture](#project-architecture)
- [Installation & Setup](#installation--setup)
- [Command Line Interface (CLI)](#command-line-interface-cli)
- [Output File Storage & Organization](#output-file-storage--organization)
- [NSE Data Acquisition & Network Strategy](#nse-data-acquisition--network-strategy)
- [Data Validation & Deduplication](#data-validation--deduplication)
- [Error Handling & Exponential Backoff](#error-handling--exponential-backoff)
- [Logging](#logging)
- [Testing Suite](#testing-suite)
- [Configuration](#configuration)
- [Docker Support](#docker-support)
- [Assumptions & Limitations](#assumptions--limitations)

---

## Overview

The National Stock Exchange of India (NSE) is India's leading stock exchange. Accessing its public feeds programmatically requires handling dynamic session cookies, anti-bot protections, and network fluctuations. 

This application provides a robust, decoupled, and maintainable pipeline that:
1. Automatically negotiates session tracking cookies with the NSE portal.
2. Queries the official structured JSON API endpoints behind the market data web pages (without fragile HTML web scraping).
3. Validates incoming schemas, detects duplicates, and filters malformed payloads.
4. Stores clean records into structured `data/<YYYY-MM-DD>/<dataset>.csv` hierarchies.
5. Provides rich CLI logging and an isolated fault-tolerant runner where one failing endpoint does not halt remaining downloads.

---

## Key Features

- **Real NSE Data**: Interacts directly with genuine NSE JSON API endpoints; zero mock or fake data in production code.
- **4 Market Feeds**: Top Gainers/Losers, Upper Band Hitters, Volume Gainers/Spurts, and 52-Week High.
- **Defensive Session Management**: Automatically establishes and refreshes cookies (`AKA_A2`, etc.) via simulated browser navigation.
- **Fault-Isolated Execution**: If one endpoint fails or returns a server error (e.g. 503), the other three continue and finish successfully.
- **Exponential Backoff Retries**: Configurable automatic retry mechanism for network drops, timeouts, and HTTP 429/5xx responses.
- **Deterministic Storage & Deduplication**: Avoids duplicate files (e.g. `file1.csv`, `final.csv`) and removes duplicate row entries using primary/composite keys.
- **Full Pytest Suite**: 24 unit and integration tests covering network timeouts, HTTP errors, schema violations, duplicate rows, and file writes.
- **Decoupled Configuration**: URLs, endpoints, and validation schemas are cleanly defined in `config/datasets.yaml` rather than hardcoded in code.
- **Production CLI**: Rich progress logs and a concise summary table matching the assignment specification.

---

## Supported Datasets

| Dataset Key | Dataset Name | Web Page URL | Official Backend Endpoint |
|---|---|---|---|
| `top-gainers-losers` | Top Gainers / Losers | [Top Gainers Losers](https://www.nseindia.com/market-data/top-gainers-losers) | `/api/live-analysis-variations?index=gainers` & `?index=loosers` |
| `upper-band-hitters` | Upper Band Hitters | [Upper Band Hitters](https://www.nseindia.com/market-data/upper-band-hitters) | `/api/live-analysis-price-band-hitter` |
| `volume-gainers-spurts` | Volume Gainers Spurts | [Volume Gainers Spurts](https://www.nseindia.com/market-data/volume-gainers-spurts) | `/api/live-analysis-volume-gainers` |
| `52-week-high` | 52 Week High Equity Market | [52 Week High](https://www.nseindia.com/market-data/52-week-high-equity-market) | `/api/live-analysis-data-52weekhighstock` |

---

## Project Architecture

```
nse-market-data-downloader/
│
├── app/
│   ├── __init__.py          # Application package declaration
│   ├── main.py              # CLI entry point, argument parsing, summary renderer
│   ├── config.py            # Typed configuration loader (.env and datasets.yaml)
│   ├── logger.py            # Console and dual-target rotating file logging
│   │
│   ├── clients/
│   │   ├── __init__.py
│   │   └── nse_client.py    # Session lifecycle, cookie bootstrap, retries, headers
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   └── downloader.py    # Pipeline orchestrator, response parsing, error isolation
│   │
│   ├── validators/
│   │   ├── __init__.py
│   │   └── data_validator.py# Schema verification, column presence, deduplication
│   │
│   └── storage/
│       ├── __init__.py
│       └── csv_storage.py   # Deterministic date-partitioned CSV file writer
│
├── config/
│   └── datasets.yaml        # Externalized dataset endpoints, keys, and schemas
│
├── data/                    # Generated market data CSVs organized by date
│   └── .gitkeep
│
├── logs/                    # Application runtime logs
│   └── .gitkeep
│
├── tests/                   # Complete Pytest unit test suite
│   ├── __init__.py
│   ├── test_downloader.py   # Integration & fault isolation tests
│   ├── test_error_handling.py# Timeout, retry, 429, 500, and malformed payload tests
│   ├── test_validator.py    # Schema integrity, empty sets, duplicate row tests
│   └── test_storage.py      # Storage overwrite, dates, and atomic writes
│
├── sample_data/             # Representative mock sample CSVs for documentation
│   ├── README.md
│   ├── sample_top_gainers_losers.csv
│   ├── sample_upper_band_hitters.csv
│   ├── sample_volume_gainers_spurts.csv
│   └── sample_52_week_high.csv
│
├── Dockerfile               # Production container image definition
├── requirements.txt         # Minimal, pinned Python dependencies
├── .env.example             # Template for local environment variables
├── .gitignore               # Standard Python & OS ignore rules
├── main.py                  # Root CLI execution shortcut
└── README.md                # Comprehensive project documentation
```

### Module Responsibilities

1. **`app.config`**: Reads `config/datasets.yaml` and `.env`. Provides strongly-typed `DatasetConfig` and `AppConfig` objects so no URLs or magic numbers exist in business logic.
2. **`app.clients.nse_client`**: Manages a persistent `requests.Session` with modern browser user-agents. Handles session cookie bootstrapping, status codes, and exponential backoff retry loops.
3. **`app.validators.data_validator`**: Validates that responses are non-empty lists of dictionaries, verifies mandatory schema fields, eliminates malformed entries, and enforces primary key uniqueness.
4. **`app.storage.csv_storage`**: Resolves target trading dates, writes clean CSV files atomically via temporary files, and implements deterministic overwrite or skip behavior.
5. **`app.services.downloader`**: Orchestrates the client, validator, and storage for individual or all datasets. Guarantees that failure in one dataset does not block subsequent datasets.
6. **`app.logger`**: Centralized logging system emitting clean messages to stdout and structured traces to `logs/nse_downloader.log`.

---

## Installation & Setup

### Prerequisites

- Python 3.10+ (tested on Python 3.10 and 3.11)
- `pip` package manager

### 1. Clone & Navigate

```bash
git clone <repository-url>
cd nse-market-data-downloader
```

### 2. Create and Activate Virtual Environment

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment (Optional)

Copy `.env.example` to `.env` to configure custom directories or log levels:
```bash
cp .env.example .env
```

---

## Command Line Interface (CLI)

The CLI supports downloading all feeds, downloading a specific feed, custom output folders, custom date overrides, and scheduled polling.

### Download All Four Datasets

```bash
python main.py
```

**Sample Output:**
```text
2026-10-04 15:27:44 [INFO] Starting NSE Market Data Downloader execution
2026-10-04 15:27:44 [INFO] Executing download pipeline for 4 datasets: ['top-gainers-losers', 'upper-band-hitters', 'volume-gainers-spurts', '52-week-high']
2026-10-04 15:27:44 [INFO] Starting download for 'Top Gainers / Losers' (top-gainers-losers)
2026-10-04 15:27:44 [INFO] Saved 40 records: data/2026-10-04/top_gainers_losers.csv
2026-10-04 15:27:44 [INFO] Saved 8 records: data/2026-10-04/upper_band_hitters.csv
2026-10-04 15:27:45 [INFO] Saved 25 records: data/2026-10-01/volume_gainers_spurts.csv
2026-10-04 15:27:45 [INFO] Saved 79 records: data/2026-10-01/52_week_high.csv

NSE Market Data Downloader
==========================

[✓] Top Gainers / Losers          40 records  (0.31s)
[✓] Upper Band Hitters             8 records  (0.32s)
[✓] Volume Gainers Spurts         25 records  (0.16s)
[✓] 52 Week High Equity Market    79 records  (0.16s)

Completed:
4/4 datasets downloaded successfully

Output directory:
data/2026-10-01/
```

### Download Individual Datasets

```bash
# 1. Top Gainers & Losers
python main.py --dataset top-gainers-losers

# 2. Upper Band Hitters
python main.py --dataset upper-band-hitters

# 3. Volume Gainers / Spurts
python main.py --dataset volume-gainers-spurts

# 4. 52-Week High
python main.py --dataset 52-week-high
```

### Additional CLI Options

```bash
# Custom output directory
python main.py --output-dir ./market_exports

# Explicit trading date override
python main.py --date 2026-10-04

# Skip existing files instead of overwriting
python main.py --skip-existing

# Set verbose debug logging
python main.py --log-level DEBUG

# List all available datasets and schemas
python main.py --list-datasets

# Scheduled continuous execution every N minutes
python main.py --schedule 15

# View CLI Help
python main.py --help
```

---

## Output File Storage & Organization

Files are saved as standard UTF-8 encoded CSV files partitioned by trading date:

```
data/
└── 2026-10-04/
    ├── top_gainers_losers.csv
    ├── upper_band_hitters.csv
    ├── volume_gainers_spurts.csv
    └── 52_week_high.csv
```

### Date Resolution
- Where available, the timestamp provided in the exchange's payload (e.g., `01-Oct-2026 16:00:00`) is parsed and used as the folder date.
- If no timestamp is present or during market closures, the system safely falls back to the current date (`YYYY-MM-DD`).

### Deterministic Filenames & Duplicate Prevention
- Filenames are strictly derived from the configured `output_filename` key.
- Running `python main.py` multiple times on the same trading day safely detects the existing file and overwrites it atomically via a hidden temporary file (`.tmp_<filename>.csv`).
- **No duplicate or messy filenames** such as `file1.csv`, `final_new.csv`, or `top_gainers(1).csv` are ever produced.

---

## NSE Data Acquisition & Network Strategy

NSE protects its infrastructure with Akamai CDN bot detection. Making unauthenticated raw GET requests directly to API URLs typically yields HTTP 403 Forbidden.

### Our Strategy:
1. **Cookie Bootstrapping**: `NSEClient` first makes an initial GET request to the NSE portal homepage (`https://www.nseindia.com/`) with standard browser headers to establish valid Akamai session cookies (`AKA_A2`, `nsit`).
2. **Standard Decompression**: We specify `Accept-Encoding: gzip, deflate` (avoiding unhandled Brotli streams) allowing `requests` to decompress payloads natively without additional external C-extensions.
3. **Structured API Querying**: We query the real backend JSON REST endpoints rather than scraping rendered HTML. This avoids brittleness when UI layouts change.
4. **Session Re-hydration**: If NSE invalidates the session mid-pipeline returning 401 or 403, `NSEClient` automatically re-establishes cookies and re-attempts the request.

---

## Data Validation & Deduplication

Before any dataset is written to disk, it passes through `DataValidator`:

1. **Non-Empty Checks**: Verifies that the payload is a valid list with length > 0.
2. **Schema Verification**: Confirms that expected mandatory fields (e.g. `symbol`, `ltp`, `turnover`) exist on the records.
3. **Malformed Record Dropping**: Individual records lacking mandatory primary keys or malformed dictionary types are dropped and logged without discarding the entire dataset.
4. **In-Memory Row Deduplication**:
   - For single-dimension datasets (e.g. `52-week-high`), uniqueness is enforced on `symbol`.
   - For multi-feed datasets (e.g. `top-gainers-losers`), uniqueness is enforced on a composite key: `(symbol, category)`.
   - Deduplication metrics are logged and reported in validation results.

---

## Error Handling & Exponential Backoff

The pipeline is designed with defensive programming:

1. **Fault Isolation**: Each dataset download is encapsulated in a dedicated try-except block. A failure in dataset #2 (e.g., HTTP 503) is logged, and the pipeline immediately proceeds to datasets #3 and #4.
2. **Exponential Backoff**:
   $$\text{delay} = \min(\text{max\_backoff}, \text{initial\_backoff} \times (\text{multiplier}^{\text{attempt}-1}))$$
   Transient failures (network timeouts, DNS errors, HTTP 429, 500, 502, 503, 504) automatically retry with backoff.
3. **Permanent Failure Fast-Path**: HTTP 404 client errors fail immediately without wasting time on futile retries.

---

## Logging

Logging is configured across both console and persistent disk logs:

- **Console Handler**: Clean, human-readable status lines.
- **File Handler (`logs/nse_downloader.log`)**: Detailed timestamps, log levels, module names, and error traces.

**Example Log Entries:**
```text
2026-10-04 15:27:44 [INFO] Starting NSE Market Data Downloader execution
2026-10-04 15:27:44 [INFO] Fetching GAINER segment for Top Gainers / Losers...
2026-10-04 15:27:44 [INFO] Validation successful for Top Gainers / Losers: 40 records, 0 duplicates removed
2026-10-04 15:27:44 [INFO] Saved 40 records: data/2026-10-04/top_gainers_losers.csv
2026-10-04 15:27:45 [INFO] Validation successful for 52 Week High Equity Market: 79 records, 14 duplicates removed
2026-10-04 15:27:45 [INFO] Completed download pipeline: 4/4 datasets downloaded successfully
```

---

## Testing Suite

The project includes an extensive test suite built with `pytest` and `unittest.mock`. Unit tests do not depend on external network connectivity or live exchange availability.

### Run Tests

```bash
pytest -v
```

### Coverage Overview (24 Tests)

- **`test_downloader.py`**:
  - `test_successful_download_single`: Verifies end-to-end single dataset download.
  - `test_one_dataset_fails_others_continue`: Simulates 503 error on one feed while verifying the other three succeed.
  - `test_unknown_dataset_key`: Verifies error handling for unregistered dataset keys.
  - `test_trading_date_extraction`: Tests multiple timestamp format parsers (DD-Mon-YYYY, ISO, etc.).
- **`test_error_handling.py`**:
  - `test_successful_request_on_first_try`: Validates clean 200 responses.
  - `test_http_404_no_retry`: Confirms 404 does not waste time in retries.
  - `test_timeout_and_retry_success`: Tests recovery after intermittent timeouts.
  - `test_timeout_exhausted_raises_network_error`: Tests max retries limit.
  - `test_http_500_internal_error_retry`: Tests 500 server error retries.
  - `test_http_429_rate_limit_retry`: Tests rate-limiting backoff.
  - `test_malformed_json_response_handling`: Tests graceful handling of corrupt JSON payloads.
- **`test_validator.py`**:
  - `test_valid_data_passes`: Validates standard conformant data.
  - `test_empty_response_fails`: Rejects empty lists.
  - `test_none_response_fails`: Rejects None payloads.
  - `test_invalid_data_structure_fails`: Rejects unexpected non-list objects.
  - `test_missing_expected_columns_fails`: Rejects schemas missing required fields.
  - `test_duplicate_rows_detected_and_purged`: Tests primary key deduplication.
  - `test_composite_key_deduplication`: Tests multi-attribute uniqueness.
  - `test_malformed_records_filtered`: Drops invalid elements while keeping valid records.
- **`test_storage.py`**:
  - `test_successful_csv_creation`: Tests pandas writing and verification.
  - `test_date_organization_subfolder`: Tests dated directory creation.
  - `test_duplicate_file_handling_overwrite`: Verifies clean overwrites without duplicate filenames.
  - `test_duplicate_file_handling_skip`: Verifies skip flag preserves existing files.
  - `test_storage_error_on_empty_records`: Prevents saving empty data.

---

## Configuration

### `config/datasets.yaml`

The application logic contains zero hardcoded URLs. All configurations reside in `config/datasets.yaml`:

```yaml
base_url: "https://www.nseindia.com"

network:
  timeout_seconds: 15
  max_retries: 3
  initial_backoff_seconds: 1.5
  backoff_multiplier: 2.0
  max_backoff_seconds: 10.0

datasets:
  top-gainers-losers:
    name: "Top Gainers / Losers"
    endpoint: "/api/live-analysis-variations"
    output_filename: "top_gainers_losers"
    primary_key: "symbol"
    expected_fields: [...]
```

---

## Docker Support

Build and run using the included lightweight Dockerfile:

```bash
# Build the Docker image
docker build -t nse-downloader .

# Run all downloads (mount local directory to persist data)
docker run --rm -v $(pwd)/data:/app/data -v $(pwd)/logs:/app/logs nse-downloader

# Run single dataset download
docker run --rm -v $(pwd)/data:/app/data nse-downloader --dataset volume-gainers-spurts
```

---

## Assumptions & Limitations

1. **Market Hours & Trading Days**: The NSE operates Monday through Friday between 09:15 AM and 03:30 PM IST (excluding exchange holidays). Outside market hours or on weekends, NSE returns snapshot data representing the most recent completed trading session.
2. **Network Environment**: Direct access from certain cloud provider IP ranges may occasionally encounter strict Akamai perimeter challenges. The built-in user-agent emulation and session re-hydration mitigates this under standard usage.
3. **Endpoint Schema Evolution**: If the exchange alters its internal endpoint structure, changes only need to be updated in `config/datasets.yaml` without modifying the core pipeline code.
