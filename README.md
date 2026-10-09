# Cadence MCP Bridge

GREL-01 adds an explicit operator runtime foundation. A bare CLI launch or
serve-operator with no settings returns SETUP_REQUIRED and cannot contact the
historical VM. Hash-bound environment/design/PDK contexts select the backend and
separate journals; unqualified operator execution remains blocked. Existing
explicit serve client fragments retain legacy compatibility. See the
[operator runtime workflow](docs/generic_release/RUNTIME_CONTEXT_V1.md).
The current feature validates bootstrap and new-circuit DC/AC/TRAN/Sweep on the
standard VM; clean artifact-only onboarding and actual Codex remain release gates.

A safe, bounded, client-independent MCP server connecting MCP clients to
registered Cadence Virtuoso/ADE/Spectre capabilities. The validated execution
reference is Windows to the registered `cadence-vm` environment. The active operating policy is
[`docs/policy/PHASE_AUTONOMY_V1.md`](docs/policy/PHASE_AUTONOMY_V1.md), including
the elapsed-limit change. The original OA/ADE, PDK, and historical results are
protected. Feature changes go through a dedicated PR.


## Generic native provider checkpoint

The current feature implements fixed authenticated admission and a common owned
OA/ADE/netlist/Spectre/result worker. The native-runtime schema/bundle CLI exports
a hash-bound runtime locally. Explicit operator stage/activate/inspect/revoke
CLI actions are implemented. In the current feature, two new standard-VM circuits
completed fresh DC/AC/TRAN with automatic extraction. Native DC3-point and a separate AC2-point Sweep and QA-only Specification
evaluation also passed on that VM. Exact installed onboarding and actual Codex
qualification remain incomplete; general release is blocked.
See [provider evidence and remaining gates](docs/generic_release/AUTHENTICATED_NATIVE_PROVIDER_V1.md).

## Coexisting operator runner

The installed package's runner bundle/export-installer/verify/preflight workflow
uses a dedicated `cadence-operator-runner`, `active-operator-runner.json` and
`operator-runner-revoked.json`. Existing `cadence-runner` and legacy state remain
preserved. On the guest, the exported helper supports explicit
`activate-operator MANAGED_ROOT MANIFEST_SHA256` and `deactivate-operator
MANAGED_ROOT MANIFEST_SHA256`. These actions need the existing trusted `run.lock`;
they never create a ledger or authorize simulations. Exact initial activation is
repeatable; an interrupted launcher-before-pointer write is recoverable.

Use the installed `runner preflight --bundle LOCAL_BUNDLE
--expected-plan-sha256 MANIFEST_SHA256` CLI. It invokes the fixed guest Python
interpreter with isolated startup flags; do not depend on a Windows-transferred
shebang. Preflight attests selected immutable package assets and the configured
VM, with analyses and license entitlement still unqualified.

The exported helper's `update-operator-preflight MANAGED_ROOT NEXT_SHA PREVIOUS_SHA`
is restricted to the known preflight runner, unchanged profile/probe/reservation
assets and a launcher revision. It shares the same physical lock, preserves old
versions and immutable transition receipts, and recovers a known interrupted pair.
It cannot update simulator worker code or replace the legacy launcher. Native
provider/migration, genuine fresh initialization and new-circuit execution remain
unfinished. See the [workflow](docs/generic_release/OPERATOR_RUNNER_COEXISTENCE_V1.md).

## Standard VM and operator trust repair

Release development targets the professor-provided CentOS/Cadence VM (or an
equivalent installation), its existing PDK and individual VMware use. Current
reference observations are CentOS6.5/i686, Virtuoso IC6.1.5.500.15 and
Spectre12.1.0.347.isr3. Each user registers their own SSH/address/key/account,
work/circuit/ADE paths, registry, journals and resource policy. Other Cadence/PDK/
OS/physical-host qualification is deferred. New-circuit execution remains a
required release gate; general release is still BLOCKED.

The installed CLI includes read-only `runner trust --profile environment.json
--output trust.private.json` and `runner repair-plan --profile environment.json
--output repair.private.json`. `runner export-repair-helper --output repair.py`
exports the fixed helper and SHA256 without remote contact. A plan grants no
permission. The VM's real operator/admin approves the exact list once and uses
their existing authentication; no import/server/doctor automatically changes it.
On this user's current VM, their2026-10-08 administrator delegation is that authority.

The helper takes explicit `inventory`, `apply` or `rollback` and bounded
private JSON on stdin. Inventory consumes the validated operator environment
profile. Apply/rollback accept only the complete profile-bound fixed-recipe plan from
inventory; arbitrary target lists are rejected before filesystem access. They consume
`{ "plan": <exact object from receipt>,
"expected_plan_sha256": <receipt hash>, "operator_authority": <actual human
scope reference> }`. Run `python -B repair.py apply < request.private.json` on
that guest only after preserving the exact private before-state and helper hash.
Redirect receipts privately. It shares the existing trusted resource lock and
never initializes/resets a budget ledger. Fresh-domain provisioning remains an
unfinished bootstrap gate. Use normal owner privileges when enough; otherwise
use the existing admin method for this helper, keeping MCP and Cadence non-root.

