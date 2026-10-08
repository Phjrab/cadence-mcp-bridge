# Operator runner coexistence v1

Support remains the professor-provided CentOS/Cadence VM or equivalent installation
with its existing PDK in each operator's VMware. Actual current-VM observations:
CentOS6.5/i686, system Python2.6.6, Virtuoso IC6.1.5.500.15,
Spectre12.1.0.347.isr3. These are reference observations from current evidence;
operator addresses, SSH keys/accounts, workspace/circuit/ADE/results and budgets
must be separately registered and verified. They are not universal defaults.

## Installed package workflow

Use `runner bundle --profile environment.json --output bundle` and
`runner export-installer --output installer.py` from the installed wheel. Inspect
the manifest, helper SHA256 and byte count. Transfer the exact private files to
the operator's guest staging area using their strict-host-key SSH connection;
verify helper and every asset hash before invoking it. On the ordinary guest user:

```text
/usr/bin/python -E -s -B installer.py install BUNDLE MANAGED_ROOT MANIFEST_SHA256
/usr/bin/python -E -s -B installer.py activate-operator MANAGED_ROOT MANIFEST_SHA256
```

The dedicated cadence-operator-runner/active-operator-runner.json/revocation record
coexist with the retained cadence-runner/active-runner.json/legacy revocation.
Ordinary-owner target binding and trusted ancestor checks remain. Activation uses
the existing run.lock without creating/truncating it. Busy, unresolved execution,
wrong-profile, wrong-content, revoked or linked state rejects. Windows content
staging fixtures do not attest POSIX trust or durability.

Repeat activation verifies the same selected immutable bundle and launcher bytes;
known launcher-before-pointer partial initial activation can resume. Unrelated
launcher bytes are never replaced. Existing-domain counters, source/OA/ADE/PDK,
results/replay and journals are not touched. This initial flow still requires an
already provisioned physical domain lock: genuine new-domain provisioning and
existing-domain migration remain unfinished GREL03 work, not private prerequisites
accepted as a finished release.

Run the installed `runner preflight --bundle bundle --expected-plan-sha256
MANIFEST_SHA256` command. It invokes fixed /usr/bin/python -E -s -B on the dedicated
launcher; the launcher also uses isolated startup for the immutable child runner.
This handles Windows text transfers without relying on a guest shebang. The exact
current package assets must match the selected bundle. Preflight is identity,
runtime/binary/root/disk qualification, not analysis support or license entitlement.
Capabilities remain unqualified and execution_authorized=false.

## Bounded preflight launcher update and recovery

```text
/usr/bin/python -E -s -B installer.py update-operator-preflight MANAGED_ROOT NEXT_SHA PREVIOUS_SHA
/usr/bin/python -E -s -B installer.py deactivate-operator MANAGED_ROOT NEXT_SHA
```

Updates require both intact immutable versions, identical profile/probe/reservation
and runner bytes, and the compiled known preflight-only runner digest. Other code,
profile/policy changes or arbitrary equal runner bytes reject. This is not a
production simulator worker upgrade gate. The same resource lock and unresolved
job/revocation guards apply. Previous/next manifests and launcher hashes are recorded
in an immutable private transition before atomic launcher/pointer replacement;
old runtime versions and legacy state remain. Fsync includes containing directories
on Linux. A crash between the two replacements leaves a pair that cannot pass
preflight until the exact update resumes. Known intermediate pairs require the
matching original history; invented/orphan or reversed pairs reject. Completion
gets a separate retained receipt. Repeating a complete transition verifies bytes
and changes nothing. Deactivation is repeatable and preserves versions/pointer.
No root MCP/EDA, ledger reset/refund, forced job termination or publication occurs.

## Actual current-VM evidence

Ordinary guest uid500 installed and activated the dedicated launcher; repeat was
exact. Initial direct shebang preflight failed because CRLF was parsed as a Python
option. That private failure remains. The fixed interpreter path then passed two
fresh active preflights; holding the actual existing run.lock in a second process
made activation reject. Legacy launcher/lock/counter inode, mode, owner/group and
content SHA256 remained unchanged.

