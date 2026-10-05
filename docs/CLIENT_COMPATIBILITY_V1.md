# CLIENT-COMPAT-01: MCP clients, protocol and qualification

## Current STORAGE-MGMT-01 overlay

The current interface has 63 tools. The five path-free storage interfaces
preserve all preceding 58 full schemas, including registered sweep lifecycle.
Both exported client settings pass actual SDK stdio inventory/plan/dry-run and
preserved native/RC results/restart regression against the same server/guards.
All six registered result groups are observed; real-host deletion is NOT_RUN.
Use 63 tools for future manual qualification. The 48/51/53-tool overlays below
remain dated history. CLAUDE_REAL_CLIENT_UNVERIFIED and fresh Codex application
NOT_TESTED are unchanged. See [storage evidence](STORAGE_MGMT_01_RESULT_V1.md).

## Current GENERIC-SWEEP-01 preparation overlay

Current inventory is 53 tools: two local registered 1D description/planning
interfaces preserve all preceding 51 schemas. They add no execution/transport
or per-client configuration. Desktop evidence states remain unchanged.
Older 48/51-tool tables below remain dated evidence. Use 53 tools for a new
manual qualification; see [sweep preparation](GENERIC_DESIGN_SWEEP_V1.md).

## Current GENERIC-MEAS-01 overlay

Current inventory is 51 tools: three additive registered measurement readers
preserve all 48 starting-main schemas. Independent JSON-RPC/installed-client
gates remain, and actual SDK stdio with both exported settings verifies bounded
DC/AC/TRAN measurement/provenance/restart equality without new simulation.
Desktop application evidence states below are unchanged; no real desktop E2E
is claimed. The original 48-tool audit below remains dated phase evidence.
Use the current 51-tool inventory for future manual qualification. See
[measurement contracts](GENERIC_MEASUREMENTS_V1.md).

## Scope and evidence states

Cadence MCP Bridge is one local stdio MCP server. Codex and Claude Desktop
configuration only launches that server. Environment/design/PDK catalogs,
journals, allowlists, UUID admission, resource guards and protected fingerprints
are bridge configuration. Clients cannot override them through tool arguments.
No client whitelist, second server, arbitrary execution or remote listener exists.

Version: bridge 1.0.0, locked MCP Python SDK 2.1.1 (`>=2,<3`). The existing
isolated wheel installation resolved SDK 2.3.0 and passed the same adapter gate.
These observations do not qualify every version in the declared range. The
48 tools and 22 v1 declarations are retained. Current qualification uses
independent JSON-RPC and SDK subprocess clients, not desktop impersonation.

| Client/evidence scope | Registration | tools/list | tools/call | Real Cadence E2E through that application |
| --- | --- | --- | --- | --- |
| Codex launch adapter, SDK subprocess regression | CONFIG_PREPARED | PROTOCOL_VERIFIED | PROTOCOL_VERIFIED | NOT_TESTED in this phase; prior native stdio evidence is separate |
| Claude Desktop launch adapter, SDK subprocess regression | CONFIG_PREPARED | PROTOCOL_VERIFIED | PROTOCOL_VERIFIED | NOT_TESTED: CLAUDE_REAL_CLIENT_UNVERIFIED |
| Independent JSON-RPC test clients | PROTOCOL_VERIFIED | PROTOCOL_VERIFIED | PROTOCOL_VERIFIED | NOT_TESTED; local discovery only |
| Other MCP applications | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED |

`VERIFIED` requires direct evidence for the named application/action.
`CONFIG_PREPARED` is a reviewed export, not installed-client verification.
`PROTOCOL_VERIFIED` identifies subprocess protocol evidence. `BLOCKED` names an
actual precondition failure; `UNSUPPORTED` means no qualified implementation.
`SERVER_PROTOCOL_QUALIFIED`, `CLAUDE_CONFIG_PREPARED` and
`CLAUDE_REAL_CLIENT_UNVERIFIED` summarize this phase. Installed/config/process
checks did not establish Claude availability. Windows Appx enumeration was
unavailable in this shell; absence is not asserted for every installation format.
Native desktop automation and a Cadence MCP binding in this agent's tools are
unavailable, so neither application is newly qualified from this chat.

## Client reference audit

The audit covers tracked source, scripts, tests and public documents. The
private occurrence inventory records file/line/category without copying secrets.
The following rules account for all audited client references; old documents
and journals are retained rather than silently renamed.

