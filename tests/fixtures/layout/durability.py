"""Disposable worker harness: synthetic OA runtime and in-process lock only.

Uses the product worker and product immutable operation reader. This does not
qualify a real VM/OA transaction or the actual POSIX shared resource lock.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any

from cadence_mcp_bridge import _native_operations


class SimulatedCrash(BaseException):
    pass


class Accounting:
    JOBS = "jobs"

    def __init__(self, root: Path, *, final_check_failure: bool = False) -> None:
        self.root = root
        self.lock = threading.RLock()
        self.final_check_failure = final_check_failure
        root.mkdir()
        (root / self.JOBS).mkdir()

    def ReservationSession(self, root: str) -> Any:  # noqa: N802
        owner = self

        class Session:
            def __enter__(self) -> Session:
                owner.lock.acquire()
                return self

            def __exit__(self, *args: Any) -> None:
                owner.lock.release()

            def check(self) -> None:
                if owner.final_check_failure:
                    raise ValueError("synthetic_final_session_check_failed")

        return Session()

    @staticmethod
    def sync_directory(path: str) -> None:
        # Native filesystem durability belongs to the existing actual accounting
        # module; this harness exercises worker control flow, not kernel fsync.
        pass

    @staticmethod
    def write_new(path: str, document: dict[str, Any]) -> None:
        raw = _native_operations.canonical(document)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())


class Runtime:
    def __init__(
        self,
        root: Path,
        before: dict[str, Any],
        after: dict[str, Any],
        *,
        failure: str | None = None,
    ) -> None:
        self.root = str(root)
        self.before, self.after = before, after
        self.failure = failure
        self.writes = 0
        self.lookups = 0

    def read_check(self, request: dict[str, Any]) -> None:
        self.lookups += 1

    def check(self, session: Any, request: dict[str, Any]) -> None:
        pass

    def inspect_for_write(self, action: str, request: dict[str, Any]) -> tuple[Any, Any, Any]:
        return copy.deepcopy(self.before), {}, {}

    def protected_snapshot(self) -> dict[str, str]:
        return {"synthetic_source": "unchanged"}

    def destination_check(self, action: str, route: dict[str, Any]) -> None:
        pass

    def write(self, *args: Any) -> dict[str, Any]:
        self.writes += 1
        if self.failure == "crash":
            raise SimulatedCrash("synthetic process loss after durable write intent")
        if self.failure == "partial":
            raise ValueError("synthetic partial write")
        after = copy.deepcopy(self.after)
        for pin in after["pins"]:
            pin["association"] = "native_verified"
        return {"snapshot": after, "saved": True, "reopened": True}


def journal(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*.json")}


def read(path: Path) -> Any:
    return json.loads(path.read_bytes())
