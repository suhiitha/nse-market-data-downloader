"""Integration unit tests for MarketDataDownloader service with mocks."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.clients.nse_client import NSEClient, NSEHTTPError
from app.config import AppConfig
from app.services.downloader import MarketDataDownloader
from app.storage.csv_storage import CSVStorage


@pytest.fixture
def mock_app_config(tmp_path: Path):
    """Creates a custom AppConfig targeting tmp_path for test isolation."""
    config = AppConfig()
    config.output_dir = tmp_path
    return config


def test_successful_download_single(mock_app_config: Path, tmp_path: Path):
    """Verify downloading a single dataset saves CSV and returns SUCCESS."""
    mock_client = MagicMock(spec=NSEClient)
    # Mock response for volume-gainers-spurts
    mock_client.get_json.return_value = {
        "timestamp": "04-Oct-2026 15:30:00",
        "data": [
            {
                "symbol": "ABC",
                "companyName": "ABC Ltd",
                "volume": 100000,
                "week1AvgVolume": 20000,
                "week1volChange": 400.0,
                "week2AvgVolume": 15000,
                "week2volChange": 566.0,
                "ltp": 250.0,
                "pChange": 4.5,
                "turnover": 500.0,
            }
        ],
    }

    storage = CSVStorage(base_output_dir=tmp_path)
    downloader = MarketDataDownloader(
        app_config=mock_app_config,
        client=mock_client,
        storage=storage,
    )

    result = downloader.download_dataset("volume-gainers-spurts")

    assert result.status == "SUCCESS"
    assert result.record_count == 1
    assert result.file_path is not None
    assert result.file_path.exists()
    assert result.file_path.name == "volume_gainers_spurts.csv"


def test_one_dataset_fails_others_continue(mock_app_config: Path, tmp_path: Path):
    """Verify that if one dataset fails (e.g. HTTP 503), the other three succeed."""
    mock_client = MagicMock(spec=NSEClient)

    def side_effect(endpoint, **kwargs):
        # Fail upper band hitters with HTTP 503
        if "price-band-hitter" in endpoint:
            raise NSEHTTPError("HTTP 503 from NSE", status_code=503)

        if "live-analysis-variations" in endpoint:
            return {
                "timestamp": "04-Oct-2026",
                "allSec": {
                    "data": [
                        {
                            "symbol": "STOCK1",
                            "series": "EQ",
                            "open_price": 100.0,
                            "high_price": 105.0,
                            "low_price": 98.0,
                            "ltp": 104.0,
                            "prev_price": 100.0,
                            "net_price": 4.0,
                            "trade_quantity": 50000,
                            "turnover": 520.0,
                            "perChange": 4.0,
                        }
                    ]
                },
            }

        if "volume-gainers" in endpoint:
            return {
                "timestamp": "04-Oct-2026",
                "data": [
                    {
                        "symbol": "VOL1",
                        "companyName": "Volume 1 Ltd",
                        "volume": 20000,
                        "week1AvgVolume": 5000,
                        "week1volChange": 300.0,
                        "week2AvgVolume": 4000,
                        "week2volChange": 400.0,
                        "ltp": 50.0,
                        "pChange": 2.0,
                        "turnover": 100.0,
                    }
                ],
            }

        if "52weekhighstock" in endpoint:
            return {
                "timestamp": "04-Oct-2026",
                "data": [
                    {
                        "symbol": "HIGH1",
                        "comapnyName": "High 1 Ltd",
                        "series": "EQ",
                        "ltp": 800.0,
                        "new52WHL": 810.0,
                        "prev52WHL": 790.0,
                        "prevClose": "780.0",
                        "change": 20.0,
                        "pChange": 2.56,
                        "prevHLDate": "01-Oct-2026",
                    }
                ],
            }

        return {}

    mock_client.get_json.side_effect = side_effect

    storage = CSVStorage(base_output_dir=tmp_path)
    downloader = MarketDataDownloader(
        app_config=mock_app_config,
        client=mock_client,
        storage=storage,
    )

    results = downloader.download_all()

    assert len(results) == 4
    # Upper band hitters failed
    assert results["upper-band-hitters"].status == "FAILED"
    assert "HTTP 503" in results["upper-band-hitters"].error_message

    # Other 3 succeeded
    assert results["top-gainers-losers"].status == "SUCCESS"
    assert results["volume-gainers-spurts"].status == "SUCCESS"
    assert results["52-week-high"].status == "SUCCESS"

    successful_count = sum(1 for r in results.values() if r.status == "SUCCESS")
    assert successful_count == 3


def test_unknown_dataset_key(mock_app_config: Path, tmp_path: Path):
    """Verify that requesting an unregistered dataset returns FAILED status gracefully."""
    downloader = MarketDataDownloader(
        app_config=mock_app_config,
        storage=CSVStorage(base_output_dir=tmp_path),
    )
    res = downloader.download_dataset("non-existent-market-data")
    assert res.status == "FAILED"
    assert "Unknown dataset key" in res.error_message


def test_trading_date_extraction():
    """Verify date parser converts NSE timestamp formats to YYYY-MM-DD."""
    downloader = MarketDataDownloader()

    # DD-Mon-YYYY HH:MM:SS format
    payload1 = {"timestamp": "01-Oct-2026 16:00:00"}
    assert downloader.extract_trading_date(payload1) == "2026-10-01"

    # DD-Mon-YYYY format
    payload2 = {"asOnDate": "15-Aug-2026"}
    assert downloader.extract_trading_date(payload2) == "2026-08-15"

    # ISO format
    payload3 = {"timestamp": "2026-05-20"}
    assert downloader.extract_trading_date(payload3) == "2026-05-20"

    # None/invalid
    assert downloader.extract_trading_date({}) is None
    assert downloader.extract_trading_date("not-a-dict") is None