| Occurrence/family | Classification | Disposition |
| --- | --- | --- |
| `onboarding.py` Codex TOML/approval settings; `__main__.py` client format selection | CLIENT_ADAPTER | Only serialization/launch configuration; shared execution path |
| `scripts/install-codex-mcp.ps1`, its `CODEX_HOME` and user config path | CLIENT_ADAPTER | Retained Codex registration; not imported by the server |
| Package verification of Codex exports | TEST_ONLY | Tests adapter launch and retained approval settings |
| Unit fixtures/assertions mentioning Codex or project `.codex` paths | TEST_ONLY | Regression/security evidence |
| README, current architecture/operations/onboarding/client guides | DOCUMENTATION_ONLY | Current product/client separation documented |
| Archived master/roadmap/release/WP history, project-local private campaign `.codex` evidence paths in operator scripts | HISTORICAL | Existing authority/accounting locations remain active where applicable; no dependency on Codex software or CODEX_HOME |
| `service.py` package-relative `.codex/sweeps-v1.sqlite3` storage assumption | CORE_DEPENDENCY (project layout), with HISTORICAL fallback | Removed as a requirement for explicitly configured installations via operator sweep setting; exact old default retained to preserve replay |

No core dependency on a Codex executable, Codex request context, CODEX_HOME,
Codex configuration parsing, hidden prompts, brand-specific result formatting
or lifecycle was found. One unnecessary project-layout requirement is now
configurable; the historical fallback remains visible and is not claimed removed.
No MCP tool name/schema is renamed. The whole tool-schema inventory is compared
to starting main, not just counted. Structured JSON text and structuredContent
remain equivalent on successful discovery; bridge failures carry stable codes.

## Operator registration

Follow [onboarding](ONBOARDING_CLI_V1.md) using approved local profiles. Use an
absolute Python executable from the installed bridge environment, not a shell
wrapper printing banners. Python 3.12/3.13 and package dependencies are required;
Node.js in the official filesystem-server tutorial is not required by this server.

```powershell
uv run cadence-mcp-bridge client-config --profile C:\private\environment.json --design-registry C:\private\designs.json --pdk-registry C:\private\pdks.json --journal C:\private\analyses-v1.sqlite3 --sweep-journal C:\private\sweeps-v1.sqlite3 --format claude-desktop --output C:\private\claude-fragment.json
```

`claude-desktop` and `mcp-json` produce identical JSON bytes for identical inputs.
`codex` retains TOML and write/prompt approval settings. Export creates a new
private fragment exclusively; it does not modify live client configuration,
create/reset journals or grant execution. Source/PDK paths remain operator local.
Launch uses the same `python -m cadence_mcp_bridge serve` for all clients.

Fictional shape only (replace with the reviewed exporter output):

```json
{
  "mcpServers": {
    "cadence-mcp-bridge": {
      "command": "C:\\approved-bridge\\.venv\\Scripts\\python.exe",
      "args": ["-m", "cadence_mcp_bridge", "serve"],
      "env": {
        "PYTHONUTF8": "1",
        "CADENCE_MCP_DESIGN_REGISTRY_PATH": "C:\\private\\designs.json",
        "CADENCE_MCP_PDK_REGISTRY_PATH": "C:\\private\\pdks.json",
        "CADENCE_MCP_ANALYSIS_JOURNAL_PATH": "C:\\private\\analyses-v1.sqlite3",
        "CADENCE_MCP_SWEEP_JOURNAL_PATH": "C:\\private\\sweeps-v1.sqlite3"
      }
    }
  }
}
```

Official MCP local-server documentation, read 2026-10-05, identifies Claude
Desktop Settings → Developer → Edit Config, Windows
`%APPDATA%\Claude\claude_desktop_config.json`, macOS
`~/Library/Application Support/Claude/claude_desktop_config.json`, the
`mcpServers`/`command`/`args` structure and a full quit/restart after editing.
Merge only the bridge entry into existing configuration; do not replace unrelated
servers. Use concrete absolute paths in JSON strings. Keep the client's own
approval controls enabled. An operator's phase delegation is not a reason to
disable client security prompts.

Both clients must reference the same approved registries and journals. Existing
users must supply the actual historical sweep ledger, not invent a fresh path
to bypass replay/accounting. If the sweep setting is omitted, the exact old
package-relative `.codex/sweeps-v1.sqlite3` path remains the compatibility default.
Installed-package users should configure it explicitly in writable operator
storage. Existing eager SweepStore initialization can create a local schema on
server startup; it does not reserve remote simulations. No ledger migration or
purge is performed by this phase. Keep one active EDA worker across clients;
the remote guards and durable admissions remain authoritative, not tool hints.

## Exact remaining real-client qualification

1. Install the same reviewed bridge build in an isolated local environment;
   run doctor and joined local verify. Generic execution remains unqualified
   until separately qualified contracts/bindings exist.