A subsequent same-profile launcher revision added isolated child startup and exact
integer schema checks. The actual helper recorded the transition and repeated it
without further changes. First revised preflight runner manifest is
4d8b5992e829d7afd5fe9b58133d8b7c974c9ac77fc2879758f5de82d49de6c6;
launcher SHA256 da2e73d0d5989028bc51fc53656f6d5d253a76ce6f7e60fc0cccd2c753711e58.
Actual installed-wheel fixed preflight and fresh-process repeat passed at
2026-10-08T06:06:04Z. Exact profile/private paths and raw receipts remain ignored.
A prior attempt to update to the identical manifest correctly rejected; that
private diagnostic is retained and made no activation change. The shipped final
installer additionally rejects the impossible new-pointer/old-launcher pair;
its source-specific final no-op receipt is recorded separately when verified.

This work submitted zero new simulations or reservations. Fresh read remains82
attempts and9,798,942,720 reserved bytes, leaving895MiB under10GiB. No historical
result/journal/PDK deletion or reset. New operator-owned staging/runtime assets
consume small actual disk occupancy independently of simulation reservation.
Original permission-repair332 differences remain as recorded in ADMIN_REPAIR_V1.md;
this work changes only bridge-owned launcher/activation assets.

## Validation and remaining gates

Local affected198 PASS/seven platform skips,19.82s; Ruff and mypy72 PASS. Security18
PASS/1.39s and locked dependency audit clean predates the final update extension;
final candidate security/package/hosted receipts are recorded as completed.
Synthetic cases cover coexisting state, exclusive collisions, initial/update crash
recovery, idempotent repeat/deactivation, strict state types and refusal of changed
profile/probe/reservations/runner. Ubuntu CI includes real flock and update fixtures.
Installed wheel tests exercise coexistence/update/reinstall/uninstall preservation;
these are separate from actual CentOS preflight and are not native job execution.

PR148 exact-source0870c73: hosted Windows2640 PASS/eight platform skips/56 warnings,
220.16s; Ubuntu95 PASS/no skips,4.86s; installed32-file preservation and matching
local wheel passed. Sdist hashes differ between the separately audited local and
hosted build representations; no byte-equality claim is made for those sdists.
Independent review is still separately observed; successful CI is not approval.

Production provider/operator consent, live migration/fresh provisioning, two new
OA/ADE designs/effective inputs/DC/AC/TRAN/automatic extraction, generic Sweep/spec,
clean actual Codex submit/read/retry/restart and full dynamic runtime attestation
remain incomplete. Continue authorized GREL02–07. GREL08/merge/publication and budget
increases remain excluded. Historical reports retain their old boundaries.

Final canonical-source receipt:199 affected PASS/seven platform skips,22.19s;
Ruff/mypy72 PASS, security18 PASS/1.69s, dependency audit clean. Python sources
use the repository LF representation, and guest invocation keeps fixed isolated
Python flags. Current-VM final exported helper/immutable assets install and
preflight-only transition/repeat PASS. Latest selected manifest is
`4bf95a3c818e2c8bc07b760d9b2ff2041e64f42d4023970796d0325b3814c02c`,
launcher `1fc18429942ad801b4c379f7c7f03be003067eedd518b3b26f6ed46c68a8672f`,
normal-user fresh repeat at `2026-10-08T06:13:52+00:00`. Previous
versions and transition records remain. Actual Python2.6 disposable-file tests
passed partial update recovery, repeats, revocation and retained legacy bytes;
no vendor code, native job or new ledger was used in those synthetic tests.

Retained audited candidate wheel SHA256
`363b95af48448e7825839db69d8081344135888a0b27330357d2101342663056`;
sdist `2e70f1c4b3b9ba1f6ebbc1c06d79011211e124409f98e0545bd46146dd3e2bb4`.
These identify this candidate, separate from earlier CRLF artifacts/failures.

Final installed package/protocol/coexistence/update/bootstrap and reinstall/uninstall
verification PASS;43 synthetic state files preserved and native jobs0.
