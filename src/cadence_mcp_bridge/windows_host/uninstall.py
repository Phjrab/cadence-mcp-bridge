"""Explicit Windows uninstall hook; conditional owned-entry cleanup, no VM actions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from cadence_mcp_bridge.windows_host.backend import data_root
from cadence_mcp_bridge.windows_host.configuration import remove_managed, snapshot


def owned_receipts(root: Path, launcher: Path) -> list[Path]:
    history = root / "config-history"
    if not history.is_dir():
        return []
    paths = list(history.glob("*.json"))
    if len(paths) > 1000:
        raise ValueError("manual_history_review_required")
    result = []
    for path in sorted(paths, key=lambda p: p.stat().st_mtime_ns, reverse=True):
        raw = snapshot(path)
        if raw is None:
            continue
        record = json.loads(raw)
        if record.get("installed", {}).get("command") == str(launcher):
            result.append(path)
    return result


def clean(root: Path, launcher: Path) -> dict[str, object]:
    removed = 0
    preserved = 0
    for receipt in owned_receipts(root, launcher):
        try:
            remove_managed(receipt, root / "config-history")
            removed += 1
        except (OSError, ValueError, KeyError):
            preserved += 1
    return {
        "managed_entries_removed": removed,
        "changed_or_inactive_entries_preserved": preserved,
        "user_data_preserved": True,
        "remote_contact": False,
        "new_simulations": 0,
    }


def main() -> int:
    try:
        report = clean(data_root(), Path(sys.executable).parent.parent / "CadenceMCPBridge.exe")
    except (OSError, ValueError, KeyError):
        print('{"status":"MANUAL_CONFIG_REMOVAL_REQUIRED","remote_contact":false}')
        return 1
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
