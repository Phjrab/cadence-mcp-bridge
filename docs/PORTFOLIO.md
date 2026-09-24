# Cadence MCP Bridge — 포트폴리오 근거 (2026-09-24)

이 문서는 공개 저장소 `main`의 `ece52c7a44befe34d61215c19f9fa39ab2af5384`를
읽어 작성한 설명 초안입니다. 당시 실행 기록과 현재 이 환경에서 새로 실행한 검증을
구별합니다. 실제 Cadence/SSH/VM 작업은 이 문서 작업에서 수행하지 않았습니다.

## 문제와 접근

레거시 Cadence 환경의 시뮬레이션 작업은 여러 명령과 결과 파일, 원격 환경의 상태를
함께 확인해야 합니다. 자연어 AI가 이 과정을 보조하더라도 임의 명령과 설계 데이터에
접근하게 하면 검증 결과를 추적하기 어렵습니다. 이 프로젝트는 AI client의 선택을
typed MCP tool로 제한하고, 실행은 allowlist가 있는 service와 고정 SSH runner에 맡깁니다.
job ID, 상태, bounded 로그·결과와 감사 기록으로 작업의 경계를 남깁니다.

| 구분 | 실제 역할과 근거 | 한계 |
|---|---|---|
| 제품 안의 AI | client가 허용된 tool을 호출하고 구조화된 결과를 읽음 ([서버 도구](../src/cadence_mcp_bridge/server.py)) | 서버는 범용 AI 회로 설계기가 아님 |
| 결정적 실행 | service/backend/runner가 고정 job과 allowlist를 적용 ([Architecture](ARCHITECTURE.md)) | 원격 결과는 당시 환경·버전에 종속 |
| 로컬 측정 | synthetic ADC 입력을 버전 계약에 따라 계산 ([계약](ADC_MEASUREMENT_CONTRACTS.md)) | 실제 ADC 회로/Monte Carlo 측정 아님 |
| 제한된 설계 변경 | 승인된 복사본의 단일 속성 검증과 rollback ([정책](DESIGN_WRITE_POLICY.md)) | 임의 토폴로지 합성·최적화 아님 |

## 대표 검증 사례

1. **v1 controlled write** — V4의 18개 수용 기준은 복사본 생성, 비변경
   dry-run, backup, 한 속성 적용, 정확한 diff, rollback과 보호 대상 불변성을
   확인한 과거 실환경 기록입니다. 이 숫자는 설계 품질이나 예측 정확도가 아닙니다.
   [릴리스 노트](RELEASE_NOTES_v1.0.0.md)와 [정책](DESIGN_WRITE_POLICY.md)을 근거로 합니다.
2. **WP-14 fail-closed 경계** — 로컬 repo runner 후보는 `0.19.0`, 마지막
   문서상 원격 관측은 `0.18.0`입니다. 첫 narrow deployment는 preflight transport
   단계에서 중단되어 원격 설치와 최종 검증에 도달하지 않았습니다
   ([실패 기록](WP14_NARROW_DEPLOYMENT_RESULT_V2.md)).
   `LOCAL_RULE_READY`는 당시 로컬 규칙 계산 가능의 의미이며 새 원격 증거나
   실행 승인으로 승격하지 않습니다 ([상태](../PROJECT_STATE.md)).

WP-14의 `0.300 V / 0.650 V`는 조건부 선택입니다. VDD·입력 공통모드·부하,
source/ADE revision 일치와 증거 freshness가 미확인이라 scientific baseline은
승인되지 않았습니다. `0.370 V / 0.650 V` 연구 후보를 같은 baseline으로 합치지
않습니다 ([V4 decision](decisions/WP14_VBIAS_DECISION_RECORD_V4.json)).

## 개발 과정의 AI 활용과 개인 기여

