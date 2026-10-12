# Operator provisioning lifetime lock

PR149 review thread PRRT_kwDOUGi5886rVcWE identified a
post-acquisition namespace gap. A detached held lock could coexist with an
independently lockable replacement while lifecycle writes followed the new path.
The review thread is the finding identifier.

The acquired integer descriptor now retains the exact directory ancestor chain
and bounded lock identity/content. Lifecycle operations recheck held and named
lock/ancestors before writes, publication/replacement and completion, including
retained-record durability recovery. Shared lock timestamps are excluded because
existing shell contenders update them; device/inode/type/mode/owner/group/link
count/size/content stay bound. Uncertain partial publications remain evidence.
This is a last-observation guard, not atomic exclusion of external filesystem tools.

Twelve owned POSIX cases detach lock or managed root after acquisition or final
publication across activation, deactivation and update. Replacement flock must
succeed independently, then the operation must reject without reporting success.
Acquisition cases publish no new active/revocation/transition state; final update
cases retain partial state without a completion receipt. A separate owned test
accepts timestamp-only changes and rejects same-size content drift. Windows skips
these native filesystem cases; exact hosted Linux results are required.

No actual VM metadata, ledger, grant, reservation or simulation changes are made
by this source correction. Normal feature integration and exact package/native
qualification remain separate gates. Original data and prior failures are retained.
