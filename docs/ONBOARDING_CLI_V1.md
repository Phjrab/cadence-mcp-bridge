# Operator onboarding CLI v1

CLIENT-COMPAT-01 adds `--format claude-desktop` as an alias of the same MCP JSON
export and optional `--sweep-journal` / `CADENCE_MCP_SWEEP_JOURNAL_PATH` for
operator-owned local storage. Existing journals are never moved/reset by export.
See [client configuration, qualification matrix and remaining manual steps](CLIENT_COMPATIBILITY_V1.md).

ONBOARD-CLI-01 joins the existing environment v1, design v1/v2/v3 and PDK v2
contracts. All commands below are local operator commands, never MCP inputs.
Registration and local consistency do not qualify a new execution route.

## 1. Install and inspect

The open-source bridge requires Python, separately installed package dependencies
and local MCP configuration. Cadence Virtuoso/Spectre/ADE, their required licenses,
PDK access and authorized SSH/environment access are user-provided prerequisites.
They are not included by cloning or installing the bridge, and retain their own
terms. Use the full reviewed repository for operator deployment helpers; the
curated sdist is package source for rebuilding the wheel. See
[licensing boundaries](../THIRD_PARTY_NOTICES.md).

On Windows with Python 3.12 or 3.13, uv and Windows OpenSSH:

```powershell
git clone https://github.com/Phjrab/cadence-mcp-bridge.git
cd cadence-mcp-bridge
uv sync --all-groups --frozen
uv run cadence-mcp-bridge --version
uv run cadence-mcp-bridge doctor
```

`doctor` reports local Python/OS, SSH availability and validation of explicitly
configured design/PDK catalogs without remote contact. The current stdio server
still uses the fixed reference transport; descriptive environment SSH aliases
do not replace `BridgeConfig.ssh_alias`. A second installation is unqualified.

## 2. Describe and register private contracts

Use an operator-owned private directory with appropriate OS permissions. Do
not place license endpoints, model content, private netlists or PSF in a catalog.
The coherent [fictional example set](examples/onboarding/environment.json)
contains `environment.json`, `designs.json` and `pdks.json`. It demonstrates
valid references only: placeholder tool hashes, unqualified analysis adapters
and unqualified numeric ranges cannot establish physical safety or execution.
Earlier standalone examples remain historical and are not a joined catalog.

Inspect schemas and the linked [environment](GENERIC_ENVIRONMENT_V1.md),
[design](GENERIC_DESIGN_V1.md), [variable](GENERIC_VARIABLES_V1.md),
[analysis](GENERIC_ANALYSIS_V1.md) and [PDK](PDK_ADAPTER_RUNTIME_V2.md) guides.
Update private profiles using approved facts. Design/variable/analysis hashes
must be recomputed with the existing canonical-digest rules after edits;
separate numeric reviews are required to qualify ranges. Do not fill ranges
from a PDK name or candidate voltage.

```powershell
uv run cadence-mcp-bridge environment validate --profile C:\private\environment.json
uv run cadence-mcp-bridge design validate --registry C:\private\proposed-designs.json
uv run cadence-mcp-bridge pdk validate --registry C:\private\proposed-pdks.json
uv run cadence-mcp-bridge design register --registry C:\private\proposed-designs.json --output C:\private\registered-designs.json
uv run cadence-mcp-bridge pdk register --registry C:\private\proposed-pdks.json --output C:\private\registered-pdks.json
```

Registration creates new local files exclusively. It cannot overwrite approved
evidence or activate source mutation, simulations or a resource ledger.

## 3. Verify the combined contracts

```powershell
uv run cadence-mcp-bridge verify --profile C:\private\environment.json --design-registry C:\private\registered-designs.json --pdk-registry C:\private\registered-pdks.json
```

This workflow verifies one environment at a time. Every design in the supplied
catalog must reference that environment, an existing PDK adapter permitting
that environment, a subset of its process-corner IDs and analyses declared in
the environment's requested capabilities. Existing loaders enforce byte/count
bounds, schemas, private bindings and numeric/analysis hash relationships.
Empty design catalogs, symlinks/junctions and inconsistent references fail
closed. Catalogs for multiple environments must be split for this workflow.

Success is `consistent_local_contracts`, `remote_contact=false`,
`generic_execution_qualified=false`, `execution_authorized=false`, and
`spec_evaluation=not_evaluated`. Output includes logical IDs/counts and byte
hashes; it excludes paths, SSH alias, source/ADE bindings and license values.
Byte hashes identify the inspected snapshot; they are not deployment authority.
Files remain operator-owned: rerun verification after editing or relocating them.

