# Final repair-target observation, 2026-10-12

Independent PR148 finding4244590385 exposed target content/ACL observations that
preceded potentially lengthy trailing library-link and membership checks. Changing
an existing file during those checks need not change directory membership, so
the prior captured hash could incorrectly be accepted at completion.

The fixed inventory retains held/named target metadata including ctime and lexical
ancestors, rechecks each complete content/ACL record after all membership scans,
then verifies the complete target and directory metadata unions. No content/name
scan follows those final metadata guards. Restored mtime, mode changes, same-byte
inode replacement and earlier-file changes during a later content scan reject.
This is a last-observation guard, not atomic exclusion of external filesystem tools.
Existing plan schema, exact mutation scope and explicit rollback remain unchanged.

Windows related repair tests90 PASS/258 actual Linux skips; Ruff PASS. Eight new
owned Linux apply/rollback cases are included in hosted CI and need exact-head
Linux evidence. Current installed helper/source952c39c is historical and does not
contain this correction; new installed/VM/review qualification remains required.
No reviewed candidate, new simulator job or release publication is claimed.

During the separately delegated VM repair, the earlier fixed installed helper call
timed out. Read-only exact state and independent full metadata comparisons observed
all233 planned0777-to0755 changes and0 remaining;509 file hashes, owner/group,
identities, links and xattrs stayed unchanged. Intentional mode/ctime differences
are recorded, and root receipts/failed evidence remain. Its final response was not
observed, so current-helper repeat/preflight remains required. Existing ledger
was read under its original lock/audit:102 attempts/12,483,297,280 reserved bytes,
16GiB ceiling,4,696,571,904 remaining. No new simulation or reservation occurred.

The user withdrew stop-after-test-failure; preserve failures and continue corrections
inside existing GREL02-08/minimum administrator/conditional normal merge authority.
Final exact-candidate public approval,500 attempts and same-change20 remain.
