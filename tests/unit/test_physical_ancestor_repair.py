"""Exact metadata-only ancestor provisioning on disposable POSIX directories."""

from __future__ import annotations

import copy
import os
import shutil
import stat
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from test_installation_repair import actual_recipe_layout

from cadence_mcp_bridge import _installation_repair
from cadence_mcp_bridge import _physical_ancestor_repair as recipe
from cadence_mcp_bridge import _physical_metadata as collector
from cadence_mcp_bridge.physical_ancestor_repair import invoke

__all__ = ["actual_recipe_layout"]


def fresh_core() -> ModuleType:
    module = ModuleType("disposable_ancestor_core")
    module.__dict__["__package__"] = None
    raw = Path(_installation_repair.__file__).read_bytes()
    exec(compile(raw, "disposable_ancestor_core.py", "exec"), module.__dict__)
    return module


def test_recipe_derives_only_registered_installation_library_ancestors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = {
        "paths": {"protected_roots": ["/install", "/source"]},
        "tools": {
            name: {"path": "/install/bin/" + name} for name in ("ocean", "spectre", "virtuoso")
        },
    }
    registration = {
        "routes": [
            {
                "libraries": [
                    {"path": "/install/pdk/oa/lib"},
                    {"path": "/source/own"},
                    {"path": "/external/not-selected"},
                ]
            }
        ]
    }
    monkeypatch.setattr(recipe.os.path, "realpath", lambda path: path)
    roots, paths = recipe.directory_paths(profile, registration, collector, fresh_core())
    assert roots == ["/install"]
    assert paths == ["/install", "/install/pdk", "/install/pdk/oa"]
    assert "/install/pdk/oa/lib" not in paths


def test_fixed_recipe_rejects_unbounded_ancestor_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = {
        "paths": {"protected_roots": ["/install"]},
        "tools": {"ocean": {"path": "/install/bin/ocean"}},
    }
    registration = {"routes": [{"libraries": [{"path": "/install/" + "a/" * 65 + "lib"}]}]}
    monkeypatch.setattr(recipe.os.path, "realpath", lambda path: path)
    with pytest.raises(ValueError, match="bound"):
        recipe.directory_paths(profile, registration, collector, fresh_core())


def test_no_generic_operation_or_mcp_repair_route(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="operation"):
        invoke(tmp_path, "a" * 64, "chmod", tmp_path / "out")
    assert not hasattr(recipe, "main")


@pytest.fixture
def layout(actual_recipe_layout: Any) -> Any:
    _, root, workspace, _, profile = actual_recipe_layout
    artist = root / "IC615/tools.lnx86/dfII/etc/cdslib/artist"
    pdk = root / "pdk/libs.oa22"
    leaves = [artist / "analogLib", pdk / "pdkLib"]
    for path in leaves:
        path.mkdir(parents=True)
        (path / "never-read").write_bytes(b"protected synthetic OA library leaf")
    changes = [artist.parent.parent, artist.parent, artist, pdk]
    for path in changes:
        path.chmod(0o777)
    registration = {"routes": [{"libraries": [{"path": str(path)} for path in leaves]}]}
    return profile, registration, changes, leaves, workspace


