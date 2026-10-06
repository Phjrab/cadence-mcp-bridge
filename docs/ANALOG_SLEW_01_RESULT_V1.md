# ANALOG-SLEW-01 — reference step diagnostics

Starting main: `b49d826448c1ddab2a2b3d4e176d07db3462412d` (merged PM PR129).
Branch: `feat/analog-slew-01`. Exact containing PR/head/review/main SHA/tree are
recorded privately after integration; no state-sync-only PR. Package1.0.0 remains.

## Actual measurement and scope

Four licensed Spectre TRAN runs use only owned input copies of the admitted
reference. Source/ADE/PDK and prior sinusoidal TRAN are unchanged. Same NN,27 C,
VDD1 V,effective bias320/702mV, input VCM0.5 V; original saved300/650mV unchanged.
Vp0.45→0.55 V and Vm0.55→0.45 V at2 us, return at6 us, stop10 us. Existing
topology has no added external output load or application feedback. Output
Vop−Vom is measured using endpoint-referenced20–80% secants and fixed plateau
windows. This is not maximum adjacent slope or a closed-loop/load slew rating.

| Actual case | Max timestep | Input edge | Native points |20–80% samples rise/fall | Result |
| --- | --- | --- | --- | --- | --- |
| coarse |10 ns |1 ns |1,076 |10/10 |COARSE_CROSSING_BRACKET; rate null |
| medium |200 ps |1 ns |50,010 |11/12 |DEFINED_TRANSITION |
| fine |100 ps |1 ns |100,001 |20/20 |DEFINED_TRANSITION |
| fast |100 ps |0.5 ns |100,005 |20/20 |DEFINED_TRANSITION |

The initial planned5 ns/2.5 ns grids were NOT_RUN. Coarse crossing evidence
justified three fixed refinements, selected and policy-bound before observing
their results, within the original four-attempt ceiling. Original intent and
failed guards/deployments are preserved. Coarse is never silently upgraded.

| Direction | Fine signed rate V/s | Magnitude V/us |200→100 ps relative change | Faster-edge change |
| --- | --- | --- | --- | --- |
| rise |598,570,781.700 |598.570782 |0.236737% |0.172440% |
| fall |−598,570,781.732 |598.570782 |0.230730% |0.173068% |

Both refined-pair and faster-edge comparisons are within the preselected1%
diagnostic threshold; input edges do not overlap measured crossings. This is
two-resolution agreement, not three-level convergence or an absolute error
bound. Plateau spans are bounded, sampled overshoot is below2%, and crossing
brackets/sample counts meet the fixed extraction criteria for the last three
cases. Fine equal20%-subwindow rate ratio is2.831135 in both directions, exceeding
the preselected1.2 constant-slope diagnostic. Endpoints are near±0.999231 V;
the open-loop response is nonlinear with saturated endpoints and intrinsic-only
loading. The large numeric value is specific to that differential transition.

**Supplemental step study: PARTIALLY_QUALIFIED. Conventional/generic slew:
UNQUALIFIED.** No specified-load, application feedback, PVT, reliability,
electrical range, offset, optimization or specification PASS/FAIL follows.
Further conventional slew qualification needs a separately reviewed application
condition/load and suitable constant-slope interval. No fabricated value is
returned for sparse/unsettled/ringing/missing transitions. See
[definition and boundary](ANALOG_SLEW_V1.md).

## Implementation and compatibility

One additive read-only `cadence_slew_study_result`:77 source MCP tools, all76 old
complete schemas exact, registry v1-v8 unchanged. It reuses original registered
slew/design/contract hash plus admitted native TRAN/measurement/PDK checks. A
new explicitly versioned native-step-summary reader binds source input/PSF,
four immutable receipts, extraction and definition hashes. Signed rates,
conditions, warnings, per-run counters and diagnostic quality stay bounded;
no raw vectors, paths, formulas or execution inputs. Generic analog slew still
returns its original UNQUALIFIED/null definition; existing specifications stay
unchanged and this supplemental result is not evaluated against targets.

Fixed operator stages reuse shared budget/lock/disk/source guards and reconstruct
the exact original input hash by reversing two source and one TRAN substitutions.
Recovery of the first run performs finish only, with no simulator/extractor rerun.
The separate immutable `slew-read-v2` reader permits later validated native IDs
and bounded cumulative ledger advancement while preserving every old job exactly.
Temporal phase conservation checks stay intact. Synthetic future-state tests do
not claim actual later-phase execution. All phase artifacts/failures are protected
evidence and never ordinary cleanup candidates.

## Verification checkpoint

- Focused operator/science/admission/transport/contract:107 PASS; separate
  server/SSH/new study suite101 PASS.
