"""Root-only model recipe integration on owned synthetic files, never a VM/PDK."""

import copy
import hashlib
import os
import stat
from pathlib import Path

import pytest
from test_installation_repair import actual_recipe_layout as actual_recipe_layout

from cadence_mcp_bridge import _installation_repair as repair


def _tiny_models(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    content = {
        "top.scs": (
            'section NN\ninclude "left.scs" section=LEFT\n'
            'include "right.scs" section=RIGHT\nendsection NN\n'
            'section FF\ninclude "unselected.scs" section=MISSING\nendsection FF\n'
        ),
        "left.scs": 'section LEFT\ninclude "shared.scs" section=CORE\nendsection LEFT\n',
        "right.scs": 'section RIGHT\ninclude "shared.scs" section=CORE\nendsection RIGHT\n',
        "shared.scs": (
            'section CORE\ninclude "top.scs" section=NN\n'
            'model synthetic resistor r=100\nendsection CORE\n'
            'section UNUSED\ninclude "absent.scs"\nendsection UNUSED\n'
        ),
        "unselected.scs": 'synthetic unused evidence; this must never be selected\n',
    }
    result = {}
    for name, raw in content.items():
        path = directory / name
        path.write_text(raw, encoding="ascii")
        result[name] = path
    return result


def _contents(paths: dict[str, Path]) -> dict[str, bytes]:
    return {name: path.read_bytes() for name, path in paths.items()}


def _request(prepared):
    return dict(
        plan=prepared["plan"], expected_plan_sha256=prepared["plan_sha256"],
        operator_authority="SYNTHETIC FIXTURE ONLY NOT HUMAN APPROVAL",
    )


@pytest.mark.parametrize("selected", ["NN", "FF"])
def test_real_model_diamond_cycle_closure_excludes_unselected_files(
    tmp_path, monkeypatch, selected,
):
    paths = _tiny_models(tmp_path / "models")
    before = _contents(paths)
    # Substitute only the platform-specific no-follow open primitive on Windows;
    # parsing, inode/hash observation, cycle detection and actual file reads run.
    if os.name == "nt":
        monkeypatch.setattr(
            repair, "open_fixed", lambda path: os.open(path, os.O_RDONLY | os.O_BINARY),
        )
        monkeypatch.setattr(repair, "inside", lambda p, r: Path(p).is_relative_to(Path(r)))
    if selected == "FF":
        with pytest.raises(ValueError, match="model_graph_section_absent"):
            repair.model_graph(str(paths["top.scs"]), selected)
    else:
        closure = repair.model_graph(str(paths["top.scs"]), selected)
        assert closure == {
            str(path): hashlib.sha256(before[name]).hexdigest()
            for name, path in paths.items() if name != "unselected.scs"
        }
        assert str(paths["unselected.scs"]) not in closure
    assert _contents(paths) == before


@pytest.fixture
def model_recipe(actual_recipe_layout):
    _shared, root, _workspace, code_paths, profile = actual_recipe_layout
    paths = _tiny_models(root / "synthetic-pdk" / "models" / "spectre")
    paths["shared.scs"].chmod(0o666)
    include = dict(
        path=str(paths["top.scs"]), section="NN",
        file_sha256=hashlib.sha256(paths["top.scs"].read_bytes()).hexdigest(),
    )
    return root, code_paths, profile, paths, include


def test_actual_model_recipe_exact_closure_and_observed_apply_retry_rollback(model_recipe):
    root, code_paths, profile, paths, include = model_recipe
    models_before, programs_before = _contents(paths), {p: p.read_bytes() for p in code_paths}
    prepared = repair.inventory_models(dict(profile=profile, model_include=include))
    original = prepared["plan"]
    expected = {str(path) for name, path in paths.items() if name != "unselected.scs"}
    ancestor = paths["top.scs"].parent
    while True:
        expected.add(str(ancestor))
        if ancestor == root:
            break
        ancestor = ancestor.parent
    assert set(original["scope"]["paths"]) == expected
    assert original["scope"]["links"] == []
    assert {row["path"] for row in original["records"] if row["kind"] == "file"} == {
        str(path) for name, path in paths.items() if name != "unselected.scs"
    }
    managed = Path(profile["paths"]["managed_root"])
    assert not list(managed.glob("trust-repair-v1-*"))
    request = _request(prepared)
    repair.mutate(request)
    assert stat.S_IMODE(paths["shared.scs"].stat().st_mode) == 0o644
    uid = os.getuid()
    receipt = managed / f"trust-repair-v1-{'admin' if uid == 0 else 'user'}-{uid}"
    receipt = receipt / (prepared["plan_sha256"] + ".json")
    receipt_before, receipt_inode = receipt.read_bytes(), receipt.stat().st_ino
    repair.mutate(request)
    repair.mutate(request, rollback=True)
    repair.mutate(request, rollback=True)
    assert stat.S_IMODE(paths["shared.scs"].stat().st_mode) == 0o666
    assert receipt.read_bytes() == receipt_before == repair.receipt_bytes(original)
    assert receipt.stat().st_ino == receipt_inode
    assert _contents(paths) == models_before
    assert {p: p.read_bytes() for p in code_paths} == programs_before


def test_actual_model_recipe_forged_before_state_cannot_authenticate_rollback(model_recipe):
    _root, _code_paths, profile, paths, include = model_recipe
    prepared = repair.inventory_models(dict(profile=profile, model_include=include))
    repair.mutate(_request(prepared))
    before = {p: (p.read_bytes(), stat.S_IMODE(p.stat().st_mode)) for p in paths.values()}
    forged = copy.deepcopy(prepared)
    row = next(r for r in forged["plan"]["records"] if r["path"] == str(paths["shared.scs"]))
    row.update(mode=0o777, acl="user::rwx\ngroup::rwx\nother::rwx\n")
    forged["plan_sha256"] = repair.digest(forged["plan"])
    with pytest.raises(ValueError, match="repair_applied_receipt_required"):
        repair.mutate(_request(forged), rollback=True)
    assert before == {p: (p.read_bytes(), stat.S_IMODE(p.stat().st_mode)) for p in paths.values()}
    assert not list(Path(profile["paths"]["managed_root"]).rglob(forged["plan_sha256"] + ".json"))


def test_actual_model_recipe_bounds_complete_profile_and_include_envelope(
    model_recipe, monkeypatch,
):
    _root, _code_paths, profile, paths, include = model_recipe
    before = _contents(paths)
    full = repair.inventory_models(dict(profile=profile, model_include=include))
    core = copy.deepcopy(full)
    for field in ("profile", "model_include", "recipe_id"):
        del core["plan"][field]
    core["plan"]["schema_version"] = 1
    core["plan_sha256"] = repair.digest(core["plan"])
    authority = "\U0001f4a5" * 512
    core_mutation = dict(
        plan=core["plan"], expected_plan_sha256=core["plan_sha256"], operator_authority=authority,
    )
    full_mutation = dict(
        plan=full["plan"], expected_plan_sha256=full["plan_sha256"], operator_authority=authority,
    )
    boundary = max(len(repair.canonical(core)), len(repair.canonical(core_mutation))) + 1
    assert boundary < max(len(repair.canonical(full)), len(repair.canonical(full_mutation))) + 1
    monkeypatch.setattr(repair, "LIMIT", boundary)
    with pytest.raises(ValueError, match="inventory_serialized_limit"):
        repair.inventory_models(dict(profile=profile, model_include=include))
    assert _contents(paths) == before
    assert not list(Path(profile["paths"]["managed_root"]).glob("trust-repair-v1-*"))


def test_model_completion_reenumerates_only_bound_selected_closure(monkeypatch):
    profile = {"environment_id": "synthetic-only"}
    include = {"path": "/fixed/model.scs", "section": "NN", "file_sha256": "a" * 64}
    original = dict(recipe_id="standard-vm-model-trust-v1", profile=profile,
                    model_include=include)
    expected = {"scope": {"paths": ["/fixed/model.scs"]}, "records": []}
    calls = []
    monkeypatch.setattr(
        repair, "inventory_models", lambda request: calls.append(request) or {"plan": expected}
    )
    def forbidden(_profile):
        raise AssertionError("model completion must not enumerate program installation")
    monkeypatch.setattr(repair, "inventory", forbidden)
    assert repair.completion_inventory(original) is expected
    assert calls == [dict(profile=profile, model_include=include)]


def test_model_completion_rejects_changed_selected_scope(monkeypatch):
    original = dict(recipe_id="standard-vm-model-trust-v1", profile={}, model_include={},
                    scope={"paths": ["/fixed/top.scs"]}, records=[])
    monkeypatch.setattr(repair, "plan", lambda scope: {"plan": dict(scope=scope, records=[])})
    monkeypatch.setattr(repair, "inventory_models", lambda request: {
        "plan": dict(scope={"paths": ["/fixed/top.scs", "/fixed/new.scs"]}, records=[])
    })
    with pytest.raises(ValueError, match="completion_recipe_scope"):
        repair.verify_completed_targets(original, False, recipe_guard=True)


@pytest.mark.parametrize("changed", ["file-mode", "ancestor-mode", "file-identity"])
def test_trusted_model_rechecks_metadata_after_final_content_scan(
    model_recipe, monkeypatch, changed
):
    _, _, _, paths, _ = model_recipe
    paths["shared.scs"].chmod(0o644)
    if os.getuid() == 0:
        pytest.skip("runtime trust intentionally rejects root")
    before = _contents(paths)
    original = repair.model_graph
    calls = 0

    def graph(main, section):
        nonlocal calls
        value = original(main, section)
        calls += 1
        if calls == 2:
            if changed == "ancestor-mode":
                paths["shared.scs"].parent.chmod(0o777)
            elif changed == "file-mode":
                paths["shared.scs"].chmod(0o666)
            else:
                original_path = paths["shared.scs"]
                original_path.rename(original_path.with_name("preserved-original-model"))
                original_path.write_bytes(before["shared.scs"])
                original_path.chmod(0o644)
        return value

    monkeypatch.setattr(repair, "model_graph", graph)
    with pytest.raises(ValueError, match="model_graph_(untrusted_metadata|metadata_drift)"):
        repair.trusted_model_graph(str(paths["top.scs"]), "NN")
    assert calls == 2 and _contents(paths) == before