def test_plan_reads_no_candidate_contents_and_preserves_metadata(
    layout: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile, registration, changes, leaves, _ = layout
    core = fresh_core()
    monkeypatch.setattr(core, "file_hash", lambda *_: pytest.fail("candidate content read"))
    before = [path.stat() for path in changes]
    result = recipe.inventory(profile, registration, collector, core)
    selected = result["plan"]["records"]
    changed = [record for record in selected if record["mode"] != record["after_mode"]]
    assert len(changed) == 4 and {record["path"] for record in changed} == set(map(str, changes))
    assert all(record["kind"] == "directory" and record["sha256"] is None for record in selected)
    assert not set(map(str, leaves)) & {record["path"] for record in selected}
    assert [path.stat() for path in changes] == before
    assert all(path in result["plan"]["directory_metadata"] for path in map(str, changes))


def test_partial_apply_resume_repeat_and_exact_rollback(
    layout: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile, registration, changes, leaves, workspace = layout
    core = fresh_core()
    result = recipe.inventory(profile, registration, collector, core)
    request = {
        "plan": result["plan"],
        "expected_plan_sha256": result["plan_sha256"],
        "operator_authority": "synthetic fixture authorization only",
    }
    protected = {p: p.read_bytes() for leaf in leaves for p in leaf.iterdir()}
    lock = workspace / ".cadence_mcp/run.lock"
    lock_before = lock.read_bytes()
    fchmod = os.fchmod
    calls: list[int] = []

    def interrupted(fd: int, mode: int) -> None:
        calls.append(1)
        if len(calls) == 2:
            raise OSError("synthetic interruption before second target")
        fchmod(fd, mode)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fchmod", interrupted)
        with pytest.raises(OSError, match="interruption"):
            recipe.mutate(request, collector, core)
    assert sum(stat.S_IMODE(p.stat().st_mode) == 0o755 for p in changes) == 1
    recipe.mutate(request, collector, fresh_core())
    recipe.mutate(request, collector, fresh_core())
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o755 for p in changes)
    recipe.mutate(request, collector, fresh_core(), rollback=True)
    recipe.mutate(request, collector, fresh_core(), rollback=True)
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o777 for p in changes)
    for old in request["plan"]["records"]:
        now = core.snapshot(old["path"])
        assert now == {
            key: value
            for key, value in old.items()
            if key not in ("after_mode", "after_acl", "reason")
        }
    assert {p: p.read_bytes() for p in protected} == protected
    assert lock.read_bytes() == lock_before
    assert list((workspace / ".cadence_mcp").glob("trust-repair-v1-*/*.json"))
    assert _installation_repair.completion_inventory is not core.completion_inventory


@pytest.mark.parametrize("drift", ["scope", "owner", "mode", "inode"])
def test_unexpected_drift_rejects_without_further_mutation(layout: Any, drift: str) -> None:
    profile, registration, changes, _, _ = layout
    core = fresh_core()
    result = recipe.inventory(profile, registration, collector, core)
    request = {
        "plan": copy.deepcopy(result["plan"]),
        "expected_plan_sha256": result["plan_sha256"],
        "operator_authority": "test only",
    }
    if drift == "scope":
        request["plan"]["scope"]["paths"].append(str(changes[0] / "unlisted"))
        request["expected_plan_sha256"] = core.digest(request["plan"])
    elif drift == "owner":
        request["plan"]["records"][0]["uid"] += 1
        request["expected_plan_sha256"] = core.digest(request["plan"])
    elif drift == "mode":
        changes[0].chmod(0o700)
    else:
        target = changes[-1]
        target.rename(target.with_name("retained-old"))
        target.mkdir(mode=0o777)
    before = [p.stat().st_mode for p in changes]
    with pytest.raises(ValueError):
        recipe.mutate(request, collector, fresh_core())
    assert [p.stat().st_mode for p in changes] == before


def test_directory_replaced_by_file_never_hashes_contents(
    layout: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile, registration, changes, _, _ = layout
    core = fresh_core()
    original = core.plan

    def substitute(request: Any) -> Any:
        target = changes[-1]
        target.rename(target.with_name("retained-old"))
        target.write_bytes(b"must not be read")
        return original(request)

    monkeypatch.setattr(core, "plan", substitute)
    monkeypatch.setattr(core, "file_hash", lambda *_: pytest.fail("candidate content read"))
    with pytest.raises(ValueError, match="directory_identity"):
        recipe.inventory(profile, registration, collector, core)


def test_extended_acl_is_reported_without_modification(layout: Any) -> None:
    if shutil.which("setfacl") is None:
        pytest.skip("ACL utility absent")
    profile, registration, changes, _, _ = layout
    subprocess.run(["setfacl", "-m", "d:u::rwx,d:g::rwx,d:o::rwx", str(changes[-1])], check=True)
    before = changes[-1].stat()
    with pytest.raises(ValueError, match="extended_acl"):
        recipe.inventory(profile, registration, collector, fresh_core())
    assert changes[-1].stat() == before
