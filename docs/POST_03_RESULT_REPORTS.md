# POST-03: existing-result discovery and reports

This additive development feature follows POST-02 PR154 and is not included in
the immutable published v2.0.0 files. Support remains the professor's standard
CentOS/Cadence/PDK VM on personal VMware. It creates reports from already completed
native jobs; reporting never submits Spectre, retries extraction or reserves capacity.

## Find and capture

Use explicit operator settings and a registered context:

```text
cadence-mcp-bridge operator-results jobs --settings <absolute-runtime.json> --context <id>
cadence-mcp-bridge operator-results jobs --settings <absolute-runtime.json> --context <id> --offset 32
cadence-mcp-bridge operator-results capture --settings <absolute-runtime.json> --context <id> --operation-id <uuid> --expected-plan-sha256 <digest> --output <new-absolute-report.json>
```

The catalog reads a validated retained admission/event chain in a read-only SQLite
transaction. A WAL database or existing journal sidecar is rejected before SQLite
reads, so reporting cannot initialize shared-memory files or recover a hot journal.
Use the existing writer/status recovery path first. It returns at most32 entries
and a next offset. It does not initialize
a missing journal, contact SSH or reconcile remote progress. If a completed job
still has stale local state, use the existing status command before capture.

Capture requires the exact locally retained SUCCEEDED job and plan. It uses the
existing authenticated result action, checks terminal receipt identity, verifies
result content and carries verified ADE/reader conditions into the report. It
does not require new submit authority for an already admitted job. Existing
context/runtime/result integrity checks remain mandatory. Output is exclusive:
an existing file or any selected operator settings, contract, provider, grant,
journal or lock destination is rejected. Reports are bounded to262144 bytes.

Native resource-capable clients can read `cadence://operations`,
`cadence://operations/page/{offset}` and
`cadence://operation/{operation_id}/{plan_sha256}/report`. The report resource
contacts the VM through verified result retrieval; the catalog stays local. These
resources preserve all85 common and11 conditional native tool declarations.

## Search, compare and preserve provenance

```text
cadence-mcp-bridge operator-results show --report <absolute-report.json>
cadence-mcp-bridge operator-results find --directory <absolute-report-directory> --design-id <id> --captured-date 2026-10-13
cadence-mcp-bridge operator-results find --directory <absolute-report-directory> --conditions-sha256 <digest>
cadence-mcp-bridge operator-results compare --reports <report-a.json> <report-b.json>
```

Use a dedicated report directory: find validates every JSON entry, rejects
malformed/unrelated documents and stops above256 entries. Offline reading rejects
links, duplicate JSON keys, oversized/nonregular files and detected identity/content
drift. Comparison accepts2–16 distinct job IDs only when design/analysis/environment/
PDK/runner/variables, verified ADE inputs, source/state/static/model hashes,
reader/transfer definition, effective input and metric conditions all match.
Changed conditions produce a closed mismatch rather than a numerical comparison.

Reports preserve values, units, logical signals, source roles, scientific
definitions, job and plan identity, provenance hashes and verification scope.
DC values and delivered power, sampled AC gain/phase and saved transient summary
quantities retain their existing definitions. An AC zero transfer may have null
dB/phase; other nonfinite or undefined quantities are rejected. These are the
existing extracted quantities, not new bandwidth/phase-margin/offset/slew evidence.

`captured_at_utc` is the report capture date. An authenticated simulation timestamp
is not available in the retained contract, so `execution_timestamp` stays null.
The date filter never labels a capture date as the simulation date. Offline files
are local content records and can be edited by their owner; their stored provenance
is not a new remote attestation. Output explicitly reports
`LOCAL_RECORD_CONTENT_ONLY_NOT_REMOTE_REATTESTATION` at offline read/compare time.

## Verification checkpoint, 2026-10-13

Initial focused report/provider tests36 PASS; after the WAL preservation guard,
affected report/result/admission/lifecycle tests126 PASS. Ruff/mypy102 source files
PASS. Isolated
installed-wheel catalog/resource and offline CLI checks PASS using explicitly
synthetic data; those checks do not qualify actual VM or actual apps. Full local,
security/package and final hosted checks are recorded with the final feature SHA.

Source-host CLI captured an existing actual standard-VM inverter DC result twice.
Four quantities and verified ADE conditions were preserved; repeated measurements
were equal. Selected settings/contracts/provider/grant and journal bytes remained
unchanged. This is SOURCE_HOST_CLI_ACTUAL_VM evidence, not exact installed-artifact
or actual-client acceptance. No new simulation, extraction or reservation occurred.
An additional isolated wheel with locked dependencies captured/read/repeated that
actual result with the same four quantities and unchanged selected files. This is
LOCKED_INSTALLED_WHEEL_ACTUAL_VM evidence, still not actual-app acceptance. The
initial disposable installation resolved newer dependencies; they were replaced
with the repository's hash-locked runtime before any VM test. The completed package
audit also preserves63 synthetic state files through reinstall/uninstall and passes
security18, locked dependency audit and original contract compatibility checks.
The final guard wheel SHA256 is
`80d19ccc0109b9499997400d60ab959b52fab59aa0c5d2294aab0cc1dfd7866d`.

The first full run had3628 PASS/392 skips and three disposable-storage failures.
A diagnostic traced failure to a271-character Windows fixture audit filename;
the storage implementation retained PARTIAL rather than reporting false completion.
Short-path report/storage tests91 PASS/8 POSIX or symlink skips. No production
storage protection was relaxed. The earlier files and failure trace are preserved.
Final full-source verification runs separately with a short fixture root, followed
by exact feature-SHA hosted verification. Neither is implied by the affected pass.

Fresh read-only accounting remained112 attempts/13,825,474,560 reserved bytes under
the approved16GiB ceiling; disk-floor checks stayed enabled. Correction history20/20
and every past failure/result/grant remain preserved.

For POST-06, the user's new explicit Claude access approval passed the normal
Computer Use access check and allowed reading window accessibility. Screenshot
capture failed with `FrameArrived timed out`, then a fresh window selection and
activation failed with `window capture timed out`. No coordinates or app inputs
were used after failed capture. Actual Claude/build/mode acceptance remains pending.

POST-04 through POST-07 retain continuous implementation approval. Extraction-only
recovery, exact selected deletion before separate compaction and reusable scientific
measurements require their own implementation and evidence. This report feature
does not mark those phases complete or alter published2.0.0. The retained native
source correction ceiling is consumed20/20; a numeric increase for required worker
changes is pending, without resetting consumption. See
[the bounded next implementation](POST_04_07_RUNTIME_BOUNDARY.md).
