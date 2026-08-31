# Actual Profile Baseline Audit

Date: 2026-08-31
Work package: WP-12
Status: `BASELINE_DECISION_REQUIRED`

## Scope and safety boundary

This audit covers the fixed `actual-differential-amplifier-tb2-transient` profile, its existing
ADE-generated source snapshot, and ADE L `state1`. The fixed runner 0.17.0 command accepts no
arguments and returns only bounded metadata. It does not return a remote path, raw netlist, raw ADE
state, PDK content, PSF data, credential, or license value.

The audit was executed twice. The profile SHA-256, source SHA-256, and ADE-state tree-metadata
fingerprint were identical before and after. No source design, ADE state, PDK, work library, or
simulation result was written.

## Repository and release reconciliation

| Item | Observed state | Reconciliation status |
| --- | --- | --- |
| GitHub repository | `PRIVATE` | Matches the current README, project state, and release operations document |
| Default branch | `main` at `4fad957753d1e432713b0d517de8a1906d715286` | Current WP-12 base |
| Annotated tag | `v1.0.0` peels to `8a0d44fab90e2095cc39322baef60fc09d741cd6` | Published tag is unchanged |
| GitHub release metadata | stable, published, not draft, not prerelease | Published state is valid |
| GitHub release body | begins with `not yet published` and ends with pre-publication statements | Stale text; external release-body edit is not part of WP-12 |
| `docs/RELEASE.md` | records the completed tag and private release | Consistent with actual publication state |

The release-body repair should be a separate, explicitly approved GitHub metadata update. It must
not move or recreate the tag, alter release assets, change the release date, or modify the immutable
`v1.0.0` source tree.

## Fixed profile evidence

| Field | Observed value |
| --- | --- |
| Profile ID | `actual-differential-amplifier-tb2-transient` |
| Registry SHA-256 | `dea735f2ba81ba5ca714df8dba1b752be1fa3ab67f5742c2cee76eb5af849a4b` |
| Repository/remote registry equality | yes |
| Fixed `VBIASN` | `300m` |
| Fixed `VBIASP` | `650m` |
| Caller-controlled variables | disabled |
| Source snapshot SHA-256 | `30e941fdc24ffdc30a8dc989ffb884cd2a5256797adfa5ce2b2c032af67d5351` |
| Latest successful actual manifest source SHA-256 | same as current source snapshot |
| Raw content included | no |
| Remote paths included | no |

## Parameter declaration and reference audit

The helper classifies a token on a source statement beginning with `parameters` as a declaration.
It reports only counts and booleans; it does not emit the containing statement or value.

| Parameter | Declared in source snapshot | Referenced outside a declaration | Total token count |
| --- | ---: | ---: | ---: |
| `VBIASN` | no | yes | 1 |
| `VBIASP` | no | yes | 1 |

Therefore the existing source snapshot consumes both names but does not define their values. The
current server-owned wrapper supplies `VBIASN=300m` and `VBIASP=650m`. This proves the binding needed
for snapshot-mode parameterization, but it does not prove that `300m` is the intended circuit
baseline.

## Snapshot and ADE-state freshness

| Evidence | Observed value |
| --- | --- |
| Source snapshot modified | `2026-08-20T09:18:28Z` |
| ADE state newest metadata modified | `2026-08-20T09:43:40Z` |
| Source minus state freshness | `-1512` seconds |
| Source not older than state | no |
| ADE-state metadata entries | 21 |
| ADE-state tree-metadata SHA-256 | `a6ead91891db7b1372e9e41515c76ac3b7dc8b2adeae281f4383d3c1ba32364d` |

The timestamp result does not prove that the circuit semantics differ. It does prove that the
snapshot cannot be claimed to represent the newest state metadata without a later fixed ADE
introspection or approved regeneration. The safe classification is
`SNAPSHOT_FRESHNESS_UNCONFIRMED`.

## Baseline conflict

The repository profile and wrapper use:

```text
VBIASN = 300m
VBIASP = 650m
```

The user previously reported a manually validated operating point of:

```text
VBIASN = 370m
VBIASP = 650m
```

WP-12 does not choose between them. Parameterized execution and sweep remain disabled until the
user approves an immutable baseline and the source/state freshness policy.

## Baseline approval form

Complete this exact decision package before WP-15 or any actual-profile parameter override:

```yaml
ACTUAL_PROFILE_BASELINE_APPROVAL:
  profile_id: actual-differential-amplifier-tb2-transient
  approved_source_sha256: 30e941fdc24ffdc30a8dc989ffb884cd2a5256797adfa5ce2b2c032af67d5351
  VBIASN:
    approved_default: 300m | 370m | <explicit other value>
    unit: V
  VBIASP:
    approved_default: 650m | <explicit other value>
    unit: V
  snapshot_freshness:
    choose_one: accept_current_snapshot | require_ade_state_regeneration
  approval_scope:
    - read_only_introspection
    - future_snapshot_profile_v2_planning
  approved_by: <user>
  approved_at: <ISO-8601 timestamp>
```

This form does not authorize a simulation, source/state write, profile implementation, sweep, or
release. Those actions retain their later work-package gates.

## Acceptance evidence

- Repository visibility and release metadata were checked read-only.
- The deployed profile registry hash equals the repository file hash.
- Both bias names have metadata-level reference evidence and no source declaration.
- Current source and latest successful actual-run manifest hashes match.
- Profile, source, and state fingerprints match across two consecutive audits.
- Design, ADE-state, PDK, and work-library writes: zero.
- Raw proprietary content, credentials, license values, and remote paths returned: zero.
