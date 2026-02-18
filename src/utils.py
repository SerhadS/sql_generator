import sqlite3
import os
from typing import List
from pathlib import Path


def create_database_connection(db_path: Path) -> sqlite3.Connection:
    """
    Create and configure a SQLite database connection.

    Args:
        db_path: Path to the database file

    Returns:
        Configured database connection with foreign keys enabled
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _get_env_int(key: str, default: int) -> int:
    """Get integer value from environment variable."""
    value = os.getenv(key)
    return int(value) if value else default


def _get_env_float(key: str, default: float) -> float:
    """Get float value from environment variable."""
    value = os.getenv(key)
    return float(value) if value else default


def _get_env_list(key: str, default: List[str]) -> List[str]:
    """Get list value from environment variable (comma-separated)."""
    value = os.getenv(key)
    if value:
        return [item.strip() for item in value.split(",")]
    return default


def _get_env_path(key: str, default: Path) -> Path:
    """Get Path value from environment variable."""
    value = os.getenv(key)
    return Path(value) if value else default
