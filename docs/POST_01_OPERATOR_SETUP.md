# POST-01: guided operator setup

Status: implemented and locally verified; feature PR checks follow, 2026-10-13. This host CLI
feature follows the published [2.0.0 release](https://github.com/Phjrab/cadence-mcp-bridge/releases/tag/v2.0.0)
and is not included in that release's wheel. No new version or release is selected.
POST-02 through POST-07 remain proposed work.

The helper reuses the existing contract validators, runtime context and client
export. It never contacts the VM, executes a command, repairs permissions,
creates a resource domain, registers remote circuits or runs a simulation.
Local consistency does not establish current authority or actual Cadence success.
The supported environment remains the professor-provided standard VM and PDK.

## 1. Choose the installation path

Run the helper from the host environment containing the bridge:

```text
python -m cadence_mcp_bridge operator-setup guide --mode fresh
python -m cadence_mcp_bridge operator-setup guide --mode existing
```

Choose one mode. `fresh` describes the later initialization path for a genuinely
empty resource domain. `existing` describes retaining the actual domain,
ledger, journals, identity, locks, results and consumed reservations. The guide
does not determine whether a remote domain is empty. The existing domain tools
must observe and validate that condition before any explicit initialization.
A new host, virtual environment or local journal is not a new resource budget.

For first-time files, use the existing `operator-starter --output NEW_DIRECTORY`.
It exports this package's fictional environment/design/PDK examples and guide,
without developer credentials, private journals or past jobs. Replace example
values with observed operator data. Keep host-key checking enabled and run the
bridge and Cadence as the ordinary account. Use `doctor` for host prerequisites.

## 2. Validate your contracts

```text
python -m cadence_mcp_bridge operator-setup check --profile ENV --design-registry DESIGNS --pdk-registry PDKS
```

`ENV`, `DESIGNS` and `PDKS` are paths to your private JSON files. This checks the
same closed schemas and cross-contract relationships as existing `verify`.
It does not infer scientific measurements or grant authority. The starter is
deliberately read-only, unqualified and zero-budget; passing local validation
does not make its fictional circuits executable.

For native use, register your actual source library/cell/view and saved ADE L
state, allowed analyses, explicit variable units/bounds/review and measurement
contracts. Use the existing schema commands; schema4 adds measurement contracts.
Use `owned_copy_only` for executable circuit registrations. Native new-domain
setup requires job and result roots `<managed_root>/native-mcp-v1-jobs`; replace
the fictional starter's example paths before that setup. Never infer a host,
account, grant, journal or resource limit from another operator's configuration.

## 3. Export a runtime context

Create or select your private host directories through your normal operator
workflow first. The state directory and both journal parents must already exist.
The helper does not create directories, journals, locks or authority records.

```text
python -m cadence_mcp_bridge operator-setup export-runtime --profile ENV --design-registry DESIGNS --pdk-registry PDKS --resource-state-root STATE_DIRECTORY --context CONTEXT_ID --runner-sha256 RUNNER_SHA256 --authority-ref AUTHORITY_REF --ledger-ref LEDGER_REF --journal ANALYSIS_JOURNAL --sweep-journal SWEEP_JOURNAL --output NEW_RUNTIME
```

The helper computes exact file hashes for your supplied contracts and validates
the resulting context before creating a new output. It preserves the existing
runtime schema and does not rewrite any selected file. Select the verified runner
hash and your actual authority and ledger references explicitly; references are
not an approval. Keep your retained state and journal paths when continuing an
installation. The two journals must be distinct and must not collide with inputs,
outputs or resource locks.

Optional native bindings remain explicit pairs:

- `--native-provider-binding` and `--native-provider-sha256`
- `--operator-grant` and `--operator-grant-sha256`
- `--native-specifications` and `--native-specifications-sha256`

Provider and grant bindings must be supplied together as required by the runtime
schema. Recording them does not authenticate the live installed provider, assess
grant expiry/remaining scope or qualify a circuit. Those checks stay in the
existing native/authority execution path. After intentionally changing bindings,
export to a new runtime filename; retain the previous settings for recovery.

Check the selected context without repeating its contract paths:

```text
python -m cadence_mcp_bridge operator-setup check --settings NEW_RUNTIME --context CONTEXT_ID
```

The two `check` input forms are exclusive. Do not mix `--settings/--context` with
the three individual contract arguments.

## 4. Complete the existing explicit VM workflow

Follow the exported starter guide for read-only environment qualification,
runner trust and preflight. Any necessary fixed repair requires the VM owner's
actual authorization and preserved rollback evidence. Select fresh setup or
retained-domain registration explicitly; keep existing accounting and history.

Use existing `native-registration observe` and `assemble` for the protected
source/state/model observations, privately exported baseline input and explicit
reader definitions. Stage the immutable native bundle, confirm the operator's
bounded grant, activate and preflight with the existing commands. These actions
have their existing permissions and integrity checks; `operator-setup` performs
none of them. Bind the resulting reviewed hashes in a new runtime settings file
and check it again. The starter guide contains full commands and schema pointers.

## 5. Export client configuration and verify the first job

```text
python -m cadence_mcp_bridge operator-setup export-client --settings RUNTIME --context CONTEXT_ID --format codex --output NEW_CLIENT_FRAGMENT
```

The selected context supplies the environment/design/PDK and journal paths to
the existing client exporter. Formats `codex`, `mcp-json` and `claude-desktop`
are available. Export format support does not qualify the corresponding actual
app; actual Claude validation remains deferred. The command creates only the new
fragment. Review it and install it into your own client settings, then restart
that MCP connection to load `serve-operator` with the selected runtime context.

Run the first actually approved job through existing `operation plan/submit`
or the registered MCP equivalents. Query its status and verified result. After
response loss or restart, reuse the same UUID and plan hash. Confirm that result
and same-ID recovery add no execution/reservation. Preserve failure evidence.
CLI/schema/fixture success alone is not proof that this VM or client ran Cadence.

## Recover from a setup error

| Problem | Next action |
| --- | --- |
| A local contract cannot be read or validated | Check the named input stage and its existing schema/validate command; keep private JSON contents out of public logs. |
| Environment, PDK, corner or analysis relationship conflicts | Correct the intended relationship in operator-owned contracts, then validate all three together. |
| Context is missing or unknown | Supply the runtime file and its explicit context ID; do not fall back to a developer connection. |
| Contract hashes are stale | Verify the intended edits, then export a new context; keep the old binding as history. |
| State or journal parent is missing | Select or explicitly prepare the correct private host directory; do not replace retained journals. |
| Journal/contract/output paths collide | Use distinct intended paths and a new output filename; preserve every existing file. |
| Output already exists or an export was interrupted | Inspect and retain the existing/partial output. Repeat with a new output filename after resolving the cause. |
| Native binding is incomplete | Provide every required path/hash pair from existing reviewed outputs. Do not invent approval or qualification. |
| Live trust, quota, disk or authority check fails later | Follow the existing VM diagnostic workflow. Do not reset accounting, disable checks or use fresh setup to avoid the failure. |

## Verification record

Final affected Windows tests: 124 passed, 5 OS symlink skips (including 33 new
setup tests). Ruff and mypy over all 100 source modules passed. Security18,
locked dependency audit and the existing 22-declaration/85-tool compatibility
audit passed. The new Linux CI group exercises setup, onboarding and runtime
checks including the symlink cases.

The first Linux run exposed test-host assumptions: uv's symlinked interpreter
was correctly refused by client export, and configured stdio constructs the
Windows OpenSSH backend. CI now prepares a copied pinned Python interpreter;
only that Windows-specific stdio case is platform-marked. The unconfigured
stdio test and local path/symlink rejection cases still run on Linux. Product
path protection and the supported Windows-host boundary are unchanged; the
failed run is retained on PR153.

The isolated wheel walkthrough passed 15 actual CLI invocations using only
packaged fictional templates, with 7 existing files preserved. It verified fresh
and retained local paths, exact hashes, Codex TOML/mcp-json exports, inherited
environment isolation, exclusive retries and stale binding refusal. Initially
absent journals and locks stayed absent. Wheel/sdist inspection found matching
source/notices, canonical license, no unexpected files or protected-content
patterns. This is installed-package local evidence, not actual VM/client execution.

Independent review found a two-snapshot client-export race. The exporter now
selects and reserves all contexts from one snapshot. Four regression cases and
independent reproduction confirm the correction: removed-context journals and
locks remain reserved, while an unrelated new output works. No blocking finding
remained in that review; it is not a formal GitHub APPROVED review. Hosted checks
are attached to the exact feature PR revision.

POST-01 makes no native executable or policy change and adds zero simulations,
reservations and native corrections. Last actual accounting observed during
release verification remains 112 attempts / 13,825,474,560 reserved bytes under
16 GiB / 500, with native corrections 20/20; this phase did not re-read the VM.
Published2.0.0 and its frozen artifacts remain unchanged. The locally built
development artifacts are test evidence, not another published2.0.0 release.
