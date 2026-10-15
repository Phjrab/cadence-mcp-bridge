# POST-05: selective-cleanup safety checkpoint

## Current integration scope, 2026-10-15

The user's latest instruction explicitly authorizes conditional normal integration
of POST154–158 in dependency order after review, CI and actual scope acceptance.
For PR156 the accepted scope is this documentation and the retained read-only
inventory/plan/dry-run evidence. No historical deletion target has been selected;
actual deletion and compaction remain incomplete and separately scoped.

The latest shared managed-VM observation is126 conservative accounting attempts
of500 and15,452,864,512 of17,179,869,184 reserved bytes, leaving1,727,004,672 bytes.
The conservative guarded-source correction counter is now24 of24: its original
scope includes the host recovery module, so the two host output-guard corrections
remain charged even though installed native assets did not change. The earlier22
observation is historical, not remaining correction capacity.
The112-attempt/13,825,474,560-byte
dry-run checkpoint below is a historical observation, not a restored ledger or
available allowance. This documentation update changes no consumption or policy.

Further Claude validation is EXCLUDED_BY_USER, not PASS. Existing actual Codex
dry-run evidence remains specific to the standard VM and unchanged storage
implementation. Published2.0.0 artifacts, original results/PSF and all ledgers,
replay and failure evidence remain preserved. Older approval exclusions below and
in prior PR descriptions remain historical where this newer instruction supersedes
them; none authorizes deletion, compaction, budget reset or a new publication.

Parent155 fe476db is integrated by a normal merge; conflicting top-of-file status
entries retain both histories with the current156 scope above dated checkpoints.
The resulting difference from155 is only this guide and the two status documents.
All source/scripts/tests/package metadata are byte-identical to the parent.
Diff/whitespace checks pass; exact156 hosted/review checks remain separate gates.

This phase reuses the existing five path-free storage tools rather than adding a
second deletion engine. Continuous POST authorization permits safety validation;
it does not choose a historical artifact for deletion. No existing result, failure,
PSF or journal has been selected or deleted. Compaction is a separate later step
and is not implemented or qualified by this checkpoint.

## Inspect before choosing

Read `cadence_storage_summary`, then page `cadence_list_storage_artifacts` using
that exact snapshot. `cadence_describe_storage_artifact` reports classification,
dependencies, fingerprint and deletion reason. Ages remain unknown; neither mtime
nor a completed measurement grants deletion permission. Partial inventory blocks
eligible selection rather than presenting incomplete totals as complete.

Submit only inspected opaque IDs to `cadence_plan_storage_cleanup`. This produces
a hash-bound plan, eligible IDs, protected exclusions and estimated logical bytes;
it performs no deletion. The current implementation permits only individually
registered disposable intermediate payloads with no active, replay or evidence
dependencies and confirmed measurement extraction. Native/legacy job groups,
original results and unknown dependencies remain protected. Source OA/ADE, PDK,
vendor files and local state are outside its roots.

For a permitted intermediate, deletion loses the selected original payload bytes
and their ability to be inspected or processed again. The contract permits no
loss of replay or evidence functionality. A request requiring removal of original
PSF/results is outside this implementation and must not be relabeled disposable.
Report preservation alone is not proof that all later re-extraction/comparison
needs have been removed.

Use `cadence_execute_storage_cleanup` with `dry_run: true`, the complete plan,
the exact selected subset and a fresh UUID to validate the selection. A dry-run
records no deletion authority and does not select objects on the user's behalf.
For real deletion, the VM operator must separately bind the user's exact choice,
plan hash and UUID through the existing consent flow; an agent-generated plan or
phase approval is not that selection. The worker rechecks fingerprints/dependencies
and the shared EDA lock immediately before mutation.

Retain the same UUID after interruption; PARTIAL and UNKNOWN preserve evidence
and never authorize blind retries or a replacement UUID. Removed logical bytes
and unlinked allocation are reported separately from an unattributed filesystem
free-space delta. Physical reclaim is not asserted from that delta. Reservations,
consumed executions, journals, audit and replay are never refunded or reset.

## Actual connected-client safety evidence, 2026-10-13

The existing Codex native QA connection inspected the actual managed standard VM.
Inventory covered16 opaque artifacts across six registered groups. A validation
plan containing one protected native DC group and one registered disposable
intermediate excluded the DC group and identified only the12288-byte intermediate
as eligible. This was an agent-created read-only validation plan, not a user's
real deletion selection.

An explicit dry-run of that eligible intermediate returned DRY_RUN, zero removed
IDs/bytes, zero free-space delta and zero refund. Repeating the identical UUID and
request returned the same outcome. A fresh summary retained the exact snapshot,
112 attempts and13,825,474,560 reserved bytes under16GiB; disk floor remained OK.
No deletion, compaction, simulation, reservation, native update or administrator
change occurred. This is actual connected Codex/native VM plan/dry-run evidence,
not Claude acceptance and not verification of original-result deletion/compaction.

Local disposable report/storage tests91 PASS/8 POSIX or symlink skips. Earlier
long Windows fixture failures remain preserved: a271-character audit path caused
partial completion; shorter fixtures pass with production protections unchanged.
Linux descriptor/flock qualification is separately tracked in hosted CI. No
history is deleted to make a test pass or regain capacity.
