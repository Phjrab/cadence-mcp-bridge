# WP-16 — ADE and sweep capability inventory v1

## Scope and evidence rule

This is a repository-only inventory, not a new Cadence probe, simulation, sweep, profile change,
MCP tool, or authorization. `docs/CURRENT_PHASE_PLAN.md` defines WP-16 as a capability matrix and
implementation-prerequisite checkpoint. Optional read-only remote probes require a separately
scoped approval; none were requested or performed. Historical observations are not claims about
today's remote state.

Evidence classes below are **R** (inspected in the current repository), **H** (dated real
observation recorded by an earlier WP), and **U** (unverified or absent). A repository file or a
synthetic test cannot upgrade an H/U item to a current remote PASS. WP-13's audit and WP-14's
blockers remain authoritative for the actual ADE profile; WP-15's adapter is a non-executable
public draft. A user-selected bias target discussed after WP-15 is not yet a versioned,
condition-verified scientific baseline and does not change the fixed profile.

## Fixed environment and execution modes

| Topic | Evidence | Classification and boundary |
| --- | --- | --- |
| Legacy stack | IC6.1.5.500.15, ADE L `state1`, Spectre 12.1.0.347.isr3 and gpdk090 v4.6 are recorded in `docs/VERIFIED_ENVIRONMENT.md` and the WP-13 audit. | H; current license/process availability is not inferred. |
| Snapshot-netlist mode | `src/cadence_mcp_bridge/profiles.py`, the fixed remote profile and `remote/bin/cadence-runner` register one actual NN transient profile with empty caller variables and outputs. The runner prepares a job-local wrapper for an already generated source. | R plus historical execution evidence. It does not load ADE state, regenerate a netlist or permit caller parameter override. |
| ADE read-only introspection | Repository runner 0.19.0 contains fixed `inspect-ade-profile`; `remote/py26/ade_profile_introspection.py` and its worker use one allowlisted profile and OA mode `r`. WP-13 recorded one successful real read-only probe on remote runner 0.18.0. | R + H. The last observed remote runner was 0.18.0; repository 0.19.0 has not been deployed or freshly verified remotely. No generic SKILL/OCEAN input is exposed. |
| ADE state-driven execution | No approved state load, current netlist generation, state-driven simulation or result extraction contract exists. | U; disabled. Historical ADE metadata inspection is not execution proof. |
| WP-14 names-only role discovery | Fixed repository-side helper exists, but deployment and invocation remain unapproved/unperformed. | R only; not a fresh VDD/VCM/load observation. |

## Capability matrix

| Capability | Fixed interface or evidence | Current result | Missing prerequisite before real use |
| --- | --- | --- | --- |
| Profile enumeration and submission | `cadence_list_profiles`, `cadence_get_profile`, `cadence_submit_profile`; runner `submit-profile` accepts a reviewed profile/corner. | R; actual profile is NN-only, `tran`-declared, with no caller-controlled variables or named outputs. | Reconcile actual ADE-state `dc` enabled / `tran` disabled drift and snapshot freshness before a new baseline claim. |
| Read-only ADE analysis/variable/model inspection | Fixed operator-side `inspect-ade-profile`, bounded ADE-state parsing, OA mode `r` open/close and before/after fingerprints. | R + H from WP-13. State1 historically reported `dc` enabled, `tran` disabled with stored stop `4m`, two bias values, NN, 27 C and no named outputs. | A new fixed, separately approved read-only probe and fresh protected fingerprints for current-state claims; no state save. |
| Parameter binding and override | Source snapshot references VBIASN/VBIASP but does not declare them; existing wrapper supplies compatibility values. `NoProfileVariables` rejects actual-profile caller variables. | H + R; no approved actual override or sweep axis. | Versioned WP-14 operating-condition/revision/freshness decision, exact binding, allowed units/default/range/step, immutable profile version and independent execution approval. |
| Snapshot provenance | WP-13 recorded stable profile/source/state hashes and source equality with the latest successful actual manifest; source timestamp was 1,512 seconds older than ADE-state metadata. | H; `SNAPSHOT_FRESHNESS_UNCONFIRMED` is not semantic equivalence. | Explicit snapshot policy and source/state semantic revision proof or separately approved regeneration. |
| Scalar/waveform extraction from actual PSF | `cadence_job_result` returns bounded completion/artifact metadata, not PSF samples. Fixed OCEAN headless smoke was historically demonstrated; synthetic ADC tools consume caller-provided arrays, not actual PSF. | R + H for metadata/headless smoke only; actual extraction U. | One fixed logical output ID, units, exact result binding, reviewed read-only parser/API, size cap, integrity checks and separately authorized probe. Do not infer an IC6.1.5 PSF/OCEAN API. |
| Process corners | Actual registry permits only case-preserved `NN`. Synthetic NN/FF/SS comparisons are local test contracts, not actual corner runs. | R; actual FF/SS or RC corners U. | Official model/corner bindings, provenance, license and fixed profile review; no defaults by analogy. |
| 1D/2D sweep and recovery | No sweep MCP endpoint, parent-child job model, point-plan registry or idempotent resume is present in the current runtime. | U; disabled. | Approved axis and deterministic points, plan hash, point/concurrency/time/resource caps, cancellation ownership, duplicate prevention and per-point provenance. |
| State-driven DC/AC/Noise/STB and campaigns | The fixed actual profile is transient snapshot mode only. | U; not implemented. | Independent fixed templates, legacy API proof, analysis/output contracts, licensed backend checks and bounded actual regression. |

