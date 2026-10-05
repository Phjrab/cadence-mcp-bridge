# GENERIC-ENV-01 result

## Objective and starting state

Implement configurable approved environment preflight around the existing safe
execution layer. Starting `origin/main`:
`407cc401e5027070a54da190537e1b7d91e80a11` (merged PR #103).
Branch: `feat/generic-env-01`. GitHub is public; v1.0.0 is actually published,
and the package remains 1.0.0. The one-phase user delegation governs integration
and the single continuation question. Historical WP/circuit work is preserved.

Feature PR: [#104](https://github.com/Phjrab/cadence-mcp-bridge/pull/104).
The initial pushed head is `1d2a7d3c2887c0cdddb07709b1fcab7515d40cec`.
The reviewed feature contains 18 public files. GitHub reported CLEAN/MERGEABLE,
no check runs, no submitted reviews and no effective branch rules; local gates
and exact public-diff review supply the verification evidence. Final PR/main
identity is verified at integration and retained in the private checkpoint and
completion report. No direct-main/force push or protection bypass is used.

## Implemented capability

- Frozen closed version-1 environment profiles, shared cross-field validation,
  exported JSON Schema and a fictional example.
- Operator CLI `doctor` and `environment schema/validate/prepare/qualify`.
  Private configuration can describe another approved host without source edits.
- A packaged Python-2.6-compatible Linux probe checks host/runtime identity,
  executable location/hash/version, protected/write-root separation, access
  permissions and disk floor. Only license-variable presence is observed.
- Fixed SSH operation, strict host keys, nonce/hash/freshness binding, bounded
  output/deadlines, no retry, executable pre/post checks and process-group cleanup.
- Environment preflight never authorizes execution, qualifies an analysis or
  resets/activates a budget ledger. There are no new MCP tools; all 35 existing
  interfaces and execution routes remain unchanged.

See [operator workflow](GENERIC_ENVIRONMENT_V1.md) and
[program decomposition](GENERIC_USER_ONBOARDING_PLAN_V1.md).

## Verification

| Gate | Actual result |
| --- | --- |
| Locked dependency sync | `uv sync --all-groups --frozen` passed |
| Ruff | `ruff check src scripts tests` passed |
| Strict mypy | `mypy src` passed, 23 source files |
| New environment plus existing CLI/config tests | 99 passed, including 87 environment cases |
| Complete unit suite | 1,188 passed, 56 existing legacy datetime warnings |
| Security gate | Secret preflight and 18 dedicated security tests passed; an OS-account pytest-cache warning does not affect assertions |
| Locked dependency audit | No known vulnerabilities |
| Build/install/version/uninstall | Existing `verify-package.ps1` passed in a separate environment |
| Actual guest compatibility | Bundled probe compiled on the unchanged Python 2.6 runtime without bytecode generation |
| Actual qualification command | Expected `blocked / executable_permissions` observed; it is not an environment qualification PASS |
| Actual subprocess MCP regression | 35 tools; preserved DC/AC/TRAN terminal status, bounded result equality and same-ID replay passed; three wrong-analysis requests rejected |
| Protected integrity and resource accounting | Fresh sealed source/ADE/PDK/reference/history checks passed before/after; existing counters and reservations equal |

The baseline full suite had 1,093 passes and eight fake-deployment failures.
Private diagnosis reproduced a Windows long-path read failure in the fake
process. Adding the extended local path prefix after fixture containment
restored all eight cases, without modifying immutable production deployers,
their assets or approval gates. The passing complete suite includes them.

## Corrections and preserved evidence

Three of three implementation corrections are consumed: strict boolean/literal
validation and local platform inspection; tuple/JSON field validation; and final
process-group/executable-drift/permission/rejection-code hardening. Earlier
versions and failures are retained privately. The final added Linux process
tests initially lacked a Windows mock for SIGKILL; the fixture was completed
without another production correction.

The first private deployment attempt stopped before SSH because a sandbox-owned
private local bundle was unreadable to the actual Windows operator. That bundle
was preserved, and identical approved bytes were exclusively prepared under the
operator account. No ACL was broadened, existing evidence overwritten or guest
OS/Cadence installation modified.

The private phase audit binds starting policy/document/source facts. Separate
deployment intent/result, qualification rejection and stdio comparison reports
preserve exact profiles, hashes, identities, result bytes and cumulative ledgers.
Public records contain only generic code, fictional configuration and reviewed
status. The resulting commit and integration belong to the containing feature
PR; remote main SHA is verified and recorded privately and in the completion
report, without a subsequent state-sync-only PR.

## Remote effects and resource use

Two fixed private files were added in a fresh environment version directory
under the approved managed root: 14,812 bytes in total. No new simulation/job ID
was generated. Spectre attempts added: zero. Result reservation increase: zero.
EDA work: no new job. Paid resources: zero. Existing elapsed-ceiling removal and
cumulative ledgers/correction histories remain. Original OA/ADE, PDK, prior
results and protected installation permissions were not changed.

The actual reference installation's executable permissions fail the new generic
gate. This is a verified fail-closed prerequisite failure, not a reason to relax
the gate or claim another installation works. Existing authorized native result
and replay routes remain reproducible.

## Residual limits and next phase

Another user can now validate their private environment description, prepare
reviewable immutable probe bytes and perform bounded preflight after reviewed
deployment. They cannot yet register or execute their own design through MCP.
Only Windows OpenSSH to Linux with the fixed system-Python operation is covered.
Successful positive preflight on another actual secure Cadence installation,
license checkout, analysis qualification, generic design/variable/measurement
and PDK bindings, full onboarding and public-release readiness remain pending.

Recommended next phase: **GENERIC-DESIGN-01**, with registered logical design IDs
and compatibility representation of the existing validated design. No arbitrary
path/library/cell or new range becomes executable through registration. Ask once
before starting it. No scientific target was invented; specification evaluation
remains `not_evaluated` and the 320/702 mV candidate/VDD constraint are unchanged.
