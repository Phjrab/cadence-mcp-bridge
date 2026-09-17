# WP-14 public contract reconciliation v1

Date: 2026-09-17
Scope: repository-only implementation and isolated tests; no execution authority.
Base: PR #32 merge c949815bac26e893bad7ad77694905a74d83fd57, PUBLIC.

## Policy and version migration

The user's public policy is already approved. Root and current-phase overlays make it
current without rewriting historical WP-00 through WP-11 requirements or release evidence.
The three request packages now have version-2 successors with immutable version-1
supersedes paths and normalized-LF hashes. All authority flags remain false.
Private local files and private discovery streams are unrelated and remain unchanged.

Hash dependency order is deployment package v2 -> narrow deployer -> collection package
v2 -> collector -> single-use request v2. There is no self-hash dependency. The previous
package hashes and all eleven asset bytes, modes, bound plans and evidence are preserved.
Only repository executors change; no remote runner or MCP surface changes.

The collector deliberately retains PACKAGE_BASE_MAIN_COMMIT 59a450c63b040a604e644638ef6e02b0a9544d09
and REPOSITORY_MAIN_COMMIT e60ab270a5e002256f8c5bbf6b81e54f65c10a31 as historical design bindings.
They do not claim to be current main. The new public_policy.migration_base_main records PR #32.
Inherited PR #22/#26/#29 fields and prerequisite sequences remain historical provenance;
the new version and executors need review/integration, not another implementation grant.
Request proposed-contract ready/implemented flags remain non-activation declarations, not
a denial of this repository implementation. PROJECT_STATE records current implementation.

## Single-use continuity

Current normalized-LF SHA-256 bindings:

| Artifact | SHA-256 |
| --- | --- |
| Deployment request v2 | 96d8f001776eb61da5ef09ba3945d988bf587c716fea95a35ad890aa95ba2431 |
| Narrow deployer | 3251100bafde66c0df4179d36462de8029c6856b59111629dba627c1b668fddc |
| Collection request v2 | 7b8d4d623a95e67a6d39e0391bcf5b9869c58dedbf02b0dd638c070853048223 |
| Collector | b0bbcd9823e561805c1979b9e1eca3b79f96a4d0126e9c8aa32fe1db0427cc7c |
| Single-use request v2 | 9b1ed3e2fc4a9ba5c05e5475bca51949a6eba0cbdcbbd47d3c54f549d576bd0f |

Both executors retain the original machine/operator-local ledger directory, operation lock
and original v1 attempt filename. The stored claim identifies the current package/runner hash,
but its durable filename stays bound to the predecessor package hash. Thus a consumed,
failed, empty or uncertain predecessor claim blocks the successor, and a successor claim
also blocks the old executor. No claim is deleted, migrated, overwritten or repaired.
New package hashes and authorization IDs cannot reset one-use eligibility.
No real operator ledger is touched during this run; tests rewrite paths in temporary copies.
The deployer also retains its original fixed snapshot and temporary destination names;
changing policy does not authorize reuse or fallback if these already exist.

## Publication and operation boundaries

Public visibility does not authorize publication of fresh evidence. Only reviewed source,
synthetic fixtures and sanitized documentation are committed. Active authorization, executor
identity/MachineGuid, credentials, licenses, PDK/OA/ADE content, netlists, raw output and
unrestricted logs remain excluded. Future exact closed evidence fields require local review
before publication. The collector rejects extra fields/content and suppresses failed output.
It does not query GitHub: repository visibility verification remains an operator prerequisite,
while runtime checks bind the exact reviewed package and its public-policy repository identity.

Remote collection still requires a new separate package/collector/executor/time-bound grant.
Old grants cannot match the new hashes. No authorization was created here. Deployment V2
authority, remote preflight/deployment and discovery remain separate later gates.
deployment_enabled=false is preserved; current remote identity/preimages and scientific
baseline remain unverified. VDD/VCM/load assumptions are not promoted to measurements.

## Acceptance and verification

1. Exact PR #32/main and PUBLIC repository verified before feature creation.
2. Three immutable v1 package hashes preserved, v2 requests have no authority.
3. Root/current phase public policy overlays preserve all other restrictions and history.
4. Eleven assets, both plans, operation schemas, time/output bounds and no-retry unchanged.
5. Complete acyclic hash binding and deliberately retained historical commit checked.
6. Old package authority, tampered input and protected extra output fail closed.
7. Success, timeout, flooding, concurrency and durable predecessor consumption use only fakes.
8. No real authorization, ledger, SSH/SCP, remote collection, deployment or Cadence operation.
9. Local static/full/security/document checks must pass before feature commit/push.
10. Remote feature SHA verification ends this run without merge or WP-15.

Validation: Ruff and strict mypy (17 files) passed. The full local suite passed 340 tests
with three real integrations skipped, five deselected and 56 existing warnings. A separate
52-test collector/contract run passed, including the four new migration-contract checks.
All 18 dedicated security tests, 349-file secret preflight and strict dependency audit passed.
Initial fixture references to v1 packages failed locally and were corrected before these
successful reruns. No real transport was used. All prior history and protected inputs match.
Final hashes are recorded above and in PROJECT_STATE; remote feature SHA is reported after push.
This repository reconciliation is not proof of live VM readiness or scientific correctness.
