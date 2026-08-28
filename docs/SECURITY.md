# Security and Reliability Baseline

## Security objective

The bridge provides a small, reviewable path from twenty-two MCP tools to fixed simulation profiles,
three metadata-only design discovery operations, one fixed write plan, and one confirmation-gated
validation operation. It is not a general remote
administration, file access, OCEAN, SKILL, netlist, or shell interface. Every boundary fails
closed when identity, path containment, allowlist membership, process ownership, payload shape,
or output limits cannot be proved.

## Assets and protected data

Protected assets include SSH private keys, passwords, PATs, OAuth tokens, license values and
files, PDK models, proprietary netlists, full PSF/raw data, design libraries, unrestricted logs,
and the integrity and availability of the CentOS/Cadence installation. None may be committed,
placed in audit records, or returned through MCP.

The remotely writable application area is:

```text
/home/buet/cds_work/.cadence_mcp
```

The user separately approved `/home/buet/cds_work/MCP_WorkLib` for one exact copy-based validation.
The Cadence installation, PDKs, shared libraries, source design data, CentOS system files, and all
other paths remain read-only and outside the runner contract.

## Trust boundaries and data flow

```text
model/user
  -> twenty-two typed MCP tools
  -> CadenceService (UUID ownership and input validation)
  -> local bounded ADC measurement engine, or
     OpenSshBackend (fixed argv, ssh alias, runner path, command allowlist)
  -> Windows OpenSSH with BatchMode and strict host-key verification
  -> fixed cadence-runner
  -> fixed fixture/actual profile or metadata-only discovery helper
  -> isolated .cadence_mcp runtime and metadata-only MCP response
```

Untrusted data is limited to a lowercase RFC 4122 job UUID, the closed `stdout|stderr` stream
enum, an integer from 1 through 200, identifiers that must exactly match reviewed allowlists, and
the finite numeric fields of the fixture variable object. The actual profile accepts only an empty
variable object. Measurement requests additionally accept only the closed synthetic contract ID,
finite arrays bounded to 4,096 values (exactly 1,024 FFT samples), an exact NN/FF/SS mapping, and a
short unit label. Profile identity, analysis, corner,
outputs, units, ranges, source template, timeout, remote root, runner path, and executable are
compiled into reviewed source. The MCP caller cannot supply shell text, paths, environment
values, script content, netlist content, arbitrary analyses, or arbitrary outputs.

Each SSH call uses an argument list and `shell=False`; there is no public raw-command method.
The runner independently validates every argument before deriving a path. Derived job paths are
formed only after UUID validation and result metadata independently proves containment under the
fixed jobs root.

## Threat model

