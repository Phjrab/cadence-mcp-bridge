# STORAGE-MGMT-01 implementation plan v1

Status: **PLANNED**, not an implemented MCP capability. The user's simulation
storage directive extends the program at the completed #115 sweep boundary.
Starting repository truth is main `3f7bd81131e40f7781351b18e7ec824f362a5ef7`.
Schedule this phase before ANALOG-MEAS-01, then SPEC-CONTRACT-01. Preserve the
completed sweep, all previous qualification and the one major-phase transition
choice. This planning record authorizes no historical-result deletion.

## Repository audit and reuse

The server currently has **58 tools**. There is no storage-management MCP API.
The fixed operator `cleanup-dry-run` command in `remote/bin/cadence-runner`
delegates to `remote/py26/result_json.py::command_retention`. It accepts no caller
path, examines canonical UUID job directories, skips symlinks and uses terminal
state plus a fixed 30-day age. It is only a legacy retention report: age and even
an `unknown` state are not evidence of deletion safety. Do not turn this report
into a delete operation or treat its candidates as qualified new candidates.

Use existing service/backend separation, strict typed contracts, closed runner
operations, shared EDA lock, durable native/sweep identities and operator-owned
configuration. No second simulator, arbitrary filesystem API or alternative
accounting system is needed.

| Storage group | Repository evidence | Default treatment |
| --- | --- | --- |
| Legacy smoke/profile jobs: raw results, netlist, logs, status and manifests | `remote/lib/run-smoke-job.sh`, `run-profile-job.sh` and fixed jobs-root runner | Replay/evidence dependencies must be resolved; age alone never permits deletion |
| Native DC/AC/TRAN job work, PSF, project copies, extraction results and logs | `remote/phase-campaign/native-mcp-v1/{run.sh,helper.py}`; v3 retains the v1 job domain | REPLAY_REQUIRED or EVIDENCE_REQUIRED; never delete the whole job directory |
| Sweep children and reservation markers | `sweeps.py`, `sweep_service.py`, `sweep-mcp-v2/budget.py` | Preserve deterministic child IDs, manifests, effective inputs and reservation records |
| Shared cumulative ledger | `sim-mcp-v2` counter used by native-v3/sweep-v2 | PROTECTED; consumed attempts/reservations never decrease |
| Qualification, PVT, scientific and controlled-write/recovery evidence | Versioned phase helpers, protected fingerprints and existing private checkpoints | EVIDENCE_REQUIRED; preserve all prior acceptance and rollback evidence |
| Immutable deployment versions, manifests and activation evidence | Versioned phase deployment helpers | PROTECTED; not a result cleanup root |
| Local native analysis journal, sweep journal and registered admissions | `analysis_store.py`, `design_sweep_service.py`, operator journal configuration | REPLAY_REQUIRED; metadata/audit must survive cleanup and restart |
| Local private authority, journals, failure transcripts and checkpoints | Existing private operator state | PROTECTED; outside remote simulation cleanup scope |
| Source OA/ADE, PDK, vendor installation, licenses and credentials | Existing source/PDK/security policies | Excluded from traversal and deletion |
| Unidentified temporary, cache or generated objects | No authoritative disposable contract yet | PROTECTED_OR_UNKNOWN |

This is a source audit, not a fresh filesystem inventory or a measured byte total.
Actual roots, dependencies, free space and artifact sizes must be observed through
a reviewed fixed metadata probe during implementation. No private paths are
needed in normal MCP responses. Operator configuration owns registered roots;
runtime callers receive opaque group/artifact/job IDs only.

## Bounded inventory and classification

Implement a versioned artifact snapshot with opaque artifact/group identity,
job/analysis/design association where reliable, creation/last-use availability,
logical bytes, allocated bytes where available, retention class, replay/evidence/
active dependencies, extraction state, deletion status/reason and provenance.
Do not substitute file mtime for creation or last use. Unknown metadata stays
unknown. A qualified measurement does not remove replay or evidence obligations.

Classification is deterministic and server-owned. Protected/active/replay/evidence
or unresolved dependencies take priority over candidate age. Keep unknown jobs,
unknown states, missing/corrupt records, protected reference inputs, hardlinked
objects and symlink/reparse objects protected. A client cannot relabel retention.
An operator-owned, reviewed disposable-artifact contract must establish the
specific leaf/group boundary before any existing output can be a delete candidate.
It is acceptable for a truthful inventory to contain zero deletable artifacts.

Bound entry counts, traversal depth, metadata read/hash work, top-N and page size.
Never read raw PDK/netlist/PSF content into responses. Interrupted or truncated
inventory must report partial coverage rather than a complete total. Pagination
must bind a stable snapshot and reject drift. Report managed versus excluded or
uninspected roots explicitly; do not claim whole-disk usage from registered roots.

Summary includes disjoint classification totals, counts, bounded per-analysis
breakdown, largest artifacts and oldest *qualified* candidates. Separate logical
file size, actual allocated space and cumulative reserved bytes. Include bounded
filesystem-free and disk-floor status from the same registered filesystem.

