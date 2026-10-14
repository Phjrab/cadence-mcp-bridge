# Generic analog measurements: experimental operator path

## Common sampled slew and input-nulling extension, 2026-10-14

The user now delegates remaining QA testbench and definition choices. Earlier
requests for that scientific choice are superseded; no routine approval is needed.
This extension remains unpublished and opt-in. No public MCP schema, native asset
or original circuit is changed. PM still needs a valid loop testbench and actual
return-ratio qualification; ordinary AC phase is never promoted to PM.

`operator-analog slew` reads complete existing authenticated TRAN frames. Its
bounded operator definition binds the exact static stimulus/load hash, distinct
input/output IDs, expected measured input endpoints, initial/final plateau windows,
tolerance, minimum response and threshold fractions. It computes the signed
average output slope between unique10/90% crossings, with linear time interpolation,
observed brackets and a minimum four saved intervals across the duration. Wrong
stimulus, unsettled endpoints, repeated/reversed input, ambiguous crossing or poor
time resolution cannot produce a valid slope. No maximum derivative, intrinsic
amplifier slew limit, continuous-waveform or grid-convergence claim is made.
The ordinary TRAN summary is unchanged. Load description is an operator
interpretation bound to the static topology, not an independent load attestation.

Actual retained new inverter TRAN:70 samples, input0.5→0.7V, unchanged registered
load, output plateau windows0–4ns and15–20ns,1mV tolerance. Authenticated result
gives a signed sampled average−1.1008757205347075V/ns between5.1960377303ns and
5.8287278735ns; largest crossing sample gap0.1023128551ns. This is a QA step
response, not a manufacturer's slew rating. Repeat agrees, old frame/journal/
settings remain identical and ordinary UID500 preflight passes. The comparator
output is unsettled in the same windows; rejection is retained without widening
the tolerance. First harness failed on that rejection; v2 records each outcome.
This read uses0 simulations/extractions/reservations/native changes. Ledger stays
116 /14,110,687,232 bytes; native sources22/24. Evidence is private
`.tmp/post07-slew-retained-v1/` and `v2/`. This is source-host actual VM evidence;
exact installed feature and actual app checks remain distinct.

`operator-analog offset` reads3–32 distinct succeeded DC jobs, using exact plans,
source/PDK/static inputs/reader/conditions, allowing only the two named input
variables to vary. Both measured input voltages must match those registered
variables, all other bias values must agree, and common mode must match. Four
distinct differential terminals are required. Nonfinite/saturated/nonmonotonic/
duplicate inputs reject. The signed applied input difference at differential
output zero is interpolated only inside a measured bracket. Missing crossing is
null. This is nominal sampled input nulling, with no absolute precision, mismatch,
Monte Carlo or PVT qualification.

A new owned amplifier OA/ADE copy and actual common-renderer DC netlist now pass
normal-user preparation and effective-input verification. Original whole
MyDesignLib and original state are preserved. A preparation harness first lacked
the helper's `__file__` identifier; failure is retained. Registerable sources are
placed in a new0700 user workspace subtree, retaining preparation copies. An
initial copy into a0755 parent was rejected; no permission/guard was weakened.
Five DC points−1,−0.5,0,+0.5,+1microV at VCM0.5V and fixed0.32/0.702V bias are
prospectively registered for at most5 attempts/640MiB in the existing domain and
journals. Registration is local preparation, not yet actual execution acceptance.
All earlier results/bundles/grants and the shared counter remain protected.

Usage requires an exact bounded definition file and existing source IDs:

```text
python -I -m cadence_mcp_bridge operator-analog slew --experimental-analog --settings ABSOLUTE_SETTINGS --context OWN_CONTEXT --operation-id RETAINED_TRAN_ID --expected-plan-sha256 EXACT_PLAN --definition ABSOLUTE_SLEW_DEFINITION
python -I -m cadence_mcp_bridge operator-analog offset --experimental-analog --settings ABSOLUTE_SETTINGS --context OWN_CONTEXT --operations ABSOLUTE_DC_ID_PLAN_LIST --definition ABSOLUTE_NULLING_DEFINITION
```

