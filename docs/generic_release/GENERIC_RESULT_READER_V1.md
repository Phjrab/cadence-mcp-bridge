# Generic bounded result reader

The package supplies an operator-only fixed reader compiler and mathematical
frame projector, not a native dispatch/provider or qualified measurement service.
It reuses immutable runtime routing and generic ADE input binding, the existing
logical measurement allowlist and shared signed-power arithmetic. Historical
registered readers,85 MCP schemas, source IDs and exact reference math remain
unchanged. A new circuit changes its reviewed bindings, not Python source.

Reader registration binds exact design/analysis/measurement IDs and canonical ADE
registration SHA256 plus the canonical analysis-specific measurement contract
SHA256 from the existing registry v4 or later. An allowlist membership alone is
insufficient: missing contracts, another analysis or stale contract digest reject.
The registered contract must remain unqualified; this compiler cannot replace a
qualified fixed historical reader/definition. Local generic preparation does not
change that contract's execution qualification. Its node selectors are canonical ASCII private names; current
selectors require a positive-terminal /INSTANCE/PLUS suffix. Voltage and current
selector sets must be disjoint; nodes ending PLUS or MINUS are refused as an
ambiguous branch-current spelling, including legitimate same-named hierarchy nodes
until a native quantity inventory can distinguish them. Actual PSF units still
need provider attestation; string syntax alone cannot prove physical quantity. Ground is explicit
null. Sources bind logical positive/negative node IDs, role and signed convention.
No source-voltage constants are inferred from another circuit. DC power sums
-Vterminal * Isigned, retains absorption and reports supply/bias/stimulus/all
registered source boundaries separately. This is not inferred DUT-only power;
complete source inventory, orientation and effective topology need native attestation.

AC transfer binds positive/negative input/output logical nodes and explicit gain
frequencies within the compiled interval. Requested frequency count cannot exceed
the registered waveform sample limit, and frequencies must remain distinct in
the binary-float representation used by projection. Matching tolerance cannot
reuse one saved sample for multiple requested frequencies. All registered waves must share an
increasing exact saved frequency axis. Each requested frequency must match one
actual sample (relative tolerance1e-12); there is no interpolation. Division uses
the measured complex differential input; zero input rejects. Zero output has
null dB and phase. No universal10Hz/DC gain, bandwidth or phase-margin claim.

TRAN uses all registered saved samples from0 to the compiled stop (relative
endpoint tolerance1e-12), identical strictly increasing axes and real values.
It reports min/max/first/last and time-weighted trapezoidal mean. The actual saved
step extrema and sample count describe resolution. This does not prove solver
maxstep, continuous extrema, settling, slew or missing between-sample behavior.
An unsupported larger waveform rejects; no silent truncation/resampling/window
selection.2–256 samples per node,1–8 nodes,1–16 gain frequencies and262144-byte
frames and1536 aggregate sample rows bound the initial reader. Numerical text uses the existing finite decimal
bounds. All required signals/current rows and END must be present exactly once,
in compiled order, with explicit contiguous indices. Extra data/errors reject.

Each frame header binds UUID4, exact immutable plan, execution_input_sha256 and
canonical reader registration. Script/registration/frame hashes identify bytes,
not origin, human approval or PSF provenance. The local projector always returns
BOUNDED_FRAME_VALIDATED_NATIVE_UNATTESTED and NOT_ATTESTED provenance. A production
provider must verify the actual runner, effective input, protected originals,
owned PSF/save inventory/selector, worker status and terminal extraction receipt
and exclusively provision a fresh job-owned frame output before running the script
before using this projector to produce native facts. The extraction script writes
only the same registered job's work/generic-frame.txt and reads work/psf; no
remote command, deployment or provider wiring is added here.

Installed CLI workflow and schema/help are included in README package metadata.
Compile artifacts are exclusive/private; old or partial files are retained.
Local plan/reader preparation creates no journal, grant, counter or EDA lock.
Frame projection stays available as local validation without reviving an expired
execution grant. It does not register a fact, evaluate a specification or add a
manual developer receipt to the actual service. Automatic terminal extraction,
extraction-only recovery, generic1D Sweep codec/SweepStore/Supervisor integration
and actual clean-client native results remain required for GREL05/06 completion.

Verification uses analytical disposable DC/AC/TRAN frames and hostile input tests,
including non-unit stimulus, complex/zero transfer, signed source absorption,
nonuniform saved time resolution, stale identities, missing samples/signals,
malformed numbers/selectors, unsupported analysis inventories and exclusive
compile outputs. Installed-wheel CLI compile/projection is distinct from native
OCEAN API qualification. No actual PSF/native result was fabricated or executed.