저장소에는 [작업 계약](../CODEX_MASTER_PROMPT.md), 단계 계획, 검증 보고서, 커밋
이력이 있어 작업을 작은 단위로 지시하고 결과를 확인한 흐름을 추적할 수 있습니다.
다만 이 자료만으로 특정 소스 줄을 누가 직접 작성했는지, 어떤 AI 모델을 실제로
썼는지, 개인별 기여율이나 시간 절약을 확정할 수 없습니다. 지원서의 1인칭 기여
문장은 아래 확인 후 작성합니다.

| 확인할 항목 | 필요한 근거 |
|---|---|
| 본인이 정한 실행·보안 경계 | 당시 요구사항·review/approval 기록과 본인 역할 확인 |
| AI에 맡긴 구체적 작업 | 실제 대화·작업 지시와 수정/리뷰 기록 |
| 본인이 검증·수정한 결정 | 테스트 실패 분석, 수용·거부 판단의 본인 기록 |
| 회로/PDK에 대한 본인 책임 | 실제 담당 범위와 공개 가능한 증거 |

작품 설명에는 사람이 목표·허용 범위를 정하고, AI가 제한된 인터페이스의 사용을
보조하며, 결정적 검증이 결과를 걸러내는 구조를 적을 수 있습니다. 이는 제품 설계
설명이지 개인 기여를 확정하는 문장이 아닙니다.

## 공개 재현과 환경

`pyproject.toml`은 Python `>=3.12,<3.14`를 지원합니다. 다음은 Windows 개발
환경에서 Cadence 없이 로컬 구현을 확인하는 명령입니다. 이 문서 작업 중 새로
실행한 결과가 아니며, `test_server.py`의 FakeBackend는 실환경 검증이 아닙니다.

```powershell
uv sync --frozen --all-groups
uv run python -m cadence_mcp_bridge --help
uv run python -m cadence_mcp_bridge --version
uv run pytest tests/unit/test_measurements.py tests/unit/test_server.py
```

실환경 실행 조건과 사용 가능한 도구는 [운영 문서](OPERATIONS.md),
[검증 환경의 당시 기록](VERIFIED_ENVIRONMENT.md), [보안 경계](SECURITY.md)를
따릅니다. 과거 환경의 성공은 현재 VM, 회로, 라이선스의 준비 상태를 보장하지 않습니다.

## 공개 화면 촬영 목록

현재 저장소에 연결할 공개 가능 실제 화면은 확인되지 않았으므로 README에 그림을
넣지 않았습니다. 아래 장면은 원본·날짜·실행 SHA·환경·검증 종류를 기록한 뒤에만
공개합니다. 계정, 호스트, 사설 IP, 라이선스, PDK, netlist, raw PSF, 설계 값을
공개 사본에서 제외합니다.

| 장면 | 입증할 내용 | 반드시 적을 범위 |
|---|---|---|
| MCP 연결과 tool 목록 | AI 요청의 제한된 진입점 | 실제 client 화면, 설정 비식별 |
| 과거 smoke job 상태→결과 | 추적 가능한 job lifecycle | 당시 날짜/버전, fixture인지 actual인지 |
| synthetic ADC 입력→출력 | 구조화된 로컬 계산 | 화면과 캡션 모두 `synthetic` |
| V4 결과 요약 | 승인 복사본의 diff·rollback | 과거 V4 기록, 설계 원문 제외 |
| WP-14 중단 상태 | drift와 fail-closed 경계 | 미배포·미승인 상태 명시 |

## GitHub 설명 변경안 (미적용)

- About: `Restricted MCP bridge for AI-assisted Cadence simulation jobs and verifiable results`
- Topics: `mcp`, `python`, `cadence`, `spectre`, `eda`, `simulation-automation`
- v1.0.0 Release 본문 상단 정정안: `Cadence MCP Bridge v1.0.0 was published on
  2026-08-31 from the reviewed tag. The repository is now public. The
  release-preparation notes below describe the earlier candidate checkpoint;
  they do not indicate that publication is still pending.`

공개 저장소와 published release는 확인했지만, 공개 재사용 라이선스는 별도 확인이
필요합니다. 위 변경안은 원격 메타데이터나 Release 본문에 적용하지 않았습니다.
