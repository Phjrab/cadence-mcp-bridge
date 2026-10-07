## Final local durable-source receipt

273 Python source/test/script hashes unchanged after related tests and final
package checks. Ruff/mypy68/security18/locked dependency audit/85 schemas PASS.
Wheel3df95d15bcf28187a304dcc9237dfc5cfbb3d2f60d504425045938dcb3919537;
sdista63b92a20328c5ac2c637a2e1bd41d2fbddcba6dea86b7c2acd193611eac6059.
76/77 curated members; source/license/notices exact, protected/unexpected content0.
Installed SDK85, contexts1-to-2-to-1, two design plans and cached journal read,
bootstrap and reinstall/uninstall19 synthetic state hashes PASS. No native jobs.
New hosted full CI and independent review remain pending until push.

# Durable lifecycle implementation checkpoint, 2026-10-08

The existing AnalysisStore now retains canonical operation plans and append-only
hash-linked progress events alongside legacy admissions. Application ID and
user_version1 are preserved. Transactional first admission and CAS transitions
reject conflicting identity, revision regression, known-state regression, terminal
mutation and corrupt or over-capacity history. A page limit applies before plan
insertion; capacity failure rolls back without hiding prior records. Hardlinked
journals are rejected. No new accounting database or worker is introduced.

The existing supervisor exposes a provider-coordinated lifecycle facet. A trusted
provider is required before journal or lock creation. Dispatch intent is committed
before transmission; loss, crash/coroutine cancellation and restart are lookup-only,
including a missing remote reply. Pending cancellation requires the provider to
atomically tombstone absent/pending identity and reject active work across clients;
no local cancellation can falsely hide another client's running job. Reservation
history is never refunded. Authoritative counters, grant use, in-flight bytes,
physical occupancy and free/disk floor remain separate observations. The provider
must recheck them atomically during accept; a self-reported snapshot is not consent.

Installed operation journal-status reads bounded last-observation metadata without
grant or remote contact. It does not report fresh remote health, qualified result
or execution permission. There is no production provider, public native dispatch,
operator attestation, extraction-only recovery or renewal workflow yet. Generic
ADE DC/AC/TRAN, new measurements/Sweep and actual clean client jobs remain absent.
This local implementation does not close GREL03 or the general release gates.

Fresh related tests144 PASS/one local OS symlink skip; Ruff and mypy68 PASS.
Synthetic cases cover two batches, response loss before/after acceptance, multiple
journals with one provider identity, shared lock during await, expiry/revocation,
accounting/space/domain denials, cancellation ambiguity, corruption, page/event
capacity and legacy preservation. Installed state includes generic lifecycle
history; final exact source package/security/hosted receipts follow when observed.
Earlier failed capacity, lock-error translation, stricter unknown transition and
Unicode audit invocations are retained privately. UTF-8 fixes the local dependency
audit invocation without changing policy. Primary review is not independent review.

Main553276d remains unchanged; PR144 continues on its existing feature branch.
Live registered storage observed82 attempts/9,798,942,720 reserved bytes/10GiB
ceiling/895MiB remainder,18,030,073 logical/48,308,224 allocated/free25,689,939,968
and floorOK. Snapshot unchanged; registered roots only, no full VM scan. Native
trust rejection remains the latest qualification (not rerun in this checkpoint).
Native simulations/reservations/deployments/deletions/permission/license changes0.
ContinuousGREL02–07 and remaining-space approval persist; merge/GREL08/publication
remain excluded. All older receipts below are historical source-scoped evidence.

# Current design-scoped correction receipt, 2026-10-08

Tested source233e27e2359e34772eecd62cbcf9af142507a555. Fresh65 legacy-analysis/
operation tests PASS, including26 operation tests; Ruff/mypy67/security18/strict
dependency/85 full schemas PASS.271 Python source/test/script input hashes
unchanged. Numeric regions require an authorized design_id; one local form now
supports zero-variable and parameterized designs with independent same-name ranges.
Installed two-design plans/repeats, SDK85/contexts/bootstrap/reinstall/uninstall
preservation are locally verified. Current hosted CI PASS and review outcome are recorded below.

