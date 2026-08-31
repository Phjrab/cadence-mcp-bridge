# Next Version Scope

## Target

The next feature line is a security-preserving extension beyond `v1.0.0`. The working release
target is `v1.1.0`, but no version change, tag, or GitHub release is authorized by WP-12.

The practical target is bounded parameterized execution and one-dimensional sweep for the fixed
actual differential-amplifier profile. Full ADE L state-driven execution remains a later,
capability-gated mode.

## Current gate state

| Gate | State | Required evidence or decision |
| --- | --- | --- |
| Repository visibility | passed | Private repository verified |
| Release publication | passed with stale body text | Separate approval required to repair only the GitHub release description |
| Actual snapshot binding | passed | `VBIASN` and `VBIASP` are referenced but not declared in the source snapshot |
| Source reproducibility | passed | Current source SHA-256 matches the latest successful actual manifest |
| Snapshot freshness | unresolved | WP-13 confirmed the source remains older than ADE-state metadata; approved regeneration or explicit snapshot policy is needed |
| Immutable bias baseline | discovered, unapproved | ADE state reports `300m/650m`; user approval is still required before parameterized execution |
| ADE analysis contract | drifted | state1 has `dc` enabled and `tran` disabled while the reviewed profile expects `tran` |
| Actual variable contract | not started | WP-14 and explicit user approval |
| Actual output contract | not started | Exact logical outputs and extraction policy must be approved |
| Sweep execution | disabled | Requires WP-15 through WP-17 gates |

## Planned work-package sequence

1. WP-13: fixed read-only ADE L profile introspection (completed on feature branch).
2. WP-14: actual parameter binding and approval package; no variable enablement.
3. User approval: immutable baseline, variable ranges, steps, and run limits.
4. WP-15: separate parameterized snapshot profile v2; v1 remains unchanged.
5. User approval: exact output IDs and measurement definitions.
6. WP-16: bounded scalar and waveform-summary extraction.
7. WP-17: first-class, single-dimension sweep with deterministic plans and point budgets.
8. WP-18 and later: capability-gated ADE state mode, expanded analyses, multidimensional sweep,
   and bounded adaptive planning.

Optional actual ADC integration is out of scope until a distinct ADC testbench and measurement
contract are supplied. The differential-amplifier profile must never be treated as an ADC.

## Non-negotiable boundaries

- No generic shell, SSH command, SKILL evaluation, OCEAN evaluation, or caller-controlled path.
- No source design, ADE state, PDK, shared-library, or preserved evidence write.
- No raw netlist, state, PSF, PDK, credential, license value, or unrestricted log response.
- All profiles, variables, analyses, corners, outputs, and measurements use closed registries.
- Global Spectre concurrency remains one until separately justified.
- Automatic retry remains disabled.
- Each work package uses a feature branch and stops after verified push unless its exact PR is
  explicitly approved for merge.
- `v1.0.0` tag and release remain immutable.

## WP-12 outcome

Runner 0.17.0 adds an operator-only `actual-profile-baseline-audit` command. It accepts no
arguments, executes no Cadence binary, writes no design or runtime artifact, and emits one bounded
JSON object containing only profile/source/state hashes, timestamps, parameter-reference metadata,
and freshness comparisons. It is not exposed as an MCP tool.

The audit outcome is `BASELINE_DECISION_REQUIRED` and `SNAPSHOT_FRESHNESS_UNCONFIRMED`. These
conditions do not prevent the next read-only introspection work package, but they block
parameterized actual execution and sweep implementation.

## WP-13 outcome

Runner 0.18.0 and `cadence_inspect_ade_profile` performed fixed read-only introspection of state1.
The source OA structure is `35/14/8`; state variables are `VBIASN=300m` and `VBIASP=650m`; model
section and temperature match `NN` and 27 C; no named output is configured. Source, state, PDK
model, and source snapshot fingerprints were identical before and after and no lock remained.

The state has `dc` enabled and `tran` disabled despite the profile's transient contract, and the
source snapshot remains older than state metadata. The structured outcome is `PROFILE_DRIFT` with
`analysis_mismatch` and `snapshot_freshness_unconfirmed`. WP-14 may document exact approval
choices, but no parameterized execution, profile rewrite, snapshot regeneration, or sweep is
authorized.
