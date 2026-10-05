# GENERIC-SIM-01 result

## Objective and starting state

The user explicitly proceeded after the registered analysis API proposal.
Starting main: `962f6ca3db9381cbab3174f4ed8fbd3974a4efcd` (merged PR #106).
Branch: `feat/generic-sim-01`. This one phase covers implementation, tests,
documentation, bounded verification and permitted feature PR integration.
No prior WP/phase, FS improvement or optimization is restarted.

Feature PR: [#107](https://github.com/Phjrab/cadence-mcp-bridge/pull/107).
Initial reviewed head: `a427c051fa56d01b1c7d5c5f12a4588e4ea3da4d`.
The public scope is 23 files. GitHub inspection reported CLEAN/MERGEABLE,
no check runs, submitted reviews, comments or effective main branch rules.
Local gates and exact diff review supply verification; no GitHub CI pass is
claimed. Final head/checks/rules are rechecked before permitted integration.
Exact PR/head/main
and tree equality are recorded at integration in the private final checkpoint
and completion report. No state-sync PR, direct main push, force push or
protection bypass is used. The repository remains public; published v1.0.0,
package version and tag/release history are unchanged.

## Implemented capability

- Registry v3 adds bounded, exact design/variable-hash-bound analysis contracts
  and a compiled adapter identity. Existing v1/v2 schemas/projections remain
  compatible and configured older registries do not inherit analysis authority.
- Six closed MCP interfaces: list, plan, submit, status, bounded result and
  cancellation capability/state. Total tool count is 45. Private bindings,
  paths, scripts, arbitrary netlists/parameters and execution flags are excluded.
- The first compiled adapter reuses the reviewed fixed native reference DC/AC/
  trap TRAN path. An exact profile/variable/adapter match is required. Other
  registered designs remain blocked even if an operator recomputes hashes.
- Durable bounded local SQLite admission commits UUID/design/analysis/plan
  identity before transport. Retries, restarts and lost/uncertain outcomes look
  up only; they never blindly resubmit. Identity substitution and stale plans
  fail before transport. Package source need not be writable for this new state.
- Existing native transport, locking, private authority, fingerprints, effective
  conditions, disk floors, cumulative budgets, replay and extraction remain
  the execution boundary. Planning adds no reservation or runtime authority.
- Native live cancellation has no qualified route. Plans/results expose
  capability false; the endpoint reports terminal no-op or unsupported active
  cancellation and never signals a process or claims cancellation.

Fixed native compatibility is distinct from generic environment qualification.
The generic executable-permission blocker is preserved. Reference bias continuous
ranges remain unqualified; 320/702 mV remain a candidate and VDD 1 V a constraint.
No optimum, safe range, new source observation or numerical target is invented.
Measurements retain `spec_evaluation=not_evaluated`. See
[contract, workflow and recovery](GENERIC_ANALYSIS_V1.md).

## Verification

| Gate | Actual result |
| --- | --- |
| Frozen dependencies | `uv sync --all-groups --frozen` passed, 72 packages |
| Ruff | `ruff check src scripts tests` passed |
| Strict mypy | Passed, 28 source files |
| Focused analysis/variable/design/server/native tests | 245 passed, one actual OS symlink creation skipped; independent mocked rejection passed |
| Complete unit suite | 1,377 passed, one actual OS symlink creation skipped, 56 existing legacy datetime warnings |
| Existing security gate | Secret preflight and 18 security tests passed; locked dependency audit found no known vulnerabilities |
| Standard package lifecycle | Build/install/version/uninstall and cleanup passed using `UV_LINK_MODE=copy` |
| Actual subprocess stdio | 45 tools; exact metadata/variable compatibility; registered native admission/result and same-ID lookup; restart with the same journal recovers all three jobs |
| Actual Cadence regression | Legacy and registered native DC/AC/TRAN results equal preserved evidence; completed-ID replay succeeds; wrong-analysis, stale-plan and unqualified-adapter requests rejected |
| Cancellation | All actual jobs terminal: no-op/cancelled=false; mocked active jobs explicitly unsupported, no signal/cancel backend used |
| Protection/accounting | Fresh sealed original/ADE/PDK/reference/history guard passed; preserved job trees and cumulative counter equal before/after; prior checkpoints unchanged |

Unit evidence includes durable restart, unknown/lost responses, crash before
sending, conflicting operation identities, changed contracts, stale plans,
remote identity mismatch, compiled-adapter redirection denial, v1/v2 missing
contracts, concurrent journal instances, capacity/corruption/symlink rejection
without reset and closed MCP inputs. Bounds and exact earlier variable policies
retain their regression tests. No live new simulation or live cancellation is
claimed by mock tests or preserved-result E2E.

GitHub checks/reviews/rules are inspected before merge. Local gates do not imply
GitHub CI success when no check run exists.

## Corrections, resources and evidence

One of three corrections for this change is consumed. Initial static checking
inferred the heterogeneous CLI schema-version map as ModelMetaclass; an explicit
`type[RegistryBase]` map fixed strict typing, with initial formatting corrected.
The private initial static evidence and passing focused/full gate logs are
retained. All earlier correction histories remain unchanged.

New Spectre attempts: zero. Result reservation delta: zero. Remote deployment:
zero bytes. EDA/paid resource starts: zero. The generic E2E journal admits only
the three existing completed native IDs. Actual cumulative counts come from the
unchanged private shared ledger; prior public numeric entries are dated history.
No result ceiling, counter or removed elapsed limit is reset.

Private activation/audit, exclusive execution seal/verifier, local registry and
admission bytes, intent/result, test/security/package logs and final integration
checkpoint preserve resume evidence. Earlier phase verifiers/journals and source/
PDK/experimental evidence are untouched. No proprietary config, ledger, native
raw result or PDK content is published. No original/OA/ADE/installation mutation
or source promotion occurs.

## Operator benefit and remaining work

The reference operator can use registered logical design/analysis IDs and a
common plan/admission/status/result/recovery API rather than raw legacy revision/
operating-point selectors. Another user can register analysis descriptions and
inspect explicit blockers. Unqualified designs cannot redirect the reference
adapter or run by declaring their own qualification flags.

Execution on newly onboarded projects/environments still needs environment/PDK
qualification, adapter/effective-input proofs and reviewed variable authority.
Parameterized analyses, real-design generic sweeps, general measurements, native
live cancellation and full public onboarding remain unqualified/planned.
The current fixed reference adapter is not universal Cadence/PDK support.

Recommended next major phase: **PDK-ADAPTER-01** to implement the existing
technology abstraction and registered capability bindings before real-design
generic sweeps. Actual continuous bias ranges and new execution bindings are
still unqualified, so automatically starting such sweeps would lack prerequisites.
Ask once before another major phase; no next phase is activated here.
