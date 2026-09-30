# Native 320/702 mV candidate comparison

Date: 2026-09-30. User-selected phase: `NATIVE-CANDIDATE-01`.
Outcome: candidate application and native DC/AC/TRAN characterization verified.
Specification evaluation: `not_evaluated`; no numeric performance target was added.

## Conditions and provenance

The source/ADE baseline completed through PR #93 and PR #94 is reused. Its saved
300/650 mV variables remain unchanged. Each candidate job uses an owned state
copy whose only variable changes are VBIASN=320 mV and VBIASP=702 mV. Native
state loading and generated input separately verify the actual candidate values.
Neither original ADE state nor any OA cellview is saved.

VDD=1.0 V, NN, 27 C, input common mode 0.5 V, source/copy/model/state/circuit
fingerprints, circuit connections and load remain bound to the verified native
baseline. The original state enables DC only. AC range and trap TRAN controls
are explicit job session settings; they are not described as saved enablement.

AC uses opposed complex inputs +0.5/-0.5 V and differential excitation 1 V.
It covers 10 Hz through 100 MHz at ten points per decade. TRAN uses opposed
1 kHz sine inputs, each 50 mV peak about 0.5 V, giving differential 100 mV peak.
It covers 0 through 4 ms with maxstep=10 us and `method=trap`. The same controls
were used in the reused baseline trap comparison.

## Measured comparison

| Measurement | Native 300/650 mV baseline | Native 320/702 mV candidate |
| --- | --- | --- |
| DC output common mode | 0.07352685 V | 0.2277073 V |
| DC output differential | 0 V | 0 V |
| AC gain at 10 Hz | 33.561506 dB | 78.951962 dB |
| AC gain at 1 kHz | 33.561492 dB | 78.951943 dB |
| First observed −3 dB bracket relative to 10 Hz | 501187.2–630957.3 Hz | 398107.2–501187.2 Hz |
| AC points | 71 | 71 |
| Trap TRAN differential min/max | −0.9951887853 / +0.9951859125 V | −0.9992316221 / +0.9992359621 V |
| Trap TRAN common mode min/max | 0.07352040135 / 0.49967482855 V | 0.22770733677 / 0.50000671403 V |
| Trap TRAN points | 604 | 754 |

The −3 dB entries are adjacent sampled-frequency brackets, not interpolated
cutoff values. Candidate small-signal gain is higher and its first −3 dB crossing
is in a lower sampled interval. These are observations, not an optimization or
specification PASS. TRAN approaches the supply-limited output region at the
chosen large excitation; it does not establish small-signal linearity at that
amplitude. Adaptive grids differ, and full waveform equivalence is not claimed.

DC, AC and TRAN each completed with zero errors, two allowlisted CMI-2477
warnings and zero notices. All finite, aligned AC vectors and TRAN node time
axes were checked. Independent private calculations verified complex gain,
magnitude, dB and phase at all 71 points; individual AC input vectors; DC common
and differential arithmetic; and TRAN supply, sine stimulus, common mode,
strictly increasing time and output extrema. Frame digests match their results.

No numerical performance target, settling, THD/SNDR/ENOB, Noise/STB, phase
margin, PVT/statistics, added-load behavior, integration-method convergence or
LVS equivalence is qualified by this phase.

## Preserved failure and first correction

| Version | Observed outcome | New Spectre attempts |
| --- | --- | --- |
| v1 / initial | Native candidate DC completed. Native AC simulation completed; extraction failed because the reused helper referenced a directory without its AC template | 2 |
| v2 / correction 1 | Rebinds the extraction template directory. Copies the failed AC job and PSF into a new owned job and performs extraction only. Native candidate trap TRAN completes | 1 |

The v1 failed AC job, PSF, local reserved journal and failure checkpoint remain
unchanged. Recovery verifies the exact prior netlist result, applied input,
protected snapshots, reservation, simulator quality and nonempty PSF before
copying. It rejects pre-existing extraction artifacts and any replay. Source
and copy content hashes, preserved job/PSF/DC trees, input hashes and the combined
AC size bind the recovery. No AC netlist or simulation is rerun. The two AC
directories together fit the original 128 MiB reservation.

Fixed operator actions, immutable versioned assets, exact policy/file digests,
private user delegation, consumed correction records, predecessor checks,
exclusive journals and the shared run lock gate execution. The candidate change
has consumed one of its three corrections. Prior native AC/TRAN remains at
three of three; prior DC remains at five of six. No budget or elapsed limit reset
occurred. No generic runtime command or new public MCP tool was added.

## Resources, checks and evidence

Three new Spectre attempts increased cumulative use from 18 to 21 of 100.
Reserved result bytes are 1,611,661,312 under the 5 GiB ceiling. Candidate DC,
preserved failed AC, recovered AC and TRAN jobs occupy 267386, 277701, 308810
and 663604 bytes respectively. Final free space is approximately 24.05 GiB,
above the greater-of-2-GiB-or-10-percent floor. Active EDA count is zero; paid
resource usage is zero. Final postflight rechecked protected original/PDK/history
fingerprints, reused results and the complete preserved v1 failure/DC trees.

Focused latest validation: 154 tests passed, including 46 candidate tests.
Ruff and strict mypy passed. Actual deployment verified exact manifests, Bash
syntax and Python 2.6 compilation. The security gate passed its 18 tests and
the frozen dependency audit reported no known vulnerabilities. The secret
preflight passed for 611 files including this report. The full regression
against the final correction passed 787 tests with eight opt-in integration
skips. A subsequent focused rerun passed all 154 tests after refining the
missing-predecessor fixture to exercise its intended guard. Skips are not PASS.
Real candidate execution is the separately scoped live validation above.

Immutable private final result: `.codex/native-candidate-01-result-v1.json`,
SHA-256 `8fccdd046961894e45a9788074b815839ec466892cae558fcd6ab716ebec5c88`.
The prior native baseline remains bound to SHA-256
`b09d1faa742dda4f39371a4373057ce58ef780796f184f84a58571c30e4f9e82`.
Private frames, raw design data and execution journals are excluded from the PR.
Only reviewed conditions, aggregate measurements, quality, implementation and
resource summaries appear here.

## Phase exit

The fixed candidate is now actually applied and characterized in native owned
ADE jobs at the verified conditions. The original saved state remains 300/650 mV.
No candidate promotion to the original design or specification compliance is
claimed. Ask once before another major phase; no additional voltage range,
sweep, optimization or statistical analysis is active.