| Threat | Attack surface | Control | Residual risk |
| --- | --- | --- | --- |
| Command injection | job ID, stream, line count | closed schemas, canonical UUIDs, fixed runner commands, argv execution without a local shell, runner-side validation | a vulnerability in OpenSSH or the fixed runner remains possible |
| Path traversal or symlink escape | job/artifact/retention paths | no caller paths, fixed jobs root, relative artifact validation, real-path containment, cleanup skips symlinks | a privileged remote user could alter the trusted installation |
| Secret disclosure | stderr, log tail, result summary, audit | local redaction, bounded safe error envelopes, metadata-only results, fixed audit fields, pre-commit secret scan | unknown secret formats require pattern updates |
| Spoofed job ownership | cancel/status identifiers | server-generated UUID, per-process cancellation ownership, returned-ID match | read-only status remains available to a caller that knows a valid UUID |
| PID reuse or stale process state | cancellation and recovery | PID=PGID, live check, current PGID, non-zombie state, exact process start marker | CentOS process inspection is trusted |
| Partial write or power loss | request/status/result files | mode-600 temporary file plus atomic rename; result-based status recovery; otherwise terminal `unknown` | a failure before audit append can leave a job requiring operator review |
| Resource exhaustion | output, logs, results, job queue | 65,536-byte transport limit, 200-line log limit, 1 MiB bounded tail scan, fixed result fields, concurrency one | submission volume can still consume job directories until reviewed retention action |
| Repudiation | job submission/cancellation | fsynced mode-600 JSON Lines events with timestamp, actor, origin, job ID, and profile | remote account compromise can alter user-owned audit files |
| Destructive cleanup | retention operations | 30-day candidate policy, fixed jobs root, UUID-only directories, symlink rejection, dry-run-only command and script | deletion requires a future reviewed, explicitly approved mechanism |
| Dependency compromise | Python packages | `uv.lock`, hashes, strict `pip-audit`, minimal runtime dependencies | vulnerability databases may lag new disclosures |
| Proprietary design disclosure | library/cell/view discovery | PDK exclusion, exact nested allowlist, real-path and symlink checks, names/existence only, helper never opens a cellview file | allowlisted names themselves are disclosed |
| Design modification or lock creation | OCEAN/SKILL headless checks | fixed no-graph scripts, isolated working/log directory under `.cadence_mcp`, no design open/save calls, before/after metadata and lock fingerprints | Cadence installation behavior is trusted |
| Profile parameter injection | profile, corner, numeric variables | closed schemas, local registry, finite range checks, empty actual-variable schema, safe token formatting, remote registry/source revalidation before job creation | each future actual profile requires separate review |
| ADE state modification | actual testbench automation | fixed read-only state/source paths, source copied into `.cadence_mcp`, reviewed wrapper, before/after metadata and lock fingerprints | correctness depends on the approved existing ADE-generated netlist |
| Warning masking | actual Spectre completion | exact `CMI-2477` code allowlist with maximum count two; every other or additional warning fails | an allowed PDK warning may still merit circuit review |
| Measurement ambiguity | ADC samples and metric selection | versioned closed contract, fixed units/formulas/FFT policies, request rejection without contract, actual-circuit inputs kept unresolved | a future actual contract requires separate user approval and review |
| Measurement payload exhaustion | bounded numeric arrays | finite-only values, 4,096-value general limit, exact 1,024-value FFT limit, local deterministic processing | repeated allowed calls can still consume local CPU |
| Unauthorized design write | library or mutation request | exact fixed source/target/property, permanent PDK/shared/source classification, canonical plan, target nonexistence check, exact confirmation | the incomplete approved target now exists, so all reruns fail closed pending a new authorization |
| Release before write acceptance | tag or GitHub release | version remains 0.1.0, release checklist requires copy apply/rollback evidence, no v1 tag while blocked | final release requires a resumed WP-11 run |

## Origin and audit contract

Every new request records `origin` as `mcp` or `operator` and a bounded `submitted_by` identity.
The MCP backend always passes the literal `mcp`; direct reviewed runner use may pass only the
literal `operator`. Any other value is rejected before job creation.

The runner appends one JSON object per line to:

```text
/home/buet/cds_work/.cadence_mcp/audit/events.jsonl
```

The audit schema contains exactly `timestamp`, `event`, `actor`, `origin`, `job_id`, and `profile`.
It never contains a command, path, environment value, license, log, netlist, circuit parameter,
or artifact payload. Appends are locked, flushed, and fsynced. The fixed `audit-tail` maintenance
command returns at most 100 lines and 65,536 bytes; it is not exposed as an MCP tool.

## Output and redaction policy

SSH stdout and stderr are each rejected above 65,536 bytes. Log tail reads at most the requested
200 trailing lines, scans at most 1 MiB, returns at most 65,536 UTF-8 bytes, and reports the limit,
returned bytes, exact original bytes when known, and whether truncation occurred. Before MCP
delivery, known tokens, private keys, license endpoints, and Windows user-profile names are
redacted; the response reports whether redaction occurred.

