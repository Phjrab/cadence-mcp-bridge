# ΣΔ ADC 연구 시작 자료

첫 대상은 17 MOS self-cascode OTA입니다. 후속 연구는 GPDK090에서 진행하며, 첫 입력 후보는 [OTA와 PDK 매핑 초안](ota-17mos.draft.json)에 있습니다. `null`은 미확정입니다. 이 파일은 연구 입력 수집 양식이며 생성기나 MCP의 실행 스키마에 속하지 않습니다. 기존 14 MOS AMP와 별도의 대상입니다.

Mario A. Jiménez-González의 ITESO 학위논문(2024년 11월) Fig. 2-12(인쇄 47쪽, PDF 57쪽)와 Table 7(인쇄 48쪽, PDF 58쪽)을 직접 대조했습니다. 초안에 17개 소자의 D/G/S/B, 역할, W/L과 배수를 기록했습니다. PM6은 논문 표에서 **W 16 µm, L 1 µm, 배수 6**입니다. 논문에서 finger 수는 확인되지 않았습니다. GPDK090에서 finger를 1로 선택한 목표 치수 8개는 비OTA 사본에서 확인했습니다. [ITESO 원문](https://rei.iteso.mx/items/5b2a7fc8-347e-4113-9cfc-93c87913ab34)

## GPDK090 기준 OTA 실환경 기록

기준 라이브러리는 `Ota17Base20261126`입니다. DUT는 `self_cascode_ota_17mos`의 schematic·symbol, 벤치는 `self_cascode_ota_tb/schematic`입니다. 같은 라이브러리의 저장본을 독립 세션에서 다시 열어 17개 MOS 각각의 OA·CDF 속성 12개를 확인했습니다. PM6의 실제 W/FW는 16 µm, L은 1 µm이며 m=6, fingers=1입니다.

| 기준 자료 | SHA-256 |
| --- | --- |
| 저장·재개방한 DUT 셀 | `2f4fd5ed2a67feae6ab0c08b82df9d171d30e9b1b5a14698b590eca35ec24f1e` |
| 심볼 | `36a7fd7bb9f6f0d6bd1efa209e8b88adb6bb93399166dbaef277d0ff2bd06921` |
| 벤치 셀 | `7e505aca6b693717d80955bac655e29c1a7ab73826cfac3192b12a8daba5bb6f` |
| 원래 ADE 상태 | `f4f596ff8594d32b843f6df9bc37244d6e488b0ba61f85d4157c9ca91dce7809` |
| DC 진단 넷리스트 | `ce78464809236cafd6e9e39f492ba184baa63f9c36de87126298058597c8504e` |
| AC 진단 넷리스트 | `45411f1bbbf3e6eef42b1cc0dfd20706c713f87e39015902516c6221317bbcff` |

생성 작업 `dafbdb6b-49a2-4909-b0ac-526a2bde60ea`는 저장과 재개방 후 넷리스트 검사에서 `OUTCOME_UNKNOWN`으로 끝났습니다. 원본에서 차동 입력 핀의 순서가 서브회로 선언과 호출에서 함께 바뀐 것을 확인했습니다. 각 핀의 연결, 17개 소자의 단자·모델·치수·접합값 및 실제 NN 모델 파일을 대조해 이 저장본을 별도로 검증했습니다. DC 진단 작업 `651941c2-087d-4cbb-9889-1b851e9aba3e`는 같은 회로에서 DC 분석문과 동작점 저장문을 출력했습니다. 두 모드 모두 전원 1 V, 입력 공통모드 0.5 V, 출력 부하 1 pF, 27 °C입니다. AC 입력 진폭은 inp에 +0.5 V, inn에 −0.5 V입니다.

### 기준 회로의 실제 DC·동작점·AC

DC 작업 `74e4610f-712b-4a2d-85b5-f891c10aaeac`과 AC 작업 `48b4d074-6a2d-428b-b409-87df84dc0d46`은 위 DUT·벤치와 같은 ADE 원본을 사용했습니다. 각각 한 번 실행했고 설치 MCP에서 같은 ID로 결과를 다시 읽었습니다. DC의 실제 입력 SHA-256은 `948c3ece63248839651dc1d0a54c94eaf92090e97a8a36ca62be827fa22a60cc`입니다.

| 측정 항목 | 기준값 |
| --- | ---: |
| DC 출력, 양 입력 0.5 V | 96.89545 mV |
| 전원 PLUS 단자로 들어가는 전류 | −107.25017 µA |
| 전원이 전달한 전력 | +107.25017 µW |
| 차동 이득, 1 Hz | 84.501530 V/V (38.53729144 dB) |
| 차동 이득, 10 Hz | 84.501530 V/V (38.53729144 dB) |
| 1 Hz 이득 대비 −3 dB 대역폭 | 465.727 kHz |
| 첫 0 dB 하강 교차 | 29.09589 MHz |

AC는 1 Hz–1 GHz의 145개 주파수에서 출력과 두 입력의 복소 전압으로 `V(out)/(V(inp)−V(inn))`을 계산했습니다. −3 dB 교차는 421.697–486.968 kHz, 0 dB 교차는 27.3842–31.6228 MHz 사이에 있습니다. 두 값은 해당 구간에서 로그 주파수에 대해 dB 이득을 선형 보간한 결과입니다. 위상여유 측정에는 별도의 루프 이득 구성이 필요합니다.

동작점 조회 `4b34c717-7d43-4881-8cac-afb661094597`는 원래 DC 결과에서 17개 MOS 각각의 id, gm, gds, vgs, vds, vdsat, region을 읽었습니다. 119개 모두 수치가 있었고 추가 Spectre 실행은 0회였습니다. 출력과 연결된 NM11의 VDS는 10.935 mV, VDSAT는 185.65 mV, gm은 0.1380 mS, gds는 2.3853 mS였습니다. 이 조건에서 출력이 아래 전원 레일에 가까워, NM11의 폭을 10 µm에서 1.5 µm로 줄이고 출력 전압·전력·이득이 어떻게 달라지는지 확인하는 후보를 선택했습니다. 길이 0.25 µm, 배수 1, finger 1을 유지합니다.

## 회로도에서 확인한 연결

- 외부 연결은 `inp`, `inn`, `out`, `VDD`, `VSS`입니다. `Vx`와 `Vy`는 그림의 라벨이고, 나머지 내부 이름은 보이는 배선을 구분하기 위해 붙였습니다. Fig. 2-12에서 추적한 68개 논리 단자와 5개 포트를 대조했습니다. 두 GPDK090 master의 CDF와 비OTA Netlist에서 Spectre의 D/G/S/B 순서, NMOS 벌크의 VSS 연결, PMOS 벌크의 VDD 연결을 확인했습니다. OTA를 실제로 생성하면 각 스택의 소스와 벌크를 독립 재개방 및 Netlist에서 다시 확인합니다.
- NM0/NM8과 NM1/NM9는 차동 입력의 두 self-cascode 가지입니다. PM2/PM4와 PM3/PM5는 미러 부하이고, 오른쪽 가지가 PM7/PM6의 공통 게이트를 구동합니다. PM8은 바이어스 공급의 다이오드 연결이며, NM6/NM2는 기준 가지, NM7/NM3은 꼬리 전류 가지, NM11/NM10은 출력 전류 싱크입니다. Fig. 2-2와 §2.3.3은 카스코드의 출력저항 역할과 공통 소스 두 번째 단을 설명합니다.
- 같은 게이트를 공유하는 쌍에서 소스 쪽 선형 동작과 드레인 쪽 포화 동작은 동작점에서 확인할 가설입니다. 다이오드 연결 소자는 정상적으로 켜져 있는지 확인합니다. 모델에 맞는 전압 부호와 여유, 실제 `id/gm/gds/vgs/vds/vdsat` 및 모델의 `region` 정의를 함께 봅니다.
- Source9와 BBE3에서 `gpdk090/nmos1v/symbol`과 `gpdk090/pmos1v/symbol`의 D/G/S/B 이름과 실제 Spectre 단자 순서를 확인했습니다. 모델은 각각 `gpdk090_nmos1v`와 `gpdk090_pmos1v`이며 BBE3 Netlist의 모델 section은 `NN`입니다. Source9의 확인된 W/FW·L은 NMOS 120/120·100 nm, PMOS 350/350·100 nm였습니다. 별도 AMP PM0에서는 120/120·1000 nm를 확인했습니다. 이 세 점의 배수와 finger는 모두 1입니다. CDF에서 `simW`는 `fw`, `simM`은 `m × fingers`에 대응했습니다. 비OTA의 PM6 대응점에서도 `m=simM=(6)*(1)`을 확인했습니다. PDK 전체 허용 범위와 다중 finger는 별도 확인 사항입니다.
- BBE3의 VDD 1 V, Vin 0 V에서 NMOS·PMOS의 원시 `region`은 각각 3·1이었습니다. 각 코드의 모델별 의미는 미확정입니다.

## 생성 전 연구 인계

- **준비된 경로** — 검증 표는 실제 Cadence에서 확인한 2 MOS 인버터와 14 MOS AMP의 결과를 다룹니다. 17 MOS OTA는 논문과 PDK 매핑을 대조하는 준비 단계입니다.

- **OTA 정적 선택** — 17개 R0 소자 위치, 포트 다섯 개, 심볼, 고정 소스와 부하의 bench 구성을 정했습니다. 첫 DC/AC 후보는 VDD 1 V, 입력 공통모드 0.5 V, 부하 1 pF, 27 °C이며 AC는 1 Hz–1 GHz, decade당 16점입니다. 소자 치수 근거를 정적 입력에 연결했습니다. 실제 OTA의 벌크·Netlist 대응과 선택한 bench primitive는 별도 확인합니다.
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

Fig. 2-13과 인쇄 49쪽이 보고한 45 nm 시뮬레이션의 저주파 이득은 약 63.91 dB, 0 dB 교차는 약 20.21 MHz입니다. 인쇄 98쪽의 평균 전력 38.8 µW는 전체 ΣΔ 모듈레이터 값입니다. 초안의 VDD 1 V, VCM 0.5 V, 27 °C, 부하 1 pF와 주파수 설정은 GPDK090 검증을 위한 후보입니다. Table 5의 1.2 V·40 dB·10 MHz 설계 예시는 초기 130 nm 첫 단에 해당합니다. GPDK090 OTA의 실측과 합격 목표는 아직 없습니다.

단일 출력 AC reader의 `TransferSignal` 예제입니다. 논리 이름은 실제 reader에 등록한 선택자에 연결하고, 기준점 10 Hz가 실제 표본에 있는지 확인합니다.

```json
{
  "positive_input": "inp",
  "negative_input": "inn",
  "positive_output": "out",
  "negative_output": null,
  "gain_frequencies_hz": ["10"]
}
```

이 정의는 복소수 `V(out)/(V(inp)-V(inn))`을 사용합니다. 분모가 0이면 해당 이득은 미평가합니다. 저주파 이득·−3 dB 대역폭·0 dB 하강 교차는 별개 지표입니다. 위상여유에는 별도의 검증된 loop-gain 구성이 필요합니다.

현재 소스의 generic measurement 샘플 상한은 256, 기존 sweep 점 상한은 16입니다. 적용 전에 설치 도구의 분석별 reader·관측 채널·파일 한도를 확인하고, 구간 선택과 지표 직접 추출을 먼저 검토합니다. [측정 안내](../../ANALOG_MEASUREMENTS_V1.md) · [sweep 안내](../../GENERIC_DESIGN_SWEEP_V2.md)

## 필요한 자료

- 논문 추적 결과와 독립 단자 대조, 대상 PDK의 벌크 정책, 실제 심볼 핀 순서·배치·배선 정보.
- 실제 GPDK090 라이브러리·셀·뷰, 모델 section과 승인된 의존 파일, D/G/S/B 실단자 이름, CDF `w`·`fw`·`l`·`m`·finger 의미, 적용 범위와 단위 증거. 소자별 의도된 역할 및 OP region 정의.
- 작업용 라이브러리, 스케메틱·심볼·테스트벤치 정의, 전원·부하·클록·분석 조건, 실제 관측 경로·단위·전류 방향. 사용자 선택이 필요한 목표와 허용 오차는 별도로 기록합니다.
- 사용할 설치 버전, 대상 회로·분석 등록, 분석별 결과 한도.

## Codex 앱 조회와 운영자 stdio

개발용 `2.2.0.dev0`의 실제 Codex 앱에서 등록된 AMP 사본의 정해진 PM0 작업과 별도 읽기 전용 연결을 확인했습니다. 읽기 전용 연결에서는 기존 AMP 비교·편집 기록과 정정 인버터(BBE3)의 보존 DC 동작점 14개를 조회했습니다. 인버터의 실제 DC 실행은 별도 운영자 stdio 연결에서 검증했습니다. 각 연결의 도구와 입력은 `tools/list`에서 확인합니다. [운영자 연결 안내](../../POST_01_OPERATOR_SETUP.md)

고정 편집 도구 `cadence_apply_fixed_amp_pm0`의 MCP 인수 예제입니다. 세 문자열 자리에는 등록된 작업 UUID, 계획 SHA-256, 작업 범위 SHA-256을 사용합니다.

```json
{
  "request": {
    "operation_id": "<registered-operation-uuid>",
    "expected_plan_sha256": "<registered-plan-sha256>",
    "expected_scope_sha256": "<registered-scope-sha256>"
  }
}
```

실제 검증은 사본 한 개에서 저장과 독립 재개방·Netlist 확인에 OCEAN을 각각 한 번 사용했습니다. Spectre 실행은 0회였습니다. 같은 입력으로 앱과 새 stdio 프로세스에서 각각 재조회해 동일한 `VERIFIED` 결과를 받았고 두 조회 모두 추가 실행은 0건이었습니다. [PR #175](https://github.com/Phjrab/cadence-mcp-bridge/pull/175)

## 검증 가능한 synthetic 예제

`inverter.synthetic.json`은 `ResearchCircuit` 형식의 필드 완비 합성 사례입니다. `TestPdk`, 두 MOS, D/G/S/B, DUT와 testbench, 심볼, 펄스 입력, DC 분석, gm 관측을 담아 Python validator에 전달할 수 있습니다. GPDK090이나 논문 회로의 셀·CDF·전기적 근거는 제공하지 않습니다. 이 파일은 design registry 문서와 다른 구조라서 `design validate --registry` 입력으로 사용하지 않습니다.

저장소 루트에서 현재 checkout의 validator를 호출하는 로컬 예시는 다음과 같습니다. 이 검사는 회로 문서 구조만 확인하며 cellview를 만들거나 native registration 또는 실행 권한을 생성하지 않습니다.

```powershell
uv run --locked python -c "from pathlib import Path; from cadence_mcp_bridge.research_circuit import ResearchCircuit, validate_research_circuit; p=Path('docs/examples/research/inverter.synthetic.json'); d=validate_research_circuit(ResearchCircuit.model_validate_json(p.read_text(encoding='utf-8'))); print(d.binding.design_id, len(d.circuits), d.source.reference)"
```

실제 회로는 합성 예제를 등록에 재사용하지 않습니다. 허용된 경로로 작업용 회로를 만들고 저장·독립 재오픈·단자/CDF·Spectre Netlist를 확인한 뒤, 운영자 context의 `native-registration schema`, `reader-schema`, `observe`, `assemble` 절차로 등록합니다. 설명용 design registry와 실행 등록은 별개입니다. [운영자 설정](../../POST_01_OPERATOR_SETUP.md)

## 설치 MCP에서 시작하는 순서

### 논문 초안을 실행 입력으로 변환

논문 초안은 `research-draft-v1`이고 도구가 검증하는 회로 정의는 `ResearchCircuit`입니다. 개발 설치본에서 아래 명령을 실행하면 포팅 문서의 JSON Schema가 `request_schema`에 반환됩니다. 스키마 제목은 `DraftPort`입니다.

```powershell
cadence-mcp-bridge operator-candidates schema --action compile-research-draft
```

포팅 문서에 다음 값을 확정합니다.

| 입력 | 값의 출처 |
| --- | --- |
| 초안과 토폴로지 | `draft_sha256`은 초안 파일 바이트의 SHA-256, `source_design`은 `self_cascode_ota_17mos`. `topology_source`는 검토한 회로도와 실제 증거 해시 |
| `binding`, DUT, 포트와 심볼 | 작업 공간의 실제 식별자와 원본 지문, 5개 DUT 포트의 순서·넷·방향·좌표, 심볼 경계와 핀 좌표. 아직 생성하지 않은 결과 revision의 지문을 입력에 사용하지 않음 |
| 소자 17개 | 초안과 동일한 이름·종류, 관측 자료로 확인한 master와 모델, 실제 R0 배치 및 각 소자의 W/FW/L·m·finger·폭 의미와 예상 Spectre W/L/m. `master_source`, `geometry.source`, `spectre.source`는 각각 검토한 증거에 연결 |
| `resolved_terminals` | 초안에서 해당 단자가 `null`인 경우에만 사용. 현재 초안은 논문 연결 전체를 기록했으므로 `{}`. 실제 벌크가 도식과 다르면 토폴로지를 먼저 재검토 |
| `bench`와 측정 | 5개 포트와 실제로 연결되는 DUT 인스턴스, 전원·입력·부하, 분석 및 관측 정의. reader의 실제 경로와 등록은 저장한 revision 확인 뒤 확정 |

파일명은 예시입니다. `ota-port.reviewed.json`에는 위 입력을 모두 확정한 실제 포팅 문서를 둡니다. 기본 렌더러의 배치는 R0와 단자 라벨 연결을 기준으로 검토합니다.

```powershell
$draft = 'docs/examples/research/ota-17mos.draft.json'
$port = 'ota-port.reviewed.json'
$draftSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $draft).Hash.ToLowerInvariant()
$portSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $port).Hash.ToLowerInvariant()
cadence-mcp-bridge operator-candidates compile-research-draft `
  --draft $draft $draftSha --port $port $portSha --output ota-request.json
if ($LASTEXITCODE -ne 0) { throw 'Draft compilation failed' }
$requestSha = (Get-FileHash -Algorithm SHA256 -LiteralPath ota-request.json).Hash.ToLowerInvariant()
cadence-mcp-bridge operator-candidates validate-research-circuit `
  --request ota-request.json $requestSha --output ota-validated.json
if ($LASTEXITCODE -ne 0) { throw 'Circuit validation failed' }
```

컴파일 출력은 `{"definition": {...}}` 형태의 검증 요청 파일입니다. 원본 파일 SHA와 검증 결과의 정규화된 `definition_sha256`을 구분합니다. 검증 결과의 `definition`과 `definition_sha256`을 아래 MOS 블록 계획에 전달합니다.

실행 연결 정보가 아직 없는 포팅 입력은 Python API `compile_research_draft(draft_bytes, port_bytes, static_preview=True)`로 회로 구조를 먼저 확인할 수 있습니다. 이 경로는 `StaticDraftPort`를 받아 `ResearchCircuitStaticPreview`를 반환합니다. 17 MOS 초안으로 DC 전용과 DC+AC 두 미리보기를 검증했습니다. 미리보기에는 미확정 소자 값이 그대로 남으며, 실행용 검증·계획 스키마는 이 형식을 받지 않습니다.

통합 CLI에서도 같은 미리보기를 만들 수 있습니다. `$staticPort`는 binding을 넣지 않은 `StaticDraftPort` 파일이며, SHA는 각 입력 파일의 실제 바이트에서 계산합니다.

```powershell
$staticPort = 'ota-port.static.json'
$staticPortSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $staticPort).Hash.ToLowerInvariant()
cadence-mcp-bridge operator-candidates compile-research-draft --static-preview `
  --draft $draft $draftSha --port $staticPort $staticPortSha --output ota-static-preview.json
```

성공 상태는 `RESEARCH_CIRCUIT_STATIC_PREVIEW_EXPORTED`입니다. 출력 파일의 `file_sha256`과 정규화한 미리보기의 `definition_sha256`은 별도입니다.

### 회로 계획부터 분석 결과 조회까지

연결한 stdio 클라이언트에서 `tools/list`로 도구를 확인합니다. 아래는 `tools/call`의 도구와 인수를 나타낸 의사 코드입니다. 반환값은 MCP 응답의 `structuredContent`를 뜻합니다. `definition`은 컴파일된 검증 요청의 `definition` 객체 또는 로컬 합성 예제의 객체입니다. `output_library`에는 계획할 새 작업용 라이브러리 이름을 넣습니다.

```text
validation = cadence_validate_research_circuit({"request": {"definition": definition}})
cadence_plan_research_mos_block({"request": {
  "definition": validation.definition, "expected_binding": validation.definition.binding,
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
status = cadence_operation_status({"request": key})
# SUCCEEDED 상태를 확인한 뒤 결과를 조회합니다.
cadence_operation_result({"request": key})
```

작업마다 UUID와 계획 해시를 함께 보관합니다. 같은 결과를 확인할 때는 보관한 두 값으로 상태와 결과를 다시 조회합니다. 보존 AC에는 `cadence_research_ac_gain_result`, DC 공급전력에는 `cadence_research_supply_power_result`, TRAN 구간에는 `cadence_research_transient_result`를 사용합니다.

### 개발 경로별 도구와 재개 지점

| 단계 | 호출 또는 재개 기준 |
| --- | --- |
| 초안과 계획 | 스키마 조회 → 컴파일 → 검증 → `cadence_plan_research_mos_block`. 입력이 미확정이면 포팅 문서를 고치고 그 파일의 새 SHA로 다시 검증합니다. 계획이 있으면 검증 정의와 계획 해시를 함께 보관합니다. |
| 등록형 생성과 저장 확인 | `cadence_plan_registered_research_generation` → `cadence_apply_registered_research_generation` → `cadence_registered_research_generation_status` → `cadence_registered_research_generation_handoff`. 중단되면 같은 ID의 상태와 단계별 보존 증거를 확인합니다. `OUTCOME_UNKNOWN`은 기존 사본을 확인하는 단계에서 멈춥니다. |
| 등록 소자 편집 | `cadence_plan_registered_mos_change`로 변경 계획을 준비합니다. 등록 후 `cadence_plan_registered_mos_edit` → `cadence_apply_registered_mos_edit` → `cadence_lookup_registered_mos_edit`를 사용합니다. 응답이 끊기면 같은 ID와 해시로 lookup부터 합니다. |
| 고정 저장본 분석 | 고정 분석 프로필에는 `cadence_plan_fixed_research_analysis`, `cadence_submit_fixed_research_analysis`, `cadence_fixed_research_analysis_status`, `cadence_fixed_research_analysis_result`가 있습니다. 네 호출은 등록된 동일 `operation_id`와 `expected_plan_sha256`을 받습니다. 응답이 끊기면 상태부터 재조회합니다. 성공 결과와 등록된 저장 revision을 대조하고, 비교 등록에 연결된 결과는 `cadence_retained_amplifier_comparison`으로 조회합니다. |

연구 재개에는 검증된 개발 wheel과 해당 운영자 연결을 사용합니다. 설치본에서 사용할 도구와 요청 형식을 확인하고, 당시 승인·자원 상태를 기존 절차로 확인합니다.

생성 전에 회로 배치·핀·심볼·bench와 소자별 목표 값을 확정합니다. 새 사본이 실제로 생성되면 저장·독립 재개방에서 DUT와 bench의 revision 및 원본 지문을 얻고, Netlist와 대조해 인계합니다. 분석 등록에서 실제 전압·공급전류·소자 selector를 확인한 뒤 계획 SHA와 작업 ID를 후속 조회에 사용합니다. 성능 목표·허용 오차는 합격 판정에, 클록·장시간 TRAN 정의는 후속 분석에 사용합니다.

#### 오프라인 생성 준비

검증한 회로 정의와 계획, 테스트벤치 조건을 `ResearchGenerationPreparationRequest`에 담습니다. 요청에서 참조하는 CDF 등 각 증거 파일은 원본 바이트 SHA-256으로 지정합니다. `--evidence FILE SHA256`은 요청의 증거 파일마다 한 번씩 전달합니다.

```powershell
cadence-mcp-bridge operator-research-generation prepare `
  --request $prepareRequest $prepareRequestSha `
  --evidence $cdfFile $cdfFileSha `
  --output-directory $newPreparationDirectory
```

출력 디렉터리의 부모는 존재해야 하며, 출력 디렉터리 자체는 새 경로여야 합니다. `LOCAL_GENERATION_PREPARED`는 정규화된 정의·계획·bench·조건, CDF 증거, 저장 및 독립 재개방 프로그램이 로컬로 준비됐다는 뜻입니다. 출력의 `preparation.private.json`과 명령이 반환한 파일 SHA를 함께 보관합니다. 기록이 중간에 끊겼다면 기존 폴더를 보존하고 새 폴더에서 오프라인 준비를 다시 합니다.

준비는 원격 접속과 실행 권한 없이 수행됩니다. 실제 Netlist 프로그램, 작업 범위와 권한, 운영자 등록은 이후 단계에서 연결합니다. 다음 명령의 등록 파일은 이 준비 결과를 검토해 별도로 만든 입력입니다.

**선택 입력 `signed_ac_vsin_pair`** — 기본값은 `false`입니다. 이 옵션을 제공하는 개발 소스에서 `true`는 보존 증거와 일치하는 접지 기준 `analogLib/vsin/symbol` 두 개에만 적용합니다. 두 소스의 DC는 각각 0.5 V, AC 진폭은 각각 +0.5 V와 −0.5 V입니다. 저장된 사인 설정 `va=50m`, `freq=1K`, `filenums=none` 및 두 번째 소스의 `sinephase=180`을 보존합니다. 이 경로의 Netlist 조건은 AC 전용입니다.

옵션을 사용하려면 `signed_ac_evidence_sha256`으로 검토한 저장·독립 재개방 관측을, 그 관측의 `effective_netlist_sha256`으로 실제 원본 Netlist를, `primitive_cdf_sha256`으로 일치하는 CDF를 연결합니다. 준비 명령에 해당 증거 파일을 각각 전달합니다. 기존 AMP의 실제 두 `vsin`에서 base/effective CDF, 저장 OA와 실행 Spectre 입력을 확보해 오프라인으로 대조했습니다. CDF의 `acp`는 단위와 값이 비어 있었고 OA에는 이 속성이 없었습니다. 이 실제 소스 증거를 합성 17 MOS의 준비 검증에 사용했습니다. 새 OTA에서 해당 옵션으로 생성·재개방·Netlist를 확인하는 절차는 대기 중입니다.

#### 등록형 생성의 CLI와 MCP 요청

`serve-operator --registered-research-generation FILE SHA256`은 한 생성 등록을 선택합니다. `FILE SHA256`은 등록 파일과 원본 바이트의 해시입니다. 네 MCP 도구에는 아래 객체를 `request`로 감싸 전달합니다. CLI의 요청 파일에는 내부 객체만 저장합니다.

```json
{
  "operation_id": "<registered-generation-uuid>",
  "expected_binding_sha256": "<canonical-generation-binding-sha256>"
}
```

생성 작업 ID는 운영자가 등록할 때 얻습니다. `expected_binding_sha256`은 등록 안의 생성 binding을 정규화한 해시입니다. 이 binding은 MOS 블록 계획·bench 계획·조건·scope의 해시에 연결됩니다. CLI는 동일한 등록·요청으로 다음처럼 호출합니다. 해시는 검토한 각 파일에 대해 앞의 PowerShell 예제와 같은 방식으로 계산합니다.

```powershell
cadence-mcp-bridge operator-research-generation --registration $registration $registrationSha plan --request $request $requestSha
cadence-mcp-bridge operator-research-generation --registration $registration $registrationSha apply --request $request $requestSha
cadence-mcp-bridge operator-research-generation --registration $registration $registrationSha status --request $request $requestSha
# VERIFIED 이후, 등록 증거 폴더 밖의 새 파일로 출력합니다.
cadence-mcp-bridge operator-research-generation --registration $registration $registrationSha handoff --request $request $requestSha --output $handoff
```

저장·독립 재개방·Netlist의 단계별 증거가 검증되면 handoff의 DUT/bench 트리 지문, Netlist 관련 지문, handoff 해시를 다음 등록에 연결합니다. MCP handoff는 해시 요약을 반환합니다. 전체 등록 후보 조립에 쓸 인계 파일은 CLI에서 내보내고 반환된 파일 SHA를 함께 보관합니다.

#### 등록 소자 편집 요청

`serve-operator --registered-mos-edit`는 운영자 context에 선택된 편집을 사용합니다. 계획 조회·적용·재조회 도구의 `request`에는 등록된 `operation_id`, `expected_plan_sha256`, `expected_scope_sha256` 세 필드를 전달합니다. 적용 후 저장·재개방·Netlist 증거가 확인된 revision을 다음 분석 등록에 연결합니다. 생성의 binding SHA나 파일 SHA를 편집의 계획·scope SHA 대신 사용하지 않습니다.

```text
cadence_lookup_registered_mos_edit({"request": {
  "operation_id": "REGISTERED_EDIT_UUID",
  "expected_plan_sha256": "EDIT_PLAN_SHA256",
  "expected_scope_sha256": "EDIT_SCOPE_SHA256"
}})
```

응답이 끊기거나 `OUTCOME_UNKNOWN`이면 같은 ID와 해시로 위 조회를 사용합니다. 조회는 보존 기록만 읽습니다. 확인되지 않은 작업은 원래 ID의 단계별 증거를 확인합니다.

두 프로필의 명령과 스키마는 개발 소스 기준입니다. 새 생성·편집 경로의 실제 Cadence 적합성은 등록 대상과 지원 속성 조합별로 검증하며, 17 MOS OTA 실행 검증은 대기 중입니다.

## 결과 조회와 Netlist 확인 예

등록된 DC 동작점(OP)은 읽기 전용 `cadence_research_device_op_result`로 조회합니다. 실제 Codex 데스크톱에서 `cadence-amp-5656-op-retained` 프로필로 조회한 결과는 `AVAILABLE`이었으며, MOS 14개에서 각각 7개씩 총 98개의 유한값을 반환했습니다. 설치본에서 독립 확인한 응답과 일치했고, 원격 접속과 새 시뮬레이션·추출·예약은 모두 0건이었습니다. 아래 MCP 호출에는 등록 카탈로그의 식별자와 성공한 DC 작업의 ID·계획 해시를 사용합니다.

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

## 현재 검증 상태

| 대상 | 확인한 결과 | 범위 |
| --- | --- | --- |
| 17 MOS 논문 OTA | 비OTA에서 검증한 8개 치수를 17개 소자에 연결했습니다. 논리 단자 68개·5포트·배치·벤치를 검토하고 DC 및 DC+AC 정적 입력을 확인했습니다. | 작업 공간 binding과 생성 뒤 관측할 revision·Netlist를 ⑤에 남겼습니다. 실제 OTA 생성·등록·분석은 보류 중입니다. |
| 정정 2 MOS 인버터 | 실제 저장·독립 재개방·구조화 검증과 Netlist 확인. 운영자 stdio MCP를 거친 Spectre DC 한 점에서 VDD 1 V, Vin 0 V, Vout 약 1.000 V. 기존 DC에서 두 MOS의 OP 14개를 반복 조회 | DC 한 점이며 `region`은 모델 의미가 미확정인 원시 코드 |
| Source9 인버터 TRAN | 이전 전압 표본에서 지연·기울기·안정화 시간 확인. 이후 공급전류를 저장한 실제 실행의 179점(0–150 ns)에서 평균 전달전력 6.6847 µW 및 에너지 1.0027 pJ 확인. 실제 앱에서도 저장 전력 조회 | 앞선 전압 전용 실행의 평균 전력은 미평가. 후속 실행은 NN·27 °C·VDD 1 V·부하 1 pF |
| 기존 14 MOS AMP와 4497 사본 | 실제 기준·사본의 DC 정적 공급전력과 AC 10 Hz 차동 이득 비교. 설치 CLI에서 기존 결과 네 건을 대조하고 Codex 앱에서 저장 비교 조회. [PR #172](https://github.com/Phjrab/cadence-mcp-bridge/pull/172) | 성능 목표와 후보 선택은 미설정 |
| 14 MOS AMP의 이전 새 사본 검증 | PM0 폭 20 µm → 120 nm, 길이 1 µm와 Minimum 유지. 독립 재개방 및 Netlist 확인. [PR #174](https://github.com/Phjrab/cadence-mcp-bridge/pull/174) | 당시 편집 요청은 `OUTCOME_UNKNOWN`, 별도 관측은 `VERIFIED` |
| 14 MOS AMP의 Codex 앱 검증 | 등록 사본에서 PM0 W/FW 120 nm, L 1 µm, Minimum과 D/G/S/B 보존. 실제 Spectre DC·AC와 원본 프레임 대조 후, 재시작한 실제 앱에서 Center와 사본의 비교를 조회. [PR #175](https://github.com/Phjrab/cadence-mcp-bridge/pull/175) · [PR #176](https://github.com/Phjrab/cadence-mcp-bridge/pull/176) | 이전 DC 실패 이력은 보존했습니다. 최종 비교는 성공한 별도 DC와 원래 AC를 사용합니다. 성능 합격 기준은 미설정 |
| 생성한 비OTA 2 MOS 인버터 | 12a0의 원래 저장·독립 재개방, 진단 Netlist, bench·ADE 증거로 별도 분석 경로를 등록했습니다. DC `2efcd005-b30d-4594-a694-3d0d5c87e0ad`가 VIN 0.5 V, VDD 1 V, 부하 1 pF에서 출력 0.404651191 V와 공급 전달 전력 16.199518 µW를 반환했습니다. | 실제 DC 입력 SHA-256 `e4d85bae999805ddd9ecac531611d3e1a584d478a7fd7c266df34c8c22b00a30`. 원래 생성 ID는 문장 순서·수치 표기 차이로 `OUTCOME_UNKNOWN`입니다. 이름을 지정한 벤치 소자의 순서와 동일 SI 값만 허용해 원본 입력을 검증했고, 별도 분석 ID에 실제 결과를 보존했습니다. |
| 작업용 Layout | 실제 Cadence에서 instance 이동, 도형·연결 pin 추가, 저장·재개방 확인. [PR #167](https://github.com/Phjrab/cadence-mcp-bridge/pull/167) | 연구 OTA Layout·DRC·LVS·PEX는 별도 단계 |

앱에서 조회한 AMP 비교는 NN, 27 °C, VDD 1 V, VBIASN 0.320 V, VBIASP 0.702 V 조건입니다.

| 지표 | Center 20 µm | 새 사본 120 nm | 사본 − 기준 |
| --- | ---: | ---: | ---: |
| 정적 공급전력 | 0.08243 mW | 1.57187 mW | +1.48944 mW |
| 10 Hz 차동 이득 | +78.952 dB | −23.724 dB | −102.676 dB |

### 소자 편집 범위

| 조합 | 호스트·MCP | 패키지 guest | 실제 Cadence 근거 |
| --- | --- | --- | --- |
| 등록 `pmos1v` 기본값 복원 | 검토된 W/FW, L 또는 동시 변경의 계획·적용·재조회 | 등록된 단일 finger 사본에서 검토된 override 제거 | 실제 Source9에서 W/FW 350 → 120 nm, L 100 nm 유지, 저장·독립 재개방·Netlist 확인. 별도 AMP 고정 편집은 20 µm → 120 nm, L 1 µm 유지. L 복원과 동시 복원의 새 실제 증거는 대기 중입니다. |
| 등록 `nmos1v`·`pmos1v`의 `SET_EXPLICIT` | 같은 master의 목표 값에 대한 독립 OA·CDF·Spectre Netlist 증거를 등록한 뒤 계획·적용·재조회 | 개발 설치본의 단일 finger 경로가 증거에 있는 W/FW/L과 검증된 종속 속성을 기록합니다. | 설치본의 로컬 검증을 통과했습니다. 지원 대상과 기대값은 등록된 조합에 한정됩니다. |
| 단일 finger의 `m` 명시 설정 | `m`과 `fingers`를 별도로 대조합니다. 치수와 `m`을 함께 바꿀 때 모든 변경을 한 작업으로 등록합니다. | 등록된 m 변경을 W/FW/L과 함께 한 작업으로 적용할 수 있습니다. `fingers`는 1로 유지하며 `nf` 편집은 지원하지 않습니다. | 후속 PDK adapter의 공통 비OTA 사본에서 PM6 대응 W/FW 16 µm, L 1 µm, m=6을 저장·재개방·Netlist로 확인했습니다. |

초기 보정 작업에서는 실제 Cadence의 MOS 8개, 포트 도형 4개, 연결 및 DUT·테스트 회로의 기준 상태를 확인했습니다. 당시 치수 변경은 0건이었고 보존된 GPDK090 MOS 넷리스트 문장 438개에는 목표 master와 W/L이 일치하는 사례가 없었습니다.

초기 `SET_EXPLICIT` 조사에서 설치된 IC6.1.5의 CDF 갱신 함수는 기존 유효값을 저장하거나 복사하는 용도로 확인됐습니다. 당시 검토한 기본 갱신 API에서는 새 치수의 접합 면적·둘레를 계산하는 비대화형 함수를 확인하지 못했습니다. 기존 `SET_EXPLICIT`는 정확한 목표 조합의 저장 OA 값, 유효 CDF 값과 같은 revision의 독립 재개방·Spectre Netlist 증거를 사용합니다. 이후 프로젝트의 자체 adapter가 아래 Source9 L200에서 설치 PDK의 계산 경로를 검증했습니다.

초기 읽기 전용 점검에서 CDF 메타데이터 60행을 독립 검증했습니다. NMOS와 PMOS 모두 기본·유효 CDF에 `formInitProc`와 `doneProc`가 있으며 각각의 식별자가 일치했습니다. 검토한 공개 v1.16 보조 도구에는 `doneProc` 실행 경로가 없어 실제 쓰기 호환성을 확인하지 못했습니다. 이 점검에서 콜백 실행·치수 변경·시뮬레이션은 0건이었습니다.

#### 신규 W/L 후보의 편집과 비교

신규 개발 경로는 프로젝트의 비대화형 adapter로 등록된 PDK 콜백을 사용합니다. Source9 비OTA L200 경로의 시작값은 W/FW 120 nm, L 100 nm, `m=1`, `fingers=1`입니다. 후속 비OTA 작업에서 두 master의 W/L 복합 변경과 공통 사본에서의 PMOS m=6도 확인했습니다. 검증된 연구 치수는 아래 별도 표에 있습니다.

| 후보 | 확인된 상태 |
| --- | --- |
| L 250 nm | 실제 등록을 읽은 개발 설치본에서 시작값 조회와 변경 계획을 확인했습니다. 실제 적용은 Cadence 시작 전 검사 코드 오류로 멈췄습니다. 설치 stdio와 실제 사용자 Codex에서 같은 ID를 조회해 `OUTCOME_UNKNOWN`을 확인했습니다. 관측 치수와 Netlist는 없으며 추가 실행·치수 변경·측정은 0건입니다. 오류 수정은 로컬에서 검증했습니다. |
| L 200 nm | 같은 기준 회로의 새 사본에서 개발 설치본 `c2858c9`의 실제 MCP 적용이 `VERIFIED`를 반환했습니다. 요청, 저장 OA, 유효 CDF, 독립 재개방 및 실제 Spectre Netlist에서 L 200 nm가 일치했습니다. W/FW 120 nm와 `m=fingers=1`이 유지됐고, Spectre 접합값은 `as=ad=69.6f`, `ps=pd=1.16u`입니다. 편집 ID를 재조회했을 때 추가 적용은 0건이었습니다. 이 revision에서 별도 Spectre DC 동작점 분석 1회가 성공했습니다. |
| PMOS W 350→3000 nm, L 100 nm 유지 | v11 전환 후 관리 사본 생성은 `VERIFIED`입니다. 편집을 한 번 실행해 PDK 초기화·폭 콜백·후처리와 저장 전 검사 준비 표식까지 확인했습니다. 실행 시간 한도에 도달해 저장 영수증과 독립 재개방·Netlist 증거는 확보되지 않았습니다. 읽기 전용 대조에서 사본의 주 회로 파일과 기존 DUT 파일은 원본과 바이트 단위로 일치했습니다. 같은 ID의 설치 MCP 조회는 `OUTCOME_UNKNOWN`을 반환했습니다. 검증된 저장 폭과 후보 측정값은 없으며 재시도는 0건입니다. |

L200 편집 작업 ID는 `53cbd04e-0106-48c6-be9a-560622bce48f`, 실제 Netlist SHA-256은 `25c25e5a49f54932456bea607f4c02fcf18e97b19d2945b481814a8d7fee3610`입니다.

PMOS 편집 작업 ID는 `4bc032e5-29c0-4418-8c8c-bb9be5c3f4d6`입니다. 사본의 백업·잠금 흔적, 원본 Source9 및 편집 전의 예약 기록 147건을 보존했습니다. 사용자 Codex 앱의 W3000 동일 ID 조회는 설치본 응답과 일치했습니다. 결과는 `OUTCOME_UNKNOWN`, 관측값 없음이며 새 실행·시뮬레이션·예약은 모두 0건이었습니다. 이 PMOS 후보의 성능 측정은 없습니다.

아래는 L200 프로필의 읽기 전용 MCP 호출 예시입니다. 계획에 사용할 등록·기준 해시는 inspect에서, 재조회에 사용할 계획·범위 해시는 plan에서 받습니다. 실제 사용자 Codex에서 `cadence_lookup_registered_mos_sizing`으로 같은 작업 ID를 조회해 W 120 nm·L 200 nm의 `VERIFIED` 결과를 확인했습니다. 설치 MCP stdio의 응답과 일치했고 추가 적용·시뮬레이션·예약은 0건이었습니다.

같은 Codex 프로필에서 inspect는 `DUT/MN`의 시작값 W 120 nm·L 100 nm와 등록 구간 L 200–250 nm를 반환했습니다. `0.2 um` 계획은 200 nm로 정규화됐고 기존 계획·범위 해시와 일치했습니다. DC 실행 전의 앱 compare는 편집 `VERIFIED`, 분석 `NOT_RUN`을 반환했습니다. 등록 구간에서 실제 편집을 검증한 값은 L 200 nm입니다.

```text
cadence_inspect_registered_mos_sizing({})
cadence_plan_registered_mos_sizing({"request": {
  "operation_id": "ENROLLED_L200_EDIT_UUID",
  "expected_enrollment_sha256": "ENROLLMENT_SHA256",
  "expected_baseline_sha256": "BASELINE_SHA256",
  "values": {"l": {"value": "0.2", "unit": "um"}}
}})
cadence_lookup_registered_mos_sizing({"request": {
  "operation_id": "ENROLLED_L200_EDIT_UUID",
  "expected_plan_sha256": "EDIT_PLAN_SHA256",
  "expected_scope_sha256": "EDIT_SCOPE_SHA256"
}})
cadence_compare_registered_mos_sizing({"request": {"edits": [{
  "operation_id": "ENROLLED_L200_EDIT_UUID",
  "expected_plan_sha256": "EDIT_PLAN_SHA256",
  "expected_scope_sha256": "EDIT_SCOPE_SHA256"
}]}})
```

#### Source9 DC 동작점 비교

Source9 동일 원본의 세 독립 사본에서 편집한 소자의 요청 W/L이 저장 OA, 재개방 CDF와 진단 Netlist에서 일치했습니다. 각각 m=1, finger=1입니다. 보존한 기준 DC와 세 후보 모두 VIN 0 V, VDD 1 V, 부하 1 pF, 모델 섹션 NN, 27 °C에서 동일한 reader로 측정했습니다.

| 사본 및 편집 소자 | 적용 W/L (µm) | 출력 (V) | 기준 대비 출력 (µV) | 공급 전달 전력 (nW) |
| --- | ---: | ---: | ---: | ---: |
| 원본 (NMOS / PMOS) | 0.12/0.10 · 0.35/0.10 | 0.999925882 | — | 25.366091 |
| L200 · NMOS | 0.12/0.20 | 0.999993267 | +67.384 | 2.443526 |
| CalP01 · PMOS | 3/0.25 | 0.999974791 | +48.908 | 31.613981 |
| CalN02 · NMOS | 1.5/0.25 | 0.999985713 | +59.830 | 5.013445 |

아래 지문은 SHA-256의 앞 12자리입니다. 독립 재개방한 DUT와 해당 사본에서 실제 DC에 사용한 입력을 구분해 추적할 수 있습니다.

| 후보 | 편집 ID | DC 분석 ID | DUT revision | 진단 Netlist | 실제 DC 입력 |
| --- | --- | --- | --- | --- | --- |
| L200 | `53cbd04e-0106-48c6-be9a-560622bce48f` | `155ca51f-c3c1-46d0-8982-bbbb76f95b82` | `2ca5e78872b0` | `25c25e5a49f5` | `3d9869846934` |
| CalP01 | `019ed03a-8a28-4234-bca2-57c31cca6af5` | `92341430-4d75-4f2b-93db-7da41c1a808a` | `28b2f162473d` | `ee8bbb2e7895` | `dddf90397056` |
| CalN02 | `b6bc7a48-78c8-4556-b9c6-a60271722b55` | `8369cc28-a440-408d-a86e-264d544bda64` | `bca3055f9472` | `83a74132888e` | `ba3f20b9d089` |

DC 분석 작업 ID는 `155ca51f-c3c1-46d0-8982-bbbb76f95b82`입니다. 실측 보고서 SHA-256은 `2a2549fe60672e386e615bf286e60e5731a369561b293a409892df4b73beb1a2`, 실제 실행 입력 SHA-256은 `3d9869846934e0760fefb10969e3b6750f7816b4146f240bf3e1d99d7e021402`입니다. 같은 분석 ID를 설치 환경에서 재조회한 결과는 최초 완료 기록과 일치했고, 예약은 승인된 한 건만 추가됐습니다. 사용자 Codex 앱에서도 `cadence-l200-dc-retained`의 읽기 전용 비교로 `SUCCEEDED / COMPARABLE`과 위 실측값을 확인했습니다. 앱 조회에 따른 새 실행과 예약은 0건입니다. L250과 W3000은 `OUTCOME_UNKNOWN` 상태이며 후보 측정값이 없습니다.

후보마다 요청 치수·단위를 기록하고, 같은 기준 revision을 사용할지 직전 편집을 이어갈지 정합니다. 실제 편집의 확인 순서는 PDK 처리·회로 검사·저장 → 별도 세션 재개방 → 실제 Spectre Netlist에서 W/L/m과 종속 접합값 대조입니다. 비교에는 해당 revision의 편집 ID·분석 ID·Netlist SHA와 실제 적용값·측정 조건·결과 단위를 함께 기록합니다. 새 분석은 등록된 실행 범위와 남은 후보·분석·저장 한도를 확인한 뒤 제출합니다. 기존 설계 변수 sweep은 등록 변수의 값을 바꿔 분석하는 기능입니다. W/L 편집 결과로 집계하려면 후보별 PDK 처리와 새 Netlist 증거가 필요합니다.

### 측정 범위

| 항목 | 범위와 남은 확인 |
| --- | --- |
| OP | 실제 Codex 데스크톱의 읽기 전용 MCP에서 BBE3 DC의 2 MOS × 7개와 AMP5656 DC의 14 MOS × 7개를 확인했습니다. 인스턴스·항목별 단위와 부호가 유지되며 모델 근거가 없는 `region`은 원시 코드로 남습니다. 17 × 7개 선언은 64개 인스턴스 한도 안에 들며 실제 OTA selector와 64 KiB 프레임 한도는 생성 후 확인합니다. |
| AC | 실제 새 AMP 사본의 71점(10 Hz–100 MHz)에서 복소 전달비와 10 Hz 이득을 재현했습니다. 10 Hz 기준 −3 dB와 0 dB 하강 교차는 모두 표본 범위에서 미관측입니다. 약 487,663 Hz의 −3 dB 대역폭은 별도 과거 후보입니다. Center는 10 Hz 이득을 확인했고 전체 표본이 없어 교차는 미평가입니다. 단일 출력 OTA의 실제 복소 데이터와 위상여유용 loop-gain은 별도입니다. |
| TRAN | 실제 Source9는 top-level 공급원의 `PLUS` 전류와 검증된 0 V 기준을 사용했습니다. 평균 전달전력은 `−(V+−V−)×I(+)`를 시간 적분한 뒤 관측 시간으로 나눕니다. 등록 전압은 최대 8개, v2 공급전류는 최대 6개, 벡터는 채널당 256점 및 전체 1536점까지입니다. 긴 원본 벡터는 상한을 넘으면 거부합니다. 표시용 축소는 측정 구간 추출과 구분합니다. |

### 첫 OTA 생성에 필요한 확인

| 확인 시점 | 항목 | 상태 |
| --- | --- | --- |
| 생성 전 | GPDK090 master·모델·단자 | 기존 Source9·BBE3에서 두 `gpdk090` symbol master와 D/G/S/B 순서, `gpdk090_nmos1v`·`gpdk090_pmos1v` 모델 및 NN 섹션을 실제 확인했습니다. OTA용 NN 의존 파일과 벌크·단자 결속은 별도 검토합니다. |
| 생성 전 | GPDK090 소자별 치수 | 아래 8개 모두 비OTA 저장값, 독립 재개방 OA·유효 CDF, 같은 revision의 실제 Spectre W/L/m과 접합 면적·둘레가 일치했습니다. DC 전용과 DC+AC 정적 입력에서 17개 모두에 근거를 연결했습니다. |
| 생성 전 | 소스·부하 | VDD 1 V와 공통모드 0.5 V, `out`에서 VSS로 연결한 1 pF를 정적 bench에 선언했습니다. 1 V 공급과 1 pF 부하는 기존 두 MOS 회로의 실제 Netlist에 관측됐습니다. 선택형 `vsin`은 5656의 실제 OA·CDF·실행 Netlist에서 두 입력 DC 0.5 V와 AC ±0.5 V를 확인했습니다. OTA에는 선택한 소스·부하의 단자·CDF·분석 조건을 별도로 결속합니다. `vsin` 증거는 AC 전용이며 첫 DC/OP에는 별도 고정 소스 조건을 사용합니다. |
| 생성 전 | 실제 ADE seed와 실행 계획 | 기존 두 MOS의 seed 재사용 계획과 로컬 Netlist 비교를 참고합니다. 작업 공간의 실제 소유 대상, seed ADE 트리 및 분석 조건, NN 모델 의존 파일, 준비 프로그램을 대조합니다. |
| 생성 후 | 저장본과 측정 선택자 | 실제 저장·독립 재개방 후 DUT·심볼·bench·ADE 트리와 유효 Netlist를 연결합니다. 이때 얻은 revision 및 `out/inp/inn`, 전원 양단, 공급원의 `PLUS` 전류와 DUT 아래 17개 MOS 경로를 실제 reader와 분석 작업에 연결합니다. |

연구용 목표값은 단일 finger, W=FW 기준입니다. CalN02와 CalP01은 별도 비OTA 제품 편집에서 검증했습니다. 나머지 여섯 점은 하나의 비OTA 보정 사본에 저장한 뒤 독립 재개방과 실제 Netlist로 검증했습니다.

| Master | 목표 `(W µm, L µm, m)` | 적용할 OTA 소자 | 비OTA 검증 |
| --- | --- | --- | --- |
| `nmos1v` | `(1, 0.25, 1)` | NM2, NM3, NM10 | 공통 CalN01 |
| `nmos1v` | `(1.5, 0.25, 1)` | NM0, NM1 | 개별 CalN02 |
| `nmos1v` | `(10, 0.25, 1)` | NM6, NM7, NM11 | 공통 CalN03 |
| `nmos1v` | `(15, 0.25, 1)` | NM8, NM9 | 공통 CalN04 |
| `pmos1v` | `(3, 0.25, 1)` | PM2, PM3, PM8 | 개별 CalP01 |
| `pmos1v` | `(30, 0.25, 1)` | PM4, PM5 | 공통 CalP02 |
| `pmos1v` | `(10, 1, 1)` | PM7 | 공통 CalP03 |
| `pmos1v` | `(16, 1, 6)` | PM6 | 공통 CalP04 |

**목표 치수 8/8과 68개 논리 단자 연결을 확인하고 17개 OTA 소자의 정적 입력에 근거를 연결했습니다.** DC 전용과 DC+AC 두 입력은 검토한 토폴로지 및 실제 비OTA 치수 증거를 참조합니다. 실제 작업 공간 binding은 ⑤를 시작할 때 선택한 소스·부하, ADE seed 및 NN 모델의 지문을 대조한 뒤 기록합니다.

연구 단계 ⑤를 시작할 때는 `--static-preview`로 회로 구조를 확인하고, 17개 소자의 D/G/S/B·벌크와 선택한 소스·부하·ADE seed·NN 근거를 검토합니다. 실제 작업 공간의 원본 지문으로 `DraftPort.binding`을 작성한 뒤 `compile-research-draft`와 `validate-research-circuit`를 실행합니다. 이후 승인된 실제 생성·저장과 독립 재개방에서 얻은 revision·인스턴스 경로·Netlist를 reader 및 분석 등록에 연결합니다.

#### P4 증거를 정적 포팅 입력에 연결

W/L/m 검증이 포함된 개발 환경에서 [오프라인 결속 도구](bind-ota-port-evidence.py)를 실행합니다. 승인된 비OTA 검증의 출력은 두 경로로 연결합니다.

- **개별 편집 2개** — 매니페스트 `points`에 NMOS `(1.5, 0.25, 1)`와 PMOS `(3, 0.25, 1)` 중 독립 검토를 마친 자료만 넣습니다. 각 행은 `MosSizingPlan`(`plan`), 같은 ID의 `RegisteredMosSizingResult`(`lookup_result`), 원본 독립 재개방 CDF(`cdf`)와 Spectre 입력(`netlist`)을 참조합니다.
- **공통 사본 6개** — C6의 검증기가 원본 setup·저장·독립 재개방/Netlist 영수증과 소자별 OA/CDF·Spectre 원본을 검증한 뒤 내보낸 `VERIFIED_FIXTURE_TUPLES` 보고서 하나를 `fixture_report`에 넣습니다. 소자별 근거는 공통 배치 ID, 사본 내 인스턴스 이름, 검증 행의 SHA-256으로 구분합니다. 여섯 소자의 Spectre 근거는 같은 원본 Netlist에 연결됩니다.

파일 참조는 매니페스트 디렉터리 기준 상대 `path`와 실제 바이트의 `sha256`을 담습니다. 포팅 입력·매니페스트·검증 보고서의 해시는 독립 검토 기록과 대조합니다. 증거가 없으면 `{"points": []}`를 사용합니다.

```powershell
python docs/examples/research/bind-ota-port-evidence.py `
  --draft $draft $draftSha --port $staticPort $staticPortSha `
  --reviewed $reviewedManifest $reviewedManifestSha --output ota-port.evidence.static.json
```

일치하는 목표 조합의 소자에만 `geometry.source`와 `spectre.source`를 연결합니다. 일부 목표의 증거만 있으면 나머지 소자를 `unbound_devices`에 남기며, 불완전한 증거 행·중복·불일치는 오류로 반환합니다. 출력은 binding 없는 정적 입력입니다. 별도 bench·ADE·NN 검토와 실제 작업 공간 지문은 위 순서로 결속합니다.

최종 정적 입력의 `topology_source`는 Fig. 2-12의 논리 배선과 실제 master의 Spectre 단자 순서를 대조한 기록을 가리킵니다. 각 소자의 `master_source`는 비OTA에서 관측한 GPDK090 심볼 단자 근거입니다. 논문 원본과 Table 7의 치수는 초안 지문으로 추적할 수 있습니다. ⑤를 시작하면 선택한 고정 소스 또는 AC용 `vsin`, 부하, ADE seed, NN 모델의 실제 파일을 보존한 지문과 대조합니다. 생성 후에는 새 DUT·bench·ADE와 실제 Netlist를 기록하고, 독립 재개방으로 관측한 경로를 reader에 연결합니다.

## 재개 프롬프트

> OTA 연구를 시작해줘. 이 README와 `ota-17mos.draft.json`을 읽고 최신 검증 설치본의 `tools/list`와 연구 범위를 확인해줘. GPDK090의 단자·벌크·CDF 매핑과 PM6 배수, 테스트벤치를 먼저 확정해줘. 확정 입력으로 `ResearchCircuit`을 구성한 뒤 정의 검증·계획 → 생성·저장 → 독립 재개방·Netlist 대조 → 대상·reader 등록 → DC/OP·AC 계획·제출·상태·결과 → 같은 ID 재조회 순으로 진행해줘. 계획 해시는 계획에서, 저장 revision과 아티팩트 지문은 생성·독립 재개방에서, 분석 작업 ID는 제출 때 기록하고 다음 호출에 연결해줘. 항목이 미확정이거나 실행이 불명확하면 해당 단계에서 멈추고 기존 증거와 ID로 상태를 확인해줘.
