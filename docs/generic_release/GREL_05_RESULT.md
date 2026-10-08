# GREL-05 generic reader implementation checkpoint

Status PARTIAL; generic native release BLOCKED. Continuous GREL02–07 and existing
895MiB are authorized. This feature is stacked on unmerged PR146 /17cb59a;
ancestors, main553276d and unrelated original OCN are preserved.

The installed package now has a generic reader compiler/projector bound to the
immutable runtime, generic ADE registration, logical measurement allowlist, plan,
UUID and execution-input digest. Registered node/source selectors configure one
fixed OCEAN program. DC projects voltages and signed source power with explicit
terminal difference and separate roles. Shared power arithmetic preserves exact
legacy six-source grouping/fSum order. AC divides measured complex differential
output by measured input at registered actual sample frequencies. TRAN summarizes
all bounded saved samples and reports their real resolution/time-weighted mean.
No source amplitude/frequency or circuit-specific names are compiled defaults.

Malformed/missing/extra/reordered rows, stale identities, unsafe selectors,
nonfinite/out-of-bound numeric text, unsupported inventories, unmatched axes,
missing gain samples, zero AC input, wrong transient interval/complex values,
per-wave and aggregate bounds are rejected without partial facts. Failed data
never becomes specification FAIL. Outputs remain native NOT_ATTESTED and targets
NOT_EVALUATED. No public MCP reader/path/tool schema changes. See
GENERIC_RESULT_READER_V1.md and installed README/schema/help.

Observed local related189 PASS /zero skips /11.08s; Ruff/mypy71 PASS and85 full
MCP schema compatibility PASS. Security18 PASS /1.32s and locked audit no known
vulnerabilities. Initial installed wheel CLI compile/project, bootstrap/protocol
and32-state reinstall/uninstall preservation PASS, but predates final aggregate
1536-row bound and README change. That log is retained as source-scoped history;
final exact-source package/hosted/independent review receipts follow separately.
Initial test1 failure was an overly exact floating total assertion; corrected to
numerical tolerance without changing signed arithmetic. Its log is preserved.

This is local development tooling and calculation infrastructure. It does not
close automatic terminal extraction or produce attested PSF/native facts. Production
provider, authentic operator confirmation/migration/renewal, trusted terminal
worker/lock integration and native copy/API/input/reader qualification remain
absent. Generic1D Sweep codec/SweepStore/Supervisor and specification fact binding
remain incomplete. Clean actual Codex new-job/restart acceptance has not run.
Native trust still blocked/executable_permissions, not requalified here. No native
script execution, simulation, reservation, deployment, result deletion, protected
repair, budget increase/reset, merge, GREL08 or publication was performed.
Two real new circuits and new DCACtran/Sweep jobs remain acceptance requirements;
analytical disposable frames and synthetic installed CLI are not substitutes.


## Analysis-specific measurement identity review correction

Independent review32906b3 found P2: allowlist membership alone permitted an AC/TRAN
frame to report dc-output identity. The generic reader now requires an exact
analysis-specific RegisteredMeasurement from existing registry v4 or later,
plus its canonical SHA256; missing/wrong-analysis/stale contracts are rejected.
Qualified fixed historical definitions cannot be rebound to this generic reader.
Unqualified declarations remain unqualified after local preparation. No registry
schema or MCP schema/version changes were needed. Tests and installed disposable
operator contexts now register explicit matching mappings for each analysis.
Earlier32906b3 software/CI/artifact receipts are historical after this correction.

At32906b3: hosted Windows2587 PASS/four POSIX skips/56 warnings/249.34s,
Ubuntu73 PASS/no skips/3.57s; run37718061280, jobs113119066492/113119066331.
Installed32-state preservation and curated79/80-member artifacts matched local:
wheel d2b7a6cef53458bd97878a13cac164d0a285843f93d43db45af3f28b16530257;
sdist a9beadee05818b082651001dfcb8a29343ca83f567435f52bceca09e9a5e7d4f.
Final current-source revalidation follows; none of this is native qualification.


## Corrected source validation receipt

Tested source a4b3930bf98242a119b905047f84445f7efc763f, PR147 ready/open/unmerged:
- Local193 related PASS /zero skips /12.64s; Ruff/mypy71 and85 schemas PASS.
- Fresh security18 PASS /1.08s; locked audit no known vulnerabilities.
- Hosted Windows run37718949128/job113121887165:2591 PASS /four POSIX skips /
  56 warnings /237.78s; lint/type/security/audit/85 schemas/installed CLI PASS.
- Ubuntu same run/job113121887034:73 PASS /zero skips /2.90s. These are retained
  shared-reservation tests, not native OCEAN or generic waveform qualification.
- Corrected installed CLI requires actual registry v4 analysis mappings; generic
  ADE compile, reader compile and mathematical frame projection PASS in a new
  disposable operator workspace. Same-version reinstall/uninstall retains32 files.
- Curated wheel79 members SHA256
  5421da2aa5ec64dc71dae1366946eed8d7acebe3571565223b6fd29a79d84597;
  sdist80 members SHA256
  e6a4eae7f5b041d2daafc11cc1f2baa0911395d85cf7d08e8b160ca0490c67f2.
  Retained local and hosted bytes match; unexpected/protected0; source/notices exact.
