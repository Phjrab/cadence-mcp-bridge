# Controlled Design Write Policy

## Current status

WP-11 design writes are **blocked after an incomplete real validation**. The user approved the
dedicated `MCP_WorkLib` library, the exact source and destination, and the sole string property
mutation. The bridge now exposes one read-only plan tool and one confirmation-gated validation
tool, for a total of twenty-two public tools.

The real run created the approved destination copy
`MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic`, then stopped before dry-run completion
because IC6.1.5 does not provide the attempted `dbFindPropByName` helper. No property apply,
backup, rollback, tag, or release occurred. The implementation now performs the lookup by walking
the cellview property list, but the approved contract says an existing destination must never be
overwritten. Consequently the runner reports `ready=false` and no second execution is permitted
without a new explicit disposition for the incomplete destination.

## Permanent protections

- PDK libraries, including `gpdk090`, are permanently read-only.
- shared Cadence libraries such as `analogLib` and `basic` are permanently read-only.
- reviewed source libraries `MyDesignLib` and `MyFirstDesign` remain read-only.
- the original cellview and ADE state must never be modified.
- arbitrary paths, file contents, SKILL/OCEAN text, and generic shell/SSH commands remain forbidden.

`write_policy.py` classifies the known protected and source library names, designates only
`MCP_WorkLib` as eligible, and lists only
`set_cellview_property:mcpMutationTest=validated-v1`. The remote plan independently checks that
the fixed source exists and the fixed target does not exist. The execution tool additionally
requires the exact `APPROVE_MCP_WRITE_VALIDATED_V1` confirmation.

## Required decision before resuming WP-11

The approved destination now exists, so the current policy correctly blocks another run. A future
run needs a new explicit user decision that names one safe disposition, such as authorizing removal
of this incomplete copy before recreating it or approving a new destination cell name. The bridge
must not infer that permission. PDK, source, and unrelated library writes remain prohibited.

## Release gate

`v1.0.0` must not be created until a real approved copy has passed dry-run/apply equivalence,
backup restore, all local/security/integration tests, install/uninstall verification, and design
source/PDK immutability checks. Because the required sequence did not complete, no tag or GitHub
release may be created from this checkpoint.
