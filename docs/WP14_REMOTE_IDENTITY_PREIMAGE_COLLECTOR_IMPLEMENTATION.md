# WP-14 Fixed Remote Identity/Preimage Collector — Version 1

Date: 2026-09-17

Status: REPOSITORY_IMPLEMENTED_LOCALLY_VERIFIED_REMOTE_NOT_AUTHORIZED

## Scope and authority

This checkpoint implements only the repository-side, argument-free, operator-only collector
defined by the merged request package. It does not create the separately named collection
authorization, contact the VM, collect evidence, deploy assets, create deployment Authorization
V2, invoke the runner or discovery, start Cadence, or access OA, ADE, design, or PDK data.

The immutable request package normalized-LF SHA-256 remains
`1906357b1ef5ba98a3d28241896fc59d0a4ff8053b64eac9f5d45f9a9bde0fcb`. The implementation
is `scripts/collect-wp14-remote-preimages.py`; its final normalized-LF SHA-256 is recorded in
`PROJECT_STATE.md` after validation. The only future activation filename is
`docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_AUTHORIZATION_V1.json`, which
is intentionally absent. The deployment V2 authorization remains absent and
`deployment_enabled=false` remains unchanged.

## Fixed collection boundary

The script accepts no arguments, paths, commands, environment overrides, design identifiers, or
values. It is not an MCP tool. After validating the immutable package, hardened deployer,
disabled deployment gate, and a separate exact-hash authorization, it may perform one fixed SSH
call to `cadence-vm`. The command reads only the expected hostname/user/root identity and the
eleven allowlisted managed destinations. It neither invokes the old runner nor creates a remote
file, snapshot, backup, audit record, or temporary artifact.

For each existing asset the output is limited to exact-byte SHA-256, mode, owner, regular-file
classification, hard-link count, non-symlink status, and containment. Optional targets may be
explicitly absent; the runner and runner-common may not. File content, unrelated listings,
environment/license values, logs, circuit data, OA/ADE content, PDK content, and raw paths outside
the fixed root are not returned.

A shared 60-second monotonic deadline, 32,768-byte combined stdout/stderr limit, strict UTF-8,
nonempty-stderr rejection, concurrency one, durable package-wide one-use claim, and no retry or
fallback are enforced. The evidence schema is closed and contains exactly eleven ordered
preimages. Uncertain identity, type, ownership, mode, link count, hash, containment, ordering,
shape, or transport state fails closed without emitting an evidence record.

## Isolated local verification

Tests copy only the fixed repository inputs into a temporary directory. The copied collector is
rewritten to start a local Python stand-in through an absolute path; production has no fake
transport switch. The stand-in records the fixed command but never evaluates it, launches SSH,
or contacts a network. Synthetic authorization exists only inside each temporary fixture and is
bound to the rewritten collector hash and synthetic executor identity.

Positive tests prove one fixed call and a bounded closed evidence record. Negative tests cover
missing and malformed authority, package/hash drift, duplicate keys, oversize input, identity and
root mismatch, required absence, malformed hashes/modes/owner/type/link/symlink/containment,
ordering/count/terminator drift, stderr, invalid UTF-8, nonzero exit, live timeout, output floods,
arguments, and irreversible single-use consumption. Full local and security results are recorded
in the completion report and `PROJECT_STATE.md`.

## Remaining gate

This implementation is not remote authority and does not prove current VM identity or asset
preimages. It must be reviewed and integrated first. A later user approval must bind the exact
merged package hash and final collector hash to one read-only collection attempt. That later
evidence still does not authorize deployment, Authorization V2 creation, discovery, role binding,
simulation, or scientific baseline confirmation. WP-14 remains blocked and WP-15 is not started.
