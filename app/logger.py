"""Logging infrastructure for NSE Market Data Downloader."""

import logging
import sys
from pathlib import Path
from typing import Optional

_LOGGER_INITIALIZED = False


def setup_logger(
    log_dir: Optional[Path] = None,
    log_level: str = "INFO",
    log_filename: str = "nse_downloader.log",
    console_output: bool = True,
) -> logging.Logger:
    """Configures and returns the application logger with console and file handlers.

    Args:
        log_dir: Directory where log files are stored. Defaults to ./logs.
        log_level: Logging verbosity level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_filename: Target name of the log file.
        console_output: Whether to attach stdout console handler.

    Returns:
        Configured logging.Logger instance.
    """
    global _LOGGER_INITIALIZED

    logger = logging.getLogger("nse_downloader")
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    # Avoid duplicate handlers if setup_logger is invoked multiple times
    if _LOGGER_INITIALIZED:
        logger.setLevel(level)
        return logger

    # Log format: YYYY-MM-DD HH:MM:SS [LEVEL] [module] Message
    log_format = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s:%(funcName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler (clean stdout)
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_format = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_format)
        logger.addHandler(console_handler)

    # File Handler
    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file_path = log_dir / log_filename
            file_handler = logging.FileHandler(str(log_file_path), encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(log_format)
            logger.addHandler(file_handler)
        except Exception as e:
            # Fall back gracefully if file cannot be created
            logger.warning("Could not initialize file log handler at %s: %s", log_dir, e)

    _LOGGER_INITIALIZED = True
    return logger


def get_logger() -> logging.Logger:
    """Returns the application logger instance."""
    return logging.getLogger("nse_downloader")
