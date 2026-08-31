# Operations

## Restricted runner deployment

WP-02 deploys only the reviewed files under:

```text
/home/buet/cds_work/.cadence_mcp
```

Run from Windows PowerShell:

```powershell
./scripts/deploy-remote.ps1 -WhatIf
./scripts/deploy-remote.ps1 -Confirm
```

The script has no remote-path parameter. It uses `BatchMode=yes`, strict host-key checking,
fixed source files, temporary files in the approved root, atomic rename, and fixed modes.

## Runner contract

The only public subcommands are:

```text
version
health
submit-smoke <job-id> <mcp|operator>
status <job-id>
log-tail <job-id> <stdout|stderr> <lines>
result <job-id>
cancel <job-id>
cleanup-dry-run
audit-tail
```

Job IDs are lowercase RFC 4122 UUID strings. Profile, executable, and remote paths are fixed in
reviewed source; no command, script text, netlist text, or path is accepted from the caller.
Log tail is restricted to 200 lines and 65,536 bytes. `cleanup-dry-run` and `audit-tail` are fixed
operator maintenance commands and are not MCP tools. The cleanup command accepts no path, age,
or deletion flag; `audit-tail` returns at most 100 JSONL records and 65,536 bytes.

## Process and concurrency strategy

CentOS diagnostics confirmed `nohup`, `setsid`, `flock`, `ps`, `kill`, `pgrep`, and `pkill`.
Each worker starts in a new session with PID equal to its process-group ID. Cancellation verifies
the stored PID, PGID, process start marker, and current PGID before signaling only that group.
The worker traps termination and records `cancelled`. A blocking `flock` on the fixed runner lock
keeps the default Spectre concurrency at one while additional jobs remain queued.

Status and result JSON are produced by the CentOS Python 2.6 standard library. Files are written
to a per-job temporary file, mode `600`, and atomically renamed. Directories use mode `700`.

## Smoke lifecycle

The fixed profile is a small RC transient simulation. Submission returns after starting a
detached worker; it does not wait for Spectre. Poll `status`, then request `result` only after a
terminal state. Result output contains the process exit code, bounded completion summary, and
artifact metadata, never raw PSF data.

## Recovery boundary

The runner never writes outside its fixed root and never modifies CentOS, Cadence installation,
PDK, shared library, or design data. Unexpected PID/PGID/start-marker mismatch makes cancellation
fail closed. Status repairs a stale active state from an existing result; when no result exists
and the recorded worker identity is absent, changed, or a zombie, it records `unknown` with a
bounded operator-review message. WP-07 retention remains dry-run-only; no automatic or
destructive deletion exists.

## WP-07 security operations

Run the local security acceptance gate before commit or deployment:

```powershell
.\scripts\verify-security.ps1
```

It runs the repository-file secret preflight, dedicated security tests, and a strict vulnerability
audit of all locked third-party dependencies. To inspect 30-day retention candidates without
deleting anything, run:

```powershell
.\scripts\cleanup-remote-jobs.ps1
```

New jobs carry `origin=mcp|operator`. The remote mode-600 JSONL audit records submission and
cancellation using only timestamp, event, actor, origin, job UUID, and fixed profile. Log responses
include byte-limit, returned-size, truncation, and redaction metadata. Result responses include
summary and artifact truncation metadata and never include raw PSF or netlist content.

## WP-02 acceptance evidence

Validated on 2026-08-28 against the verified CentOS 6.5 VM:

- required commands present: `bash`, `nohup`, `setsid`, `ps`, `kill`, `pgrep`, `pkill`,
  `date`, `mktemp`, and `flock`;
- runner health returned SSH `ok`, fixed host/user, both Cadence versions, OCEAN available,
  and `CDS_LIC_FILE=SET` without exposing its value;
- smoke submission returned in 792 ms and states were observed as
  `queued -> running -> succeeded`;
- Spectre result was exit code 0 with 0 errors, 0 warnings, and 1 accepted notice;
- result contained metadata for four bounded artifacts and no raw PSF content;
- invalid, multiline, metacharacter, traversal, wildcard, and option-like job IDs were rejected;
- cancellation reached `cancelling -> cancelled` with exit code 143 while an independent
  fixture process group remained alive;
