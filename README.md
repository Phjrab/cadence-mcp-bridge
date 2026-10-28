# Cadence MCP Bridge

교수님 제공 **CentOS·Cadence·PDK 표준 VM**을 개인 VMware에서 사용하는 운영자가
자기 회로를 등록하고, MCP 클라이언트에서 허용된 DC·AC·TRAN, 제한된 1D Sweep과
결과 조회를 수행하는 브리지입니다. 등록된 회로는 공통 템플릿을 사용합니다.

## 현재 공개 안정판

**[v2.1.0 다운로드 — GitHub Releases](https://github.com/Phjrab/cadence-mcp-bridge/releases/tag/v2.1.0)**

공개 commit: `36f75834b8556c9dd88761120a4442a25379d7ae`.
Release의 wheel, `locked-runtime-2.1.0.txt`, `SHA256SUMS`, 설치 안내를 함께 받으세요.

| 구분 | 현재 상태 |
| --- | --- |
| 공개 안정판 | **2.1.0**, 공개된 9개 파일 |
| main | **2.2.0.dev0** 미출시 개발 코드. PR #163 후보 묶음 포함 |
| [PR #164](https://github.com/Phjrab/cadence-mcp-bridge/pull/164) | 미병합 source-binding 관찰 작업. 실제 후보 실행 미완료 |
| Windows 간편 설치 EXE | 별도 개발 중. 아직 공개 다운로드 없음 |

[2.1.0 설치](docs/releases/2.1.0/INSTALL.md)·[검증 범위](docs/releases/2.1.0/QUALIFICATION.md)의
“candidate” 표현은 후보 평가 당시 기록입니다. 현재 공개 여부는 위 Release가 기준이며
기존 v2.0.0/v2.1.0 배포 파일과 당시 문서를 변경하지 않습니다.

## 지원 환경과 준비물

- Windows 호스트의 MCP 클라이언트, 교수님 제공 VM과 기존 PDK, 해당 제품 이용 권한.
- 켜진 VM, 일반 게스트 계정, 자신의 SSH 주소/별칭·인증·호스트 키.
- 자신의 작업 경로, library/cell/view·저장된 ADE 상태, registry·journal·결과 위치.
- 자신의 자원 한도와 승인된 실험 범위. 개발자의 계정·과거 UUID·장부를 복사하지 않습니다.

기존 현장 관측은 Windows/Python 3.12.10, CentOS 6.5/i686/Python 2.6.6,
Virtuoso IC6.1.5.500.15, Spectre 12.1.0.347.isr3입니다. 각 설치의 실제 preflight를
대신하지 않습니다. Windows x64 호스트와 i686 게스트는 다른 아키텍처입니다.
다른 PC·Cadence 버전·PDK·클라우드는 검증 범위 밖입니다. VM·Cadence·PDK·라이선스는 배포하지 않습니다.

## 설치

간편 설치기는 **미공개**입니다. 현재 안정판은 Python 3.12와 Windows OpenSSH Client를
준비하고 다음 수동 경로로 설치합니다. 전체 해시 검사는 [설치 안내](docs/releases/2.1.0/INSTALL.md)를 따르세요.

```powershell
Get-FileHash -Algorithm SHA256 .\cadence_mcp_bridge-2.1.0-py3-none-any.whl
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r locked-runtime-2.1.0.txt
.\.venv\Scripts\python.exe -m pip install --no-deps .\cadence_mcp_bridge-2.1.0-py3-none-any.whl
.\.venv\Scripts\python.exe -m cadence_mcp_bridge --version
.\.venv\Scripts\python.exe -m cadence_mcp_bridge doctor
.\.venv\Scripts\python.exe -m cadence_mcp_bridge operator-starter --output .\my-operator-setup
```

파일 해시는 Release의 `SHA256SUMS`와 대조합니다. checksum 일치는 내용 무결성 검사이며
그 자체가 배포자 서명은 아닙니다. 미공개 EXE를 안정판 파일로 안내하지 않습니다.

## 최초 VM·Codex 연결

내보낸 `my-operator-setup/README.md`와 [설정 도우미](docs/POST_01_OPERATOR_SETUP.md)를 따릅니다.

1. 기존 설치는 `operator-setup guide --mode existing`, 실제 이력이 없는 설치는
   `--mode fresh` 안내를 선택합니다. 새 호스트라고 새 VM 장부를 만들지 않습니다.
2. 본인의 환경·회로·PDK 계약을 `operator-setup check`로 확인하고 `export-runtime`으로
   설정합니다. 예제의 가상 값은 production 값이 아니며 개발자 private journal은 필요하지 않습니다.
3. 읽기 전용 환경 검사, 필요한 관리자 보정, 장부 연결, 회로 등록, native 묶음·승인·preflight를
   순서대로 수행합니다. 원격 변경은 정확한 별도 동의가 필요합니다.
4. `operator-setup export-client`로 선택한 context의 Codex 설정을 내보내고 기존 설정을
   보존하며 연결합니다. 새 운영자는 `serve-operator`를 사용합니다.
5. 회로·분석·입력·예산을 확인한 뒤 첫 작업을 별도로 제출합니다.

설치, 로컬 설정, MCP 등록, VM 연결, preflight, 회로 등록, 실행 승인은 각각 다른 상태입니다.
import·doctor·서버 시작은 VM 설치나 시뮬레이션을 하지 않습니다. 설정이 없으면
`SETUP_REQUIRED`이며 개발자의 VM에 자동 접속하지 않습니다.

## 주요 기능과 검증 범위

| 기능 | 배포/코드 상태 | 실제 증거와 한계 |
| --- | --- | --- |
| 등록형 DC·AC·TRAN·1D Sweep·결과 조회 | 안정판 2.1.0 | 표준 VM의 서로 다른 두 신규 회로에서 2.0.0 출시 당시 실행·자동 추출 검증 |
| 설정 도우미·기능 안내·결과 보고서 | 안정판 2.1.0 | 로컬/설치본 검증. 보고서 생성은 시뮬레이션을 재실행하지 않음 |
| DC 추출 전용 복구 | 명시적 실험 기능 | 등록 inverter DC 한 경로 실제 검증. 원래 실패·PSF와 새 추출 이력 보존 |
| 제한된 아날로그 측정 | 실험 기능 | 측정 정의·조건·샘플 한계 적용. 일반 PM/Offset/Slew 검증 아님 |
| 로컬 설계 계획·좁은 회로 생성 | 실험적 operator 경로 | 관측 CDF inverter의 OA 생성·DC/TRAN 사례. 일반 편집/최적화 아님 |
| 전압/전류 후보 2~16개 비교 | **main 미출시**, 실행 기본 비활성 | 소프트웨어·보관 결과 비교 검증. 새 native 후보 실행 qualification 미완료 |
| W/L 혼합·일반 최적화·layout·DRC/LVS/PEX | 미완료/미지원 | 파일 존재나 synthetic 계산은 실제 지원 증거가 아님 |
| 실제 앱 | 2.0.0 Codex 신규 작업·조회·재시작 증거 | 2.1.0 전체 앱 업그레이드 검증 아님. 추가 Claude 검증은 사용자 지시로 제외 |

`cadence://feature-guidance` 또는 `operator-features`에서 현재 가능한 기능을 확인합니다.
`REQUIRES_EXECUTION_CHECKS`는 실행 승인이 아닙니다. 결과는 값·단위·정의·조건·ID·출처를
보존합니다. [기능 안내](docs/POST_02_FEATURE_GUIDANCE.md) · [보고서](docs/POST_03_RESULT_REPORTS.md)

## 업데이트·제거·복구

프로그램과 사용자 설정·registry·journal·승인·결과를 분리합니다. 호스트 패키지와 VM
native runtime 변경은 별도 작업입니다. 호스트 업데이트만으로 원격 배포·실행 권한이 생기지 않습니다.
활성 작업을 강제 종료하거나 사용량을 초기화하지 마세요.

응답 유실·재시작 뒤에는 **같은 UUID와 plan**을 조회합니다. 실패·불명 상태를 새 ID로
재실행하지 않습니다. 제거해도 원격 회로·장부·결과와 외부 설정은 보존합니다.
검증된 조합의 [업데이트·복구 안내](docs/releases/2.1.0/INSTALL.md)를 따르세요.

## 자주 발생하는 문제

| 상태 | 다음 조치 |
| --- | --- |
| `SETUP_REQUIRED` | 본인 runtime과 context 등록 |
| SSH 없음·인증 실패·호스트 키 불일치 | OpenSSH·인증 확인. 호스트 키 검사 유지 |
| `executable_permissions` | VM 소유자가 정확한 보정/원복 계획 검토 후 적용·재검사 |
| `authority_inactive` | 승인 범위·만료·소비량 확인. 소진 승인 재사용 금지 |
| 예산·디스크 부족 | 실제 누적 장부/여유 확인. 실패 소비와 디스크 검사 유지 |
| 입력·추출 실패 | 같은 ID와 증거 보존 후 등록·적용 입력·추출 경로 확인 |
| Codex 연결 누락 | `CODEX_HOME`과 프로젝트 설정 우선순위 확인 후 필요한 재연결 |

## 미출시 개발과 로드맵

Windows x64 EXE·전용 런타임, 기존 설정 가져오기, 최초 안내 화면과 안전한 Codex 설정
적용은 별도 개발합니다. 실제 공개 파일 확인 전 다운로드 버튼을 추가하지 않습니다.
[게시 후 README 전환 조건](docs/WINDOWS_INSTALL_README_TRANSITION.md)

main의 [명시적 후보](docs/EXPLICIT_CANDIDATES_01.md)와 PR #164는 설치기와 독립 작업입니다.
W/L·자동 최적화·물리 설계는 후속 범위입니다. [PROJECT_STATE](PROJECT_STATE.md)의
과거 checkpoint를 현재 공개 사실로 해석하지 마세요.

## 기여·라이선스·고급 운영

[기여](CONTRIBUTING.md) · [보안](SECURITY.md) ·
[전체 최초 설정](src/cadence_mcp_bridge/operator_starter/README.md) ·
[회로 생성 증거](docs/M2_OWNED_INVERTER_01.md) ·
[물리 메타데이터 개발 기록](docs/M2_PHYSICAL_METADATA_01_STATUS.md)

Windows/Linux CI는 Cadence 없는 합성/설치 검증입니다. Windows Server CI 성공은 모든
Windows 10/11 PC나 실제 앱·VM의 성공을 뜻하지 않습니다. 원본 코드는 [Apache-2.0](LICENSE),
외부 제품과 의존성은 각자의 조건을 따릅니다. [배포 권리](THIRD_PARTY_NOTICES.md)와
[계획 자료 제외 정책](docs/AGENT_PLAN_EXPORT_BOUNDARY_V1.md)을 확인하세요.
새 GitHub Release는 정확한 후보 승인 후 게시하며 PyPI·MCPB는 별도 결정입니다.
