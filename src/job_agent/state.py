from __future__ import annotations

import sqlite3
from pathlib import Path


class State:
    def __init__(self, path: str | Path) -> None:
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS seen_jobs (identity TEXT PRIMARY KEY, seen_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )

    def is_seen(self, identity: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM seen_jobs WHERE identity = ?", (identity,)
        ).fetchone()
        return row is not None

    def mark_seen(self, identities: list[str]) -> None:
        self.connection.executemany(
            "INSERT OR IGNORE INTO seen_jobs(identity) VALUES (?)", ((item,) for item in identities)
        )
        self.connection.commit()