- First full source checkpoint:1,990 PASS,four Windows symlink SKIP,56 warnings,
  522.46s. Final source full gate:2,002 PASS,four Windows symlink SKIP,56 warnings,
  502.93s, including timeless-reader tests.
- Canonical Ruff PASS; mypy54 source modules PASS; exact77-tool/old76/v1-v8
  contract audit PASS. First static failures and all correction records retained.
- Security18 PASS,one existing cache warning; locked dependency audit reports
  no known vulnerabilities. Secret preflight916 files PASS at initial checkpoint;
  final scan924 files PASS, including the remaining reader/documentation artifacts.
- Initial wheel62/sdist63 members PASS:canonical Apache LICENSE/NOTICE/third-party
  notices, zero unexpected/protected/imported files. Isolated install, CLI/doctor,
  three SDK configuration formats with77 tools and uninstall PASS. Final artifacts
  are rebuilt after the fixed historical-reader transport change:62/63 members,
  notices/source exact,zero unexpected/protected/imported findings and isolated
  77-tool/three-format/CLI/uninstall PASS.
- Actual four Spectre TRAN runs PASS:each zero errors,two existing CMI-2477
  warnings,zero notices; native waveform extraction/effective-input/protection
  checks PASS. One first-run finish guard failed after simulation and was
  recovered without rerun. Pre-simulation v1/v2 failures consumed no attempts.
- Current-source exported Codex config/v8 SDK stdio:77 schemas, supplemental
  step/old generic null, DC/AC/TRAN/power/bandwidth/sweep reads and restart PASS;
  original admission journal and1,487 prior private hashes exact.
- Actual current Codex agent:69 exposed names; real analog inventory read is
  empty. New study tool NOT_EXPOSED/NOT_RUN; no global configuration change.
  This is distinct from SDK subprocess verification. Claude actual app and
  other Cadence/PDK/host qualification remain DEFERRED/UNVERIFIED.
- GitHub CI and external independent review are reported separately from local
  gates and primary-agent exact-tree review; no PASS is invented for absence.

## Resources and protection

This phase consumes **four attempts and536,870,912 bytes cumulative reservation**.
Final ledger **68/500 attempts;7,919,894,528/10,737,418,240 reserved bytes**. No
refund/reset, elapsed campaign ceiling, result deletion or original-source write.
Four actual job trees occupy96,680,022 logical bytes /96,923,648 allocated bytes.
Six immutable deployment versions occupy188,205 logical /335,872 allocated bytes
at the measured checkpoint; failed pre-simulation owned setup adds6,383 logical
bytes, with its allocated size reported separately in private evidence. These
are phase-owned observations, not total VM inventory or historical reservation
refunds. Free-space/disk floor is observed separately from accounting.

Nine conservative correction events of20 are retained:read syntax/continuation,
initial static audit, cross-Python float policy identity, changing disk telemetry,
legitimate reservation/finish recovery plus justified finer controls,new-source
typing/catalog correction,timeless historical-read protection and removal of
an unsupported live-app registry-version inference during primary review. Historical
BW12/PM3 and earlier correction histories remain immutable. Source OA/ADE/PDK,
prior native/sizing/bandwidth/jobs/replay/admission and1,487 prior private hashes
remain exact. Old bandwidth temporal conservation is recorded FAIL after new
reservations; composed exact step-sequence/fingerprint verification is PASS.
No old verifier is monkeypatched or mislabeled PASS.

## Distribution and next phase

Apache-2.0 covers original bridge source only; Cadence/PDK/client terms and
imported archive exclusion/LEGAL_REVIEW_REQUIRED are retained. No tag, release,
publication, relicensing or history rewriting. PUBLICATION_NOT_AUTHORIZED.

Operators with the reviewed current registry/admission/deployment can retrieve
bounded real rise/fall step diagnostics and provenance using standard MCP,
without exposing waveforms or executing new simulations. Conventional slew
remains unqualified and actual current-app tool qualification remains open.
Recommended next phase: **ANALOG-OFFSET-01**, only after one user confirmation.


## Final gate checkpoint

Final code:2,002 full unit PASS,four OS symlink SKIP,56 warnings/502.93s;
focused107 and101 PASS,canonical Ruff/mypy54 PASS,exact77/old76/v1-v8
contract audit PASS,security18 PASS/one cache warning,locked dependency audit
no known vulnerabilities,924-file secret preflight PASS. Final wheel62/sdist63
content/Apache/isolated77-tool three SDK formats/CLI/uninstall PASS. Changed
Markdown105 visible relative links and balanced fences PASS. Every initial
failure is preserved; SKIP and NOT_RUN are separate. Current-source SDK step/
old paths/restart and real four-run evidence PASS; actual new app tool NOT_RUN.
Primary exact-tree review and permitted PR/main integration are recorded privately.
