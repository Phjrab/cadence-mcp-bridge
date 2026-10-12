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

## Exact file durability on resumed publication

Independent review findings4244941346 and4244941354 identify complete bytes left
after a failed file fsync. Activation and update now reopen every runtime asset
and manifest without following links, bind held/named identity, content and
metadata, fsync the same inode and revalidate before directory barriers. Initial
activation also repeats this file barrier for an exact retained launcher before
publishing the pointer. Existing transition/pending/completion recovery uses the
same checked file barrier. No retained file is rewritten or replaced for fsync.

Twelve portable action/asset failures retry twice without state advancement;
launcher first-write and two retained retries preserve the same inode and deny
pointer publication. Content drift rejects; actual open-file replacement and
permission drift require POSIX. Python3.12 Windows stat/fstat have different
ctime semantics, so synthetic Windows checks retain named ctime separately;
native POSIX checks bind both held and named ctime. Atime is excluded because
the verification itself reads the file. Earlier failing Windows text-mode,
metadata and test-injection harness outcomes are retained as private evidence.

Current Windows bootstrap112 PASS/30 platform skips, Ruff PASS. Exact hosted
Linux/package/security and refreshed independent review remain required. These
source tests do not assert actual VM or final native candidate qualification.
