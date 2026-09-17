# WP-14 Narrow Deployment Result — Version 1

Date: 2026-09-17

Result: **BLOCKED_BEFORE_REMOTE_PREFLIGHT**

## Scope and provenance

The user explicitly approved this execution's approval record and one fixed remote preflight /
exact eleven-asset deployment, bound to these normalized-LF SHA-256 values:

- Approval package: `7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87`.
- Narrow deployer: `b48b7cb2b24cb3a8ac257031dd6fa79116ea71a4b2117e22226683837692bc1e`.

Both values, both bound version-1 plans, and all eleven package asset hashes match. The immutable
request package still has all authority flags false; the new user decision is recorded separately
in `approvals/WP14_NARROW_REMOTE_DEPLOYMENT_APPROVAL_RECORD_V1.json`.

GitHub PR #25 is MERGED: reviewed head `5ca08e86c3411e50a13fbe8cb5bb83bec624faf9`, merge commit
`42405e271f54595eae69ca193dc9e3fef30dac94`, merged at `2026-09-16T12:19:05Z`. That merge was the
fetched latest origin/main; the repository was PRIVATE and the starting tree clean. The dedicated
branch `wp/WP-14-narrow-deployment-attempt` starts at that exact commit. No merge is performed in
this run.

## Local blockers found before remote contact

### B1 — Success-marker double escaping

PowerShell AST inspection of the exact approved script finds these literal shell strings:

- Line 229: `printf 'WP14_NARROW_PREFLIGHT_OK\\n'`.
- Line 252: `printf 'WP14_NARROW_SNAPSHOT_OK\\n'`.
- Line 306: `printf 'WP14_NARROW_DEPLOYMENT_VERIFIED\\n'`.

The format suffix is bytes `5c 5c 6e`: **two** backslashes then `n`. PowerShell does not consume
those backslashes, and the shell's single quotes preserve them. `printf` interprets the two
backslashes as one literal backslash, leaving the letter `n`, not a newline. The preflight's
modeled output is therefore the marker followed by bytes `5c 6e`. The deployer's `.Trim()` does
not remove that suffix, so the exact marker comparison fails even if every preceding remote check
were to succeed. The install marker uses the same escaping pattern.

Observed preflight format bytes:

```text
575031345f4e4152524f575f505245464c494748545f4f4b5c5c6e
```

Modeled preflight output bytes:

```text
575031345f4e4152524f575f505245464c494748545f4f4b5c6e
```

Method: local PowerShell AST extraction followed by Python POSIX tokenization and escape decoding
of the extracted constant only. All three standalone markers failed the modeled exact-match
check. This is a local language-semantics check, **not an observed SSH response or a remote shell
execution**. The install marker was inspected statically, not executed.

### B2 — Snapshot find terminator double escaping

Line 251 contains `find '$snapshotRoot' -type d -exec chmod 500 {} \\;`. The last bytes are
`30 20 7b 7d 20 5c 5c 3b`. Local POSIX lexical analysis yields a literal backslash argument
followed by an unquoted control semicolon, not the required semicolon argument to `find -exec`.
Joining the command list with `; ` also leaves an invalid adjacent separator. This is a later
snapshot-stage blocker; that stage was not reached. Snapshot TSV formats on line 248 have the
same double-escaped separator pattern and also require review. No snapshot was created.

### Test-readiness gap, separate from deployment evidence

The five existing deployer tests pass in their original gate-absent state. However,
`tests/unit/test_wp14_narrow_deployer.py:79` asserts that the activation file does not exist, and
its current-execution test runs the repository script expecting that absence. Those tests do not
exercise an authorized successful deployment. Creating a live activation file must not be used to
turn a local test run into transport activity. Future tests need isolated authorization fixtures
and explicit fake transports for authorized, rejected, timeout, and failure paths.

Passing the existing test suite is not evidence that these shell strings work. No test, deployer,
or approved asset was changed to bypass these findings.

## Approval handling and stage results

The user's approval is present and recorded, not denied or treated as missing. Because the user
also required a stop on any blocker and approved one exact deployer hash, no corrected script or
alternative remote command was substituted. The executable gate record
`approvals/WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V1.json` was not activated or created.
The separately named audit record cannot satisfy the script's authorization gate.

| Stage | Result | Evidence / limitation |
| --- | --- | --- |
| PR #25 / latest main / private repository | PASS | Exact identities above; clean branch creation. |
| Package, deployer, two plans, eleven asset hashes | PASS | Fifteen normalized-LF hashes checked locally; 7 assets mode 0700 and 4 mode 0600 in the unchanged package. |
| PowerShell parsing | PASS | Zero syntax errors; this does not validate generated shell commands. |
| Generated shell readiness | BLOCKED | B1 and B2 above, before any SSH/SCP. |
| Remote preflight / remote identity | NOT RUN | Zero remote attempts; current remote state is unknown. |
| Recoverable before-snapshot | NOT RUN | No path created; no snapshot identity claimed. |
| Eleven asset installs | NOT RUN | Zero installed assets. |
| Post-install hashes / modes / runner 0.19.0 | NOT RUN | No remote verification or deployment success claim. |
| Cadence / discovery / simulation / design access | NOT RUN | Explicitly outside approval. |

The historical last-observed remote version remains 0.18.0, **not freshly verified**. No SSH,
SCP, remote preflight, snapshot, deployment, cleanup, recovery, fallback, or retry was performed.
The original deployment script, package, bound plans, runner assets, and `deployment_enabled=false`
are unchanged. No source, ADE-state, work-library, PDK, or V1-V4 evidence was accessed or modified.
No remote fingerprint or lock-state equality is claimed without a measurement.

## Local verification

- Ruff: PASS.
- Contract-defined strict `mypy src`: PASS, 17 source files.
- Full local pytest: PASS, 205 passed, eight real integrations deliberately skipped, 56 existing
  legacy deprecation warnings. Integration environment flag remains disabled.
- Local marker/terminator diagnostics: reproducibly identify B1/B2; remote readiness is BLOCKED.
- Document verification: PASS, exactly three documentation files; prior checkpoint/progress text,
  planning assumptions, protected metadata and all fifteen bound hashes preserved; unique flat
  YAML keys, JSON parsing, Markdown fences, absent activation file and false deployment gate.
- Security verification: PASS, 333-file secret preflight, 18 dedicated security tests, and strict
  locked dependency audit with no known vulnerabilities.
- `git diff --check`: PASS.

The deployment acceptance gate has not passed. WP-14 remains blocked; WP-15 is not started.
VDD=1.0 V, VCM=0.5 V, and no added external load remain review-only assumptions. Conditional
VBIASN=0.300 V / VBIASP=0.650 V, unknown actual operating conditions, source/state semantic
equivalence, and snapshot freshness are unchanged.

## Next bounded action — not authority

Obtain separate repository-only correction approval: fix the generated shell escaping, validate
snapshot manifest delimiters and the exact `find` terminator, and add isolated authorized-path
tests with no SSH/SCP access. Review the remaining preflight identity, bounds, and single-use
checks against the immutable package before asserting readiness. Do not modify the package,
asset allowlist, or deployment flag. A corrected deployer has a different hash; this run's approval
must not be carried forward to it. Remote deployment needs a new exact-hash approval after that
review. Discovery invocation remains an independent, later approval.
