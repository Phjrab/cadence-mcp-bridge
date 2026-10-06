# Fixed reference step study v1

ANALOG-SLEW-01 uses a separate versioned step-result reader. Original native
TRAN, analog slew definition and all earlier contracts remain unchanged. This
is an open-loop differential output transition study, with no added external
load. It does not establish a conventional closed-loop or specified-load slew
rate. Saturated endpoints, nonlinear transition and missing qualification are
reported explicitly. No numerical target is registered or evaluated.

## Preselected experiment

Same reference topology/PDK NN,27 C,VDD1 V,effective bias320/702mV; original saved
300/650mV and OA/ADE/PDK stay exact. Two opposite ideal pulse sources retain
input common mode0.5 V: Vp0.45→0.55 V, Vm0.55→0.45 V at2 us, return at6 us.
This stays within the prior sinusoidal input excursion; it is not a qualified
continuous electrical range or a reliability guarantee. Stop10 us, original
trap/tolerance/save controls, initial DC solution at the first pulse endpoints.
The output is Vop−Vom; both output directions must be measured separately.

| Case | Maximum timestep | Input edge |
| --- | --- | --- |
| coarse |10 ns |1 ns |
| medium (original plan, NOT_RUN) |5 ns |1 ns |
| fine (original plan, NOT_RUN) |2.5 ns |1 ns |
| fast (original plan, NOT_RUN) |2.5 ns |0.5 ns |
| medium (actual refinement) |200 ps |1 ns |
| fine (actual refinement) |100 ps |1 ns |
| fast (actual refinement) |100 ps |0.5 ns |

The coarse run exposed an insufficient crossing bracket. Before observing any
remaining result, version4 fixes the remaining three cases to200/100/100 ps.
The original unexecuted grid intent and all first failures remain preserved.
No fifth attempt is authorized. Up to160,000 native samples per signal and a
64MiB private frame bound fit within each128MiB owned reservation; public
responses contain only scalar diagnostics. Coarse keeps its original parser.

Maximum four new attempts and four128MiB cumulative reservations. Shared500
attempt/10GiB ledger, EDA lock, worker/disk guards, durable one-shot admissions,
per-process timeout/file bounds and reverse original-input hash verification
precede execution. New raw results are protected scientific evidence. A failed
or uncertain job is retained and investigated; no automatic rerun/refund/reset.

## Definition and diagnostic criteria

Plateau reference means use fixed windows1–1.5 us,5–5.5 us and9–9.5 us. Each
needs at least eight native samples. The transition's endpoints define20% and
80% output voltages; one monotonic upward normalized crossing of each level is
required, with linear time interpolation inside observed brackets only. Return
signed0.6×absolute output swing/(t80−t20) in V/s, and separate rise/fall. It is
not the largest adjacent slope. A missing crossing is never extrapolated.

Diagnostics fixed before execution: swing≥0.1 V; plateau span≤0.1% of swing;
overshoot≤2%; at least eight native samples within20–80%; endpoint crossing
brackets≤1/8 of the interval. Missing/sparse data, multiple crossings, unsettled
or ringing output produces no rate. Equal20% subwindow secants provide a
linearity ratio; ratio>1.2 is nonlinear, not constant-slope slew. Crossing while
the input is changing flags input-edge overlap. Timestep agreement and faster-
edge agreement each require≤1% relative change. Three-level convergence cannot
be assessed when coarse has no valid rate; do not claim decreasing errors from
that missing value. The actual refined pair supports a two-resolution agreement
observation only.
These are empirical study diagnostics, not absolute error bounds or user specs.

Even numerical convergence in this unloaded open-loop saturation test remains
PARTIALLY_QUALIFIED. It does not qualify another load, feedback condition, PVT,
device rating, input range, or the original generic slew/specification contract.
Further closed-loop/load/constant-slope scientific qualification is separate.

## Operator and protection boundary

`scripts/slew_reference_audit.py` (version2 authority) reads only the pinned preserved TRAN and two
installed help topics. `scripts/slew_qualification.py` permits only deployment,
the four fixed cases, result and postflight, plus finish-only recovery of the original coarse result.
`recover-coarse` never executes Spectre or OCEAN. Exact policy/deployment hashes and
private explicit user delegation are required; a clone is not execution authority.
No caller path, netlist, script, expression, signal, amplitude or timing is accepted.
Each new input reconstructs the entire original input hash when the two source
and one TRAN substitutions are reversed. Whole immutable completion receipts
and a separately composed exact reservation sequence protect historical jobs,
replay, sizing and bandwidth evidence. Old temporal conservation checks remain
unchanged; they cannot be reported PASS after the ledger advances.

Private native vectors, circuit/help/vendor/PDK content and paths are excluded
from public results and distributions. No storage deletion, new optimization,
source editing, release/tag/publication or client-specific execution is added.
Apache applies only to original bridge code. Imported rights remain
LEGAL_REVIEW_REQUIRED; PUBLICATION_NOT_AUTHORIZED. Claude actual app and other
Cadence/PDK/host qualification remain user-deferred.


## Durable read interface

`cadence_slew_study_result(request)` accepts the existing registered
`analog-slew-rate` design/contract hash and the preserved admitted TRAN UUID4.
It checks the original analog hash, registered `tran-summary` contract, PDK,
analysis/admission, pinned input/PSF and the exact four-case extraction digest.
An unregistered design, unadmitted operation, stale contract, altered source,
extra field, different result or private transport failure is denied. It cannot
start a step experiment or extraction. Original `cadence_analog_measurement_result`
still returns UNQUALIFIED/null for generic slew; specification behavior is exact.

The separate `slew-read-v2` reader checks every original job fingerprint and all
whole completion receipts, reverse input identity, exact historical reservation
markers and bounded parsed summaries. It tolerates separately validated later
native job IDs and a later cumulative ledger within500/10GiB, preserving every
old job exactly. The strict version4 phase conservation verifier remains temporal
and unchanged. Neither reader discounts prior reservations or changes historical
counters. Future-ledger/job extension is tested synthetically; no later-phase
simulation is fabricated to qualify it. Actual current68 replay and SDK restart
are separately verified. Both reads share the EDA lock and reject active workers.

The public definition/hash identifies open-loop, Vop−Vom, intrinsic-only load,
input/condition/plateau/window/units and empirical criteria. Each run retains
input/PSF/frame hashes, original source hashes, its original counter and status.
Each direction reports signed V/s and magnitude V/us, pairwise timestep and edge
agreement and nonlinear/insufficient status. No raw waveform, PSF, proprietary
source, private path or false PASS/FAIL is returned. Client transport is standard
stdio; the actual live Codex69-name catalog and empty analog registry lacks this new tool/analog registry.
Current-source SDK77-tool/v8 is verified independently of actual application E2E.
See [phase result](ANALOG_SLEW_01_RESULT_V1.md).