The operations file is a bounded JSON array of `operation_id` and
`expected_plan_sha256` records; definitions use the closed models in
`generic_slew.py` and `generic_offset.py`. Neither command submits, extracts or
updates a journal. Definitions must describe the actual registered source, not
invent loading/feedback from a metric label. Public2.0.0 assets stay immutable.

The previous9d2e406 Linux check failed an exact floating-point roundtrip assertion
(100.0000000000002 vs100). A tight1e-12 relative test and a separately exact
threshold fixture fix this without changing the scientific crossing calculation.
Related164 host tests/Ruff/mypy107 currently pass; final source CI/package/installed
validation must be refreshed. These tests are synthetic, not native acceptance.

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

## Actual wider AC checkpoint, 2026-10-14

Exact unpublished source26be132 wheel9eed762a passes rights/content auditing and
isolated installed compatibility. Ordinary UID500 immutable registration update,
repeat0 and preflight pass with identical13 native assets, previous bundles/grants
and journal preserved. Two fresh owned-circuit AC jobs run10Hz–1THz at8 points per
decade (89 samples each); common OA copy/netlisting/effective input, Spectre,
automatic OCEAN extraction and normal result retrieval succeed.

The inverter has a sampled-reference3dB crossing estimate13,055,949,311.797434Hz,
bracketed by approximately10GHz–13.335GHz, relative to measured16.3402163273dB
at10Hz. This is QA sampled-transfer evidence, **not** a claim of useful amplifier
bandwidth, PDK model validity at those frequencies or grid convergence. The
comparator's extremely small reference transfer (-222.43829093dB) never crosses
downward in that interval; its estimate is null. This is not a useful comparator
bandwidth qualification. No optimization/specification target was invented.

Same-ID repeats in the original installed process spend0 additional attempts or
reservations. Normal-user final preflight passes. This experiment2 attempts/
256MiB; cumulative116 /14,110,687,232 bytes,16GiB remaining3,069,181,952 bytes.
Native source22/24 unchanged. Old OA/ADE/model/result/failure protections remain.
Private evidence `.tmp/post07-wide-v1/` preserves original inputs/receipts/frames.

A separate-process installed CLI read exposed a host-only settings-path type
error before contacting the VM. Its failure is retained; argparse now converts
the setting to Path, with a regression checking bounded rejection for a missing
configuration. This correction changes no native asset or simulation input;
rebuild/reinstall and repeat existing-ID reads only. Actual Claude acceptance,
PM/offset/slew testbenches and final review remain separate incomplete work.

## Corrected installed restart checkpoint, 2026-10-14

Source d03f3f14 fixes only the host CLI path type; native code, extraction script,
registrations and the two already successful jobs remain unchanged. Exact new
wheel SHA-256 is b9543a0d3a6fc63b2950273f0f0fe6d9bfdf188be16cadf7507f2148f22c85c5;
sdist is0d878f1326bb8461efecb86b1761af6dc3c6f2e7e19e53cf37b832c6c503f081.
These are private **unpublished feature** artifacts with2.0.0 metadata inherited
from the development branch, not replacements for GitHub's public2.0.0 assets.
Rights/content audit and isolated installed compatibility pass. Related133 tests,
Ruff/mypy105 pass; Linux CI now explicitly includes generic analog/grid tests.

Both existing job IDs pass installed CLI reads in separate processes. Same-ID
submit after restart dispatches0/reserves0; measurement/spectrum hashes agree
with the original installed process. Local journal/settings/registry/grant/provider
contents are unchanged, UID500 preflight and retained116/14,110,687,232 ledger pass.
Exact installed native SDK starts with96 tools and unchanged journals; no new
public analog tool or remote contact. SDK harness initially rejected an existing
legacy analog name by an overbroad assertion; corrected harness passes and the
failed attempt is retained. This is SDK evidence, not Claude app acceptance.
Hosted final SHA and independent review remain pending; PR158 stays draft.
