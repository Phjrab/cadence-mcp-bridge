from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from mcp import Client
from pydantic import ValidationError
from test_native_diagnostics import native_payload

import cadence_mcp_bridge.__main__ as cli
import cadence_mcp_bridge.analysis_store as storage
from cadence_mcp_bridge.analyses import (
    AnalysisJobQuery,
    AnalysisSelection,
    AnalysisSubmission,
)
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.designs import (
    DesignAnalysisRegistry,
    DesignContractRegistry,
    DesignRegistry,
    load_design_registry,
    reference_analysis_registry,
    reference_contract_registry,
    reference_registry,
    register_designs,
)
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.native_diagnostics import (
    NativeDiagnosticRequest,
    NativeDiagnosticResult,
    NativeDiagnosticStatus,
)
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService
from cadence_mcp_bridge.variable_contracts import canonical_digest

DESIGN = "reference-differential-amplifier-tb2"


def selection(analysis: str = "dc") -> AnalysisSelection:
    return AnalysisSelection(design_id=DESIGN, analysis_id="native-" + analysis)


class NativeBackend:
    def __init__(self) -> None:
        self.submissions: list[NativeDiagnosticRequest] = []
        self.reads: list[tuple[UUID, str]] = []
        self.results: list[tuple[UUID, str]] = []
        self.fail_send = False
        self.fail_lookup = False
        self.running = False
        self.wrong_identity = False

    def status(self, job: UUID, analysis: str) -> NativeDiagnosticStatus:
        return NativeDiagnosticStatus(
            job_id=uuid4() if self.wrong_identity else job,
            analysis=cast(Any, analysis),
            state="running" if self.running else "succeeded",
            stage="simulating" if self.running else "succeeded",
            simulator="running" if self.running else "succeeded",
            extraction="not_started" if self.running else "succeeded",
            updated_at=datetime.now(UTC),
        )

    async def submit_native_diagnostic(
        self, request: NativeDiagnosticRequest
    ) -> NativeDiagnosticStatus:
        self.submissions.append(request)
        if self.fail_send:
            raise RemoteFailureError("Lost submission response")
        return self.status(UUID(request.operation_id), request.analysis)

    async def native_diagnostic_status(self, job_id: UUID, analysis: str) -> NativeDiagnosticStatus:
        self.reads.append((job_id, analysis))
        if self.fail_lookup:
            raise RemoteFailureError("Job state unavailable")
        return self.status(job_id, analysis)

    async def native_diagnostic_result(self, job_id: UUID, analysis: str) -> NativeDiagnosticResult:
        self.results.append((job_id, analysis))
        value = native_payload(analysis)
        value["job_id"] = str(uuid4() if self.wrong_identity else job_id)
        return NativeDiagnosticResult.model_validate(value)

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"Generic analysis widened backend route: {name}")


def service(backend: NativeBackend, journal: Path, registry: Any = None) -> CadenceService:
    return CadenceService(cast(CadenceBackend, backend), registry, analysis_journal=journal)


