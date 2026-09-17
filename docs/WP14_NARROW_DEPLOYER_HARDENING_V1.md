# WP-14 Narrow Deployer Safety Controls — Version 1

Date: 2026-09-17

Scope: repository implementation and isolated local testing only. Remote readiness is BLOCKED.
This document is not an authorization record, preimage manifest, or remote observation.

## Provenance and preserved boundaries

- Resumed feature: wp/WP-14-narrow-deployment-attempt.
- Incoming local and freshly verified remote HEAD:
  b0e8da3aac0efa1312acc857cf90b5550b165bf2.
- Fetched origin/main remains 42405e271f54595eae69ca193dc9e3fef30dac94; repository PRIVATE.
- Immutable deployment package normalized-LF SHA-256:
  7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87.
- Hardened deployer normalized-LF SHA-256:
  227b1c0d3831e7de8f974192d7da9434276ee5a25c2448a6f5ad87922e9e0b17.
- The eleven assets, both plans, original correction review v1, deployment result v1,
  historical approval record, decision records, V1-V4 evidence, and false deployment gate remain
  unchanged. Old approvals are not migrated, activated, or reused.
- No remote preflight, SSH/SCP, deployment, Cadence, discovery, simulation, design access,
  role binding, scientific baseline confirmation, merge, tag, release, or WP-15 work is performed.

## Closed authorization contract V2 — absent and inactive

The only future activation filename is
docs/approvals/WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V2.json.
It is intentionally NOT created. V1 activation records are not accepted.
The operator-only entry point still accepts no custom arguments, paths, commands, designs or values.
PowerShell 7.5 or later is required for typed, string-preserving JSON parsing.

The record has exactly the following keys, with no duplicate (including case-variant), missing,
extra, deeply nested or oversized fields. The input bound is 32,768 bytes, depth eight, and
32 array items. Invalid JSON content is never echoed. All local ancestors must be non-reparse.

| Key | Required interpretation |
| --- | --- |
| schema_version | JSON integer 2, not a string or boolean |
| record_kind | explicit_remote_preflight_and_deployment_authorization |
| status | APPROVED |
| package_normalized_lf_sha256 | Exact immutable package hash above |
| deployer_normalized_lf_sha256 | Exact reviewed final script hash, including all control implementation |
| remote_preflight_authorized, remote_deployment_authorized | JSON boolean true, separately authorized by the user; this implementation approval is insufficient |
| max_uses | JSON integer 1 |
| authorization_id | Lowercase canonical UUID-shaped identifier; not a path |
| executor_binding | SHA-256 of current Windows user SID, separator pipe, and local MachineGuid; no raw SID/MachineGuid is logged |
| not_before, expires_at | Strict UTC second timestamps ending Z; current time within interval; validity at most 24 hours |
| observed_at | Reviewed remote evidence timestamp no later than not_before and no more than 24 hours old |
| evidence_sha256 | Nonzero lowercase 64-hex hash identifying separately reviewed evidence; not an invented observation |
| remote_identity | Exactly hostname=cadence, user=buet, fixed .cadence_mcp root, verified=true |
| preimages | Exactly one entry for each of the eleven fixed package paths, no duplicates/extras |

Each preimage has exactly path, presence, sha256, mode. Presence is file or absent.
For file, sha256 is a nonzero 64-hex digest of actual remote bytes (NOT normalized text);
mode is the explicitly observed 600 or 700. For absent, hash and mode are null.
Runner and runner-common must be files. Unknown, other types/modes, incomplete evidence and guessed
hashes fail locally before a process or ledger claim. The current VM is NOT inferred from git blobs.
Expected host/user constants describe the permitted identity, not a claim of a fresh observation.
Ownership buet, regular file type, one hard link, no symlink, exact mode and exact bytes are checked
remotely before old runner execution. Unknown required evidence requires a separate scoped plan and
approval; this script does not bootstrap its own authority by probing the VM.

This is an operator-reviewed file contract, not a cryptographic signature mechanism. An operator
must verify the evidence/hash linkage and explicit user approval before creating any future record.
No generator, example executable grant, bypass switch, or approval-import mechanism is added.

## Identity and preimage enforcement

Preflight checks fixed hostname and user, canonical root/parents, symlink absence and existing
blockers. Every managed preimage is checked before the old runner is executed for version 0.18.0.
The old runner and its sourced code must have been reviewed as part of the preimage evidence;
a self-reported version alone is not identity.

The same per-file preimage guard is repeated before snapshot copy and before replacement.
Each copied before-image hash is compared with its reviewed preimage hash. Absent targets are
explicit, and unknown files cannot be treated as absent. Snapshot mode changes are limited to the
backup, while before.tsv retains original mode metadata. The existing fixed snapshot cannot be
overwritten. Each of the four fixed shell files now gets its own syntax check.
Each generated AND-list assertion explicitly exits with code 42 on failure; it does not rely
on Bash errexit applying to a non-final AND operand. Tests enforce this in the generated strings.

These are defensive checks, not a filesystem transaction against a malicious same-user process.
The trusted remote OS/account can still change paths between checks, alter command implementations,
or interfere with a snapshot. Actual snapshot recovery is not proven by these fake tests.
No remote cleanup, rollback, repair, path fallback, or new managed asset is introduced.

## Live deadline and bounded streams

Transport uses only fixed Windows System32 OpenSSH executables, fixed SSH options and argv lists.
No PATH-based lookup, shell execution, visible window, raw-command CLI, MCP tool or test-mode
switch is added. Authorization, local package/plan/asset checks and durable claim precede transport.

