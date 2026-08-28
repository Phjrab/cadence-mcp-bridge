# Architecture

## Scope at WP-05

WP-06 adds idempotent Codex Desktop registration and the operator workflow over the verified WP-05
lifecycle. The user-level MCP entry uses absolute Windows paths, starts only the reviewed Python
module, and prompts for both state-changing tools. No new remote or Cadence capability is added.

## Layer boundaries

```text
MCPServer v2 stdio adapter (six allowlisted tools)
          |
          v
CadenceService (transport-independent orchestration)
          |
          v
CadenceBackend protocol
          |
          v
OpenSshBackend -> Windows ssh.exe -> fixed cadence-runner
```

- `config.py` owns operator configuration and enforces fixed SSH and remote-root boundaries.
- `models.py` defines immutable health, job, artifact, and error contracts.
- `errors.py` maps failures to stable, sanitized envelopes.
- `sanitization.py` removes credential, license, and Windows-profile details and bounds output.
- `service.py` separates application behavior from the SSH and MCP adapters.
- `ssh_backend.py` maps typed operations to the fixed runner and stable transport errors.
- `server.py` defines tool schemas, annotations, stable error results, and the stdio runtime.
- `e2e.py` verifies health, submission latency, bounded polling, logs, result, artifacts, and
  remote job storage through the public MCP tools.
- `__main__.py` starts stdio by default and keeps explicit help/version/configuration checks.

## Trust boundaries

Model-provided values must never become arbitrary paths, shell fragments, SKILL, or OCEAN.
The MCP adapter invokes only typed service methods. The Windows SSH backend invokes
the fixed runner at `/home/buet/cds_work/.cadence_mcp/bin/cadence-runner` through the fixed
alias `cadence-vm`, with allowlisted subcommands and validated single-token arguments. It uses
an argv list, `shell=False`, `BatchMode=yes`, and strict host-key checking. There is no public
raw-command method.

The service creates UUID job identifiers. Cancellation is limited to jobs submitted by the
same running MCP service instance. Health, status, log-tail, and result tools are annotated
read-only; submit is non-destructive but state-changing; cancel alone is annotated destructive.
Every tool is closed-world. Expected failures become stable structured error envelopes with
`isError=true`, while exception details remain on stderr.

The generated submit UUID is also the idempotency key. If SSH times out after remote creation,
the service queries status for that same UUID exactly once; it adopts the job only when the
runner returns the matching identifier. It never retries submission with a second UUID.

Polling defaults to one second with a five-minute maximum. Spectre concurrency remains fixed at
one by the remote `flock`. For queued, running, or cancelling jobs, status verifies the stored
PID, process group, start marker, and non-zombie process state. A completed result repairs stale
status; otherwise a missing or mismatched worker becomes the terminal `unknown` state for
operator review.

The Windows process may write local runtime metadata only in bounded application locations.
Before WP-11, remote writes are limited to `/home/buet/cds_work/.cadence_mcp`; design data,
PDKs, shared libraries, and CentOS system files remain read-only.

## Data contracts

- Timestamps require explicit time zones.
- Job IDs use UUID values.
- Job states are a closed enumeration.
- Artifact paths are relative metadata, never unrestricted filesystem inputs.
- License state is represented only as `SET` or `UNSET`.
- Unexpected backend exceptions become a stable `backend_unavailable` error without exposing
  raw exception text.
- Output and error strings are redacted and length-bounded before crossing trust boundaries.

## Dependency and verification policy

The project targets Python `>=3.12,<3.14` and locks dependencies with `uv`. Ruff, mypy, and
pytest are mandatory acceptance checks. Unit tests mock subprocess and perform no SSH,
Cadence, network, or remote filesystem operations. The separately marked integration test
contacts `cadence-vm` only when `CADENCE_MCP_RUN_INTEGRATION=1` is explicitly set.