Only enumerated wrapper/32-bit/shared-library code paths and exact ancestors are
planned. No full-installation recursion, license/PDK/OA/ADE content change or
result/journal deletion. Apply removes only group/other writes, preserves owner
write/read/execute/traversal and hashes/owners, and rejects stale content/inodes,
hardlinks or special modes. Named/default ACL changes are recorded. It supports
idempotent apply, known chmod/ACL intermediate states and hash-bound rollback
using the original request. Preserve failed/partial evidence; do not replace an
unknown state with a new trusted baseline. Recheck environment and runner as the
ordinary guest user afterward. Complete dynamic dependency attestation and
new-job execution are separate gates. Full repository runbook:
[standard VM repair](docs/generic_release/ADMIN_REPAIR_V1.md).

## Generic ADE input preparation (native execution unqualified)

The installed package includes `cadence-mcp-bridge ade-input schema`, `compile`
and `verify-input`. These operator-only commands prepare private ADE L job inputs
and compare a bounded local Spectre input with explicit registered variables,
model sections, analysis settings and reviewed circuit/stimulus/load fingerprints.
See the [full workflow and native limitations](docs/generic_release/GENERIC_ADE_INPUTS_V1.md)
in the repository. They do not contact Cadence, reserve capacity or authorize jobs.

After configuring the existing hash-bound runtime and local operation plan,
create an operator-reviewed registration using `ade-input schema`. It requires
the exact design-profile/variable-set, protected source/state and reviewed static
input hashes, protected model references, and typed DC/AC/TRAN settings. The CLI
requires `--settings`, `--context`, `--grant`, `--expected-grant-sha256`,
`--request`, `--registration`, `--expected-registration-sha256`, `--operation-id`
and `--expected-plan-sha256`. Add `--output NEW_DIRECTORY` for `compile`, or
`--native-input INPUT_SCS` for `verify-input`. Use `--help` for shell-ready syntax.
The exclusive output contains `netlist.ocn`, `registration.json`, `manifest.json`;
existing output and failed partial artifacts are preserved. Do not run the script
until a trusted native provider has attested the owned copy, source/state/model
bytes, operator authority and the additional `execution_input_sha256` identity.

Only ADE L with `owned_copy_only` is supported by this compiler. Native API/copy
qualification remains pending. The initial verifier accepts a deliberately narrow
single-line ASCII Spectre dialect; unsupported formatting and scalar expressions
are rejected. Local input matches explicitly retain native-attestation false.
Actual new-circuit DC/AC/TRAN, automatic extraction, Sweep and clean-client
execution remain required for general release.

## Generic result reader preparation (native provenance unqualified)

The installed `cadence-mcp-bridge result-reader schema`, `compile` and
`project-frame` commands bind a fixed OCEAN reader to registered logical nodes,
source currents and the exact ADE registration, plan and execution-input identity.
No circuit names are compiled into the reader. DC returns node voltages and signed
power separately for supply, bias and stimulus sources; ground terminals use null.
AC gain uses measured complex differential output divided by measured complex
input at operator-selected actual sample frequencies, rather than assuming a1V
source or10Hz. Zero transfer has null dB/phase. TRAN returns min/max/first/last,
time-weighted trapezoidal mean, saved sample count and time-step bounds without
resampling. Missing/failed/truncated data is rejected, never specification FAIL.

Create an operator-reviewed registration from `result-reader schema`: specify
logical design/analysis/measurement IDs, canonical ADE and measurement-contract digests,
1–8 logical nodes with canonical private selectors, DC source inventory with
signed positive-terminal `/INSTANCE/PLUS` currents and logical voltage terminals,
or an AC differential transfer and1–16 positive increasing gain frequencies.
Voltage and current selectors must be disjoint. Node selectors ending in
`PLUS`/`MINUS` are unsupported because those spellings can denote branch currents.
Use the existing registry v4 or later measurement contract to bind the measurement
ID to the exact selected analysis. Its reader must remain `unqualified`; this
compiler cannot replace a qualified historical definition. Registry v3 allowlists
alone are insufficient. `measurement_contract_sha256` binds the canonical
registered contract. Selectors stay in operator artifacts; MCP has no path input.
`maximum_samples` is2–256 per waveform, with1536 aggregate sample rows. The minimum TRAN sample count from stop/maxstep, the declared AC logarithmic grid (including both endpoints conservatively) and requested gain-frequency count must fit that limit before compilation. Frequencies must remain distinct as binary floats; complete declared AC grids and both endpoints are required within a relative tolerance of1e-12. Exact sample equality takes precedence over tolerant matching, and one saved sample cannot satisfy multiple requested frequencies; oversized, unsampled requested frequencies
and unsupported selectors are refused. Native reader API/save inventory and
power scope still require trusted provider qualification.

