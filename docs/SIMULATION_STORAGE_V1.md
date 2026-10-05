# Bounded simulation storage management v1

STORAGE-MGMT-01 adds five client-independent typed tools to the same MCP server:
summary, paginated artifact metadata, one artifact description, cleanup planning,
and dry-run/selected execution. This document describes the implemented contracts;
actual reference-host qualification is recorded separately in the phase result.
No general filesystem, shell, path, expression or glob interface is exposed.

## Inventory scope and meaning

The initial compiled reference adapter registers six logical result groups:
legacy jobs, native jobs, diagnostic jobs, PVT jobs, headroom jobs and isolated
disposable intermediates. Root bindings remain operator/execution configuration,
not MCP inputs. Other phase roots, source OA/ADE, PDK, vendor installations and
local private state are excluded from traversal. The report is not whole-VM usage.
Native/sweep admission journals, accounting ledgers, prior evidence, deployments
and rollback evidence remain protected. The existing fixed 30-day operator
cleanup report is unchanged and does not confer deletion eligibility.

Snapshots expose opaque `sa-` identities and logical/allocated bytes, job/analysis
associations when established, classification, dependencies and fingerprints.
Creation and last-use times stay null when unavailable; file mtime is not used to
invent these facts. No oldest-candidate claim is made without reliable timestamps.
Logical totals partition by retention and analysis. The largest list is limited to
five; pages to 20; each snapshot to 64 groups/artifacts. Historical artifacts are
aggregated by registered root, analysis and retention, with protected membership
fingerprints and job counts; they are never individual cleanup candidates.
Isolated disposable leaves retain individual IDs. Each of the six fixed roots
has an 8,192-node and depth-16 limit, so a snapshot visits at most 49,152 nodes.
STORAGE_SCAN_V2.json binds this scan contract; the original global-node policy
and its partial-coverage evidence remain historical. Traversal skips no unsafe
object silently: unsupported/link/corrupt/bounded
work becomes protected/partial. Payload hashing is bounded to 64 MiB per snapshot.
Incomplete totals are lower bounds and cannot authorize cleanup.
The snapshot/summary reports `scan_nodes` and closed `group_coverage_reason`
codes. A group description reports aggregate bytes/dependencies/counts without
expanding thousands of protected job records or returning their paths.

Filesystem-free telemetry is separate from snapshot identity because unrelated
free-space changes are not artifact identity changes. Artifact, dependency, active
state and cumulative-ledger changes invalidate the snapshot/plan. Pagination is
snapshot-bound. Unknown analyses remain unknown; no scientific result is inferred.

## Calls

1. `cadence_storage_summary()` obtains the snapshot ID, totals, classes, coverage,
   disk-floor status and cumulative reservation telemetry.
2. `cadence_list_storage_artifacts(request)` uses that snapshot ID, offset and
   page limit. `cadence_describe_storage_artifact(request)` also takes one opaque ID.
3. `cadence_plan_storage_cleanup(request)` selects 1-16 exact IDs from the snapshot.
   It returns a stable `sc-` plan ID/hash, eligible IDs, protected exclusions,
   fingerprints and estimated logical reclaim. It deletes nothing.
4. Report that concrete plan and obtain explicit human selection. A category such
   as "all TRAN" must first resolve to exact artifact IDs and a reviewable plan.
5. `cadence_execute_storage_cleanup(request)` takes the original selection/plan,
   chosen subset, canonical version-4 operation UUID and `dry_run` (default true).
   Dry-run reports eligibility and expected bytes without an audit or data mutation.

Unknown, active, replay/evidence-required or protected artifacts cannot be selected
for deletion. Historical simulation results default to replay/evidence protection.
Measurement extraction or age alone is insufficient. No automatic cleanup occurs
before simulation or when the disk floor is low.

## Eligible isolated intermediates and operator review

The initial deletable class is deliberately narrow: one regular `payload.bin` in
an isolated, operator-owned private UUID intermediate container. It is not an
entire simulation job, raw PSF directory, work-copy project or existing evidence
tree. The payload must have one link, match exact metadata/content fingerprints,
and fall within the bounded hash-work contract. Its container has no extra leaf.
Source/PDK/replay/evidence roots cannot be redirected into this class.

