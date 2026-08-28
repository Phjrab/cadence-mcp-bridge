# ADC Measurement Contracts

## Contract registry

WP-10 exposes one closed, versioned contract: `adc-synthetic-v1`, version `1`. It is classified
as a non-proprietary fixture and is not an authorization to measure a user circuit. Every
measurement request must name this exact contract; a missing or unknown contract is rejected.
Inputs are finite, bounded arrays with at most 4,096 values (exactly 1,024 for FFT and seven ADC
transitions for linearity).

Every structured result includes the contract ID and version, units, formulas, and a measurement
manifest. The manifest records contract version `1`, the `windows-python` post-processor, and a
SHA-256 hash of the canonical validated input. Repeating the same request therefore produces the
same metrics and input hash without storing or returning a waveform file.

## Fixed definitions

| Metric | Unit | Definition |
| --- | --- | --- |
| DC power | W | `mean(v_supply[n] * i_supply_into_circuit[n])`; positive current means current entering the circuit |
| Offset | V | `mean(v_observed[n] - 0 V)` |
| Settling time | s | earliest `t >= 0 s` after which every remaining sample satisfies `abs(v(t) - 1 V) <= 0.01 V`; returns unsettled with no numeric value if none exists |
| SNR | dB | `10*log10(Pfundamental/Pnoise)` |
| SNDR | dB | `10*log10(Pfundamental/(Pnoise+Pharmonics))` |
| THD | dB | `10*log10(Pharmonics/Pfundamental)` |
| ENOB | bit | `(SNDR_dB - 1.76) / 6.02` |
| DNL | LSB | `code_width/ideal_LSB - 1` |
| INL | LSB | `(transition[k] - ideal_transition[k]) / ideal_LSB` |
| Corner comparison | caller unit | value and percent delta from the fixed `NN` reference; minimum, maximum, and largest absolute delta corner are returned |
| Monte Carlo summary | caller unit | count, mean, sample standard deviation (`n-1`), min/max, median, and linearly interpolated p05/p95 |

The numeric test tolerance is `1e-9`. The fixture ADC is three-bit, spans 0 V through 1 V, and
uses endpoint linearity. Its required corner set is exactly `NN`, `FF`, and `SS`.

## FFT contract

All FFT choices are fixed rather than inferred:

- sample frequency: `1024 Hz`
- coherent input tone: `64 Hz`
- sample count: `1024`
- analysis time window: `0 s` through `0.9990234375 s`
- initial transient exclusion: `0` samples
- window: rectangular
- DC: bin 0 excluded
- fundamental: exact coherent bin 64
- harmonics: four integer multiples (2nd through 5th), folded at Nyquist and de-duplicated
- noise: positive-frequency bins from 1 through Nyquist, excluding the fundamental and harmonic bins
- differential signal expression: `fixture:adc_output`
- ENOB equation: `(SNDR_dB - 1.76) / 6.02`

The request is rejected if the samples do not contain nonzero fundamental, harmonic, and noise
power. This avoids undefined logarithms and prevents the processor from silently inventing a
floor or alternate bin policy.

## Post-processing decision

Versioned Windows Python post-processing is used instead of OCEAN for this contract. It is more
reproducible here because the algorithm, schemas, bounds, formulas, and synthetic vectors run in
the locked local test environment and do not depend on legacy OCEAN functions or a proprietary
PSF reader. The implementation uses a deterministic radix-2 FFT and Python standard-library
statistics. OCEAN remains outside the public command surface, and no raw PSF, netlist, model,
path, or arbitrary expression crosses MCP.

## Actual-circuit boundary

No actual ADC measurement is defined or executed by WP-10. A future actual contract requires the
user to supply and approve the exact circuit/profile, supply voltage and signed current expression,
offset nodes/reference, settling target and tolerance, every FFT choice listed above, ADC bits and
input range, transition extraction method, corner set/reference, Monte Carlo population and
summary policy, and result acceptance limits. These values must become a separately reviewed
versioned contract; they must not be copied from the synthetic fixture as defaults.