Both commands require `--settings`, `--context`, `--plan`,
`--expected-plan-sha256`, `--ade-registration`, `--expected-ade-sha256`,
`--reader-registration`, `--expected-reader-sha256`, `--operation-id` and
`--execution-input-sha256`. The two registration digests use canonical model JSON;
the plan digest is the previously prepared plan identity. Use `--output NEW_DIR`
for `compile`, or `--frame LOCAL_FRAME` for `project-frame`; `--help` lists syntax.
Compile writes exclusive private `extract.ocn`, `registration.json`, `manifest.json`.
Projection always reports `native_provenance=NOT_ATTESTED` and
`spec_evaluation=not_evaluated`. These commands perform no remote execution,
reservation or admission. Manual frame validation is development tooling;
a production worker must automatically extract and attest its own terminal job.
Actual new-job extraction, Sweep and clean-app gates remain open.

## Release scope

The [current release readiness assessment](docs/RELEASE_READINESS_V3.md) separates
original-code wheel/sdist preparation, exact Git source archives, client evidence
and imported planning rights. Package metadata remains1.0.0; v1.1.0 is a conditional
recommendation only. Current85-tool SDK/protocol verification does not establish
complete latest desktop app qualification. No new tag/release/index publication
is authorized by passing local gates.

## MCP clients

[Actual Codex lifecycle investigation](docs/CLIENT_LIFECYCLE_QUAL_01.md) captured
initialize and all85 full wire tool schemas, matching the preserved SDK schemas.
Installed Codex product version26.1002.6548.0 and source files at child launch
were observed. Imported-memory identity and graceful app shutdown remain
unverified. The temporary observer was removed from configuration; direct launch
and26 read tools are restored. Preserved results and no-target evaluations match
after reconnect. No new simulation or deletion occurred.

[Earlier Codex Storage read qualification](docs/CLIENT_STORAGE_QUAL_01.md)
verifies actual summary, paginated inventory, descriptions and read-only plans
with26 filtered read tools (the prior22 plus four Storage reads). Existing
amplifier registries/journals remain selected; cleanup execution is excluded.
Full app schema/build/version/lifecycle qualification remains incomplete.

[Earlier Codex operator read checkpoint](docs/CLIENT_REAL_QUAL_CODEX_OPERATOR_03.md):
22 explicitly filtered read tools from the85-tool server; actual operator-v8
Gain/Power/DC/AC/TRAN and no-target specification reads match preserved results.
Separate finite-grid runtime, two preserved Sweeps and six no-target evaluation
facts also match historical results; the final profile selects this context.
The two operator contexts remain distinct. Full app schemas,
build identity and new lifecycle remain unverified. The previous
[default-registry85-name checkpoint](docs/CLIENT_REAL_QUAL_CODEX_CURRENT_02.md)
remains dated evidence.
Claude Desktop Code-tab reads and restart are already verified in the dated
[PR127 report](docs/validation/claude-desktop/20261006T0407Z/REPORT.md).


Codex and Claude Desktop launch the same server package over local stdio.
Codex TOML and Claude `mcpServers` JSON configuration are prepared and tested
through actual subprocess protocol clients. Independent JSON-RPC tests verify
initialization, typed schemas, calls/errors, concurrent read requests,
stdout integrity and EOF shutdown. This is `SERVER_PROTOCOL_QUALIFIED`.
Claude Desktop Code-tab actual calls verified existing-result reads and matching
re-reads after an app restart in the recorded 2026-10-06 run. The tested source
tree digest remains unknown; Desktop chat, full schemas/protocol, new jobs and
the blocked sweep read remain unverified. `CLAUDE_REAL_CLIENT_UNVERIFIED` is
retained for the complete qualification gate. Configuration and SDK tests alone
do not prove real desktop execution. The current
Codex adapter passes protocol regression. Historical Codex discovery and preserved
native DC reads were verified for the earlier69-tool server. The lifecycle report
above records the latest full schemas and product version; imported-memory
identity, graceful app shutdown and new execution remain unverified.
See the [client matrix and exact manual procedure](docs/CLIENT_COMPATIBILITY_V1.md).
Other MCP hosts are `NOT_TESTED`. No public endpoint is required or provided.

## Finite reference bias qualification

The operator-reviewed VBIASN319/320/321 mV grid has actual bounded DC/AC evidence
at fixed NN/27 C/VDD1 V/VBIASP702 mV. Existing variable tools can describe/check
an explicitly selected operator registry v2; numeric matching grants no execution.
The separately qualified compiled Sweep adapter now executes only this finite
grid through the existing engine, with signed DC supply-rail power and10 Hz AC
gain. It requires explicit operator registry selection and shared budget guards.
Continuous ranges and device ratings remain unqualified. See
[grid scope and measured results](docs/BIAS_RANGE_QUALIFICATION_V1.md).
The [Sweep guide](docs/REAL_AMPLIFIER_SWEEP_V1.md) documents the five additive tools,
replay, pending-only cancellation and exact configuration boundary. Source83
preserves old78 full schemas; current-source SDK execution is distinct from live
app qualification. No optimization, new target, deletion or publication follows.

