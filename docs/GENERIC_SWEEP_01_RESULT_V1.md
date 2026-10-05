# GENERIC-SWEEP-01 registered contract/planning preparation result

## Scope and starting state

Starting main: `13e17f8f8604737a901aeaa5c6d907efc1996a63`, merged #113.
Branch: `feat/generic-sweep-01`. The user's next-step approval selects the
previous report's **registered 1D contract/planning preparation**, with
unqualified real-design execution blocked. This completes that selected phase;
it does not claim the broader physical sweep program is implemented.
The containing feature PR records integration; the exact ending SHA is verified
in a private post-merge checkpoint. No state-sync-only PR is created.

## Implementation

Two local read-only tools: `cadence_describe_design_sweep` and
`cadence_plan_design_sweep`. Inventory **51 → 53**. All preceding 51 full schemas
and registry v1/v2/v3/v4 schemas are exactly equal to the starting baseline.
The compiled planner reuses the existing registry v4, separate numeric reviews,
variable checks, PDK metadata, analysis plans and same-analysis measurements.
No additional operator configuration or model-controlled registration exists.

Plans require logical registered IDs, a current contract hash, explicit axis
unit and exactly all non-axis fixed values. Bounded decimal strings are
canonicalized; one axis, 1–16 unique explicit/linear points, exact endpoints and
independent initial conditions. Descending and canonical equivalent explicit/
linear requests produce equal plans, independent of the ambient decimal context.
No default or scientific range is inferred. Fixed checks appear once to bound
output. Stale/cross-analysis/unknown/injected inputs and oversized/inexact
sequences are rejected; known numeric denials remain explicit.

Local numeric matching and parameterized execution remain separate. Every
point is **NOT_RUN**, with no reservation, job ID, durable admission, measurement,
effective-input or cancellation claim. Even reviewed fixture numbers cannot
activate a physical adapter. `execution_authorized=false` and
`spec_evaluation=not_evaluated` are unconditional. Legacy fixture submission
cannot accept these plans. Current fixed native input/plan/admission/measurement
contracts and original execution code are unchanged.

## Verification

| Gate | Actual evidence |
| --- | --- |
| Frozen sync | Pass; 72 packages checked |
| Ruff / mypy | Pass; 34 source files |
| Focused planner/fixture/measurement/server/protocol | 76 passed; one cache-permission warning |
| Full unit | 1,534 passed; three OS symlink skips; 56 existing warnings plus one cache-permission warning |
| Security / locked dependency audit | 18 passed; one cache warning; no known locked vulnerabilities |
| Actual package | Audited wheel/sdist, isolated CLI install, fictional registry v4, three exported stdio formats, 53 tools/22 historical names, NOT_RUN/no admission and existing unqualified analysis/measurement denial, uninstall/import absence/cleanup pass |
| Exact compatibility | All previous 51 full tool schemas and four old registry schemas equal; source/native/analysis/measurement/fixture implementations unchanged except reviewed service/server additions |
| Actual preserved-job stdio | Codex/Claude exported SDK settings: blocked reference plans, explicit/linear equality, stale hash denial; three preserved native results/registered measurements equal, restart plans/measurements equal |
| Integrity | Fresh source/PDK/job/counter equality; existing journal bytes and prior private hashes equal |

The final package-script-only recheck passes four tests (one cache warning).
Persisted wheel/sdist contain 42/43 files, canonical Apache license/three notices,
exact curated source and zero unexpected/protected-pattern files. Imported
planning, private journals/results and external Cadence/PDK material are excluded.

SDK subprocess tests do not qualify named desktop applications. Claude remains
**CLAUDE_REAL_CLIENT_UNVERIFIED**; no fresh Codex application E2E is claimed.
Published fixtures are synthetic; actual circuit observations remain private.
See [request schema](schemas/design-sweep-request-v1.schema.json) and
[workflow](GENERIC_DESIGN_SWEEP_V1.md).

## Corrections and resources

Corrections: **2/3**. First fixed literal/constructor typing and JSON-array
adaptation without numeric coercion, plus a tiny-step test outside the accepted
decimal magnitude. Second isolated temporary package DLLs with uv copy installation.
The initial build/install/stdio/uninstall passed but final cleanup was denied.
`os.path.samefile` proved the temporary DLL and source-environment DLL were uv
hardlinks to the same file. Cleanup succeeded after source tests ended. A later
isolated build dependency installation encountered a Windows PE-resource access
denial; setting `UV_LINK_MODE=copy` for build isolation completed the same
canonical gate. No ACL, platform security or runtime guard was changed.
Failed/partial transcripts remain private; earlier attempts are not labeled PASS.

New Spectre attempts **0**, result reservation delta **0 bytes**, remote
deployment **0 bytes**. Existing cumulative counter: 62/500 attempts and
7,114,588,160 historically reserved bytes, retained without reset or inferred
new capacity. Removed elapsed ceiling stays absent. Original/PDK, historical
evidence, imported planning and old release/license files are preserved.
Package version remains 1.0.0; no release/tag/index publication is activated.

## Operator benefit and remaining prerequisites

Another operator can plan reviewed numeric 1D sequences against registered
contracts, obtain deterministic hashes/denials and distinguish missing numeric
authority from missing execution capability before any resource consumption.
Reference bias ranges remain unqualified; finite 320/702 mV candidate evidence
does not qualify a continuous range. VDD=1 V stays fixed. A plan is not simulation,
optimality, scientific range review or specification PASS.

Physical sweeps still need reviewed numeric bounds and parameterized environment/
design/PDK adapters with effective-input verification, durable resume/replay,
cumulative reservations/disk floor, cancellation and bounded measurements.
These runtime gates are prerequisites, not implemented planner features.
New physical environments/designs/PDKs remain unqualified; real desktop evidence
and imported planning rights remain public-release prerequisites. Original-code
Apache-2.0 and separate external Cadence/PDK/client/dependency terms remain.

Recommend **GENERIC-EXEC-PREP-01** to prepare registered physical binding/adapter
contracts around the proven fixed execution layer while rejecting unqualified
routes. Actual voltage-range decisions and execution accounting must remain
separate. Report and ask once before that phase; no automatic next phase follows.
