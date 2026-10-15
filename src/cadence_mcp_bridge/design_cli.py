"""Explicit local M2 metadata and typed plan commands, with no execution backend."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from cadence_mcp_bridge.design_revisions import RevisionEvidence, RevisionRejected, RevisionStore
from cadence_mcp_bridge.physical_capabilities import (
    PhysicalCapabilityInventory,
    assess_physical_capabilities,
)
from cadence_mcp_bridge.schematic_plan import (
    DeviceRegistry,
    RevisionBinding,
    SchematicPlan,
    dry_run_plan,
    synthetic_inverter_fixture,
)


def add_design_plan_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    parser = subparsers.add_parser("operator-design", help="Local revision and inverter plan only.")
    actions = parser.add_subparsers(dest="design_plan_action", required=True)
    fixture = actions.add_parser("example", help="Export fictional inverter registry/plan/binding.")
    fixture.add_argument("--output", type=Path, required=True)
    initialize = actions.add_parser("init", help="Initialize a new dedicated local revision store.")
    initialize.add_argument("--store", type=Path, required=True)
    for action in ("validate", "record"):
        command = actions.add_parser(action)
        command.add_argument("--plan", type=Path, required=True)
        command.add_argument("--registry", type=Path, required=True)
        command.add_argument("--binding", type=Path, required=True)
        command.add_argument("--store", type=Path, required=action == "record")
    read = actions.add_parser("show")
    read.add_argument("--store", type=Path, required=True)
    read.add_argument("--workspace", required=True)
    read.add_argument("--design", required=True)
    read.add_argument("--revision", required=True)
    evidence = actions.add_parser(
        "attach-reference", help="Attach an unverified external result ID."
    )
    evidence.add_argument("--store", type=Path, required=True)
    evidence.add_argument("--reference", type=Path, required=True)
    physical = actions.add_parser(
        "physical-assess", help="Assess local observations; no VM contact."
    )
    physical.add_argument("--inventory", type=Path, required=True)


def _load(path: Path, model: type[BaseModel]) -> Any:
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise RevisionRejected("regular_input_file_required")
    with path.open("rb") as stream:
        data = stream.read(1_048_577)
    if len(data) > 1_048_576:
        raise RevisionRejected("input_size_limit")
    return model.model_validate_json(data)


def run_design_plan(arguments: argparse.Namespace) -> int:
    result: dict[str, Any]
    try:
        action = arguments.design_plan_action
        if action == "example":
            binding = RevisionBinding(
                workspace_id="synthetic-work",
                design_id="inverter",
                revision_id="draft-one",
                source_baseline_sha256="0" * 64,
            )
            registry, plan = synthetic_inverter_fixture(binding)
            arguments.output.mkdir(mode=0o700)
            for name, model in (("registry", registry), ("plan", plan), ("binding", binding)):
                with (arguments.output / (name + ".json")).open("x", encoding="utf-8") as stream:
                    stream.write(model.model_dump_json(indent=2) + "\n")
            result = {"status": "SYNTHETIC_EXAMPLE_EXPORTED", "production_cdf": "UNVERIFIED"}
        elif action == "init":
            RevisionStore(arguments.store).initialize()
            result = {"status": "LOCAL_REVISION_STORE_INITIALIZED"}
        elif action in ("validate", "record"):
            plan = _load(arguments.plan, SchematicPlan)
            registry = _load(arguments.registry, DeviceRegistry)
            binding = _load(arguments.binding, RevisionBinding)
            if action == "record":
                record = RevisionStore(arguments.store).add(plan, registry, binding)
                result = {
                    "status": record.status,
                    "revision_sha256": record.revision_sha256,
                    "record": record.model_dump(mode="json"),
                }
            else:
                baseline = None
                if plan.binding.parent_revision_id is not None:
                    if arguments.store is None:
                        raise RevisionRejected("parent_store_required")
                    parent = RevisionStore(arguments.store).read(
                        binding.workspace_id,
                        binding.design_id,
                        binding.parent_revision_id,
                    )
                    if parent.revision_sha256 != binding.parent_revision_sha256:
                        raise RevisionRejected("parent_revision_digest_mismatch")
                    baseline = parent.plan
                result = dry_run_plan(plan, registry, binding, baseline=baseline).model_dump(
                    mode="json",
                )
        elif action == "show":
            store = RevisionStore(arguments.store)
            record = store.read(arguments.workspace, arguments.design, arguments.revision)
            references = store.evidence(arguments.workspace, arguments.design, arguments.revision)
            result = {
                "status": record.status,
                "revision_sha256": record.revision_sha256,
                "record": record.model_dump(mode="json"),
                "references": [ref.model_dump(mode="json") for ref in references],
                "verification": {
                    kind: "REFERENCE_UNVERIFIED"
                    if any(ref.kind == kind for ref in references)
                    else "NOT_ASSESSED"
                    for kind in (
                        "simulation",
                        "measurement",
                        "erc",
                        "drc",
                        "lvs",
                        "pex",
                        "post_layout",
                    )
                },
            }
        elif action == "attach-reference":
            RevisionStore(arguments.store).attach(_load(arguments.reference, RevisionEvidence))
            result = {"status": "EXTERNAL_REFERENCE_RECORDED_UNVERIFIED"}
        else:
            result = assess_physical_capabilities(
                _load(arguments.inventory, PhysicalCapabilityInventory),
                assessed_at=datetime.now(UTC),
            ).model_dump(mode="json")
    except (OSError, ValueError, sqlite3.Error, RecursionError) as failure:
        reason = (
            failure.reason
            if isinstance(failure, RevisionRejected)
            else "local_input_or_store_invalid"
        )
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": reason,
                    "remote_contact": False,
                    "execution_authorized": False,
                },
                sort_keys=True,
            )
        )
        return 1
    result.update(remote_contact=False, execution_authorized=False, new_reservations=0)
    print(json.dumps(result, sort_keys=True))
    return 0
