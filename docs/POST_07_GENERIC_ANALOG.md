# Generic analog measurements: experimental operator path

This unpublished POST-07 feature is separate from immutable public v2.0.0.
It reuses the standard VM's registered generic reader and terminal/content
verification. No circuit-specific Python reader, new MCP tool, OCEAN invocation,
netlisting or Spectre run is added by measurement lookup.

## Scientific definitions

`operator-analog requirements` explains eligibility and current blockers.
Bandwidth here means the first downward magnitude crossing after a selected
**measured** reference frequency, at the reference gain minus an explicit positive
drop (default 3.0 dB). Complex registered output voltage is divided by measured
complex input voltage at every saved AC sample. The complete registered frequency
grid and nonzero input are checked before the host computes the crossing.

Interpolation is linear in dB against log10(frequency), inside the observed
bracket only. The result retains definition/hash, measured reference, threshold,
bracket, grid range/count, registered transfer, effective conditions, source job,
plan, input/frame/reader/extraction hashes and native provenance. Missing crossing
returns `NOT_OBSERVED_IN_SAMPLED_RANGE` with a null value, not zero, infinity or an
extrapolated estimate. Zero/nonfinite transfer, wrong reference or incomplete
grid rejects. A computed crossing is a sampled-reference estimate; no DC plateau,
continuous-response, discretization uncertainty or grid convergence is claimed.
The ordinary result and legacy fixed analog contracts remain unchanged.

PM remains blocked pending an actual validated loop-gain testbench, injection,
loading and sign definition. Output AC phase is insufficient. Offset requires
an explicit input-referred/output definition, common mode, feedback state and
threshold method. Slew requires actual step stimulus, loading, amplitude,
direction, settled endpoints, thresholds and a waveform window. None of those
three measures is qualified by inverter/comparator extrema, synthetic calculations
or the legacy reference circuit.

## Use

Use the existing operator settings and a retained succeeded registered AC job:

```text
python -I -m cadence_mcp_bridge operator-analog requirements
python -I -m cadence_mcp_bridge operator-analog bandwidth --experimental-analog --settings ABSOLUTE_OPERATOR_SETTINGS --context OWN_CONTEXT --operation-id RETAINED_AC_ID --expected-plan-sha256 EXACT_PLAN --reference-frequency-hz 10 --drop-db 3
```

The command reads the existing journal without creating or updating it and makes
only the provider's bounded `result` call. It never submits/retries a simulation
or recovers extraction. Expired execution scope is not refreshed for result
lookup. Failures report uncertain remote-contact status honestly. The explicit
experimental flag is required; MCP/import/doctor do not activate this extension.

## Evidence checkpoint, 2026-10-14

Related host tests132 PASS, Ruff and mypy105 files PASS. Numerical fixtures are
synthetic evidence only. An initial test fixture import and then a reason-string
assertion failed and were corrected; this did not change deployed native source.

Actual source-host read-only checks retrieve complete16-point 10Hz–1MHz AC frames
from two separately registered new inverter/comparator circuits on the standard
VM. Both report NOT_OBSERVED, because no downward3dB crossing occurs in that
interval. Repeat results agree; original frames, local settings and journals are
unchanged. Ordinary UID500 preflight passes before/after. Actual ledger remains
114 attempts /13,842,251,776 reserved bytes. New simulations/extractions/reservations
and native source changes are0. This is actual retained-frame extraction/projection
evidence, not fresh bandwidth-crossing, exact installed build or actual Claude
qualification. Evidence is private `.tmp/post07-readonly-v2/`; the failed local
relative-path harness remains in v1.

Next bounded experiment: prepare exact installed host artifact and two common
registered AC routes with a wider finite frequency interval, preserving original
OA/ADE/PDK, existing ledger/journals and all earlier native bundles/grants. Record
exact input/expected reservation/stop conditions before admission; retain any
failure. A wider interval still cannot qualify PM, offset or slew. The feature
remains partial/experimental until relevant actual criteria pass.