## Real point specification evaluation

The [read-only specification adapter](docs/SPEC_REAL_EVALUATION_V1.md) binds
existing finite-grid gain/power results to the reused condition/comparison engine.
Its operator companion target catalog is empty: all six actual point facts remain
NOT_EVALUATED, with exact definitions, hashes and effective conditions preserved.
No target, value, script or path can be registered from MCP. Source85 preserves
all earlier83 full schemas; SDK qualification remains distinct from real app E2E.

## Reference step diagnostics

`cadence_slew_study_result` reads a fixed admitted reference step study. It reports
separate signed rise/fall20--80% secants, conditions, provenance and timestep/input
edge agreement. The unloaded open-loop output transition is nonlinear and reaches
saturated endpoints: it is PARTIALLY_QUALIFIED diagnostic evidence. Conventional
slew remains UNQUALIFIED; no specification PASS/FAIL or other-load/PVT claim follows.
It accepts registered IDs, an existing admission and its contract hash, with no
caller waveform/stimulus/path/script or simulation route. See the
[definition and read boundary](docs/ANALOG_SLEW_V1.md) and
[actual result](docs/ANALOG_SLEW_01_RESULT_V1.md). The step-phase checkpoint exposed77 tools,
with all prior76 schemas preserved; the live app catalog is a separate checkpoint.

## Running-server configuration

`cadence_runtime_info` reports the connected bridge version, loaded design/PDK
catalog versions/counts/semantic hashes and default/operator journal selection.
It is local and accepts no inputs; it returns no private paths or file contents.
Use it after client registration to detect a default v4 catalog instead of an
intended operator v7 catalog. It does not check journal health, license entitlement,
environment qualification or execution authority. See the
[runtime observation guide](docs/RUNTIME_CONFIGURATION_V1.md).

Operator registry v8 uses `cadence_runtime_info_v2` (observation version 2).
The original observation retains its v1-v7 schema and returns a bounded v2
handoff for v8; it never reports a false catalog version.

The historical Claude deferral was lifted for the documented Code-tab read and
restart run. Its limited evidence is preserved in the
[Claude report](docs/validation/claude-desktop/20261006T0407Z/REPORT.md);
`CLAUDE_REAL_CLIENT_UNVERIFIED` remains for the untested scope.

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
Built-in reference ranges remain unqualified; the separate reviewed finite grid
is documented above. VDD=1 V remains a fixed constraint.
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
definitions were outside that phase. See [measurement workflow](docs/GENERIC_MEASUREMENTS_V1.md).

ANALOG-MEAS-01 adds operator registry v6 and three read-only derived measurement
tools. It reuses registered, admitted native evidence and keeps every old schema
and execution identity unchanged. Differential gain is measured at **10 Hz**;
bandwidth is a **sampled-reference 3.0 dB crossing estimate** with its observed
bracket and conditions. It is not a DC, unity-gain or closed-loop qualification.
Phase margin, power, offset and slew rate in the original analog v1 remain
**UNQUALIFIED** with explicit
requirements; no numerical value is invented. No new simulation or PSF extraction
is triggered, and specifications remain `not_evaluated`.
See [analog definitions and workflow](docs/ANALOG_MEASUREMENTS_V1.md).

ANALOG-POWER-01 adds two read-only interfaces with a separate `dc-supply-power-v1`
definition. One preserved reference native DC result is **QUALIFIED** for signed
VDD/VSS rail power; bias/input-source contributions are reported separately.
Six-source inventory, effective voltage, signed current, independent OP-field
comparison and source/frame provenance are verified. It reuses operator v6/v7
registration and existing admission. MCP never initiates extraction or simulation.
Other designs/jobs remain unqualified; original v7 goals keep their original bindings.
See [power scope and workflow](docs/ANALOG_POWER_V1.md).

MEAS-CONTRACT-02 connects that existing power reader to a bounded
`cadence_measurement_catalog` and operator registry v8 power goals.
`cadence_evaluate_specification_v2` reuses the existing conditions/comparator
and returns the versioned signed-power result without changing old definitions.
The reference has no numerical target and remains NOT_EVALUATED. No additional
simulation or wider scientific qualification follows. See
[measurement binding workflow](docs/MEASUREMENT_BINDINGS_V2.md).

SPEC-CONTRACT-01 adds operator registry v7 and three read-only specification
tools. Goals bind exact measurement definitions, units and effective conditions.
Only QUALIFIED results at matching conditions can yield PASS/FAIL; partial or
unqualified measurements and mismatches remain explicit. **No reference numerical
goal exists**, so the reference list is empty and `not_evaluated` remains intact.
Targets and measurement facts cannot be supplied through MCP. See
[specification contracts](docs/SPECIFICATION_CONTRACTS_V1.md).

