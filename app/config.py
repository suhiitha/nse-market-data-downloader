"""Configuration loader and management for NSE Market Data Downloader."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "datasets.yaml"


class DatasetConfig:
    """Strongly-typed representation of a single dataset's configuration."""

    def __init__(self, key: str, data: Dict[str, Any]):
        self.key: str = key
        self.name: str = data.get("name", key)
        self.source: str = data.get("source", "NSE")
        self.web_url: str = data.get("web_url", "")
        self.endpoint: str = data.get("endpoint", "")
        self.output_filename: str = data.get("output_filename", key.replace("-", "_"))
        self.primary_key: str = data.get("primary_key", "symbol")
        self.description: str = data.get("description", "")
        self.sources: Optional[List[Dict[str, Any]]] = data.get("sources")
        self.expected_fields: List[str] = data.get("expected_fields", [])

    def __repr__(self) -> str:
        return f"<DatasetConfig key={self.key} name='{self.name}'>"


class AppConfig:
    """Application-wide settings combining YAML configs and environment variables."""

    def __init__(self, config_file: Optional[Path] = None):
        self.config_path = config_file or DEFAULT_CONFIG_PATH
        self._raw_yaml: Dict[str, Any] = self._load_yaml()

        # Paths
        self.base_dir: Path = BASE_DIR
        env_output_dir = os.getenv("NSE_OUTPUT_DIR", "./data")
        self.output_dir: Path = (
            Path(env_output_dir) if Path(env_output_dir).is_absolute() else BASE_DIR / env_output_dir
        )
        env_log_dir = os.getenv("NSE_LOG_DIR", "./logs")
        self.log_dir: Path = (
            Path(env_log_dir) if Path(env_log_dir).is_absolute() else BASE_DIR / env_log_dir
        )

        # Logging
        self.log_level: str = os.getenv("NSE_LOG_LEVEL", "INFO").upper()

        # Network settings from YAML with env overrides
        net_cfg = self._raw_yaml.get("network", {})
        self.base_url: str = self._raw_yaml.get("base_url", "https://www.nseindia.com")
        self.timeout_seconds: float = float(
            os.getenv("NSE_REQUEST_TIMEOUT", str(net_cfg.get("timeout_seconds", 15)))
        )
        self.max_retries: int = int(
            os.getenv("NSE_MAX_RETRIES", str(net_cfg.get("max_retries", 3)))
        )
        self.initial_backoff_seconds: float = float(
            os.getenv("NSE_INITIAL_BACKOFF", str(net_cfg.get("initial_backoff_seconds", 1.5)))
        )
        self.backoff_multiplier: float = float(
            os.getenv("NSE_BACKOFF_MULTIPLIER", str(net_cfg.get("backoff_multiplier", 2.0)))
        )
        self.max_backoff_seconds: float = float(
            os.getenv("NSE_MAX_BACKOFF", str(net_cfg.get("max_backoff_seconds", 10.0)))
        )
        self.user_agent: str = net_cfg.get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        # Parse datasets
        self.datasets: Dict[str, DatasetConfig] = {}
        for key, data in self._raw_yaml.get("datasets", {}).items():
            self.datasets[key] = DatasetConfig(key, data)

    def _load_yaml(self) -> Dict[str, Any]:
        """Loads and parses the datasets.yaml file."""
        if not self.config_path.exists():
            return {"datasets": {}, "network": {}}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            raise RuntimeError(f"Failed to parse configuration file at {self.config_path}: {e}") from e

    def get_dataset(self, key: str) -> Optional[DatasetConfig]:
        """Returns the configuration for a specific dataset key, or None if not found."""
        return self.datasets.get(key)

    def list_dataset_keys(self) -> List[str]:
        """Returns a list of all configured dataset keys."""
        return list(self.datasets.keys())


# Singleton instance for standard use
config = AppConfig()
