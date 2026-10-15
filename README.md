# Cadence MCP Bridge

Register your own circuits and run bounded DC/AC/TRAN analyses and 1D Sweeps in
the professor-provided CentOS/Cadence/PDK VM running in your personal VMware.
Operator settings select a common execution template; another supported circuit
requires no bridge-core patch or circuit-specific Python extractor.

**[2.0.0 is published](https://github.com/Phjrab/cadence-mcp-bridge/releases/tag/v2.0.0).**
Two distinct new inverter/comparator test circuits completed DC/AC/TRAN,
automatic extraction and a bounded AC Sweep on the standard VM. Exact installed
2.0.0 also submitted a new job through the actual Codex app. Result retrieval,
same-ID retry and actual app restart preserved its result without duplicate
execution or reservation. The release includes the exact candidate's installation,
artifact and acceptance reports. Earlier source checkpoints remain in the
[acceptance record](docs/generic_release/GENERIC_ACCEPTANCE_CURRENT.json).

## Supported environment

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
2.0.0; a later development checkout does not change those published files.

```powershell
Get-FileHash -Algorithm SHA256 .\cadence_mcp_bridge-2.0.0-py3-none-any.whl
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r locked-runtime-2.0.0.txt
.\.venv\Scripts\python.exe -m pip install --no-deps .\cadence_mcp_bridge-2.0.0-py3-none-any.whl
.\.venv\Scripts\python.exe -m cadence_mcp_bridge --version
.\.venv\Scripts\python.exe -m cadence_mcp_bridge doctor
.\.venv\Scripts\python.exe -m cadence_mcp_bridge operator-starter --output .\my-operator-setup
```

The exclusive starter export includes the complete setup guide and fictional
environment/design/PDK templates. It needs no developer checkout, private journal
or past job. Keep setup and journals outside the package. Import, doctor and MCP
startup do not initialize accounting, repair permissions or run EDA.

## POST-01 development: guided local setup

The current feature adds `operator-setup` to reduce manual context and client
configuration. This command is not included in the published 2.0.0 wheel yet.
Start with `operator-setup guide --mode fresh` for a genuinely new installation,
or `--mode existing` when preserving an existing resource domain. The guide is
local and does not inspect or initialize the VM.

Use `check` for your environment/design/PDK contracts, `export-runtime` to write
one new settings file, then `check --settings RUNTIME --context ID`. After the
existing explicit VM setup, registration and authority steps, `export-client`
derives its paths from that selected context. Exports never overwrite an existing
file or create journals. See the [step-by-step guide](docs/POST_01_OPERATOR_SETUP.md)
for required inputs, retained-state handling and error recovery.

## M2 development: local design plans

The development-only `operator-design` CLI stores immutable local revisions and
validates a bounded CMOS inverter plan. It is not included in published 2.0.0.
It has no remote execution backend. Start in a new operator-owned directory:

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
to your client and reconnect. Actual Codex is validated; SDK compatibility of
another client is separate from actual application qualification.

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
