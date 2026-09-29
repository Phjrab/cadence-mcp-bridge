# User Inputs Required

## Active post-v1 interpretation — DOC-INTENT-FACT-01

Use [Goals, facts, and execution approvals](interaction/GOALS_FACTS_AND_APPROVALS.md)
before treating any item below as a current user question. The older WP-09 through
WP-11 sections are historical contract records, not a new request to resubmit their
inputs or reopen those WPs. This overlay does not edit their decisions or authorize
execution.

| Category | Current responsibility | Example |
| --- | --- | --- |
| User design choice (`USER_INTENT`) | User decides the desired behavior, constraint, trade-off, or candidate when the active task needs it. | VBIASN 320 mV and VBIASP 702 mV are future candidates; VDD 1.0 V is a prior design constraint. Do not re-ask their values or units. |
| Agent investigation (`AGENT_DISCOVERY`) | Agent checks present values, connections, source/ADE revisions, hashes, and freshness through an already authorized fixed method. | Actual VDD, input VCM, output load, source/state equivalence. Do not ask the user to calculate hashes or identify raw OA names. |
| Execution approval (`OPERATOR_APPROVAL`) | User separately authorizes a concrete access or side effect when the existing contract requires it. | One bounded remote read, deployment, simulation, copy-based apply, or PR merge; an approval request alone grants nothing. |
| Environment/implementation dependency | Agent records a missing capability, expired observation, or unavailable resource and explains the smallest next step. | An undeployed read-only collector is `capability_missing`, not a missing voltage answer from the user. |

Keep candidate, observation, applied value, and validation separate. The 320/702 mV
candidate and VDD constraint are not observed current-file values or verified
performance. Historical 300/650 mV observations and 370/650 mV research remain
unchanged. Historical VCM 0.5 V and no-added-load assumptions are not promoted.
The WP-14 scientific baseline remains blocked while WP-15/WP-16 repository-only
progress is preserved. Unknown present conditions are investigation items, not
user omissions; never infer them or equate a local preflight with remote or circuit
validation. Future ADC, PLL, or layout specifications are asked only when their
later active task needs a genuine user design decision. Where an older section
says the user must supply a technical file identity, expression, or hash, first use
approved discovery; request only the remaining semantic choice or the minimal
separate access approval. Do not interpret this as authority for a new tool or run.

## WP-09 actual ADE profile — resolved

The user supplied and approved the WP-09 project-owned choices on 2026-08-28. The reviewed actual
profile is `actual-differential-amplifier-tb2-transient`:

- `MyDesignLib/Differential_Amplifier_TB2/schematic`, ADE L `state1`
- gpdk090 v4.6, model section `NN`, 27 degrees C
- transient stop `4m` (0.004 seconds)
- no caller-controlled design variables
- no requested ADE outputs or measurements

Read-only validation found two bias parameter assignments in the ADE-generated input. They are
fixed inside the reviewed remote profile for reproducibility and are not exposed as design-variable
inputs. No PDK content, OA database, netlist, waveform, credential, or license value is committed or
returned through MCP. There are currently no outstanding WP-09 user inputs.

## WP-10 actual ADC measurement contract — required before execution

WP-10 validates only the non-proprietary `adc-synthetic-v1` fixture. No actual ADC circuit or
measurement definition has been supplied, so no actual-circuit measurement was attempted. Before
one can be added, the user must provide and approve:

- exact library/cell/view and reviewed simulation profile/state;
- supply voltage and the signed current expression used for DC power;
- offset output expression, reference value, and averaging interval;
- settling output expression, target, tolerance, start, and stay-within-band policy;
- sample frequency, input tone, sample count, analysis window, transient exclusion, window
  function, DC/fundamental/harmonic/noise-bin policies, differential signal expression, and ENOB
  equation;
- ADC bit count, input range, transition extraction method, and DNL/INL reference method;
- corner names/reference and the metric to compare;
- Monte Carlo sample population, standard-deviation/percentile policy, and acceptance limits;
- required units, numeric tolerances, and pass/fail limits for every metric.

These inputs must form a new versioned, reviewed contract. None will be inferred from the synthetic
fixture or from the existing differential-amplifier ADE profile.

## WP-11 controlled design write — validation resolved

The user supplied the complete fixed write contract and actual-apply approval on 2026-08-28.
`MCP_WorkLib` was created and registered, and the approved source copy was created at
`MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic`. Validation then failed before dry-run
completion because of a legacy IC6.1.5 property-query API mismatch. The approved property was not
applied, and no backup or rollback stage ran.

V1/V2/V3 attempts and recovery evidence remain preserved. The user subsequently approved immutable
V4 plan SHA-256 `c5b2f418c5a76bfe54adc24c2ee947a33d904122b404bba323706dfbe3cbdd66` and one fixed execution.
Run `e636eeba-80dc-4280-b2ea-4f23b0cd1139` passed all 18 criteria, restored the V4 target from its
fixed backup, and proved Source, PDK, and all prior evidence unchanged. No controlled-write domain
input remains outstanding.

The remaining user decision is repository/release authorization: review the
`wp/WP-11-v1-release` release-preparation branch, explicitly authorize its PR merge when satisfied,
and then separately authorize creation of the annotated `v1.0.0` tag and private GitHub release.
No tag or release has been created.
