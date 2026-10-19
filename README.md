## Published2.1.0 and separate candidate development, 2026-10-18

**[2.1.0 is published](https://github.com/Phjrab/cadence-mcp-bridge/releases/tag/v2.1.0)**
at `36f75834b8556c9dd88761120a4442a25379d7ae`. Its approved nine attachments were
downloaded and checked against the frozen SHA256SUMS. See its
[release notes](docs/releases/2.1.0/RELEASE_NOTES.md) and
[qualification limits](docs/releases/2.1.0/QUALIFICATION.md); those files preserve
their prepublication assessment. No fresh2.1.0 native activation or app upgrade
is implied by publication.

This separate checkout is **unreleased2.2.0.dev0**. Its explicit experimental
operator candidate workflow plans complete registered V/A vectors, coordinates
one child per advance and compares retained scalar reports/CSV. Source/installed
software checks are separate from actual circuit qualification. No new native
candidate experiment or W/L support is established. See
[candidate workflow and remaining evidence](docs/EXPLICIT_CANDIDATES_01.md).
This development work does not modify the published2.1.0 artifacts.

Draft PR164 now connects a separate finite operator source-binding observation
path: exact installed bootstrap, existing account claim/resource lock, owned copy,
one fixed OCEAN process and retained terminal/frame evidence. It remains opt-in
and requires separately approved finite authority and reviewed standard-VM
runtime/init trust evidence. Declared member hashes do not prove dynamic closure;
an already provisioned persistent8MiB/256-inode filesystem is also required to
enforce stage capacity, including open-unlinked files. Current-VM setup is pending;
software/synthetic tests do not establish actual Cadence observation or a fresh
three-candidate experiment. See the
[operation and evidence boundary](docs/BINDING_OBSERVER_OPERATION_V1.md).

# Cadence MCP Bridge

Register your own circuits and run bounded DC/AC/TRAN analyses and 1D Sweeps in
the professor-provided CentOS/Cadence/PDK VM running in your personal VMware.
Operator settings select a common execution template; another supported circuit
requires no bridge-core patch or circuit-specific Python extractor.

**[Earlier2.0.0 qualification](https://github.com/Phjrab/cadence-mcp-bridge/releases/tag/v2.0.0).**
Two distinct new inverter/comparator test circuits completed DC/AC/TRAN,
automatic extraction and a bounded AC Sweep on the standard VM. Exact installed
2.0.0 also submitted a new job through the actual Codex app. Result retrieval,
same-ID retry and actual app restart preserved its result without duplicate
execution or reservation. The release includes the exact candidate's installation,
artifact and acceptance reports. Earlier source checkpoints remain in the
[acceptance record](docs/generic_release/GENERIC_ACCEPTANCE_CURRENT.json).

## Supported environment

Development-only physical metadata inspection is an explicit operator API with a
separate bounded staging/query approval. It launches no EDA or license utilities
and cannot qualify layout/DRC/LVS/PEX from file presence. See the
[fixed collector runbook](docs/M2_PHYSICAL_READINESS_01.md). It is not included in
the already published2.0.0 artifacts. The earlier pre-claim replay defect is fixed.
Source checks do not authorize another VM operation or qualify a physical backend.
Use only the explicitly authorized finite operator workflow in
[metadata recovery](docs/PHYSICAL_METADATA_RECOVERY_OPERATOR_V1.md); source/grant
changes never restore spent collections.

Actual host evidence is Windows/Python3.12.10. The reference VM observation is
CentOS6.5/i686/Python2.6.6, Virtuoso IC6.1.5.500.15 and Spectre12.1.0.347.isr3.
Ordinary OCEAN execution is observed; a separate OCEAN version is not established.
Preflight checks your actual installation rather than assuming these values.
Each operator supplies their own verified SSH alias/host key, ordinary guest
account, workspace, library/cell/view/ADE state, registries, journals, result paths
and approved resource limits. Other physical PCs, host OS combinations, Cadence
versions and PDKs are deferred. Package support accepts Python3.12–3.13; actual3.13
qualification is not claimed. No VM, Cadence executable, PDK, license or proprietary
circuit is bundled. Your existing software entitlement remains required.

## Install from release files

Use the wheel, locked runtime file and SHA256SUMS from the same published release.
Compare every file's hash before installation. The following commands install
the stable2.1.0 release; the development checkout is a separate unreleased build.

```powershell
Get-FileHash -Algorithm SHA256 .\cadence_mcp_bridge-2.1.0-py3-none-any.whl
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r locked-runtime-2.1.0.txt
.\.venv\Scripts\python.exe -m pip install --no-deps .\cadence_mcp_bridge-2.1.0-py3-none-any.whl
.\.venv\Scripts\python.exe -m cadence_mcp_bridge --version
.\.venv\Scripts\python.exe -m cadence_mcp_bridge doctor
.\.venv\Scripts\python.exe -m cadence_mcp_bridge operator-starter --output .\my-operator-setup
```

The exclusive starter export includes the complete setup guide and fictional
environment/design/PDK templates. It needs no developer checkout, private journal
or past job. Keep setup and journals outside the package. Import, doctor and MCP
startup do not initialize accounting, repair permissions or run EDA.

## 2.1.0 candidate: guided local setup

`operator-setup` reduces manual context and client configuration. This command
is included in the2.1.0 candidate and absent from the published2.0.0 wheel.
Start with `operator-setup guide --mode fresh` for a genuinely new installation,
or `--mode existing` when preserving an existing resource domain. The guide is
local and does not inspect or initialize the VM.

Use `check` for your environment/design/PDK contracts, `export-runtime` to write
one new settings file, then `check --settings RUNTIME --context ID`. After the
existing explicit VM setup, registration and authority steps, `export-client`
derives its paths from that selected context. Exports never overwrite an existing
file or create journals. See the [step-by-step guide](docs/POST_01_OPERATOR_SETUP.md)
for required inputs, retained-state handling and error recovery.

## Experimental operator design and physical metadata

The candidate's `operator-design` CLI stores immutable local revisions and
validates a bounded CMOS inverter plan. Its public CLI is local-only and has no
remote execution backend. It is absent from published2.0.0. Start in a new
operator-owned directory:

```powershell
python -m cadence_mcp_bridge operator-design example --output inverter-example
python -m cadence_mcp_bridge operator-design init --store revisions.sqlite3
python -m cadence_mcp_bridge operator-design validate --plan inverter-example/plan.json --registry inverter-example/registry.json --binding inverter-example/binding.json
python -m cadence_mcp_bridge operator-design record --store revisions.sqlite3 --plan inverter-example/plan.json --registry inverter-example/registry.json --binding inverter-example/binding.json
python -m cadence_mcp_bridge operator-design show --store revisions.sqlite3 --workspace synthetic-work --design inverter --revision draft-one
```

The exported device values and zero source hash are explicitly synthetic. They
are not PDK/CDF guidance. Use a separate metadata store, never the existing
analysis/sweep journal. Retry retains the same revision; a changed plan needs a
new revision ID and exact parent binding. External result references remain
unverified; plan validation cannot grant execution, ERC/LVS or physical signoff.
`physical-assess --inventory FILE` assesses supplied typed metadata locally.
See [M2 foundation](docs/M2_FOUNDATION_01.md) for API and preservation limits and
[physical observations](docs/M2_PHYSICAL_OBSERVATIONS.md) for current unknowns.

The experimental operator-only CDF API adds no MCP tool or remote execution CLI
and never runs at import/server startup. A separately authorized, observed-CDF
inverter case created owned OA and completed DC/TRAN plus automatic extraction.
Independent effective-input checks verified that narrow source's device geometry;
this does not provide general W/L editing or prove logic switching, settling,
performance or signoff. Earlier failed observations/netlists remain preserved.
See [the actual result and limits](docs/M2_OWNED_INVERTER_01.md).

Physical metadata collection is also an explicit, finitely authorized operator
API. Durable OS-account claims survive plans, package transitions and restarts;
failed/unknown claims stay spent. File presence does not establish a usable API,
license or layout/DRC/LVS/PEX backend. The candidate's framing correction has
synthetic boundary tests and requires no new VM collection. See
[metadata status](docs/M2_PHYSICAL_METADATA_01_STATUS.md).

## 2.1.0 candidate: available features

Read `cadence://feature-guidance` in a resource-capable MCP client, or run
`operator-features --settings RUNTIME --context ID` for explicit local inspection.
The report distinguishes the loaded operator/legacy mode, circuit descriptions,
synthetic fixtures, reference adapters, missing bindings and submit authority scope.
`REQUIRES_EXECUTION_CHECKS` still requires the normal job-specific checks; it is
not live qualification or permission to execute. Expired submit authority does
not imply that admitted results are unavailable. Private paths and remaining
budget are not exposed. This additive candidate feature is absent from the
published2.0.0 wheel. See [states and verification scope](docs/POST_02_FEATURE_GUIDANCE.md).

## 2.1.0 candidate: existing-result reports

Use `operator-results jobs` to browse retained native jobs, then `capture` with
the exact successful job ID and plan hash to export a verified existing result.
Offline `find`, `show` and `compare` preserve quantities, units, definitions and
provenance and reject incompatible conditions. Dates refer to report capture;
simulation dates are unknown. Reporting dispatches no simulation or extraction
and reserves no capacity. Native clients also receive additive catalog/report
resources. This candidate feature is absent from the published2.0.0 wheel. See
[commands and evidence scope](docs/POST_03_RESULT_REPORTS.md).

`operator-results compare` checks repetitions with matching complete conditions;
it does not compare changed W/L or mixed-input candidates. Experimental
`operator-analog` readers preserve sampled definitions and null/unqualified
outcomes. `operator-recovery` is explicit extraction-only recovery, actually
qualified only on one registered inverter DC route. Neither is automatically
activated by import, doctor, reporting or ordinary same-ID retry. See the
[qualification table](docs/releases/2.1.0/QUALIFICATION.md) before use.

## Set up your VM and register a circuit

Follow the exported `my-operator-setup/README.md` in order. Every installed command
has `--help` and closed JSON schemas; the complete arguments and binding rules
are included in that guide.

1. Register your environment, design and existing PDK; validate their hashes and
   runtime context. Set job/result roots to `<managed_root>/native-mcp-v1-jobs`.
   Never import another operator's credentials, UUIDs, policy, grant or journal.
2. Run read-only environment/trust checks. If correction is necessary, export
   the fixed repair helper and exact plan. Your VM owner approves the targets,
   preserves rollback information and applies only necessary metadata changes
   through normal administrator access. Recheck as the ordinary account.
3. Choose genuine zero-history domain initialization or retained existing-domain
   registration. Keep the actual counter, shared lock, identity, history and
   results. A different host journal cannot reset remote consumption.
4. Register your source schematic and saved ADE L state through `native-registration
   observe` and `assemble`, with protected source/model baselines and registered
   result signals. The collector is read-only; execution uses owned work copies.
5. Export/stage the immutable native bundle, confirm a bounded operator grant,
   activate and preflight normally. Bind exact hashes to your context. A valid
   configuration or plan does not authorize execution.

The common parser supports DC operating point, typed AC frequency grids and typed
TRAN stop/max-step settings. Unsupported statements, hidden analyses, expressions
and unregistered includes reject. Register actual signals and scientific meanings;
the bridge does not infer arbitrary measurements.

## Run, query and repeat

Export `client-config` for your context, add its explicit `serve-operator` fragment
to your client and reconnect. Actual Codex qualification belongs to published
2.0.0 and its recorded configuration; an actual2.1.0 client update is not tested.
SDK compatibility is separate from actual application qualification.

Use `operation plan`, then `operation submit` with that plan hash and one chosen
UUID. MCP equivalents are `cadence_plan_operation`, `cadence_submit_operation`,
`cadence_operation_status` and `cadence_operation_result`. They accept registered
logical inputs, never caller paths, shell commands, SKILL, OCEAN or netlists.
Results contain bounded DC voltages/signed power, registered AC transfer samples
or TRAN summaries with verified provenance. `native-sweep` coordinates registered
bounded1D points under the same ledger. Specifications use explicit targets,
units and conditions: missing targets give NOT_EVALUATED and mismatched conditions
cannot become PASS. There is no unlimited search or automatic optimization.

After response loss/restart, query and retry the **same UUID and plan**. Existing
IDs look up retained work rather than dispatch again. Preserve failed/unknown
records; do not mint another ID, delete journals or reset accounting to conceal
uncertainty. Failures stay charged.

## Update, rollback and legacy clients

2.0.0 changes the documented bare launch from the historical reference backend
to operator setup. Missing settings give SETUP_REQUIRED without contacting the
developer VM. This configuration migration requires a major version even though
the original22 MCP declarations remain pinned. Users deliberately retaining
legacy behavior explicitly select `serve`:

```toml
args = ["-m", "cadence_mcp_bridge", "serve"]
```

New operators use `serve-operator` with their own context. Legacy fixed-circuit
tools keep their historical policy and evidence; they are not a fallback for your
registered circuit. Keep old wheels/dependencies/client settings/native bundles,
grants and external journals. Host package and native runtime transitions are
separate integrity-checked operations. Old1.0 cannot launch `serve-operator`;
restore explicit old settings without deleting new state. Uninstall preserves
external journals and every remote source/result/ledger/history. See
[installation and recovery](docs/generic_release/INSTALL_DRAFT_2_0_0.md).

For the2.1.0 candidate, use the separate
[upgrade and rollback guide](docs/releases/2.1.0/INSTALL.md). A host package
transition does not activate or roll back the native runtime. Existing journals,
grants, shared accounting, account-scoped metadata claims and unrelated client
settings must be retained. Installing a version grants no new execution scope.

## Troubleshooting and limits

| Observation | Action |
| --- | --- |
| SETUP_REQUIRED | Export the starter and configure your own context. |
| executable_permissions | Preserve the read-only plan; have your VM owner apply exact authorized repair, then recheck normally. |
| authority_inactive | Check loaded grant, expiry and confirmation; preserve spent scope. |
| Busy/lock/recovery rejection | Identify the live owner; preserve evidence and unrelated jobs. |
| Budget/disk rejection | Read consumption and bounded work requirements; keep failures charged and disk checks enabled. |
| Input/extraction failure | Preserve the UUID and artifacts; inspect registration and effective-input/reader bindings. |

Fresh generic destructive storage and active simulator termination are unavailable;
cancellation is pending-only. General phase margin/offset/slew, arbitrary PVT,
other PDKs, cloud/multi-user EDA and Claude application qualification are not claimed.
MCP/SSH/Cadence/extraction run without root. No public sudo/chmod/chown, generic
shell, unrestricted OA/PSF interface or license bypass is exposed.

## Development and distribution rights

Hosted Windows/Linux CI uses synthetic data and locked dependencies for
lint/type/security/contract/package and installation checks. It has no Cadence/PDK
or license access. Actual VM/app evidence is separate. See
[contribution guidance](CONTRIBUTING.md) and [security](SECURITY.md).

Apache-2.0 covers original bridge code within its licensing rights. Dependencies,
Cadence/PDK and clients keep their own terms. Imported planning remains
LEGAL_REVIEW_REQUIRED and is excluded from curated packages and inspected new
Git archives; exclusion does not clear history, clones or external adaptations.
See [third-party scope](THIRD_PARTY_NOTICES.md) and
[archive boundary](docs/AGENT_PLAN_EXPORT_BOUNDARY_V1.md).

GitHub Releases hosts the published2.0.0 build. Any later release requires its
own exact commit/files/hashes and final user approval before tag/Release/upload.
PyPI/MCPB/marketplace posting is a separate decision.
