# Windows host installer preview — 2.2.0a1

Unpublished, unsigned Windows x64 preview. This is not an addition to v2.1.0.
The frozen bridge base is main a713eb6b1db2a90652501bb71a3dacbe75c65460;
PR164 is excluded. Main's explicit V/A candidates remain experimental opt-in and
not actually native-qualified. No VM, Cadence/PDK/license/circuit/PSF is bundled.

Run CadenceMCPBridge-2.2.0a1-windows-x64-setup.exe as your ordinary user. No Python,
Git, uv or pip installation is required. Windows .NET Framework 4.x supplies the
native setup GUI; the package supplies isolated CPython 3.13.12 and locked wheels.
Windows OpenSSH Client is checked separately. If absent, use Windows Optional
Features with the required OS permission; the bridge stays connection-pending.
Do not disable host key checking, SmartScreen, antivirus or execution policy.

The setup GUI offers new connection guidance, import of an existing runtime, or
program-only installation. Enter your own VM host/alias/ordinary username and
select an existing key if needed. No password is collected. Independently verify
the VM host key before populating OpenSSH known_hosts. The explicit connection
button makes one fixed SSH response check; no EDA or result reservation follows.
Connection drafts do not rewrite your SSH configuration.

Import a runtime and select its context. Local checks preserve every original
registry/journal/grant/resource-state path. New users can export the existing
operator starter and follow its reviewed registration and authority workflow;
fictional examples never become production evidence. Native provisioning,
registration and execution still require actual observed inputs and consent.

Codex configuration uses CODEX_HOME or ~/.codex/config.toml. Preview the one MCP
entry before applying; same-name update requires an explicit selection. Other
servers, settings and comments are retained. Backups and change receipts are
kept in LocalAppData/CadenceMCPBridge/UserData/config-history. External changes
detected before save reject and require a fresh preview. The atomic file replace
is not a universal cross-process compare-and-swap; avoid simultaneous edits.
Project overrides are reported for the selected project, conservatively including
ancestors. Managed policy/CLI overrides and actual app connection need separate
verification. Reconnect Codex normally when needed; never force-close the app.

Programs use version-specific directories under LocalAppData/Programs. User data
stays separate. Updates install a new version alongside the old, then explicitly
preview the client switch. Existing jobs are not terminated. A host update does
not deploy a VM runtime. Do not downgrade without verified state compatibility.
Before removing a version, use its GUI's managed-connection removal: only an
unchanged owned entry is removed/restored, never the whole historical backup.
Windows uninstall removes program-owned files; external settings and all remote
circuits/results/accounting/evidence remain. Interrupted installs can be rerun;
retain diagnostics and do not reset a ledger to recover setup.

INSTALL-MANIFEST.json binds the source commit, runtime/dependency inputs and all
payload bytes. DEPENDENCY-LICENSES.json accompanies wheel dist-info license files
and CPython LICENSE.txt. Checksums establish consistency, not publisher identity.
No signing certificate was purchased. Inno Setup 6.7.3 is used under its license:
https://jrsoftware.org/files/is/license.txt (commercial use permitted; upstream
requests commercial support). Its compiler is only a build dependency.

Official Codex references consulted 2026-10-28:
https://developers.openai.com/codex/config-basic/
https://developers.openai.com/codex/mcp/

Host installed, client configured, VM connected, preflight passed, circuit
registered and execution authorized are separate states. Windows CI/SDK evidence
does not establish actual Codex/VM success or all Windows 10/11 compatibility.
