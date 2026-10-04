# Preserved MOS operating-point diagnosis

Date: 2026-10-04. User-selected phase: `ADE-PVT-DIAG-01`.
Outcome: all 700 requested scalar fields read and FF/FS gain loss explained by
observed device headroom and conductance changes. No new circuit simulation.
Specification evaluation: `not_evaluated`.

## Conditions and evidence

Reuse the five preserved native DC datasets and PR #98's corresponding AC
results. Their qualified owned copies use 320/702 mV, VDD=1.0 V, 27 C and
VCM=0.5 V with the existing circuit, stimulus and load. This diagnosis applies
no voltage, model section or ADE change. The original saved state remains
300/650 mV, NN, 27 C with DC enabled. Candidate characterization does not
establish a specification PASS or promote the original scientific baseline.

The installed OCEAN reader has callable `pv`; `dcOpInfo` is the sole available
tested selector in all five saved DC results. Read 14 MOS devices per corner,
ten fields each: `id`, `gm`, `gds`, `gmbs`, `vgs`, `vds`, `vbs`, `vth`,
`vdsat`, `region`. All 700 fields are numeric; none is missing. The private
inventory proves the same eight NMOS/six PMOS identities, terminal connections
and model digests across the five preserved netlists. Original names,
connections and model identifiers stay private; the report uses opaque aliases.

## Device evidence for FF and FS

Headroom below means `abs(vds) - abs(vdsat)`, in mV. Negative values show
insufficient drain-source voltage relative to the saved saturation-voltage
estimate. `gm/gds` is a device metric, not the complete circuit gain. Region
codes remain vendor numbers: no undocumented code-to-region mapping is used.

| Role / alias | NN headroom (mV) | FF headroom (mV) | FS headroom (mV) | NN gm/gds | FF gm/gds | FS gm/gds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Input NMOS / mos01 | 497.5315 | -53.8377 | -252.9136 | 175.6023 | 1.8914 | 0.04540 |
| Shared-source bias NMOS / mos03 | 23.4399 | -2.7199 | -122.3543 | 17.8124 | 7.5615 | 0.23661 |
| First-stage PMOS bias load / mos09 | 67.3449 | 602.0901 | 831.5290 | 43.6056 | 192.8017 | 337.1525 |
| Output NMOS / mos08 | 150.0744 | 243.9327 | 230.2561 | 186.3094 | 55.1218 | 60.0830 |
| Output PMOS / mos12 | 698.7238 | -175.7839 | -307.8908 | 368.3715 | 1.2499 | 0.93105 |

The paired input/bias devices and all four second-stage PMOS show the same
headroom failure pattern in FF and FS. Both input and output stages contribute:

- **FF:** input gm increases from 366.1852 to 423.3063 uS, but input gds
  increases from 2.08531 to 223.8037 uS. The loss is therefore not an input-gm
  decrease. The input drain-source voltage is only 108.3888 mV versus a saved
  vdsat of 162.2265 mV. The output PMOS has only 318.0481 mV of drain-source
  voltage versus 493.8320 mV of saturation voltage; its gds rises from
  0.3503615 to 759.5320 uS.
- **FS:** the input has only 13.47885 mV of drain-source voltage versus
  266.3924 mV of saturation voltage. Input gm falls to 54.21268 uS while gds
  grows to 1194.062 uS. The shared-source bias devices also lose voltage
  margin. Output PMOS voltage is 391.8856 mV versus 699.7764 mV vdsat,
  with gds=543.7889 uS. Input gm/gds below unity explains the especially
  severe first-stage collapse.
- The first-stage bias PMOS still has positive voltage margin in FF/FS;
  blaming every PMOS or a universal gm loss would contradict the saved data.
  The output PMOS gate drive and output common mode move substantially:
  output common mode is 0.2277073 V in NN, 0.6819519 V in FF and 0.6081144 V
  in FS. Output branch current rises from 6.376831 uA to 462.8679 uA in FF
  and 351.6212 uA in FS, about 72.59 and 55.14 times NN. Increased second-stage
  current and gm do not compensate for the much larger output conductance.

These observations support a corner-sensitive DC bias/headroom problem at the
fixed candidate, producing high conductance in the input and output PMOS devices.
The exact gain impact is corroborated below. A corrected bias, robust operating
range, transient settling or acceptable design performance has not been tested.

## Independent gain arithmetic

`scripts/ade_pvt_diag_analysis.py` performs local calculations only. It pins
the private graph bytes, extraction journal/result and measurement-frame bytes.
One method stamps all 14 saved MOS devices into a DC small-signal nodal system
using gm, gds and gmbs with drain/source current conservation, fixed bias/supply
increment zero and differential input increments +0.5/-0.5 V. A separate
symmetric half-circuit calculation resolves first-stage gain and second-stage
direct-plus-mirror response. The two calculations agree numerically in all five
corners. No full circuit topology or raw evidence is published.

