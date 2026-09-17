# WP-14 Package-Bound Narrow Deployer Implementation

Date: 2026-09-17 (original implementation: 2026-09-16)

Status: `LOCAL_ESCAPE_REGRESSION_VERIFIED_DEPLOYMENT_BLOCKED_ON_CONTRACT_GAPS`

The 2026-09-17 correction changes six generated-shell string statements only. See
`WP14_NARROW_DEPLOYER_CORRECTION_REVIEW_V1.md` for the new deployer hash, isolated fake-transport
tests, and the identity, live bounds, and single-use gaps that still block deployment. The earlier
deployment result and approval audit record remain unchanged historical evidence; that approval
does not apply to the corrected hash.

## Scope

`scripts/deploy-wp14-narrow.ps1` implements the repository side of the narrow deployment contract
requested by the immutable approval package whose normalized-LF SHA-256 is
`7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87`.

The script accepts no custom parameters. It independently fixes the same eleven repository paths,
normalized-LF hashes, and remote modes as the package. It validates the package, both bound plans,
all local asset hashes, path containment, reparse-point absence, runner lineage, and
`deployment_enabled=false` before considering any transport operation.

## Independent remote-authorization gate

This implementation does not grant remote authority. Before resolving or invoking `ssh` or `scp`,
the script requires a future record at
`docs/approvals/WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V1.json`.

That future record must explicitly authorize remote preflight and deployment, declare exactly one
use, and bind both the immutable package hash and the final normalized-LF hash of the deployer.
The current code checks the declared count but does not enforce durable consumption or concurrency.
The live record remains intentionally absent. Therefore current execution fails
closed before any remote command. `remote/config/runner-lineage.json` remains unchanged with
`deployment_enabled=false`; the existing broad deployer remains blocked.

## Implemented deployment boundary

The current implementation contains the following controls. They do not establish full compliance
with the package, and a new authorization record must not be created before the review gaps are
resolved:

- SSH alias `cadence-vm` and remote root `/home/buet/cds_work/.cadence_mcp`;
- the package's exact eleven assets with no caller-provided path or value;
- strict host-key checking, batch mode and connection-liveness options; a 300-second elapsed-time
  check before/after transport and a 65,536-byte check after response collection (not hard live
  process or memory bounds);
- no retry loop, but no durable approval consumption or operation-wide concurrency lock;
- a fixed package-bound before-snapshot that refuses overwrite;
- same-directory temporary files followed by atomic rename;
- exact post-install hashes and modes;
- shell/Python syntax, runner version 0.19.0, preserved fixed ADE introspection, and presence of the
  operator-only `wp14-role-discovery` command surface;
- `deployment_enabled=false` in the installed lineage record; and
- no Cadence process, design access, discovery invocation, simulation, automatic retry, remote
  cleanup, fallback destination, or automatic rollback.

The script does not run `wp14-role-discovery`. A successful future deployment would produce only
deployment evidence and must stop before the separately approved one-invocation stage.

## Local acceptance

Repository tests verify package and plan immutability, all eleven asset hashes, zero custom
arguments, exact scope, false lineage gate, authorization-before-transport ordering, no design-write
asset, no generic shell evaluator, and syntax/surface-only remote verification strings. Executable
tests copy only the required assets into a pytest temporary repository. Synthetic authorization
exists only there; PATH is replaced by an empty fixture directory and in-process fake SSH/SCP
functions handle every call. Neither the live repository script nor real SSH/SCP is invoked.

Tests cover generated printf/TSV/find escaping, successful fake sequencing and upload hashes,
rejected/missing/old-hash authority, binding tamper, failures and wrong markers at each stage,
completed-response overflow, a pre-transport expired deadline, WhatIf, and historical-regression
detection. These tests do not execute Bash, Cadence, or remote commands and do not prove an actual
install, snapshot restore, remote identity, hard in-flight deadline, bounded streaming, or approval
consumption. The single-use characterization test explicitly reproduces a remaining gap with fake
preflight failures; it is not a replay acceptance criterion.
