# GREL-03 shared-reservation implementation checkpoint

Status: PARTIAL; generic release BLOCKED. Continuous GREL02–07 and the existing
895MiB remainder are authorized; no repeat approval is requested.
Latest main553276d28c54d8e87092229d102bfd05ec98e74f remains unchanged.
This feature is stacked on unmerged PR145 /81aebdd, preserving ancestors.

The shipped internal adapter uses the existing counter, native job markers and
physical EDA lock, with barrier-first immutable intent/receipt writes, lookup-only
replay, conservative crash uncertainty, same-grant accounting and in-flight
disk floor. Schema2 carries the asset; schema1 history remains verifiable.
Launcher simulation stays disabled. See SHARED_RESERVATIONS_V1.md.

## Observed validation

- Historical local207 PASS /5 skips /19.79s: four POSIX-only checks and one OS-denied
  Windows symlink. Disposable actual files/processes, not native execution.
- Ruff PASS; mypy70 source files PASS; all85 full MCP schemas PASS.
- Actual VM Python2.6 grammar-only parsing of five fixed assets PASS, no execution,
  write or simulation.
- Security18 PASS /1.30s; locked dependency audit: no known vulnerabilities.
- Initial installed-wheel/bootstrap/accounting/reinstall/uninstall PASS;29
  synthetic state files preserved. This build predates the README edit.
- A README-final package run also PASS/29 retained files, but predates the
  subsequent receipt type correction. Both old logs remain historical.
- Final corrected-source installed protocol/context/forms/generic compiler/bootstrap/
  two-batch accounting/reinstall/uninstall PASS;29 synthetic files preserved.
- Retained audited wheel78 members SHA256
  0fa90e1bb75d0040a44616bd579711dce2f30e3a54dc973388de7259c6783029;
  sdist79 members SHA256
  189c29ad9ced80168d214aa15385f44b3b2c069a869b3dd3b8d43946d77ac890.
  Source/license/notices exact; unexpected/protected content0.
- Final325 inputs have zero unexpected drift. Corrected snapshotSHA256
  dfe9875e8f9d2299e58c0bd3b07aa73b2c406df24ee108c8ae53989b44226994.
  Its sole deliberate change from the original snapshot is the Ubuntu uv checksum.
- Source-scoped hosted CI/review is pending at3928377ea52626011edcabc17a24c342e5f2fc29.
  PR146 is ready/open/unmerged, stacked on145.
- Primary review corrected receipt type equality: boolean schema versions and
  floating counters cannot compare equal to the required integer receipt.
- PR145 docs-head81aebdd: both checks success, runs37709365383/37709359975.
  Its older2473-test source receipt remains scoped to a3f5fb8.

No native simulation/reservation/deployment/deletion/protected-permission/license
change, budget increase, merge, GREL08 or publication occurred. The last live
82 /9,798,942,720 observation was not rerun here. Other-worker OCN rehashed unchanged:
2cf3673f4e80cb3c2bd6815f919c0d2aaf9b20a944b2ef1b8eb231589c634b32.

## Remaining boundary

This is accounting infrastructure. Production provider/OS operator attestation,
native provisioning and terminal worker receipts are absent. No public dispatch
is connected. No generic native circuit/API/input/extraction/Sweep/clean-client
gate closes. Last native trust check remains blocked/executable_permissions,
not rerun. MyDesignLib identifies a circuit library, not a trusted Cadence
executable/dependency installation. Owner-supplied trusted installation and
fresh qualification remain required before native deployment/jobs. Independent
authorized implementation can continue without phase reapproval.


Initial source4396c4e Ubuntu CI failed before tests because its uv Linux archive
was compared with the Windows archive checksum. Official GitHub release asset
metadata for uv0.12.6 gives Linux SHA256
8681d8921e7d520fb368991dcf5f9c1905b80f5bf2a265a0ed085c8d8e342477;
the platform-specific pinned checksum is corrected without changing version.
Failures37711436546/job113098028221 and37711481159/job113098168368 are retained.
Windows checks at that initial source were still running when observed.


## Corrected reservation identity and legacy-marker review

Primary integration review added mandatory execution_input_sha256 in addition to
the OperationPlan hash, binding the compiler's generic DC/AC/TRAN settings.
Replay cannot substitute that digest; another operation in the same grant can
use a different compiled input. This does not authenticate the supplied digest.

Independent PR146 review at3928377 found one P1: current-ledger floor was applied
to historical native-v1 markers. NATIVE_MCP_V1.json verifies original21 attempts /
1,611,661,312 bytes. Marker validation now retains counts22–24 from that domain;
the current ledger and new before/after records retain the newer32 /
3,088,056,320 floor. Historical conservation guards and original policy are unchanged.
Regression tests prove old marker bytes preserved and current-ledger rollback denied.

