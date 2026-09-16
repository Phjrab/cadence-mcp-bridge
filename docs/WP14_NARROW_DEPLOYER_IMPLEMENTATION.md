# WP-14 Package-Bound Narrow Deployer Implementation

Date: 2026-09-16

Status: `REPOSITORY_IMPLEMENTED_LOCAL_VERIFIED_REMOTE_NOT_AUTHORIZED`

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

That future record must explicitly authorize remote preflight and deployment, permit exactly one
use, and bind both the immutable package hash and the final normalized-LF hash of the deployer.
The record is intentionally absent in this implementation run. Therefore current execution fails
closed before any remote command. `remote/config/runner-lineage.json` remains unchanged with
`deployment_enabled=false`; the existing broad deployer remains blocked.

## Implemented deployment boundary

Only after a separately reviewed, exact-hash-bound authorization record exists, the script is
constrained to:

- SSH alias `cadence-vm` and remote root `/home/buet/cds_work/.cadence_mcp`;
- the package's exact eleven assets with no caller-provided path or value;
- strict host-key checking, batch mode, bounded connection liveness, one attempt, 300 seconds, and
  65,536 bytes per transport response;
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
arguments, exact scope, false lineage gate, authorization-before-transport ordering, no transport
call in the current state, no design-write asset, no generic shell evaluator, and syntax/surface-only
remote verification. PowerShell parsing and a direct fail-closed invocation are also required.
