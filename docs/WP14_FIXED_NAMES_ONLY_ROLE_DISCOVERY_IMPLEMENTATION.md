# WP-14 Fixed Names-Only Role Discovery — Repository Implementation

Date: 2026-09-15

Status: `REPOSITORY_IMPLEMENTED_LOCAL_VERIFIED_DEPLOYMENT_BLOCKED`

Bound plan: `WP14_FIXED_NAMES_ONLY_ROLE_DISCOVERY_PLAN` version 1

Normalized-LF plan SHA-256:
`2e44ca523c122744f6b16036785f285fc0f6a3d7b1b904326fe84ecc9165f12d`

## Authority and result

This change implements and locally tests only the repository-side fixed discovery described by the
reviewed plan. It does not authorize or perform remote deployment, SSH execution, Cadence startup,
simulation, OA save/write, ADE-state modification, design/PDK modification, role binding, bias
application, or scientific-baseline approval.

The implementation is an argument-free operator runner command named `wp14-role-discovery`. It is
not present in the MCP server, service, models, or SSH-backend tool surface. The source identity,
expected 35/14/8 topology, plan hash, and required source fingerprint are fixed in reviewed code.
No caller path, design identifier, property name/value, shell text, or SKILL text is accepted.

## Runner provenance reconciliation

The current `origin/main` runner is version 0.17.0. The observed deployed runner reports 0.18.0,
whose ADE-profile introspection implementation exists only at historical unmerged reference head
`15d85bf440b86d191a8f9d07e7b9e687ccf003c0` on
`wp/WP-13-ade-readonly-introspection`. That stale branch was inspected as provenance evidence only;
it was not merged, rebased, or reused.

The repository candidate is therefore versioned 0.19.0 and accompanied by
`remote/config/runner-lineage.json`. Deployment remains hard-blocked in `deploy-remote.ps1` while
`deployment_enabled` is false. This prevents a repository deployment from silently replacing the
deployed 0.18.0 command surface before a separately reviewed capability reconciliation. The WP-14
assets are listed for a future reconciled deployment, but this run did not contact or modify the
remote host.

## Security boundary

- The only OA target is `MyDesignLib/Differential_Amplifier_TB2/schematic`, opened with mode `r`.
- The SKILL contains no save, copy, replace, create, delete, dynamic load/eval, shell, or process API.
- Property inspection is limited to allowlisted property names and `valueType`; property values are
  never read.
- Only closed analogLib master classes and fixed connection/property-slot enums can reach the
  redacted result. Unsupported masters, slots, topology, or resource bounds fail closed.
- Private OA identifiers exist only transiently in the anonymous child-process pipe consumed by the
  redaction helper. They are not written to logs, stdout artifacts, stderr artifacts, result files,
  or repository evidence. Cadence logging and stderr persistence are disabled for this command.
- The result contains only bounded candidate counts, opaque domain-separated SHA-256 selector
  commitments, allowlisted enums, ambiguity/blocker enums, and invariant booleans. Every candidate
  has `semantically_confirmed=false`.
- The runner uses a nonblocking single-worker lock and a 60-second total timeout; the OA process has
  a 30-second timeout. Private input is bounded to 65,536 bytes and final JSON to 16,384 bytes.
- Before/after protection covers the source cellview tree, source snapshot, ADE-state tree, fixed
  profile registry, PDK model, and lock/artifact classification. Drift blocks the result.

## Local acceptance evidence

The implementation-specific tests cover the exact plan hash, preservation of the v1 package and
v2-v4 records, fixed target and zero-argument route, absence from MCP, deployment blocking,
read-only/no-save SKILL primitives, no property-value access, bounded redacted output, deterministic
source-bound commitments, unique-candidate non-approval, multiple-candidate ambiguity, caller input
injection, Unicode/confusables, malformed markers, topology/property/candidate overflow, source
fingerprint mismatch, blocking lock, and protected-fingerprint drift.

The complete local gate passed:

- Ruff: passed.
- strict mypy: passed for 17 source files.
- pytest: 191 passed, eight expected real-integration skips, 56 pre-existing deprecation warnings.
- secret preflight: passed for 321 repository files.
- dedicated security suite: 18 passed.
- strict locked dependency audit: passed as part of the security gate.
- PowerShell parser and Python helper compilation: passed.
- `git diff --check`: passed (Git reports only the existing Windows LF-to-CRLF checkout notice for
  the PowerShell script).

No actual Cadence/SKILL syntax or behavioral validation was run because Cadence execution is
explicitly outside this approval. Consequently no role candidates, selector commitments, operating
condition evidence, or scientific conclusion were produced.

## Remaining gate

WP-14 remains blocked. A later approval must first reconcile the deployed 0.18.0 capability with
the repository 0.19.0 candidate and review the exact implementation commit. Deployment and one
fixed read-only invocation each require separate explicit approval. Any produced candidate remains
unresolved until a separate, hash-bound role-binding and final scientific-baseline decision is made.
WP-15 remains unstarted.