async def submission(
    svc: CadenceService, analysis: str = "dc", operation: str | None = None
) -> AnalysisSubmission:
    plan = await svc.plan_analysis(selection(analysis))
    return AnalysisSubmission(
        **selection(analysis).model_dump(),
        operation_id=operation or str(uuid4()),
        expected_plan_hash=plan.plan_hash,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("analysis", ["dc", "ac", "tran"])
async def test_registered_native_lifecycle_and_restart_replay(
    tmp_path: Path, analysis: str
) -> None:
    backend, journal = NativeBackend(), tmp_path / "admission.sqlite3"
    svc = service(backend, journal)
    listed = await svc.list_analyses(DESIGN)
    assert len(listed.analyses) == 3 and not journal.exists()
    plan = await svc.plan_analysis(selection(analysis))
    assert plan.dispatch_eligible and plan.qualification_scope == "fixed_native_compatibility"
    assert plan.cancellation_supported is False
    sent = await submission(svc, analysis)
    first = await svc.submit_analysis(sent)
    assert len(backend.submissions) == 1 and first.native.state == "succeeded"
    query = AnalysisJobQuery(**selection(analysis).model_dump(), operation_id=sent.operation_id)
    assert (await svc.analysis_status(query)).native.analysis == analysis
    result = await svc.analysis_result(query)
    assert result.native.analysis == analysis and result.spec_evaluation == "not_evaluated"
    assert len(result.model_dump_json().encode()) < 65_536
    restored = service(backend, journal)
    assert (await restored.submit_analysis(sent)).operation_id == sent.operation_id
    assert len(backend.submissions) == 1  # durable lookup across server restarts
    assert (await restored.cancel_analysis(query)).outcome == "terminal_noop"


@pytest.mark.asyncio
async def test_lost_send_unknown_and_recovery_never_resend(tmp_path: Path) -> None:
    backend, journal = NativeBackend(), tmp_path / "admission.sqlite3"
    svc = service(backend, journal)
    sent = await submission(svc)
    backend.fail_send = True
    with pytest.raises(RemoteFailureError):
        await svc.submit_analysis(sent)
    backend.fail_lookup = True
    with pytest.raises(RemoteFailureError):
        await service(backend, journal).submit_analysis(sent)
    backend.fail_lookup = False
    assert (await service(backend, journal).submit_analysis(sent)).native.state == "succeeded"
    assert len(backend.submissions) == 1


@pytest.mark.asyncio
async def test_crash_before_send_remains_lookup_only(tmp_path: Path) -> None:
    backend, journal = NativeBackend(), tmp_path / "admission.sqlite3"
    svc = service(backend, journal)
    sent = await submission(svc)
    AnalysisStore(journal).admit(
        sent.operation_id, sent.design_id, sent.analysis_id, sent.expected_plan_hash
    )
    backend.fail_lookup = True
    with pytest.raises(RemoteFailureError):
        await svc.submit_analysis(sent)
    assert backend.submissions == [] and len(backend.reads) == 1


@pytest.mark.asyncio
async def test_plan_and_job_identity_conflicts_fail_before_transport(tmp_path: Path) -> None:
    backend, journal = NativeBackend(), tmp_path / "admission.sqlite3"
    svc = service(backend, journal)
    sent = await submission(svc)
    with pytest.raises(InvalidInputError):
        await svc.submit_analysis(sent.model_copy(update={"expected_plan_hash": "0" * 64}))
    assert not journal.exists() and not backend.submissions
    await svc.submit_analysis(sent)
    conflicting = await submission(svc, "ac", sent.operation_id)
    with pytest.raises(InvalidInputError):
        await svc.submit_analysis(conflicting)
    with pytest.raises(InvalidInputError):
        await svc.analysis_result(
            AnalysisJobQuery(**selection("ac").model_dump(), operation_id=sent.operation_id)
        )
    assert len(backend.submissions) == 1 and backend.results == []
    with pytest.raises(InvalidInputError):
        await svc.analysis_status(
            AnalysisJobQuery(**selection().model_dump(), operation_id=str(uuid4()))
        )
    assert backend.reads == []


@pytest.mark.asyncio
async def test_contract_change_cannot_rebind_admitted_operation(tmp_path: Path) -> None:
    backend, journal = NativeBackend(), tmp_path / "admission.sqlite3"
    svc = service(backend, journal)
    sent = await submission(svc)
    await svc.submit_analysis(sent)
    value = reference_analysis_registry().model_dump(mode="json")
    value["analysis_contracts"][0]["analysis_id"] = "renamed-dc"
    changed = DesignAnalysisRegistry.model_validate_json(json.dumps(value))
    other = service(backend, journal, changed)
    renamed = AnalysisSelection(design_id=DESIGN, analysis_id="renamed-dc")
    new_plan = await other.plan_analysis(renamed)
    assert new_plan.plan_hash != sent.expected_plan_hash
    with pytest.raises(InvalidInputError):
        await other.submit_analysis(
            AnalysisSubmission(
                **renamed.model_dump(),
                operation_id=sent.operation_id,
                expected_plan_hash=new_plan.plan_hash,
            )
        )
    assert len(backend.submissions) == 1


@pytest.mark.asyncio
async def test_active_cancel_is_explicitly_unsupported_and_never_signals(tmp_path: Path) -> None:
    backend = NativeBackend()
    backend.running = True
    svc = service(backend, tmp_path / "admission.sqlite3")
    sent = await submission(svc)
    await svc.submit_analysis(sent)
    query = AnalysisJobQuery(**selection().model_dump(), operation_id=sent.operation_id)
    outcome = await svc.cancel_analysis(query)
    assert outcome.outcome == "unsupported_active_cancellation"
    assert outcome.cancelled is False and outcome.cancellation_supported is False
    assert outcome.status.native.state == "running" and len(backend.reads) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["submit", "status", "result"])
