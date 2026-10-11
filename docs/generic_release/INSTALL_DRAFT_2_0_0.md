# Standard VM installation draft for 2.0.0

**DRAFT / NOT_RC_READY / DO_NOT_PUBLISH.** The final commit, versioned assets and
SHA-256 list are not frozen. Current tested packages still report1.0.0. Complete
final integrated native and actual Codex qualification before shipping this guide.

## Host installation from reviewed release files

Use Windows with Python3.12 or3.13 and your own professor-provided VM in VMware.
The bridge uses the VM's existing CentOS, Cadence, PDK and license entitlement;
do not upgrade guest Python or install Cadence/PDK from the bridge package.
Other host/Cadence/PDK combinations remain unqualified.

Download the exact reviewed wheel, locked runtime file and SHA256SUMS together.
Compare each file with its published hash using `Get-FileHash -Algorithm SHA256`.
Create a dedicated host environment in an operator-selected directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r locked-runtime-2.0.0.txt
.\.venv\Scripts\python.exe -m pip install --no-deps .\cadence_mcp_bridge-2.0.0-py3-none-any.whl
.\.venv\Scripts\python.exe -m cadence_mcp_bridge --version
.\.venv\Scripts\python.exe -m cadence_mcp_bridge doctor
.\.venv\Scripts\python.exe -m cadence_mcp_bridge operator-starter --output .\my-operator-setup
```

The exported directory must not already exist. It contains the complete packaged
setup guide and three fictional zero-authority templates. No developer checkout,
UUID, private journal, approval file, proprietary circuit or PDK is required.
`doctor` is local read-only and does not provision or perform administrator repair.
Keep unrelated client settings, all earlier packages and private operator data.

## Register and qualify your own installation

Follow the exported README in order. Supply your SSH alias and verified host key,
ordinary guest user, workspace, managed/result roots, resource limits and observed
executable paths/hashes/versions. Keep authentication and license values private.
A common reference version is not proof of your executable identity or entitlement.
The current validation VM's16GiB policy is not another operator's default.

Export schemas with the installed CLI. Validate the environment/design/PDK
registries and explicit runtime settings. Read-only trust and repair-plan commands
report exact targets; only that VM's owner may approve and apply necessary bounded
metadata changes through their normal administrator access. Preserve contents,
metadata, rollback information and all original OA/ADE/PDK/results/journals.
Use the normal account to recheck. Neither MCP nor Cadence runs as root.

Choose the correct accounting flow: genuine zero-history initialization uses the
fresh-domain commands; an already-used VM registers and retains the existing
ledger, lock, identity and history. A new host journal or directory cannot reset
remote consumption. Keep failures charged and disk floors/per-job bounds enabled.

Register your own source cell/view and saved ADE state. The installed common
collector/assembler binds private baseline inputs, model closure and reader
signals for DC/AC/TRAN. Create only owned copies. No circuit-specific bridge
patch or Python extractor is needed; unqualified/unsupported input forms reject.
Stage the exact immutable native bundle, confirm a bounded operator grant, activate
and preflight as the ordinary user. A plan or package install grants no execution.

Export `client-config` from the installed CLI with your explicit runtime context.
The fragment selects `serve-operator`; merge it into your own client's configuration
and reconnect that MCP server. Submit a new registered job, query its result and
retry the same UUID/plan after reconnecting. Check the retained ledger adds no
second execution/reservation. CLI/SDK success does not substitute for this app test.
If the client cannot reconnect, retain that application qualification as pending.

## Migration, update and rollback

Published1.0.0 used the historical reference route for a bare launch. The new safe
operator default returns SETUP_REQUIRED without private operator setup. This is a
breaking launch change and motivates2.0.0. Preserve the original22 tool contracts.
Users intentionally retaining the historical route must select explicit `serve`:

```toml
args = ["-m", "cadence_mcp_bridge", "serve"]
```

Back up your exact old wheel, locked dependency file, client settings, native
bundle/registration/grants and external journals. Install the reviewed replacement
host package, verify its version and exported commands, then explicitly stage and
update changed native assets using previous/replacement manifest hashes. Confirm
only actual authorized remaining scope; retain consumed reservations and history.
Do not copy a developer's grant or use the original unspent limit after consumption.

A host-package rollback and a native-runtime rollback are separate decisions.
The old v1 package cannot run `serve-operator`. Restore its explicit historical
client fragment while retaining new operator data; never downgrade by deleting
journals or resetting a VM. Partially published records/failed candidates remain
for exact-command retry or diagnosis. Unrelated collisions and unknown jobs stop;
do not invent new IDs to bypass uncertain outcomes. Final exact-version upgrade,
downgrade and re-upgrade evidence is still pending for this draft.

Uninstall the selected host package/environment and remove only its reviewed
client entry. Preserve external local state and every remote ledger, result,
failed record, source library, ADE state, PDK, license and native history.

## Troubleshooting and scope

- SETUP_REQUIRED: export the starter and configure your own explicit context.
- authority_inactive: inspect the bounded grant/OS confirmation and client-loaded
  settings; expiry or a stale connection cannot be bypassed with another journal.
- executable_permissions: preserve a read-only exact repair plan, obtain that VM
  owner's authority, apply only reviewed metadata differences and recheck normally.
- busy/lock/recovery rejection: preserve files and identify the live owner; never
  remove locks or terminate an unrelated simulator to pass a gate.
- budget/disk rejection: report current consumption and required bounded work;
  do not delete/refund/reset or disable disk checks.
- unsupported input or extraction failure: retain the original UUID and artifacts;
  inspect effective-input/reader bindings before another expressly scoped experiment.

The intended verified functions are registered DC/AC/TRAN, bounded1D Sweep,
automatic bounded results and condition-bound specifications in the standard VM.
No destructive generic cleanup, active simulator termination, general PM/offset/
slew/PVT, unlimited optimization or universal Cadence/PDK support is promised.
Public posting of the exact candidate still requires one final user approval.
