"""Validate the original paired OTA HNL outputs and their phase binding."""

import json
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, field_validator, model_validator

from cadence_mcp_bridge._shared_reservations import JOBS
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.pmos_default_service import _artifact, _require
from cadence_mcp_bridge.registered_mos_transport import _LIMIT, _Terminal
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel

_INPUT_LIMIT = 32_768
_Once = Annotated[int, Field(strict=True, ge=1, le=1)]
_Zero = Annotated[int, Field(strict=True, ge=0, le=0)]


class OtaHnlModeReceipt(VariableModel):
    analysis: Literal["ac", "dc"]
    operation_id: OperationId
    scope_sha256: Digest
    saved_receipt_sha256: Digest
    dut_revision_sha256: Digest
    testbench_revision_sha256: Digest
    isolated_bench_tree_sha256: Digest
    isolated_state_tree_sha256: Digest
    project_tree_sha256: Digest
    registered_inputs_sha256: Digest
    hnl_stdout_sha256: Digest
    netlist_sha256: Digest
    state_path: str
    project_path: str
    input_path: str
    enabled_analyses: tuple[Literal["ac", "dc"]]
    netlisted: StrictBool

    @field_validator("state_path", "project_path", "input_path")
    @classmethod
    def canonical_path(cls, raw: str) -> str:
        path = PurePosixPath(raw)
        if (
            not path.is_absolute()
            or path.anchor != "/"
            or path.as_posix() != raw
            or ".." in path.parts
            or len(raw) > 1024
            or not all(part.isascii() and part.isprintable() for part in path.parts)
        ):
            raise ValueError("OTA HNL path must be canonical POSIX")
        return raw

    @model_validator(mode="after")
    def owns_input(self) -> Self:
        if (
            not self.netlisted
            or PurePosixPath(self.project_path) not in PurePosixPath(self.input_path).parents
        ):
            raise ValueError("OTA HNL input must be inside its project")
        return self


class OtaDualHnlReceipt(VariableModel):
    schema_version: _Once
    ocean_invocations: _Once
    spectre: _Zero
    reservations: _Zero
    ac: OtaHnlModeReceipt
    dc: OtaHnlModeReceipt

    @model_validator(mode="after")
    def separate_modes(self) -> Self:
        ac_project, dc_project = map(PurePosixPath, (self.ac.project_path, self.dc.project_path))
        if (
            self.ac.analysis != "ac"
            or self.dc.analysis != "dc"
            or self.ac.enabled_analyses != ("ac",)
            or self.dc.enabled_analyses != ("dc",)
            or self.ac.state_path == self.dc.state_path
            or ac_project.is_relative_to(dc_project)
            or dc_project.is_relative_to(ac_project)
            or self.ac.netlist_sha256 == self.dc.netlist_sha256
            or self.ac.hnl_stdout_sha256 != self.dc.hnl_stdout_sha256
        ):
            raise ValueError("OTA HNL must use two distinct single-mode outputs")
        return self


class _OtaDualHnlTerminal(_Terminal):
    dc_input_base64: str
    diagnostics: OtaDualHnlReceipt


def read_ota_dual_hnl(
    raw: bytes, previous_receipt_sha256: str, *, managed_root: str
) -> tuple[_Terminal, OtaDualHnlReceipt, bytes, bytes]:
    """Read both original netlists from a captured terminal without normalizing either."""
    _closed_document(raw, max_bytes=_LIMIT)
    _require(_canonical(json.loads(raw)) == raw, "registered_ota_dual_hnl_terminal_shape")
    terminal = _OtaDualHnlTerminal.model_validate_json(raw)
    receipt, observed = terminal.diagnostics, terminal.readback
    operation = observed.operation_id
    selected = PurePosixPath(managed_root) / JOBS / operation / operation
    workcell = "Grel_" + operation.replace("-", "_")
    _require(
        all(
            (
                mode.operation_id,
                mode.scope_sha256,
                mode.saved_receipt_sha256,
                mode.dut_revision_sha256,
                mode.testbench_revision_sha256,
            )
            == (
                observed.operation_id,
                observed.scope_sha256,
                previous_receipt_sha256,
                observed.netlisted_revision_sha256,
                observed.netlisted_testbench_revision_sha256,
            )
            for mode in (receipt.ac, receipt.dc)
        )
        and receipt.ac.netlist_sha256 == observed.netlist_sha256
        and (observed.netlisted_revision_sha256, observed.netlisted_testbench_revision_sha256)
        == (observed.reopened.revision_sha256, observed.reopened.testbench_revision_sha256),
        "registered_ota_dual_hnl_binding",
    )
    for mode, capture, alias in (
        ("ac", receipt.ac, "MCP_GREL_Work"),
        ("dc", receipt.dc, "MCP_GREL_WorkDc"),
    ):
        root = selected / mode
        _require(
            capture.project_path == (root / "project").as_posix()
            and capture.state_path
            == (root / "state-root" / alias / workcell / "spectre/state1").as_posix(),
            "registered_ota_dual_hnl_mode_path",
        )
    ac_input = _artifact(terminal.input_base64, receipt.ac.netlist_sha256, _INPUT_LIMIT)
    dc_input = _artifact(terminal.dc_input_base64, receipt.dc.netlist_sha256, _INPUT_LIMIT)
    return (
        _Terminal(
            readback=observed,
            input_base64=terminal.input_base64,
            cdf_frame_base64=terminal.cdf_frame_base64,
        ),
        receipt,
        ac_input,
        dc_input,
    )