| Corner | First stage (V/V) | Second stage (V/V) | MOS-only DC product (V/V) | Preserved AC at 10 Hz (V/V) | Relative difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| NN | 37.01514 | 242.39518 | 8972.29284 | 8863.354002 | +1.2291% |
| FF | 1.86782 | 2.00562 | 3.746135 | 3.731396 | +0.3950% |
| SS | 6.17840 | 299.63448 | 1851.26315 | 1839.439201 | +0.6428% |
| FS | 0.045378 | 1.52867 | 0.0693681 | 0.0692544 | +0.1641% |
| SF | 0.41477 | 169.08043 | 70.130027 | 69.054660 | +1.5573% |

Relative difference is `(MOS-only gain / saved 10-Hz AC magnitude - 1)*100`.
This is a consistency comparison, not a specification tolerance or PASS gate.
The model omits frequency-dependent capacitance, other passive admittances and
MOS derivatives outside the three saved conductances. The remaining 0.16–1.56%
difference is not assigned to a particular omitted effect without evidence.
It reproduces the large corner-dependent gain changes and identifies the two
affected stages; it does not replace full Spectre AC or predict bandwidth.

SS and SF provide useful counterchecks: their input NMOS keep positive
headroom, while the first-stage PMOS bias loads have negative headroom
(-6.5488/-114.6832 mV for mos09). Their second-stage currents are much smaller
than NN and their saved gate voltages are below threshold magnitude. Region
code 3 is recorded without assigning a vendor meaning. Neither corner is
declared acceptable solely because its gain exceeds FF or FS.

## Implementation, corrections and verification

The operator provides only fixed deploy, probe, extract, saved-status and
postflight actions. No caller script, path, signal or model is accepted and
no generic MCP execution tool is added. Shared locking permits one EDA reader;
durable journals reserve operations before side effects. Existing runtime
sources, original/PDK/history and five DC job trees are pinned before/after.
Saved-status reads have three-attempt limits and do not launch OCEAN again.

The initial v1 probe reached `pv` then timed out on `unbound variable - info`:
a quoted hyphenated SKILL symbol was interpreted as subtraction. Its partial
frame, logs, reserved journal and runtime tree are preserved. One of three
diagnostic corrections is consumed. V2 uses string selector arguments and
compares the string forms of available results; probe and extraction succeed.
Both immutable deployments and prior correction histories remain intact.
A separate fixed artifact-size read initially failed before Python execution
because of shell quoting; the corrected read uses standard shell escaping.
It consumed no simulation or new deployment and changed no protected evidence.

Full regression: 928 passed, eight opt-in remote integrations skipped,
56 existing deprecation warnings. This run began before the v2 correction and
local arithmetic additions. Final affected-suite verification covers the v2
operator, actual failure's string-selector regression, synthetic arithmetic,
evidence tampering, PVT qualification and security: 116 passed. Ruff and strict
mypy pass for product source and all four new operator/test modules (25 files).
No skipped remote test is claimed passing. Actual live OCEAN extraction,
saved-result integrity and protected postflight are separately verified.

The private graph/frame hashes match their remote original bytes. Missing data,
nonfinite values, nonpositive denominators, singular nodal systems and changed
evidence fail closed rather than producing invented gains. Public fixtures are
synthetic; raw device identities, connections, PDK statements, PSF and logs stay
private. No dependencies or active MCP execution contracts change; reuse
PR #97's same-day frozen dependency audit. Final publication/security checks
and exact feature-head review precede normal PR integration. The final secret
preflight passes for 664 repository files; flat state metadata keys are unique.
Both new OCEAN source directories explicitly retain LF through Git checkout,
preserving the exact deployed bytes and policy bindings.

V2 policy SHA-256:
`20c292f5a8d80250014b5b77fd45804c1bfaa27cf60c750d1bc3d0f25d9e9ab3`.
V2 deployment manifest SHA-256:
`41ab0453dfa07c83c8d99520b9657464e174dae557245e156000d020dd1fa823`.
Extraction frame SHA-256:
`b6bafad4df7378a0b6bcc3d74bb16bcae40128ad08c24f934dc5c51474b77538`.
Private device inventory SHA-256:
`c23b33abf0dae4f838f14cc013dbc964f9a003dfc590883b935fa82137a04a44`.
Original remote JSON and local canonical JSON digests remain distinct.

## Resources and phase exit

New Spectre attempts: zero. Shared ledger unchanged at 32/100 and
3,088,056,320 reserved result bytes under 5 GiB. Both diagnostic runtimes
and deployments occupy 157,921 bytes including the retained v1 failure and
managed interpreter cache, below the 2-MiB phase artifact cap and remaining
campaign headroom. Free disk: 25,819,258,880 bytes of 62,382,514,176,
above the greater-of-2-GiB-or-10% floor. Active EDA and paid resources are zero.
The user's removed elapsed ceiling is not restored.

No source/ADE/PDK/bias change, new simulation, optimization, statistical run,
cleanup, OS/Python upgrade, tag/release, main push or state-sync-only PR occurs.
Reviewed feature integration is followed by a private merge checkpoint and
completion report. Ask once whether to prepare a bounded bias/headroom
improvement plan as a new major phase; no new voltage range or execution is
activated by this diagnosis.