An independent operator registration records analysis type, completed extraction,
exact fingerprints and reviewed absence of replay/evidence/active dependencies.
All of these assertions require actual operator evidence. Registration is outside
MCP and cannot relabel a protected historical group. Do not copy/move protected
results into the intermediate area merely to evade a dependency or a fingerprint.
New work that produces a genuinely disposable intermediate may adopt this contract;
automatic conversion of existing simulation results is not implemented.

`scripts/storage_operator.py register --record <private-record> --review <private-review>`
publishes only that closed record after a separate dependency review. The private
review must equal `operator_review=explicit-reviewed-disposable-intermediate` plus
the canonical registration SHA. The tool does not create, copy or delete payloads.
Use a new UUID for a new artifact, never overwrite consumed identity or registration.

## Exact deletion consent

General development delegation is not deletion consent. Runtime callers cannot
submit `approved=true`, write approval files or supply paths. A separate
operator-owned mode-600 record in a mode-700 directory must bind the original
cleanup request SHA, exact plan SHA, chosen IDs and operation UUID to explicit
human selection. The server compares these facts under the shared EDA lock.

After actual user selection, the operator publishes the exact reviewed record:

```powershell
uv run python scripts/storage_operator.py approve --record <private-selected-request> --review <private-explicit-user-selection-record>
```

The selection record contains contract version 1, canonical request SHA, plan SHA,
chosen IDs and `user_selection=explicit-selected-items`; the request sets
`dry_run=false`. Neither the agent's own proposal nor a phase authorization is
evidence of that selection. The operator path cannot perform deletion. Every MCP
client receives the same execution checks and cannot generate its own grant.

## Safe execution and durable outcomes

Linux descriptor-relative `openat`, `renameat`, `unlinkat`, `mkdirat` and streaming
`readdir64` pin parent identities and reject symlink traversal. Metadata directories
must belong to the execution user and have mode 0700; private records require
mode 0600 and canonical bounded JSON. Windows deletion is not a supported route;
unit tests explicitly emulate POSIX metadata/handle semantics on temporary data.

Execution rechecks the entire plan and dependencies under the existing shared EDA
lock. Active/queued/extracting/cancelling/recovering or unresolved states cannot
authorize deletion. Intent is durably written before destructive work. Only the
selected leaf is atomically moved into a private operation quarantine, then its
inode/device/mode/link count/size/content are reverified before unlink. A substituted
object is preserved in quarantine, not deleted. No generic recursive removal exists.

Audit records include operation/plan/IDs/time, pre-delete classification,
expected bytes, per-item verified removal and the bounded final result. States
are DRY_RUN, DENIED, COMPLETE, PARTIAL or UNKNOWN. Retry the same operation UUID
and exact request: completed outcomes replay; uncertain intent never blind-retries.
An uncertain quarantine needs a separately bounded recovery investigation, not a
new UUID or deletion retry. Prior evidence and ledgers are never cleanup targets.

## Space and budgets

Logical removed bytes, unlinked allocation and observed filesystem-free delta are
different quantities. A positive free delta cannot always be attributed to this
cleanup: unrelated writes and open handles affect physical reclaim. Therefore
`actual_reclaimed_bytes` remains null when causal attribution is unavailable;
the response reports the measured delta and precise unlink metadata separately.
Estimated logical bytes are never presented as measured physical reclaim.

Cumulative reserved bytes are history, not current disk occupation. Cleanup
**never refunds or resets reservations/attempts**. Preserve 500 Spectre attempts,
10 GiB cumulative reservation, one EDA job, 128 MiB reservation per new job and
max(2 GiB, 10%) free-space floor. The elapsed ceiling remains removed. Read-only
storage qualification requires no Spectre run. STORAGE-COMPACT-01, compression,
cloud archival, migration and automatic cleanup remain deferred.

The active repository correction ceiling is 20 through
PHASE_CORRECTION_LIMIT_V5.json and explicit private user delegation. Consumed
corrections and older extensions are preserved; the policy alone grants no
remote operation or deletion authority. The current immutable reference helper
is storage-mgmt-v6, retaining the original control/spool/operation identity domain.