GENERIC-SWEEP-01 prepares registered 1D contracts and local plans with two
read-only tools. It reuses v4 reviews/analyses/measurements, requires all fixed
values explicitly and bounds exact decimal sequences to 16 points. Numeric
eligibility is separate from execution: every point is NOT_RUN and all
parameterized physical execution is not authorized by that preparation contract.
Built-in continuous bias ranges remain unqualified. See
[sweep preparation](docs/GENERIC_DESIGN_SWEEP_V1.md) and the separate finite adapter above.

GENERIC-SWEEP-INTEGRATION-01 adds registry v5 and five lifecycle tools around the
existing engine: prepare, submit/resume, status, result and cancel. The only
parameterized adapter in that interface is the reviewed passive RC fixture; explicit
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
| Supported by contract | Operator-only environment preflight, joined local verification/client export, v1–v8 design registration and logical PDK registry v2; bound numeric reviews; exact compiled reference and durable admission; bounded inputs and protected source; unqualified designs/PDKs cannot execute |
| Experimental | Successful preflight on other approved installations; positive observation paths have fixtures, but no second Cadence installation is qualified |
| Planned | Execution of newly onboarded environments/designs/PDKs through qualified physical bindings; parameterized real-design sweep, additional qualified measurements, native live cancellation and a new public release after remaining gates |

Arbitrary Cadence projects/PDKs, autonomous optimization, layout, DRC/LVS,
statistical simulation/Monte Carlo and multidimensional sweep are not generally
supported. Existing finite copied-circuit changes are specific reviewed
operations. No automatic circuit modification capability is added here.
License-variable presence does not prove entitlement; newly registered physical
execution routes remain `unqualified` until separately reviewed. A measurement
without a user target remains `not_evaluated`.
The reference installation's writable Cadence executables fail the new generic
qualification check; its protected installation is unchanged.

GitHub v1.0.0 was published on 2026-08-31. Current main includes later capability
work. PUBLIC-RELEASE-01 adds installed-wheel CLI/stdio acceptance and a
[release readiness reassessment](docs/RELEASE_READINESS_V2.md). The conditional next
version recommendation is v1.1.0 based on additive interfaces; package version
and release/tag history remain unchanged. The owner selected Apache-2.0 for
original bridge code; see the licensing boundary below. An exact candidate and
publication scope remain owner decisions; imported planning rights need review.
The curated original-code package is **CONDITIONALLY_READY**. A new significant
GitHub release at current main is **NOT_READY**: real client qualification and
full application and exact distribution/candidate gates remain unresolved. Imported
rights remain under review for clone/history material. See the archive boundary
below. A local contract PASS never grants
publication; run `uv run python scripts/verify-release-readiness.py` from a reviewed checkout.
Actual Codex discovery and a preserved native DC result read are now
[verified](docs/CLIENT_REAL_QUAL_CODEX_READS_V1.md). Claude and full application
qualification remain pending; see the [client handoff](docs/CLIENT_REAL_QUAL_01_CHECKPOINT_V1.md).

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

## Source archives and preserved planning

New Git archives at commits containing `docs/.gitattributes` exclude
`docs/agent_plan/`. Exact local and GitHub snapshots require member/content
inspection before `IMPORT_EXCLUDED_VERIFIED` is claimed; see the
[export boundary and evidence](docs/AGENT_PLAN_EXPORT_BOUNDARY_V1.md).
This does not remove the directory from web browsing, clone, fork, Git bundle,
old commits or existing downloads. Its rights remain `LEGAL_REVIEW_REQUIRED`;
a new tag/release remains `PUBLICATION_NOT_AUTHORIZED`.

To install from an inspected source ZIP/tar.gz, unpack it into a new directory,
then run `uv sync --all-groups`, `uv run cadence-mcp-bridge doctor` and the
[onboarding workflow](docs/ONBOARDING_CLI_V1.md). Bridge installation supplies
no Cadence, PDK, licenses or execution qualification. The archive retains
source, dependency lock, examples, schemas, tests and package verification.
`scripts/verify-package.ps1` checks the build/distribution and isolated installed
CLI/stdio without the imported planning helper. See its distinct archive
installation evidence in the export-boundary document.

Historical imported-package checks and ICF planning require a reviewed clone
and their exact preserved inputs. The old `docs/agent_plan/tools/verify_package.py`
is deliberately absent from source archives; it is not an installation step.
Do not skip its missing-input failure or call it PASS. The Git-based secret
preflight also requires a checkout: run it there before export, then compare
archive contents to that exact commit. A ZIP directory is not a full Git
operator checkout.

## Current MCP interface

