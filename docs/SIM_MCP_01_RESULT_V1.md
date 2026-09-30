# SIM-MCP-01 — fixed work-copy diagnostics through MCP

Date: 2026-09-30. Outcome: `MCP_DC_AC_E2E_VERIFIED_SPEC_NOT_EVALUATED`.

Four typed tools expose the pinned WP14 work-copy DC and AC diagnostics. An
actual MCP client listed the 26-tool registry, submitted both jobs, polled their
status, and read bounded scalar and spectrum results. The original 22 tool
contracts remained present. Both new results had valid simulator and extraction
states and matched preserved same-condition operator observations within the
versioned verification tolerances. These are diagnostic comparisons, not a
design-specification PASS.

The request contract permits only the reviewed work-copy revision, candidate
operating point, DC/AC analyses, and matching logical outputs. It accepts no raw
path, netlist, expression, SKILL, OCEAN, sweep, source write, or PDK input. The
remote helper checks the protected source, ADE state, model and copy fingerprints
and the fixed job-local binding before and after execution. The legacy actual
transient profile retains its prior contract.

The first immutable helper version exposed a preparation-stage defect. Its job
failed before Spectre, consumed no simulation attempt, and remains preserved in
the managed private job history. The corrected second version passed deployment
hash and Python 2.6 checks and completed the DC/AC MCP run. The cumulative
Spectre counter advanced from 9 to 11 of 100. The new result budget reserves
128 MiB per attempt plus a conservative 1 MiB for prior managed results; the
managed disk floor was satisfied after both runs. There was no active EDA job at
postflight.

Raw observations, job IDs, fingerprints, and comparison calculations remain in
the ignored private report `.codex/sim-mcp-v2-e2e-private.json` and the managed
VM job directories. The report digest is
`9264ab94e673e334554db8dd8eca1794728e5ea6dd06e2a847c85f65439f9f05`.
No raw circuit data, PSF, netlist, PDK file, or private job path is published
here.

The local Codex project entry was backed up and pointed to the verified checkout.
The platform's automatic approval review rejected a persistent auto-approval
override for the new simulation submit tool. The installed entry therefore
retains prompt approval for side-effecting MCP tools. This platform approval
boundary is separate from the project's phase delegation.

Original OA/ADE candidate application, historical source equivalence, numeric
specification evaluation, load behavior outside the pinned copy, and physical
signoff remain unverified. `SWEEP-MCP-01` is a possible next phase only after a
separate user choice; it was not entered here.
