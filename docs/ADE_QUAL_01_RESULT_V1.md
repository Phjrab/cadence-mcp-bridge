# ADE-QUAL-01 — current source/ADE state DC qualification

Date: 2026-09-30. Outcome: `CURRENT_SOURCE_ADE_DC_QUALIFIED_SPEC_NOT_EVALUATED`.
The selected first analysis bundle, DC at the saved state's current settings,
completed native netlisting, effective-condition verification, one Spectre run
and PSF scalar extraction. This qualifies the fixed operator path for this
observed revision and bundle. It does not establish a performance-specification
PASS or qualify other analyses.

## Scope and actual execution

The user's explicit additional allowance renewed three corrections of the same
ADE-QUAL-01 change. `policy/ADE_QUAL_CORRECTION_RENEWAL_V1.json` binds that change
to the preserved earlier checkpoint. It keeps the prior three corrections,
raises only this change's maximum to six, and preserves all other cumulative
budgets and the removed elapsed ceiling. The operator requires a private
delegation and reserves each correction before deployment; another version
cannot reset consumed corrections. Five of six corrections have been consumed.

The original OA source and ADE state were read and fingerprinted. The existing
verified OA work copy was reused, and each new job received its own ADE state
copy with only library/cell identity and project routing remapped. Read-only
native signatures compared instances, properties, terminals, nets and
connections. Native ADE loaded that owned state and generated the netlist.
No source, work-copy cellview or original ADE state save was called.

| Immutable version | Verified outcome | New Spectre attempts |
| --- | --- | --- |
| v1–v4 | Earlier failures remain in `ADE_QUAL_01_CHECKPOINT_V1.md` | 0 |
| v5 / correction 4 | Source/copy signatures, ADE session identity, state load and native netlisting succeeded. The validator rejected an assumed include layout: native input embeds its circuit directly | 0 |
| v6 / correction 5 | Exact native inline body, closed header/control statements and effective conditions verified; DC simulation and scalar extraction succeeded | 1 |

The session uses installed IC6.1.5 `sevStartSession` with documented
library/cell/view arguments. `asiGetTopCellView` verifies its actual work-copy
identity before state loading. The verifier reads actual graphical output
markers from the owned CIW log, rejects errors, echoed commands, missing markers
and duplicates. Process exit alone is insufficient.

Native `input.scs` must contain the verified circuit exactly once, one approved
model include and the observed closed header/control statements. Unexpected
includes, analyses, parameters or output paths are rejected before reservation.
The circuit's comment/whitespace-normalized records match the protected earlier
copied netlist. All input/circuit bytes are fingerprinted and rechecked before
simulation and completion. `results()` must advertise the exact `dcOp` result;
selection writes a separate bounded proof, and scalar parsing requires a complete
finite five-node frame. PSF, input and circuit fingerprints are in the private
result. Ordinary AC phase is not interpreted as phase margin.

## Observed conditions and result boundaries

| Item | Evidence |
| --- | --- |
| Saved-state and effective biases | VBIASN=0.300 V, VBIASP=0.650 V |
| Supply | Native circuit and measured VDD=1.0 V |
| Input common mode | Native source binding and measured Vp/Vm give 0.5 V |
| Model and temperature | NN, 27 C, verified in state and generated input |
| Analysis | Single native DC operating point, result selector `dcOp` |
| Simulator quality | Zero errors, two allowlisted CMI-2477 warnings, zero notices |
| Extraction | Complete valid scalar frame; common-mode/differential arithmetic verified |
| Specification | `not_evaluated`; no numerical targets were supplied |

The five printed node scalars agree with the preserved 300/650 mV baseline at
matching circuit, model, temperature, supply and input conditions. This bounded
comparison does not assert equivalence of every simulator option. The native
wrapper uses the saved state's options; the older diagnostic used its own fixed
wrapper. The 320/702 mV candidate's earlier snapshot results have different bias
conditions and were excluded from this comparison. That candidate remains a
separate user choice and was not applied in this native current-state run.

No load, device size or circuit topology was changed. The observed circuit-body
match binds this run's connections and load to that revision; it does not qualify
future loaded behavior or PCell/LVS semantics. Native current-state AC/TRAN,
Noise/STB, PVT/corner runs, statistics and Monte Carlo remain unqualified. Model
section declarations alone do not qualify those capabilities. The existing
snapshot DC/AC and fixture sweep MCP interfaces are unchanged. This operator
qualification adds no general command, path, SKILL or OCEAN input or new MCP tool.

## Protection, resources and verification

Postflight verified unchanged original source, ADE state tree, model, OA copy,
historical copied netlist/project and pinned snapshot fingerprints. No EDA
process remained active. Free space was approximately 24.06 GiB. Cumulative
Spectre attempts increased once, 14 to 15 of 100, and reserved result bytes
increased to 806,354,944 under 5 GiB. The v6 job occupied 265,278 bytes at
postflight. One active EDA maximum, disk floor, paid-resource zero and replay
boundaries remain in force. No elapsed ceiling was reinstated.

Local validation: 76 relevant tests passed, covering ADE qualification, campaign
authority, existing diagnostics and security. Ruff across src/scripts/tests and
mypy for src, the operator and focused tests passed. Secret preflight passed.
Remote deployment passed Bash syntax, actual Python 2.6 compilation and exact
manifest verification. The earlier full regression remains 692 passes and eight
integration skips; it preceded this renewal and is not represented as a fresh
full-suite run. Actual native DC qualification is the new remote evidence.

Private immutable result: `.codex/ade-qual-01-result-v1.json`, SHA-256
`63386ebb020277747e495069ff0ff0f7f179fe05d7a255d44d3fa0a06f29d48a`.
The original checkpoint, failed job/deployment evidence, reservations and earlier
results remain preserved. Raw OA/ADE/PDK/netlist/PSF/logs and scalar result bytes
stay private. This document contains reviewed capability, condition and quality
summaries only. Continue the existing feature PR #93; no status-sync PR is needed.

## Next major phase

The current DC bundle is complete. Starting another major phase requires one
user choice. A bounded next option is native AC/TRAN qualification with explicit
stimulus, output and measurement definitions. Optimization would first require
actual performance goals and priorities. Neither option is active in this result.