2. Export Codex TOML and Claude JSON from the same profiles and existing
   journals. Record config digests privately; install the reviewed bridge entry
   using each application's registration UI/config without unrelated edits.
3. Fully restart each application. Record app version, time, server version,
   registration status and observed tool inventory. Verify 53 names and schemas
   against this phase's inventory. App UI availability alone is not tools/list.
4. In each app request `cadence_list_designs`, then `cadence_describe_design`
   for a listed ID and `cadence_design_pdk_status` for that ID. Compare structured
   results for the same configuration; they must not grant execution. Ask for
   no shell, paths, scripts, simulation, source mutation or PDK content.
5. If a real Cadence read is needed and approved evidence is available, call
   status/result for an already completed native UUID only. Compare preserved
   results and fresh protected/accounting checks. Do not submit a new job just
   to establish client compatibility. Record blocked/unavailable facts precisely.
6. Verify protocol stderr/log separation and normal app-owned process shutdown.
   Preserve evidence privately. Upgrade matrix fields to VERIFIED only for
   directly observed named app operations; remaining fields stay NOT_TESTED.

## Protocol audit and regression

- SDK owns stdio framing, initialization/version negotiation, capabilities,
  tools/list/tools/call and method errors. Test clients advertise no special
  host capabilities and use unrelated clientInfo names.
  Independent wire tests exercise legacy 2025-11-25 initialization; the locked
  SDK native replay negotiated 2026-07-28. Both paths are observed separately.
- Every stdout line is parsed as JSON-RPC; no banner/progress/shell output.
  Application logging uses stderr. A deliberate registered-ID error exercises
  code-only warning logging and stable structured error envelopes.
- All 48 tools have names/descriptions and object input/output schemas; none
  includes Codex context. SDK schema validation and existing stricter registered
  input hooks reject extra paths. Method-not-found returns -32601; ping and calls
  continue afterward.
- Two simultaneous read requests correlate independently by ID and return equal
  bounded results. This does not claim arbitrary concurrent EDA execution.
  Original locks/reservations/UUID journals protect stateful operations.
- Stdin EOF exits normally. Historical Cadence jobs are remotely durable; a
  client exit is not interpreted as permission to reset or blindly resubmit them.
- Installed-wheel gates launch TOML, generic JSON and Claude JSON from another
  cwd and deny fictional admission. Closed inputs and legacy declarations are
  unchanged. Private reference E2E reads completed DC/AC/TRAN IDs, with restart
  lookup and fresh protected checks, without new simulations.

## MCPB: PACKAGING_INVESTIGATION

Official Anthropic article confirms `.mcpb` replaces `.dxt`, ZIP bundles,
`manifest.json`, server/config/runtime metadata, OS secret storage and managed
extension updates. Its old 0.1 examples are historical. The linked current
official manifest repository redirects to `modelcontextprotocol/mcpb`.
The inspected MANIFEST file at `a5d9ae8ed28786a6bb7cddb114553bdf8a808dd6`
has a 0.3 header and a newer 0.4+ `uv` section: required metadata includes
manifest_version/name/version/description/author/server; user_config can collect
file/directory/string fields, and platform overrides support win32.

For `python`, dependencies are bundled and a compatible Python runtime is
specified. The 0.4+ `uv` type declares pyproject dependencies and says the host
installs/runtime-manages them without user Python; it must not bundle lib/venv.
This requires qualification against an actual host version and controlled
dependency/update provenance. Current plain JSON installation still requires
external Python/dependencies (uv is an installation convenience). Windows
OpenSSH, known hosts and keys remain external in every proposal. Bundles must
exclude SSH keys/credentials, private profiles/hosts, journals, evidence, PDK,
Cadence binaries and licensed content. Updates must preserve existing ledgers
and reviewed contracts. Secret storage does not qualify arbitrary config values.

Decision: defer packaging until real Claude qualification and generic execution
onboarding improve. Packaging can simplify runtime installation, but cannot
qualify a Cadence environment or settle owner licensing. No bundle, directory
submission, release, port, tunnel or firewall change is implemented here.

## Official sources

- [MCP local servers / Claude Desktop registration](https://modelcontextprotocol.io/docs/2026-07-28/develop/connect-local-servers)
- [Anthropic desktop extensions article](https://www.anthropic.com/engineering/desktop-extensions)
- [Current official MCPB manifest](https://github.com/modelcontextprotocol/mcpb/blob/a5d9ae8ed28786a6bb7cddb114553bdf8a808dd6/MANIFEST.md)
- [Codex local MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