- deployed directories and job directories were mode `700`; source, status, and result files
  were mode `600` or executable mode `700` as required;
- no temporary `.new` deployment files remained.

## Windows OpenSSH transport

`OpenSshBackend` resolves Windows `ssh.exe` and invokes only the fixed alias, runner path, and
allowlisted runner subcommands. SSH receives each local argument through an argv list with
`shell=False`. Batch mode prevents password prompts, strict host-key checking remains enabled,
and connect timeout is independent from the full operation timeout.

Both stdout and stderr are byte-bounded before UTF-8 decoding. Transport failures map to
stable timeout, host-key, authentication, unavailable-backend, invalid-input, or remote-failure
errors. Error details pass through the project sanitizer before reaching a caller.

Run the real health integration explicitly from Windows PowerShell:

```powershell
$env:CADENCE_MCP_RUN_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest tests/integration/test_real_ssh_backend.py -v
```

## WP-03 acceptance evidence

Validated on 2026-08-28 from the Windows D-drive worktree:

- Ruff and strict mypy passed;
- 43 default tests passed, with the opt-in integration test skipped by default;
- the opt-in real `cadence-vm` health integration passed without a password prompt;
- subprocess tests verified argv-list execution, `shell=False`, fixed alias and runner path,
  separate connect/operation timeouts, bounded stdout/stderr, and stable error mapping;
- all required malicious job-ID inputs were rejected before subprocess invocation;
- fixed method signatures provide no profile, path, shell text, or raw-command input.

## MCP stdio server

The installed MCP Python SDK is version 2.1.1. WP-04 uses its v2 `MCPServer` API and the
official in-process `Client(MCPServer)` test path. Start the protocol server with:

```powershell
.\.venv\Scripts\python.exe -m cadence_mcp_bridge
```

No banner is written to stdout. Application and expected-error logging goes to stderr. The
server exposes exactly twenty-two tools: six lifecycle tools, three metadata discovery tools,
profile list/detail/submission, eight read-only synthetic ADC measurement tools, one fixed write
plan, and one exact confirmation-gated write validation. No remote path,
netlist text, command, script text, arbitrary
analysis, or arbitrary output is accepted.

## WP-04 acceptance evidence

Validated on 2026-08-28 from the Windows D-drive worktree:

- the MCP SDK v2 in-memory client listed exactly six tools with structured input/output schema;
- tool annotations identified the four read-only tools, non-destructive submission, and only
  cancellation as destructive;
- mock success calls covered all six tools and mock failures returned stable error envelopes;
- submission returned a queued status within the client timeout without status/result polling;
- an EOF startup probe exited successfully with an empty stdout stream;
- Ruff, strict mypy, and the default pytest suite passed;
- real `cadence-vm` SSH health and MCP `cadence_health` integration tests both passed without a
  password prompt;
- no Codex Desktop configuration or CentOS files were changed by WP-04.

## WP-05 lifecycle verification

Run the single real lifecycle command from Windows PowerShell:

```powershell
.\scripts\verify-e2e.ps1
```

It uses only the six public MCP tools. The verifier requires SSH and Spectre health, submission
within the 10-second target, a terminal success before the five-minute deadline, exit code 0,
zero Spectre errors, artifact metadata, a 50-line/65,536-byte bounded log response, and job
storage contained under the fixed jobs root with mode `0700`. It prints metadata only; it never
prints license values or raw PSF data.

Submission uses its generated UUID as an idempotency key. If the submit SSH operation times out,
the service performs one status lookup for the same UUID. A matching job is recovered and owned;
otherwise the original timeout is returned. No second job is submitted.

The polling defaults are one second and a maximum wait of 300 seconds. Remote Spectre concurrency
is fixed at one. Failed, cancelled, and unknown terminal fixtures are rejected with bounded safe
messages. The actual cancellation isolation test submits five jobs, cancels one queued job, and
requires every independent job to succeed.

## WP-05 acceptance evidence

Validated on 2026-08-28 from the Windows D-drive worktree against `cadence-vm`:

- runner 0.3.0 deployed atomically under `/home/buet/cds_work/.cadence_mcp` and passed remote Bash
  and Python 2.6 syntax checks;
