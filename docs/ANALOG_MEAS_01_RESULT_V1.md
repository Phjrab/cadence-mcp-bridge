# ANALOG-MEAS-01 result

Date: 2026-10-06. Starting main:
`e3fcfad30f35c68b1a90160d4d5f3a364436ab12` (merged STORAGE-MGMT-01 #117).
Feature branch: `feat/analog-meas-01`; containing feature PR
[#118](https://github.com/Phjrab/cadence-mcp-bridge/pull/118). All final gates pass;
integration uses this containing reviewed feature PR. Resulting remote SHA/tree
verification is retained privately after permitted merge, without a state-sync PR.
Package/server version stays 1.0.0; no tag/release is created.

## Implementation and API

Registry v6 adds operator-owned `analog_contracts` over the unchanged v5
design/variable/analysis/source-measurement/sweep framework. Exact compiled
definition and registered source hashes bind derived reads. Old registry schemas,
profiles and native analysis/admission identities remain unchanged. No implicit
analog reader is attached to an old registry. Fictional v6 example and public
JSON schema use original definitions and no private/vendor material.

Three additive read-only tools increase inventory from 63 to 66:

- `cadence_list_analog_measurements`
- `cadence_describe_analog_measurement`
- `cadence_analog_measurement_result`

All previous 63 complete tool schemas are equal. Results include method/unit,
qualification/reason, source-result digest and full native measurement provenance
with effective conditions. No frequency/formula/array/path/script/target input is
accepted. Existing admitted result reading validates source identity, PDK,
effective settings, arithmetic and protected fingerprints before derivation.
No new extractor, remote deployment, simulation, admission or reservation is added.

Sweep identity projects v6 into the entire validated v5 execution snapshot;
only new read-only analog declarations are separate. Every execution field still
contributes to the hash. Preserved v5 sweep admissions remain exactly retrievable;
changed execution scope changes the identity. Analog reads separately bind their
full compiled/source contracts. No replay ledger is reset or migrated.

## Measurement qualification matrix

| Measurement | Contract | Extraction | Evidence | Status |
| --- | --- | --- | --- | --- |
| Gain | Differential magnitude gain at 10 Hz | Validated AC sample, 20 log10 magnitude ratio | Preserved admitted native AC; 78.95196190699784 dB | QUALIFIED for that frequency and identified reference conditions |
| Bandwidth | First downward 3.0 dB crossing relative to measured 10 Hz gain | dB versus log10 frequency interpolation inside observed bracket | 487663.02407720726 Hz, bracket 398107.2–501187.2 Hz | PARTIALLY_QUALIFIED; sampled-reference estimate, no DC plateau or interpolation-error qualification |
| Phase Margin | Qualified loop-gain stability margin | No qualified loop-gain reader | Existing output AC phase is insufficient | UNQUALIFIED |
| Power | Delivered DC power from all signed identified supplies | Supply current extraction not qualified | Seven native DC node-voltage scalars do not establish supply currents | UNQUALIFIED |
| Offset | Input-referred/output definition and loop/stimulus conditions required | No qualified offset method | Ordinary differential DC output is not relabelled | UNQUALIFIED |
| Slew Rate | Rising/falling step response in a reviewed time/voltage window | No qualified step stimulus or bounded waveform interval | Current TRAN is opposed sinusoidal 1 kHz input, summary extrema only | UNQUALIFIED |

Observed AC values belong to pinned native revision/operating point, NN, 27°C,
VDD 1.0 V, applied 320/702 mV biases, verified existing input/common-mode/load
conditions. They do not characterize every PVT corner or the latest FS work copy.
Gain is neither DC nor maximum gain. Bandwidth is neither unity-gain nor
closed-loop bandwidth and uses 3.0 dB rather than exact half-power. These are
measurements, not design compliance or optimality claims. Specification evaluation
is always `not_evaluated`; no scientific target has been invented.

The workflow records evidence classes and precise future requirements. Phase
margin/slew need reviewed stimuli and readers; power needs signed supply-current
extraction; offset needs a selected scientific definition and conditions. Their
implementation scaffolding does not establish physical qualification.

## Verification

- Ruff and mypy: PASS, 42 source modules.
- All-group dependency sync: PASS.
- Focused analog/registered measurement/sweep lifecycle: 94 passes, one cache warning.
- Final full unit: 1,651 passed, four OS symlink skips, 57 warnings in 771.76 seconds.
- Security: 18 passes; locked dependency audit: no known vulnerabilities.
- Actual wheel/sdist license/content audits, isolated install, CLI/uninstall and
  three exported client settings: PASS, 66 tools; fictional v6 metrics stay
  UNQUALIFIED with null values and no admission.
  Wheel has 50 members and sdist 51, canonical Apache-2.0 license/notices,
  zero unexpected/private/protected-content findings; imported planning is excluded.
- Actual exported Codex/Claude SDK stdio: all 63 previous schemas equal;
  gain/bandwidth provenance matches the preserved native AC result; repeat/restart
  values equal. Protected native DC/AC/TRAN, fixture three-point sweep and storage
  inventory remain reproducible without a new simulator attempt.
- Closed malformed/stale/unknown/UUID4 inputs, unadmitted/wrong-source rejection,
  definition/source redirection, duplicate/colliding IDs, unchanged v1–v5 schemas
  and v5 sweep identity, zero/absent crossing and no extrapolation verified.
- Independent single-pole transfer checks both 10 Hz gain and the 3.0 dB crossing
  estimate; exact sample, first crossing and re-crossing semantics are explicit.

SDK/configuration evidence is not real Desktop application qualification.
CLAUDE_REAL_CLIENT_UNVERIFIED remains; no fresh Codex app qualification is claimed.
Actual Linux storage deletion remains NOT_RUN; this phase grants no deletion intent.

## Failures, corrections and evidence

Five corrections used against the active ceiling of 20; all earlier phase
histories stay preserved. Correction 1 resolves initial long definition strings,
import ordering and typed result mapping. Correction 2 resolves actual stdio sweep
lookup rejection caused by whole-registry hash drift after adding read-only analog
metadata, using the complete validated v5 execution projection and explicit tests.
Correction 3 restores the regression test's digest import removed earlier as unused.
Correction 4 updates the old exact-tool-name inventory expectation for the three
additive analog tools; runtime/source seals stay unchanged. Earlier full-suite
failure and corrected inventory rerun (33 passes) are retained; final whole-suite
gate passes on the corrected checkout.
Correction 5 also updates the separate exact read-only-name expectation revealed
by that rerun. All three analog annotations were already correctly read-only;
only old test expectations change.
Failed tests/transcripts, first E2E registry/intent/journal and source seals remain
private immutable evidence; a new E2E version verifies the correction.

The initial `uv run pytest` collection entry point resolved an external `scripts`
namespace; canonical `uv run python -m pytest` restores the repository import
context without changing test scope. The first E2E authority check failed before
remote contact because Git safe-directory/runtime settings were absent; restoring
the existing repository-specific environment resolved it without changing guards.
An initial patch with a missing documentation context applied no files and was
reissued with verified context. These recovery records do not reset budgets.

## Resources, integrity and limitations

New Spectre attempts: 0; cumulative 62/500.
New result reservations: 0; cumulative 7,114,588,160 / 10,737,418,240 bytes (10 GiB).
New remote deployment, extraction and historical deletion: 0.
Original source/ADE/PDK, saved jobs, accounting and all 1,024 earlier private
evidence records remain equal. Native admission journal bytes are unchanged.
Elapsed ceiling remains removed; existing EDA lock and disk floor remain binding.

Another operator can register reviewed derived analog IDs in the same registry,
inspect exact definitions/missing requirements and reuse admitted native evidence
without exposing expressions or raw results. Only the compiled reference physical
reader is qualified. New designs/PDKs/Cadence versions, four missing physical
metrics, real Desktop E2E and imported planning rights review remain limitations.
Apache-2.0 boundaries, LICENSE/NOTICE/THIRD_PARTY_NOTICES, version and release state
remain unchanged. No proprietary content, client fork or arbitrary execution is added.

Recommended next phase: SPEC-CONTRACT-01, then release-readiness reassessment.
Ask once at completion; no target registration, optimization or next phase is
activated by this result.