Local wheelc6b83193519f4db9e99b40fa8b65adb9e3d0afae6bab7d5d4b0be16414ce4312 /
sdist0ee63730ee6e9b542108be7e7d5f5455d1ec5e09e3e87bfe763a406a50e19218;
75/76 curated members, no unexpected/protected content, exact source/license/notices.
All earlier exact-head receipts below remain historical; general release BLOCKED.
Native authority/provider/lifecycle, generic ADE/new-job extraction/Sweep and actual
clean-client execution are incomplete. Trust remains blocked/executable_permissions.
Existing895MiB approval persists; zero native simulations/reservations/deployments/
deletions/license/permission changes. GREL08/publication/merge remain excluded.

# Historical0ee2c17 receipt and native boundary, 2026-10-08

Tested source0ee2c17ba68cced8423d279b64d011319b60ef9a.271 source/test/script
inputs unchanged after checks and documentation-only parent merge. Fresh94
related unit tests PASS/2 local OS symlink skips; Ruff/mypy67/security18/strict
dependency audit/85 full schemas PASS. Actual VM Python2.6 grammar4 assets PASS
with no asset execution or remote write. Locked installed three SDK profiles85,
operator contexts1-to-2-to-1, local authority forms, root-bound synthetic lifecycle
and same-version reinstall/uninstall19-state preservation PASS. This is synthetic
installed-package evidence; actual Codex continues the preserved earlier context.

Current local wheel5bdba4e85d085b18f2d4df88d97aade1edf8f7fc0206d75463c013356c0b4004 /
sdistf7a27cf40c6b972b40c2e982085752e8e6fa5aa5af6a4e45452b4dc1dfd8c3e2;
75/76 curated members, exact source/license/notices, protected/unexpected content0.
Precedingfe22a3a full2357/7 OS skips and hosted2364 passes are historical.
Current full CI receipt is below; PR144 independent review found the design-region issue recorded below.

Fresh native environment qualification again reports blocked/executable_permissions/
execution_authorized=false. No protected repair or trust exception is applied.
Latest registered storage snapshot retains82 attempts/9,798,942,720 cumulative
reserved bytes/10GiB ceiling/895MiB approved remainder; free25,690,238,976/floorOK;
18,030,073 logical/48,308,224 allocated. Registered scope excludes OA/ADE/PDK/vendor
and unregistered roots. Original unrelated OCN edit SHA256 remains exact; selected
99,964-file local baseline check found0 changes. These are distinct observations,
not a new full native source/PDK scan. Program native simulations/reservations/
deployments/deletions/license/permission changes remain0.

GREL03 authority forms/local plans and GREL07 public CI/preservation are partial.
GREL03 authoritative native admission/reconciliation/cancellation/recovery/renewal,
GREL04 generic ADE copies/DC/AC/TRAN, GREL05 new-job extraction/Sweep and GREL06
actual clean-client runs remain NOT_IMPLEMENTED/NOT_RUN. Generic release BLOCKED.
Installation owner must establish the trusted executable/dependency chain before
native acceptance; the895MiB permission persists but does not replace trust.
GREL08/publication remain excluded. No next-phase approval is requested in02–07.

The following dated sections preserve earlier failure/correction/source receipts.

# GREL-07 independent CI/preservation checkpoint

Independent public verification is implemented while GREL02/03 native prerequisites
remain blocked. This does not mark the operational-security phase complete.

A GitHub-hosted windows-2022/Python3.12.10 workflow runs locked lint/type/unit,
security and dependency audit,85-schema compatibility, curated distribution
inspection and clean installed SDK/operator/bootstrap/state checks. Read-only token,
SHA-pinned inspected checkout/setup-uv actions, fixed uv0.12.6 binary checksum,
no persisted credentials/cache/artifact upload/secret/self-hosted access. No
privileged workflow trigger or laboratory VM is used. Contributions/security/
fictional bug-report instructions preserve Apache conditions and private data.

Installed verification uses only shipped fixed assets, staged manifest candidate,
activation collision/partial preservation/append-only deactivation. Durable local
AnalysisStore replay, SweepStore, original/replay/ledger sentinels live outside
site-packages. Exact19 synthetic state hashes survive same-version reinstall and
uninstall; import absent afterward. Final runtime requirements are uv.lock pinned.
Earlier unconstrained allowed-range install also passed but is not locked CI proof.
Native and semantic N-to-N+1/downgrade migration remain NOT_TESTED. Live migration
and active-pointer replacement are UNSUPPORTED and explicitly denied. Generic
Storage, deletion, cancellation and native result operations stay disabled. No
old-result consent, deletion/refund, stale-lock removal or process termination.

