# Cadence MCP Bridge

A safe, bounded, client-independent MCP server connecting MCP clients to
registered Cadence Virtuoso/ADE/Spectre capabilities. The validated execution
reference is Windows to the registered `cadence-vm` environment. The active operating policy is
[`docs/policy/PHASE_AUTONOMY_V1.md`](docs/policy/PHASE_AUTONOMY_V1.md), including
the elapsed-limit change. The original OA/ADE, PDK, and historical results are
protected. Feature changes go through a dedicated PR.

## MCP clients

Codex and Claude Desktop launch the same server package over local stdio.
Codex TOML and Claude `mcpServers` JSON configuration are prepared and tested
through actual subprocess protocol clients. Independent JSON-RPC tests verify
initialization, typed schemas, calls/errors, concurrent read requests,
stdout integrity and EOF shutdown. This is `SERVER_PROTOCOL_QUALIFIED`.
Claude Desktop is `CLAUDE_CONFIG_PREPARED` / `CLAUDE_REAL_CLIENT_UNVERIFIED`;
configuration and SDK tests do not prove real desktop execution. The current
Codex adapter passes protocol regression; a fresh Codex application E2E is
also not claimed. See the [client matrix and exact manual procedure](docs/CLIENT_COMPATIBILITY_V1.md).
Other MCP hosts are `NOT_TESTED`. No public endpoint is required or provided.

## Generic onboarding status

ONBOARD-CLI-01 adds operator `verify` for joined environment/design/PDK contracts
and `client-config` for exclusively created private Codex TOML or stdio MCP JSON
fragments. Explicit registry/journal settings survive desktop-client startup;
`doctor` also validates configured registries. See the complete
[onboarding workflow](docs/ONBOARDING_CLI_V1.md). Local consistency and exported
configuration do not qualify a new execution route.

GENERIC-ENV-01 adds operator-owned environment descriptions and bounded
preflight qualification. Another operator can describe their host without
source edits. Existing MCP execution still uses the registered reference
environment; a valid profile does not authorize or route a simulation.

```powershell
uv sync --all-groups
uv run cadence-mcp-bridge doctor
uv run cadence-mcp-bridge environment schema
uv run cadence-mcp-bridge environment validate --profile C:\private\environment.json
uv run cadence-mcp-bridge environment prepare --profile C:\private\environment.json --output C:\private\new-bundle
# After separately reviewed deployment of the exact bundled probe:
uv run cadence-mcp-bridge environment qualify --profile C:\private\environment.json
```

GENERIC-DESIGN-01 adds local operator registration through
`design schema/validate/register` and `CADENCE_MCP_DESIGN_REGISTRY_PATH`.
MCP clients can list registered IDs and inspect logical design allowlists without
source edits. Private source/ADE bindings are excluded from MCP results.
Registration grants no generic execution or electrical-range qualification.
See [design workflow](docs/GENERIC_DESIGN_V1.md).

GENERIC-VAR-01 extends that registry to v2 with private variable bindings,
exact units/types, mutation policy and separately reviewed numeric contracts.
Two local read-only tools inspect contracts and check explicit decimal values.
Reference bias ranges remain unqualified; VDD=1 V remains a fixed constraint.
Numeric matching grants no execution or electrical safety certification.
See [variable workflow](docs/GENERIC_VARIABLES_V1.md).

GENERIC-SIM-01 adds registry v3 analysis contracts and six lifecycle interfaces.
The compiled adapter reuses the fixed reference native DC/AC/trap TRAN guards;
other designs remain unqualified. Durable local admission binds UUID/design/
analysis/plan; retries and server restarts look up the same job without blind
resubmission. Inputs have no parameter or voltage fields. Native live
cancellation is explicitly unsupported. See
[analysis workflow](docs/GENERIC_ANALYSIS_V1.md).

PDK-ADAPTER-01 implements runtime PDK registry v2 and operator
`pdk schema/validate/register` with `CADENCE_MCP_PDK_REGISTRY_PATH`. Three
read-only tools inspect capabilities and resolve design PDK/environment IDs.
Registered analysis dispatch requires the exact compiled reference; other PDKs
remain unqualified. Local gates and preserved-result stdio regression are verified.
See [PDK workflow](docs/PDK_ADAPTER_RUNTIME_V2.md)
and [phase result](docs/PDK_ADAPTER_01_RESULT_V1.md).

GENERIC-MEAS-01 adds registry v4 and three read-only measurement tools. They
bind exact analysis/definition hashes and reuse completed admitted native DC
voltage scalars, AC differential transfer spectrum and TRAN summary. Results
retain effective settings, fingerprints and source-result hashes; no new
simulation or extraction is triggered. Old registry versions remain valid.
Specifications stay `not_evaluated`; bandwidth, phase margin, power and OP
definitions are not added. See [measurement workflow](docs/GENERIC_MEASUREMENTS_V1.md).

GENERIC-SWEEP-01 prepares registered 1D contracts and local plans with two
read-only tools. It reuses v4 reviews/analyses/measurements, requires all fixed
values explicitly and bounds exact decimal sequences to 16 points. Numeric
eligibility is separate from execution: every point is NOT_RUN and all
parameterized physical execution remains unqualified. Reference bias ranges
remain unqualified. See [sweep preparation](docs/GENERIC_DESIGN_SWEEP_V1.md).

GENERIC-SWEEP-INTEGRATION-01 adds registry v5 and five lifecycle tools around the
existing engine: prepare, submit/resume, status, result and cancel. The only
parameterized adapter is the already reviewed passive RC fixture; explicit
registered contracts and numeric reviews cannot redirect it. Durable registered
admission uses the same operator journal and deterministic engine identities.
Real-design ranges remain unqualified. The explicit active cumulative result
ceiling is now 10 GiB, with 500 attempts and consumed counters retained; new
immutable native-v3/sweep-v2 guards enforce it. Historical versioned metadata
retains its earlier fields. See [registered lifecycle](docs/GENERIC_DESIGN_SWEEP_V2.md).