The server has 76 typed tools; all previous 75 full schemas are preserved.
`cadence_bandwidth_study_result` adds an admission-bound, read-only fixed-reference
grid study. Actual 50/100 points-per-decade refinements observe a final estimate
of489.007 kHz and successive change0.02475%; the original10 Hz/3.0 dB definition
and PARTIALLY_QUALIFIED status remain. This is empirical convergence without an
absolute error bound or specification PASS. See
[scope and API](docs/BANDWIDTH_QUALIFICATION_V1.md) and
[reference evidence](docs/BANDWIDTH_QUAL_02_RESULT_V1.md).
Three additions provide measurement discovery, v2 specification evaluation and
v2 runtime observation. The separate power readers retain their original schemas.
One additive local `cadence_runtime_info` interface inspects loaded configuration.
Three additive read-only specification interfaces list, describe and evaluate
operator-owned exact-condition goals. No goal is invented for the reference.
Three new read-only analog interfaces expose operator-registered definitions and
qualified 10 Hz gain / partial bandwidth estimates; the original other analog v1
metrics stay unqualified.
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
completion, not an analog scalar. That legacy interface cannot run amplifier
bias sweeps; the separately versioned finite adapter above provides that binding. The
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

Reference Phase Margin applicability has been audited against the actual pinned
circuit and installed STB help. The current open-loop testbench has no defined
application feedback loop, so Phase Margin remains UNQUALIFIED/null. The fixed
operator audit preserves this distinction; it adds no MCP execution route. See
[reference loop assessment and future qualification](docs/ANALOG_PHASE_MARGIN_V1.md).

