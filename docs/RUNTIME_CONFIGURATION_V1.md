# RUNTIME-CONFIG-01: connected-server configuration observation

## Contract

`cadence_runtime_info()` takes no arguments and returns a bounded typed local
snapshot. It reports bridge package version, stdio transport, loaded design/PDK
schema versions and entry counts, semantic catalog digests, and journal selection.
Each catalog source is `builtin_reference` or `operator_supplied`.

The schema is v1. Every previous MCP tool/schema remains unchanged; the current
catalog has 70 tools. The separate `MCP_RUNTIME_CONFIG_V1_SNAPSHOT.json` records
the additive schema without editing the historical 69-tool readiness snapshot.
The contract gate checks both exact inventories and still rejects unreviewed tools.

No names, private bindings, paths, host addresses, license values, journal contents,
job records or PDK contents are returned. No configuration reload/set operation is
provided. The observation uses frozen service-startup models and makes no new
filesystem or transport calls. Existing service startup behavior is unchanged,
including initialization of its sweep database.

## Interpreting the response

| Field | Meaning | Limit |
| --- | --- | --- |
| `bridge_version` | Version declared by the running bridge package | Source SHA or build identity is not asserted; unreleased main still declares 1.0.0 |
| `designs.schema_version` | Registry actually loaded by this process | Built-in default is v4; it does not automatically load operator v7 |
| `pdks.schema_version` | Loaded logical adapter registry version | v2 metadata does not qualify other physical PDKs |
| `entry_count` | Number of loaded design profiles / adapters | Does not count simulations or indicate execution qualification |
| `semantic_sha256` | Existing canonical-digest rule over the loaded model | Not the original file-byte hash, signature or authorization |
| `journals.analysis` | `platform_default` or `operator_supplied` | Selection only; not existence, integrity, accessibility or persistence verification |
| `journals.sweep` | `package_relative_default` or `operator_supplied` | The historical default is package-relative; explicit selection is recommended for installation |

`health_assessed`, `execution_authority_assessed`,
`environment_qualification_assessed` and `remote_contact` are false. A catalog
being loaded never grants simulation, mutation or deletion authority. No budget
or fresh protected-object assertion is inferred from this local response.

Environment profiles are used by the existing operator CLI verification; they
are not loaded here as execution selectors. `cadence_health` remains the separate
fixed remote-health operation. This local tool requires no Cadence host/license.

## Operator workflow

1. Validate/register private catalogs with the existing CLI.
2. Export the existing client fragment with explicit design/PDK settings and
   the intended **existing** analysis/sweep journal paths. Review it privately.
3. Install/restart through the client's supported registration mechanism.
4. Call `cadence_runtime_info`, then `cadence_list_designs`. Check versions,
   counts and digests against the intended validated models.
5. If defaults or unexpected digests are returned, inspect the operator/client
   launch configuration. Restart after correcting it; do not migrate, reset,
   replace or delete historical journals as a troubleshooting shortcut.

Whitespace/key-order changes in a registry file do not change its semantic digest.
Loaded models stay fixed until restart, even if the operator file changes.
Registration fragments and journals remain private. Existing CLI byte hashes
serve a different purpose and should not be compared to this semantic hash.

## Qualification and scheduling

The user defers Claude actual-app testing. Its adapter remains present, with
`CLAUDE_REAL_CLIENT_UNVERIFIED / DEFERRED_BY_USER`. SDK tests using a config format
remain protocol evidence only. Existing actual Codex five-read/69-name evidence
remains historical; it does not prove app exposure of this new seventieth tool.

No new simulation, result reservation, deployment, cleanup, optimization,
version bump, tag or release is part of this phase. Native DC/AC/TRAN, PVT,
sweeps and qualified evidence keep their existing scientific scope. Imported
planning rights remain `LEGAL_REVIEW_REQUIRED` for whole-repository distribution.
