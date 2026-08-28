# Architecture

## Scope at WP-03

WP-03 adds the Windows OpenSSH adapter for the restricted runner deployed in WP-02. It does
not expose an MCP server, register Codex, or accept arbitrary remote commands. Those
capabilities remain reserved for later work packages.

## Layer boundaries

```text
Future MCP stdio adapter
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
- `service.py` separates application behavior from the SSH and future MCP adapters.
- `ssh_backend.py` maps typed operations to the fixed runner and stable transport errors.
- `__main__.py` exposes only local help/version/configuration validation at this stage.

## Trust boundaries

Model-provided values must never become arbitrary paths, shell fragments, SKILL, or OCEAN.
The future MCP adapter may invoke only typed service methods. The Windows SSH backend invokes
the fixed runner at `/home/buet/cds_work/.cadence_mcp/bin/cadence-runner` through the fixed
alias `cadence-vm`, with allowlisted subcommands and validated single-token arguments. It uses
an argv list, `shell=False`, `BatchMode=yes`, and strict host-key checking. There is no public
raw-command method.

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
