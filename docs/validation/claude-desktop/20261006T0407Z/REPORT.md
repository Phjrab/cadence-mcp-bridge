# CLIENT-REAL-QUAL-01: Claude Desktop actual tool calls (run 20261006T0407Z)

Observed: 2026-10-06, 04:07–04:13 UTC (13:07–13:13 KST), from the local clock.
Status: **pre-restart checkpoint, partial.** Machine-readable results are in
[RESULTS.json](RESULTS.json) and the evidence map is in
[EVIDENCE_INDEX.json](EVIDENCE_INDEX.json).

## Client and execution mode

| Item | Observation | Source |
| --- | --- | --- |
| Application | Claude Desktop for Windows, package version 2.19675.1.0 | Local Appx package query |
| Execution mode | **Code tab** of Claude Desktop (the Claude Code agent inside the app, process version 2.1.288.0) | Host environment and process query |
| Bridge registration | Claude Desktop configuration file; no other bridge registration found in the inspected Claude Code configuration | Configuration key names only |
| Tool naming | `mcp__cadence-mcp-bridge__<tool>`, loaded lazily through host tool search | Host tool list |
| OS | Windows 10 Home 10.0.19045 | Host environment |

All calls below were made from that Code-tab conversation. The Desktop **chat**
surface (outside the Code tab) was not exercised. Claude Code CLI or SDK runs
were not used and are not counted here.

## Repository baseline vs tested server

