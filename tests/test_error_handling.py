"""Unit tests for network failures, HTTP errors, timeouts, and retry logic."""

from unittest.mock import MagicMock, patch
import pytest
import requests

from app.clients.nse_client import (
    NSEClient,
    NSEClientError,
    NSEHTTPError,
    NSENetworkError,
    NSEParsingError,
)


@patch("time.sleep", return_value=None)
def test_successful_request_on_first_try(mock_sleep):
    """Verify clean 200 response parsed correctly."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok", "data": [1, 2, 3]}
    mock_session.get.return_value = mock_resp

    client = NSEClient(session=mock_session, max_retries=3)
    client._cookies_initialized = True

    data = client.get_json("/api/test")
    assert data == {"status": "ok", "data": [1, 2, 3]}
    assert mock_session.get.call_count == 1
    assert mock_sleep.call_count == 0


@patch("time.sleep", return_value=None)
def test_http_404_no_retry(mock_sleep):
    """Verify that permanent 404 client error is not retried unnecessarily."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_session.get.return_value = mock_resp

    client = NSEClient(session=mock_session, max_retries=3)
    client._cookies_initialized = True

    with pytest.raises(NSEHTTPError) as exc_info:
        client.get_json("/api/non-existent")

    assert exc_info.value.status_code == 404
    assert mock_session.get.call_count == 1
    assert mock_sleep.call_count == 0


@patch("time.sleep", return_value=None)
def test_timeout_and_retry_success(mock_sleep):
    """Verify that transient timeout triggers retries with exponential backoff and recovers."""
    mock_session = MagicMock()
    timeout_resp = requests.exceptions.Timeout("Connection timed out")
    success_resp = MagicMock()
    success_resp.status_code = 200
    success_resp.json.return_value = {"result": "recovered"}

    # Fails twice with Timeout, succeeds on 3rd attempt
    mock_session.get.side_effect = [timeout_resp, timeout_resp, success_resp]

    client = NSEClient(
        session=mock_session,
        max_retries=3,
        initial_backoff=1.0,
        backoff_multiplier=2.0,
    )
    client._cookies_initialized = True

    result = client.get_json("/api/flaky")
    assert result == {"result": "recovered"}
    assert mock_session.get.call_count == 3
    assert mock_sleep.call_count == 2


@patch("time.sleep", return_value=None)
def test_timeout_exhausted_raises_network_error(mock_sleep):
    """Verify that persistent timeouts raise NSENetworkError after max retries."""
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.exceptions.Timeout("Read timeout")

    client = NSEClient(session=mock_session, max_retries=3)
    client._cookies_initialized = True

    with pytest.raises(NSENetworkError, match="Network failure fetching"):
        client.get_json("/api/timeout-dead")

    assert mock_session.get.call_count == 3
    assert mock_sleep.call_count == 2


@patch("time.sleep", return_value=None)
def test_http_500_internal_error_retry(mock_sleep):
    """Verify that HTTP 500 triggers retry and raises NSEHTTPError when exhausted."""
    mock_session = MagicMock()
    resp_500 = MagicMock()
    resp_500.status_code = 500

    mock_session.get.return_value = resp_500

    client = NSEClient(session=mock_session, max_retries=3)
    client._cookies_initialized = True

    with pytest.raises(NSEHTTPError) as exc_info:
        client.get_json("/api/server-error")

    assert exc_info.value.status_code == 500
    assert mock_session.get.call_count == 3
    assert mock_sleep.call_count == 2


@patch("time.sleep", return_value=None)
def test_http_429_rate_limit_retry(mock_sleep):
    """Verify that HTTP 429 rate limit triggers backoff retries."""
    mock_session = MagicMock()
    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {"rate_limited": False}

    mock_session.get.side_effect = [resp_429, resp_200]

    client = NSEClient(session=mock_session, max_retries=3)
    client._cookies_initialized = True

    data = client.get_json("/api/throttled")
    assert data == {"rate_limited": False}
    assert mock_session.get.call_count == 2
    assert mock_sleep.call_count == 1


@patch("time.sleep", return_value=None)
def test_malformed_json_response_handling(mock_sleep):
    """Verify that invalid/corrupt JSON triggers retries and raises NSEParsingError."""
    mock_session = MagicMock()
    resp_corrupt = MagicMock()
    resp_corrupt.status_code = 200
    resp_corrupt.json.side_effect = ValueError("Expecting value: line 1 column 1")

    mock_session.get.return_value = resp_corrupt

    client = NSEClient(session=mock_session, max_retries=2)
    client._cookies_initialized = True

    with pytest.raises(NSEParsingError, match="Malformed JSON payload"):
        client.get_json("/api/corrupt")

    assert mock_session.get.call_count == 2