Results contain only a 512-character completion summary, up to 16 allowlisted artifact metadata
records, origin, storage containment, and explicit summary/artifact truncation metadata. Raw PSF,
netlist content, and unrestricted Cadence logs are never result fields. Result summaries pass
through the same local redactor before reaching MCP.

Discovery responses contain only allowlisted library/cell/view names, an allowed-cell count, and
cellview existence. They explicitly set `proprietary_content_included=false`. PDK libraries,
remote paths, file names inside cellviews, file bytes, model data, and cellview content are never
response fields.

Profile results contain only the existing bounded summary and artifact metadata. The reproducible
manifest, copied actual netlist, and generated wrapper remain in the mode-700 job directory and are
not embedded in MCP output. Raw waveform, generated netlist, ADE state, and proprietary circuit
content are never direct response fields.

Synthetic measurement results contain only structured scalar/vector metrics, units, formulas, and
a small manifest with contract ID/version, processor identity, and canonical input SHA-256. The
input arrays are not echoed in results or written to remote storage. Measurement tools cannot read
PSF, netlists, models, paths, or arbitrary signal expressions and never invoke SSH.

## Process, concurrency, and recovery

A blocking `flock` on the fixed runner lock permits at most one Spectre worker to run. Concurrent
submissions receive distinct UUIDs and wait as queued jobs. Cancellation verifies the stored PID,
PGID, current PGID, non-zombie process state, and exact start marker before signaling only that
process group. A mismatch fails closed.

Request, status, and result JSON use a same-directory temporary file, mode `600`, followed by an
atomic rename. After interruption or power loss, an existing result repairs a stale active status.
Without a trustworthy live worker or complete result, status becomes `unknown` with an
operator-review message; the runner never guesses success and never signals a reused PID.

## Retention and cleanup

Terminal job directories become retention candidates after 30 days. WP-07 supplies only a
dry-run planner: `scripts/cleanup-remote-jobs.ps1` calls the fixed `cleanup-dry-run` command, which
accepts no arguments and cannot delete. It examines only canonical UUID directories whose real
parent is the fixed jobs root and skips symlinks and unrelated files. Automatic or destructive
remote cleanup, force-push, and destructive remote repair are prohibited. Any future deletion
requires a separate reviewed change and explicit operator approval.

## Controlled-write gate

`src/cadence_mcp_bridge/write_policy.py` is intentionally fail-closed. `gpdk090`, `analogLib`,
`basic`, `MyDesignLib`, and `MyFirstDesign` are non-writable. Only `MCP_WorkLib` and the exact
`mcpMutationTest=validated-v1` contract are eligible. The runner accepts no caller path, library,
cell, view, property, value, or script text. The V2 contract fingerprints the preserved V1 target,
rejects an existing V2 destination or backup, and refuses source/V2 OA lock, panic, or recovery
artifacts. The V2 plan and read-only API preflight passed, but an active source lock owned by
Virtuoso PID 25425 blocked copy before any V2 design write. See `docs/DESIGN_WRITE_POLICY.md`.

## Verification

Run the repeatable local security gate:

```powershell
.\scripts\verify-security.ps1
```

It scans tracked and untracked repository files for credential-like filenames, private-key
headers, GitHub token formats,
and concrete license endpoints; runs the dedicated path, injection, Unicode, redaction, audit,
truncation, cleanup, PID, partial-write, power-loss, and concurrency tests; exports all locked
third-party dependencies; and runs strict `pip-audit`. On 2026-08-28 the audit reported no known
vulnerabilities.

## Forbidden capabilities

- generic shell or arbitrary SSH execution
- arbitrary SKILL or OCEAN evaluation
- arbitrary path, profile, netlist, environment, or command input
- unrestricted file read, write, or delete
- PDK, shared library, Cadence installation, or CentOS system modification
- credential, license value, circuit data, raw PSF, or unrestricted log return
- automatic destructive remote cleanup, direct `main` push, or force-push