async def test_remote_identity_is_checked(tmp_path: Path, action: str) -> None:
    backend = NativeBackend()
    svc = service(backend, tmp_path / "admission.sqlite3")
    sent = await submission(svc)
    if action != "submit":
        await svc.submit_analysis(sent)
    backend.wrong_identity = True
    query = AnalysisJobQuery(**selection().model_dump(), operation_id=sent.operation_id)
    with pytest.raises(RemoteFailureError):
        if action == "submit":
            await svc.submit_analysis(sent)
        elif action == "status":
            await svc.analysis_status(query)
        else:
            await svc.analysis_result(query)


@pytest.mark.parametrize(
    "target,field,value",
    [
        ("profile", "environment_id", "other-lab"),
        ("profile", "pdk_adapter_id", "other-pdk"),
        ("profile", "work_copy_policy", "read_only"),
        ("profile", "design_id", "other-design"),
        ("contract", "analysis", "monte-carlo"),
        ("contract", "adapter_kind", "arbitrary-shell"),
        ("contract", "adapter_contract_sha256", "0" * 64),
        ("contract", "variable_set_sha256", None),
        ("contract", "input_policy", "unqualified"),
        ("contract", "path", "/private"),
        ("contract", "qualified", True),
    ],
)
def test_compiled_adapter_cannot_be_redirected(target: str, field: str, value: Any) -> None:
    payload = reference_analysis_registry().model_dump(mode="json")
    if target == "profile":
        payload["designs"][0][field] = value
        # Even recomputing local review hashes cannot qualify a different design/environment.
        profile = DesignRegistry.model_validate_json(
            json.dumps({"schema_version": 1, "designs": payload["designs"]})
        ).designs[0]
        payload["variable_sets"][0]["design_profile_sha256"] = canonical_digest(profile)
        if field == "design_id":
            payload["variable_sets"][0]["design_id"] = value
        variable_set = (
            reference_contract_registry()
            .variable_sets[0]
            .model_validate_json(json.dumps(payload["variable_sets"][0]))
        )
        for contract in payload["analysis_contracts"]:
            contract["design_id"] = profile.design_id
            contract["design_profile_sha256"] = canonical_digest(profile)
            contract["variable_set_sha256"] = canonical_digest(variable_set)
    else:
        payload["analysis_contracts"][0][field] = value
    with pytest.raises(ValidationError):
        DesignAnalysisRegistry.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "kind", ["duplicate-mode", "duplicate-id", "stale-profile", "stale-variable", "too-many"]
)
def test_analysis_registry_identity_and_bounds(kind: str) -> None:
    payload = reference_analysis_registry().model_dump(mode="json")
    if kind == "duplicate-mode":
        payload["analysis_contracts"].append(
            {**payload["analysis_contracts"][0], "analysis_id": "alias"}
        )
    elif kind == "duplicate-id":
        payload["analysis_contracts"][1]["analysis_id"] = "native-dc"
    elif kind == "stale-profile":
        payload["analysis_contracts"][0]["design_profile_sha256"] = "0" * 64
    elif kind == "stale-variable":
        payload["analysis_contracts"][0]["variable_set_sha256"] = "0" * 64
    else:
        payload["analysis_contracts"] *= 17
    with pytest.raises(ValidationError):
        DesignAnalysisRegistry.model_validate_json(json.dumps(payload))


@pytest.mark.asyncio
async def test_unqualified_and_v1_v2_designs_do_not_gain_native_execution(tmp_path: Path) -> None:
    backend = NativeBackend()
    for old in (reference_registry(), reference_contract_registry()):
        svc = service(backend, tmp_path / "no.sqlite3", old)
        assert (await svc.list_analyses(DESIGN)).analyses == ()
        with pytest.raises(InvalidInputError):
            await svc.plan_analysis(selection())
    payload = reference_analysis_registry().model_dump(mode="json")
    for contract in payload["analysis_contracts"]:
        contract.update(
            adapter_kind="unqualified", adapter_contract_sha256=None, input_policy="unqualified"
        )
    svc = service(
        backend,
        tmp_path / "no.sqlite3",
        DesignAnalysisRegistry.model_validate_json(json.dumps(payload)),
    )
    plan = await svc.plan_analysis(selection())
    assert plan.dispatch_eligible is False and plan.blocking_reason == "adapter_unqualified"
    with pytest.raises(InvalidInputError):
        await svc.submit_analysis(await submission(svc))
    assert not (tmp_path / "no.sqlite3").exists() and backend.submissions == []


