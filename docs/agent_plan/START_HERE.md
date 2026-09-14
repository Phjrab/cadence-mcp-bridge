# 여기서 시작 — Cadence MCP 최종 통합 프롬프트 패키지

**이 패키지는 잃어버린 실행 문서의 복구본과, 재점검 결과를 반영한 새 통합 실행 계획이다. Cadence MCP 구현 코드나 최신 저장소 백업은 아니다.**

- 패키지 문서 버전: `2.0.0` / 작성일: `2026-09-05`
- 대상: `Phjrab/cadence-mcp-bridge`
- 최종 목표: 사양 → 회로·시험환경 → 시뮬레이션·최적화 → 레이아웃 → DRC/LVS/ERC → PEX → post-layout → 공식 제작 PDK → chip top·GDS 제출 준비 → 실리콘 측정.
- 첫 실행: **문서 통합만**. 실제 회로·PDK·runner·진행 중인 작업에는 쓰지 않는다.
- 기존 WP-00~WP-11, 이후 WP, V1~V4 이력 및 기존 release/tag는 보존한다.

## 1. 지금 실제로 할 일

1. ZIP을 `Downloads` 등 임시 위치에 풀어 `CADENCE_MCP_FINAL_PROMPT_PACKAGE` 폴더를 만든다. **기존 저장소 루트에 파일을 덮어쓰지 않는다.**
2. Codex에서 실제 사용 중인 `cadence-mcp-bridge` 로컬 저장소를 연다. 패키지 폴더를 첨부하거나 Codex가 읽을 수 있는 위치로 제공한다.
3. 아래 시작 문장을 입력한다. 처음부터 전체 roadmap 또는 과거 approval 파일을 실행하지 않는다.

```text
첨부한 CADENCE_MCP_FINAL_PROMPT_PACKAGE의 START_HERE.md와 IMPORT_PROMPT.md를 읽어라.
실제 로컬 cadence-mcp-bridge 저장소의 AGENTS.md, CODEX_MASTER_PROMPT.md,
PROJECT_STATE.md, 현재 branch 및 변경사항을 먼저 확인하라.
이번 실행은 IMPORT_PROMPT.md에 정의된 PKG-INTEGRATE-01 문서 통합 작업만 수행한다.
기존 진행 이력을 reset하지 말고, 현재 실행 계약의 더 강한 제한을 유지하라.
회로/PDK/ADE state/remote runner/job/기존 V1~V4 evidence를 변경하지 마라.
가능한 문서 검증 후 전용 feature branch에 commit/push하고 원격 SHA를 확인한 뒤 STOP하라.
merge, tag, release, deployment, 실제 Cadence 실행은 하지 마라.
현재 진행 중인 WP와 충돌하면 강제 전환하지 말고 read-only 통합 계획만 보고하라.
```

이 문장을 실제로 입력하는 것은 위 **문서 통합 작업**에 대한 요청이다. 이후 remote compute, 설계 쓰기, 권한 변경, 제작 제출까지 포괄 승인하는 문장은 아니다.

## 2. 통합 이후 사용하는 문장

통합 PR이 별도로 검토·병합된 다음에는 [NEXT_WP_PROMPT.md](NEXT_WP_PROMPT.md)를 사용한다. 한 번의 개발 실행에는 하나의 WP만 진행하고, 결과마다 다음 WP·추천 모델·추론 강도·시작 프롬프트가 나온다.

실제 진행 상태를 모르면 임의로 WP-12 또는 F00부터 다시 시작하지 않는다. 이미 구현된 capability는 증거를 확인하여 대응시키고, 아직 없는 다음 작업 하나만 고른다.

## 3. 각 파일의 역할

