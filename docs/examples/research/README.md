# ΣΔ ADC 연구 시작 자료

첫 대상은 17 MOS self-cascode OTA입니다. 후속 연구는 GPDK090에서 진행하며, 첫 입력 후보는 [OTA와 PDK 매핑 초안](ota-17mos.draft.json)에 있습니다. `null`은 미확정입니다. 이 파일은 연구 입력 수집 양식이며 생성기나 MCP의 실행 스키마에 속하지 않습니다. 기존 14 MOS AMP와 별도의 대상입니다.

논문 서지 정보는 Mario A. Jiménez-González, *Design of a 12-bit Sigma Delta ADC in 45 nm CMOS technology*, ITESO, 2024년 11월입니다. Fig. 2-12, Table 7, 단자 연결 및 수치는 원문 대조가 필요합니다. 초안의 W/L 단위는 µm이며 PM6의 배수는 6입니다. GPDK090으로 옮길 때 W/L과 배수는 CDF와 유효 Netlist에 맞춰 결정합니다. [ITESO 서지 기록](https://rei.iteso.mx/items/5b2a7fc8-347e-4113-9cfc-93c87913ab34)

## 연구 인계

- **준비된 경로** — 실제 GPDK090 인버터에서 저장, 독립 재개방, 전체 테스트벤치 Netlist와 등록 후보 조립까지 확인했습니다. 설치본 `0a84000`은 별도의 AMP 20 µm 기준본과 자동 120 nm 사본의 기존 Spectre DC·AC 결과 네 건을 비교 파일로 저장했고, 독립 QA와 Windows·POSIX CI를 통과했습니다. [PR 172](https://github.com/Phjrab/cadence-mcp-bridge/pull/172) · [CI 결과](https://github.com/Phjrab/cadence-mcp-bridge/actions/runs/45112099367)
- **OTA 미확정 입력** — 논문의 D/G/S/B 연결과 치수, 실제 GPDK090 셀·CDF·모델 매핑, 테스트벤치의 공급·입력·부하와 관측 경로를 확정해야 합니다. 성능 목표와 허용 오차도 미정입니다.
- **호출 순서** — 설치 MCP에서 `tools/list` → 회로 정의 검증 → MOS 블록 계획 → 지원되는 Cadence 경로에서 작업 사본 생성·저장 → 독립 재개방 및 Netlist 대조 → 대상과 분석 reader 등록 순으로 진행합니다. 실행 범위가 확정되면 분석 계획 → 제출 → 상태 → 결과 → 같은 작업 ID로 재조회 순으로 확인합니다. 첫 OTA는 DC/OP와 AC부터 시작합니다.

## 블록 순서와 진입 조건

| 순서 | 필요한 입력 | 먼저 확인할 결과 |
| --- | --- | --- |
| OTA | Fig. 2-12 단자와 넷, Table 7, PDK 매핑, 부하·입력 조건 | DC 동작점, 단일 출력 차동 AC 이득, 전력 |
| Transmission gate | NMOS/PMOS bulk, complementary 제어, 입력 범위와 부하 | 도통/차단, 스위칭 구간 응답 |
| Comparator | 클록, 입력 차·공통모드, 판정 기준과 부하 | 극성, 에지별 지연과 미판정 사례 |
| 1-bit feedback DAC | Comparator 출력 매핑, 기준 전압, 스위치 위상 | 코드별 출력, 에지 응답과 settling |
| SC integrator | OTA·TG, 커패시터 값과 연결, 샘플/적분 위상 | 위상별 전하 전달, 이득, settling |
| 아날로그 ΣΔ 루프 | 검증된 블록, 피드백 부호, 공통 시간축과 초기 조건 | 루프 전이 및 bitstream 수집 가능 범위 |

초기 테스트벤치는 이상적인 non-overlap 클록을 사용합니다. 주파수, dead time, 에지, 레벨과 초기 위상을 결정한 뒤 각 블록의 클록 입력에 연결합니다. 디지털 클록 생성기, CIC, decimator, RTL, 연구 회로 Layout 및 장시간 FFT는 별도 연구 단계입니다.

## 측정 계획

| 분석 | 설정과 판정 근거 |
| --- | --- |
| DC/OP | VDD 1.0 V, VSS 0 V, 초기 공통모드 0.5 V·27 °C. 17개 관측 인스턴스의 실제 경로를 등록하고 `id`, `gm`, `gds`, `vgs`, `vds`, `vdsat`, `region`의 항목·단위·원시 부호·출처·누락 사유를 보존합니다. Region 해석은 모델 정의와 소자 역할을 근거로 합니다. OP 항목 수와 파형 노드 수는 별도로 확인합니다. 공급원의 양단 전압과 선언된 전류 기준 방향으로 signed 전력을 산출합니다. |
| AC | 후보 `inp` DC 0.5 V, AC 0.5∠0°, `inn` DC 0.5 V, AC 0.5∠180°. 후보 그리드 1 Hz–1 GHz, 16점/decade. 부하 1 pF는 검증용 가정입니다. 실제 복소 입력 차와 출력으로 `V(out)/(V(inp)-V(inn))`을 계산합니다. 저주파 샘플과 교차를 끼는 두 점, 보간 방법을 기록하고 교차 부재·범위 부족을 구분합니다. Phase margin은 검증된 loop-gain 구성과 부호로 평가합니다. |
| TRAN | 신호와 시간 창, 최대 스텝, 임계값과 edge 방향, slew 구간, settling 기준·오차·남은 관측 기간, 평균 전력의 공급원·구간을 정의합니다. Settling은 진입 이후 관측 끝까지 오차 내 유지 여부를 확인합니다. 충분한 원본 해상도에서 지표를 계산하고 표시용 축소 데이터와 구분합니다. 불충분한 구간이나 해상도는 누락 사유로 남깁니다. |

참고 수치 63.91 dB와 20.21 MHz는 원문 대조할 비교값입니다. 38.8 µW는 전달받은 자료에서 전체 아날로그 모듈레이터 전력으로 설명됩니다. 초기 조건과 커패시터 환산값도 확인이 필요합니다. 합격 목표와 허용 오차는 미설정입니다. 장시간 bitstream 분석은 별도로 샘플링·관측 길이·FFT 조건을 정합니다. 개별 블록 측정은 ADC 12-bit 성능의 검증 단계와 구분합니다.

현재 소스의 generic measurement 샘플 상한은 256, 기존 sweep 점 상한은 16입니다. 적용 전에 설치 도구의 분석별 reader·관측 채널·파일 한도를 확인하고, 구간 선택과 지표 직접 추출을 먼저 검토합니다. [측정 안내](../../ANALOG_MEASUREMENTS_V1.md) · [sweep 안내](../../GENERIC_DESIGN_SWEEP_V2.md)

## 필요한 자료

- 논문 원문 Fig. 2-12와 Table 7 대조본, 각 소자의 D/G/S/B 및 bulk, 실제 핀·내부 넷·계층 연결, 심볼 방향 및 배선 정보.
- 실제 GPDK090 라이브러리·셀·뷰, 모델 section과 승인된 의존 파일, D/G/S/B 실단자 이름, CDF `w`·`fw`·`l`·`m`·finger 의미, 적용 범위와 단위 증거. 소자별 의도된 역할 및 OP region 정의.
- 작업용 라이브러리, 스케메틱·심볼·테스트벤치 정의, 전원·부하·클록·분석 조건, 실제 관측 경로·단위·전류 방향. 사용자 선택이 필요한 목표와 허용 오차는 별도로 기록합니다.
- 기존 운영자 context와 대상별 등록·실행 범위, 설치 wheel 버전과 정확한 SHA, 런타임 자산 및 결과 한도. 원본·PDK·실행 장부와 사설 증거는 운영자 관리 저장소에 둡니다.

## 현재 앱 connector와 개발 저장소 stdio

현재 앱의 실제 read-only 조회는 `cadence_runtime_info_v2`에서 bridge `1.0.0`, stdio, 설계 설명 1개, PDK 2개를 반환했습니다. `cadence_list_designs`의 `reference-differential-amplifier-tb2`는 설명 전용이며 검증되지 않은 항목입니다. 이 connector에는 총 26개 도구가 노출되고, `cadence_plan_operation`·`cadence_submit_operation`·`cadence_operation_status`·`cadence_operation_result`는 없습니다. 따라서 현재 앱 connector로 이 연구의 등록 회로나 시뮬레이션을 호출할 수 없습니다.

개발용 `serve-operator` 설치본은 `2.2.0.dev0`, 소스 커밋 `e5486215808ed02438f6b08e8e3fcee15ef2f9b3`, wheel SHA-256 `10ee8302cef94a8dced6b13b9bf07940ed0633bc5d14726c820e85802d2f2797`입니다. 설치 검증 환경의 운영자 프로필에서 도구 112개를 확인했습니다. 기준 설치본의 103개 도구 스키마를 유지하고 연구용 도구 9개를 추가했습니다. 같은 작업 ID로 상태·결과를 재조회하고 제출을 반복해도 합성 실행 수와 예약량이 유지됐습니다.

이 설치본을 사용할 때는 운영자가 `operator-setup export-client --settings RUNTIME --context CONTEXT_ID --format codex --output NEW_CLIENT_FRAGMENT`으로 만든 클라이언트 설정의 Python 경로와 `serve-operator` 인수를 사용합니다. 연결 후 `tools/list`에서 아래 도구와 입력 스키마를 확인합니다. [운영자 연결 안내](../../POST_01_OPERATOR_SETUP.md)

## 검증 가능한 synthetic 예제

`inverter.synthetic.json`은 `ResearchCircuit` 형식의 필드 완비 합성 사례입니다. `TestPdk`, 두 MOS, D/G/S/B, DUT와 testbench, 심볼, 펄스 입력, DC 분석, gm 관측을 담아 Python validator에 전달할 수 있습니다. GPDK090이나 논문 회로의 셀·CDF·전기적 근거는 제공하지 않습니다. 이 파일은 design registry 문서와 다른 구조라서 `design validate --registry` 입력으로 사용하지 않습니다.

저장소 루트에서 현재 checkout의 validator를 호출하는 로컬 예시는 다음과 같습니다. 이 검사는 회로 문서 구조만 확인하며 cellview를 만들거나 native registration 또는 실행 권한을 생성하지 않습니다.

```powershell
uv run --locked python -c "from pathlib import Path; from cadence_mcp_bridge.research_circuit import ResearchCircuit, validate_research_circuit; p=Path('docs/examples/research/inverter.synthetic.json'); d=validate_research_circuit(ResearchCircuit.model_validate_json(p.read_text(encoding='utf-8'))); print(d.binding.design_id, len(d.circuits), d.source.reference)"
```

실제 회로는 합성 예제를 등록에 재사용하지 않습니다. 허용된 경로로 작업용 회로를 만들고 저장·독립 재오픈·단자/CDF·Spectre Netlist를 확인한 뒤, 운영자 context의 `native-registration schema`, `reader-schema`, `observe`, `assemble` 절차로 등록합니다. 설명용 design registry와 실행 등록은 별개입니다. [운영자 설정](../../POST_01_OPERATOR_SETUP.md)

## 설치 MCP에서 시작하는 순서

연결한 stdio 클라이언트에서 `tools/list`로 도구를 확인합니다. 아래는 각 `tools/call`의 도구 이름과 인수 조합입니다. `definition`에는 예제 파일을 파싱한 JSON 객체를 사용합니다. `output_library`에는 계획할 새 작업용 라이브러리 이름을 넣습니다.

```text
cadence_validate_research_circuit({"request": {"definition": definition}})
cadence_plan_research_mos_block({"request": {
  "definition": definition, "expected_binding": definition.binding,
  "expected_definition_sha256": validation.definition_sha256, "output_library": output_library
}})
```

계획 뒤에는 담당자가 지원되는 Cadence 생성 경로에서 작업 사본을 저장하고, 독립 재오픈 및 실제 Netlist를 확인합니다. `cadence_verify_research_mos_block`으로 계획과 추출 증거를 대조한 뒤 해당 revision과 DC·AC·TRAN reader를 등록합니다. 아래 기호는 이 등록과 기존 실행 범위에서 얻습니다. `values`는 분석에 등록된 모든 명시 변수를 담고, `bytes`는 해당 작업의 등록된 결과 예약량입니다.

```text
request = {"schema_version": 1, "design_id": design_id, "analysis_id": analysis_id,
           "values": [{"logical_id": variable_id, "value": number_text, "unit": unit}],
           "result_reservation_bytes": bytes}
plan = cadence_plan_operation({"request": request})
key = {"operation_id": uuid, "expected_plan_sha256": plan.plan_sha256}
cadence_submit_operation({"submission": {"operation_id": uuid,
  "expected_plan_sha256": plan.plan_sha256, "request": request}})
cadence_operation_status({"request": key})
cadence_operation_result({"request": key})
```

작업마다 UUID와 계획 해시를 함께 보관합니다. 같은 결과를 확인할 때는 보관한 두 값으로 상태와 결과를 다시 조회합니다. 보존 AC에는 `cadence_research_ac_gain_result`, DC 공급전력에는 `cadence_research_supply_power_result`, TRAN 구간에는 `cadence_research_transient_result`를 사용합니다.

## 결과 조회와 Netlist 확인 예

등록된 DC operation에서 OP 읽기는 아래 입력만 받습니다. `device_op_catalog_path`와 `device_op_catalog_sha256`는 operator context에 함께 고정된 설정이며 요청에 경로나 파일 내용을 직접 전달하지 않습니다. 이 도구는 보존 결과를 읽기만 합니다.

```text
cadence_research_device_op_result({
  "request": {
    "registration_id": "DEVICE_OP_REGISTRATION_ID",
    "operation_id": "SUCCEEDED_DC_OPERATION_UUID",
    "expected_plan_sha256": "CANONICAL_PLAN_SHA256"
  }
})
```

Raw Spectre Netlist 파일은 MCP에 보내지 않습니다. 로컬 operator CLI에서 계획·파일 해시로 제한해 비교합니다.

```powershell
uv run cadence-mcp-bridge operator-candidates verify-research-raw-netlist `
  --plan PLAN.json --expected-plan-sha256 PLAN_SHA256 `
  --netlist DUT_NETLIST.scs NETLIST_FILE_SHA256 --output NEW_RESULT.json
```

MCP OP readback과 raw Netlist CLI 비교는 기존에 보존된 입력에 대한 국소 확인이며, 새 회로 생성·편집·시뮬레이션 권한을 부여하지 않습니다. 실제 등록, 분석 실행과 같은 operation ID의 결과 조회는 운영자 연결 설정과 승인 범위 안에서만 진행합니다. [운영자 연결 안내](../../POST_01_OPERATOR_SETUP.md)

## 새 테스트벤치를 등록할 때

Source9 형식의 인버터를 새 작업용 라이브러리에 생성할 때는 DUT와 테스트벤치를 한 번에 저장합니다. 별도 Cadence 프로세스에서 두 셀을 다시 열고, 그 테스트벤치의 전체 Spectre 입력을 생성합니다. 같은 작업 ID에 속한 세 단계의 기록과 실제 실행한 생성·재개방 스크립트를 보존합니다.

운영자 코드의 `verify_mos_block_handoff`는 선언·CDF로 스크립트를 재생성해 실행된 바이트와 대조합니다. 전체 Netlist에서 DUT의 포트 순서와 내부 소자, 최상위 DUT 연결, 전원·입력·부하를 확인합니다. 운영자는 이 결과와 `native-registration observe`의 관측값을 다음 명령에 전달합니다.

```powershell
cadence-mcp-bridge operator-candidates assemble-research-registration `
  --settings SETTINGS --context CONTEXT --request REQUEST.json REQUEST_FILE_SHA256 `
  --output NEW_REGISTRATION.json
```

`REQUEST.json`에는 스키마 버전 1, `expected_context_sha256`, `expected_handoff_sha256`, `identity_manifest_sha256`와 네 입력(`probe`, `observation`, `reader_definition`, `handoff`)의 `path`·`sha256` 쌍이 들어갑니다. 파일 해시는 실제 바이트 기준이고, `expected_handoff_sha256`은 검증된 handoff 객체의 정규화된 해시입니다. 등록 대상은 테스트벤치 셀과 해당 ADE 상태입니다. 라이브러리 전체, DUT 셀, 테스트벤치 셀의 지문을 구분해 보관합니다.

출력은 운영자가 검토할 등록 후보입니다. 이후 활성화된 대상과 권한을 갖춘 context에서 위의 MCP 계획·제출·조회 절차를 사용합니다.

## 버전별 구현과 검증 상태

| 기능 | 구현·MCP 연결 상태 | 검증 수준과 근거 | 관련 커밋/PR | 남은 입력 또는 작업 |
|---|---|---|---|---|
| 등록된 분석과 동일 ID 조회 | 개발용 stdio MCP에서 계획·제출·상태·결과 조회 | 설치본에서 합성 DC 실행 1회. 재제출·반복 조회·없는 결과 조회 후 추가 예약과 실행 0회 | `e548621` | 실제 연구 revision, 등록한 분석·reader 및 실행 범위 |
| 회로 정의·MOS 블록 | MCP에서 선언 검증·계획·증거 비교. 운영자 코드에서 DUT·심볼·테스트벤치를 생성하고 CLI에서 등록 후보 조립 | 실제 GPDK090 인버터의 세 뷰 저장, 별도 Cadence 프로세스의 배치·연결·속성 재조회, 전체 테스트벤치의 Spectre DC Netlist 생성 확인. 이전 사본의 NMOS 좌표 불일치도 독립 재조회에서 검출 | `9a8ac69`, [PR 172](https://github.com/Phjrab/cadence-mcp-bridge/pull/172) | 실제 생성 사례는 Source9 형식의 2 MOS·단일 finger 인버터. 새 분석 실행에는 해당 revision에 등록한 reader와 운영자 실행 권한 필요 |
| MOS 변경과 저장값 | MCP에서 등록된 변경을 계획하고 증거를 비교. 실제 자동 편집은 운영자가 대상과 범위를 고정한 Cadence 경로에서 실행 | 작업용 AMP에서 PM0의 폭·접합 관련 명시 속성 6개를 제거하고 저장. 독립 재개방에서 W/FW 120 nm, L 1 µm, Minimum을 확인. 기준 20 µm 회로와 두 실제 실행 Netlist를 비교했을 때 PM0의 `w/as/ad/ps/pd`만 변경. 동일한 모델·온도·Bias에서 사본의 DC 정적 공급전력과 AC 10 Hz 차동 이득을 측정하고 기존 기준 회로 결과와 대조 | `1ceed52`, [PR 172](https://github.com/Phjrab/cadence-mcp-bridge/pull/172) | 저장 시 도형 갱신 카운터가 변경되어 최초 편집 요청은 `OUTCOME_UNKNOWN`으로 보존. 별도 읽기 전용 관측과 해당 사본의 DC·AC 실행으로 저장값과 성능을 확인. 범용 MCP 자동 편집은 후속 작업 |
| AC·DC·OP | MCP에서 복소 이득·unity 교차·부호 있는 공급전력·등록 소자 OP 조회 | 설치 합성 입력에서 교차와 DC 2 mW 확인. OP 예제에서 id −3 µA와 gm 누락 사유 반환. 기존 AMP Bias 두 값의 실제 DC/AC·CLI 비교는 이전 실측 | `65f1ffd`, `e548621`, [PR 171](https://github.com/Phjrab/cadence-mcp-bridge/pull/171) | 실제 OTA 관측 경로·소자 OP catalog·전류 방향. 위상여유는 별도의 검증된 loop-gain 조건 필요 |
| TRAN 구간 측정 | MCP에서 원래 저장된 표본으로 delay·slew·settling·평균 공급전력을 평가. CLI는 크기가 제한된 파일 출력 지원 | 설치된 reader의 합성 전류 포함 결과에서 평균 3 mW, 전류 없는 버전에서는 미평가 확인. 표시용 축소 파형은 정밀 지표에서 제외 | `4c153f8`, `5012914`, `e548621` | 실제 공급전류 selector·부호, 등록된 native reader와 해상도 확인 |
| 작업용 Layout | 기존 조회·fork·편집·저장·재개방·diff 도구 유지 | 이전 실제 Cadence 작업용 Layout에서 instance 이동, 도형·연결 pin 추가 후 재개방. 동일 ID 재호출 시 추가 실행 0회 | [PR 167](https://github.com/Phjrab/cadence-mcp-bridge/pull/167) | 연구 회로 Layout·DRC·LVS·PEX는 별도 단계 |

## 재개 프롬프트

> 저장소의 `docs/examples/research/README.md`와 `ota-17mos.draft.json`을 읽고, 최신 C0 상태와 설치본의 MCP 도구를 먼저 확인해줘. ITESO 논문 Fig. 2-12와 Table 7로 후보값·연결을 대조하고, 실제 GPDK090의 셀·CDF·모델·단자 근거를 확인해 미확정 입력을 식별해줘. 확인된 정의로 OTA의 작업 복사본 생성→저장→독립 재오픈→Spectre Netlist 검증→기존 등록→MCP 계획·실행·상태·결과·같은 ID 재조회 순서로 이어가되, 실행 범위와 기존 장부를 유지해줘. 각 단계의 소스 SHA, 설치 버전, 근거와 검증 수준을 기록해줘. 첫 연구 결과를 확인한 뒤 TG, comparator, DAC, SC integrator, 아날로그 루프는 위 순서를 따라 진행해줘.
