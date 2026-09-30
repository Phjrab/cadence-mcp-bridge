# Cadence MCP Bridge

Restricted stdio MCP bridge from Windows to the registered `cadence-vm` Virtuoso,
Spectre, and OCEAN environment. The active operating policy is
[`docs/policy/PHASE_AUTONOMY_V1.md`](docs/policy/PHASE_AUTONOMY_V1.md), including
the elapsed-limit change. The original OA/ADE, PDK, and historical results are
protected. Feature changes go through a dedicated PR.

## Current MCP interface

The server has 35 typed tools. The original 22 lifecycle, discovery, profile,
synthetic measurement, and write-validation tools remain available. The
`actual-differential-amplifier-tb2-transient` profile keeps its existing v1
contract.

SIM-MCP-01 adds four tools for the pinned WP14 work-copy revision:

- `cadence_list_actual_diagnostics` lists the fixed DC and AC profiles.
- `cadence_submit_actual_diagnostic` accepts the exact revision
  `wp14-copied-netlist-v1`, operating point `candidate-320-702mv-v1`, one of
  `dc` or `ac`, and its matching logical output ID.
- `cadence_actual_diagnostic_status` reports job, simulator, and extraction
  state for a returned UUID and analysis.
- `cadence_actual_diagnostic_result` returns bounded voltage scalars or a
  70–72 point differential gain spectrum, fixed provenance, quality, and
  `spec_evaluation=not_evaluated`.

The operating point represents the already reviewed 320/702 mV candidate on a
job-local copy. VDD is fixed at 1.0 V and the pinned input common mode is 0.5 V.
The input has no arbitrary netlist, path, script, expression, corner, sweep, or
source mutation field. A valid diagnostic result confirms only this copied
revision under these conditions. It does not claim a design-specification PASS,
an original OA/ADE edit, or physical verification.

The VM implementation is the immutable `phase-campaign/sim-mcp-v2` helper under
the managed root. It checks protected fingerprints and job-local bindings before
and after execution, shares the single EDA lock, reserves the cumulative
Spectre and result budgets, and checks the disk floor. The earlier v1 helper and
its failed pre-simulation job remain in the private VM history. The v2 deployment
and MCP DC/AC comparison are recorded in private journals; the public phase
report contains only reviewed status.

SWEEP-MCP-01 adds `cadence_plan_sweep`, `cadence_submit_sweep`,
`cadence_sweep_status`, `cadence_sweep_result`, and `cadence_cancel_sweep`.
This first 1D version supports the registered RC fixture's numeric axes, up
to 16 points, a durable same-key resume, per-point effective-input checks,
and a cumulative Spectre/result budget guard. Its measurement is simulation
completion, not an analog scalar. An actual-circuit bias sweep is unavailable
until a single-axis binding and bounded voltage range are reviewed. The
historical three bias pairs vary two variables together. See
[`docs/SWEEP_MCP_01_RESULT_V1.md`](docs/SWEEP_MCP_01_RESULT_V1.md).

ADE-QUAL-01 qualified one current-source/ADE-state DC bundle through native
netlisting, verified effective conditions, Spectre and PSF scalar extraction.
The observed biases are 300/650 mV; the 320/702 mV candidate remains separate.
See [`docs/ADE_QUAL_01_RESULT_V1.md`](docs/ADE_QUAL_01_RESULT_V1.md) for scope,
resource use and remaining analysis gaps. Earlier failures remain preserved in
the checkpoint. That phase retained the then-existing 31 MCP tools. The fixed operator
`scripts/ade_qual.py status` reads the preserved result; execution requires exact
private delegation, correction, predecessor, integrity and replay guards.

NATIVE-MCP-01 adds `cadence_list_native_diagnostics`,
`cadence_submit_native_diagnostic`, `cadence_native_diagnostic_status` and
`cadence_native_diagnostic_result`. These execute a native ADE owned-state
DC/AC/trap TRAN bundle at the fixed 320/702 mV candidate, VDD 1 V, NN and 27 C.
The original saved state remains 300/650 mV. Submission accepts a caller UUID4,
one analysis, `revision_id=wp14-native-ade-v1` and
`operating_point_id=candidate-320-702mv-v1`; retain the ID on retry. Existing
IDs read status without another execution. Results contain DC scalars, AC
spectrum or a bounded TRAN summary and qualified provenance. No arbitrary
path, script, variable range or raw waveform is accepted. See
[`docs/NATIVE_MCP_01_RESULT_V1.md`](docs/NATIVE_MCP_01_RESULT_V1.md).

## Development and verification

```powershell
uv sync --all-groups
uv run ruff check src scripts tests
uv run mypy src
uv run pytest tests/unit
uv run python -m cadence_mcp_bridge serve
```

`scripts/deploy_sim_mcp_v2.py` deploys only the fixed reviewed helper after its
private delegation and policy binding are present. It is one-time and journaled.
`scripts/verify_sim_mcp_v2.py` exercises real MCP `tools/list` and `tools/call`
operations on the VM copy and compares new DC/AC observations with the prior
private candidate records. Its `run` mode reserves the verification; `resume`
continues only recorded job IDs. Neither command is a general simulation or
remote-shell interface. Use them only for a new reviewed deployment or recovery.

`scripts/deploy_native_mcp_v1.py` preserves an immutable deployment with the
existing shared budget ledger. `scripts/verify_native_mcp_v1.py run|resume`
uses an actual subprocess stdio client and a private journal. Resume reuses
the recorded request IDs and completed results. Windows SSH stdin is isolated
from the MCP pipe, and missing PROGRAMDATA is resolved from the OS known folder.

The project server registration is managed with
[`scripts/install-codex-mcp.ps1`](scripts/install-codex-mcp.ps1). Existing
installation guidance is in [`docs/CODEX_DESKTOP.md`](docs/CODEX_DESKTOP.md).
See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the transport and runner
boundaries, and [`docs/ADC_MEASUREMENT_CONTRACTS.md`](docs/ADC_MEASUREMENT_CONTRACTS.md)
for the separate synthetic ADC measurement contract.
