# Operator metadata recovery on the supported standard VM

Current managed-VM source accounting uses the additive
[source60 policy](policy/PHYSICAL_METADATA_LIMIT_V4.md) and V6 guard. It preserves
the source40 and collection history described below; no collection allowance or
actual VM execution scope is increased by that source-only extension.

This development operator path inspects registered installation metadata. It does
not qualify a physical EDA backend, license, DRC/LVS/PEX, or a different VM/PDK.
No public MCP repair/shell tool is added. Import, server startup and doctor never
apply permissions. The published 2.0.0 installation is a separate artifact.

## Provisioning

Use the exact tested package and the authenticated existing native bundle, retaining
its managed root, resource lock, journals, ledger, registrations and approvals.
The helper leaves installed native sources unchanged. It derives only canonical
ancestor directories of registered libraries contained within registered tool
installations. Library leaves, user circuits, model contents and executable files
are excluded. It never enumerates whole installations recursively.

Read-only planning writes its private response and rollback material locally:

```text
python -m cadence_mcp_bridge.physical_ancestor_repair plan --bundle <bundle> --manifest-sha256 <digest> --output <new-private-plan-directory>
```

An operator must review the exact paths, canonical identities, ownership, modes,
ACLs, proposed differences, purpose and rollback method. Planning is not consent.
For this recipe, unexpected symlinks, non-directory targets, extended/default ACLs,
identity drift and scope expansion reject. Do not automatically change another VM
because the current managed validation VM has an administrator delegation.

After that VM's operator/admin authorizes the exact scope, apply the hash-bound
`plan.private.json`, using a new private output directory:

```text
python -m cadence_mcp_bridge.physical_ancestor_repair apply --bundle <bundle> --manifest-sha256 <digest> --output <new-private-output> --plan <plan.private.json> --plan-sha256 <digest> --authority <reference-to-direct-operator-delegation>
```

Only group/other write bits are removed; owner/group and read/execute access stay.
The held-inode guard, authenticated receipt and existing resource lock protect the
operation. The ordinary owning account can apply its own directories; the MCP
server and EDA commands remain ordinary-user processes. This helper deliberately
rejects root execution: if another owner requires administrator intervention, use
the established exact installation provisioning procedure rather than a root MCP.

Retain failed/partial outputs. Repeating the same authenticated plan resumes only
known before/after/intermediate states and changes nothing when already correct.
For rollback, use the same command with `rollback` and another fresh output path;
the preserved original plan/receipt must authenticate the original metadata.
Rollback restores modes/ACLs, not historical ctime. Never claim metadata unchanged
after an authorized repair. Contents are not opened by the directory recipe;
directory metadata digests are not vendor-content hashes.

## Finite follow-up collections

Original collection failures remain spent, including local account claims, partial
remote staging, stderr and journals. A source-hash change is not another query
authorization. The newer package retires its initial single-query entry path.

The operator API `physical_metadata.prepare_followup(bundle, manifest_digest,
authorization_path, new_output)` prepares locally; `collect(prepared, plan_digest)`
is the explicit remote operation. The allowance records direct operator consent,
the exact profile/manifest and original collector/plan/host-request/remote-request
digests. A generated allowance file is not independent approval. The predecessor
must still be an authenticated incomplete two-file stage without a success receipt.

The closed `OPERATOR_APPROVED_PHYSICAL_METADATA_FOLLOWUP_V1` schema requires:

- `schema_version: 1`, `kind`, and `max_additional_attempts` from1 through10;
- `profile_sha256` and `manifest_sha256`;
- `predecessor_collector_sha256`, `predecessor_plan_sha256`,
  `predecessor_host_request_sha256`, and `predecessor_remote_request_sha256`.

The remote-request digest hashes the canonical original inner request; the host
request digest hashes the original full envelope. Preserve both without substitution.
Preparation chooses the first unused slot; collection atomically stores that slot and its unique
invocation together before SSH. Failures, partial writes and unknown transport outcomes stay
spent. Account-scoped host claims and VM numbered stages survive new source, grant,
plan, aliases and process restart. An unchanged invocation cannot select another
slot. A short OS lock serializes the ten-slot nonce scan and publication; concurrent
losers create no extra invocation files. Existing legacy orphan evidence is retained
without enumerating it or letting its count block unused slots. A partial or unknown
slot remains spent. Do not remove markers to retry.

For the current managed validation scope only, immutable V3 preserves source36
and failed collection1, raising the finite ceilings to source40 and total11
collections (ten additional). New source commits and reverts remain counted by
`scripts/verify-physical-metadata-boundary-v5.py`; its retained source checkpoint
preserves the original V3 limit and source37 pins. V1/V2/V3 guards and records stay
intact and continue to describe their own source versions. These are not fresh-install defaults or simulation budget increases.

Before each justified collection, pin package sources, record purpose/conditions/
limits/stop criteria, and freshly check the existing ledger, disk floor, runtime
and journals. Keep128 entries,60seconds and1MiB per output stream. New simulation,
extraction and result reservation are zero. Begin with one collection; ten is a
ceiling, not a batch request. Retain actual outcomes privately and distinguish
portable tests, hosted POSIX tests, installed-package checks and actual VM evidence.

Filesystem mtime/ctime values in collected metadata and private repair plans use
round-trip17-digit strings. They preserve binary64 observations while avoiding
Python2.6/modern-Python JSON float rendering differences in authenticated digests.

The additive V5 guard retains V4 byte-for-byte and additionally requires the
retained source37 and source38 commits to be ancestors of the checked candidate.
Objects merely remaining in Git storage do not satisfy history preservation.
Run this gate on the canonical candidate lineage; a separately cherry-picked
local development history is not a substitute for that evidence. This guard-only
correction changes no product source or source allowance and does not retire
existing failed collection claims.
