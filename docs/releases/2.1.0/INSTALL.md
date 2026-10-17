# 2.1.0 candidate installation, update and rollback

This guide prepares an unpublished candidate. Use only files from the same final
reviewed release and verify every SHA-256 against its SHA256SUMS. Current public
2.0.0 files are not replaced by development artifacts with the same old version.
Python3.12 is the actually tested host interpreter; the professor's standard VM
and existing PDK remain the supported Cadence environment.

## New installation

Keep operator files outside the package environment. In a new host environment:

```powershell
Get-FileHash -Algorithm SHA256 .\cadence_mcp_bridge-2.1.0-py3-none-any.whl
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r locked-runtime-2.1.0.txt
.\.venv\Scripts\python.exe -m pip install --no-deps .\cadence_mcp_bridge-2.1.0-py3-none-any.whl
.\.venv\Scripts\python.exe -m cadence_mcp_bridge --version
.\.venv\Scripts\python.exe -m cadence_mcp_bridge doctor
.\.venv\Scripts\python.exe -m cadence_mcp_bridge operator-starter --output .\my-operator-setup
.\.venv\Scripts\python.exe -m cadence_mcp_bridge operator-setup guide --mode fresh
```

The hash command is an example of one file; compare all release files before use.
Fictional starter examples are not actual credentials, PDK/device recommendations
or execution authority. Register your own observed environment, circuit/ADE,
PDK, ordinary account, work/results paths and limits through the exported guide.
`doctor`, import/server startup and setup guidance do not initialize a VM domain,
repair permissions, create a journal or run EDA. An actual owner-approved repair,
domain setup, immutable native installation, registration and bounded confirmed
grant are separate operations. Never copy a developer's private journal/grant.

## Updating an existing2.0.0 installation

Preserve the old wheel and its locked requirements, exact existing client config,
operator contracts/context/provider/grant files, local analysis/sweep journals
including active SQLite sidecars, native bundle manifests and histories, and the
existing resource-domain/OS-account metadata claim state. Back up consistent
journals while their writers are stopped; copying an active SQLite main file
alone is not a consistent backup. Do not change or delete the live domain to
make a new installation appear empty. Consumed/failed/unknown scope stays spent.

1. Verify the exact candidate release hashes and its qualification/limits.
2. Install the candidate wheel and its hash-locked dependencies in a separate
   venv, preserving the old venv for rollback. Package installation cannot contact
   or activate the VM. Run `--version`, `doctor` and existing-mode setup guidance.
3. Validate your existing contracts with `operator-setup check`. Preserve explicit
   `serve` or configured `serve-operator` launch and all unrelated client entries.
   A new venv needs its own interpreter path in only the selected client entry.
4. Review any new feature's native requirements. A retained2.0 runtime is not
   automatically upgraded or qualified for recovery. If needed, use the existing
   explicit immutable native stage/update/confirmation/preflight workflow with
   both old/new manifest hashes, current ordinary-user trust checks and remaining
   authorized scope. Keep predecessor bundles and partial/failed update receipts.
5. Reconnect the changed MCP connection once. Check the loaded package/context,
   retrieve a retained admitted job, then repeat the exact ID/plan after restart.
   Lookup must not dispatch or reserve again. An expired submit grant does not
   authorize new work; result access retains its own identity/integrity checks.

Current candidate acceptance distinguishes isolated host transitions from actual
client reconnection/native activation. If no actual application update has been
performed, report it as untested rather than inferring success from SDK startup.

## Rollback and recovery

Restore the old venv/interpreter and only the saved selected client entry, keeping
other client settings and all external state. Do not restore an older copy of a
live ledger/journal over consumed current history. A host downgrade leaves newer
records intact; preserve unsupported records and restore the qualified newer
package to read them. A wheel downgrade does not undo native activation or bless
a semantic native downgrade. Use the documented immutable predecessor/recovery
procedure only within its explicit authority. Never reset grants/account claims.

If update/reconnect is interrupted, inspect the existing operation/status and
exact update intent before retry. Same ID/plan reconciles; unknown/running states
must not become a replacement job. Keep original failure, PSF and receipts.
Extraction-only recovery is separate experimental admission, not an ordinary
retry or automatic result lookup. Compaction/deletion is not an upgrade step.

## Repeatable release verification

`scripts/verify-package.ps1` builds curated artifacts and checks same-version
installed protocol/bootstrap/setup/recovery plus reinstall/uninstall preservation.
It does not demonstrate an old-to-new transition. From a source verification venv,
run the separate bounded host verifier with independently checked release inputs:

```powershell
python -I -X utf8 scripts/verify-version-transition.py --published-wheel ABSOLUTE_PUBLISHED_2_0_WHEEL --published-lock ABSOLUTE_PUBLISHED_2_0_LOCK --candidate-wheel ABSOLUTE_CANDIDATE_2_1_WHEEL --candidate-lock ABSOLUTE_CANDIDATE_2_1_LOCK --workspace NEW_ABSOLUTE_DISPOSABLE_DIRECTORY
```

It creates its own isolated venv, installs each version's hash-locked dependencies,
then checks2.0.0→2.1.0→2.0.0→2.1.0 with real disposable journal replay, full common
MCP declarations and unchanged external synthetic state. The installed2.1 durable
claim API creates a claim in a substituted disposable account home and rejects
the same identity after rollback/upgrade. Its real owner/mode/exclusive-write
guards remain active; the actual OS-account home and VM are never accessed.
Logs and failures remain in that new directory. Dependency
downloads may occur; no SSH/EDA executable is available to the child bridge, and
no actual VM/native activation or app update is performed by this test.

## Troubleshooting

Missing setup: use your own exported starter; do not enable a developer default.
`executable_permissions`: retain the read-only exact repair plan and have this
VM's owner authorize/apply only the necessary reversible metadata changes.
Authority/budget/disk failures: inspect current bindings and consumption; do not
create another journal/domain, refund failures or disable disk floors.
Recovery/lock/unknown state: preserve evidence and identify the current owner
before another admission. Neither bridge nor Cadence should run as root.
No license files, server restrictions, system Python or Cadence/PDK contents are
changed by this release. Existing software entitlement remains required.