Local package/source-license/installed protocol/bootstrap/reinstall/uninstall PASS;
Ruff/mypy67/security18/dependency/85-schema PASS. Initial exact local full:2338 PASS/7 OS skips/56 warnings in788.53s.
Hosted first run37647459157:2343 PASS/2 FAIL, all privileged Windows symlink
fixtures ran (no OS skips). Actual checkout-origin spelling dependency and cold
PowerShell ready deadline caused failures. Synthetic origin inputs now include
explicit reject cases and ready wait is15s; production guards are unchanged.
Workflow uses short exclusive RUNNER_TEMP pytest base. Original failures retained.
Corrected full: PASS_ON_FE22A3A_HISTORICAL_AFTER_LIFECYCLE_FIX; corrected hosted: PASS_ON_FE22A3A_HISTORICAL_AFTER_LIFECYCLE_FIX.
Local green is not hosted green. Node20 pinned actions are forced to Node24 by
GitHub; setup/lint/type steps passed with a deprecation warning.
Primary source review is not independent review; automatic PR review pending.
Source wheel/sdist identities and native blocker are recorded in GREL_03_RESULT.md.
No branch protection/administrator/publication setting was changed.

Generic operational lifecycle/storage/native evidence and versioned migration
still depend on GREL02-through-06. GREL07 PARTIAL; general release BLOCKED.
GREL08/publication NOT_AUTHORIZED. Preserve continuous approval and complete the
remaining actual gates after the installation owner supplies a trusted executable
and dependency chain. See OPERATIONAL_PRESERVATION.md and NATIVE_RESUME_BOUNDARY.md.

Parent PR143 independent P1 native-target binding and primary directory-ancestor
security correction is integrated. Prior2338 local and hosted46c56a5 PASS are
historical source receipts. Parent assets changed, so that candidate was superseded; its exact local/hosted receipts appear below; no old artifact hash is reused as this head.
The in-progress test-only correction local invocation was superseded and stopped
as its source changed. Failed/interrupted evidence is retained. Final source is
frozen for new checks; no native deployment or permission change occurred.


## Exact pre-lifecycle-correction receipt

Sourcefe22a3a: local2357 PASS/7 OS symlink skips/56 warnings in808.40s;
187 source/test file hashes unchanged at completion. Hosted PR run37650489494
at that exact source passed2364 tests/56 warnings in230.45s, security18,
strict dependency audit,85 full schemas and package/installed preservation.
Local wheel5b64108d4363fb562d796c12e37d333eccc944281a9b5b37bdbf85309abf4e08 /
sdist9cd2a44cab26252316b95e59b1e1c559c5bb7c80fc3ff501fbc6ca3747b64362.
Hosted wheelc3d9385fa9beae7e5740dabd8912b9a28349fe1e50b85a61fa766090ce723cad /
sdist4da01722e53d9feb7b4729af0d9c2a9cc1814082c68b333a83465acbcfe266a3.
Each audit matched its own checkout bytes; local and hosted artifacts are distinct.

Later independent PR143 review found activation target unbound. Parent69d3f43
adds exact manifest/profile-root validation to activate and deactivate, with
exported-command no-write regressions. The installed acceptance script now
rejects the ordinary unbound Windows staged tree and tests positive lifecycle
only with explicitly synthetic target-bound hash-valid content. No positive
Linux installation or native qualification is inferred. Fresh affected94 PASS/
2 OS symlink skips; Ruff/mypy67 PASS. New local package PASS; current hosted full receipt follows below.
Earlier full/package/CI receipts are retained as historical evidence.


## Current independent hosted receipt

PR workflow37652706492/job112899890790 on exact source0ee2c17 completed SUCCESS:
2366 PASS/0 skips/56 warnings in177.28s. Hosted privileged Windows ran all symlink
fixtures. Ruff/mypy/security18/dependency/85-schema/package/installed state gates
PASS. Hosted wheelbcf81db757c25a6b22fc96ab07afd2b246f4fc5997ff14fc76981a48416faf8c /
sdistaa3b7eef9921f1872f5bee853e7dbafdc39e467bcbf48f4e567a2c7eed220995;
75/76 audited members match that checkout exactly. Hosted and local artifact hashes
are separately recorded; their identities are not interchangeable. Synthetic
positive lifecycle is explicitly hash-valid disposable target content, not a
qualified Linux profile. Unbound staged activation is denied.19 synthetic state
files survive reinstall and uninstall; native jobs0. Semantic N-to-N+1/downgrade
and native migration remain NOT_TESTED. No universal migration claim is made.

