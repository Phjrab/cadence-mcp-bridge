# WP-13 Actual ADE Profile Baseline and Capability Audit

Date: 2026-09-14

Repository base: `198900ecc96c9cadd3697022f96c90bd5baf937a`

Audit result: `PASS_WITH_PROFILE_DRIFT`

Baseline decision: `BASELINE_DECISION_REQUIRED`

Snapshot freshness: `SNAPSHOT_FRESHNESS_UNCONFIRMED`

## Scope and authority

This work package audits one fixed actual ADE profile and the existing read-only IC6.1.5
introspection capability. It does not choose a bias baseline, change a profile, regenerate a
snapshot, run a simulation, enable parameterized execution, deploy a runner, add an MCP tool, or
write an OA database, ADE state, circuit, layout, work library, or PDK.

The existing remote runner reported version `0.18.0`. No remote file was deployed or replaced.
The fixed introspection refreshed only bounded logs and a before-snapshot under the already
approved `.cadence_mcp/ade-profile-introspection` runtime. All design, state, source-netlist, and
PDK-model fingerprints were checked before and after.

## Evidence provenance

| Evidence | Identity | Use in this audit |
|---|---|---|
| Current repository | `origin/main` `198900ecc96c9cadd3697022f96c90bd5baf937a` | Authoritative Git base |
| WP-12 baseline audit | `docs/ACTUAL_PROFILE_BASELINE_AUDIT.md` | Historical baseline and fixed helper contract |
| Prior implementation branch | `origin/wp/WP-13-ade-readonly-introspection` at `15d85bf440b86d191a8f9d07e7b9e687ccf003c0` | Reference evidence only; not merged or reused as code |
| Prior implementation commit | `6f6e32f48ae9bcbb0fe23bab5efc3e8a48cffb41` | Source provenance for runner 0.18.0 capability |
| Current baseline probes | two consecutive pre-introspection calls and one post-introspection call | Current profile/source/state consistency |
| Current ADE introspection | one fixed `inspect-ade-profile` call | Current bounded ADE/OA observations and before/after invariants |

The remote deployment reports runner 0.18.0, while current `origin/main` contains runner 0.17.0.
This deployment/repository drift is recorded rather than repaired. The current run did not compare
remote file bytes to the unmerged branch, so version and observed behavior—not byte identity—are
the bounded provenance claim.

## Fixed actual profile

| Field | Audited value | Status |
|---|---|---|
| Profile ID | `actual-differential-amplifier-tb2-transient` | fixed |
| Design | `MyDesignLib/Differential_Amplifier_TB2/schematic` | fixed |
| ADE product/state | ADE L / `state1` | exists and readable |
| PDK/version | `gpdk090` / `4.6` | fixed; content not returned |
| Model section | `NN` | state/profile match |
| Temperature | 27 C | state/profile match |
| Profile analysis | transient, stop `4m` | reviewed profile contract |
| ADE-state analysis | `dc` enabled; `tran` disabled with stored stop `4m` | `analysis_mismatch` |
| Named outputs | none | state/profile match |
| Caller-controlled variables | disabled | unchanged |
| Source structure | 35 instances / 14 nets / 8 terminals | read-only OA observation |

The ADE-state analysis result is not promoted into the reviewed transient profile. It is recorded
as drift requiring an explicit later decision. The structured result is `profile_drift` with
`analysis_mismatch` and `snapshot_freshness_unconfirmed`.

## Fingerprints and freshness

