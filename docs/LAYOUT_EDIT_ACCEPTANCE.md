# Layout edit acceptance

The first scenario inspects a registered source, forks an exclusive owned revision,
moves an instance and a shape, and adds a rectangle and a connected pin. It saves,
closes, reopens and compares the observed objects with the plan. A repeated apply
ID must add zero writes and zero objects. Selecting the preserved parent must
leave both revisions intact. The source fingerprint must remain unchanged.

An owned target accepts one first apply and is then sealed. A different operation
ID cannot edit that sealed target again. Further editing starts with another
exclusive fork from a preserved revision; it never reopens the original target
for an unrelated write. Same-ID replay returns `executed=false`.

`tests/fixtures/layout/scenario.json` is explicitly synthetic: 1000 DBU/um and a
5 DBU manufacturing grid. Its expected integer coordinates are independent test
oracles. An actual VM scenario must use the inspected technology and registered
layer-purpose pairs; these synthetic technology values are never VM defaults.

## Acceptance record

Record an exact integration commit and each actual command/tool invocation.
Keep private source data, local connection settings and raw OA files outside Git.

| Feature | Exact build | Environment | Command/tool | Before → after | Source preserved | Result | Limit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Independent edit oracle + rejection/receipt checks | C2 dependency `fcb42bb1589e59e02f42bde268bcc647b7fe64c2`; C4 implementation SHA recorded in role STATUS | Local synthetic | `python -m pytest tests/unit/test_layout_acceptance.py tests/integration/test_layout_edit_e2e.py -q` | Instance (1000,2000) → (1005,1990); shape (0,0)-(100,100) → (10,5)-(110,105); rectangle + pin match fixture | Logical fixture unchanged | PASS; actual receipt test NOT_RUN | No actual VM, package install or app claim |
| Inspect units/grid/LPP/objects | Pending | Actual VM, via C1 | `cadence_layout_inspect` | Pending observation | Pending | NOT_RUN | Registered layout required |
| Fork owned revision | Pending | Actual VM, via C1 | `cadence_layout_fork` | Source → exclusive child | Pending | NOT_RUN | No source overwrite |
| Plan move + rectangle + pin | Pending | Local + actual observed metadata | `cadence_layout_plan` | Explicit um → integer DBU | Pending | NOT_RUN | Supported edits only |
| Apply and reopen/diff | Pending | Actual VM, via C1 | `cadence_layout_apply`, `cadence_layout_diff` | Observed coordinates/counts/connectivity match plan | Pending | NOT_RUN | Must save, close and reopen |
| Same-ID replay | Pending | Actual VM, via C1 | Repeat identical apply | Zero additional dispatch/write/object | Pending | NOT_RUN | Restart replay included |
| Sealed target | Pending | Actual VM, via C1 | Different-ID apply on same target | Rejected, zero new writes | Pending | NOT_RUN | Further edit needs a new fork |
| Invalid unit/LPP/stale revision | Pending | Synthetic and actual path where available | Invalid plan/apply requests | Rejected before write | Pending | NOT_RUN | Include nonfinite/off-grid input |
| Partial failure | Pending | Fault-injected synthetic; actual only if observed | Interrupted apply | Failure/partial retained, no resend | Pending | NOT_RUN | Never induce destructive VM failure |
| Select earlier revision | Pending | Actual VM, via C1 | `cadence_layout_select` | Parent selected, child preserved | Pending | NOT_RUN | Selection, no destructive restore |
| Installed CLI/MCP | Pending | Installed package/SDK | `cadence-mcp-bridge layout … --request …` | Same typed request/result | Pending | NOT_RUN | SDK and desktop app tracked separately |
| Desktop app invocation | Pending | Actual app | Actual exposed tool | Pending | Pending | APP_NOT_TESTED | SDK result alone does not cover app |
| DRC / LVS / PEX | Pending | Tool/deck/license not established | None | None | N/A | NOT_RUN | No physical/manufacturing signoff |

## Verification order

During implementation run only affected scenario/unit tests and changed-file lint.
At C0's fixed integration SHA run the full suite, published contracts, security,
package/install and retained-state preservation checks once. Record initial
failures and any subsequent focused corrections. Existing platform-required CI
and review still apply. Do not rerun Spectre for layout editing evidence.

All VM requests go through C1's single writer queue. C4 never starts another
SSH/OCEAN writer. Unknown apply outcomes require read-only reconciliation and
retention of the original operation ID and failure artifacts.

## Read-only receipt checker

Run with the Python environment containing the exact integrated layout package:

```text
python scripts/verify-layout-edit.py --receipt <retained-private-receipt.json>
```

The JSON object contains `build_sha` (full 40-character commit), `environment`
(`synthetic_fixture` or `actual_vm`), `source_before`, `source_after`, `before`
(typed LayoutSnapshots), `request` (LayoutApplyRequest), `result` and `replay`
(LayoutResults), and `write_counts` with integer `before_apply`, `after_apply`,
`after_replay`. Actual-VM receipts additionally contain equal
`source_tree_before_sha256` and `source_tree_after_sha256` from C1's protected-tree
fingerprint checks. Retain original private commands, outcomes and counters.

The checker rebuilds the plan from the recorded baseline, recomputes the observed
diff and checks the recorded replay has no added writes. It reads at most 4 MiB
and never edits the input or contacts the VM. `RECEIPT_CONSISTENT` means the
supplied evidence agrees internally. It does not authenticate the source of
that evidence or complete fork, partial-failure, sealed-target, install or app
acceptance. Those retain separate rows and actual evidence references above.

For the read-only integration receipt test, C1 supplies the receipt path through
`CADENCE_LAYOUT_E2E_RECEIPT`. The receipt's exact build must equal the current
integration HEAD. Absence explicitly skips with `NOT_RUN`; a synthetic receipt
cannot pass this actual-VM evidence check.
