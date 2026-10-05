"""Durable local admission identity; retries look up, never blindly resubmit."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError

APPLICATION_ID = 1128353101
MAX_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 10_000


def default_analysis_journal() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
    else:
        root = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
    return root / "cadence-mcp-bridge" / "analyses-v1.sqlite3"


class AnalysisStore:
    def __init__(self, path: Path) -> None:
        self.path = path.absolute()

    @contextmanager
    def connection(self, *, create: bool) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            for component in (self.path, *self.path.parents):
                if component.is_symlink():
                    raise ConfigurationError("Analysis journal is unavailable")
            if self.path.exists() and (
                not self.path.is_file() or self.path.stat().st_size > MAX_BYTES
            ):
                raise ConfigurationError("Analysis journal is unavailable")
            new = False
            if not self.path.exists():
                if not create:
                    raise InvalidInputError("Analysis operation is not admitted")
                self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                try:
                    descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    os.close(descriptor)
                    new = True
                except FileExistsError:
                    pass
            sidecar = self.path.with_name(self.path.name + "-journal")
            if sidecar.is_symlink():
                raise ConfigurationError("Analysis journal is unavailable")
            connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5)
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            if new:
                connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                connection.execute("PRAGMA user_version=1")
                connection.execute(
                    "CREATE TABLE admissions (operation_id TEXT PRIMARY KEY, "
                    "design_id TEXT NOT NULL, "
                    "analysis_id TEXT NOT NULL, plan_hash TEXT NOT NULL)"
                )
            if (
                connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                or connection.execute("PRAGMA user_version").fetchone()[0] != 1
                or connection.execute("PRAGMA quick_check").fetchone()[0] != "ok"
            ):
                raise ConfigurationError("Analysis journal is unavailable")
            yield connection
            connection.commit()
        except (OSError, sqlite3.Error):
            raise ConfigurationError("Analysis journal is unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    def admit(self, operation_id: str, design_id: str, analysis_id: str, plan_hash: str) -> bool:
        """Persist before dispatch; exactly one caller gets first-send authority."""
        with self.connection(create=True) as connection:
            row = connection.execute(
                "SELECT design_id, analysis_id, plan_hash FROM admissions WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            identity = (design_id, analysis_id, plan_hash)
            if row is not None:
                if row != identity:
                    raise InvalidInputError("Analysis operation identity conflicts")
                return False
            if connection.execute("SELECT COUNT(*) FROM admissions").fetchone()[0] >= MAX_RECORDS:
                raise ConfigurationError("Analysis journal capacity reached")
            connection.execute(
                "INSERT INTO admissions VALUES (?, ?, ?, ?)", (operation_id, *identity)
            )
            return True

    def require(self, operation_id: str, design_id: str, analysis_id: str, plan_hash: str) -> None:
        with self.connection(create=False) as connection:
            row = connection.execute(
                "SELECT design_id, analysis_id, plan_hash FROM admissions WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if row != (design_id, analysis_id, plan_hash):
                raise InvalidInputError("Analysis operation is not admitted with this identity")
