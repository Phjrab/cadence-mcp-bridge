"""Independent synthetic acceptance oracles; no VM access or physical signoff."""

from __future__ import annotations

import copy
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from cadence_mcp_bridge.layout_models import (
    LayoutApplyRequest,
    LayoutCapabilities,
    LayoutPlanRequest,
    LayoutSnapshot,
)
from cadence_mcp_bridge.schematic_plan import RevisionBinding

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = json.loads((ROOT / "tests/fixtures/layout/scenario.json").read_text(encoding="utf-8"))
spec = importlib.util.spec_from_file_location(
    "layout_acceptance_verifier", ROOT / "scripts/verify-layout-edit.py"
)
assert spec is not None and spec.loader is not None
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
OPERATION_ID = UUID("18c5fef8-92cb-4e65-9b5b-13b29453ad28")


def point(values: list[int]) -> dict[str, int]:
    return dict(zip(("x", "y"), values, strict=True))


def bbox(values: list[list[int]]) -> dict[str, Any]:
    return {"lower_left": point(values[0]), "upper_right": point(values[1])}


def load_snapshot(payload: dict[str, Any]) -> LayoutSnapshot:
    return LayoutSnapshot.model_validate_json(json.dumps(payload))


def load_request(payload: dict[str, Any]) -> LayoutPlanRequest:
    return LayoutPlanRequest.model_validate_json(json.dumps(payload))


def snapshots() -> tuple[LayoutSnapshot, LayoutSnapshot, LayoutSnapshot]:
    technology = SCENARIO["technology"]
    binding = RevisionBinding(
        workspace_id="qa-layout",
        design_id="fixture",
        revision_id="source",
        source_baseline_sha256="a" * 64,
    )
    source = load_snapshot(
        {
            "binding": binding.model_dump(mode="json"),
            "source_baseline_sha256": "a" * 64,
            "technology": {
                "dbu_per_um": technology["dbu_per_um"],
                "manufacturing_grid_dbu": technology["manufacturing_grid_dbu"],
                "allowed_layer_purposes": [
                    {"layer": layer, "purpose": purpose}
                    for layer, purpose in technology["allowed_lpp"]
                ],
                "provenance": "synthetic_fixture",
            },
            "instances": [
                {
                    "object_id": "instance-one",
                    "master_id": "synthetic-device",
                    "orientation": "R0",
                    "origin_dbu": point(SCENARIO["before"]["instance_origin_dbu"]),
                    "bbox_dbu": bbox([[1000, 2000], [1100, 2100]]),
                }
            ],
            "shapes": [
                {
                    "object_id": "shape-one",
                    "kind": "rect",
                    "layer": "metal1",
                    "purpose": "drawing",
                    "bbox_dbu": bbox(SCENARIO["before"]["shape_bbox_dbu"]),
                }
            ],
            "provenance": "synthetic_fixture",
            "capabilities": LayoutCapabilities(
                move="supported", add_rect="supported", add_pin="supported"
            ).model_dump(mode="json"),
        }
    )
    child = source.model_dump(mode="json")
    child.pop("semantic_sha256")
    child["binding"].update(
        {
            "revision_id": "working",
            "parent_revision_id": "source",
            "parent_revision_sha256": source.semantic_sha256,
        }
    )
    child.update(owned=True, read_only=False)
    before = load_snapshot(child)
    expected = before.model_dump(mode="json")
    expected.pop("semantic_sha256")
    oracle = SCENARIO["expected"]
    expected["instances"][0]["origin_dbu"] = point(oracle["instance_origin_dbu"])
    expected["instances"][0]["bbox_dbu"] = bbox([[1005, 1990], [1105, 2090]])
    expected["shapes"][0]["bbox_dbu"] = bbox(oracle["shape_bbox_dbu"])
    expected["shapes"].append(
        {
            "object_id": "rectangle-new",
            "kind": "rect",
            "layer": "metal1",
            "purpose": "drawing",
            "bbox_dbu": bbox(oracle["rectangle_bbox_dbu"]),
        }
    )
    expected["pins"] = [
        {
            "object_id": "pin-new",
            "layer": "metal1",
            "purpose": "pin",
            "bbox_dbu": bbox(oracle["pin_bbox_dbu"]),
            "net_id": "net-out",
            "terminal_id": "out",
            "association": "requested",
        }
    ]
    return source, before, load_snapshot(expected)


