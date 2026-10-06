# Finite reference bias grid v1

BIAS-RANGE-QUAL-01 starts at merged Offset main
`5e89fd0fb03eb4975c2be10df852b49ea42a22c5`, branch `feat/bias-range-qual-01`.
The user explicitly delegated this phase and the subsequent real Sweep and
Specification phases continuously. Prior Offset evidence and correction history
remain immutable; no new goal, deletion or publication authority follows.

## Scientific scope

Only VBIASN **0.319 / 0.320 / 0.321 V** is reviewed. VBIASP0.702 V,
VDD1 V, input common mode0.5 V, NN/27 C, original topology/no added external
load remain fixed. Original saved300/650 mV differs from this applied experiment.
The center reuses admitted DC/AC and qualified signed-power evidence. Two owned
endpoint copies per analysis consume four new Spectre attempts. Before execution,
the finite grid, order, four-attempt ceiling, fixed conditions and first-invalid
stop rule were recorded. No automatic point generation or expansion.

This is **FINITE_GRID_SIMULATION_QUALIFIED**, not a continuous safe range,
MOS operating-region assessment, device absolute rating, reliability, closed-loop
stability or PVT guarantee. Gain varies strongly across these three points;
no optimal point or achieved performance requirement is inferred.

| Applied VBIASN | Differential gain at10 Hz | Supply-rail delivered DC power |
| --- | --- | --- |
|319 mV |74.29542081 dB |69.80969696 microW |
|320 mV, existing center |78.95196191 dB |82.42816000 microW |
|321 mV |82.81298238 dB |140.95061997 microW |

Gain is20 log10(abs((Vop−Vom)/(Vp−Vm))) from the original bounded AC reader;
it is low-frequency AC gain at10 Hz, not maximum or zero-frequency gain.
The original71-point10 Hz–100 MHz analysis and opposed1 V differential AC
excitation are retained. DC requires measured rails, both inputs and both bias
nodes plus all six signed independent sources. Voltage is positive minus negative
terminal; current is positive into each source's positive terminal. Delivered
power is−V×I, with absorption retained. VDD/VSS rail contributions, bias-source
and input-source contributions, and all-source sum remain distinct. This is DC
static power; no transient average or DUT-only dissipation assertion.
Existing center power has its historical extraction precision; it is not
silently upgraded to the endpoint reader's16-digit extraction.

## Contract and operator workflow

`scripts/bias_range_qualification.py` is a fixed operator qualification path,
not an MCP script/parameter execution endpoint. Its immutable policy/delegation
bind exact deployed bytes, four closed cases, parent authority and budget.
The same registered SSH target, EDA lock, active-process check,500-attempt/10 GiB
ledger and disk floor apply. A single VBIASN parameter token is replaced in a
copy; reversing it must reproduce the pinned original input hash. No OA/ADE
netlisting or design mutation. Complete admission and whole-result receipts
preserve source/PSF, parser, effective inputs and exact reservation sequence.
Unknown, incomplete or uncertain outcomes block further execution and blind retry.

`BiasExtraction` v1 validates the four cases, source/analysis identities, finite
scalar/signed inventory, bounded AC arithmetic and exact73–76 ledger markers.
`finite_grid_registry()` creates an **operator-owned registry v2** with grid
minimum0.319, maximum0.321, step0.001 V and an exact evidence-hash review.
VBIASP0.702 and VDD1 V are fixed constraints, distinct from range qualification.
The unchanged variable MCP APIs can describe/check those three numeric points.
Off-grid0.3195 V and outside-grid values fail. Matching numeric values does not
grant execution; this registry contains no analysis adapter or sweep admission.
The existing built-in and v1–v8 registries remain unchanged and unqualified for
parameterized amplifier execution. That integration is the next approved phase.

Private registration, raw input/PSF, source currents, transport logs, receipts,
jobs and provenance stay local/managed. Public status contains reviewed bounded
measurements and digests only. No caller path/script/expression/raw waveform,
vendor/PDK content or additional MCP tool is introduced. Source remains78 tools.

## Resources and integrity

Baseline72 attempts/8,456,765,440 reserved bytes; phase4/536,870,912;
cumulative76/500 and8,993,636,352/10,737,418,240 reserved bytes.
Four owned job trees occupy732,166 logical/958,464 allocated bytes at postflight.
Remaining reservation1,743,781,888 bytes =13 full128 MiB slots. Usage is never
refunded or reset. Source/ADE/PDK/vendor, every prior native/sizing/bandwidth/
slew/Offset job, replay/admission and1,746 prior private files remain exact.
Grid evidence SHA-256:
`ee1f01556c5ef0fcb0bf5aa82a223180ff0ae6aa120f747ddf940746036813da`.
Operator registry semantic SHA-256:
`101901f99990e481ce54b93d65d161893b50504cee428169fee569eb6c849a1f`.
Strict historical phase guards are preserved; new cumulative accounting is
checked by the composed Bias guard. No deletion, source rewrite or reservation refund.

See [phase result](BIAS_RANGE_QUAL_01_RESULT_V1.md) for exact current gates.
Apache applies to original bridge code only; Cadence/PDK/client terms remain
separate. Imported planning rights remain LEGAL_REVIEW_REQUIRED and publication
PUBLICATION_NOT_AUTHORIZED. Claude/new environments remain deferred.
