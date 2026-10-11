## Authenticated native module loading checkpoint

The dispatcher loads all fixed internal executable assets explicitly from their
manifest-verified bytes. A cached top-level module from a system startup hook
cannot replace storage, confirmation or another native component. Compilation
uses the bound installed filename for diagnostics and creates no bytecode; no
caller module name, script or path is accepted. Regressions poison the cached
module names and prove both the complete loader and storage route use verified
bytes. Local affected75 PASS/31 Windows POSIX skips; mypy96 PASS. Final hosted
checks/review and exact installed/VM qualification remain required.

Fixed run.lock guards retain device/inode/UID/GID/mode/nlink/size and a bounded
content hash. They intentionally exclude only timestamps: existing reviewed
launchers truncate an empty lock before testing flock, which legitimately
changes mtime/ctime while preserving identity and bytes. Contents, metadata
permissions, fixed names and artifact fingerprints remain protected. New
regressions cover normal contention and same-size content substitution.

## Fixed storage lock checkpoint

The storage worker now pins the ordinary user's private root and a regular,
mode600, single-link run.lock by descriptor and fixed named path. It verifies
ownership, metadata and identity after the lock decision, after the native
activation callback, immediately before payload rename/unlink, and before a
response can claim completion. Lock or root drift denies the operation; a moved
payload remains in quarantine and an interrupted cleanup retains its intent and
unknown outcome. No retry resets a reservation or removes retained evidence.

The existing standalone factor and operator transport share these checks. Busy
inventory remains conservative and read-only. Public inputs still contain no
path, shell, permission or administrator facility. No actual VM cleanup is part
of this validation.

Local affected tests:95 PASS,15 Windows POSIX/symlink skips; full Ruff and mypy96
PASS. These are synthetic temporary-file tests. Exact Ubuntu nofollow/flock
regressions, final review, current installed assets and VM inventory remain
required. Earlier counts below retain their source-specific meaning.

# Operator native storage integration

Status: implementation checkpoint, final standalone integration, review, hosted
checks and exact installed/VM qualification pending. General release is BLOCKED.
This document is a technical record, not additional approval or a frozen candidate.

The selected operator context now connects the existing five path-free storage
MCP tools to its immutable native provider, environment profile and accounting
identity. It does not inherit the reference developer address, account or managed
root. The public input/output declarations remain unchanged. No caller path,
shell, administrator command, retention registration or consent writer is added.

Requests use fixed storage_inventory/storage_cleanup actions on the registered
provider. Closed canonical envelopes bind the exact runtime SHA, resource anchor
and action. A changed host grant/provider binding requires review and restart;
transport loss is never automatically retried. Cleanup replies must preserve the
operation ID, selected IDs and plan ID, and a dry-run cannot claim deletion.
Independent exact selected-item operator consent remains mandatory remotely.

The native dispatcher verifies the complete immutable bundle before importing
storage, and rechecks bundle, active pointer and activation history at the locked
worker boundary. The root comes only from the validated profile. Busy inventory
must remain conservative/read-only; lock contention cannot authorize cleanup.
The worker factor and generic protected job-group coverage are still pending
PR151 integration at this checkpoint. Historical deployed providers that lack the
new actions reject; their prior results do not qualify the updated dispatch.

Local configured public MCP/transport/runtime tests:84 PASS,1 Windows symlink
skip; full mypy95 PASS and touched Ruff PASS. These use a synthetic wire and do
not claim remote storage or Cadence validation. No VM cleanup, chmod/chown,
simulation, reservation, ledger reset or refund occurred. The earlier actual
Codex reconnect/same-ID result remains evidence for40c/bf6 only. Final current-code
read-only storage inventory, source/model/content protection and package checks
remain required before candidate acceptance.