def plan_request(before: LayoutSnapshot) -> LayoutPlanRequest:
    edits = SCENARIO["edits_um"]
    return load_request(
        {
            "binding": before.binding.model_dump(mode="json"),
            "operation_id": str(OPERATION_ID),
            "expected_baseline_sha256": before.semantic_sha256,
            "edits": [
                {
                    "kind": "move",
                    "object_id": "instance-one",
                    "dx_um": edits["instance_delta"][0],
                    "dy_um": edits["instance_delta"][1],
                },
                {
                    "kind": "move",
                    "object_id": "shape-one",
                    "dx_um": edits["shape_delta"][0],
                    "dy_um": edits["shape_delta"][1],
                },
                {
                    "kind": "add_rect",
                    "object_id": "rectangle-new",
                    "layer": "metal1",
                    "purpose": "drawing",
                    "bbox_um": sum(edits["rectangle_bbox"], []),
                },
                {
                    "kind": "add_pin",
                    "object_id": "pin-new",
                    "layer": "metal1",
                    "purpose": "pin",
                    "bbox_um": sum(edits["pin_bbox"], []),
                    "net_id": "net-out",
                    "terminal_id": "out",
                },
            ],
        }
    )


def packet(*, native_claim: bool = False, owned_seed: bool = False) -> dict[str, Any]:
    from cadence_mcp_bridge.layout_engine import build_plan, compute_diff

    source, before, after = snapshots()
    if native_claim or owned_seed:
        # Fabricated labels exercise receipt validation; this is still synthetic
        # test data and proves no VM execution or native provenance.
        native_snapshots = []
        for snapshot in (source, before, after):
            data = snapshot.model_dump(mode="json")
            data.pop("semantic_sha256")
            if owned_seed and not native_snapshots:
                data.update(owned=True, read_only=False)
            if native_claim:
                data["provenance"] = "native_readback"
                data["technology"]["provenance"] = "native_observed"
                for pin in data["pins"]:
                    pin["association"] = "native_verified"
            if native_snapshots:
                data["binding"]["parent_revision_sha256"] = native_snapshots[0].semantic_sha256
            native_snapshots.append(load_snapshot(data))
        source, before, after = native_snapshots
    plan = build_plan(before, plan_request(before))
    assert plan.expected_semantic_sha256 == after.semantic_sha256
    diff = compute_diff(before, after, expected=after).model_dump(mode="json")
    diff["matches_plan"] = True
    result = {
        "executed": native_claim,
        "status": "EDIT_VERIFIED" if native_claim else "NOT_VERIFIED",
        "operation_id": str(OPERATION_ID),
        "binding": before.binding.model_dump(mode="json"),
        "snapshot": after.model_dump(mode="json"),
        "diff": diff,
        "saved": True,
        "reopened": True,
        "source_unchanged": True,
    }
    receipt = {
        "build_sha": "b" * 40,
        "environment": "actual_vm" if native_claim else "synthetic_fixture",
        "source_before": source.model_dump(mode="json"),
        "source_after": source.model_dump(mode="json"),
        "before": before.model_dump(mode="json"),
        "request": LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256).model_dump(
            mode="json"
        ),
        "result": result,
        "replay": dict(result, replayed=True, executed=False),
        "write_counts": {"before_apply": 0, "after_apply": 1, "after_replay": 1},
        "source_tree_before_sha256": "c" * 64,
        "source_tree_after_sha256": "c" * 64,
    }
    if owned_seed:
        protected = {"original-cell": source.source_baseline_sha256, "pdk-library": "e" * 64}
        receipt.update(
            source_kind="owned_seed",
            protected_trees_before_sha256=protected,
            protected_trees_after_sha256=dict(protected),
        )
    return receipt


def test_independent_coordinate_oracle_and_synthetic_receipt() -> None:
    receipt = packet()
    before = copy.deepcopy(receipt)
    report = verifier.verify_receipt(receipt)
    assert receipt == before
    assert report["status"] == "RECEIPT_CONSISTENT"
    assert report["environment"] == "synthetic_fixture"
    assert report["app_status"] == "APP_NOT_TESTED"
    assert set(report["physical_verification"].values()) == {"NOT_RUN"}