- `verify-e2e.ps1` reported health success, submit in 0.453 seconds, states
  `queued -> succeeded`, exit code 0, four artifact metadata entries, and job storage mode `0700`;
- the actual MCP concurrency/cancellation integration passed repeatedly: one of five jobs was
  cancelled and every independent job succeeded;
- unit fixtures covered succeeded, failed, cancelled, and unknown outcomes, plus submit timeout
  recovery with the same UUID;
- Ruff, strict mypy, the default test suite, and opt-in real lifecycle tests passed;
- no license value, raw PSF content, arbitrary command, arbitrary path, or proprietary design data
  was written to evidence.

## Codex Desktop operator flow

Install or update the user-level MCP entry with:

```powershell
.\scripts\install-codex-mcp.ps1 -WhatIf
.\scripts\install-codex-mcp.ps1 -Confirm
```

The script backs up the existing Codex config before change and is idempotent. It registers the
absolute virtual-environment Python executable, the module entrypoint, a 20-second startup
timeout, a 180-second per-tool timeout, and prompt approval for smoke submission and cancellation.
Restart Codex Desktop and use `/mcp` to confirm the server and exact twenty-two-tool allowlist. Detailed
acceptance prompts and recovery steps are in `docs/CODEX_DESKTOP.md`.

## WP-06 acceptance evidence

Validated on 2026-08-28 from the Windows D-drive worktree:

- installed Codex CLI `0.150.0-alpha.8` confirmed the supported MCP add/get/list interface;
- the current official Codex MCP manual confirmed shared host configuration, absolute stdio
  commands, startup/tool timeouts, and `writes`/per-tool prompt approval modes;
- the existing user config was backed up before registration;
- two consecutive installer runs left exactly one entry; the second run changed neither config
  hash nor backup count;
- `codex mcp get cadence-mcp-bridge --json` returned the absolute Python command, module args,
  absolute cwd, 20-second startup timeout, and 180-second tool timeout;
- a fresh ephemeral Codex host called `cadence_health` successfully and returned runner 0.3.0,
  Spectre available, and only `CDS_LIC_FILE=SET`;
- a fresh Codex host selected submit, status, and result tools for the smoke acceptance prompt and
  observed `queued -> succeeded`, exit code 0, zero errors, zero warnings, and four artifact
  metadata entries;
- no raw shell, SSH, file, SKILL, or OCEAN execution capability was added.

The running Codex Desktop process must be restarted before its `/mcp` UI can confirm the newly
written configuration. That UI-only confirmation is intentionally left to the operator because
restarting the app would terminate the current WP execution.

## WP-07 acceptance evidence

Validated on 2026-08-28 from the Windows D-drive worktree against `cadence-vm`:

- runner 0.4.0 deployed atomically under `/home/buet/cds_work/.cadence_mcp` and passed remote Bash
  and CentOS Python 2.6 syntax/version checks;
- Ruff and strict mypy passed; the default suite passed 86 tests with five opt-in integration tests
  skipped, and all five real integration tests passed when enabled;
- the dedicated 18-test security suite passed path traversal, shell metacharacter, multiline,
  NUL, option-like, full-width Unicode, emoji, redaction, truncation, audit, cleanup, stale PID,
  PID reuse, partial-write, power-loss, and concurrency controls;
- the tracked-and-untracked repository secret preflight passed, and strict `pip-audit` over every
  locked third-party runtime and development dependency reported no known vulnerabilities;
- real MCP-to-Spectre verification observed `queued -> running -> succeeded`, exit code 0, four
  artifact metadata entries, runner 0.4.0, and job storage contained with mode `0700`;
- simultaneous real submissions produced alternating `job_started`/`job_finished` audit pairs,
  proving the fixed `flock` kept execution concurrency at one;
- cancellation isolation passed: one queued job was cancelled and all independent jobs succeeded;
- the actual retention command returned `dry_run=true`, the fixed jobs root, 30 days, and no
  candidates; no deletion was performed;
- actual audit JSONL records contained only actor, event, job UUID, origin, fixed profile, and
  timestamp, and traced MCP submission and execution without secrets or circuit data.

