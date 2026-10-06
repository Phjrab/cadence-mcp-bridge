# Reference Phase Margin applicability v1

ANALOG-PM-01 investigates a scientific loop before providing a Phase Margin.
It preserves the registered `analog-phase-margin` definition/hash and every
existing MCP schema. No additional MCP tool or unqualified extraction route is
needed for this checkpoint. The result is **UNQUALIFIED**, with no margin value.

## Actual reference boundary

The audit pins the admitted native AC input and its complete circuit bytes,
reusing the same reference source/PDK/effective-input guards. The observed
condition is NN /27 C /VDD1 V /effective320/702 mV, original saved300/650 mV
unchanged. Independent ideal sources drive the two differential inputs. In the
inspected explicit circuit boundary, both outputs occur only at MOS drains;
neither returns to an input or an explicit output-sensing common-mode network.
There is no registered application feedback loop or inserted stability probe.

Two diode-connected internal bias devices do not define an amplifier application
Phase Margin. MOS intrinsic reverse transfer, capacitive feedback and possible
model-internal loops are **not assessed** by this terminal-connectivity check.
This audit does not claim the circuit has no local feedback, is stable/unstable,
or meets an application requirement. The two-output boundary also cannot establish
PVT-wide stability. Existing output AC phase remains a transfer-function fact.

## Installed capability evidence

Read-only fixed `spectre -h` queries are made against the current installed
Spectre12.1. Vendor text stays private; no manual, example probe subcircuit,
netlist, PDK file or generated vendor artifact is copied into this repository.

| Topic | Observation | Meaning |
| --- | --- | --- |
| STB | HELP_DOCUMENTED_ONLY | Installed help describes DC linearization and return-ratio stability analysis; actual licensed execution has not run |
| iprobe | HELP_DOCUMENTED_ONLY | Installed help describes a current probe and its terminal-direction convention; no probe has been inserted |
| diffstbprobe | NOT_DOCUMENTED_BY_INSTALLED_HELP | This topic returns exit0 plus an unknown-topic warning; exit0 alone is not support evidence |

Installed STB help distinguishes loop-based and device-based methods. Its
loop-based method requires a suitable probe on the loop of interest with unchanged
circuit characteristics. Differential and common-mode loop tests require distinct
definitions and appropriate paired injection. The documentation includes an
alternative paired-injection approach, but this checkpoint neither copies its
source nor qualifies an implementation. A modern `diffstbprobe` recipe cannot
simply be assumed on this installation.

Device-based STB examines a particular active device; it does not automatically
measure the Phase Margin of the intended amplifier application. Applicability,
critical-device selection, nulling assumptions and passive-network conditions
would need separate proof. Selecting one of the fourteen MOS instances merely to
obtain a margin would not provide that proof.

## Fixed operator audit

```powershell
uv run python scripts/phase_margin_qualification.py inspect
```

This phase-only command needs the exact operator-owned policy and private user
delegation. A checked-out policy is not execution authority. It accepts only the
fixed `inspect` action, no path/script/expression/frequency/probe/loop input.
It verifies manifests and pinned source, takes the existing nonblocking EDA lock,
rejects active EDA workers, uses fixed bounded help commands, and rechecks protected
source/jobs/ledger before and after. No remote deployment, simulation, source/ADE
mutation, result deletion, reservation, counter refund or reset is implemented.

The versioned local assessment contains source/circuit hashes, opaque admitted
operation ID, bounded topology observations, installed-help statuses/hashes,
conditions, an explicit UNQUALIFIED/null result and preserved accounting. Raw
source/help are retained only in private audit receipts. Normal output contains
no private path or source/model text. Unknown statements/components, incomplete
boundaries, hash substitutions and changed baseline ledger are rejected. The
audited ledger identity64/7,383,023,616 is a temporal qualification baseline, not
a replacement accounting engine or a global permanent budget setting.

An exclusive durable intent precedes transport. Successful receipt and preserved
failure state cannot be overwritten or blindly retried. Future requalification
requires a new reviewed version; changing evidence to make this audit pass is
not permitted. This is operator qualification, not a runtime model registration
or a client-independent unrestricted execution interface.

## Existing MCP and specification behavior

Existing `cadence_describe_analog_measurement` and
`cadence_analog_measurement_result` still describe the original registered
Phase Margin contract and return UNQUALIFIED/null with
`qualified_loop_gain_measurement_unavailable`. The new audit's precise reason
is `no_defined_application_feedback_loop_in_reference_testbench`; it supplements
the original contract without silently changing its definition/hash or schema.
An UNQUALIFIED measurement cannot yield specification PASS/FAIL. No numerical
stability target is invented.

Current-source v8 SDK stdio checks confirm all76 tool schemas and the same
UNQUALIFIED result after restart. The actual connected Codex tool surface exposes
69 names: the reference analog list is empty and its Phase Margin description
returns invalid_input because that contract is not loaded. This is a real app
configuration checkpoint, not a PASS for current Phase Margin integration.
Global client configuration was not changed; runtime schema/version/lifecycle
qualification remains separate. Claude actual-app validation stays deferred.

## Future qualification path

1. Define the intended application feedback loop and its loading/closed-loop
   condition. A differential loop and a common-mode control loop are distinct.
   Creating a feedback fixture would change the present open-loop experiment;
   the present baseline cannot automatically qualify it.
2. In an approved owned copy, document a specific loop/probe location, orientation,
   sign and injection network supported by this installation. Preserve originals
   and old evidence. Verify DC operating point, source conditions, load and probe
   transparency against an otherwise identical closed-loop fixture.
3. Calibrate the loop-gain sign/phase convention with independent known-loop
   evidence. Do not obtain Phase Margin from ordinary output AC phase or choose
   a sign that makes the number look favorable.
4. Register a separate versioned stability analysis/reader and definition. Bind
   design/revision/probe/mode/analysis/conditions, effective inputs, raw-result and
   definition hashes, current shared admission/replay/ledger and bounded extraction.
5. Predefine unity-loop-gain crossing selection and all observed crossings, phase
   unwrapping convention, no-crossing/ambiguous/insufficient-data states and
   observed frequency range. Multiple-loop/crossing results need explicit limits;
   no unsupported extrapolation or whole-circuit stability guarantee.
6. Run only a justified finite campaign with bounded points/reservations/stop
   criteria, independently verify extraction and convergence, and expose a margin
   only within its proven scope. Licensed STB execution and scientific extraction
   remain NOT_RUN here.

See [phase result](ANALOG_PM_01_RESULT_V1.md). Independent slew-rate work may
proceed at its separately confirmed phase boundary; this loop blocker does not
justify inventing a measurement or blocking every other analog feature.
