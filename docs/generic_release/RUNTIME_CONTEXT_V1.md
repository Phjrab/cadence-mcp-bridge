# GREL-01 operator runtime contexts

GREL-01 connects the existing environment, design registry v1–v8 and PDK v2
contracts to a frozen server context. It does not qualify a generic Cadence
runner or authorize an experiment. New operator launches cannot use historical
reference execution or fall back to the developer VM.

## Local workflow and migration

A bare **cadence-mcp-bridge** launch and **serve-operator** use the operator path.
Without settings they expose local MCP schemas/discovery and deny remote calls
with SETUP_REQUIRED, without constructing SSH or creating journals.

The existing explicit **serve** command and legacy_reference configuration keep
the historical compatibility behavior. Existing client fragments use that
explicit command; they remain intact. This is a migration boundary, not an
automatic upgrade of a legacy circuit or its authorization.

Generate the installed schema without a repository checkout:

~~~powershell
cadence-mcp-bridge runtime schema
cadence-mcp-bridge runtime verify
cadence-mcp-bridge verify --profile environment.json --design-registry designs.json --pdk-registry pdks.json
~~~

The existing joined verification reports raw-file digests for the operator's own
contracts. Use those current digests in the runtime settings. They are input
integrity references, not user consent or installed runner attestations.

Runtime settings schema v1 contains an absolute resource_state_root and one
to sixteen context bindings. Each binding has the following fields:

| Field | Meaning |
| --- | --- |
| context_id | Unique logical context selected explicitly at startup |
| environment_profile, environment_sha256 | Existing environment JSON and its raw-byte SHA-256 |
| design_registry, design_sha256 | Existing bounded registry and its raw-byte SHA-256 |
| pdk_registry, pdk_sha256 | Existing PDK metadata and its raw-byte SHA-256 |
| runner_sha256 | Expected digest only; not attested or executable in GREL-01 |
| authority_ref | Logical reference only; this CLI does not create approval |
| ledger_ref | Existing resource accounting reference; no ledger is created/reset |
| analysis_journal, sweep_journal | Distinct absolute operator journal selections |

All fields are closed and bounded. JSON duplicates, stale hashes, unregistered
designs, conflicting aliases/environment IDs, ambiguous cross-context design
IDs, shared-domain policy conflicts, unsafe profiles, symlink/junction path
components and journal/input collisions deny startup. Journal parents and the
resource state root must already exist. Verification does not create them.

Resolve a registered logical design locally:

~~~powershell
cadence-mcp-bridge runtime verify --settings C:/operator/runtime.json --context lab-a
cadence-mcp-bridge runtime resolve --settings C:/operator/runtime.json --context lab-a --design-id rc-a
~~~

Supply the operator context to an MCP process:

~~~powershell
$env:CADENCE_MCP_RUNTIME_MODE = "operator"
$env:CADENCE_MCP_RUNTIME_SETTINGS_PATH = "C:/operator/runtime.json"
$env:CADENCE_MCP_RUNTIME_CONTEXT_ID = "lab-a"
cadence-mcp-bridge serve-operator
~~~

Do not combine it with inherited legacy design/PDK/journal/target overrides or
transport-root overrides. A default-context guess is forbidden, even when a
file has only one context. Choose the reviewed context before restarting the
server. Active server objects keep their existing immutable contract snapshot.

The existing client-config exporter supports --runtime-settings and --context
together with its existing profile/design/PDK/journal arguments.
It verifies that those inputs and both journal selections equal the selected
context before exclusively writing a private fragment. It emits serve-operator,
never writes a global app setting, and creates no journal.
Without those new flags it emits the explicit legacy compatibility fragment.

## Execution and privacy boundaries

The selected environment supplies the SSH alias and managed root; the runner
path is the fixed bin/cadence-runner child. MCP callers cannot supply a host,
path, executable, script, code, corner binding or registration document.
OperatorTransport is separate from the legacy BridgeConfig alias allowlist.
The actual backend constructor receives that frozen transport. Its central
invocation guard rejects every operator request until a later reviewed runner
implementation exists. No generic command or profile route is enabled.

Operator MCP discovery reuses registry/PDK/variable implementations. Every other
unqualified operation, including reference result readers, simulation, Sweep,
storage and writes, returns RUNNER_SETUP_REQUIRED. It never opens either
journal or delegates to a reference backend. The old 85 wire schemas and all
historical engines remain unchanged. Registration, description validity,
environment preflight, analysis qualification, execution authority and result
validation are reported as separate facts.

Runtime verify/resolve reports logical IDs, hashes, requested capabilities,
separate states and a package source fingerprint. It excludes paths, SSH alias,
library/cell/ADE bindings, credentials, license values and PDK data.
The fingerprint covers installed .py files on disk; it is not a commit SHA,
loaded-memory measurement or external installation attestation. Those fields
stay null/false. Existing MCP runtime v1/v2 schemas retain their exact shape;
the selected operator server reports its loaded catalogs. A setup server denies
runtime v1/v2 rather than claiming that nonexistent journals were supplied.

## Resource-domain foundation

Contexts describing the same hostname/architecture derive the same declared
domain regardless of alias, context name, username or managed-root changes.
Within a runtime settings file they must use the same ledger reference and
limits. Context journals cannot overlap. The nonblocking OS lock at the shared
resource root/domain digest is tested across aliases and separate processes.
Regular-file identity and hardlink checks protect lock leaves.

This is a declared local identity model, not proof of physical host identity.
All processes for the same resource must use the same reviewed state root.
Independent state roots, host-name impersonation and cross-user state ownership
require the attested domain/ledger provisioning in GREL-02/03 before execution.
The operator route is disabled throughout this phase, so declarations cannot
multiply simulator capacity. No environment limit or new context grants budget.
Existing remote shared EDA locks, historical counters and reservations are
untouched. Unresolved remote identity never becomes execution authority.

## Setting classification

| Category | Examples |
| --- | --- |
| Fixed legacy regression | cadence-vm BridgeConfig, existing compiled reference profiles/readers |
| Operator-owned configuration | Environment/design/PDK files, context ID, journal paths, resource root |
| Generated identity | Contract/context/domain/package fingerprints |
| Secret, excluded | Authentication, license endpoints, private raw results and proprietary models |
| Authority, independently verified later | Runner attestation, approval reference, existing ledger reference |

GREL-02 must supply installable fixed runner assets, trust/permission checks and
bootstrap. GREL-03 must supply reusable authority and resource lifecycle.
New same-VM circuits and actual DC/AC/TRAN/Sweep remain later gates. Other
Cadence versions, PDKs, physical PCs and full Claude qualification stay deferred.
No release/tag/PyPI/MCPB publication is authorized by this phase.
