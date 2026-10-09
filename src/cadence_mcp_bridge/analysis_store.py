"""Durable local admission identity; retries look up, never blindly resubmit."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.operator_operations import (
    DurableOperation,
    OperationPlan,
    OperationProgress,
    OperationRejected,
    progress_transition,
)

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
                if component.is_symlink() or component.is_junction():
                    raise ConfigurationError("Analysis journal is unavailable")
            if self.path.exists() and (
                not self.path.is_file()
                or self.path.stat().st_size > MAX_BYTES
                or self.path.stat().st_nlink != 1
            ):
                raise ConfigurationError("Analysis journal is unavailable")
            for suffix in ("-journal", "-wal", "-shm"):
                sidecar = self.path.with_name(self.path.name + suffix)
                # SQLite removes its own rollback journal after commit. A single
                # lstat avoids exists/is_file/stat races during another writer.
                try:
                    metadata = sidecar.lstat()
                except FileNotFoundError:
                    continue
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or sidecar.is_junction()
                    or metadata.st_nlink not in (0, 1)
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

    @staticmethod
    def native_sweep_claims(
        connection: sqlite3.Connection,
    ) -> Iterator[tuple[str, OperationPlan | None, str]]:
        # The immutable parent document is the durable claim, including existing
        # pre-index journals. Read it under the same BEGIN IMMEDIATE transaction
        # as every admission; no journal reset or unsafe migration is needed.
        if (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_sweeps_v1'"
            ).fetchone()
            is None
        ):
            return
        from cadence_mcp_bridge.native_sweeps import NativeSweepRecord

        for index, (sweep_id, raw) in enumerate(
            connection.execute("SELECT sweep_id,document FROM native_sweeps_v1")
        ):
            try:
                if index >= MAX_RECORDS or not isinstance(raw, str) or len(raw) > 524288:
                    raise ValueError("capacity")
                record = NativeSweepRecord.model_validate_json(raw)
                if record.sweep_id != sweep_id:
                    raise ValueError("identity")
            except ValueError:
                raise InvalidInputError("Native sweep checkpoint identity is invalid") from None
            yield sweep_id, None, sweep_id
            for operation_id, plan in zip(record.operation_ids, record.plan.points, strict=True):
                yield operation_id, plan, sweep_id

    @classmethod
    def _check_native_sweep_claim(
        cls,
        connection: sqlite3.Connection,
        operation_id: str,
        plan: OperationPlan | None = None,
        sweep_id: str | None = None,
    ) -> None:
        claims = [
            (point, owner)
            for identity, point, owner in cls.native_sweep_claims(connection)
            if identity == operation_id
        ]
        if claims:
            if len(claims) != 1 or plan is None or claims[0] != (plan, sweep_id):
                raise InvalidInputError("Operation ID is reserved by a native sweep")
        elif sweep_id is not None:
            raise InvalidInputError("Native sweep point identity is not reserved")

    @classmethod
    def native_sweep_identity_available(
        cls,
        connection: sqlite3.Connection,
        operation_id: str,
    ) -> bool:
        return connection.execute(
            "SELECT 1 FROM admissions WHERE operation_id=?",
            (operation_id,),
        ).fetchone() is None and not any(
            identity == operation_id for identity, _, _ in cls.native_sweep_claims(connection)
        )

    def admit(self, operation_id: str, design_id: str, analysis_id: str, plan_hash: str) -> bool:
        """Persist before dispatch; exactly one caller gets first-send authority."""
        with self.connection(create=True) as connection:
            self._check_native_sweep_claim(connection, operation_id)
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

    @staticmethod
    def _lifecycle_capacity(connection: sqlite3.Connection) -> None:
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        connection.execute(f"PRAGMA max_page_count={MAX_BYTES // page_size}")

    @staticmethod
    def _operation_tables(connection: sqlite3.Connection, *, create: bool) -> None:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
                "('operator_plans_v1','operator_events_v1')"
            )
        }
        if names:
            if names != {"operator_plans_v1", "operator_events_v1"}:
                raise ConfigurationError("Analysis lifecycle journal is unavailable")
            return
        if not create:
            raise InvalidInputError("Operator operation is not admitted")
        AnalysisStore._lifecycle_capacity(connection)
        # Additive tables only. Existing admissions/application identity/version are retained.
        connection.execute(
            "CREATE TABLE operator_plans_v1 (operation_id TEXT PRIMARY KEY, "
            "plan_json TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE operator_events_v1 (operation_id TEXT NOT NULL, "
            "sequence INTEGER NOT NULL, progress_json TEXT NOT NULL, "
            "previous_sha256 TEXT NOT NULL, event_sha256 TEXT NOT NULL, "
            "PRIMARY KEY(operation_id,sequence))"
        )

    @staticmethod
    def _event_digest(operation_id: str, sequence: int, progress: str, previous: str) -> str:
        data = json.dumps([operation_id, sequence, progress, previous], separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @classmethod
    def _read_operation(cls, connection: sqlite3.Connection, operation_id: str) -> DurableOperation:
        cls._operation_tables(connection, create=False)
        row = connection.execute(
            "SELECT plan_json FROM operator_plans_v1 WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if row is None:
            raise InvalidInputError("Operator operation is not admitted")
        try:
            if len(row[0]) > 32768:
                raise ValueError("plan size")
            plan = OperationPlan.model_validate_json(row[0])
            admission = connection.execute(
                "SELECT design_id,analysis_id,plan_hash FROM admissions WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if admission != (plan.request.design_id, plan.request.analysis_id, plan.plan_sha256):
                raise ValueError("plan identity")
            rows = connection.execute(
                "SELECT sequence,progress_json,previous_sha256,event_sha256 "
                "FROM operator_events_v1 WHERE operation_id=? ORDER BY sequence LIMIT 65",
                (operation_id,),
            ).fetchall()
            if not rows or len(rows) > 64:
                raise ValueError("event capacity")
            previous = "0" * 64
            progress = None
            for index, (sequence, raw, prior, digest) in enumerate(rows, 1):
                if (
                    len(raw) > 1024
                    or sequence != index
                    or prior != previous
                    or digest != cls._event_digest(operation_id, sequence, raw, previous)
                ):
                    raise ValueError("event chain")
                current = OperationProgress.model_validate_json(raw)
                if progress is None:
                    if current != OperationProgress(phase="ADMITTED"):
                        raise ValueError("initial progress")
                else:
                    progress_transition(progress, current)
                progress, previous = current, digest
            assert progress is not None
            return DurableOperation(
                operation_id=operation_id, plan=plan, progress=progress, event_count=len(rows)
            )
        except (ValueError, TypeError):
            raise ConfigurationError("Analysis lifecycle journal is unavailable") from None

    @classmethod
    def _append_progress(
        cls,
        connection: sqlite3.Connection,
        operation_id: str,
        sequence: int,
        progress: OperationProgress,
        previous: str,
    ) -> None:
        cls._lifecycle_capacity(connection)
        raw = progress.model_dump_json()
        connection.execute(
            "INSERT INTO operator_events_v1 VALUES (?,?,?,?,?)",
            (
                operation_id,
                sequence,
                raw,
                previous,
                cls._event_digest(operation_id, sequence, raw, previous),
            ),
        )

    def admit_operation(
        self,
        operation_id: str,
        plan: OperationPlan,
        *,
        dispatch_intent: bool = False,
        sweep_id: str | None = None,
    ) -> bool:
        raw = plan.model_dump_json()
        if len(raw) > 32768:
            raise ConfigurationError("Analysis lifecycle plan exceeds capacity")
        with self.connection(create=True) as connection:
            self._check_native_sweep_claim(connection, operation_id, plan, sweep_id)
            existing = connection.execute(
                "SELECT 1 FROM admissions WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if existing is not None:
                record = self._read_operation(connection, operation_id)
                if record.plan != plan:
                    raise InvalidInputError("Analysis operation identity conflicts")
                return False
            if connection.execute("SELECT COUNT(*) FROM admissions").fetchone()[0] >= MAX_RECORDS:
                raise ConfigurationError("Analysis journal capacity reached")
            self._lifecycle_capacity(connection)
            self._operation_tables(connection, create=True)
            connection.execute(
                "INSERT INTO admissions VALUES (?,?,?,?)",
                (operation_id, plan.request.design_id, plan.request.analysis_id, plan.plan_sha256),
            )
            connection.execute("INSERT INTO operator_plans_v1 VALUES (?,?)", (operation_id, raw))
            admitted = OperationProgress(phase="ADMITTED")
            self._append_progress(connection, operation_id, 1, admitted, "0" * 64)
            if dispatch_intent:
                previous = self._event_digest(operation_id, 1, admitted.model_dump_json(), "0" * 64)
                self._append_progress(
                    connection,
                    operation_id,
                    2,
                    OperationProgress(phase="UNKNOWN_OUTCOME"),
                    previous,
                )
            return True

    def operation(self, operation_id: str) -> DurableOperation:
        with self.connection(create=False) as connection:
            return self._read_operation(connection, operation_id)

    def advance_operation(
        self, operation_id: str, expected: OperationProgress, progress: OperationProgress
    ) -> DurableOperation:
        with self.connection(create=False) as connection:
            record = self._read_operation(connection, operation_id)
            if record.progress == progress:
                return record
            if record.progress != expected:
                raise OperationRejected("operation_progress_conflict")
            progress_transition(record.progress, progress)
            if record.event_count >= 64:
                raise ConfigurationError("Analysis lifecycle event capacity reached")
            previous = connection.execute(
                "SELECT event_sha256 FROM operator_events_v1 WHERE operation_id=? AND sequence=?",
                (operation_id, record.event_count),
            ).fetchone()[0]
            self._append_progress(
                connection, operation_id, record.event_count + 1, progress, previous
            )
            return self._read_operation(connection, operation_id)