| 파일/폴더 | 역할 |
|---|---|
| `IMPORT_PROMPT.md` | 기존 작업을 보존하면서 새 문서 체계를 넣는 첫 실행 |
| `CODEX_MASTER_PROMPT.md` | 새 공통 실행 계약. 검토 후 기존 계약에 병합하는 제안본 |
| `AGENTS_APPEND_TEMPLATE.md` | 현재 AGENTS.md에 필요한 부분만 병합할 읽기 순서 |
| `docs/ROADMAP.md` | 전체 개발 순서와 M0~M5 완주 목표 |
| `docs/WORK_PACKAGE_INDEX.md` | 신규 고유 작업 ID와 상세 prompt 탐색 |
| `phases/` | 분야별 목표·설계 방향·선행 조건 |
| `prompts/work_packages/` | 작업별 입력·산출물·테스트·권한·다음 실행 |
| `docs/*CONTRACTS*.md`, 기타 상세 문서 | 보안·복구·측정·PDK·검증 설계 원칙 |
| `templates/` | 승인 요청·작업 상태·보고서·측정·기술 계약 양식. 승인값이 아님 |
| `planning/` | 계획 카탈로그. 현재 저장소 상태를 대체하지 않음 |
| `archive/LEGACY_INPUTS.zip` | 되찾은 과거 파일 원본. 역사 자료이며 실행 지시/승인 아님 |
| `tools/verify_package.py` | 로컬 읽기 전용 패키지 무결성·참조·의존성 검사 |

## 4. 무엇을 바꾸고 무엇을 유지하는가

**교체 대상은 낡은 실행 문서의 충돌과 순서이지, 진행 중인 프로젝트·코드·승인 이력이 아니다.**

새 문서의 `ICF-xx-yy`는 통합 계획의 고유 ID다. 기존 `WP-12`와 `P0-01`은 별도 namespace로 보존한다. 실제 현재 작업은 저장소에서 확인하여 매핑한다.

`PROJECT_STATE.md`를 덮어쓰는 완성형 파일은 패키지에 넣지 않았다. `templates/PROJECT_STATE_MIGRATION.template.json`은 미확인 상태를 표현하는 양식이고, 기존 상태를 읽은 뒤 필요한 필드만 추가한다.

## 5. 현재 확실한 것과 아닌 것

이 대화의 원본 파일들은 복구했다. 2026-08-31 기록에는 v1.0.0과 fixed Spectre baseline이 보고되어 있다. 2026-09-05 GitHub 메타데이터 조회는 404였으므로 최신 HEAD·공개/비공개·현재 완료 WP는 이 패키지 작성에서 재확인하지 못했다. 404를 삭제나 private 전환의 증거로 쓰지 않는다.

실제 Windows/CentOS/Cadence E2E는 이번 문서 생성에서 실행하지 않았다. 패키지 무결성 테스트와 실제 회로 검증을 구분한다.

## 6. 변하지 않는 사용자 제약

- 현재 연구 VDD는 **1.0 V**. 과거 0.8~1.2 V 예시를 승인 범위로 해석하지 않는다.
- 300m/650m과 370m/650m은 출처·조건을 연결해 compatibility/scientific baseline으로 나눌 수 있다. 기억으로 전역 교체하지 않는다.
- CentOS 6.5/Python 2.6.6과 Cadence 설치를 in-place 업그레이드하지 않는다.
- source/PDK 및 기존 실패·복구 증거를 보존한다.
- actual ADE/sweep부터 점진적으로 구현하되, 전체 목표를 임의로 축소하지 않는다.
- MyChip 상세 사양은 공식 배포 PDK와 해당 제작 프로그램 자료로만 확정한다.
- 최종 제출·주문·비용·waiver·실험실 위험 작업에는 별도 사람 승인이 필요하다.

## 7. 모델 선택

첫 통합 작업은 계정에서 선택 가능할 때 **GPT-5.6 Sol / High**를 제안한다. 실제 UI/CLI 표시와 지원 여부를 먼저 확인한다. 복잡한 권한·legacy API·복구는 `Extra High` 또는 지원되는 높은 설정으로 올릴 수 있지만, 모든 작업에 Max/Ultra를 강제하지 않는다. 자세한 매핑과 fallback은 [docs/MODEL_MATRIX.md](docs/MODEL_MATRIX.md)에 있다.

## 8. 보관과 검증

Windows Python이 이미 있으면 패키지 폴더에서 다음을 실행할 수 있다. 설치·SSH·GitHub 변경은 하지 않는 검사다.

```powershell
python .\tools\verify_package.py
```

`PASS`는 ZIP에서 복구한 **문서 패키지**가 일관되다는 뜻이지, Cadence 회로/DRC가 통과했다는 뜻이 아니다. ZIP과 별도 SHA-256 파일을 같이 보관한다.
