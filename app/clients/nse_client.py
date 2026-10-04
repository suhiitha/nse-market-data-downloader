"""High-reliability HTTP Client for National Stock Exchange (NSE) API interactions."""

import time
from typing import Any, Dict, Optional, Union
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.logger import get_logger

logger = get_logger()


class NSEClientError(Exception):
    """Base exception for NSE client failures."""
    pass


class NSENetworkError(NSEClientError):
    """Raised for connection drops, DNS lookup failures, or network timeouts."""
    pass


class NSEHTTPError(NSEClientError):
    """Raised when NSE returns an unsuccessful HTTP status code."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class NSEParsingError(NSEClientError):
    """Raised when the response payload cannot be parsed as valid JSON."""
    pass


class NSEClient:
    """Robust HTTP client managing cookies, sessions, headers, and retries for NSE."""

    def __init__(
        self,
        base_url: str = "https://www.nseindia.com",
        timeout: float = 15.0,
        max_retries: int = 3,
        initial_backoff: float = 1.5,
        backoff_multiplier: float = 2.0,
        max_backoff: float = 10.0,
        user_agent: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.backoff_multiplier = backoff_multiplier
        self.max_backoff = max_backoff
        self.user_agent = (
            user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        self._session = session or requests.Session()
        self._cookies_initialized = False
        self._init_session_defaults()

    def _init_session_defaults(self) -> None:
        """Initializes default headers and connection pool settings on the session."""
        self._session.headers.update({
            "User-Agent": self.user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        })

    def initialize_session(self, referer_path: str = "/") -> bool:
        """Navigates to the NSE root homepage to establish required session cookies.

        NSE infrastructure requires visiting the homepage before issuing API requests
        to receive AKAMAI session tracking cookies (e.g. AKA_A2).
        """
        init_url = f"{self.base_url}{referer_path}"
        logger.debug("Initializing NSE session cookies from %s", init_url)

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
        }

        try:
            resp = self._session.get(init_url, headers=headers, timeout=self.timeout)
            logger.debug(
                "Session init response: HTTP %d, cookies acquired: %s",
                resp.status_code,
                list(self._session.cookies.keys()),
            )
            self._cookies_initialized = True
            return True
        except Exception as exc:
            logger.warning("Session initialization warning: %s", exc)
            return False

    def get_json(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        referer: Optional[str] = None,
    ) -> Union[Dict[str, Any], list]:
        """Performs a GET request to an NSE endpoint with retries and exponential backoff.

        Args:
            endpoint: API endpoint path (e.g. '/api/live-analysis-variations') or full URL.
            params: Query parameters.
            referer: Optional specific Referer header to mimic user navigation.

        Returns:
            Parsed JSON object (dict or list).

        Raises:
            NSENetworkError: If network connectivity or timeout occurs after retries.
            NSEHTTPError: If HTTP error occurs and cannot be recovered.
            NSEParsingError: If response body is not valid JSON.
        """
        if not self._cookies_initialized:
            self.initialize_session()

        target_url = endpoint if endpoint.startswith("http") else f"{self.base_url}{endpoint}"
        referer_header = referer or f"{self.base_url}/market-data/top-gainers-losers"

        request_headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": referer_header,
        }

        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            logger.debug(
                "Request started [attempt %d/%d]: GET %s params=%s",
                attempt,
                self.max_retries,
                target_url,
                params,
            )
            try:
                response = self._session.get(
                    target_url,
                    params=params,
                    headers=request_headers,
                    timeout=self.timeout,
                )

                # If session invalidated (401 or 403), re-initialize cookies and retry
                if response.status_code in (401, 403) and attempt < self.max_retries:
                    logger.warning(
                        "NSE returned HTTP %d on attempt %d. Re-establishing session cookies...",
                        response.status_code,
                        attempt,
                    )
                    self.initialize_session()
                    self._backoff_sleep(attempt)
                    continue

                # Server error or rate limiting (429, 500, 502, 503, 504) -> transient retry
                if response.status_code in (429, 500, 502, 503, 504):
                    logger.warning(
                        "NSE returned HTTP %d on attempt %d for %s",
                        response.status_code,
                        attempt,
                        target_url,
                    )
                    if attempt < self.max_retries:
                        self._backoff_sleep(attempt)
                        continue
                    raise NSEHTTPError(
                        f"HTTP {response.status_code} from NSE for {target_url}",
                        status_code=response.status_code,
                    )

                # Client error (4xx) not recoverable
                if 400 <= response.status_code < 500:
                    raise NSEHTTPError(
                        f"Client error HTTP {response.status_code} for {target_url}",
                        status_code=response.status_code,
                    )

                # Non-2xx general check
                if response.status_code >= 300:
                    raise NSEHTTPError(
                        f"Unexpected HTTP {response.status_code} for {target_url}",
                        status_code=response.status_code,
                    )

                # Parse JSON
                try:
                    data = response.json()
                    return data
                except ValueError as err:
                    logger.error("Failed to parse JSON response from %s: %s", target_url, err)
                    if attempt < self.max_retries:
                        self._backoff_sleep(attempt)
                        continue
                    raise NSEParsingError(f"Malformed JSON payload from {target_url}") from err

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_exception = exc
                logger.warning(
                    "Network error on attempt %d/%d for %s: %s",
                    attempt,
                    self.max_retries,
                    target_url,
                    exc,
                )
                if attempt < self.max_retries:
                    self._backoff_sleep(attempt)
                    continue
                raise NSENetworkError(
                    f"Network failure fetching {target_url} after {self.max_retries} attempts: {exc}"
                ) from exc
            except NSEClientError:
                raise
            except Exception as exc:
                last_exception = exc
                logger.error("Unexpected error fetching %s: %s", target_url, exc)
                if attempt < self.max_retries:
                    self._backoff_sleep(attempt)
                    continue
                raise NSEClientError(f"Unexpected error fetching {target_url}: {exc}") from exc

        raise NSEClientError(f"Failed to fetch {target_url} after {self.max_retries} retries: {last_exception}")

    def _backoff_sleep(self, attempt: int) -> None:
        """Computes exponential backoff sleep interval and sleeps."""
        delay = min(
            self.max_backoff,
            self.initial_backoff * (self.backoff_multiplier ** (attempt - 1)),
        )
        logger.info("Retrying with exponential backoff in %.2f seconds (attempt %d)...", delay, attempt)
        time.sleep(delay)

    def close(self) -> None:
        """Closes the underlying requests session and releases sockets."""
        if self._session:
            self._session.close()

    def __enter__(self) -> "NSEClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
