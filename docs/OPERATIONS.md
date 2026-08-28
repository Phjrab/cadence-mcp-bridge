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
submit-smoke <job-id>
status <job-id>
log-tail <job-id> <stdout|stderr> <lines>
result <job-id>
cancel <job-id>
```

Job IDs are lowercase RFC 4122 UUID strings. Profile, executable, and remote paths are fixed in
reviewed source; no command, script text, netlist text, or path is accepted from the caller.
Log tail is restricted to 200 lines and 65,536 bytes.

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
bounded operator-review message. Automated retention remains deferred to WP-07.

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
server exposes exactly six tools: health, smoke submission, job status, bounded log tail,
structured result, and owned-job cancellation. No profile, remote path, netlist, command, or
script text is accepted.

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
