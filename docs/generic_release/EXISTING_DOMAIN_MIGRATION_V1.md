# Existing standard-VM domain migration

This operator CLI attaches an immutable accounting identity to a retained legacy
installation. It preserves the counter, prior attempt markers, jobs, shared EDA
lock and old launcher. It does not initialize a budget, issue a grant or enable
simulation. GREL03 remains partial until fresh installation, authentic provider
and actual new-job paths pass. The current user's explicit continuous GREL02–07
instruction is the authority for this VM; a generated plan is not human consent.

Support is the professor-provided CentOS/Cadence VM or an equivalent reproduced
installation, existing PDK and individual VMware. Address, SSH keys, account,
paths, circuits/ADE, registries/journals and limits are operator configuration.
The reference legacy policy applies only when reusing the historical installation;
fresh users must not import its developer counter, approvals or private checkpoints.
Fresh-domain initialization is not implemented by these commands.

## Existing installation flow

Use the installed package as the normal guest account. Register an environment
profile with the actual host identity, strict SSH alias, existing managed/job/result
roots and already authorized limits. Do not create an alternate root to bypass
past consumption. Imports, server startup and doctor never invoke migration.

1. `cadence-mcp-bridge domain export-helper-bundle --output <new-private-directory>`
   exports four fixed helper files and their canonical manifest. Preserve the returned
   manifest SHA256. Stage that exact set under the profile's
   `managed_root/operator-helpers/<manifest-sha256>/`, owned by the guest user,
   without shared write permissions. Verify every file hash and all ancestor paths.
   Staging is explicit operator provisioning, not an arbitrary MCP upload tool.
2. `cadence-mcp-bridge domain plan-existing --profile <profile.json> --output
   <new-private-plan.json> --expected-helper-sha256 <manifest-sha256>` performs a
   read-only inventory using the shared lock. Preserve the returned plan SHA256.
   Private plans contain host/path and ledger metadata; never commit them.
3. Review the retained ledger and plan. The current VM is already authorized by the
   actual user instruction. Other VM owners must provide their own confirmation.
   Run `cadence-mcp-bridge domain apply-existing --profile <profile.json> --plan
   <private-plan.json> --output <new-private-receipt.json> --expected-plan-sha256
   <plan-sha256> --expected-helper-sha256 <manifest-sha256> --operator-authority
   <reference-to-actual-human-instruction>`.
4. Inspect the receipt: `ledger_modified=false`, `ledger_initialized=false`,
   `reservation_cost=0`, `execution_authorized=false`. Repeating the same command
   with a new local receipt path returns `anchor_created=false` without rewriting
   retained records. This proves migration idempotence, not job replay qualification.

The authority string records the actual instruction; it cannot authenticate or mint
an execution grant. No grant-generation route is exposed by this helper.

## Durable protection and failure recovery

Before any write, the fixed helper verifies the package manifest, host/account,
profile, original counter conservation, historical markers and the existing lock.
It then compares the current inode/metadata/content snapshot with the plan. Later
consumption invalidates a stale plan and is retained. Busy or active/unresolved
installations reject; no process is killed, reservation refunded or old job removed.

The helper fsyncs a plan-hash-indexed intent before creating
`reservation-identity/manifest.json` and a matching completion receipt. Only a
known identical partial state resumes. Orphan/mismatched records reject. After a
complete migration and subsequent consumption, use the established provider path;
do not regenerate a baseline or retry migration to reset the ledger. There is no
automatic rollback deleting the anchor or receipts. Investigate partial failure
with all original evidence intact.

Exact standalone Python2.6 files are hash-bound before helper imports. SSH uses
BatchMode and StrictHostKeyChecking; the fixed system Python invocation isolates
PYTHONPATH and suppresses bytecode writes. MCP has no migration/admin/shell tool.
No installer, system Python, license, Cadence/PDK content or OA/ADE is modified.

## Evidence boundary

Local synthetic tests cover stale consumption, forged bindings, partial recovery,
repeat, shared POSIX flock and conservation. Installed-wheel tests check fixed
helper export and preserved migration state through reinstall/uninstall. Actual VM
migration receipts are recorded separately; neither category proves new circuit
execution, automatic extraction, generic Sweep/specification or actual Codex jobs.

## Actual current VM receipt, 2026-10-08

Installed wheel helper digest
`4e94ec6ba4709c1b4110c132e402c910c24dffa034a40185f6c967ddeb65de62`;
plan `6ec6210b46e855a2393339bd56640d0c10fe922c62b374a99171fc3fb4a433d1`;
identity manifest `d1b82e1653d60cafc2c0d313c297ac249541e7a1b721bd346212e5025b773e22`.
Normal-user actual inventory/apply/repeat PASS; the earlier read-only plan snapshot
was identical immediately before apply. Shared counter82 /9,798,942,720, its
metadata, lock and three historical job records remained unchanged. New anchor,
intent and completion records only; no new simulations, reservations or grant.
Private full plans/receipts remain ignored. Installed helper bytes match the
previously staged exact standalone assets. Metadata repair history stays intact.

Retained installed-wheel SHA256
`8faa8405e02a32c378502427e900b77ac284e385dc3937bf8b4e882b4520e823`;
sdist `3a0f9fdb4a5f5aea618f9081c7444e9a1a6d91d9b8bf6f42494eefa672f8d6af`.
These precede this documentation receipt. Local140 affected PASS/eight Windows
platform skips; security18 PASS/1.55s/audit clean; mypy74/Ruff/85-schema checks PASS.
Installed disposable helper-export/migration/repeat PASS. Full candidate package
preservation and hosted checks are recorded after completion; no formal review
approval, publication or new circuit validation is implied.

Final canonical package verification PASS: installed CLI/protocol/bootstrap and
retained accounting tests; reinstall and uninstall preserve43 synthetic operator
files plus5 synthetic migration files. These are local disposable records, not
actual new jobs. Public hosted checks remain pending for this new feature source.