Corrected related213 PASS /5 skips /19.33s; Ruff/mypy70 PASS; actual five-asset
Python2.6 grammar-only parsing PASS. Final corrected package/security/hosted
Windows+POSIX and independent review receipts are pending.
Final325-input snapshot4bf4256a4e6d31c5c44d662dcc236b771a8c648e4cbb8357b2e9b45d7b10ab89.
Earlier package/artifact/CI figures above remain source-scoped history.


## Final source/package/hosted checkpoint

Tested source52b5452664411152b84e114332507f745918800d (PR146, ready/unmerged):
- Local related213 PASS /5 skips /20.46s;35 bootstrap PASS /one OS skip separately.
- Ruff/mypy70 PASS. Fresh security18 PASS /1.13s; locked audit no known vulnerabilities.
- Actual VM source parsing: five Python2.6 assets PASS; no asset execution/write.
- Hosted Windows run37712345189/job113100964367:2527 PASS /4 POSIX-only skips /
  56 warnings /211.49s. Ruff/mypy70/security18/audit/85 schemas/all installed
  protocol/context/compiler/bootstrap/accounting/reinstall/uninstall PASS.
- Hosted Ubuntu run37712341835/job113101014540:56 PASS /zero skips /0.99s,
  including independently held flock and actual group-writable component refusal.
- Final local and hosted artifacts byte-identical: wheel78 members SHA256
  e09be827e092ac614759c4fce42a2c4a4057f9ea4c43b95c381114e65b7a482f;
  sdist79 members SHA256
  908db5556babfef92be92acffabb608db047bc7becace43600fca460ea5da819.
  Curated source/license/notices exact; unexpected/protected content0.
- Final installed accounting two batches/replay and29-file same-version
  reinstall/uninstall preservation PASS. Native install/migration not qualified.
- Final325 local source/test/package/contract inputs zero unexpected drift;
  snapshotc85049aff1a86e988fd05eba02881d96482081434d98ba1185007248e3f2bd03.
- One supported CI log read returned HTTP502; retry through the same reviewed
  backend succeeded. No CLI CI-log fallback was used.
- Independent P1 old-marker finding corrected. Latest automated review still
  in progress when this record was prepared; no formal approval or merge inferred.

Earlier logs and source/artifact receipts remain history. No GREL02–07 native
acceptance gate is promoted by this source checkpoint. Continuation remains
authentic production provider/operator confirmation, terminal worker/lock
integration, native source/copy/API/input attestation, new-job extraction/Sweep
and clean actual-client qualification. Native execution also still requires
owner-supplied trusted Cadence installation and fresh runtime qualification.


## Second independent marker correction

Review52b5452 at2026-10-08T01:26:19Z found P2: the unincremented native-v1
policy baseline was accepted as a reserved marker. Reserved markers now require
at least22 /1,745,879,040 (the original baseline plus one128MiB reservation).
Both baseline-pair rejection and one-field boundary cases are tested, while
valid old22–24 markers remain unchanged. Current-ledger floor and historical
policies/conservation guards remain unchanged. Final source revalidation follows;
52b5452 CI/package evidence above is historical after this correction.


## Third independent marker correction

Reviewe2eb709 found P2: independent count/byte floors permitted impossible legacy
pairs (e.g.22 /3,088,056,320). Audit now conserves the original21 /
1,611,661,312 baseline and fixed128MiB legacy increments, adjusted by preceding
immutable own variable-reservation records. It checks all marker pairs, each own
before/after and the current ledger, and rejects duplicate native marker slots.
It still never infers completion from a later counter or manufactures a receipt.

Tests now cover inconsistent legacy/current pairs, duplicate old slots, mixed
legacy+variable reservations, dropped variable records, and a genuine synthetic
500-attempt/10GiB exhausted state represented by actual immutable disposable files.
The first conservation test run had one stale fixture incorrectly using16MiB
for a legacy increment; it was corrected to the source-defined128MiB. Initial
failure log/test-temp evidence is retained. No historical guards or policy changed.
Earlier sourcee2eb709 evidence is historical after this correction.


## Independent identity-loss correction

Reviewe1a6437 found P1: disappearing128MiB own jobs (or cancelling variable
adjustments) could look like implicit legacy increments and lose grant/in-flight
usage. The same domain now requires a hash-bound operator migration anchor and
immutable per-UUID identity seals outside job folders. It retains the existing
counter/physical lock, introduces no mutable budget total, and denies missing
seals/jobs/anchor or uncovered post-migration slots without reinitialization.
Future legacy UUIDs must be explicitly predeclared; generic IDs cannot reuse them.
Unlisted legacy increments are not silently accepted. Provider authenticity,
real migration provisioning and supported renewal remain incomplete.

Tests delete disposable job records/seals for exact128MiB and64+192MiB cases,
check missing anchors, migration rebind, predeclared legacy identity conflicts,
unlisted increments and every durable write (now including the identity seal).
No real native migration, grant, deployment or reservation was created.
Earlier sourcee1a6437 package/CI evidence is historical after this correction.
