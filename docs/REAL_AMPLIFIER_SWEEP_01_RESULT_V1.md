# REAL-AMPLIFIER-SWEEP-01 result

Start: `a809b5e19a61eadd747a8beca0da3ae2ee67a023` (Bias PR132).
Branch: `feat/real-amplifier-sweep-01`. Exact reviewed candidate/containing PR/main
identity is retained in private integration receipts; no state-sync-only PR.

## Actual implementation and qualification

The existing durable sweep engine and journal now execute the explicit reference
finite grid via a compiled adapter and version2 internal codecs. Five bounded
tools are additive; all old78 full schemas, v1-v8 registries/native readers and
RC identities remain exact. No new resource ledger or sweep engine was created.
The numeric registry remains operator selected and legacy generic analysis
execution does not become unrestricted. See [contract](REAL_AMPLIFIER_SWEEP_V1.md).

One three-point DC sweep and one three-point AC sweep completed on the reference
CentOS6.5/IC6.1.5/Spectre/gpdk090 environment. Conditions: NN27C,VDD1V,
VBIASP702mV,VCM0.5V,original topology/no added external load. Only the owned
VBIASN token changed; reverse source hashes, effective inputs and complete
signed-source/AC extraction passed. These facts qualify finite nominal
simulation points only; no continuous/device-rating/load/PVT/optimization claim.

| Applied VBIASN | Signed supply-rail DC power W | Differential AC gain at10Hz dB |
| --- | --- | --- |
|0.319V|0.00006980969696024215|74.29542080598108|
|0.320V|0.00008242815901312446|78.95196190699784|
|0.321V|0.0001409506199734541|82.81298237831557|

Gain and the separate `signed-dc-supply-rail-power-grid-v2` definition are QUALIFIED
for this scope. Supply rails,bias sources,input sources and all-source totals
remain separate, preserving signed `-V*I`; these are not DUT-only/TRAN averages.
The original center power extraction/precision/schema remains unchanged. Results
retain definitions, source/result/PSF/frame hashes, conditions and per-point
admissions. PM and generic Offset stay UNQUALIFIED; no numerical user goals
exist and all design specifications remain NOT_EVALUATED.

## Evidence classes and gates

- Actual Cadence: six new Spectre runs and bounded qualified DC/AC extraction PASS.
- Current-source SDK stdio: exact83 tools/old78 schemas, explicit registryv2/runtime
  digest, DC/AC plan/submit/result, same-key replay, completed cancellation no-op,
  fresh server result equality and cumulative conservation PASS.
- Preserved-result SDK regression: original DC/AC/TRAN/power/BW/slew/Offset/RC
  Sweep, restart, admissions and prior private hashes PASS, without new simulation.
- Synthetic guards: malformed/unknown/off-grid/contract/hash/source/current/unit,
  active input proof, symlink/containment, exact ledger/gaps/overflow/disk guards,
  uncertain reservation/send, partial failure, active-point cancellation and
  restart reconciliation PASS. Real crash injection/active cancellation/partial
  simulator failure are NOT_RUN; active termination is not implemented/qualified.
- Actual Codex `cadence_runtime_info_v2`: PASS for observing builtin registryv4 and
  default journal selection. New83 schemas/finite adapter execution in that app
  NOT_RUN; no global app configuration change. SDK is not app E2E.
- Claude complete gate: `CLAUDE_REAL_CLIENT_UNVERIFIED`; preserve PR127 limited
  Code-tab historical reads, with no unsupported source/version/lifecycle claim.
- Full unit2,194 PASS/four OS symlink SKIP/56 warnings,524.03s. Lint/type58/
  exact contract83/security18/locked dependency audit PASS. Security gate has a
  nonfunctional cache-permission warning; no known dependency vulnerabilities.
  First preparation failures remain preserved. Built wheel/sdist exact content,
  Apache LICENSE/NOTICE/third-party notices,absence of private/protected/imported
  material,isolated install/CLI,three stdio formats83 tools and uninstall PASS.
  Integration receipts are attached to the containing reviewed PR; skips are not PASS.

## Resources, protection and corrections

Phase:6 attempts/805,306,368 reserved bytes. Cumulative:82/500 attempts,
9,798,942,720/10,737,418,240 reserved bytes. Seven128MiB slots remain; physical
storage is not the cumulative reservation ledger. The six owned jobs contain
1,105,799 logical bytes and1,511,424 allocated bytes at postflight. No refund,
reset, result deletion or compaction occurred. One shared EDA lease/disk floor
and the bounded fixed worker/extractors remain active.

Original OA/ADE,PDK/vendor,prior jobs/replay/evidence and1,810 prior private file
hashes are unchanged. Whole-job receipts, no-follow exact input/admission hashes
and complete pre/post protection checks passed. Successful replay consumes zero
extra attempts. Historical failure receipts/counters are retained. Conservative
same-change corrections10/20, including initial preparation/static/fixture/
annotation/async-test fixes, were recorded before immutable deployment. No
actual simulation rerun or deployed helper correction was needed.

## User-visible result and remaining boundaries

An operator with this exact registry/PDK/deployment/journal can prepare,submit,
resume and retrieve a bounded one-axis reference sweep with actual qualified
gain/power facts. Cancellation stops pending points only; the active point keeps
running and its outcome remains recorded. This six-slot campaign activation
is exhausted and is not blanket authority for new experiments.

Apache2.0/external Cadence/PDK boundaries remain. Imported planning rights retain
LEGAL_REVIEW_REQUIRED and publication remains PUBLICATION_NOT_AUTHORIZED. No
version bump,tag,release,PYPI/MCPB,source mutation,optimization or historical
storage deletion was performed. Other environments/portability/PDKs and full
app qualification are deferred. Under the already explicit continuous user
delegation,next phase is SPEC-REAL-EVAL-01,using these real facts with absent
targets and zero new simulations.