def test_store_atomic_admission_across_instances_and_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "store.sqlite3"
    bootstrap = AnalysisStore(path)
    assert bootstrap.admit(str(uuid4()), DESIGN, "native-dc", "a" * 64)
    operation = str(uuid4())
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(
            pool.map(
                lambda _: AnalysisStore(path).admit(operation, DESIGN, "native-dc", "b" * 64),
                range(12),
            )
        )
    assert sum(outcomes) == 1
    monkeypatch.setattr(storage, "MAX_RECORDS", 2)
    with pytest.raises(ConfigurationError, match="capacity reached"):
        bootstrap.admit(str(uuid4()), DESIGN, "native-dc", "a" * 64)
    bootstrap.require(operation, DESIGN, "native-dc", "b" * 64)


@pytest.mark.parametrize("kind", ["corrupt", "wrong-application", "symlink", "oversized"])
def test_journal_invalidity_fails_closed_without_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    path = tmp_path / "sensitive.sqlite3"
    path.write_bytes(b"not a sqlite database")
    if kind == "wrong-application":
        path.write_bytes(b"")
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE unrelated (id INTEGER)")
    elif kind == "symlink":
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda item: item == path or original(item))
    elif kind == "oversized":
        monkeypatch.setattr(storage, "MAX_BYTES", 1)
    before = path.read_bytes()
    with pytest.raises(ConfigurationError, match="^Analysis journal is unavailable$"):
        AnalysisStore(path).admit(str(uuid4()), DESIGN, "native-dc", "a" * 64)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "value", [True, "../../escape", "00000000-0000-1000-8000-000000000000", "A" * 36]
)
def test_operation_identity_is_strict_uuid4(value: Any) -> None:
    with pytest.raises(ValidationError):
        AnalysisJobQuery(design_id=DESIGN, analysis_id="native-dc", operation_id=value)


@pytest.mark.asyncio
async def test_mcp_schema_closed_inputs_and_real_result_wrapper(tmp_path: Path) -> None:
    backend = NativeBackend()
    svc = service(backend, tmp_path / "store.sqlite3")
    async with Client(create_server(svc)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert len(tools) == 58
        for name in (
            "cadence_list_analyses",
            "cadence_plan_analysis",
            "cadence_submit_analysis",
            "cadence_analysis_status",
            "cadence_analysis_result",
            "cadence_cancel_analysis",
        ):
            assert tools[name].input_schema["additionalProperties"] is False
        planned = await client.call_tool(
            "cadence_plan_analysis", {"request": selection().model_dump(mode="json")}
        )
        assert not planned.is_error
        assert "MyDesignLib" not in str(planned.structured_content)
        sent = await submission(svc)
        args = {"submission": sent.model_dump(mode="json")}
        for key in ("values", "corner", "temperature", "path", "script", "netlist", "library"):
            assert (await client.call_tool("cadence_submit_analysis", {**args, key: True})).is_error
            nested = {"submission": {**args["submission"], key: True}}
            assert (await client.call_tool("cadence_submit_analysis", nested)).is_error
        assert backend.submissions == []
        assert not (await client.call_tool("cadence_submit_analysis", args)).is_error
        query = {
            "request": AnalysisJobQuery(
                **selection().model_dump(), operation_id=sent.operation_id
            ).model_dump(mode="json")
        }
        result = await client.call_tool("cadence_analysis_result", query)
        assert not result.is_error and result.structured_content["native"]["quality"] == "valid"
        cancelled = await client.call_tool("cadence_cancel_analysis", query)
        assert cancelled.structured_content["outcome"] == "terminal_noop"


def test_v1_v2_v3_schema_cli_and_exclusive_registration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = Path(__file__).resolve().parents[2]
    for version, model in (
        (1, DesignRegistry),
        (2, DesignContractRegistry),
        (3, DesignAnalysisRegistry),
    ):
        assert (
            json.loads((root / f"docs/schemas/design-registry-v{version}.schema.json").read_bytes())
            == model.model_json_schema()
        )
    assert cli.main(["design", "schema", "--schema-version", "3"]) == 0
    assert json.loads(capsys.readouterr().out) == DesignAnalysisRegistry.model_json_schema()
    source, output = tmp_path / "proposed.json", tmp_path / "snapshot.json"
    source.write_text(reference_analysis_registry().model_dump_json(), encoding="utf-8")
    assert register_designs(source, output)["execution_authorized"] is False
    assert source.read_bytes() == output.read_bytes()
    loaded, _ = load_design_registry(output)
    assert isinstance(loaded, DesignAnalysisRegistry)
    fictional, _ = load_design_registry(root / "docs/examples/design-registry-v3.fictional.json")
    assert all(c.adapter_kind == "unqualified" for c in fictional.analyses_for("example-amplifier"))
