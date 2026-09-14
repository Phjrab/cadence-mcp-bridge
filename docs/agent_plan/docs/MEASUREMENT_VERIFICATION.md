# ADE·Sweep·측정·수치 검증 설계

## 1. 기능 검증 순서

읽기 가능한 profile → exact source/state/include graph → parameter binding → effective value → precision result extraction → metric reference → small campaign → recovery → 고급 optimization.

state-driven batch 및 live GUI capability는 snapshot mode와 분리한다. `state1` 이름만 기록한 wrapper를 ADE가 state를 직접 load한 결과라고 부르지 않는다.

## 2. 데이터 경로

```text
PSF 원본(보호 로컬)
 ├─ precision read/sampling/complex data → metric + validity + provenance
 └─ display downsampling → bounded preview + truncation/sample policy
```

4096개 등 preview sample cap은 표시 정책 예시다. 필요한 FFT/settling/glitch 데이터 정밀도를 그 cap으로 잘라서는 안 된다. precise extraction에는 별도의 resource budget이 필요하다.

## 3. DCOP

허용 device만 Id/gm/gds/VGS/VDS/VBS/VDSAT/region과 operating constraints를 추출한다. PMOS sign convention·body connection·model validity를 명시한다. `region=2`와 어느 한 sat-margin은 특정 조건의 정보일 뿐 전체 PVT/입력 범위 통과 증거가 아니다.

Saturation margin의 식과 부호는 모델·소자 극성에 맞춰 정의하고 VDSAT 절댓값 비교 같은 간편식을 모든 소자에 무조건 적용하지 않는다.

## 4. 차동 AC와 안정도

정의 가능한 경우:

`A_d(f) = [Voutp(f)-Voutn(f)] / [Vinp(f)-Vinn(f)]`

Stimulus의 각 input magnitude/phase와 differential normalization을 기록한다. single-ended output에는 다른 contract를 쓴다. CMRR/PSRR는 별도 stimulus와 같은 operating point·load 조건에 결부한다.

PM/GM은 정확한 loop/probe/closure/feedback/load에 대한 loop gain으로 계산한다. no crossing, multiple crossings, common-mode feedback loop 미정의는 유효성 상태로 반환한다. open-loop forward AC phase를 곧바로 phase margin으로 쓰지 않는다.

Noise는 input/output referred·band·integrated/spot·PSD 단위·필터/alias 조건을 명시한다. 미지원 device noise를 0으로 채우지 않는다.

## 5. Transient와 전력

Startup/power ramp/reset/valid interval·load/input amplitude·settling band/final reference·stay-within·slew 구간·glitch 감지 sampling을 지정한다.

비균일 sample에서는 시간 가중/적분 기준을 사용한다.

`P_avg = integral(V(t) * I(t), t0, t1) / (t1 - t0)`

전류 부호와 공급원/바이어스원 포함 범위를 고정한다. startup을 제외했으면 별도 startup metric이 필요한지 spec에서 결정한다. spec failure를 지우기 위해 exclusion window를 agent가 늘리지 않는다.

## 6. FFT·ADC

N, fs, tone frequency, coherent sampling 여부, uniform grid, strobe/보간 방법, window·ENBW·bin policy·DC/fundamental/harmonics·folding·aliasing·startup exclusion·code encoding/full-scale/latency/data-valid를 contract로 관리한다.

Spectre 12.1의 strobe 등 옵션은 actual help/fixture로 확인한다. maxstep만으로 정확한 uniform FFT sample grid를 보장했다고 하지 않는다. synthetic ADC fixture는 independent oracle 테스트에 사용하고 실제 ADC의 측정 조건으로 자동 승격하지 않는다.

SNR/SNDR/ENOB/DNL/INL 계산식은 적용 조건과 함께 고정한다. ENOB 표준 sine/full-scale 관계 적용 가능성을 확인하고, 임의 신호의 값을 ADC ENOB로 과장하지 않는다.

## 7. Sweep 의미

- independent campaign: 각 child가 독립 초기화.
- simulator-native sweep: 이전 해 상속 등 solver state 정책을 확인.
- transient sequence: 실제 시간 연속적 stimulus.

warm/cold start, forward/reverse order, hysteresis, initial conditions, endpoint 포함/step direction, duplicate point 처리, explicit ordered decimal values를 기록한다. native result family의 축 순서/metadata는 확인 없이 추측하지 않는다.

## 8. 범위와 budgets

초기 concurrency=1 유지. 3-point actual benchmark를 먼저 검증한다. 11/21/49 points나 최대 2-stage는 과거 제안 예시이며 승인된 production cap이 아니다. template의 상한은 `null`로 두고 operator policy를 요구한다.

전체 child/attempt/wall time/queue wait/storage/license/model usage를 집계한다. failed point도 사용 budget으로 계산한다. retry/resume/cached result를 구분하고 timeout 이후 duplicate apply를 막는다.

## 9. Monte Carlo와 robust validation

Process/mismatch/RC corner는 별도 모델 지원과 identity가 필요하다. seed/run count만 지정해서 actual foundry mismatch가 생긴다고 하지 않는다. 통계 모델이 없으면 hypothetical perturbation experiment로 labeling한다.

표본수, success definition, confidence interval·missed failures·independent seeds·PRNG/tool/model versions를 기록한다. optimizer가 보지 않은 holdout으로 frozen candidate를 검증한다. 예를 들어 독립 200회 모두 통과는 확정 100% yield 증거가 아니다.

## 10. 수치 허용오차

각 metric마다 absolute/relative tolerance·solver refinement·frequency/time grid 조건을 사전에 정한다. 나중 결과에 맞게 tolerance를 바꾸지 않는다. 다른 tool/OS/serialization의 result bytes가 항상 같다는 전제도 금지한다.

Reproducibility 층:
1. request/plan/model/deck/executor identity는 digest.
2. circuit/topology는 semantic comparison.
3. numeric metrics는 선언한 tolerance.
4. stochastic campaigns는 seed/모델·분포·통계적 범위.

## 11. 첫 강력한 성공 기준

M1은 단순 세 job 성공이 아니다. approved variable의 actual effective values가 각각 맞고, 유효한 metric을 추출하여 기준과 비교하고, restart/cancel/idempotency/source 불변을 동일 campaign에서 증명해야 한다.

이후 optimizer를 붙여도 evaluator는 독립적으로 유지한다. 유효한 결과지만 spec fail이면 설계 탐색 실패점이며 시스템 장애가 아니다.
