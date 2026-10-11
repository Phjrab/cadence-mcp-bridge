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
