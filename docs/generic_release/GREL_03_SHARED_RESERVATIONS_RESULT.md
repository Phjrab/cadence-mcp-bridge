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

- Related local207 PASS /5 skips /19.79s: four POSIX-only checks and one OS-denied
  Windows symlink. Disposable actual files/processes, not native execution.
- Ruff PASS; mypy70 source files PASS; all85 full MCP schemas PASS.
- Actual VM Python2.6 grammar-only parsing of five fixed assets PASS, no execution,
  write or simulation.
- Security18 PASS /1.30s; locked dependency audit: no known vulnerabilities.
- Initial installed-wheel/bootstrap/accounting/reinstall/uninstall PASS;29
  synthetic state files preserved. This build predates the README edit.
- A README-final package run also PASS/29 retained files, but predates the
  subsequent receipt type correction. Both old logs remain historical.
- Final source packaging and source-scoped CI/review are pending.
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
