# WP-14 Runner Lineage Reconciliation

## Scope

This repository-only reconciliation preserves the fixed read-only ADE profile introspection
capability observed on remote runner 0.18.0 while retaining the names-only WP-14 discovery added
to repository runner 0.19.0. It does not authorize deployment or execution.

## Provenance review

- Current base: PR #20 merge commit `0e3ebe266ea7cf6e1d3b693f64243a7e8a82e845`.
- Repository runner: `0.19.0`.
- Observed remote runner: `0.18.0`.
- Historical reference only: `15d85bf440b86d191a8f9d07e7b9e687ccf003c0`.
- The historical branch was inspected as evidence only. It was not merged, cherry-picked, or used
  as the working branch. The repository capability was independently reconstructed on the current
  feature branch.

## Capability result

| Capability | Remote 0.18.0 | Main 0.19.0 before | Reconciled 0.19.0 |
| --- | --- | --- | --- |
| Fixed actual-profile baseline audit | present | present | present |
| Fixed `inspect-ade-profile` ADE/OA audit | present | absent | present |
| WP-14 names-only role discovery | absent | present | present |
| MCP exposure of either WP-14 operator audit | absent | absent | absent |

The restored command accepts only the literal profile
`actual-differential-amplifier-tb2-transient`. Its helper fixes the source cellview, ADE state,
source snapshot, model file, and profile registry in code. The OA probe opens only
`MyDesignLib/Differential_Amplifier_TB2/schematic` in mode `r`, closes it, and has no save or write
operation. Before/after fingerprints and lock counts must match; the 35/14/8 topology, input sizes,
runtime duration, output size, and single-operation concurrency are bounded. Any mismatch fails
closed.

## Deployment gate

`remote/config/runner-lineage.json` keeps `deployment_enabled` set to `false`.
`scripts/deploy-remote.ps1` continues to stop before any network operation when that gate is false.
The restored files appear in the future deployment manifest only so a later separately approved
deployment cannot silently omit the reconciled capability.

No SSH connection, remote file update, Cadence or SKILL invocation, simulation, OA save/write, ADE
state change, source/design/work-library/PDK change, parameter application, merge, tag, release, or
WP-15 work is part of this reconciliation.
