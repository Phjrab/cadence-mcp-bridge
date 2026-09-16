# WP-14 Bounded Read-Only Discovery Deployment and Execution Approval Package

Date: 2026-09-16

Status: `READY_FOR_REVIEW_NOT_AUTHORITY`

Machine-readable package:
`docs/approvals/WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE_V1.json`

## Purpose

This package defines the minimum reviewable path from the merged repository runner 0.19.0 to one
bounded names-only discovery result. It does not authorize implementation, remote access,
deployment, Cadence startup, or invocation. Every authority field in the machine-readable record
is false.

PR #22 is recorded as merged at
`5ce2ae8480e4f5b1678f99f714ddb250c9103ec0`, with reviewed head
`a03b2f76ac1714a2d05f5cc876c699152b38667e`. The repository remains private. No fresh remote
observation was made while preparing this package; remote runner 0.18.0 is historical evidence.

## Why deployment and execution remain separate

The existing `scripts/deploy-remote.ps1` manifest also updates unrelated historical
write-validation assets. It is therefore too broad for this approval package and is not approved.
A future repository-only change must implement an exact-allowlist deployer for the eleven assets
whose normalized-LF hashes are fixed in the package. That implementation must be locally tested,
reviewed, and merged before any remote use can be considered.

After that, remote preflight and deployment require their own explicit package- and
deployer-hash-bound approval. Deployment must stop after verifying the atomic install, file modes,
hashes, runner version 0.19.0, preserved ADE introspection, fixed role-discovery command, and the
absence of Cadence/design access.

One zero-argument `wp14-role-discovery` invocation requires a further explicit approval bound to
the verified deployment evidence. This sequencing prevents package review or deployment approval
from silently becoming permission to start Virtuoso.

## Proposed deployment boundary

- Remote root: `/home/buet/cds_work/.cadence_mcp` only.
- Exact allowlist: eleven package-hashed runner, compatibility, discovery, lineage, and profile
  assets only.
- Existing managed asset identities must be captured before replacement.
- Installation must use same-directory temporary files and atomic rename.
- One recoverable package-bound snapshot is permitted only after a future explicit deployment
  approval; rollback may restore only those exact managed files.
- Maximum attempts and parallelism are one. Automatic retry, cleanup, fallback names, and scope
  expansion are forbidden.
- Deployment verification may run syntax, hash, mode, command-surface, and runner-version checks.
  It may not start Cadence or read source, ADE-state, work-library, or PDK content.

`remote/config/runner-lineage.json` remains `deployment_enabled=false` in this documentation run.

## Proposed one-invocation boundary

- Operator command: `wp14-role-discovery` with zero arguments.
- MCP exposure: none.
- Fixed source: `MyDesignLib/Differential_Amplifier_TB2/schematic`.
- OA lifecycle: mode `r`, close without save.
- Required structure: 35 instances, 14 nets, eight terminals.
- Required source fingerprint:
  `046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714`.
- Runner/OA timeouts: 60/30 seconds.
- Concurrency and attempts: one.
- Private stream/public result: at most 65,536/16,384 bytes.
- Runtime writes: only bounded mode-700/mode-600 lock, before-snapshot, redacted result, and
  PID-scoped `.before.*.tmp`/`.result.*.tmp` failure artifacts under
  `/home/buet/cds_work/.cadence_mcp/wp14-role-discovery`.
- Result: bounded counts, opaque source-bound commitments, allowlisted enums, ambiguity/blocker
  enums, and invariant booleans only.

Names, property values, paths, raw OA objects, netlists, ADE-state content, PDK content, waveforms,
license values, environment values, credentials, and unbounded logs are forbidden. Active or
ambiguous locks, recovery artifacts, identity drift, fingerprint drift, topology mismatch,
unsupported candidates, resource overflow, or lifecycle failure stop the run without repair or
retry.

## Meaning of a successful result

A successful result is candidate evidence only. It does not establish a semantic VDD, VCM, or
load binding; does not confirm `VBIASN` or `VBIASP`; does not establish source/ADE-state semantic
equivalence; and does not approve the condition collector, simulation, parameterized execution,
or WP-15.

## Review sequence

1. Review and merge this documentation-only package.
2. Separately approve repository-only implementation and local testing of the narrow deployer.
3. Review and merge that implementation.
4. Separately approve exact remote preflight and deployment.
5. Review the verified deployment evidence.
6. Separately approve exactly one fixed discovery invocation.
7. Review the bounded discovery evidence before any role-binding or scientific-baseline decision.

No step authorizes the next step automatically.