```powershell
uv sync --all-groups
uv run ruff check src scripts tests
uv run mypy src
uv run python -m pytest tests/unit
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

Nominal input-nulling Offset has a bounded supplemental diagnostic reader; it
remains partially qualified and is not physical femtovolt accuracy or a
specification result. See [Offset study](docs/ANALOG_OFFSET_V1.md).

### Native Storage qualification

The existing Storage interface has a bounded native qualification: one newly
generated8KiB synthetic payload was deleted only after exact user selection and
separate operator consent. Inventory, plan/dry-run, direct audit, retained control
and historical artifacts, same-operation replay and SDK server restart were verified.
This does not qualify arbitrary historical result deletion or whole-VM cleanup.
Actual Codex-app summary/list/describe/plan reads are now
[verified in their bounded scope](docs/CLIENT_STORAGE_QUAL_01.md).
Actual app cleanup execution remains NOT_RUN; SDK/native evidence is separate.
See [STORAGE-REAL-QUAL-01 result](docs/STORAGE_REAL_QUAL_01_RESULT_V1.md).

## Operator runner content preparation (GREL-02)

The installed package contains original fixed Python2.6-compatible runner,
launcher, installer and the existing environment probe. No Cadence/PDK files or
private deployment scripts are bundled. Content installation alone does not
qualify the environment or permit DC/AC/TRAN.

~~~powershell
cadence-mcp-bridge runner bundle --profile environment.json --output fresh-bundle
cadence-mcp-bridge runner export-installer --output install-runner.py
cadence-mcp-bridge runner install --bundle fresh-bundle --target existing-private-root --expected-plan-sha256 REVIEWED_HASH
cadence-mcp-bridge runner verify --target existing-private-root --expected-plan-sha256 REVIEWED_HASH
~~~

Review the generated manifest hash, byte inventory, private profile and target.
The bundle contains operator paths and is private. New bundles use schema2 and
include the hash-bound internal shared-counter accounting asset. Schema1 history
remains verifiable. The asset has no public command and requires a production
provider's independent operator/job/resource attestation; it cannot authorize
execution or initialize/reset a budget. The target must be a reviewed
existing owned directory with no links and safe permissions. The hash directory
is exclusive: partial installs and drift remain preserved and blocked, never
overwritten or silently retried. Successful repeated install verifies all bytes.

For a Linux host, an operator can transfer the exact bundle and exported installer
through their strict-host-key SSH/SCP configuration into an approved staging area,
verify the exported installer SHA256, then run the fixed installer with
/usr/bin/python -B install-runner.py install BUNDLE TARGET REVIEWED_HASH.
Use verify TARGET REVIEWED_HASH before activate TARGET REVIEWED_HASH. The fixed
launcher accepts identity HASH or preflight HASH NONCE only; simulation is not enabled.
Activation refuses an existing launcher/active marker, preserving legacy installs.
A dedicated registered managed root is required for a fresh operator installation.
Deactivation is append-only: deactivate TARGET REVIEWED_HASH retains installed
versions and the original activation record. Updating an existing active pointer
requires the reviewed lifecycle migration gate; it cannot override a running job.

Registration, content verification, native environment preflight, runner trust,
analysis qualification and operation authority are different gates. An
executable_permissions rejection requires administrator investigation of the
actual executable and its dependency/ancestor trust; no ignore switch, wrapper
exception or vendor chmod is performed by the bridge. License configuration is
not license checkout or entitlement evidence. Current generic execution remains
blocked until those gates and reusable authority are implemented and verified.

The installed runner trust diagnostic is read-only:
~~~powershell
cadence-mcp-bridge runner trust --profile environment.json --output fresh-private-trust-report.json
~~~
Only the private exclusive report includes affected executable/ancestor paths.
The console returns bounded per-tool counts; it never chmods or grants execution.
Metadata diagnosis does not attest transitive dependencies or license entitlement.
An administrator must inspect the installation and dependent code before treating
it as trusted; changing only a wrapper's permissions is insufficient.

After reviewed activation, request the exact current installed preflight:
~~~powershell
cadence-mcp-bridge runner preflight --bundle fresh-bundle --expected-plan-sha256 REVIEWED_HASH
~~~
The CLI binds the private profile, fixed package bytes, selected manifest and
fresh nonce, and reuses the existing environment qualifier. Successful preflight
is identity/runtime/binary/root/disk evidence; analysis, license entitlement,
physical ledger provisioning and operation authority remain separate gates.


### Local reusable authority and operation plans

Installed operator CLI now supplies closed authority/request schemas and local
immutable planning:

~~~powershell
cadence-mcp-bridge operation grant-schema
cadence-mcp-bridge operation request-schema
cadence-mcp-bridge operation check-authority --settings C:/operator/runtime.json --context lab-a --grant C:/operator/grant.json --expected-grant-sha256 <reviewed-raw-file-sha256>
cadence-mcp-bridge operation plan --settings C:/operator/runtime.json --context lab-a --grant C:/operator/grant.json --expected-grant-sha256 <reviewed-raw-file-sha256> --request C:/operator/request.json
~~~

The operator supplies their reviewed private record; these commands never write
or sign approval. The form binds runner/domain/existing ledger/catalogs and
logical design/analysis/numeric scope, ceilings and lifetime. The request names a
registered design/analysis and all explicit values with units and reservation size.
Both registered numeric contracts and narrower authority regions are enforced;
there is no inherited ADE default. Plans contain canonical numbers and logical
IDs/hashes, not private bindings. A matching local form reports remote accounting
and human attestation as unassessed and always execution_authorized=false.
Native dispatch, pending cancellation and extraction recovery remain unavailable
until trusted runner, actual shared ledger, generic adapter and operator
confirmation are implemented and qualified. A form is not an execution grant.

Operator journals must live outside site-packages in preexisting selected state
parents. Installing, same-version reinstalling or uninstalling the package does
not migrate/reset them. Bootstrap staging preserves the selected runner;
active-pointer replacement, live migration and N-to-N+1/downgrade qualification
are not supported at this checkpoint. Retain originals, results, replay, partial
candidates, unresolved jobs, audit and cumulative reservations. Fresh operator
Storage/deletion remains disabled; phase approval is not result deletion consent.

Public verification uses disposable GitHub-hosted Windows/Python3.12 machines,
locked dependencies, SHA-pinned actions, read-only token permission and a pinned
uv binary checksum. It runs synthetic lint/type/unit/security/contract/curated
build/isolated SDK+bootstrap+preservation checks without Cadence/PDK/license/SSH
secrets. Actual native acceptance and actual-app new execution remain distinct
BLOCKED/NOT_RUN gates. See CONTRIBUTING.md for commands and SECURITY.md for
sanitized reports. General release and publication remain blocked.


Native standalone runner installation refuses a TARGET that differs from the
hash-verified profile's paths.managed_root before creating any directory. A
mistyped target cannot create a runtime tree in an original/source/vendor root.
Windows runner install is local content staging only and reports
WINDOWS_LOCAL_CONTENT_STAGING_ONLY/native_installation_verified=false. The
standalone Linux installer has no staging command; Linux installation still
requires the exact managed root and positive native trust is a separate gate.


Native install, activate and deactivate all require TARGET to equal the managed
root in the hash-verified bundled profile before any write. A hash-valid copied
runtime at another root cannot authorize activation or revocation there. Windows
content staging does not permit standalone lifecycle activation of that tree.

Existing standard-VM installations: see [retained-ledger migration](docs/generic_release/EXISTING_DOMAIN_MIGRATION_V1.md). This explicit operator CLI preserves accounting and does not authorize simulation.

New standard-VM operator initialization and existing-domain reuse: [setup workflow](docs/generic_release/FRESH_DOMAIN_V1.md). Fixed staging is explicit, and existing history never becomes a fresh budget.


### Standard-VM operator confirmation

The generic-release target is the professor-provided CentOS/Cadence VM and its
existing PDK, used in individual VMware installations. SSH/account/workspace,
circuit/ADE, result/journal and resource policy bindings belong to each operator.
Current generic native execution remains incomplete; historical result readers
and synthetic qualification do not prove new-circuit execution.

The installed operator-only `operator-authority` CLI exports/stages a fixed helper
and explicitly records, inspects or revokes authenticated OS-operator confirmation.
It preserves the existing accounting domain and never launches EDA or reserves
capacity. No model-facing grant writer or administrator shell is added. Import,
server startup and doctor perform no provisioning. See the current
[confirmation procedure and qualification boundary](docs/generic_release/OPERATOR_CONFIRMATION_V1.md)
and [domain setup procedure](docs/generic_release/FRESH_DOMAIN_V1.md).


### Explicit native operator execution (implementation checkpoint)

For the professor-provided CentOS/Cadence VM and its existing PDK, native operations
are selected by the operator context. The package contains the fixed runner, setup
helper and schemas; no Cadence/PDK binary is bundled. Actual new-circuit execution
qualification remains incomplete. Other Cadence versions, PDKs and host machines
have not been verified.

Use `native-runtime schema` and `native-runtime bundle` for the
registered source cell, saved ADE state, variables and DC/AC/TRAN reader. Place
source/state copies in the registered workspace, preserve the originals, and use
measured hashes rather than example placeholders. The bundle receipt supplies
`manifest_sha256` and `provider_binding`; save the latter as operator JSON with
its exact byte SHA256. Select that manifest as the context's `runner_sha256`.
Staging an immutable bundle is separate from activation and simulation consent:
`native-runtime stage|activate|inspect|revoke --help` shows the fixed setup interface.
Administrator repair, when needed, requires the owner of that VM; routine server
and EDA execution run as the ordinary user.

To enable native MCP operations, add all four fields to that context:
`native_provider_binding` (absolute local JSON path), `native_provider_sha256`,
`operator_grant` (absolute local grant path) and `operator_grant_sha256`.
The grant must come from the actual operator's authorized scope and be separately
confirmed through the OS-operator workflow. Configuration alone cannot grant
execution. Existing installations reuse their real resource ledger and replay
history; a new local journal does not create a fresh remote budget.

Start the exported `serve-operator` configuration. These five conditional tools
are available only with the explicit binding:
`cadence_plan_operation`, `cadence_submit_operation`, `cadence_operation_status`,
`cadence_operation_result`, `cadence_cancel_pending_operation`.
Plan every registered numeric value and result reservation explicitly. Submit
with one UUID4 and the returned exact plan SHA. Repeat that same ID for a lost
reply or after restart: retries only reconcile, never resend. Pending cancellation
cannot stop an active simulator or refund consumed reservations.

The operator CLI offers the same fixed lifecycle through
`operation submit|reconcile|result|cancel-pending --help`.
Results require a successful terminal receipt and unchanged input, reader, frame
and PSF; only registered bounded measurements are returned. No simulation or
extraction rerun occurs during retrieval. Goals remain `not_evaluated` unless a
separate applicable specification is registered. Legacy/no-native-binding mode
retains its original 85 tool schemas. The additional tool contract is recorded in
`docs/contracts/MCP_NATIVE_OPERATIONS_V1_SNAPSHOT.json` in the source repository.


For a new registered source, prepare an owned QA/source copy in Cadence and use
Check and Save after changing schematic stimuli. Keep a valid ADE L state and
register the numeric variables that the common renderer sets after loading it;
do not invent internal saved-state variable component structures. DC support
requires a true operating-point state, without a component/parameter sweep.
Register new source/state/static-input hashes after reviewing any source edit.
Model includes must use canonical installed paths and separately attested hashes.

The standard-VM HNL verifier supports bounded terminal backslash continuations and
only the known relative sensitivity/DC/TRAN output defaults. It rejects incomplete
statements, arbitrary output paths, duplicate or unsupported inherited analysis
options, and a saved DC sweep even if its statement hash matches. Spectre runs in
its owned work directory. Two new QA sources have generated and verified all three
analysis inputs on the actual standard VM; fresh simulator/results/clean-client
qualification remains pending. See
[native input qualification](docs/generic_release/NATIVE_NETLIST_QUALIFICATION_V1.md).


## Native runtime update and current preflight

The fixed operator CLI supports an explicit immutable runtime update:
`native-runtime update --bundle NEW_BUNDLE --expected-manifest-sha256 NEW_SHA
--previous-manifest-sha256 OLD_SHA --operator-authority ACTUAL_AUTHORITY_REFERENCE`.
Stage the new exact package bundle first. Existing runtime/history/grants/jobs,
local journals and cumulative ledger remain preserved; mismatching predecessors
or a live worker reject. Partial updates resume only from matching durable records;
repeating a completed update changes0 files. This does not renew a spent budget.

`native-runtime preflight --bundle NEW_BUNDLE --expected-manifest-sha256 NEW_SHA`
is a read-only current-profile/package/environment/domain/accounting check. It
verifies fresh nonce/time, executable bindings and disk floors without changing
files or granting execution. The old profile-bound `environment qualify` is kept
for its exact original deployment. Normal users run the MCP server and Cadence;
setup helpers remain explicit operator actions. See
[native update and actual six-analysis evidence](docs/generic_release/NATIVE_UPDATE_AND_RESULTS_V1.md).

Registered native1D coordination and QA result/specification evidence, operator CLI
commands, replay and output bounds are documented in the
[native Sweep/spec workflow](docs/generic_release/NATIVE_SWEEP_SPEC_V1.md).
