# Registered analog measurements v1

Current continuation: [ANALOG-POWER-01](ANALOG_POWER_V1.md) separately qualifies
one preserved DC supply-power reader. This historical analog v1 contract and
its UNQUALIFIED power result are unchanged; current v7 goals still bind v1.

ANALOG-MEAS-01 extends the existing measurement architecture with local derived
definitions. Registry v6 adds `analog_contracts` to v5; unchanged design profiles,
variable/analysis/source-measurement hashes and fixture sweep contracts remain
the only execution routes. Explicit old registries do not gain implicit readers.
The operator owns registration outside MCP; no caller expression, script, path,
sample array, frequency, unit or target is accepted by these new tools.

## Definitions and qualification

| Measurement | Evidence class | Definition / requirement | Qualification |
| --- | --- | --- | --- |
| Gain | IMPLEMENTABLE_FROM_EXISTING_EVIDENCE | `20 log10(abs(Vout_diff / Vin_diff))` at the validated 10 Hz AC sample | QUALIFIED only for this measured frequency and admitted native conditions |
| Bandwidth | IMPLEMENTABLE_FROM_EXISTING_EVIDENCE | First downward 3.0 dB crossing relative to measured 10 Hz differential gain; dB interpolation against log10(frequency) inside the observed bracket | PARTIALLY_QUALIFIED when a finite crossing exists; no interpolation-error bound or DC plateau qualification |
| Phase Margin | REQUIRES_STIMULUS_CHANGE | Review loop break/injection or STB, loading, sign and loop-gain crossing | UNQUALIFIED: output AC phase is not loop gain |
| Power | REQUIRES_EXTRACTION_WORK | Identify all supplies and current directions; qualify voltage and signed supply-current extraction before summing delivered V × I | UNQUALIFIED: native DC reader has seven node voltages, no qualified supply-current set |
| Offset | REQUIRES_USER_SCIENTIFIC_INPUT | Select input-referred/output definition, loop conditions and zero-crossing or other qualified method | UNQUALIFIED: ordinary DC output is not offset |
| Slew Rate | REQUIRES_STIMULUS_CHANGE | Review step amplitude/output signal, rise/fall directions, measurement interval and voltage/percentage windows; qualify bounded waveform extraction | UNQUALIFIED: current TRAN stimulus is opposed 1 kHz sinusoidal input and results contain extrema only |

Gain is not maximum, DC or asymptotic low-frequency gain. Bandwidth is not
unity-gain, closed-loop bandwidth or an exact half-power crossing: the definition
uses **3.0 dB**, not 10 log10(2). The first downward crossing is intentional even
if a later crossing exists; it makes no monotonicity or universal bandwidth claim.
Missing/zero reference gain, nonfinite bracket or no crossing in the registered
10 Hz–100 MHz spectrum returns UNQUALIFIED without extrapolation. A sparse
crossing estimate cannot establish a conventional low-frequency bandwidth by itself.

## Operator configuration

Use the existing local registration and launch workflow:

```powershell
uv run cadence-mcp-bridge design schema --schema-version 6
uv run cadence-mcp-bridge design validate --registry C:\private\designs-v6.json
uv run cadence-mcp-bridge design register --registry C:\private\designs-v6.json --output C:\private\registered-v6.json
```

Each derived contract allowlists a design/measurement/metric identity and exact
compiled definition hash. Gain/bandwidth may bind an exact registered native AC
measurement ID/hash. Duplicate metrics/IDs, source collisions, foreign designs,
source hash drift, wrong analysis, arbitrary definitions and attempts to grant an
unqualified metric a reader are rejected. A source-free gain/bandwidth declaration
stays unqualified. Registration neither changes a design profile nor adds execution
authority. v1–v5 schemas and plans are preserved; normal startup takes one frozen
registry snapshot. The reference example constructor is `reference_analog_registry()`.

Sweep durable identity in v6 uses its validated complete v5 execution snapshot.
Only the new read-only analog declarations are excluded; every design, variable,
review, analysis and original measurement field still contributes. Analog reads
bind their own full derived-contract and source hashes. This preserves admitted
v5 sweep lookup after adding analog metadata without accepting execution drift.

## MCP workflow

1. `cadence_list_analog_measurements(design_id)` lists up to six registered
   definitions, source IDs, current contract hashes and qualification requirements.
2. `cadence_describe_analog_measurement(request={design_id, measurement_id})`
   describes one allowlisted definition.
3. `cadence_analog_measurement_result(request={design_id, measurement_id,
   operation_id, expected_contract_sha256})` derives from one completed admitted
   UUID4. Missing scientific qualification returns UNQUALIFIED and a null value.

Admission, result identity, PDK compatibility, effective input and native-result
validation remain in the existing analysis/measurement path. Unadmitted, stale,
malformed, unknown or failed source requests remain errors, not specification FAIL.
The derived result includes definition, unit, status, reason, source-result hash,
native provenance and effective corner/temperature/VDD/bias/revision/settings.
For AC derivation it also includes reference frequency/gain; bandwidth includes
the observed frequency bracket. Repeated reads/restart use the same admission and
result without new journals, reservation, extraction or simulation.

`spec_evaluation = not_evaluated` is unconditional. No targets, PASS/FAIL, optimization,
candidate generation or schematic changes are included. Existing synthetic ADC
power/offset tools remain fixtures and do not qualify physical amplifier metrics.

## Deployment, security and limits

Only local bridge code changes; no guest helper/deployment is required. One
reference Cadence/PDK route is qualified; other versions/PDKs remain deferred.
Read-only stdio clients use the same server with unchanged execution guards.
CLAUDE_REAL_CLIENT_UNVERIFIED remains; SDK transport/configuration verification
does not prove Desktop app E2E. Source/ADE/PDK, accounting and prior evidence stay
protected. Storage cleanup remains separately selected/authorized; this phase
does not delete data, reset counters or automatically compact results.

Apache-2.0 covers original bridge code only. No Cadence/PDK data is added; imported
planning LEGAL_REVIEW_REQUIRED remains. No release/tag/version bump is implied.
See [phase result](ANALOG_MEAS_01_RESULT_V1.md).
