# 테스트·benchmark·완료 판정

## 1. 관측하지 않은 성공은 없다

Process return 0, file 존재, MCP 응답 성공, unit tests, actual spec pass, fabrication readiness는 서로 다르다. 각 수락 기준은 evidence ID·입력 identity·판정·미실행 이유를 가진다.

## 2. 공통 테스트 층

| 층 | 검사 | 예시 |
|---|---|---|
| T0 | 문서/ID/참조/계약 | 중복 WP·missing dependency·예전 approval replay 차단 |
| T1 | pure schema·units·numeric | NaN/Inf·단위 변환·point count·analytic RC |
| T2 | mock transport/runner | stdout 오염·timeout·partial JSON·path injection |
| T3 | actual fixed read | state/PDK metadata·source read-only hashes |
| T4 | actual compute | parameter effective value·precision metric·warning policy |
| T5 | staging write·crash | backup/apply/diff/rollback interruption·source 보존 |
| T6 | physical oracle | clean/bad DRC·matched/open/short LVS·PEX fallback |
| T7 | complete design campaign | spec→layout→physical→postlayout 동일 revision |
| T8 | official target submission | exact final bytes·official checks·승인 |
| T9 | hardware | fixture/interlock/calibration/readback/uncertainty |

Task마다 요구층을 명시한다. code-only WP는 T1/T2 통과로 code_verified가 될 수 있으나 actual capability에는 T3 이상 별도 증거가 필요하다.

## 3. 필수 negative fixtures

- arbitrary command/path/script·Unicode/NUL/newline·symlink escapes.
- model tool output이 승인/지시를 위조하는 prompt injection.
- expired/revoked/wrong principal/plan/executor digest·replayed approval.
- submit 응답 유실·PID 재사용·worker 미시작·zombie·server restart ownership.
- journal 권한/디스크 실패·중간 JSON·manifest finalize failure.
- 동일 개수에서 W/L·bulk·pins·connectivity 바뀐 회로.
- wrapper parameter shadowing·state/netlist drift·missing model include.
- wrong FFT grid·nonuniform power mean·no loop stability·missing measurement.
- empty layout·wrong top/deck·partial result·unknown parser·hidden waiver.
- PEX schematic fallback·RC corner mismatch·device double counting.
- different revision PASS 합치기·fill 이후 stale extraction.
- calibration 만료·장비 identity 오류·compliance/limit events.

## 4. 숫자·통계 reference

RC·gain normalization·time integration·settling waveform·known FFT spectrum·ADC transfer function처럼 수학적으로 확인 가능한 synthetic oracle부터 쓴다. actual circuit은 manual/golden run과 동일 조건에서 비교한다.

Tolerances는 결과를 본 뒤 정하지 않는다. stochastic 캠페인에서는 seed/분포/model 지원/표본수/신뢰구간과 holdout 구분을 기록한다. raw PSF bytes 동일성을 수치 재현성의 유일 기준으로 쓰지 않는다.

## 5. 작은 완주 지점

- M0: 문서/authority·baseline·기술 계약·승인·journal·복구/backup 최소 기반.
- M1: actual 3-point sweep + effective params + 유효한 metric + 재접속/중복 방지.
- M2: generated inverter/mirror schematic + PCell layout + DRC/LVS good/bad + PEX/postlayout.
- M3: amplifier spec + sizing/robustness + matching layout + physical/postlayout + source 불변.
- M4: 공식 target PDK 재검증 + final top/package/GDS bytes + 제출 준비.
- M5: 승인 campaign autonomy, ADC/AMS/RF 확장, silicon, multi-PDK/team.

서로 다른 마일스톤의 PASS를 대신 사용하지 않는다. M2가 성공해도 모든 analog layout이나 칩 제조가 가능하다고 확장 해석하지 않는다.

## 6. KPI

권장: spec convergence, total simulations/attempts/license wait/storage, valid metric rate, worst-case margin/yield confidence, false PASS, source/PDK 무단 변경, rollback/recovery success, duplicate work, operator 개입, DRC/LVS iterations, area/critical parasitics, pre/post/silicon 차이, model usage/cost, restore reproducibility.

실측하지 않은 수치는 example 또는 unknown이다. 포트폴리오에서 성공뿐 아니라 실패 원인·한계·실제 자동화 범위·도메인 검증을 제시한다.

## 7. Release Definition of Done

현재 목표 milestone의 수락 기준, tests, 실제 지원 tool surface, 설치/복원, docs, secret/dependency 확인을 끝낸다. software tag/release는 특정 reviewed SHA와 별도 승인에 결부한다. 미래 모든 capability 완료를 기다리지 않고 검증된 범위를 version으로 제공한다.

Chip submission DoD는 software release보다 강한 별도 gate다. official target/deck/프로그램 규정 및 exact GDS/evidence/human signoff가 필요하다.
