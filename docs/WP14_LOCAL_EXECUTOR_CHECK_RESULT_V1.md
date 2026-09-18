# WP-14 local executor check result v1

## Fixed inputs and time gate

- PR #42 merge commit and latest `origin/main`:
  `8e10143c4bbb0ca74e6af803568ca24c0af0a512`
- Checker: `scripts/verify-wp14-executor.ps1`
- Checker normalized-LF SHA-256:
  `39cc05f53097f3d8847e473200f140e9e9f283eddd04f194f5e7e69c96bfe975`
- Execution time: `2026-09-18T04:46:35.4834645Z`
- Evidence boundary: `2026-09-18T08:05:01Z`
- Time decision: `within_validity=true`

The repository was PUBLIC and `deployment_enabled=false` before the run. The
working tree was clean and a dedicated result branch was created from the exact
merge commit before invoking the checker.

## Single execution result

The fixed no-argument checker was invoked exactly once. Its closed result was:

```json
{"success":true,"code":"LOCAL_RULE_READY"}
```

The checker exit code was zero. It read the Windows SID and MachineGuid twice,
validated stable supported shapes, and calculated the fixed binding rule in
memory. It emitted neither identity input nor binding value, and it did not
persist them. No retry was performed.

An outer operator wrapper tried to capture the checker's console-direct line as
a PowerShell pipeline object and therefore emitted a post-execution cardinality
error after the checker had already returned the single valid line and exit zero.
This was an orchestration observation, not a checker failure. The checker was not
invoked again.

## Meaning and exclusions

`LOCAL_RULE_READY` proves only that, at the execution instant, the local inputs
were stable, supported, and yielded a computable digest under the fixed rule. It
does not expose or save the digest, compare any Authorization, establish current
remote preflight, renew evidence, authorize deployment, or approve a scientific
baseline.

No Authorization, executor-binding record, claim or lock was created. The
recovery deployer was not executed or dot-sourced. No SSH/SCP, remote collection,
preflight, deployment, Cadence/SKILL/discovery/simulation, OA/ADE/design/PDK
change, direct-main push, merge, or WP-15 work occurred. Existing evidence and
consumed claims remain unchanged.

## Acceptance result

1. Exact PR #42 merge and latest main: PASS.
2. Checker normalized-LF hash: PASS.
3. Execution before the evidence boundary: PASS.
4. Exactly one checker invocation and no retry: PASS.
5. Closed success/code result and exit zero: PASS.
6. Raw identity and binding absent from output and repository records: PASS.
7. No Authorization, claim, lock, deployer or remote action: PASS.
8. PUBLIC and `deployment_enabled=false` preserved: PASS.
9. WP-14 only; WP-15 unstarted: PASS.

## Repository validation

`git diff --check`, Ruff, strict mypy for 17 source files, the 367-file secret
preflight, 18 dedicated security tests and the strict locked dependency audit
passed. No known dependency vulnerability was reported.

The first full-suite run in the live checkout reported two inactive-contract
failures because the previously consumed, untracked and ignored deployment
Authorization remains present. The file was preserved without modification as
required. A clean temporary copy of the same tracked tree plus this documentation
change, excluding that live Authorization, passed 384 tests; eight real integration
tests were deliberately skipped and 56 existing deprecation warnings remained.
The temporary copy was removed after the run. The production checker was not
invoked during either test run.

## Next boundary

This result requires review and integration before later WP-14 work. The evidence
clock remains immutable. At or after `2026-09-18T08:05:01Z`, do not create or
prepare a recovery Authorization from the existing evidence; preserve its
timestamp, hashes and consumed claims and prepare only a versioned fail-closed
evidence-renewal plan.