The shared monotonic budget is 300 seconds for the whole attempt, not 300 seconds per command.
Both stdout and stderr are read concurrently in 4,096-byte buffers. Their combined cumulative
per-call limit is 65,536 bytes, including stderr. Output is checked before appending it to the
bounded stdout buffer; stderr content is discarded, not logged. A nonempty stderr, nonzero exit,
invalid UTF-8, overflow, expired authorization or expired deadline fails closed.

Deadline and authorization expiry are checked while reads/process completion are pending,
including a live process that never closes its pipes. On failure only this invocation's owned
local transport process tree is terminated, with at most a one-second confirmation wait after
termination is requested. Unconfirmed termination is BLOCKED; this is never proof that remote
commands stopped or that an installation was undone. No remote signal or retry is sent.
OS process creation/termination primitives and scheduler timing remain trusted; the one-second
local termination confirmation is distinct from the 300-second execution budget.

## Durable single-use and concurrency contract

The fixed Windows operator ledger is under the current user's LocalApplicationData:
CadenceMcpBridge/wp14-narrow. It is outside git and shared by all checkouts for that operator.
The executor binding prevents the same record being used on another user/machine.
No environment/CLI override for this path exists in production.

1. Complete local package/assets/schema/evidence validation.
2. Respect WhatIf/ShouldProcess; a declined dry run makes no claim and starts no transport.
3. Reject reparse ancestors. Open operation.lock with exclusive sharing for the entire attempt.
4. Create attempt-PACKAGE_SHA256.json using CreateNew, WriteThrough and Flush(true).
5. Only after that durable claim may the first transport start.
6. Release the live lock in finally, but NEVER delete, truncate, reset or repair the claim.

The claim contains only consumed-before-transport status, authorization UUID/hash, package hash,
deployer hash and UTC timestamp. Existence is decisive even if zero-length, truncated, malformed,
from a crashed process, or associated with a failed preflight/startup. Success does not restore
authority. Changing the approval UUID cannot reset this package-wide one-attempt slot.
The unchanged activation file is evidence; consumption is recorded independently.
Another concurrent process fails before transport. An operating-system-released lock after crash
does not release the permanent claim. No stale-lock deletion or automatic recovery is implemented.

This deliberately stricter package-level claim means a future retry needs a separately reviewed
recovery contract and new explicit approval, not a copied record or new ID. Local administrators,
same-user tampering, ledger deletion and machine rollback are outside this cooperative operator
threat model. The ledger is metadata only, inherits the operator's protected local app-data ACL,
and is not a cross-machine distributed lock or tamper-proof authorization service.

## Local test isolation and acceptance

Pytest copies only required repository inputs into temporary fixtures. Tests rewrite ONLY that
copied script's executable construction to launch the local fake Python process; the production
script has no injection hook. The fixture also substitutes its temporary ledger and synthetic
executor binding. Synthetic V2 records bind the rewritten fixture hash and never enter the repo.
PATH is empty; the fake process never imports a network client or evaluates the supplied commands.
Actual Windows OpenSSH compatibility and the current VM remain untested in this run.

The production streaming/deadline/claim control code runs against the fake process, rather than
mocking away those controls. The fake records argv, staged file hashes, PID and fixed command
strings only inside the temporary fixture. A closed assertion model compares generated preimage
checks against independent synthetic host/user/hash/mode data; it is not a Bash interpreter.

Acceptance includes:

- Immutable package/plans/eleven assets/disabled gate; no arbitrary execution interface.
- Positive fake 25-call workflow, exact upload hashes, modes, generated escaping and four syntax checks.
- Missing/old/wrong-hash/expired/malformed/duplicate/oversized/unknown authority rejected.
- Missing/unknown/malicious/duplicate/extra preimage and identity fields rejected before transport.
- Synthetic remote host/user/hash/mode/type/symlink/hardlink drift stops before snapshot.
- Preimages precede old-runner execution and each overwrite; explicit absence retained.
- Live blocked process, endless stdout/stderr/both streams, wrong markers, invalid UTF-8 and
  stderr payloads rejected without content disclosure or later calls.
- Owned fake process exit verified after timeout/overflow.
- Failed preflight/startup consumes the attempt; partial claim, new ID and overlapping invocation
  cannot cause a second transport; a shared ledger blocks a second checkout; WhatIf does not consume.
- The monotonic deadline is shared across sequential fake commands rather than reset per call.
- Entire local suite, Ruff, strict mypy, PowerShell parsing, document preservation and security gate.

Final local results:

- Ruff: PASS; strict mypy: PASS for 17 source files.
- Full pytest: 289 passed, eight deliberately skipped real integrations, 56 existing warnings.
  All 89 focused narrow-deployer cases are included in that passing run.
- Security: 337-file secret scan, 18 security tests and strict locked dependency audit PASS;
  no known vulnerabilities found.
- Both PowerShell syntax checks, seven-file scope, prior-history/assumption preservation,
  immutable package/plan/asset hashes, final deployer hash, metadata/fences and diff checks PASS.
- Actual authorization V1/V2 and real operator ledger remain absent.

An intermediate fixture-only Korean-path encoding failure was corrected by explicit UTF-8 before
the passing full rerun. Final negative cases also reject array-typed scalar identity/hash fields,
avoiding PowerShell's array-filter comparison semantics.

## Next gate, not an execution grant

Review the feature implementation and local evidence. Before any deployment, integrate through a
separately approved PR, resolve the missing reviewed identity/preimage evidence with a separately
scoped read-only plan, and obtain new final-hash-bound authority for exactly the intended stage.
Neither an old hash approval nor this local implementation approval permits remote use.
Discovery invocation remains a separate later decision. VDD=1.0 V, VCM=0.5 V and no added external
load are still planning assumptions; scientific baseline confirmation remains BLOCKED.