## WP-08 read-only OCEAN/SKILL discovery

The runner 0.5.0 adds fixed `discovery-health`, `list-libraries`, `list-cells`, and
`inspect-cellview` commands. `discovery-health` uses reviewed scripts only and runs OCEAN and
Virtuoso/SKILL with `-nograph` and `-nocdsinit` from an isolated directory under `.cadence_mcp`.
The three metadata commands use the fixed `remote/config/discovery-allowlist.json`; callers cannot
supply a path or script.

Validated on 2026-08-28 from the Windows D-drive worktree against `cadence-vm`:

- installed `ocean -help` and `virtuoso -help` confirmed the legacy `-nograph`, `-restore`,
  `-log`, and `-nocdsinit` options;
- fixed OCEAN and SKILL scripts both started and exited headlessly within 60 seconds;
- actual runner and MCP calls returned only allowlisted names, counts, and existence metadata;
- the PDK library request was denied with runner exit 64 and a stable MCP `invalid_input` error;
- responses contained no remote path, `cds.lib`, OA filename, model, or cellview content;
- design-tree metadata and pre-existing lock-file fingerprints were identical immediately before
  and after a combined headless and discovery run; no save or new design lock occurred.

## WP-09 profile automation

Runner 0.7.0 exposes two separately classified profiles through the fixed `submit-profile` command.
`fixture-rc-transient` remains the synthetic fixture with bounded resistance, capacitance, and stop
time. `actual-differential-amplifier-tb2-transient` fixes `MyDesignLib/Differential_Amplifier_TB2`
schematic, ADE L `state1`, gpdk090 v4.6 section `NN`, 27 degrees C, transient stop `4m` (0.004
seconds), no caller-controlled variables, and no requested measurements.

The actual profile validates the fixed state, model, and source netlist before creating a job. It
copies the existing ADE-generated circuit netlist into the private job directory, creates a reviewed
wrapper, and records the source SHA-256 and applied configuration in `run-manifest.json`. It never
writes the original cellview, state, PDK, model, or simulation result directory. MCP exposes only
bounded completion and artifact metadata.

Validated on 2026-08-28 against `cadence-vm`:

- the fixture profile completed on the actual VM with exit code 0, zero errors, zero warnings,
  and one notice;
- result returned metadata for the manifest and bounded artifacts, never waveform or manifest
  contents;
- a resistance below the minimum was denied with exit 64 before a job directory was created;
- an unknown corner was denied with exit 64;
- all eight real integration tests passed, including actual profile, smoke, fixture, and discovery
  regression;
- design-tree and lock fingerprints were identical before and after profile execution.
- the actual profile completed with exit code 0, zero errors, two allowlisted `CMI-2477` warnings,
  and one notice; any other warning or more than two occurrences fails closed;
- the fixed bias parameters found in the ADE-generated input are recorded in the remote-only run
  manifest but remain unavailable as caller-controlled design variables.

## WP-10 ADC measurement contracts

The eight measurement tools run locally and read only `adc-synthetic-v1`, version `1`. They do not
submit a Cadence job or access a user design. Exact definitions, units, FFT policy, and the
Windows-Python reproducibility rationale are in `docs/ADC_MEASUREMENT_CONTRACTS.md`.

WP-10 acceptance uses a coherent 1,024-sample synthetic waveform with a known fundamental,
harmonic, and two noise tones, plus ideal three-bit transitions and fixed corner/Monte Carlo
vectors. Tests require expected metrics within `1e-9`, identical repeated output, explicit formulas
and units, rejection without a contract, and a stable input hash in the measurement manifest.
Actual-circuit measurement remains unavailable until the user supplies and approves a separate
complete contract.

## WP-11 blocked write and release checkpoint