@pytest.mark.parametrize(
    "corruption",
    [
        "build",
        "source",
        "reopen",
        "duplicate_write",
        "replay_identity",
        "replay_snapshot",
        "unexpected_diff",
        "lying_native",
        "wrong_plan_hash",
        "wrong_coordinates",
    ],
)
def test_false_success_receipts_are_rejected(corruption: str) -> None:
    receipt = packet()
    if corruption == "build":
        receipt["build_sha"] = "main"
    elif corruption == "source":
        receipt["source_after"]["instances"][0]["origin_dbu"]["x"] += 5
        receipt["source_after"].pop("semantic_sha256")
    elif corruption == "reopen":
        receipt["result"]["reopened"] = False
    elif corruption == "duplicate_write":
        receipt["write_counts"]["after_replay"] += 1
    elif corruption == "replay_identity":
        receipt["replay"]["operation_id"] = "2579c7e9-1e77-4a56-9afd-84e856d49528"
    elif corruption == "replay_snapshot":
        receipt["replay"]["snapshot"] = receipt["before"]
    elif corruption == "unexpected_diff":
        receipt["result"]["diff"]["unexpected_object_ids"] = ["extra"]
    elif corruption == "lying_native":
        receipt["environment"] = "actual_vm"
    elif corruption == "wrong_plan_hash":
        receipt["request"]["expected_plan_sha256"] = "c" * 64
    elif corruption == "wrong_coordinates":
        receipt["result"]["snapshot"]["instances"][0]["origin_dbu"]["x"] += 5
        receipt["result"]["snapshot"].pop("semantic_sha256")
    with pytest.raises(ValueError):
        verifier.verify_receipt(receipt)