| Item | Current evidence |
|---|---|
| Profile registry SHA-256 | `dea735f2ba81ba5ca714df8dba1b752be1fa3ab67f5742c2cee76eb5af849a4b` |
| Source snapshot SHA-256 | `30e941fdc24ffdc30a8dc989ffb884cd2a5256797adfa5ce2b2c032af67d5351` |
| ADE-state tree-metadata SHA-256 | `a6ead91891db7b1372e9e41515c76ac3b7dc8b2adeae281f4383d3c1ba32364d` |
| Source snapshot modified | `2026-08-20T09:18:28Z` |
| ADE-state newest metadata | `2026-08-20T09:43:40Z` |
| Source minus state | `-1512` seconds |
| Latest successful actual manifest source match | yes |
| Pre-probe baseline calls identical | yes |
| Post-probe profile/source/state hashes identical | yes |
| Source/state/PDK-model/source-netlist introspection fingerprints unchanged | yes |
| Active source/state locks observed | zero |
| Raw content or remote paths returned | no |

The source snapshot is reproducible relative to the latest successful actual manifest, but it is
older than the newest ADE-state metadata. Timestamps do not prove semantic drift; they do prevent a
claim that the snapshot is the newest state representation. Freshness therefore remains
`SNAPSHOT_FRESHNESS_UNCONFIRMED`.

## VBIASN and VBIASP source-of-truth boundary

| Evidence source | VBIASN | VBIASP | Authority in WP-13 |
|---|---:|---:|---|
| Source snapshot | referenced once, not declared | referenced once, not declared | proves consumption only |
| Fixed repository wrapper/profile | `300m` | `650m` | compatibility execution value, not approved design truth |
| Current ADE state | `300m` | `650m` | current read-only observation, not a mutation approval |
| Historical research report | `370m` | `650m` | separate candidate with unmatched conditions/revision |

WP-13 does not select between `300m/650m`, `370m/650m`, or another explicit value. It also does not
infer equivalence between caller-controlled variables being disabled and ADE state containing two
stored design-variable values. Parameterized execution and sweep remain disabled.

## Legacy IC6.1.5 capability inventory

| Capability | Current result | Integration status |
|---|---|---|
| Argument-free baseline metadata audit without Cadence execution | actual verified | present in current main runner 0.17.0 |
| Fixed ADE-state file parsing for identity, analyses, variables, outputs, model section, and temperature | actual verified | implementation exists only on prior unmerged branch |
| OA open in mode `r`, 35/14/8 counting, close without save | actual verified | implementation exists only on prior unmerged branch |
| Before/after source, state, PDK-model, and source-netlist fingerprints | actual verified | implementation exists only on prior unmerged branch |
| Source/state lock rejection | actual verified with zero locks | implementation exists only on prior unmerged branch |
| Bounded metadata-only result with no paths or raw content | actual verified | implementation exists only on prior unmerged branch |
| `cadence_inspect_ade_profile` MCP exposure | historical branch evidence only | not integrated into current main |
| Simulation, parameter override, snapshot regeneration, or sweep | not run and not authorized | disabled |

The read-only capability works in the observed legacy environment, but current main does not own
the 0.18.0 implementation. A later implementation work package must reconcile or reimplement it
from the then-current main instead of merging the stale branch automatically.

## Acceptance result

- Actual profile identity and bounded metadata were obtained from a fixed allowlisted command.
- Current profile, source snapshot, and ADE-state hashes were stable across the audit sequence.
- OA/source/state/PDK-model/source-netlist before/after fingerprints were unchanged.
- Unknowns and drift are explicit: analysis mismatch, snapshot freshness, bias authority, and
  repository/deployment version mismatch.
- No bias value was selected by inference.
- No runner deployment, MCP change, simulation, profile edit, snapshot regeneration, OA save,
  design/state/PDK/work-library write, tag, release, merge, or direct-main push occurred.

WP-13 passes as an audit. It does not pass the profile contract, freshness gate, bias baseline,
parameterized execution, or sweep gates.

## Next gate

After this feature branch is reviewed and merged, WP-14 may prepare a versioned
`VBIASN`/`VBIASP`, analysis-mode, and snapshot-freshness decision package. WP-14 must not enable or
execute parameters and must preserve the unresolved alternatives until the user explicitly chooses
them.
