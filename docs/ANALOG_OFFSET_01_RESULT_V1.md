# ANALOG-OFFSET-01 — nominal input-nulling diagnostics

Starting main: `09339c48c692f6e00e53b36adc725516b54b4daf`.
Branch: `feat/analog-offset-01`; exact reviewed head/containing PR/remote main
SHA and tree are recorded privately after integration, without a state-sync PR.

## Scientific result

The user selects applied Vp−Vm where Vop−Vom=0 in the nominal open-loop
reference, NN/27 C/VDD1 V/VCM0.5 V/effective bias320/702 mV, original topology
without an added external output load. Four new fixed owned DC runs at−1,+1,
−0.5,+0.5 microV and scalar extraction from preserved zero-input DC are complete.
Source/ADE/PDK and original saved300/650 mV remain unchanged.

| Diagnostic | Observed result |
| --- | --- |
| coarse root |−2.2672600779374006e−15 V |
| fine root |−2.2670260850857216e−15 V |
| fine containing bracket |[-5.000000000143778e−7,0] V |
| root-pair difference |2.3399285167900047e−19 V |
| local gain coarse/fine |8864.667560/8865.582253 V/V |
| relative local-gain difference |0.01031735% |
| supplemental study |PARTIALLY_QUALIFIED |
| generic offset-v1 |UNQUALIFIED/null |
| specification |NOT_EVALUATED; no user target |

The tiny interpolated root is **numerical residual consistent with nominal zero**,
not femtovolt physical accuracy. No absolute-error bound, solver-tolerance
convergence, mismatch/Monte Carlo, closed-loop or PVT-wide qualification follows.
Fixed local output/headroom diagnostics do not prove MOS operating regions or
device ratings. Sign is applied nulling input, not automatically negated.

## Implemented path and compatibility

One additive read-only `cadence_offset_study_result`,78 source tools with all77
old full schemas/v1-v8 exact. Registered design/offset contract hash plus original
admitted DC operation only; existing analysis/measurement/PDK/admission checks
are reused. Fixed source input/PSF, five whole receipts, extraction/definition
hashes, scalar effective inputs and counter sequence are checked. Response
contains fixed results, conditions, brackets, provenance and warnings without
caller path/script/expression/range, raw waveform or execution authority.

Immutable qualification and separate preserved-result readers share the existing
lock/disk/accounting guards. The strict historical verifier remains unchanged;
future bounded counters and individually validated added native IDs are permitted
only by the separate reader, with all original jobs/markers/bytes preserved.
This reader is not a sweep engine, optimization route or new resource ledger.

## Verification

Final gate:2,073 full unit PASS/four OS symlink SKIP/56 warnings in546.75s.
Initial failures remain preserved; skips are not counted as passes.

- Actual licensed Spectre:4 fixed DC simulations and5 bounded scalar frames PASS;
  no unnecessary zero-input simulation. Effective-input/rail/common-mode,
  source reversal/quality/whole-receipt/composed protection PASS.
- Current-source exported Codex configuration SDK stdio:78 complete schemas,
  old77 exact; new Offset and preserved DC/AC/TRAN/power/bandwidth/slew/sweep
  retrieval, process restart, unchanged admissions/1,652 prior private hashes PASS.
- Actual Codex runtime-info-v2: builtin registryv4. New Offset tool NOT_EXPOSED;
  actual new-app Offset E2E NOT_RUN. SDK is not app qualification.
- Canonical Ruff/mypy56/78-tool old77 and v1-v8 contract checks PASS.
- Security18 PASS/one existing cache warning; strict locked dependency audit
  reports no known vulnerabilities;944-file initial secret preflight PASS.
- Final wheel64/sdist65 members, canonical Apache LICENSE/NOTICE/third-party
  notices and exact source, zero unexpected/protected/imported findings PASS.
  Isolated install/CLI/stdio across three SDK configurations78 tools/uninstall PASS.
- Focused science/operator/reader/service/contract/server119 PASS. Separate SSH
  safety suite and final full suite are recorded in the final gate checkpoint.

The initial console pytest namespace collection error,13 old-inventory/backend
allow-list failures in the first full run and later one remaining allow-list
failure are retained. Counts/explicit typed method expectations are corrected;
no failing security test is skipped or diluted. Initial checkout CRLF, lint/type,
fixture/private-baseline-bound and optional metadata lookup failures also remain.
No successful scientific operation was rerun to correct local metadata/tests.

## Resources and protection

Phase4 attempts/536,870,912 reserved bytes; cumulative72/500 and
8,456,765,440/10,737,418,240 reserved bytes. Five job directories occupy660,771
logical/929,792 allocated bytes. Reservations and disk occupancy remain distinct;
remaining cumulative reservation2,280,652,800 bytes,17 further128 MiB slots.
No refund/reset/deletion. Source OA/ADE/PDK/vendor, historical native/sizing/
bandwidth/slew/jobs/replay/admissions and1,652 prior private files remain exact.
Conservative corrections16/20; all earlier phase corrections retained separately.

## User capability and next phase

An operator using the reviewed current registry/admission/deployment can retrieve
bounded real nominal input-nulling diagnostics and provenance over standard MCP.
Original generic offset and goal evaluation retain their safe unavailable states.
Claude remains deferred/CLAUDE_REAL_CLIENT_UNVERIFIED; other environments deferred.
Apache covers original bridge code, not Cadence/PDK/clients. Imported rights remain
LEGAL_REVIEW_REQUIRED and publication PUBLICATION_NOT_AUTHORIZED; no tag/release.

Next approved phase is **BIAS-RANGE-QUAL-01**, then REAL-AMPLIFIER-SWEEP-01 and
SPEC-REAL-EVAL-01 continuously under the user's explicit four-phase delegation.
Each phase keeps its independent gates, reviewed PR and remote verification.

## Final gate checkpoint

2,073 full unit PASS/four OS symlink SKIP/56 warnings in546.75s; focused119
and SSH32 PASS; Ruff/mypy56/exact78 old77/v1-v8 contracts PASS. Security18
PASS/one existing cache warning, locked audit no known vulnerabilities,945-file
secret scan PASS. Wheel64/sdist65 notices/source/protected-content/isolated78
three SDK formats/CLI/uninstall PASS. Changed Markdown94 links/balanced fences
PASS. Exact containing-PR primary review and permitted merge/remote SHA/tree
verification recorded privately; independent review/CI are not inferred from
local checks. No publication or deletion.