def test_cli_retains_receipt_and_reports_no_private_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "receipt.json"
    data = json.dumps(packet()).encode()
    path.write_bytes(data)
    assert verifier.main(["--receipt", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "RECEIPT_CONSISTENT"
    assert path.read_bytes() == data
    private = b'{"build_sha":"private-do-not-return"}'
    path.write_bytes(private)
    assert verifier.main(["--receipt", str(path)]) == 1
    output = capsys.readouterr().out
    assert "private-do-not-return" not in output
    assert path.read_bytes() == private


@pytest.mark.parametrize("invalid", ["unit", "lpp", "stale", "off_grid", "nonfinite"])
async def test_service_scenario_rejects_bad_plan_before_provider_write(invalid: str) -> None:
    from cadence_mcp_bridge.layout_service import LayoutService

    _, before, _ = snapshots()
    provider = SimpleNamespace(inspect=AsyncMock(return_value=before), apply=AsyncMock())
    service = LayoutService(provider)
    valid = await service.plan(plan_request(before))
    assert valid.preview.created == 2 and valid.preview.moved == 2
    request = plan_request(before).model_dump(mode="json")
    if invalid == "unit":
        request["edits"][0]["unit"] = "nm"
    elif invalid == "lpp":
        request["edits"][2]["layer"] = "unregistered"
    elif invalid == "stale":
        request["expected_baseline_sha256"] = "f" * 64
    elif invalid == "off_grid":
        request["edits"][0]["dx_um"] = "0.001"
    else:
        request["edits"][0]["dx_um"] = "NaN"
    reads_before = provider.inspect.await_count
    with pytest.raises(ValueError):
        await service.plan(load_request(request))
    provider.apply.assert_not_awaited()
    if invalid in ("unit", "nonfinite"):
        assert provider.inspect.await_count == reads_before


async def test_service_does_not_promote_synthetic_save_reopen_to_native_success() -> None:
    from cadence_mcp_bridge.layout_models import LayoutResult
    from cadence_mcp_bridge.layout_service import LayoutService

    receipt = packet()
    request = LayoutApplyRequest.model_validate_json(json.dumps(receipt["request"]))
    result = LayoutResult.model_validate_json(json.dumps(receipt["result"]))
    provider = SimpleNamespace(apply=AsyncMock(return_value=result))
    returned = await LayoutService(provider).apply(request)
    assert returned.status == "NOT_VERIFIED"
    assert returned.snapshot is not None
    assert returned.snapshot.provenance == "synthetic_fixture"
    assert returned.saved and returned.reopened
    provider.apply.assert_awaited_once_with(request)


async def test_partial_unknown_result_is_retained_without_service_retry() -> None:
    from cadence_mcp_bridge.layout_models import LayoutResult
    from cadence_mcp_bridge.layout_service import LayoutService

    receipt = packet()
    request = LayoutApplyRequest.model_validate_json(json.dumps(receipt["request"]))
    partial = LayoutResult(
        status="OUTCOME_UNKNOWN",
        binding=request.plan.request.binding,
        operation_id=request.plan.request.operation_id,
    )
    provider = SimpleNamespace(apply=AsyncMock(return_value=partial))
    assert await LayoutService(provider).apply(request) == partial
    provider.apply.assert_awaited_once_with(request)


async def test_service_selection_returns_preserved_parent_without_writer_call() -> None:
    from cadence_mcp_bridge.layout_models import LayoutResult, LayoutSelectRequest
    from cadence_mcp_bridge.layout_service import LayoutService

    source, _, _ = snapshots()
    original = source.model_dump_json()
    result = LayoutResult(status="SELECTED", binding=source.binding, snapshot=source)
    provider = SimpleNamespace(select=AsyncMock(return_value=result), apply=AsyncMock())
    returned = await LayoutService(provider).select(
        LayoutSelectRequest(
            binding=source.binding,
            expected_baseline_sha256=source.semantic_sha256,
        )
    )
    assert returned.snapshot is not None and returned.snapshot.model_dump_json() == original
    assert not returned.executed
    provider.apply.assert_not_awaited()


def test_declared_native_receipt_still_reports_only_supplied_consistency() -> None:
    report = verifier.verify_receipt(packet(native_claim=True))
    assert report["evidence_scope"] == "supplied_receipt_consistency_only"
    assert report["app_status"] == "APP_NOT_TESTED"


def test_owned_seed_receipt_keeps_honest_ownership_and_separate_tree_evidence() -> None:
    # These native labels are fabricated validator inputs, not actual OA evidence.
    receipt = packet(native_claim=True, owned_seed=True)
    original = copy.deepcopy(receipt)
    report = verifier.verify_receipt(receipt)
    assert receipt == original
    assert receipt["source_before"]["owned"] and not receipt["source_before"]["read_only"]
    assert report["source_kind"] == "owned_seed"
    assert report["evidence_scope"] == "supplied_receipt_consistency_only"
    assert verifier.verify_receipt(packet())["source_kind"] == "registered_read_only"


@pytest.mark.parametrize(
    "corruption",
    [
        "implicit_kind",
        "unknown_kind",
        "readonly_parent",
        "same_revision",
        "other_workspace",
        "other_design",
        "parent_geometry",
        "parent_drift",
        "parent_tree",
        "protected_missing",
        "protected_empty",
        "protected_drift",
        "protected_anchor",
        "protected_digest",
    ],
)
def test_owned_seed_receipt_rejects_missing_lineage_or_conservation(corruption: str) -> None:
    receipt = packet(native_claim=True, owned_seed=True)
    if corruption == "implicit_kind":
        receipt.pop("source_kind")
    elif corruption == "unknown_kind":
        receipt["source_kind"] = "legacy"
    elif corruption in {
        "readonly_parent",
        "same_revision",
        "other_workspace",
        "other_design",
        "parent_geometry",
    }:
        source = receipt["source_before"]
        if corruption == "readonly_parent":
            source.update(owned=False, read_only=True)
        elif corruption == "same_revision":
            source["binding"]["revision_id"] = receipt["before"]["binding"]["revision_id"]
        elif corruption == "other_workspace":
            source["binding"]["workspace_id"] = "other"
        elif corruption == "other_design":
            source["binding"]["design_id"] = "other"
        else:
            source["instances"][0]["origin_dbu"]["x"] += 5
        source.pop("semantic_sha256")
        receipt["source_before"] = load_snapshot(source).model_dump(mode="json")
        receipt["source_after"] = copy.deepcopy(receipt["source_before"])
    elif corruption == "parent_drift":
        receipt["source_after"]["capabilities"]["move"] = "unsupported"
    elif corruption == "parent_tree":
        receipt["source_tree_after_sha256"] = "d" * 64
    elif corruption == "protected_missing":
        receipt.pop("protected_trees_before_sha256")
    elif corruption == "protected_empty":
        receipt["protected_trees_before_sha256"] = {}
        receipt["protected_trees_after_sha256"] = {}
    elif corruption == "protected_drift":
        receipt["protected_trees_after_sha256"]["pdk-library"] = "d" * 64
    else:
        value = "d" * 64 if corruption == "protected_anchor" else "not-a-digest"
        receipt["protected_trees_before_sha256"]["original-cell"] = value
        receipt["protected_trees_after_sha256"]["original-cell"] = value
    with pytest.raises(ValueError):
        verifier.verify_receipt(receipt)


@pytest.mark.parametrize("missing", ["tree", "pin_association", "actual_dispatch", "diff_changes"])
def test_declared_native_success_requires_conserved_source_and_pin_evidence(missing: str) -> None:
    receipt = packet(native_claim=True)
    if missing == "tree":
        receipt["source_tree_after_sha256"] = "d" * 64
    elif missing == "pin_association":
        receipt["result"]["snapshot"]["pins"][0]["association"] = "requested"
    elif missing == "actual_dispatch":
        receipt["result"]["executed"] = False
    else:
        receipt["result"]["diff"]["changes"] = []
    with pytest.raises(ValueError):
        verifier.verify_receipt(receipt)


def worker_fixture(tmp_path: Path, **options: Any) -> tuple[Any, Any, Any, Any, dict[str, Any]]:
    worker = pytest.importorskip(
        "cadence_mcp_bridge._layout_worker", reason="native worker dependency not imported yet"
    )
    fixture_spec = importlib.util.spec_from_file_location(
        "layout_durability_fixture", ROOT / "tests/fixtures/layout/durability.py"
    )
    assert fixture_spec is not None and fixture_spec.loader is not None
    harness = importlib.util.module_from_spec(fixture_spec)
    fixture_spec.loader.exec_module(harness)
    receipt = packet()
    root = tmp_path / "synthetic-runtime"
    accounting = harness.Accounting(
        root, final_check_failure=options.get("final_check_failure", False)
    )
    runtime = harness.Runtime(
        root, receipt["before"], receipt["result"]["snapshot"], failure=options.get("failure")
    )
    core = worker.LayoutWorker(runtime, accounting, harness._native_operations)
    return worker, harness, accounting, core, receipt["request"]


@pytest.mark.parametrize("failure", ["crash", "partial"])
def test_worker_durable_intent_restart_never_redispatches_or_reopens_partial(
    tmp_path: Path,
    failure: str,
) -> None:
    worker, harness, accounting, core, request = worker_fixture(tmp_path, failure=failure)
    with pytest.raises((harness.SimulatedCrash, ValueError)):
        core.execute("apply", request)
    original = harness.journal(accounting.root)
    assert any(name.endswith("layout-intent.json") for name in original)
    assert not any(name.endswith("layout-receipt.json") for name in original)
    if failure == "partial":
        assert any(name.endswith("layout-failure.json") for name in original)
    restarted_runtime = harness.Runtime(accounting.root, core.runtime.before, core.runtime.after)
    restarted = worker.LayoutWorker(restarted_runtime, accounting, harness._native_operations)
    replay = restarted.execute("apply", request)
    assert replay["state"] == "OUTCOME_UNKNOWN" and replay["replayed"]
    assert not replay["executed"] and restarted_runtime.writes == 0
    assert harness.journal(accounting.root) == original
    from cadence_mcp_bridge.layout_engine import build_plan

    before = load_snapshot(core.runtime.before)
    second_plan = build_plan(
        before, plan_request(before).model_copy(update={"operation_id": str(uuid4())})
    )
    second = LayoutApplyRequest(
        plan=second_plan,
        expected_plan_sha256=second_plan.plan_sha256,
    ).model_dump(mode="json")
    with pytest.raises(ValueError, match="already_sealed"):
        restarted.execute("apply", second)
    assert restarted_runtime.writes == 0
    assert harness.journal(accounting.root) == original


def test_worker_different_ids_contend_for_one_sealed_target(tmp_path: Path) -> None:
    from cadence_mcp_bridge.layout_engine import build_plan

    _, _, _, core, first = worker_fixture(tmp_path)
    before = load_snapshot(core.runtime.before)
    second_plan = build_plan(
        before, plan_request(before).model_copy(update={"operation_id": str(uuid4())})
    )
    second = LayoutApplyRequest(
        plan=second_plan,
        expected_plan_sha256=second_plan.plan_sha256,
    ).model_dump(mode="json")

    def invoke(request: dict[str, Any]) -> str:
        try:
            return str(core.execute("apply", request)["state"])
        except ValueError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(invoke, (first, second)))
    assert sorted(results) == ["SUCCEEDED", "layout_working_revision_already_sealed"]
    assert core.runtime.writes == 1


def test_worker_final_session_failure_cannot_replay_as_success(tmp_path: Path) -> None:
    _, harness, accounting, core, request = worker_fixture(tmp_path, final_check_failure=True)
    with pytest.raises(ValueError, match="synthetic_final_session_check_failed"):
        core.execute("apply", request)
    assert any(name.endswith("layout-failure.json") for name in harness.journal(accounting.root))
    writes = core.runtime.writes
    replay = core.execute("apply", request)
    assert core.runtime.writes == writes
    assert replay["state"] == "OUTCOME_UNKNOWN", "terminal failure must not replay as success"