The user approved `MCP_WorkLib`, an exact source/destination copy, and the sole
`mcpMutationTest=validated-v1` mutation. V1 remains preserved after its incomplete run. V2 passed
source verification, copy, 35/14/8 baseline, dry-run, unchanged verification, backup, and the
approved apply marker, then timed out before verification and rollback. Runner 0.12.0 supplies
fixed operator-only `design-write-v2-forensic` and confirmation-gated
`design-write-v2-rollback` commands plus the operator-only
`design-write-v2-property-diff` inspection; none accepts a path, design identifier, property,
value, or SKILL text. The property-diff command opens Source, V2 target, and V2 backup read-only
and reports only a differing property's name, type, presence, and value-equality flag. It never
reports a property value. Its fixed inspection found exactly two differences: the baseline
`schGeometryLastUpdated` property exists as `int` in target and backup but has unequal values, and
`mcpMutationTest` is absent from backup and present as `string` in target. Source, preserved V1,
V2 target, V2 backup, and `gpdk090` tree fingerprints each matched before and after; source,
target, and backup topology remained 35/14/8. The conditional rollback command was not invoked.
Read-only property-diff evidence exists, but no rollback evidence or rollback audit success record
exists.

`remote/config/design-write-v3-plan.json` remains the immutable approval asset. It uses only the
approved V3 destination and backup names, preserves all V1/V2 evidence, specifies a 300-second
worker limit and the full clean validation sequence. Its SHA-256 is
`3362e4fc13874d4f16c78506c24ae6ebd64c882718fe57e9cb2bb60619890c87`; all ten acceptance
criteria remain present. After the user separately approved implementation and execution, runner
0.12.0 added a SHA-bound, confirmation-gated, fixed V3 command. The first invocation stopped before
validation runtime creation or V3 copy because the preflight conservatively classified the
preserved V1 `sch.oa-` as blocking. Read-only follow-up proved that V1 `master.tag` authoritatively
selects its regular `sch.oa` and that no active lock, panic, or recovery file exists. The gate now
preserves and fingerprints that auxiliary file while continuing to reject actual blockers, but the
V3 sequence was not automatically retried.

The user subsequently approved one corrected-runner invocation. Validation
`0b9bf93c-11e9-416f-9e4a-69b1060fbd8e` passed copy, baseline, dry-run unchanged verification,
backup, and apply, then failed at exact-diff verification with `V3 apply changed a baseline
property`. The process exited normally with no remaining Virtuoso process, but rollback and audit
finalization were not reached. The V3 target and backup now exist and are preserved. Source, V1
including `sch.oa-`, both V2 views, and gpdk090 retained their exact pre-run tree fingerprints.
Do not retry, overwrite, delete, or reuse either V3 view. Further Cadence action requires a new
fixed read-only forensic and conditional recovery plan plus explicit approval. The release gate
remains disabled.

The approved fixed read-only follow-up used runner 0.13.0 and validation ID
`0b9bf93c-11e9-416f-9e4a-69b1060fbd8e`. It reported only property name, type, presence, and
equality metadata. Exactly two differences were found: `schGeometryLastUpdated` exists as `int` in
target and backup with unequal values; `mcpMutationTest` is absent from backup, present as `string`
in target, and equals the fixed approved value. Actual values were neither output nor stored. The
evidence SHA-256 is `8e1bbd824b1d4ea130c3f921e2745dddfffe9ef533a696e77e7a46884954abf6`.
Source, V1 including `sch.oa-`, both V2 views, both V3 views, and gpdk090 fingerprints matched
before and after. No rollback or other design write occurred.

The proposed conditional restore is documented but non-executable at
`remote/config/design-write-v3-conditional-recovery-plan.json`. Its SHA-256 is
`edb34edf04b8ef4616f2215381cedf10f7ccf3ca7dfdcc8836e01d6e9f3b2d1b`; it contains 14 stages
and 14 acceptance criteria and is not deployed. A future run must revalidate both hashes, all
protected fingerprints, the exact two-property diff, topology 35/14/8, and blocker absence before
an exact confirmation can permit the fixed V3 backup-to-target restore. No current approval permits
that overwrite.

An additional exact-value investigation was separately approved for only Source, V3 target, and
V3 backup. Runner 0.14.0 performed the argument-free `design-write-v3-deep-forensic` command once,
using OpenAccess read mode for all three objects. Their tree fingerprints were identical before
and after. All retain topology 35/14/8 and the same instance, net, and terminal summary hashes.
Source and backup contain the same eight cellview properties. The target differs from backup only
as follows:

- `mcpMutationTest`: target `string` value `validated-v1`; backup and Source absent;
- `schGeometryLastUpdated`: target `int` value `107169`; backup and Source `int` value `107168`.

The report is mode 600 at the fixed validation evidence path and has SHA-256
`6329eafc458098b744a40b70fc0a1a0d876af57c326d2d79e854e1ceaeb9b02f`. The original stage log
shows backup before apply and the investigation classified the state as `SAFE_ROLLBACK_CANDIDATE`.
The original completion manifest, audit record, and normal runner job record are missing. No
rollback was run. The exact non-executable plan is
`remote/config/design-write-v3-exact-conditional-rollback-plan.json`, SHA-256
`eb057da2a866b92be5e1474bc3d06aba05f6ae49b5001465dd65ed9921afc911`; it is not deployed and
requires separate explicit approval before the fixed target overwrite.

The separately approved exact rollback attempt used run ID
`38cfdbf3-ae92-470b-bf38-6789887a3ae9`. Plan and forensic hashes and all three tree fingerprints
passed before execution. The worker then failed before starting Virtuoso because
`.cadence_mcp/write-rollback-v3` did not exist, so its child runtime could not be created. No OA
operation, manifest, or audit append occurred. Post-failure fingerprints exactly matched the
preflight values. The repository worker and deploy layout have been corrected to create only that
bounded mode-700 evidence root. Do not deploy and retry the corrected worker without a new explicit
approval; V3 remains in its pre-rollback state.

The user then supplied that separate approval for corrected commit
`77c1dcac9c96ab909146128fb92de9f9e0813806`, bound to plan SHA-256
`eb057da2a866b92be5e1474bc3d06aba05f6ae49b5001465dd65ed9921afc911`. Runner 0.15.0 was
redeployed and exactly one fresh execution, `575356ae-1853-409f-a913-25c1ba9038a8`, rechecked every
precondition and completed as `V3_ROLLBACK_VERIFIED`. It restored the fixed V3 target from the
fixed V3 backup with exactly two expected property transitions: `mcpMutationTest` was removed and
`schGeometryLastUpdated` changed from `107169` to `107168`. Topology remained 35/14/8, all logical
structure hashes were unchanged, the final target property hash matched the backup, and Source and
backup tree fingerprints were unchanged. All 15 acceptance criteria passed.

The immutable manifest is
`.cadence_mcp/write-rollback-v3/575356ae-1853-409f-a913-25c1ba9038a8/rollback-manifest.json`
(mode 400, SHA-256 `77c92d1bd0bf7c68666c60cceb630ad66945ece402d4f36271a24eb6078aac34`). The audit file
`.cadence_mcp/audit/v3-rollback-events.jsonl` is mode 600 and contained exactly 14 records for this
run (verification-time SHA-256
`4786eab04bdc3ea9d1626b1123e62a25a00ee8efdcce919db4da653ab9c8e34f`). Preserve all V1/V2/V3
objects and evidence. Do not start V4, create a tag, or create a release without a separately
reviewed V4 plan and explicit approval; the failed V3 validation is not converted into a release
PASS by its successful recovery.

The next clean-validation proposal is checked in at
`remote/config/design-write-v4-plan.json`, SHA-256
`c5b2f418c5a76bfe54adc24c2ee947a33d904122b404bba323706dfbe3cbdd66`. It uses only the new fixed
V4 target and backup names, preserves every V1/V2/V3 cellview, and contains 18 fixed stages and 18
acceptance criteria. It distinguishes the proposed one-property semantic mutation from the bounded
Cadence-maintained `schGeometryLastUpdated` integer side effect discovered during V3. The asset is
planning-only: it has no confirmation token and is absent from the runner and deployment manifest.
Do not implement, deploy, create either V4 cellview, or perform any OA write until a separate
approval is explicitly bound to this raw plan SHA-256.

Packaging lifecycle is independently verifiable with:

```powershell
.\scripts\verify-package.ps1
```

The script builds, installs, checks, and uninstalls the current `0.1.0` package entirely in a
validated temporary directory. `v1.0.0` remains prohibited until a clean copy-only sequence,
dry-run/apply equivalence, backup restore, and design immutability checks pass.
