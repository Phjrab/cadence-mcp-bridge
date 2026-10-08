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
