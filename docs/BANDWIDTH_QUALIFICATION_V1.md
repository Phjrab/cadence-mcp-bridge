# Bounded reference bandwidth grid study v1

## Definition and scientific limits

`bandwidth-grid-study-v1` supplements the original analog bandwidth definition.
Both use the differential transfer `(Vop - Vom)/(Vp - Vm)`, its gain at exactly
10 Hz, a **3.0 dB decrease**, the **first observed downward crossing**, and linear
gain in dB against log10 frequency interpolation. An exactly sampled crossing
uses that sample. No extrapolation is allowed.

This is not the exact half-power decrease `10 log10(2)`, unity-gain bandwidth,
closed-loop bandwidth or a newly qualified DC/continuum low-frequency bandwidth.
The original analog contract, result, specification binding and
`PARTIALLY_QUALIFIED` status remain unchanged.

The study reports the sampled gain span at 10–1,000 Hz, sampled peaking above
the 10 Hz gain, downward-crossing count, first containing sample bracket and
interpolation. `NO_CROSSING`, `MULTIPLE_DOWNWARD_CROSSINGS` and
`INSUFFICIENT_DATA` prevent a convergence claim. Malformed axes, nonfinite data,
wrong references and oversized input fail closed.

Before observing refinement results, the plan fixes these diagnostics:

- 10, 50 and 100 points/decade; new runs only at 50/100, 10 Hz–1 MHz.
- Sampled 10–1,000 Hz gain span and observed peaking each <=0.05 dB.
- Reference gain agreement across grids <=0.001 dB.
- Successive change decreases; the last relative change is <=0.1%.
- Containing brackets become narrower relative to their estimates.

These are empirical study criteria, not user design goals or device ratings.
`OBSERVED_WITHIN_0_1_PERCENT` describes those particular grids. The successive
change is **not an absolute or relative error bound**. Printed native samples
also have finite formatting precision. The containing bracket describes sampled
data; it is not proof of a unique continuous crossing between samples. No
solver-tolerance study, rigorous interpolation-error bound, or broad PVT
qualification follows. All study results remain `PARTIALLY_QUALIFIED`,
`absolute_error_bound_hz=null`, `spec_evaluation=not_evaluated`.

## Fixed operator execution

`scripts/bandwidth_qualification.py` is an operator workflow, not a caller-script
or filesystem MCP capability. The versioned [policy](policy/BANDWIDTH_QUAL_V1.json)
and explicit private delegation bind the exact remote bytes. A checkout alone
does not activate it. It admits only two fixed grids over the one reviewed
preserved native AC operation.

Before execution, verify installed AC `dec` controls, admitted input/PSF, protected
source/ADE/PDK, historical jobs and current ledger. Each new owned job copies the
exact native input and changes only its one AC line. Reversing that change must
reproduce the original input SHA256 before reservation and at result verification.
No OA/ADE, source circuit, model, other analysis or simulator option changes.
The source saved biases300/650 mV remain distinct from the existing effective
320/702 mV candidate. Conditions are NN/27 C/VDD1 V, original stimulus/load.

Reuse the shared EDA lock, existing cumulative ledger, disk floor (greater of
2 GiB/10%), exclusive durable admission and reservation marker, atomic ledger
transaction, fixed process timeouts and bounded extraction. At most two attempts
and two128 MiB reservations are added to existing usage. Existing/uncertain
admissions are denied; no blind retry, counter reset or refund. No new native
result schema: separately versioned refinement frames contain exactly251/501
samples for the same four fixed signals. Unknown extra signals, malformed frame,
wrong axes or effective AC excitation are rejected. Completion receipts bind
every owned entry; links, special objects and escape paths fail closed.

Preserve raw jobs/PSF as phase verification evidence outside ordinary cleanup
candidates. There is no deletion or compaction authority.

### Historical counter domains

The sealed FS-SIZING-SCREEN-02 postflight knows only its own attempts. After this
study advances the shared ledger, that historical whole-phase conservation check
returns FAIL; its failure is retained and its original source/policies are unchanged.
The study's `postflight()` composes original protected checks, exact historical
request/status/whole-job fingerprints against the verified pre-study baseline,
native protection checks, and strict ordered historical-plus-refinement reservation
identities. It verifies the actual64/7,383,023,616-byte ledger without calling the
historical check a PASS, monkeypatching its usage function or resetting the ledger.
This is a phase completion verifier, not a new general execution accounting engine.

## MCP read

`cadence_bandwidth_study_result(request)` accepts the existing `AnalogQuery`:
registered design/bandwidth measurement IDs, current original analog contract
SHA256 and admitted UUID4. Get the contract from
`cadence_describe_analog_measurement`. Only the reviewed reference AC operation
has a fixed refinement receipt. Registry/PDK/admission/source checks precede the
artifact read; wrong metric, operation, stale contract, source or receipt fail closed.

The response includes the **unchanged original result**, a versioned study
definition/hash, three bounded summaries, empirical convergence, exact extraction
digest and two refinement input/PSF/frame/quality/reservation provenance records.
No raw vectors, private paths, caller frequencies, grid controls, formulas,
simulator command, execution, registration or target input are accepted.
Private helper/transport errors are redacted. Completed reads do not reserve
resources and permit a valid exhausted500/10 GiB ledger. Uncertain/invalid ledger
state is still denied. Reads remain identical across SDK server restart.

All previous75 MCP schemas and registry v1-v8 contracts remain exact. The new
[schema snapshot](contracts/MCP_BANDWIDTH_STUDY_V1_SNAPSHOT.json) is additive.
See the [phase evidence](BANDWIDTH_QUAL_02_RESULT_V1.md).
