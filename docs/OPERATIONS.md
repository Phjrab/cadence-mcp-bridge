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
fail closed. More complete stale-process recovery and retention are deferred to WP-05/WP-07.

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
