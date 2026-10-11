# Hash-bound reference storage runtime v7

PR151 review4239830332 identified an actual production-layout gap: the historical
v6 launcher deployed `worker.py` without `reservations.py` or the canonical
hash-directory manifest required by fresh accounting. Imported unit tests did not
exercise the empty-package branch. The old immutable v6 and its receipts remain
historical. They are not fresh-domain storage acceptance.

The explicit operator-only `scripts/storage_deploy.py deploy` now targets the new
fixed `storage-mgmt-v7` namespace. Its exact private authority must match the new
contract4 file hashes, two-asset runtime manifest pin and preserved policy/correction/
scan identities. Old v6 authority is not reused. Import, server startup and doctor
never deploy. Staging failures/evidence are retained and automatic retry is absent.
No deployment, actual VM contact, deletion, reservation or administrator change
was performed by this corrective source work.

The packaged pure `reference_storage_bundle()` constructs `run.sh` and exactly
`runtime/<sha256>/storage.py`, `reservations.py`, `manifest.json`. The canonical
manifest binds the two asset bytes and fixed reference managed root. The closed
launcher verifies the outer deployment hashes and exact operator-configured pin,
accepts only inventory/cleanup plus bounded hexadecimal JSON, and runs storage
with the standard profile flags `-E -s -B`: Python environment overrides and
user-site imports are disabled, and no bytecode is written. Before accounting import, the worker checks
the manifest kind/version/location, trusted ancestors, file ownership/link/mode,
size and hashes. Missing, altered, writable or wrongly named assets reject.
No CWD/PYTHONPATH helper fallback or arbitrary path/shell endpoint exists.

Set the operator-owned legacy-reference setting
`CADENCE_MCP_REFERENCE_STORAGE_MANIFEST_SHA256` to the exact deployed manifest
SHA-256 after independent bundle qualification. That pin selects the fixed v7
launcher. An absent pin retains explicit historical v6 routing; v6 does not become
fresh storage capable. Operator runtime profiles use the separately qualified
native provider route, not this fixed reference setting. Configured pins must be
64 lowercase hex characters; operator mode rejects the reference pin.

The shared internal `execute_fixed(root_path, action, request, before=None,
native_generic=False)` accepts a trusted caller root, never a public path input.
It takes the existing nonblocking `run.lock`; exact provider activation checks
run after successful lock acquisition or before a protected busy inventory.
Cleanup contention/unknown lock errors reject. The legacy implementation leaves
`native_generic=True` fail-closed pending root152's protected two-root consumer;
it does not silently omit generic-native result storage.

Portable setting/backend/bundle and held/busy activation ordering regressions
pass locally. Ubuntu workflow now includes real standalone empty-package tests,
real filesystem modes/descriptor checks/flock and exact packaged code, plus
missing/changed/writable/wrong-name helper and manifest failures, restart, bounded
backend routing and cleanup dry-run with retained payload/ledger/operations.
Only the disposable fixture account home/root are substituted; Windows skips the
Linux cases and is not POSIX qualification. Exact hosted checks, package/security
and refreshed independent review remain gates. Current general release is BLOCKED.

Current direct authority remains GREL02-08 candidate preparation, conditional
normal related-PR merges and the validation VM's retained16GiB/500/20 ceiling.
Other installations keep their registered budgets; counters/history are preserved.
Public tag/Release/assets still require final exact-candidate approval.


## Import isolation review correction

Review4239887478 at b83726a found the initial v7 launcher used only `-B`.
Its exact standalone/accounting/descriptor and installed43+20-state tests passed,
but those checks did not qualify startup isolation against PYTHONPATH/user-site
code. The corrected launcher and explicit deployment compile use `-E -s -B`,
matching the standard-VM reference invocation. The real standalone fixture uses
these exact flags, asserts interpreter environment/user-site/bytecode flags, and
injects malicious sitecustomize/usercustomize/json/hashlib/types environment
modules; none may execute or shadow the fixed runtime. Previous b837 package and
Ubuntu396-pass receipts remain source-scoped history, not this corrected gate.
No VM/deployment/actual ledger/admin/reservation changes occurred. Hosted checks,
exact corrected package and refreshed review remain required.


