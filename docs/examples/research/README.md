# ΣΔ ADC 연구 시작 자료

첫 대상은 17 MOS self-cascode OTA입니다. 후속 연구는 GPDK090에서 진행하며, 첫 입력 후보는 [OTA와 PDK 매핑 초안](ota-17mos.draft.json)에 있습니다. `null`은 미확정입니다. 이 파일은 연구 입력 수집 양식이며 생성기나 MCP의 실행 스키마에 속하지 않습니다. 기존 14 MOS AMP와 별도의 대상입니다.

논문 서지 정보는 Mario A. Jiménez-González, *Design of a 12-bit Sigma Delta ADC in 45 nm CMOS technology*, ITESO, 2024년 11월입니다. Fig. 2-12, Table 7, 단자 연결 및 수치는 원문 대조가 필요합니다. 초안의 W/L 단위는 µm이며 PM6의 배수는 6입니다. GPDK090으로 옮길 때 W/L과 배수는 CDF와 유효 Netlist에 맞춰 결정합니다. [ITESO 서지 기록](https://rei.iteso.mx/items/5b2a7fc8-347e-4113-9cfc-93c87913ab34)

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

## 현재 앱 연결과 로컬 운영자 stdio

C0가 실제 앱 연결에서 읽기 전용으로 조회한 결과, `cadence_runtime_info_v2`는 bridge 1.0.0, stdio, 설계 설명 1개, PDK 2개를 보고했습니다. `cadence_list_designs`에서 확인한 유일한 설명은 `reference-differential-amplifier-tb2`이며 실행 검증이 없는 설명용 항목입니다. 앱의 connector에 노출된 26개 도구에는 아래 네 작업 도구가 없습니다. 통합 소스 및 설치 검증용 개발 wheel `2.2.0.dev0`의 운영자 stdio 경로는 별도입니다.

연구용 클라이언트에는 선택한 wheel의 Python을 지정하고 `python -m cadence_mcp_bridge operator-setup export-client --settings RUNTIME --context CONTEXT_ID --format codex --output NEW_CLIENT_FRAGMENT`로 생성한 설정을 사용합니다. 설정의 `serve-operator` 연결을 추가해 다시 연결한 뒤 `tools/list`로 작업 도구와 스키마가 보이는지 확인합니다. `SETUP_REQUIRED` 또는 도구 누락은 context·등록·실행 제한을 다시 확인할 신호입니다. [운영자 연결 절차](../../POST_01_OPERATOR_SETUP.md)


## 등록과 MCP 호출

1. 확인한 회로 정의를 설치본이 실제 지원하는 생성 경로에 맞춥니다. 작업용 대상에서 생성·저장·별도 프로세스 재오픈·D/G/S/B와 속성 재조회·Spectre Netlist 대조를 마친 후 등록합니다. 파라미터 수정 후에는 변경 계획과 적용값, 재오픈값, Netlist의 모델·연결·유효 파라미터와 비대상 변경 여부를 다시 확인합니다.
2. `native-registration schema`와 `native-registration reader-schema`로 버전별 형식을 확인합니다. `native-registration observe --settings SETTINGS --context CONTEXT --request REQUEST --output NEW_RECORD`로 실제 지문을 수집합니다. `native-registration assemble`에 같은 설정·context와 `--identity-manifest-sha256`, 대응하는 `--request`, `--record`, `--reader-definition` 묶음, `--output`을 제공합니다. Design registry의 설명 등록과 native 실행 등록은 별도입니다.
3. 등록을 `native-runtime bundle`에 연결한 뒤 현재 운영자 절차에 따라 기존 장부를 유지하며 stage·activate/update·preflight를 진행합니다. 설치본의 `operator-setup export-client`로 `serve-operator` context를 연결하고 MCP `tools/list`에서 실제 이름과 입력 스키마를 확인합니다. 아래는 등록과 실행 범위 확정 뒤 사용하는 인수 구조입니다. [운영자 설정](../../POST_01_OPERATOR_SETUP.md) · [실행 준비](../../../README.md#run-query-and-repeat)

```text
cadence_plan_operation({
  "request": {
    "schema_version": 1, "design_id": DESIGN_ID, "analysis_id": ANALYSIS_ID,
    "values": [{"logical_id": VARIABLE_ID, "value": NUMBER_TEXT, "unit": UNIT}],
    "result_reservation_bytes": APPROVED_BYTES
  }
})
cadence_submit_operation({
  "submission": {
    "operation_id": UUID, "expected_plan_sha256": RETURNED_PLAN_SHA256,
    "request": SAME_PLAN_REQUEST
  }
})
cadence_operation_status({"request": {"operation_id": UUID, "expected_plan_sha256": RETURNED_PLAN_SHA256}})
cadence_operation_result({"request": {"operation_id": UUID, "expected_plan_sha256": RETURNED_PLAN_SHA256}})
```

`values`에는 등록된 명시 입력 전체를 넣습니다. 계획으로 실행 권한이 생기지 않습니다. 같은 UUID와 계획 해시로 상태와 결과를 재조회하고, 미완료나 실패는 원래 기록을 보존합니다. 입력 등록용 템플릿과 위 기호 자리표시자는 직접 제출 전에 각각 설치 스키마와 실제 등록값으로 채웁니다.

## 버전별 근거

| 기능 | 구현·MCP 연결 상태 | 검증 수준과 근거 | 커밋·PR | 남은 입력 또는 작업 |
| --- | --- | --- | --- | --- |
| 운영자 등록과 등록된 DC/AC/TRAN 호출 | 기존 operator CLI와 MCP 네 도구 재사용 | 공개 2.0.0의 실제 Codex 자격 기록과 2.1.0의 배포 범위. 현 브랜치는 `2.2.0.dev0` 소스 확인 | [2.1.0 자격 범위](../../releases/2.1.0/QUALIFICATION.md), [native MCP 기록](../../NATIVE_MCP_01_RESULT_V1.md) | 실제 설치본·context·grant 확인 |
| 생성·재오픈·Layout | 기존 인버터 생성 및 제한된 Layout 기능 참고 | 기존 검증 회로에서의 생성·Layout 증거 | PR167/168, [M2 인버터](../../M2_OWNED_INVERTER_ACCEPTANCE_20261015.md), [Layout MCP](../../LAYOUT_MCP_CLI.md) | 17 MOS 선언형 생성부터 등록까지 확인 |
| 파라미터 변경 | 제한된 기존 변경·readback 경로 재사용 후보 | 등록 인버터 변경과 AMP 수동 변경 검증. AUTO120 최신 소스에서 stale readback 회귀 확인, 실제 자동 변경 결과 대기 | PR169/170, `4aab9ca4aacf4604a150c2d5d48305425b7da948` | 정확한 OTA CDF·연결과 자동 변경 저장·재오픈·Netlist 검증 |
| 저장 ADE 비교 | 기존 내부 operator CLI에서 증거 비교 | 실제 AMP DC/AC, 설치 CLI, 동일 SHA CI Windows 13/13 및 POSIX 25/25 | `d95342b527b68f74d631a504c47548d4af4eb26d`, PR171, run `43580064449` | OTA 생성 또는 OTA 전용 측정 경로의 실제 MCP 검증 |
| OTA OP·AC·TRAN | 기존 결과 reader·측정 계약 재사용 후보 | 이 문서의 초안과 스키마 대조. 17 MOS OP, 단일 출력 이득, 정밀 TRAN 지표의 통합 지원은 별도 확인 | [측정 바인딩](../../MEASUREMENT_BINDINGS_V2.md), [ADC 측정 계약](../../ADC_MEASUREMENT_CONTRACTS.md) | 모델·관측·시뮬레이터 입력과 출력 수단 검증 |

## 재개 프롬프트

> 저장소의 `docs/examples/research/README.md`와 `ota-17mos.draft.json`을 읽고, 최신 C0 상태와 설치본의 MCP 도구를 먼저 확인해줘. ITESO 논문 Fig. 2-12와 Table 7로 후보값·연결을 대조하고, 실제 GPDK090의 셀·CDF·모델·단자 근거를 확인해 미확정 입력을 식별해줘. 확인된 정의로 OTA의 작업 복사본 생성→저장→독립 재오픈→Spectre Netlist 검증→기존 등록→MCP 계획·실행·상태·결과·같은 ID 재조회 순서로 이어가되, 실행 범위와 기존 장부를 유지해줘. 각 단계의 소스 SHA, 설치 버전, 근거와 검증 수준을 기록해줘. 첫 연구 결과를 확인한 뒤 TG, comparator, DAC, SC integrator, 아날로그 루프는 위 순서를 따라 진행해줘.