See [environment workflow](docs/GENERIC_ENVIRONMENT_V1.md),
[fictional profile](docs/examples/environment-v1.fictional.json),
[program plan](docs/GENERIC_USER_ONBOARDING_PLAN_V1.md) and
[phase evidence](docs/GENERIC_ENV_01_RESULT_V1.md).

STORAGE-MGMT-01 adds five typed storage tools for registered-group inventory,
classification, exact cleanup plans and default dry-run. Reference-host SDK
stdio verifies all six registered groups: protected history is aggregated by
analysis/retention, with snapshot-bound pages and descriptions. This reports
managed result roots, not whole-VM storage. Unsafe or over-limit inventories
remain partial lower bounds and cannot authorize deletion.
Historical replay/evidence results remain protected. Actual deletion requires
explicit human selection and a separate operator record; real-host deletion
has not been tested. Only separately reviewed isolated intermediate leaves can
be deleted; historical results remain protected. See the
[storage workflow](docs/SIMULATION_STORAGE_V1.md) and
[phase evidence](docs/STORAGE_MGMT_01_RESULT_V1.md).

| Status | Scope |
| --- | --- |
| Validated | Registered reference MCP lifecycle/native DC/AC/TRAN, fixed candidate, PVT and diagnostics; bounded fixture sweep; environment contract/CLI tests and actual permission rejection; design/variable introspection and numeric checking; registered fixed-native results/replay across stdio restart; v1/v2 compatibility; PDK catalog inspection/resolution and missing-adapter denial; joined onboarding contracts, exported TOML/JSON and actual stdio from those settings; registered native measurement values/provenance/restart; registered RC fixture lifecycle/replay/restart through the existing engine |
| Supported by contract | Operator-only environment preflight, joined local verification/client export, v1/v2/v3/v4/v5 design registration and logical PDK registry v2; bound numeric reviews; exact compiled reference and durable admission; bounded inputs and protected source; unqualified designs/PDKs cannot execute |
| Experimental | Successful preflight on other approved installations; positive observation paths have fixtures, but no second Cadence installation is qualified |
| Planned | Execution of newly onboarded environments/designs/PDKs through qualified physical bindings; parameterized real-design sweep, additional qualified measurements, native live cancellation and a new public release after remaining gates |

Arbitrary Cadence projects/PDKs, autonomous optimization, layout, DRC/LVS,
statistical simulation/Monte Carlo and multidimensional sweep are not generally
supported. Existing finite copied-circuit changes are specific reviewed
operations. No automatic circuit modification capability is added here.
License-variable presence does not prove entitlement; requested analyses remain
`unqualified` and a measurement without a user target remains `not_evaluated`.
The reference installation's writable Cadence executables fail the new generic
qualification check; its protected installation is unchanged.

GitHub v1.0.0 was published on 2026-08-31. Current main includes later capability
work. PUBLIC-RELEASE-01 adds installed-wheel CLI/stdio acceptance and a
[release readiness review](docs/RELEASE_READINESS_V1.md). The conditional next
version recommendation is v1.1.0 based on additive interfaces; package version
and release/tag history remain unchanged. The owner selected Apache-2.0 for
original bridge code; see the licensing boundary below. An exact candidate and
publication scope remain owner decisions; imported planning rights need review.

## License

Cadence MCP Bridge's original source code is licensed under the
[Apache License 2.0](LICENSE), with attribution in [NOTICE](NOTICE).
This grant does not license Cadence Virtuoso, Spectre, ADE, PDKs, MCP clients
or third-party products. Users must provide their authorized Cadence/PDK
environment and maintain every required external license and access permission.
Cadence software, license-server access and PDK files are not included.
The project is independent; no Cadence, OpenAI or Anthropic endorsement is claimed.

[THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md) records separate dependency terms
and `LEGAL_REVIEW_REQUIRED` for imported `docs/agent_plan/` material. Root
LICENSE does not relicense that material. Audited package distributions exclude
it; a blanket Apache claim for a full repository bundle is not approved.
See the [licensing audit](docs/LICENSING_AUDIT_V1.md).

## Current MCP interface

The server has 63 typed tools; all previous 58 full schemas are preserved.
The five new storage interfaces have verified reference-host inventory/plan/dry-run
behavior; actual Linux deletion is unverified. All clients receive the same guards.
`cadence_describe_design_sweep` and `cadence_plan_design_sweep` are local
contract/planning preparation only. Registered
`cadence_list_measurements`, `cadence_describe_measurement` and
`cadence_measurement_result` are read-only. `cadence_list_designs` and
`cadence_describe_design(design_id)` add read-only local introspection; generic physical profiles remain unqualified; the compiled registered RC fixture
has a bounded lifecycle adapter. The original 22
lifecycle, discovery, profile,
synthetic measurement, and write-validation tools remain available. The
`actual-differential-amplifier-tb2-transient` profile keeps its existing v1
contract.

`cadence_list_design_variables(design_id)` and
`cadence_check_variable_values(request)` add bounded local numeric inspection
and explicit-value checking. No default is filled or applied, no source value
is inferred, and no simulation or mutation is authorized by these checks.

`cadence_list_analyses`, `cadence_plan_analysis`, `cadence_submit_analysis`,
`cadence_analysis_status` and `cadence_analysis_result` expose registered
contracts and the guarded fixed-native compatibility lifecycle.
`cadence_cancel_analysis` reports capability/state only: terminal no-op or
unsupported active cancellation. All six reject unknown arguments and private
execution selectors. Generic environment qualification remains a separate gate.

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