PR144 is ready/unmerged. Automated independent review is pending after its ready
transition; primary inspection is not independent approval. Parent PR143's two
independent P1 findings were fixed, with a bot+1 afterward as recorded in its
report. Later documentation-only merge/receipt heads are not the cited0ee2c17 CI
head;271 checked Python source/test/script inputs remain byte-identical. Any new
head workflow is reported separately, never inferred PASS. Main553276d unchanged.


## Independent PR144 review correction

Independent review of0ee2c17 found P2: globally keyed numeric regions prevented
one grant from planning both a zero-variable design and a parameterized design.
Each region now requires design_id. Uniqueness is scoped to(design_id,logical_id),
region designs must belong to the grant and planning selects only request.design_id.
Exact registered-variable completeness and unit/range denials remain. Missing
unscoped draft forms are rejected; no operator grant is rewritten or renewed.

Fresh26 operation tests PASS; combined legacy analysis/operation65 PASS, Ruff/
mypy67 PASS. New tests cover zero-variable and two parameterized designs sharing
one grant, same logical variable names with different numeric ranges, irrelevant
other-design regions, same-design duplicates, unknown design and missing scope.
No journal/lock/admission is created. Installed verification now checks both
zero-variable and parameterized requests and stable distinct plan identities.
An initial synthetic fixture incorrectly used strict Python validation of JSON
lists:22 PASS/4 fixture errors plus lint line-length findings. JSON entry-point
validation and formatting corrected the fixtures; historical evidence retained.
Previous0ee2c17 CI2366 and artifacts above are historical after this source change.
New local package PASS; exact hosted full/review receipt is pending; native trust remains BLOCKED.


PR144 review bot reacted+1 at2026-10-07T16:46:55Z after corrected233e27e ready
transition. The automation supplied no further suggestions; no formal approval or
new separately head-bound text review is inferred. Prior P2 and correction remain
visible. Fresh installed package confirms two design scopes under one fictional
grant, stable distinct plan identities,19 synthetic state files preserved after
same-version reinstall/uninstall, and absence of import afterward. Native jobs0.


## Final corrected independent receipt

Exact source233e27e: hosted PR run37654390528/job112905827756 SUCCESS;
2373 PASS/0 skips/56 warnings in258.88s. Lint/mypy67/security18/dependency/
85-schema/package/installed two-design form/bootstrap/reinstall/uninstall gates
PASS. Hosted wheel34d4b8f10dc3950925557dffc883027b55f60bc5b5d74177487da670e5bddcc2 /
sdist43edc5d6c62d59aaf983eb3f1d50f96235337e870021707eb277bcfdb80fd8bb;
75/76 curated members match that checkout/source/license/notices, protected and
unexpected content0. Current local artifacts at the top are independently audited
Windows workspace bytes; do not substitute either artifact identity for the other.

271 local Python source/test/script inputs are unchanged after the checks. Later
receipt commits alter only documentation and cite this tested source explicitly.
New documentation-head workflows are not inferred PASS from this receipt. PR143/
PR144 are ready/open/unmerged; no direct main write or merge. Three independent
findings(two parent P1 and one P2 design scope) are corrected with regressions.
Bot+1 signals after corrected ready transitions are distinct from formal approval.

General release remains BLOCKED. GREL02 native positive trust/attestation, GREL03
native shared ledger/admission/lifecycle/recovery/renewal, GREL04 actual generic
ADE execution, GREL05 new-job extraction/Sweep, GREL06 clean actual Codex and
GREL07 native operating/migration qualification remain incomplete. Existing02–07/
895MiB permission persists; no approval/ledger/consumption reset. Zero program
native simulation/reservation/deployment/deletion/permission/license changes.
Installation-owner trusted executable/dependency chain is the first external gate;
NATIVE_RESUME_BOUNDARY.md gives the ordered resume boundary. GREL08/publication
are not authorized. No additional phase question is asked within02–07.
