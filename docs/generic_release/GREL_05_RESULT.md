## Serialized AC grid correction, 2026-10-09

Final review exposed valid ultra-narrow grids whose %.16g displacement exceeds
the quarter-gap cap. Projection now compares the expected grid in the extractor's
serialized representation and normalizes requested frequencies to that same format
before unique sample selection. The quarter-gap bound remains disjoint; missing
boundaries and collapsed serialized grids still reject before execution. Both
reviewer counterexamples pass compile/projection regression, with both endpoints
selected. Local352 tests/4 POSIX skips, Ruff/mypy71 and exact isolated wheel/sdist/
installed32-state preservation pass. Final exact-head hosted checks and independent review are pending.
No new native deployment, simulation or reservation; publication remains blocked.
Earlier receipts below retain their historical source scope.

## Narrow AC grid review correction, 2026-10-09

Latest PR147 review found an additional P2: relative1e-12 endpoint/full-grid
tolerance could consume the entire spacing of a valid ultra-narrow high-frequency
sweep, accepting a missing start/end sample. Both checks now cap tolerance at one
quarter of the nearest declared grid gap. Regressions request only the unchanged
endpoint and demonstrate the other missing boundary still rejects. Exact close
neighbors and normal16-digit serialized endpoints remain supported.
Local350 related tests PASS/4 Windows POSIX skips, Ruff/mypy71 PASS; exact isolated
wheel/sdist/CLI/SDK/bootstrap/reinstall/uninstall32-state preservation PASS.
Current PR152 host reader also reprojects both retained actual AC results identically;
that is prior-bundle result evidence, not fresh candidate simulation/app acceptance.
All ten earlier findings remain implemented with distinct regressions. Final exact
hosted CI and fresh independent review are still required before conditional merge.

PR145 and146 normally merged asbdcba004 and5a85beb; current main5a85beb. Direct
GREL02-08/retained16GiB/conditional related merge authority continues; consumption,
replay and history are retained. No new VM jobs/admin changes/reservations. This
foundation remains native-unqualified, release BLOCKED and exact publication approval
separate. Earlier dated restrictions below are preserved historical checkpoints.

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


## Analysis/reader feasibility review correction

Independent c3f5ca5 review found two P2s: a requested AC frequency could lie inside
the interval without matching the declared grid, and a TRAN stop/maxstep ratio
could require more saved points than reader capacity. Binding now uses the same
exact-first/tolerance/unique-index selector as projection on the serialized
declared AC grid. TRAN requires ceil(stop/maxstep)+1 within maximum_samples.
The initial all-saved-points contract supports no thinning/strobe; projection
also rejects saved gaps larger than the declared maxstep. Additional adaptive
points can still overflow and reject without partial facts; none of these local
checks attest actual native sampling, units or provenance.

Nine regression cases cover unavailable/duplicate AC grid samples, integer and
partial TRAN sample bounds, and saved-time gaps despite valid endpoints/count.
Analytical TRAN fixture maxstep is explicitly4ms to match its coarse saved grid.
Corrected local/hosted/artifact/review receipts follow separately; c3f5ca5
receipts remain historical after this correction. No native side effect occurred.


## Final feasible-reader software receipt, 2026-10-08

Tested code source f5a1de2626c0a6b9323d15bd13e89622ff3577de in PR147,
stacked on unmerged PR146/17cb59a. Later receipt-only HEADs are not this source.
- Local247 related PASS/no skips/26.15s; Ruff and mypy71 PASS.
- Fresh security18 PASS/1.61s; locked dependency audit no known vulnerabilities.
- Hosted Windows run37723131490/job113135125151:2622 PASS/four POSIX skips/
  56 warnings/268.39s; lint/type/security/audit/85 schemas/installed CLI PASS.
- Ubuntu same run/job113135125399:73 PASS/no skips/2.58s. These are
  actual disposable POSIX files/flock tests, not Cadence execution.
- Exact installed-wheel reader/ADE CLI, isolated SDK/protocol/bootstrap and
  same-version reinstall/uninstall32-state preservation PASS. Native jobs0.
- Curated79-member wheelSHA256
  046f2f9cf2ce8e1288ff8c977730c663393a9891c214d04776524b46986e0ea2;
  80-member sdistSHA256
  8b9f3ea8dce4e56814c3181f2c37ec1d4565b38180bb13fe65d599c540667d5e.
  Hosted/local retained bytes match; source/notices exact; unexpected/protected0.
-327 inputs have zero unexpected drift; final snapshotSHA256
  81112255023d333731c70af8b3a27374a5ad78e02eb1d7a812be05aee64480ed.
  Only intentional changes from previous source are README, reader and tests.
- Ten independent P2s corrected. Corrected-source automatic review returned
  bot+1 at2026-10-08T03:34:41Z with no new findings. This is not formal APPROVED.
- Latest main553276d unchanged; original unrelated OCN retains
  2cf3673f4e80cb3c2bd6815f919c0d2aaf9b20a944b2ef1b8eb231589c634b32.
  Prior99,964-file preservation observation was not rehashed wholesale.

Prior c3f5ca5 Windows2613 PASS/268.07s and matching037640.../f58ff5...
artifacts are history after feasibility fixes. Its Ubuntu success was observed,
but log read after branch movement returned HTTP409; its count/timing stay
null in the machine receipt. Current f5a1de2 Ubuntu73/2.58s was actually read.
All earlier failure/correction/source evidence remains retained and scoped.

User-visible capability now available from the package: register private logical
reader bindings, compile one fixed reader and locally validate bounded DC/AC/TRAN
frames without circuit-specific Python edits. Mathematical outputs remain
NOT_ATTESTED/NOT_EVALUATED. No native OCEAN API, PSF-unit/source-orientation,
actual whole-waveform or clean-app new-job qualification is claimed. Installed
fixtures are synthetic; they are not two actual newly simulated circuits.

Generic release remains BLOCKED. Production authenticated provider/operator
confirmation/migration/renewal/terminal lock; trusted native copy/API/input/reader
attestation; automatic extraction/recovery; generic1D Sweep/specification fact
binding; actual clean-app jobs/restart and native operational/update qualification
remain incomplete. Other Cadence versions/PDKs/PCs stay deferred. Last native
trust still rejected executable_permissions; trust/resources were not refreshed
by this local checkpoint. MyDesignLib is a circuit-library hint, not executable/
dependency-chain attestation. Installation-owner trust action remains required.

Continuous02–07 and existing895MiB authorization persists without phase reapproval.
This checkpoint0 native executions/reservations/deployments/deletions; no protected
permission/license change, budget reset/increase, merge, GREL08 or publication.
Fresh shared-ledger/trust checks are required before any later native admission.