### Optional remote preflight

After approved deployment of the exact bundle from `environment prepare`, add
`--remote-preflight` to `verify`. This explicitly invokes the existing bounded
read-only probe after local contracts pass. Its reopened environment profile
must match the inspected byte hash before SSH. Strict host keys, fixed command,
output bound and 45-second transport deadline remain enforced; there is no
deployment, arbitrary command or automatic retry in this workflow.

Preflight qualifies only identity/runtime/binary/roots/disk observations.
License entitlement, analysis capability and generic execution remain unqualified.
The current reference's mode-0777 wrappers are still rejected; do not change
protected installation permissions to make qualification pass.

## 4. Export a reviewable client configuration

```powershell
uv run cadence-mcp-bridge client-config --profile C:\private\environment.json --design-registry C:\private\registered-designs.json --pdk-registry C:\private\registered-pdks.json --journal C:\private\admissions.sqlite3 --format codex --output C:\private\new-codex-fragment.toml
# Alternative for clients accepting the common stdio mcpServers format:
uv run cadence-mcp-bridge client-config --profile C:\private\environment.json --design-registry C:\private\registered-designs.json --pdk-registry C:\private\registered-pdks.json --journal C:\private\admissions.sqlite3 --format mcp-json --output C:\private\new-mcp-fragment.json
```

Both exports first verify the combined contracts, exclusively create a private
output, and persist absolute design/PDK/journal settings. Neither creates the
journal, contacts a host nor modifies live client configuration. The interpreter
is the current installed Python; the entry point is `-m cadence_mcp_bridge serve`.
All BridgeConfig defaults are explicit, including fixed reference routing and
limits, preventing inherited terminal Cadence overrides. The environment profile
is used for verification, not as a server execution selector.

Keep exports private: they contain local paths. POSIX mode 0600 is requested;
on Windows use a private directory's ACL. The CLI does not change ACLs. Existing
journals may be referenced for durable resume but must never be reset or replaced.
Resolved journal/output paths must differ from contract paths and each other; parent directories
must already exist and symlink/junction paths are rejected. Review exports before
installation, and regenerate after interpreter relocation or contract changes.

### Codex

Back up the operator's `~/.codex/config.toml`. Merge the reviewed
`[mcp_servers.cadence-mcp-bridge]` tables into it, replacing only an existing
registration with the same name. Do not overwrite unrelated settings. Trusted
project configuration is also available; follow current official guidance.
Run `codex mcp list`, restart/reconnect the client and inspect the tools.

The export preserves `default_tools_approval_mode="writes"` and explicit prompt
overrides for submissions/cancellation/design-write tools, including registered
analysis submission. It does not disable platform approvals. The legacy
`scripts/install-codex-mcp.ps1` remains the reference installer; it does not
persist operator catalogs, so use the reviewed fragment for this workflow.
Official configuration fields were checked on 2026-10-05 against
[Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

### Other compatible MCP clients

Merge the generated `mcpServers` entry using the client's current documented
configuration workflow. JSON stdio format support and client-side approval
controls vary. This phase verifies bridge subprocess behavior, not installation
inside Claude/ChatGPT or those clients' permission controls. Server-side closed
contracts and resource/integrity/replay guards apply independently.

## 5. Inspect through MCP

Start with `cadence_list_designs`, `cadence_describe_design`,
`cadence_list_design_variables`, `cadence_list_pdk_adapters`,
`cadence_design_pdk_status`, `cadence_list_analyses` and `cadence_plan_analysis`.
There remain 48 MCP tools, with no model-facing registration/path/script fields.
Unqualified designs and PDKs cannot dispatch. Only the exact existing reference
analysis adapter can reuse guarded native DC/AC/trap TRAN. A measurement without
a scientific target is not a specification PASS.

## Remaining public-use limits

This is a complete local description/registration/verification/export workflow.
New physical execution adapters, a positively qualified second installation,
reviewed real-design variable ranges, generic measurements and release/legal
readiness remain separate work. RELEASE-LICENSE-01 applies Apache-2.0 to original
bridge source; imported planning rights remain under review and external software
retains its own terms. Package/release version remains 1.0.0; public visibility
alone does not grant rights. This phase adds no generic remote execution, optimization, layout,
DRC/LVS/PEX, Monte Carlo or multidimensional sweep.
