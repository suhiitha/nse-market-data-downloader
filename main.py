#!/usr/bin/env python3
"""Root executable wrapper for NSE Market Data Downloader."""

import sys
from app.main import run_cli

if __name__ == "__main__":
    sys.exit(run_cli())