-327 inputs zero unexpected drift; snapshotSHA256
  46a0f687cc116711786a0242dcd6dca954c3bfcef9b4238e9aff2242956221c2.
  Four intentional review changes from the prior snapshot are README, installed
  verifier, generic measurement module and its tests. Earlier evidence is retained.
- Corrected-source independent review is still pending when this receipt is written.

Fresh current-connected-app local MCP observation at2026-10-08T02:43:18Z differs
from historical builtin-v4 observations: operator-supplied design registryv2,
one reference-differential-amplifier-tb2 description, PDK registryv2/two entries,
and operator-supplied analysis/Sweep journals. Registration is unqualified and
execution_authorized=false; health/trust/authority are not assessed. Exact semantic
hashes are in PROGRAM_CONTINUATION.json. Self-reported1.0.0 does not attest the
candidate source/build or imported memory. No global config change/restart/new job
was performed. Preserve this current selection; historical app receipts remain
scoped history. This is not GREL06 clean-client or complete app schema acceptance.

No native execution/reservation/deployment/deletion or protected permission/license
change occurred. Last actual native trust/resource observations were not refreshed.
Production provider/operator authenticity/migration/renewal, terminal worker lock,
native copy/API/input/reader proof, automatic extraction/recovery, generic1D Sweep,
specification fact binding and actual clean-client qualification remain incomplete.
Generic release BLOCKED. Continuous02–07/895MiB persists without phase reapproval.
Receipt-only later HEADs must not be represented as this tested source revision.


## Voltage/current selector separation review correction

Independent reviewa4b3930 found P2: a selector shared between node/current sets
could feed the same branch-current value into volts and amperes, yielding
invalid power dimensions. Both sets must now be disjoint, and node selectors with
known PLUS/MINUS branch suffixes reject even without a matching source entry.
Legitimate hierarchy nodes with those names are temporarily unsupported rather
than inferred to be volts. Actual saved-quantity units remain an unqualified
native provider responsibility. Earlier a4b3930 validation receipts remain
source-scoped history after this correction. No native state was mutated.


## AC frequency feasibility and representation review correction

Independent af0a6c3 review found two P2s: a requested frequency set could exceed
the waveform sample limit, or unique Decimal frequencies could collapse to one
binary float. Registration now rejects both before compiling a reader. Projection
also rejects requests that match the same saved sample through tolerance, so a
frame cannot emit duplicate frequency results. Five regression cases cover count
limits, two float-collapse magnitudes and distinct nearby requests sharing a sample.
Local related225 PASS/no skips/25.87s; Ruff/mypy71 and85 schemas PASS. Final package,
security, hosted and corrected-source review follow separately. A test invocation
with two nonexistent legacy test filenames ran zero tests and was corrected; it is
not PASS evidence. One new regression initially used W instead of protocol P and
failed before reaching the intended branch; corrected protocol test now passes.

At af0a6c3, hosted Windows2595 PASS/four POSIX skips/56 warnings/229.15s and
Ubuntu73 PASS/no skips/3.73s, run37719977175/jobs113125162135/113125161889.
Hosted79/80-member wheel/sdist matched retained local8f8854.../c9c2d0... bytes.
These are historical after the AC correction; no native qualification follows.
Security invocation without local PYTHONUTF8 failed in pip-api decoding the Korean
workspace path. The failed log is retained; process-only UTF8 retry is pending.
No runtime, protected installation, global app setting or native state changed.


## AC full-grid capacity and serialized endpoint review correction

Independent48f8879 review found two more P2s: a full declared AC grid could exceed
the reader's sample capacity even though requested gain count fits, and %.16g
serialization could round an endpoint just outside strict float interval checks.
Binding now conservatively counts the whole logarithmic grid with128-digit
Decimal arithmetic and rejects over-capacity compilation. AC interval comparisons
use relative1e-12 endpoint tolerance, retaining rejection of material excursions.
Five whole/partial-decade capacity cases and two high-precision endpoint cases
pass; original AC fixture reader limit was raised from impossible4 to64 for its
51-sample declared grid. All63 reader tests pass. Final related/package/security/
hosted/review receipts follow separately;48f8879 receipts are source-scoped history.
No native action, budget reservation, protected repair or original mutation occurred.


## Complete AC frame and exact-sample selection review correction

Independent e756b5e review found two P2s: omitted endpoints could pass an interior
subset frame, and two close valid samples made even an exact requested frequency
ambiguous under tolerant-only matching. Both endpoints must now match, and the
full declared logarithmic grid is checked for count and each interior frequency.
Exact sample equality takes precedence; ambiguous tolerance and duplicate sample
use remain rejected. Grids collapsing under actual %.16g serialization reject
before compiling. Other native sampling forms remain unsupported/unqualified.

Six added regression cases cover omitted endpoints/interiors, exact close neighbors,
complete-grid success/shifted-interior rejection, and output-resolution collapse.
Default analytical AC fixture now uses a complete two-point1kHz–2kHz grid. A broad
test-text replacement accidentally changed a1e11 float-collapse example and was
corrected after its expected rejection failed;69 reader tests now pass. Final
source-scoped related/package/CI/review receipts follow. Prior source evidence is
retained without being promoted to this corrected source or native acceptance.