| Identity | Value |
| --- | --- |
| `repository_main_sha` | `d97d9934341d382c1131ee1f5d61ab8cc75ace38` (PR #126, 75 reviewed tools) |
| `server_version` | 1.0.0 |
| `tested_server_commit` | **UNKNOWN.** Local checkout with HEAD equal to main on a local-only branch, plus uncommitted changes |
| `installed_artifact_identity` | **UNKNOWN.** Launched from source; no operator-attested digest |
| Loaded registry | Operator design registry v8 (2 entries), operator PDK registry v2 (2 entries) |
| Journals | Analysis: operator supplied. Sweep: **package-relative default** |

The server version alone does not identify the build. The loaded server is
**not** a reviewed main build: it exposes one tool outside the reviewed inventory.

## Tool inventory scope

- Model-visible names: **76**. All **75** names from the four reference
  snapshots (69 + runtime 1 + power 2 + measurement-contract 3) are present.
- One extra name: `cadence_bandwidth_study_result`. It is not on main or any
  remote branch. It is consistent with the in-progress local build, and it was
  exposed only, never called.
- Full-schema equality: **NOT_TESTED.** The host shows the model a simplified
  input schema. Nested `$defs`/`$ref` request objects appear as an empty schema,
  and pattern, maxLength, additionalProperties, output schemas and annotations
  are not visible. Server-side validation still applied (C12). What the app itself
  received, plus initialize/negotiation, stderr and EOF, was not observable.

## Case results

| Case | Status | Scope actually verified |
| --- | --- | --- |
| C01 runtime | PASS | `runtime_info` returns the documented v8 hand-off error; `runtime_info_v2` reports v8/v2 operator catalogs, no health/authority claim |
| C02 design | PASS | list → describe → PDK status for the same ID; execution and generic qualification stay false |
| C03 catalog | PASS | 3 fixed native analyses, 3 measurements, 6 analog definitions, separate signed power reader, 1 targetless v2 spec |
| C04 native DC read | NOT_TESTED | No admitted operation ID available |
| C05 native AC/TRAN | NOT_TESTED | Same blocker |
| C06 measurement | PARTIAL | Definitions/units/source policy only; no result read |
| C07 analog | PARTIAL | Gain stays "at 10 Hz", bandwidth stays a sampled estimate; PM/offset/slew/legacy power are not read-eligible, with reasons; no result read |
| C08 power | PARTIAL | `dc-supply-power-v1` described with its own contract hash and dc-scalars source; result read NOT_TESTED |
| C09 spec | PASS | Legacy list empty; v2 targetless power spec → `NOT_EVALUATED / target_not_selected`, no source read |
| C10 sweep | NOT_TESTED | No admitted sweep identity |
| C11 storage | PASS | 1 summary + 1 complete page; logical/allocated/reservation/free kept distinct |
| C12 reject/recover | PASS (narrow) | 2 unregistered IDs → SERVER_REJECTED `invalid_input`; later reads succeeded |
| C13 repeat | PARTIAL | Local reads identical, including hash strings; remote result repeat and counter invariance NOT_TESTED |
| C14 restart | NOT_TESTED | RESTART_NOT_VERIFIED; awaiting a human quit and relaunch |

### Expected contract behavior vs failures

- **Power separation.** The legacy analog `analog-power` v1 stays non-read-eligible
  (no signed-current source). The separate `dc-supply-power-v1` reader carries a
  different contract hash. This is the documented PR #125/#126 split, not a
  compatibility failure. The reader at main reads only a pinned preserved
  extraction and fails closed for other operations. It authorizes no extraction
  or simulation.
- **Unqualified metrics.** Phase margin, offset and slew rate are reported as
  unavailable with blocking reasons. This shows the server follows its contract.
  It does not mean these quantities can be measured.
- **Specifications.** The v1 `describe_specification` rejects the v2 spec ID
  as "not registered". v2 specs live in the separate v8 array and are reached
  through the catalog and `evaluate_specification_v2`. This is consistent with
  the contract, though the error text could point to the catalog.
- **Runtime v1 rejection** of a v8 catalog is the documented hand-off.

### Storage observation (registered result roots only)

Logical managed bytes are about 18.0 MB and allocated bytes about 48.3 MB.
Potential reclaim is 0, and all 14 artifacts are protected. The disk-floor
status is OK. Cumulative counters are **64/500 Spectre attempts** and
**7,383,023,616 / 10,737,418,240 reserved bytes**. That is 2 attempts and
268,435,456 bytes (2 × 128 MiB) above the last repository-recorded 62 /
7,114,588,160. This session called no submit tool, and the cause was not
determined here. These numbers do not describe whole-VM usage.

## Resources and side effects

No submit, cancel, sweep, extraction, deployment, cleanup (including plan or
dry-run), deletion, target registration or configuration change was made. No
write tool was called. The storage reads contacted the configured host. Reads may
still produce normal logs or inventory snapshots, so "zero filesystem writes" is
**not** claimed.

## Publication boundary

This report contains no raw arguments or results, real operation UUIDs, registry
or contract hashes, storage snapshot or artifact IDs, PDK names, paths, host
details or measurement values. Design and PDK identifiers are aliased in the
private store. Private evidence stays in the originating conversation and in a
local file outside the repository.

## Compatibility status

`CLAUDE_DESKTOP_CODE_TAB_LOCAL_READS_PARTIAL`: Claude Desktop (Code tab) verified
design discovery, the catalog, the power-reader description, targetless v2
specification evaluation, storage reads and bounded rejection/recovery.
The following remain NOT_TESTED:

- existing native DC/AC/TRAN, power and sweep result reads
- restart
- full schema and protocol
- new job lifecycle
- Desktop chat mode

The repository-level `CLAUDE_REAL_CLIENT_UNVERIFIED` gate is narrowed for the
verified reads only. It is not cleared.

## Follow-up

1. Provide existing admitted completed DC/AC/TRAN (and optional sweep) operation
   IDs from private evidence. Then rerun C04–C08, C10 and C13 as reads only.
2. Quit and relaunch Claude Desktop, then repeat runtime/design/native/power
   reads with the same IDs for C14.
3. Repeat against a reviewed build, either main or an installed wheel with an
   attested digest. The current run used an unreviewed local working tree.
4. Optionally set an explicit sweep journal in the Claude registration, without
   migrating or resetting any ledger.
