# CLIENT-REAL-QUAL-01: Claude Desktop actual tool calls (run 20261006T0407Z)

Observed: 2026-10-06, 04:07–04:20 UTC (13:07–13:20 KST), from the local clock.

**Status:** pre-restart. Existing-result reads are verified; restart is pending.
RESULTS.json and EVIDENCE_INDEX.json describe the latest state.

[RESULTS.json](RESULTS.json) holds the machine-readable results.
[EVIDENCE_INDEX.json](EVIDENCE_INDEX.json) holds the evidence map.

## Update 04:13–04:20 UTC: existing admitted result reads

The user supplied existing completed operation IDs in chat (aliases DC_OP_1,
AC_OP_1, TRAN_OP_1) and one completed sweep ID (SWEEP_OP_1). Nothing was
generated or enumerated. The supplied note asked to load an earlier admission
journal; that was **not** done, because changing the live configuration is
outside this run's scope. The analysis journal already resolved all three
operations.

| Case | Status | Verified scope |
| --- | --- | --- |
| C04 native DC | PASS | Succeeded, quality valid, fixed NN/27 C/VDD 1 V/applied bias conditions, 7 V scalars, per-result protected flag true, `not_evaluated` |
| C05 native AC/TRAN | PASS | Both valid. AC has a 72-point differential spectrum (10 Hz–100 MHz). TRAN has a bounded 754-point summary with verified stimulus. Design identity is shared across the three analyses |
| C06 measurements | PASS | dc-scalars / ac-spectrum / tran-summary results via contract hashes, full provenance, frames equal to the analysis reads |
| C07 analog | PASS | Gain QUALIFIED at **10 Hz** (not DC/max). Bandwidth **PARTIALLY_QUALIFIED** (no error bound). Phase margin and legacy analog-power v1 UNQUALIFIED with reasons, value null |
| C08 power | PASS | `dc-supply-power-v1` QUALIFIED. Six signed sources; rail power separate from bias/input. Value equal to the repository-recorded preserved reference. Same DC identity as C04 |
| C10 sweep | BLOCKED | `Unknown registered sweep admission`. The live registration uses the package-relative default sweep journal. Configuration was not changed |
| C13 repeat | PASS (reads) | Repeat DC result and power result identical (returned hash strings equal). Counter invariance not measured |

The new power reader and the legacy analog-power v1 give **different, documented**
answers for the same DC operation: QUALIFIED versus UNQUALIFIED. This is the
intended contract split. The tool outside the reviewed inventory,
`cadence_bandwidth_study_result`, was still not called. No measurement values,
spectra, currents or result hashes are published here.

## Initial checkpoint (04:07–04:13 UTC, preserved)

The section below is the first checkpoint (commit `cc0b661`), kept unchanged.
Its C04–C08, C10 and C13 rows are superseded by the update above.

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

The first checkpoint recorded `CLAUDE_DESKTOP_CODE_TAB_LOCAL_READS_PARTIAL`.

The current status is `CLAUDE_DESKTOP_CODE_TAB_EXISTING_READS_VERIFIED_RESTART_PENDING`.
Claude Desktop (Code tab) verified the following:

- design discovery and catalog
- existing native DC/AC/TRAN reads
- registered measurement reads
- analog gain/bandwidth/unqualified states
- the dedicated DC power reader
- targetless v2 specification evaluation
- storage reads
- repeated reads
- bounded rejection and recovery

The sweep read is BLOCKED by the configuration. The following remain NOT_TESTED:

- restart
- full schema and protocol
- new job lifecycle
- Desktop chat mode

The tested server was an unreviewed local working tree. The repository-level
`CLAUDE_REAL_CLIENT_UNVERIFIED` gate is narrowed for these reads only, not cleared.

## Follow-up

1. Quit and relaunch Claude Desktop, then repeat runtime/design/native/power
   reads with the same IDs for C14. Append the results to this report with a date.
2. Repeat against a reviewed build, either main or an installed wheel with an
   attested digest.
3. For C10, the operator sets an explicit historical sweep journal in the Claude
   registration, then restarts and re-reads. No ledger is migrated, reset or
   replaced.