## Existing limits versus unapproved future budgets

The present Windows configuration fixes one concurrent remote job, a 10-second SSH connect
timeout, a 120-second SSH operation timeout and a 65,536-byte transport output limit
(`src/cadence_mcp_bridge/config.py`). The actual profile fixes a 300-second Spectre worker
timeout; the fixture fixes 60 seconds (`src/cadence_mcp_bridge/profiles.py`). The runner's fixed
ADE introspection has a 120-second outer limit and a 90-second Virtuoso child limit. Result/log
responses have bounded metadata/tail contracts (`docs/SECURITY.md`). These are **current
single-operation limits**, not an approved sweep budget. Sweep point count, aggregate wall time,
retry count, disk/PSF allowance, license consumption and failure aggregation remain unset; no
fallback to guessed defaults is permitted.

## Fail-closed implementation prerequisites

1. Preserve PUBLIC repository policy, protected PDK/design/evidence secrecy, exact Git approval
   gates and `deployment_enabled=false`. Repository runner 0.19.0 is not deployment proof.
2. Resolve WP-14's scientific baseline and semantic source/ADE-state revision relationship.
   VDD, VCM, load condition, analysis choice and snapshot freshness remain unverified. A user
   value choice alone is not a circuit observation or simulation authorization.
3. For any new read-only legacy probe, first review a fixed target, allowlist, output schema,
   redaction, lock treatment, before/after fingerprints, timeout and single-use authority.
   No generic shell, SKILL, OCEAN, path, signal or property argument may be exposed.
4. Select one extraction backend only after a bounded, non-mutating, fixed-output capability
   test. Keep raw PSF, netlist, ADE state and PDK data outside public Git/MCP results.
5. Before parameterized or sweep execution, approve a new profile/version and exact variable,
   analysis, corner, output and budget contracts; test fixture-only negative cases first.
   A future real run needs separate authorization and current environment/preflight evidence.

## WP-16 acceptance and disposition

- PR #54's reviewed WP-15 head is merged into the branch base. This is an inventory of current
  repository code and dated WP-13 observations, not a fresh remote qualification.
- Snapshot, read-only introspection, extraction and sweep paths are distinguished without
  promoting a historical runner version or synthetic metric to actual capability.
- Fixed interfaces, current single-operation bounds, missing sweep budgets and fail-closed
  prerequisites are recorded. No speculative legacy API or PDK binding is asserted.
- No source/runtime/MCP/runner/profile/PDK/OA/ADE/design change, SSH/SCP, Cadence call,
  simulation, sweep, authorization, claim, lock, deployment or remote probe occurs in WP-16.
- Repository-only inventory may pass after documentation, static, test and security checks.
  Current remote capability and phase exit remain blocked pending separate gates.