## Shared named-lock identity correction

Independent root review found that a held descriptor alone did not prove the
named resource lock/root remained current and privately owned. The shared fix
from ece0b328 is included in standalone storage: pin the UID-owned0700 root and
single-link UID-owned0600 run.lock with owner/group/content metadata, reopen the
named root/lock and compare identities before and after flock, activation checks
and completion. Busy read-only inventory receives the same checks. Cleanup checks
again before operation intent creation, payload quarantine rename and unlink.
Replacement, hard-linking, owner/mode/content drift rejects; partial quarantine
and UNKNOWN receipts are preserved and no cumulative reservation is refunded.
No generic group/provider/model or retained16-policy source was imported from that
root change. Native-generic consumption remains fail-closed in this legacy worker.

Portable shared/storage104 PASS/16 Windows Linux skips and Ruff/mypy78 PASS are
local source evidence. Four additional real Linux inode/nofollow/flock races are
included in Ubuntu CI with the existing exact standalone fixture. Earlier15a
Ubuntu397-pass/zero-skip isolation result is retained as its source history.
The storage asset and runtime manifest pin change again; old bundle/native
receipts do not qualify this correction. No actual VM/deployment/result/ledger/
admin/reservation/simulation changes occurred. Exact source package, hosted
checks, final parent integration and refreshed review remain separate gates.


## Compatible lock contention correction

Fresh review4239919242 found that existing fixed phase launchers open run.lock
with O_TRUNC before their nonblocking flock. An unchanged empty file therefore
gets new mtime/ctime even when the competing launcher correctly fails to acquire
the held lock. The previous guard incorrectly denied that legitimate contention.

The guard now binds dev/inode/type/mode/link count/UID/GID/size plus SHA-256 of
at most4096 actual lock bytes, checking held and named descriptors and restoring
the read offset. Only lock mtime/ctime are excluded. Artifact fingerprints and
metadata protection remain unchanged. Same-size content changes, replacement,
permissions/ownership/link drift and oversized lock content still reject.
Timestamp-only changes at flock/activation/completion and between quarantine
rename/unlink complete normally; content-drift UNKNOWN preservation is retained.
A real Linux shell9> contender must fail flock while exact storage inventory
continues with all records unchanged. Windows emulation is not that Linux proof.
No VM/actual deployment/admin/ledger/reservation/simulation change occurred; final
parent integration, exact package, hosted checks and fresh review remain gates.


## Standalone stdlib path correction

Independent150 transitive-import review prompted the same boundary check for
storage. Exact direct-script fixtures reproduced unmanifested json/ctypes/hashlib/
subprocess modules beside the worker executing before its trust checks despite
-E -s -B. Both original failure logs are retained; the Windows newline assertion
was corrected before confirming the four actual startup-shadow failures.

Standalone/runtime storage now uses only builtin sys to remove the script startup
entry and empty/CWD entry before filesystem-backed imports, then removes all
canonical aliases before other stdlib imports and before retained helper execution.
Normal installed package
imports preserve the host application's paths. The launcher flags and supported
platform scope remain unchanged. Six exact direct packaged-script regressions
place unmanifested stdlib-named modules in the runtime directory and require clean
closed-dispatch denial without executing them; those portable startup checks do
not attest real Linux filesystem operations. Exact Linux standalone fixtures and
the changed bundle pin must be requalified. No VM/deployment/admin/ledger/result/
reservation/simulation changes occurred; full latest-parent/package/CI/review
gates remain pending and general release stays BLOCKED.

Local storage/fresh regression210 PASS/17 Windows platform skips; managed source/
script/test Ruff and mypy78 PASS. An accidental broad lint scan included historical
remote campaign code and reported its pre-existing735 findings; no historical code
was changed, and the configured CI lint scope was rerun successfully.
