# Windows installer preview validation

Unpublished 2.2.0a1; bridge base main a713eb6b1db2a90652501bb71a3dacbe75c65460.
PR164 is excluded, v2.1.0 stays unchanged, and existing V/A candidates remain
experimental opt-in without a new native qualification claim.

Run the preview EXE as an ordinary user, then open the setup helper. Existing
operators can select their runtime/context, preview one Codex MCP entry and
apply it with a backup. New operators can save their own connection details,
export registration guidance and assemble a runtime from registered inputs;
the helper computes pins. No Python, Git, uv, pip or manual TOML editing is
needed on the consumer machine. Missing OpenSSH, registration, preflight and
authority remain separate pending stages. Native enrollment itself still uses
the existing reviewed operator workflow; this is not first-simulation approval.

## Evidence through 2026-10-28

| Layer | Result and boundary |
| --- | --- |
| Local Python/static | Host regressions cover config comments/conflicts/recovery, Unicode, process death, original paths and no implicit remote access. Ruff and strict mypy pass. |
| Local package | Wheel/sdist content/license audit, isolated installed protocol/bootstrap/setup, reinstall/uninstall and retained synthetic state pass. |
| Actual Windows EXE | Windows 10 Home x64, build 19045 (current OS query). Source 1ef4a23 built and installed per-user under Korean/spaced paths with Python/Git/uv/pip hidden from PATH, poisoned Python environment and no checkout cwd. Explicit OS OpenSSH lookup restores configured stdio startup. |
| Actual installed behavior | SDK list/read, config preview/apply, in-use reinstall rejection, repeat install, pre-Python corruption/extra-hook rejection and uninstall pass. Bridge/client/operator files stay identical through reinstall; later unrelated client edits survive uninstall. No admin elevation or Windows restart required. |
| Actual setup GUI | Window startup and Korean-path runtime import returned LOCAL_CONTEXT_VALID through real keyboard/UI interaction. Invalid context exposed a generic error; the backend now returns a stable reason and corrective guidance. New runtime dialog compiles and uses the existing exporter. |
| GUI images | **Incomplete**: Computer Use returned app-approval timeout, then FrameArrived/window-capture timeouts. Accessibility text is retained privately and is not a screenshot or visual-layout PASS. |
| Hosted checks | Exact final-head GitHub checks are required. Earlier 1ef4a23 Linux passed; Windows full suite exposed a missing host-subpackage fixture, and installer acceptance counted Windows icon caches as operator state. Both harness defects are corrected without weakening content or protected-state checks. |
| Actual Codex/VM | **Not run for this installer**. SDK evidence is not an actual Codex connection. No VM contact, administrator action, EDA, simulation or new reservation. |

The local acceptance harness is not a clean Windows OS image. Windows Server CI
does not establish all Windows 10/11 configurations. Disk-full/config-replace
failure is fault-injected; actual disk exhaustion, mid-installer cancellation,
and cross-version host upgrade/downgrade remain unverified. The preview is unsigned.
Checksums establish consistency, not publisher authentication.

Failure logs/builds and the initializer track's accounting remain preserved.
The final external candidate record must bind the exact commit, CI URLs, EXE,
package/manifest/license inventory and SHA256SUMS. Do not publish or describe
this preview as fully accepted until the remaining evidence is recorded and
the user approves the identical public candidate.