## Minimal proposed MCP surface

Names below are proposals, not current tools; finalize against implementation.

- `cadence_storage_summary`: bounded snapshot totals and disk/resource status.
- `cadence_list_storage_artifacts`: snapshot-bound pagination and closed filters.
- `cadence_describe_storage_artifact`: one opaque artifact's metadata/dependencies.
- `cadence_plan_storage_cleanup`: concrete selected IDs, exclusions, fingerprints,
  plan ID/hash, estimated reclaim and replay/evidence impacts; no deletion.
- `cadence_execute_storage_cleanup`: exact plan/hash/selected IDs, durable operation
  identity and dry-run or separately approved execution; bounded per-item outcome.

No path, glob, shell, expression, script or client-controlled retention fields.
Reuse an equivalent existing interface if the implementation audit discovers one.
Plans do not silently resolve a category into authorization to delete it.

## User selection and server authorization

Default workflow: INSPECT -> REPORT -> USER SELECTS -> VALIDATE -> DELETE -> VERIFY.
Routine development delegation is not destructive user intent. The report makes
the exact IDs, affected bytes and exclusions reviewable before asking for selection.

The server must not accept a client-supplied `approved=true` as proof of consent.
Reuse or implement an operator-owned approval record outside model-controlled
registration, bound to the plan hash, exact selected IDs, fingerprints and cleanup
operation identity. Deletion requires that record; absent, changed or consumed
authority fails closed. A model cannot mint its own deletion capability.
Dry-run, inventory and planning need no destructive grant and cannot delete.
Implementation tests use synthetic disposable fixtures with separate test authority;
historical simulation data is not an E2E delete fixture.

## Execution, race protection and recovery

1. Validate strict schema, plan/hash, selection subset, unique IDs and operation ID.
2. Acquire existing shared EDA protection and cleanup serialization; inspect every
   active/queued/extracting/cancelling/recovering job and relevant sweep state.
3. Revalidate current registry, protected exclusions, dependency records, exact
   fingerprints and parent/device/inode identity before any destructive action.
4. Reject path traversal, symlink/junction/reparse traversal, hardlink ambiguity,
   root replacement, plan drift and ID substitution. Establish safe platform
   deletion primitives for CentOS/Python 2.6 before qualifying deletion; plain
   check-then-recursive-delete is insufficient for the plan/delete race.
5. Persist a small durable intent/audit before deleting only exact registered
   objects. Never recursively remove an entire job/workspace as a shortcut.
6. Verify each outcome, persist tombstone/audit, and report blocked/partial/unknown
   states. Restart and duplicate operation IDs must not blind-retry uncertain work.
7. Report logical removed bytes and observed disk-space delta separately. Do not
   label estimated size as actual reclaimed physical bytes; filesystem changes
   and delayed open-file reclamation can affect free space.

Audit retains IDs, time, pre-delete classification, expected/actual byte semantics,
plan/operation identity and per-item verification, without private paths or bulky
copies. Preserve resource-accounting and replay/admission metadata. A result that
must remain retrievable is REPLAY_REQUIRED, not disposable. Tombstones do not
retroactively authorize breaking previous replay guarantees.

## Resources, qualification and tests

Keep 500 attempts, 10 GiB cumulative reservation, one active EDA job, 128 MiB
per-job reservation and max(2 GiB, 10%) disk floor. The elapsed ceiling remains
removed. Latest #115 checkpoint records 62 attempts and 7,114,588,160 reserved
bytes; refresh current counters at execution, never reset or refund them on delete.
Physical deletion increases available space only; cumulative accounting is history.
No new Spectre simulation is needed merely to qualify storage APIs.

Test protected/active/replay/evidence/unknown rejection; hash, stale-plan and ID
substitution; traversal, symlinks, reparse and root/inode races; bounded inventory;
dry-run; duplicate execution, partial failure and crash recovery; concurrent
inventory/delete and restart; actual versus expected reclaim; malformed MCP
requests; shared disk/reservation accounting. Run canonical lint/type/full-unit,
security/dependency, distribution/install and actual stdio gates. Compare all 58
previous full tool schemas and reuse preserved native/sweep results for regression.

Actual reference-host E2E initially covers bounded inventory/plan/dry-run and
protected-object equality. A real deletion E2E requires a concrete synthetic,
owned disposable fixture and explicit selected-delete authority. If safe platform
primitives or an artifact's disposable status cannot be proved, report that scope
as BLOCKED/UNQUALIFIED; do not fake a delete PASS or discard protected evidence.

## Phase boundary and deferred work

Complete one reviewed feature PR and permitted merge; verify remote SHA. Record
implementation states, tests/E2E, budgets, failures/corrections, inventory coverage,
classification reasons, remaining blockers and protected integrity. Then report
and ask once before ANALOG-MEAS-01.

STORAGE-COMPACT-01 is separate future work. Compression, cloud archival, migration,
automatic cleanup and destructive measurement-based compaction are not activated.
No license, release, scientific range/specification or security boundary changes.
