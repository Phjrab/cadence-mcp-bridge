"""Comment-preserving, reviewed single-entry Codex changes and conditional removal."""

from __future__ import annotations

import difflib
import hashlib
import importlib
import json
import os
import re
import stat
import tempfile
import tomllib
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import tomlkit

LIMIT = 2 * 1024 * 1024
NAME = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")


class SetupRejected(ValueError):
    """A stable non-secret error code, suitable for the local setup UI."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ordinary(path: Path) -> Path:
    if not path.is_absolute():
        raise SetupRejected("absolute_path_required")
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise SetupRejected("linked_path_rejected")
    if path.exists():
        st = path.stat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise SetupRejected("ordinary_file_required")
    return path


def snapshot(path: Path) -> bytes | None:
    ordinary(path)
    if not path.exists():
        return None
    with path.open("rb") as stream:
        value = stream.read(LIMIT + 1)
    if len(value) > LIMIT:
        raise SetupRejected("configuration_too_large")
    return value


def codex_config() -> Path:
    base = os.environ.get("CODEX_HOME")
    root = Path(base) if base else Path.home() / ".codex"
    if not root.is_absolute():
        raise SetupRejected("codex_home_must_be_absolute")
    return root / "config.toml"


def project_overrides(project: Path | None) -> list[str]:
    if project is None:
        return []
    if not project.is_absolute() or not project.is_dir():
        raise SetupRejected("project_directory_required")
    # Include all ancestors conservatively; actual Codex trust/root selection is
    # client-owned. Never claim this scan resolves managed policy or CLI overrides.
    return [
        str(p / ".codex" / "config.toml")
        for p in (project, *project.parents)
        if (p / ".codex" / "config.toml").is_file()
    ]


def parse(raw: bytes | None) -> Any:
    return tomlkit.parse((raw or b"").decode("utf-8-sig"))


def stanza(name: str, entry: dict[str, Any] | None) -> str:
    if entry is None:
        return ""
    doc = tomlkit.document()
    doc["mcp_servers"] = {name: entry}
    return tomlkit.dumps(doc)


def preview(
    path: Path,
    name: str,
    entry: dict[str, Any],
    *,
    replace: bool = False,
    project: Path | None = None,
) -> dict[str, Any]:
    if NAME.fullmatch(name) is None:
        raise SetupRejected("server_name_invalid")
    raw = snapshot(path)
    doc = parse(raw)
    servers = doc.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise SetupRejected("mcp_table_invalid")
    previous = servers.get(name)
    if previous is not None and previous != entry and not replace:
        raise SetupRejected("name_conflict_choose_update_another_name_or_cancel")
    if "mcp_servers" not in doc:
        doc["mcp_servers"] = tomlkit.table()
    doc["mcp_servers"][name] = entry
    updated = tomlkit.dumps(doc).encode("utf-8")
    if raw is not None and raw.startswith(b"\xef\xbb\xbf"):
        updated = b"\xef\xbb\xbf" + updated
    parsed = tomllib.loads(updated.decode("utf-8-sig"))
    if parsed["mcp_servers"][name] != entry:
        raise SetupRejected("generated_entry_invalid")
    return {
        "path": str(path),
        "name": name,
        "entry": entry,
        "expected": None if raw is None else digest(raw),
        "after": digest(updated),
        "unchanged": previous == entry,
        "diff": "".join(
            difflib.unified_diff(
                stanza(name, previous).splitlines(True),
                stanza(name, entry).splitlines(True),
                fromfile="current entry",
                tofile="proposed entry",
            )
        ),
        "project_overrides": project_overrides(project),
        "client_connection_verified": False,
        "precedence_notice": "Managed policy, CLI overrides and trusted project settings may "
        "override this user entry. Actual app reconnection is separate.",
    }


@contextmanager
def configuration_lock(path: Path) -> Iterator[None]:
    """Process-lifetime OS lock; a crash releases it without deleting its inode."""
    lock = ordinary(path.with_name(path.name + ".cadence-setup.lock"))
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        held, named = os.fstat(fd), lock.lstat()
        if (
            not stat.S_ISREG(held.st_mode)
            or held.st_nlink != 1
            or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise SetupRejected("configuration_lock_invalid")
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SetupRejected("configuration_busy") from None
        yield
    finally:
        # Closing releases the OS lock, including on process termination. Keep the
        # named inode so another writer cannot lock a replacement during handoff.
        os.close(fd)


def _replace_checked(
    path: Path,
    before: bytes | None,
    after: bytes,
    history: Path,
    record: dict[str, Any] | None = None,
) -> Path:
    """Last-read conflict detection + atomic replace, not a cross-app CAS primitive."""
    ordinary(path)
    if not path.parent.is_dir() or not history.is_dir():
        raise SetupRejected("private_parent_required")
    with configuration_lock(path):
        return _replace_locked(path, before, after, history, record)


def _replace_locked(
    path: Path,
    before: bytes | None,
    after: bytes,
    history: Path,
    record: dict[str, Any] | None,
) -> Path:
    temp: Path | None = None
    try:
        if snapshot(path) != before:
            raise SetupRejected("configuration_changed_preview_again")
        identifier = uuid.uuid4().hex
        backup = history / (identifier + ".before")
        with backup.open("xb") as stream:
            stream.write(before or b"")
            stream.flush()
            os.fsync(stream.fileno())
        if record is not None:
            # Preserve intent before the visible change. A crash after replace
            # cannot lose the ownership/conditional-removal information.
            record["backup"] = str(backup)
            with (history / (identifier + ".json")).open("x", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=True, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
        rawfd, rawname = tempfile.mkstemp(prefix=".cadence-config-", dir=path.parent)
        temp = Path(rawname)
        with os.fdopen(rawfd, "wb") as stream:
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        if snapshot(path) != before:
            raise SetupRejected("configuration_changed_preview_again")
        os.replace(temp, path)
        temp = None
        if snapshot(path) != after:
            raise SetupRejected("configuration_changed_after_apply")
        return backup
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def apply(plan: dict[str, Any], history: Path) -> dict[str, Any]:
    path = Path(plan["path"])
    before = snapshot(path)
    if (None if before is None else digest(before)) != plan["expected"]:
        raise SetupRejected("configuration_changed_preview_again")
    fresh = preview(path, plan["name"], plan["entry"], replace=True)
    if fresh["after"] != plan["after"]:
        raise SetupRejected("preview_changed")
    if fresh["unchanged"]:
        return {"status": "CLIENT_CONFIGURED", "changed": False, "actual_app_verified": False}
    doc = parse(before)
    previous = doc.get("mcp_servers", {}).get(plan["name"])
    if "mcp_servers" not in doc:
        doc["mcp_servers"] = tomlkit.table()
    doc["mcp_servers"][plan["name"]] = plan["entry"]
    after = tomlkit.dumps(doc).encode("utf-8")
    if before is not None and before.startswith(b"\xef\xbb\xbf"):
        after = b"\xef\xbb\xbf" + after
    record = {
        "path": str(path),
        "name": plan["name"],
        "installed": plan["entry"],
        "previous": previous,
        "before_sha256": plan["expected"],
        "after_sha256": digest(after),
    }
    backup = _replace_checked(path, before, after, history, record)
    receipt = history / (backup.stem + ".json")
    return {
        "status": "CLIENT_CONFIGURED",
        "changed": True,
        "receipt": str(receipt),
        "actual_app_verified": False,
        "reconnect_required": True,
    }


def remove_managed(receipt: Path, history: Path) -> dict[str, Any]:
    """Remove/restore only the exact entry still owned by this installation."""
    raw = snapshot(receipt)
    if raw is None:
        raise SetupRejected("receipt_missing")
    record = json.loads(raw)
    path = Path(record["path"])
    before = snapshot(path)
    doc = parse(before)
    servers = doc.get("mcp_servers", {})
    if servers.get(record["name"]) != record["installed"]:
        raise SetupRejected("managed_entry_changed_preserved")
    if record["previous"] is None:
        del servers[record["name"]]
    else:
        servers[record["name"]] = record["previous"]
    after = tomlkit.dumps(doc).encode("utf-8")
    if before is not None and before.startswith(b"\xef\xbb\xbf"):
        after = b"\xef\xbb\xbf" + after
    tomllib.loads(after.decode("utf-8-sig"))
    backup = _replace_checked(path, before, after, history)
    return {
        "status": "MANAGED_ENTRY_REMOVED",
        "backup": str(backup),
        "other_settings_preserved": True,
        "user_data_preserved": True,
    }
