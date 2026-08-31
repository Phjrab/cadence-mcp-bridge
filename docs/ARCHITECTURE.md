# Architecture

## Scope at WP-13 checkpoint

WP-10 retains the versioned simulation profile registry and adds a separate local, versioned ADC
measurement-contract registry. Only the non-proprietary `adc-synthetic-v1` contract exists; the
actual ADE L profile is not treated as an ADC and no actual-circuit measurement is inferred.
The controlled-write boundary fixes one approved source, a dedicated work library, one semantic
property mutation, and generation-specific targets/backups. Historical V1/V2/V3 evidence remains
preserved. Runner 0.16.0 completed the separately approved V4 clean validation against new fixed
names, explicitly bounded the Cadence-maintained `schGeometryLastUpdated` side effect, restored the
V4 target from its backup, and proved Source/PDK/prior-evidence immutability. The published v1.0.0
surface remains immutable. Runner 0.18.0 adds a separate fixed read-only ADE L introspection path
for the one reviewed actual profile; parameterized execution remains disabled.

## Layer boundaries

```text
MCPServer v2 stdio adapter (twenty-three allowlisted tools)
          |
          v
CadenceService (transport-independent orchestration)
       /     \
      v       v
local versioned ADC   CadenceBackend protocol
measurement engine            |
                              v
                 OpenSshBackend -> Windows ssh.exe -> fixed cadence-runner
```

- `config.py` owns operator configuration and enforces fixed SSH and remote-root boundaries.
- `models.py` defines immutable health, job, artifact, discovery, ADE-introspection, and error
  contracts.
- `discovery.py` enforces the reviewed library/cell/view allowlist before SSH.
- `profiles.py` owns the reviewed local profile contract and rejects unknown profiles/corners.
- `measurement_models.py` defines bounded measurement inputs, structured metrics, and manifests.
- `measurements.py` owns the deterministic synthetic ADC calculations and closed contract registry.
- `write_policy.py` permanently classifies PDK/shared/source libraries as non-writable and makes
  only the fixed `MCP_WorkLib` contract eligible; the remote target-existence check remains the
  final fail-closed gate.
- `write_models.py` defines the immutable plan and validation-result contracts.
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
read-only, as are discovery, profile inspection, and all eight measurement tools; submit is
non-destructive but state-changing; cancel
alone is annotated destructive. Every tool is closed-world. Expected failures become stable
structured error envelopes with `isError=true`, while exception details remain on stderr.

Discovery uses a fixed JSON allowlist deployed under `.cadence_mcp/config`. The remote helper
re-checks `cds.lib`, exact real paths, directory type, and symlink containment before returning
only names, allowed counts, and existence. It never opens a cellview file and never returns a
remote path, PDK entry, netlist, model, or cellview content.

ADE introspection is a separate closed path. The caller supplies only the literal
`actual-differential-amplifier-tb2-transient` profile ID. Runner 0.18.0 invokes one fixed Python
2.6 metadata parser and one fixed SKILL template. SKILL opens only
`MyDesignLib/Differential_Amplifier_TB2/schematic` with OA mode `r`, returns counts, closes the
cellview, and never saves. The helper reads only the fixed state files, source snapshot, source
tree, and gpdk090 model file. It returns safe design-variable names/numeric values, analysis enable
state, output names, hashes, timestamps, lock counts, and topology `35/14/8`; paths and raw content
remain internal. Source, state, PDK model, and source-netlist fingerprints must match before and
after or the command fails. Contract differences return `profile_drift` and cannot modify either
the profile registry or Cadence data.

Profile submission accepts one closed profile identifier, one allowed corner, and a profile-specific
typed variable object. The fixture accepts three bounded numeric variables. The actual profile
accepts only an empty object and fixes ADE L `state1`, gpdk090 v4.6 section `NN`, 27 degrees C,
transient stop `4m` (0.004 seconds), no adjustable design variables, and no requested measurements.
The Windows service validates the selected contract; the remote runner repeats registry and source
checks before creating a job. For the actual profile, the helper copies only the fixed existing
ADE-generated circuit netlist into the mode-700 job directory and builds a reviewed Spectre wrapper.
It never opens or saves the OA cellview or ADE state. The manifest records the source hash and exact
fixed configuration. MCP returns artifact metadata, not manifest, netlist, or waveform content.

Profile completion is strict by default. The actual profile alone permits at most two occurrences
of the observed non-fatal gpdk090 `CMI-2477` warning; any other warning, additional occurrence,
nonzero exit, or Spectre error fails the job.

ADC measurements do not invoke SSH or Cadence. The caller must select the exact
`adc-synthetic-v1` contract and provide finite bounded samples. Each result records units,
formulas, contract version, the fixed Windows-Python post-processor, and a canonical input SHA-256.
Unknown or omitted contracts fail before calculation. The FFT policy and all other definitions are
documented in `docs/ADC_MEASUREMENT_CONTRACTS.md`; no synthetic setting is promoted to an actual
circuit default.

The generated submit UUID is also the idempotency key. If SSH times out after remote creation,
the service queries status for that same UUID exactly once; it adopts the job only when the
runner returns the matching identifier. It never retries submission with a second UUID.

Polling defaults to one second with a five-minute maximum. Spectre concurrency remains fixed at
one by the remote `flock`. For queued, running, or cancelling jobs, status verifies the stored
PID, process group, start marker, and non-zombie process state. A completed result repairs stale
status; otherwise a missing or mismatched worker becomes the terminal `unknown` state for
operator review.

Each request records a closed `mcp|operator` origin. The MCP backend supplies only the literal
`mcp`; direct reviewed operator use may supply only `operator`. Submission and cancellation append
fixed-field JSONL audit records under the approved remote root. Audit records cannot contain
commands, paths, environment values, logs, circuit data, or artifacts.

Retention is a 30-day policy with a dry-run-only planner. It scans only canonical UUID directories
whose real parent is the fixed jobs root, skips symlinks, and exposes no deletion switch. Log and
result responses carry explicit bounds and truncation metadata, and known secrets are redacted
before crossing the MCP boundary.

The Windows process may write local runtime metadata only in bounded application locations.
Remote application writes remain limited to `/home/buet/cds_work/.cadence_mcp`. The user separately
approved `/home/buet/cds_work/MCP_WorkLib`, preservation of all V1/V2/V3 evidence, and one
plan-bound V4 clean validation. Only the new V4 target and its backup were writable during that
sequence; rollback left the target logically equal to the backup baseline. PDKs, source/shared
libraries, historical evidence, and CentOS system files remain read-only.

## Data contracts

- Timestamps require explicit time zones.
- Job IDs use UUID values.
- Job states are a closed enumeration.
- Artifact paths are relative metadata, never unrestricted filesystem inputs.
- License state is represented only as `SET` or `UNSET`.
- Discovery identifiers must match both the closed schema and the reviewed library/cell/view
  allowlist; discovery responses explicitly report that proprietary content is absent.
- Unexpected backend exceptions become a stable `backend_unavailable` error without exposing
  raw exception text.
- Output and error strings are redacted and length-bounded before crossing trust boundaries.

## Dependency and verification policy

The project targets Python `>=3.12,<3.14` and locks dependencies with `uv`. Ruff, mypy, pytest,
the secret preflight, and strict locked-dependency `pip-audit` are mandatory acceptance checks.
Unit tests mock subprocess and perform no SSH,
Cadence, network, or remote filesystem operations. The separately marked integration test
contacts `cadence-vm` only when `CADENCE_MCP_RUN_INTEGRATION=1` is explicitly set.
